import os
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import URL


@dataclass(frozen=True)
class DatabaseSettings:
    host: str
    port: int
    name: str
    user: str
    password: str = field(repr=False)

    @classmethod
    def from_env(cls) -> "DatabaseSettings":
        """Read database connection settings without exposing the password in repr."""
        port = int(os.environ.get("DB_PORT", "5432"))
        if not 1 <= port <= 65535:
            raise ValueError("DB_PORT must be between 1 and 65535")
        return cls(
            host=os.environ.get("DB_HOST", "db"),
            port=port,
            name=os.environ.get("DB_NAME", "marketplace"),
            user=os.environ.get("DB_USER", "marketplace"),
            password=os.environ.get("DB_PASSWORD", "marketplace_local"),
        )

    @property
    def url(self) -> URL:
        """Build a psycopg URL without manually escaping credentials."""
        return URL.create(
            "postgresql+psycopg",
            username=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
            database=self.name,
        )


@dataclass(frozen=True)
class AuthSettings:
    secret: str = field(repr=False)
    issuer: str = "marketplace-hw2"
    audience: str = "marketplace-api"
    access_seconds: int = 20 * 60
    refresh_seconds: int = 14 * 24 * 60 * 60

    @classmethod
    def from_env(cls) -> "AuthSettings":
        """Require an explicit signing secret with at least 32 UTF-8 bytes."""
        secret = os.environ.get("JWT_SECRET", "")
        if len(secret.encode("utf-8")) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 UTF-8 bytes")
        return cls(secret=secret)


@dataclass(frozen=True)
class OrderSettings:
    interval_minutes: int = 1

    @classmethod
    def from_env(cls) -> "OrderSettings":
        """Read a nonnegative operation interval; zero disables only the time-based limit."""
        value = int(os.environ.get("ORDER_OPERATION_INTERVAL_MINUTES", "1"))
        if value < 0:
            raise ValueError("ORDER_OPERATION_INTERVAL_MINUTES must be nonnegative")
        try:
            timedelta(minutes=value)
        except OverflowError as exc:
            raise ValueError("ORDER_OPERATION_INTERVAL_MINUTES is too large") from exc
        return cls(interval_minutes=value)

    @property
    def interval(self) -> timedelta:
        """Expose the configured interval for comparisons with database timestamps."""
        return timedelta(minutes=self.interval_minutes)
