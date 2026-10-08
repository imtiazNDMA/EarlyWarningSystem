"""Async database engine, session factory and declarative base."""

from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for ORM models; Alembic reads its metadata."""


def create_engine(database_url: str, **kwargs: Any) -> AsyncEngine:
    """Create an async engine for the given database URL.

    Args:
        database_url: SQLAlchemy URL using the asyncpg driver
        **kwargs: Extra options passed to SQLAlchemy, such as ``poolclass``

    Returns:
        The engine; the caller is responsible for disposing it
    """
    return create_async_engine(database_url, pool_pre_ping=True, **kwargs)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create a factory for sessions bound to the engine."""
    return async_sessionmaker(engine, expire_on_commit=False)
