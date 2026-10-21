import time
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any
from uuid import UUID, uuid4

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from marketplace_api.models.error_code import ErrorCode
from marketplace_api.models.token_pair import TokenPair
from starlette.concurrency import run_in_threadpool

from app.errors import ApiException
from app.models import User
from app.settings import AuthSettings

password_hasher = PasswordHasher()
bearer = HTTPBearer(auto_error=False)
# Unknown users still pay the password verification cost.
dummy_password_hash = password_hasher.hash(uuid4().hex)


async def hash_password(password: str) -> str:
    """Hash a password with Argon2id outside the event loop."""
    return await run_in_threadpool(password_hasher.hash, password)


async def verify_password(password_hash: str, password: str) -> bool:
    """Check an Argon2 hash without blocking the event loop or exposing failures."""
    try:
        return await run_in_threadpool(password_hasher.verify, password_hash, password)
    except (VerificationError, InvalidHashError):
        return False


def issue_token_pair(user: User, settings: AuthSettings) -> TokenPair:
    """Issue signed tokens with separate types, lifetimes and random identifiers."""
    now = datetime.now(timezone.utc)

    def encode(token_type: str, seconds: int) -> str:
        """Sign the claims for one token using the fixed HS256 algorithm."""
        return jwt.encode(
            {
                "sub": str(user.id),
                "role": user.role,
                "token_type": token_type,
                "jti": str(uuid4()),
                "iss": settings.issuer,
                "aud": settings.audience,
                "iat": now,
                "exp": now + timedelta(seconds=seconds),
            },
            settings.secret,
            algorithm="HS256",
        )

    return TokenPair(
        access_token=encode("access", settings.access_seconds),
        refresh_token=encode("refresh", settings.refresh_seconds),
        token_type="bearer",
        expires_in=settings.access_seconds,
    )


def token_error(code: ErrorCode = ErrorCode.TOKEN_INVALID) -> ApiException:
    """Create a contract authentication error with the Bearer challenge header."""
    message = "Access token expired" if code == ErrorCode.TOKEN_EXPIRED else "Invalid access token"
    return ApiException(401, code, message, headers={"WWW-Authenticate": "Bearer"})


def decode_token(token: str, settings: AuthSettings, expected_type: str) -> dict[str, Any]:
    """Verify shared JWT claims and map failures according to the expected token type."""
    try:
        claims = jwt.decode(
            token,
            settings.secret,
            algorithms=["HS256"],
            issuer=settings.issuer,
            audience=settings.audience,
            options={
                "require": ["sub", "role", "token_type", "jti", "iss", "aud", "iat", "exp"],
                "verify_exp": False,
            },
        )
        UUID(claims["sub"])
        UUID(claims["jti"])
        if (
            claims["token_type"] != expected_type
            or claims["role"] not in ("USER", "SELLER", "ADMIN")
            or type(claims["iat"]) is not int
            or type(claims["exp"]) is not int
            or claims["exp"] <= claims["iat"]
        ):
            raise ValueError("Invalid access claims")
    except (jwt.InvalidTokenError, ValueError, TypeError, AttributeError) as exc:
        raise (refresh_error() if expected_type == "refresh" else token_error()) from exc
    if claims["exp"] <= time.time():
        raise refresh_error() if expected_type == "refresh" else token_error(ErrorCode.TOKEN_EXPIRED)
    return claims


def refresh_error() -> ApiException:
    """Return the same contract error for invalid, expired or consumed refresh tokens."""
    return ApiException(401, ErrorCode.REFRESH_TOKEN_INVALID, "Invalid refresh token")


def decode_access_token(token: str, settings: AuthSettings) -> dict[str, Any]:
    """Accept only a signed, well-formed and unexpired access token."""
    return decode_token(token, settings, "access")


def decode_refresh_token(token: str, settings: AuthSettings) -> dict[str, Any]:
    """Accept only a signed, well-formed and unexpired refresh token."""
    return decode_token(token, settings, "refresh")


async def get_current_user(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
) -> User:
    """Resolve identity in a short session and release its connection before business work."""
    if credentials is None:
        raise token_error()
    claims = decode_access_token(credentials.credentials, request.app.state.auth_settings)
    async with request.app.state.database.sessions() as session:
        user = await session.get(User, UUID(claims["sub"]))
        if user is None or user.role != claims["role"]:
            raise token_error()
        session.expunge(user)
    request.state.user_id = str(user.id)
    return user


def require_roles(*roles: str):
    """Build a dependency that checks the current user's permitted operation roles."""
    async def check(user: Annotated[User, Depends(get_current_user)]) -> User:
        """Reject forbidden roles before invoking the operation handler."""
        if roles and user.role not in roles:
            raise ApiException(403, ErrorCode.ACCESS_DENIED, "Access denied")
        return user

    return check
