from collections import deque
from datetime import datetime, timezone
import logging
import logging.config
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from starlette.types import ASGIApp, Message, Receive, Scope, Send
import yaml

from app.json_codec import dump_json, load_json


request_logger = logging.getLogger("marketplace.requests")
MAX_BODY_LOG_BYTES = 65536
REDACTED = "[REDACTED]"


def configure_logging() -> None:
    """Configure one JSON console handler and suppress duplicate access logs and exception details."""
    path = Path(__file__).with_name("logging.yaml")
    logging.config.dictConfig(yaml.safe_load(path.read_text(encoding="utf-8")))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        """Serialize one JSON line, escaping lone surrogates for safe UTF-8 output without tracebacks."""
        if hasattr(record, "request_event"):
            line = dump_json(record.request_event)
        else:
            line = dump_json({
                "event": "server", "timestamp": datetime.now(timezone.utc).isoformat(),
                "level": record.levelname,
                "message": "Unhandled server exception" if record.exc_info else record.getMessage(),
            })
        return line.encode("utf-8", errors="backslashreplace").decode("utf-8")


def redact_body(value: Any, depth: int = 0) -> Any:
    """Mask sensitive JSON keys recursively and omit subtrees beyond a bounded nesting depth."""
    if depth >= 16:
        return {"_omitted": "nesting_limit"}
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            normalized = "".join(character for character in key.casefold() if character.isalnum())
            sensitive = (any(part in normalized for part in ("password", "token", "secret"))
                         or normalized in {"authorization", "cookie", "setcookie", "apikey"})
            result[key] = REDACTED if sensitive else redact_body(item, depth + 1)
        return result
    if isinstance(value, list):
        return [redact_body(item, depth + 1) for item in value]
    return value


def logged_body(raw: bytes, reason: str | None) -> Any:
    """Return redacted JSON or an omission marker without exposing malformed, oversized or scalar bodies."""
    if reason is not None:
        return {"_omitted": reason}
    if not raw:
        return None
    try:
        value = load_json(raw)
    except (ValueError, RecursionError):
        return {"_omitted": "invalid_json"}
    if not isinstance(value, dict):
        return {"_omitted": "non_object_json"}
    return redact_body(value)


async def capture_body(receive: Receive) -> tuple[Receive, bytes, str | None]:
    """Read a bounded logging prefix and replay identical ASGI messages before forwarding the remaining stream."""
    pending: deque[Message] = deque()
    raw = bytearray()
    reason = None
    while True:
        message = await receive()
        pending.append(message)
        if message["type"] == "http.disconnect":
            reason = "incomplete_body"
            break
        if message["type"] != "http.request":
            continue
        chunk = message.get("body", b"")
        if len(raw) + len(chunk) > MAX_BODY_LOG_BYTES:
            reason = "size_limit"
            break
        raw.extend(chunk)
        if not message.get("more_body", False):
            break

    async def replay() -> Message:
        """Replay cached messages without truncation, then continue reading from the original receive callable."""
        return pending.popleft() if pending else await receive()

    return replay, bytes(raw), reason


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        """Wrap the entire HTTP stack while forwarding lifespan and WebSocket scopes unchanged."""
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Attach a fresh UUID and emit one event after the response, including framework-generated errors."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = perf_counter()
        timestamp = datetime.now(timezone.utc).isoformat()
        request_id = str(uuid4())
        state = scope.setdefault("state", {})
        state["request_id"], state["user_id"] = request_id, None
        status_code, complete = 500, False
        raw, reason = b"", None
        mutating = scope["method"] in {"POST", "PUT", "DELETE"}

        async def observe_send(message: Message) -> None:
            """Observe the actual status and add the same generated request ID to every response start."""
            nonlocal status_code, complete
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = [(key, value) for key, value in message.get("headers", []) if key.lower() != b"x-request-id"]
                message = {**message, "headers": [*headers, (b"x-request-id", request_id.encode("ascii"))]}
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body", False):
                complete = True

        try:
            if mutating:
                receive, raw, reason = await capture_body(receive)
            await self.app(scope, receive, observe_send)
        finally:
            event = {
                "event": "http_request", "request_id": request_id,
                "method": scope["method"], "endpoint": scope["path"], "status_code": status_code,
                "duration_ms": round((perf_counter() - started) * 1000, 3),
                "user_id": state["user_id"], "timestamp": timestamp, "response_complete": complete,
            }
            if mutating:
                event["request_body"] = logged_body(raw, reason)
            request_logger.info("HTTP request", extra={"request_event": event})


class LoggedFastAPI(FastAPI):
    def build_middleware_stack(self) -> ASGIApp:
        """Place request logging outside ServerErrorMiddleware so HTTP 500 responses carry the same ID."""
        return RequestLoggingMiddleware(super().build_middleware_stack())
