from uuid import UUID

from marketplace_api.models.error_code import ErrorCode
from marketplace_api.models.product_create import ProductCreate
from marketplace_api.models.product_response import ProductResponse
from marketplace_api.models.product_page import ProductPage
from marketplace_api.models.product_status import ProductStatus
from marketplace_api.models.product_update import ProductUpdate
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiException
from app.models import Product, User


def product_response(product: Product) -> ProductResponse:
    """Map persisted product fields explicitly to the generated public response DTO."""
    return ProductResponse(
        id=product.id, name=product.name, description=product.description,
        price=product.price, stock=product.stock, category=product.category,
        status=product.status, seller_id=product.seller_id,
        created_at=product.created_at, updated_at=product.updated_at,
    )


async def create_product(data: ProductCreate, user: User, session: AsyncSession) -> ProductResponse:
    """Commit a product owned by the actor or an explicitly chosen seller for ADMIN."""
    if data.seller_id is not None and user.role != "ADMIN":
        raise ApiException(403, ErrorCode.ACCESS_DENIED, "Only ADMIN may specify seller_id")
    async with session.begin():
        owner_id = user.id
        if data.seller_id is not None:
            owner = await session.scalar(
                select(User).where(User.id == data.seller_id).with_for_update(read=True)
            )
            if owner is None or owner.role != "SELLER":
                raise ApiException(
                    400, ErrorCode.VALIDATION_ERROR, "Invalid seller_id",
                    {"violations": [{"field": "body.seller_id", "message": "Must identify an existing SELLER", "type": "value_error"}]},
                )
            owner_id = owner.id
        product = Product(
            name=data.name, description=data.description, price=data.price,
            stock=data.stock, category=data.category, status=data.status.value,
            seller_id=owner_id,
        )
        session.add(product)
        await session.flush()
        response = product_response(product)
    return response


async def find_product(product_id: UUID, session: AsyncSession, *, for_update: bool = False) -> Product:
    """Find a product or raise HTTP 404, optionally locking its row until transaction end."""
    product = await session.get(Product, product_id, with_for_update=True if for_update else None)
    if product is None:
        raise ApiException(
            404, ErrorCode.PRODUCT_NOT_FOUND, "Product not found", {"product_id": str(product_id)}
        )
    return product


async def get_product(product_id: UUID, session: AsyncSession) -> ProductResponse:
    """Return any stored product, including archived products, or a contract HTTP 404."""
    return product_response(await find_product(product_id, session))


async def list_products(
    page: int, size: int, status: ProductStatus | None, category: str | None, session: AsyncSession
) -> ProductPage:
    """Count and page identically filtered products within one repeatable-read snapshot."""
    filters = []
    if status is not None:
        filters.append(Product.status == status.value)
    if category is not None:
        filters.append(Product.category == category)
    async with session.begin():
        await session.connection(execution_options={"isolation_level": "REPEATABLE READ"})
        total = await session.scalar(select(func.count()).select_from(Product).where(*filters))
        rows = [] if page * size >= total else await session.scalars(
            select(Product).where(*filters).order_by(Product.created_at, Product.id)
            .offset(page * size).limit(size)
        )
        response = ProductPage(
            content=[product_response(product) for product in rows],
            totalElements=total, page=page, size=size,
        )
    return response


async def editable_product(product_id: UUID, user: User, session: AsyncSession) -> Product:
    """Lock a product and allow only its SELLER owner or any ADMIN to mutate it."""
    product = await find_product(product_id, session, for_update=True)
    if user.role != "ADMIN" and (user.role != "SELLER" or product.seller_id != user.id):
        raise ApiException(403, ErrorCode.ACCESS_DENIED, "Access denied")
    return product


async def update_product(
    product_id: UUID, data: ProductUpdate, user: User, session: AsyncSession
) -> ProductResponse:
    """Replace every editable field atomically while preserving owner, ID and creation time."""
    async with session.begin():
        product = await editable_product(product_id, user, session)
        product.name = data.name
        product.description = data.description
        product.price = data.price
        product.stock = data.stock
        product.category = data.category
        product.status = data.status.value
        await session.flush()
        response = product_response(product)
    return response


async def archive_product(product_id: UUID, user: User, session: AsyncSession) -> None:
    """Archive an authorized product once without deleting its row or updating it on replay."""
    async with session.begin():
        product = await editable_product(product_id, user, session)
        if product.status != "ARCHIVED":
            product.status = "ARCHIVED"
            await session.flush()
