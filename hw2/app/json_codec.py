import json
from decimal import Decimal, DecimalException
from typing import Any

import simplejson
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel


def reject_json_constant(value: str) -> None:
    """Reject non-standard JSON numbers rather than accepting NaN or Infinity."""
    raise json.JSONDecodeError("Non-finite numbers are not valid JSON", value, 0)


def load_json(data: str | bytes | bytearray) -> Any:
    """Read JSON fractions as Decimal and normalize decoding failures to JSONDecodeError."""
    try:
        return json.loads(data, parse_float=Decimal, parse_constant=reject_json_constant)
    except json.JSONDecodeError:
        raise
    except (UnicodeDecodeError, ValueError, DecimalException) as exc:
        raise json.JSONDecodeError("Invalid JSON input", "", 0) from exc


def encode_json_value(value: Any) -> Any:
    """Encode model, UUID and datetime values without altering Decimal numbers."""
    if isinstance(value, BaseModel):
        return value.model_dump(mode="python", by_alias=True)
    return jsonable_encoder(value)


def dump_json(value: Any) -> str:
    """Write finite Decimal values as exact JSON numbers and retain Unicode text."""
    return simplejson.dumps(
        value, default=encode_json_value, use_decimal=True, allow_nan=False,
        ensure_ascii=False, separators=(",", ":"),
    )
