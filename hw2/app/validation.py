from datetime import datetime, timezone
from decimal import Decimal
import re


def require_number(value: object) -> int | float | Decimal:
    """Reject booleans and strings where the contract requires a JSON number."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise ValueError("Input must be a JSON number")
    return value


def require_datetime(value: object) -> str | datetime:
    """Accept RFC 3339 strings or aware Python datetimes, rejecting epoch numbers and naive dates."""
    if isinstance(value, datetime):
        if value.utcoffset() is not None:
            return value
    elif isinstance(value, str) and re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}[Tt][0-9]{2}:[0-9]{2}:[0-9]{2}"
        r"(?:\.[0-9]+)?(?:[Zz]|[+-][0-9]{2}:[0-9]{2})", value,
    ):
        return value
    raise ValueError("Input must be a date-time with a timezone")


def normalize_utc_datetime(value: datetime, *, minimum: str, maximum: str) -> datetime:
    """Normalize an aware instant to UTC and reject values outside the contract's UTC range."""
    try:
        normalized = value.astimezone(timezone.utc)
    except OverflowError as exc:
        raise ValueError("Date-time must be representable in UTC within years 1 through 9999") from exc
    if not datetime.fromisoformat(minimum) <= normalized <= datetime.fromisoformat(maximum):
        raise ValueError(f"Date-time in UTC must be between {minimum} and {maximum}")
    return normalized
