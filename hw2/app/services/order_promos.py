from datetime import datetime
from decimal import Decimal, ROUND_DOWN, ROUND_HALF_UP
from uuid import UUID

from marketplace_api.models.error_code import ErrorCode
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiException
from app.models import PromoCode


async def lock_promo(session: AsyncSession, *, code: str | None = None, promo_id: UUID | None = None) -> PromoCode:
    """Lock a promo after product locks, returning only the committed configuration after any wait."""
    condition = PromoCode.code == code if code is not None else PromoCode.id == promo_id
    promo = await session.scalar(select(PromoCode).where(condition).with_for_update())
    if promo is None:
        raise ApiException(422, ErrorCode.PROMO_CODE_INVALID, "Promo code is invalid")
    return promo


def validate_promo(promo: PromoCode, now: datetime, *, reserved: bool = False) -> None:
    """Check inclusive validity and capacity while counting an existing order's own reserved use."""
    if reserved and promo.current_uses <= 0:
        raise RuntimeError("Saved promo code has no reserved use")
    if (not promo.active or not promo.valid_from <= now <= promo.valid_until
            or (not reserved and promo.current_uses >= promo.max_uses)):
        raise ApiException(422, ErrorCode.PROMO_CODE_INVALID, "Promo code is invalid")


def discounted_amounts(subtotal: Decimal, promo: PromoCode) -> tuple[Decimal, Decimal]:
    """Round discounts to cents, keeping percentage savings at or below the exact 70 percent ceiling."""
    cent = Decimal("0.01")
    if promo.discount_type == "PERCENTAGE":
        raw = subtotal * min(promo.discount_value, Decimal("70")) / Decimal("100")
        ceiling = (subtotal * Decimal("0.70")).quantize(cent, rounding=ROUND_DOWN)
        discount = min(raw.quantize(cent, rounding=ROUND_HALF_UP), ceiling)
    else:
        discount = min(promo.discount_value, subtotal).quantize(cent, rounding=ROUND_HALF_UP)
    return subtotal - discount, discount


def release_use(promo: PromoCode) -> None:
    """Return exactly one reserved use without validating dates or silently allowing a negative counter."""
    if promo.current_uses <= 0:
        raise RuntimeError("Saved promo code has no reserved use")
    promo.current_uses -= 1


async def apply_new_promo(code: str | None, subtotal: Decimal, session: AsyncSession) -> tuple[UUID | None, Decimal, Decimal]:
    """Validate and reserve one new promo use together with the surrounding order transaction."""
    if code is None:
        return None, subtotal, Decimal("0.00")
    promo = await lock_promo(session, code=code)
    now = await session.scalar(select(func.clock_timestamp()))
    validate_promo(promo, now)
    if subtotal < promo.min_order_amount:
        raise ApiException(422, ErrorCode.PROMO_CODE_MIN_AMOUNT, "Order amount is below the promo minimum",
                           {"min_order_amount": promo.min_order_amount, "order_amount": subtotal})
    total, discount = discounted_amounts(subtotal, promo)
    promo.current_uses += 1
    return promo.id, total, discount


async def recalculate_promo(
    promo_id: UUID | None, subtotal: Decimal, session: AsyncSession
) -> tuple[UUID | None, Decimal, Decimal]:
    """Retain an already reserved promo without incrementing it, or detach it below the minimum."""
    if promo_id is None:
        return None, subtotal, Decimal("0.00")
    promo = await lock_promo(session, promo_id=promo_id)
    if subtotal < promo.min_order_amount:
        release_use(promo)
        return None, subtotal, Decimal("0.00")
    now = await session.scalar(select(func.clock_timestamp()))
    validate_promo(promo, now, reserved=True)
    total, discount = discounted_amounts(subtotal, promo)
    return promo.id, total, discount
