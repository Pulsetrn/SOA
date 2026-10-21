from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from marketplace_api.models.api_error import ApiError
from marketplace_api.models.error_code import ErrorCode
from starlette.exceptions import HTTPException
from starlette.responses import Response

from app.http import DecimalJSONResponse


class ApiException(Exception):
    def __init__(
        self,
        status_code: int,
        error_code: ErrorCode,
        message: str,
        details: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        """Carry an HTTP status and contract error data through application layers."""
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details
        self.headers = headers


async def handle_api_error(_request: Request, exc: ApiException) -> Response:
    """Serialize an application error using the generated error DTO."""
    error = ApiError(
        error_code=exc.error_code, message=exc.message, details=exc.details
    )
    return DecimalJSONResponse(error, status_code=exc.status_code, headers=exc.headers)


async def handle_validation_error(
    _request: Request, exc: RequestValidationError
) -> Response:
    """Return HTTP 400 with field violations, without exposing submitted values."""
    violations = [
        {
            "field": ".".join(str(part) for part in error["loc"]),
            "message": error["msg"],
            "type": error["type"],
        }
        for error in exc.errors()
    ]
    error = ApiError(
        error_code=ErrorCode.VALIDATION_ERROR,
        message="Request validation failed",
        details={"violations": violations},
    )
    return DecimalJSONResponse(error, status_code=400)


async def handle_http_error(_request: Request, exc: HTTPException) -> Response:
    """Normalize framework HTTP errors while preserving status and headers."""
    error = ApiError(error_code=ErrorCode.HTTP_ERROR, message=str(exc.detail))
    return DecimalJSONResponse(error, status_code=exc.status_code, headers=exc.headers)


async def handle_unexpected_error(_request: Request, _exc: Exception) -> Response:
    """Return a generic HTTP 500 without exposing implementation details."""
    error = ApiError(
        error_code=ErrorCode.INTERNAL_ERROR, message="An unexpected error occurred"
    )
    return DecimalJSONResponse(error, status_code=500)


def register_error_handlers(app: FastAPI) -> None:
    """Install the shared error format for application and framework failures."""
    app.add_exception_handler(ApiException, handle_api_error)
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(HTTPException, handle_http_error)
    app.add_exception_handler(Exception, handle_unexpected_error)
