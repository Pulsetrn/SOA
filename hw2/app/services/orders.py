from uuid import UUID
from collections.abc import Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from math import ceil

from marketplace_api.models.error_code import ErrorCode
from marketplace_api.models.order_item_response import OrderItemResponse
from marketplace_api.models.order_create import OrderCreate
from marketplace_api.models.order_response import OrderResponse
from marketplace_api.models.order_status import OrderStatus
from marketplace_api.models.order_status_change import OrderStatusChange
from marketplace_api.models.order_update import OrderUpdate
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiException
from app.models import Order, OrderItem, Product, User, UserOperation
from app.security import token_error
from app.settings import OrderSettings
from app.services import order_promos


ALLOWED_TRANSITIONS = {
    OrderStatus.CREATED: frozenset({OrderStatus.PAYMENT_PENDING, OrderStatus.CANCELED}),
    OrderStatus.PAYMENT_PENDING: frozenset({OrderStatus.PAID, OrderStatus.CANCELED}),
    OrderStatus.PAID: frozenset({OrderStatus.SHIPPED}),
    OrderStatus.SHIPPED: frozenset({OrderStatus.COMPLETED}),
    OrderStatus.COMPLETED: frozenset(),
    OrderStatus.CANCELED: frozenset(),
}


def ensure_transition(current: OrderStatus, target: OrderStatus) -> None:
    """Reject every state change outside the forward chain or the two allowed cancellations."""
    if target not in ALLOWED_TRANSITIONS[current]:
        raise ApiException(
            409, ErrorCode.INVALID_STATE_TRANSITION, "Invalid order state transition",
            {"current_status": current.value, "target_status": target.value},
        )


async def get_order(order_id: UUID, user: User, session: AsyncSession) -> OrderResponse:
    """Read the header and price snapshots in one SQL snapshot, enforcing owner or ADMIN access."""
    rows = (await session.execute(
        select(Order, OrderItem).outerjoin(OrderItem, OrderItem.order_id == Order.id)
        .where(Order.id == order_id).order_by(OrderItem.id)
    )).all()
    if not rows:
        raise ApiException(404, ErrorCode.ORDER_NOT_FOUND, "Order not found", {"order_id": str(order_id)})
    order = rows[0][0]
    if user.role != "ADMIN" and (user.role != "USER" or order.user_id != user.id):
        raise ApiException(403, ErrorCode.ORDER_OWNERSHIP_VIOLATION, "Order belongs to another user")
    return order_response(order, [item for _, item in rows if item is not None])


def order_response(order: Order, items: Sequence[OrderItem]) -> OrderResponse:
    """Map stored order values to generated DTOs with a stable position order."""
    return OrderResponse(
        id=order.id, user_id=order.user_id, status=order.status, promo_code_id=order.promo_code_id,
        total_amount=order.total_amount, discount_amount=order.discount_amount,
        created_at=order.created_at, updated_at=order.updated_at,
        items=[OrderItemResponse(
            id=item.id, product_id=item.product_id, quantity=item.quantity, price_at_order=item.price_at_order,
        ) for item in sorted(items, key=lambda row: row.id)],
    )


def ensure_creation_interval(last: datetime, now: datetime, interval: timedelta) -> None:
    """Reject creation before the exact interval boundary and return a usable retry delay."""
    ensure_operation_interval(last, now, interval, "CREATE_ORDER")


def ensure_operation_interval(last: datetime, now: datetime, interval: timedelta, operation_type: str) -> None:
    """Enforce an operation-specific interval with an exact boundary and rounded retry delay."""
    if interval and now - last < interval:
        remaining = max(1, ceil((interval - (now - last)).total_seconds()))
        raise ApiException(
            429, ErrorCode.ORDER_LIMIT_EXCEEDED, "Order operation limit exceeded",
            {"operation_type": operation_type, "retry_after_seconds": remaining},
            headers={"Retry-After": str(remaining)},
        )


async def check_creation_limits(user_id: UUID, session: AsyncSession, settings: OrderSettings) -> None:
    """Check successful creation history before checking for an active order under the actor lock."""
    last = await session.scalar(
        select(UserOperation.created_at)
        .where(UserOperation.user_id == user_id, UserOperation.operation_type == "CREATE_ORDER")
        .order_by(UserOperation.created_at.desc()).limit(1)
    )
    if last is not None:
        now = await session.scalar(select(func.clock_timestamp()))
        ensure_creation_interval(last, now, settings.interval)
    active = await session.scalar(
        select(Order.id).where(Order.user_id == user_id, Order.status.in_(["CREATED", "PAYMENT_PENDING"]))
        .limit(1)
    )
    if active is not None:
        raise ApiException(409, ErrorCode.ORDER_HAS_ACTIVE, "User already has an active order")


async def locked_catalog(data: OrderCreate, session: AsyncSession) -> dict[UUID, Product]:
    """Lock products in UUID order, validate the entire catalog, then collect all stock deficits."""
    products = await lock_products([item.product_id for item in data.items], session)
    validate_catalog(data, products, {key: row.stock for key, row in products.items()})
    return products


async def lock_products(product_ids: Sequence[UUID], session: AsyncSession) -> dict[UUID, Product]:
    """Acquire the full set of product locks in a common UUID order before changing stock."""
    rows = await session.scalars(
        select(Product).where(Product.id.in_(product_ids))
        .order_by(Product.id).with_for_update()
    )
    return {row.id: row for row in rows}


def validate_catalog(data: OrderCreate | OrderUpdate, products: dict[UUID, Product], available: dict[UUID, int]) -> None:
    """Check all requested products before reporting every deficit against the supplied availability."""
    for item in data.items:
        product = products.get(item.product_id)
        if product is None:
            raise ApiException(404, ErrorCode.PRODUCT_NOT_FOUND, "Product not found", {"product_id": str(item.product_id)})
        if product.status != "ACTIVE":
            raise ApiException(409, ErrorCode.PRODUCT_INACTIVE, "Product is not active", {"product_id": str(item.product_id)})
    deficits = [
        {"product_id": str(item.product_id), "requested_quantity": item.quantity,
         "available_stock": available[item.product_id]}
        for item in data.items if available[item.product_id] < item.quantity
    ]
    if deficits:
        raise ApiException(409, ErrorCode.INSUFFICIENT_STOCK, "Insufficient product stock", {"products": deficits})


async def lock_actor(user: User, session: AsyncSession) -> User:
    """Serialize actor operations and revalidate identity after waiting for the user row lock."""
    actor = await session.get(User, user.id, with_for_update=True)
    if actor is None or actor.role != user.role:
        raise token_error()
    if actor.role not in {"USER", "ADMIN"}:
        raise ApiException(403, ErrorCode.ACCESS_DENIED, "Access denied")
    return actor


def checked_total(quantities: dict[UUID, int], prices: dict[UUID, Decimal]) -> Decimal:
    """Compute exact item cost and reject an aggregate outside the order storage range."""
    total = sum((prices[key] * quantity for key, quantity in quantities.items()), Decimal("0.00"))
    if total > Decimal("9999999999.99"):
        raise ApiException(
            400, ErrorCode.VALIDATION_ERROR, "Order total exceeds storage range",
            {"violations": [{"field": "body.items", "message": "Total must not exceed 9999999999.99", "type": "value_error"}]},
        )
    return total


async def create_order(
    data: OrderCreate, user: User, session: AsyncSession, settings: OrderSettings
) -> OrderResponse:
    """Commit stock reservation, snapshots, total and successful history together after ordered checks."""
    try:
        async with session.begin():
            actor = await lock_actor(user, session)
            await check_creation_limits(actor.id, session, settings)
            products = await locked_catalog(data, session)
            for item in data.items:
                products[item.product_id].stock -= item.quantity
            total = checked_total(
                {item.product_id: item.quantity for item in data.items},
                {key: product.price for key, product in products.items()},
            )
            promo_id, total, discount = await order_promos.apply_new_promo(data.promo_code, total, session)
            order = Order(user_id=actor.id, status="CREATED", promo_code_id=promo_id,
                          total_amount=total, discount_amount=discount)
            session.add(order)
            await session.flush()
            items = [OrderItem(
                order_id=order.id, product_id=item.product_id, quantity=item.quantity,
                price_at_order=products[item.product_id].price,
            ) for item in data.items]
            session.add_all(items)
            session.add(UserOperation(user_id=actor.id, operation_type="CREATE_ORDER", created_at=func.clock_timestamp()))
            await session.flush()
            response = order_response(order, items)
        return response
    except IntegrityError as exc:
        if exc.orig.sqlstate == "23505" and exc.orig.diag.constraint_name == "uq_orders_one_active_per_user":
            raise ApiException(409, ErrorCode.ORDER_HAS_ACTIVE, "User already has an active order") from exc
        raise


async def editable_order(order_id: UUID, actor: User, session: AsyncSession) -> Order:
    """Lock an existing order and check owner or ADMIN before state and frequency checks."""
    order = await session.get(Order, order_id, with_for_update=True)
    if order is None:
        raise ApiException(404, ErrorCode.ORDER_NOT_FOUND, "Order not found", {"order_id": str(order_id)})
    if actor.role != "ADMIN" and order.user_id != actor.id:
        raise ApiException(403, ErrorCode.ORDER_OWNERSHIP_VIOLATION, "Order belongs to another user")
    return order


async def check_update_limit(actor_id: UUID, session: AsyncSession, settings: OrderSettings) -> None:
    """Throttle successful updates by the requesting actor independently of creation history."""
    last = await session.scalar(
        select(UserOperation.created_at)
        .where(UserOperation.user_id == actor_id, UserOperation.operation_type == "UPDATE_ORDER")
        .order_by(UserOperation.created_at.desc()).limit(1)
    )
    if last is not None:
        now = await session.scalar(select(func.clock_timestamp()))
        ensure_operation_interval(last, now, settings.interval, "UPDATE_ORDER")


def apply_reservation(products: dict[UUID, Product], available: dict[UUID, int], requested: dict[UUID, int]) -> None:
    """Assign net stock after virtual return and reservation, rejecting final INTEGER overflow."""
    final = {key: available[key] - requested.get(key, 0) for key in products}
    overflow = [{"product_id": str(key), "stock_after_operation": value, "max_stock": 2147483647}
                for key, value in final.items() if value > 2147483647]
    if overflow:
        raise ApiException(409, ErrorCode.STOCK_RETURN_OVERFLOW, "Returned stock exceeds storage range", {"products": overflow})
    for key, product in products.items():
        product.stock = final[key]


async def update_order(
    order_id: UUID, data: OrderUpdate, user: User, session: AsyncSession, settings: OrderSettings
) -> OrderResponse:
    """Replace order contents atomically, preserving retained snapshots and returning the previous reserve."""
    async with session.begin():
        actor = await lock_actor(user, session)
        order = await editable_order(order_id, actor, session)
        if order.status != "CREATED":
            raise ApiException(409, ErrorCode.INVALID_STATE_TRANSITION, "Order can only be updated in CREATED",
                               {"current_status": order.status, "target_status": "CREATED"})
        await check_update_limit(actor.id, session, settings)
        old_items = list((await session.scalars(select(OrderItem).where(OrderItem.order_id == order.id))).all())
        previous = {item.product_id: item for item in old_items}
        requested = {item.product_id: item.quantity for item in data.items}
        products = await lock_products(sorted(set(previous) | set(requested)), session)
        available = {key: row.stock + (previous[key].quantity if key in previous else 0)
                     for key, row in products.items()}
        validate_catalog(data, products, available)
        prices = {key: previous[key].price_at_order if key in previous else products[key].price for key in requested}
        apply_reservation(products, available, requested)
        subtotal = checked_total(requested, prices)
        order.promo_code_id, order.total_amount, order.discount_amount = await order_promos.recalculate_promo(
            order.promo_code_id, subtotal, session,
        )
        order.updated_at = func.clock_timestamp()
        items = []
        for key, old in previous.items():
            if key not in requested:
                await session.delete(old)
        for key, quantity in requested.items():
            if key in previous:
                item = previous[key]
                item.quantity = quantity
            else:
                item = OrderItem(order_id=order.id, product_id=key, quantity=quantity, price_at_order=prices[key])
                session.add(item)
            items.append(item)
        session.add(UserOperation(user_id=actor.id, operation_type="UPDATE_ORDER", created_at=func.clock_timestamp()))
        await session.flush()
        response = order_response(order, items)
    return response


async def cancel_order(order_id: UUID, user: User, session: AsyncSession) -> OrderResponse:
    """Cancel an eligible order once, returning every reserved unit within the same transaction."""
    async with session.begin():
        actor = await lock_actor(user, session)
        order = await editable_order(order_id, actor, session)
        ensure_transition(OrderStatus(order.status), OrderStatus.CANCELED)
        items = list((await session.scalars(select(OrderItem).where(OrderItem.order_id == order.id))).all())
        reserved = {item.product_id: item.quantity for item in items}
        products = await lock_products(sorted(reserved), session)
        available = {key: row.stock + reserved[key] for key, row in products.items()}
        apply_reservation(products, available, {})
        if order.promo_code_id is not None:
            promo = await order_promos.lock_promo(session, promo_id=order.promo_code_id)
            order_promos.release_use(promo)
        order.status = "CANCELED"
        await session.flush()
        response = order_response(order, items)
    return response


async def change_order_status(
    order_id: UUID, data: OrderStatusChange, user: User, session: AsyncSession
) -> OrderResponse:
    """Advance the locked order by one main-chain edge as ADMIN, without changing its reserve."""
    async with session.begin():
        actor = await lock_actor(user, session)
        if actor.role != "ADMIN":
            raise ApiException(403, ErrorCode.ACCESS_DENIED, "Access denied")
        order = await editable_order(order_id, actor, session)
        current, target = OrderStatus(order.status), data.status
        if target == OrderStatus.CANCELED:
            raise ApiException(
                409, ErrorCode.INVALID_STATE_TRANSITION, "Cancellation requires the cancel operation",
                {"current_status": current.value, "target_status": target.value},
            )
        ensure_transition(current, target)
        order.status = target.value
        await session.flush()
        items = list((await session.scalars(select(OrderItem).where(OrderItem.order_id == order.id))).all())
        response = order_response(order, items)
    return response
