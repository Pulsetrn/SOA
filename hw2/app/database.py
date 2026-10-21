from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.settings import AuthSettings, DatabaseSettings, OrderSettings


class Database:
    def __init__(self, settings: DatabaseSettings) -> None:
        """Create the async engine and session factory without creating database tables."""
        self.engine = create_async_engine(
            settings.url, pool_pre_ping=True, connect_args={"connect_timeout": 5}
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def check_connection(self) -> None:
        """Verify database availability before accepting API traffic."""
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def close(self) -> None:
        """Release pooled database connections during application shutdown."""
        await self.engine.dispose()


@asynccontextmanager
async def database_lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Connect on startup and dispose the engine even when startup fails."""
    app.state.auth_settings = AuthSettings.from_env()
    app.state.order_settings = OrderSettings.from_env()
    database = Database(DatabaseSettings.from_env())
    app.state.database = database
    try:
        await database.check_connection()
        yield
    finally:
        await database.close()
