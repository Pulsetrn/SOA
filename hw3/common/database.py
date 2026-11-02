import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


class Database:
    def __init__(self):
        self.engine = create_async_engine(
            os.environ["DATABASE_URL"], pool_pre_ping=True
        )
        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def check(self):
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def close(self):
        await self.engine.dispose()
