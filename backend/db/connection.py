from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import settings


class DatabaseManager:
    """Owns the async SQLAlchemy engine and session factory."""

    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self.engine: AsyncEngine | None = None
        self.session_factory: async_sessionmaker[AsyncSession] | None = None

    def initialize(self) -> None:
        if self.engine is not None and self.session_factory is not None:
            return

        self.engine = create_async_engine(
            self.database_url,
            pool_pre_ping=True,
            future=True,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            autoflush=False,
        )

    async def dispose(self) -> None:
        if self.engine is not None:
            await self.engine.dispose()
            self.engine = None
            self.session_factory = None

    async def healthcheck(self) -> bool:
        self.initialize()
        assert self.engine is not None

        async with self.engine.begin() as connection:
            await connection.execute(text("SELECT 1"))

        return True

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        self.initialize()
        assert self.session_factory is not None

        session = self.session_factory()
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# Shared singleton used by FastAPI lifespan, routes, tools, and agent loop.
db_manager = DatabaseManager(settings.database_url)
