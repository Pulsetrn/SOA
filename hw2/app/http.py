from collections.abc import Callable, Coroutine
from typing import Any

from fastapi.exceptions import ResponseValidationError
from fastapi.routing import APIRoute
from pydantic import TypeAdapter, ValidationError
from starlette.requests import Request
from starlette.responses import Response

from app.json_codec import dump_json, load_json


class DecimalRequest(Request):
    async def json(self) -> Any:
        """Decode JSON fractions directly as Decimal before request validation."""
        if not hasattr(self, "_json"):
            self._json = load_json(await self.body())
        return self._json


class ContractRoute(APIRoute):
    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        """Use decimal-preserving JSON parsing for generated API routes."""
        original_handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            """Pass the request through FastAPI using our JSON decoder."""
            return await original_handler(DecimalRequest(request.scope, request.receive))

        return handle


class DecimalJSONResponse(Response):
    media_type = "application/json"

    def render(self, content: Any) -> bytes:
        """Write Decimal as exact JSON numbers and encode UUID and datetime values."""
        return dump_json(content).encode("utf-8")


def contract_response(value: Any, response_type: Any, status_code: int) -> Response:
    """Validate generated response types before preserving decimals in JSON output."""
    if isinstance(value, Response):
        return value
    try:
        validated = TypeAdapter(response_type).validate_python(value)
    except ValidationError as exc:
        raise ResponseValidationError(exc.errors(), body=value) from exc
    if status_code == 204:
        return Response(status_code=204)
    return DecimalJSONResponse(validated, status_code=status_code)
