from marketplace_api.models.error_code import ErrorCode
from marketplace_api.models.promo_code_create import PromoCodeCreate
from marketplace_api.models.promo_code_response import PromoCodeResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiException
from app.models import PromoCode, User
from app.security import token_error


def promo_response(promo: PromoCode) -> PromoCodeResponse:
    """Map persisted configuration and server-owned counters to the generated response DTO."""
    return PromoCodeResponse(
        id=promo.id, code=promo.code, discount_type=promo.discount_type,
        discount_value=promo.discount_value, min_order_amount=promo.min_order_amount,
        max_uses=promo.max_uses, current_uses=promo.current_uses,
        valid_from=promo.valid_from, valid_until=promo.valid_until, active=promo.active,
    )


async def create_promo_code(data: PromoCodeCreate, user: User, session: AsyncSession) -> PromoCodeResponse:
    """Create a globally unique promo configuration atomically after revalidating SELLER/ADMIN access."""
    try:
        async with session.begin():
            actor = await session.scalar(select(User).where(User.id == user.id).with_for_update(read=True))
            if actor is None or actor.role != user.role:
                raise token_error()
            if actor.role not in {"SELLER", "ADMIN"}:
                raise ApiException(403, ErrorCode.ACCESS_DENIED, "Access denied")
            promo = PromoCode(
                code=data.code, discount_type=data.discount_type.value, discount_value=data.discount_value,
                min_order_amount=data.min_order_amount, max_uses=data.max_uses,
                valid_from=data.valid_from, valid_until=data.valid_until,
                active=True if data.active is None else data.active,
            )
            session.add(promo)
            await session.flush()
            response = promo_response(promo)
    except IntegrityError as exc:
        if exc.orig.sqlstate == "23505" and exc.orig.diag.constraint_name == "uq_promo_codes_code":
            raise ApiException(409, ErrorCode.PROMO_CODE_ALREADY_EXISTS, "Promo code already exists") from exc
        raise
    return response
