from typing import Any, Self

from pydantic import BaseModel, ValidationError

from app.json_codec import load_json


class ContractModel(BaseModel):
    @classmethod
    def model_validate_json(
        cls, json_data: str | bytes | bytearray, *, strict: bool | None = None,
        context: Any = None, by_alias: bool | None = None, by_name: bool | None = None,
    ) -> Self:
        """Preserve native JSON validation, then revalidate exact decimal input values."""
        try:
            parsed = load_json(json_data)
        except ValueError as exc:
            raise ValidationError.from_exception_data(
                cls.__name__, [{"type": "json_invalid", "loc": (), "input": json_data, "ctx": {"error": str(exc)}}]
            ) from exc
        # Native JSON mode preserves its own strict UUID/datetime and input-type rules.
        super().model_validate_json(
            json_data, strict=strict, context=context, by_alias=by_alias, by_name=by_name,
        )
        # Native mode may pass floats to field validators; validate the original numbers again.
        # Input types already passed native checks, so Python mode can parse JSON UUID/date strings.
        return cls.model_validate(
            parsed, strict=False, context=context, by_alias=by_alias, by_name=by_name,
        )
