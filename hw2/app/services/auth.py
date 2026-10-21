import hashlib
import hmac
from datetime import datetime, timezone
from uuid import UUID

from marketplace_api.models.error_code import ErrorCode
from marketplace_api.models.login_request import LoginRequest
from marketplace_api.models.register_request import RegisterRequest
from marketplace_api.models.refresh_request import RefreshRequest
from marketplace_api.models.token_pair import TokenPair
from marketplace_api.models.user_response import UserResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.errors import ApiException
from app.models import RefreshSession, User
from app.security import decode_refresh_token, dummy_password_hash, hash_password, issue_token_pair, refresh_error, verify_password
from app.settings import AuthSettings


async def register_user(data: RegisterRequest, session: AsyncSession) -> UserResponse:
    """Commit a user with a password hash and translate only username conflicts."""
    return await create_user(data.username, data.password, data.role.value if data.role is not None else "USER", session)


async def create_user(username: str, password: str, role: str, session: AsyncSession) -> UserResponse:
    """Create a user for validated registration or the trusted administrator command."""
    password_hash = await hash_password(password)
    try:
        async with session.begin():
            user = User(
                username=username,
                password_hash=password_hash,
                role=role,
            )
            session.add(user)
            await session.flush()
            response = UserResponse(
                id=user.id, username=user.username, role=user.role,
                created_at=user.created_at, updated_at=user.updated_at,
            )
    except IntegrityError as exc:
        if (
            getattr(exc.orig, "sqlstate", None) == "23505"
            and getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == "uq_users_username"
        ):
            raise ApiException(409, ErrorCode.USERNAME_TAKEN, "Username is already registered") from exc
        raise
    return response


async def store_refresh_session(pair: TokenPair, user: User, session: AsyncSession, settings: AuthSettings) -> None:
    """Store a refresh token digest and identity within the caller's transaction."""
    claims = decode_refresh_token(pair.refresh_token, settings)
    session.add(RefreshSession(
        jti=UUID(claims["jti"]), user_id=user.id,
        token_hash=hashlib.sha256(pair.refresh_token.encode()).hexdigest(),
        expires_at=datetime.fromtimestamp(claims["exp"], timezone.utc),
    ))
    await session.flush()


async def login(data: LoginRequest, session: AsyncSession, settings: AuthSettings) -> TokenPair:
    """Authenticate credentials and commit a refresh session before returning tokens."""
    async with session.begin():
        user = await session.scalar(select(User).where(User.username == data.username))
        password_hash = user.password_hash if user is not None else dummy_password_hash
        valid_password = await verify_password(password_hash, data.password)
        if user is None or not valid_password:
            raise ApiException(401, ErrorCode.INVALID_CREDENTIALS, "Invalid username or password")
        pair = issue_token_pair(user, settings)
        await store_refresh_session(pair, user, session, settings)
    return pair


async def refresh_tokens(data: RefreshRequest, session: AsyncSession, settings: AuthSettings) -> TokenPair:
    """Atomically consume one stored refresh token and commit its replacement."""
    claims = decode_refresh_token(data.refresh_token, settings)
    async with session.begin():
        stored = await session.scalar(
            select(RefreshSession).where(RefreshSession.jti == UUID(claims["jti"])).with_for_update()
        )
        now = datetime.now(timezone.utc)
        digest = hashlib.sha256(data.refresh_token.encode()).hexdigest()
        if (
            stored is None or stored.revoked_at is not None or stored.expires_at <= now
            or stored.user_id != UUID(claims["sub"])
            or not hmac.compare_digest(stored.token_hash, digest)
        ):
            raise refresh_error()
        user = await session.get(User, stored.user_id)
        if user is None or user.role != claims["role"]:
            raise refresh_error()
        stored.revoked_at = now
        pair = issue_token_pair(user, settings)
        await store_refresh_session(pair, user, session, settings)
    return pair
