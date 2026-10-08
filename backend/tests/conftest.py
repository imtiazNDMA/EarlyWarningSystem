"""Shared fixtures: a disposable database per run and a rolled-back session per test."""

import asyncio
import os
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import asyncpg
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.pool import NullPool

from ews.api.app import create_app
from ews.api.dependencies import get_session
from ews.core.db import create_engine
from ews.core.settings import Settings
from ews.districts.registry import sync_districts

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Server used to create the disposable database; the user needs CREATEDB
ADMIN_URL = os.getenv(
    "EWS_TEST_ADMIN_DATABASE_URL", "postgresql://ews:ews@localhost:5434/postgres"
)


def run_migrations(database_url: str) -> None:
    """Apply every Alembic migration to the given database."""
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(config, "head")


async def load_reference_data(database_url: str) -> None:
    """Commit the district registry, which every test may read but none changes."""
    engine = create_engine(database_url, poolclass=NullPool)
    try:
        async with AsyncSession(engine) as session:
            await sync_districts(session)
            await session.commit()
    finally:
        await engine.dispose()


@pytest.fixture(scope="session")
async def database_url() -> AsyncIterator[str]:
    """Create a uniquely named, migrated database and drop it after the run."""
    name = f"ews_test_{uuid.uuid4().hex[:12]}"

    admin = await asyncpg.connect(ADMIN_URL)
    try:
        await admin.execute(f'CREATE DATABASE "{name}"')
    finally:
        await admin.close()

    base = ADMIN_URL.rsplit("/", 1)[0].replace("postgresql://", "postgresql+asyncpg://")
    url = f"{base}/{name}"
    try:
        # Alembic's async env starts its own event loop, so run it off this one
        await asyncio.to_thread(run_migrations, url)
        await load_reference_data(url)
        yield url
    finally:
        admin = await asyncpg.connect(ADMIN_URL)
        try:
            await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()


@pytest.fixture(scope="session")
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    """Engine for the disposable database."""
    engine = create_engine(database_url, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Session whose work is rolled back, so no test sees another's data."""
    async with engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            await transaction.rollback()


@pytest.fixture
def app(database_url: str, db_session: AsyncSession) -> FastAPI:
    """Application wired to the test's rolled-back session."""
    app = create_app(Settings(environment="test", database_url=database_url))

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """HTTP client that calls the application in-process."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
