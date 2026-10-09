"""Shared fixtures: a disposable database per run and a rolled-back session per test."""

import asyncio
import copy
import json
import os
import uuid
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import asyncpg
import httpx
import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession
from sqlalchemy.pool import NullPool

from ews.api.app import create_app
from ews.api.dependencies import (
    get_air_quality_client,
    get_forecast_client,
    get_session,
    get_session_factory,
)
from ews.core.db import create_engine
from ews.core.settings import Settings
from ews.cycles.events import SessionFactory
from ews.districts.registry import sync_districts
from ews.sources.open_meteo import OpenMeteoForecastClient
from ews.sources.open_meteo_air_quality import OpenMeteoAirQualityClient

BACKEND_ROOT = Path(__file__).resolve().parent.parent

# Server used to create the disposable database; the user needs CREATEDB
ADMIN_URL = os.getenv(
    "EWS_TEST_ADMIN_DATABASE_URL", "postgresql://ews:ews@localhost:5434/postgres"
)

ADMIN_TOKEN = "test-admin-token"  # noqa: S105 - not a real credential

# One location of a real Open-Meteo response: three calm days in Lahore
RECORDED_FORECAST: dict[str, Any] = json.loads(
    (BACKEND_ROOT / "tests/fixtures/open_meteo_forecast_two_locations.json").read_text(
        encoding="utf-8"
    )
)[0]
RECORDED_AIR_QUALITY: dict[str, Any] = json.loads(
    (BACKEND_ROOT / "tests/fixtures/open_meteo_air_quality_lahore.json").read_text(
        encoding="utf-8"
    )
)
CALM_AIR_QUALITY = copy.deepcopy(RECORDED_AIR_QUALITY)
CALM_AIR_QUALITY["hourly"]["pm2_5"] = [0.0 for _ in CALM_AIR_QUALITY["hourly"]["pm2_5"]]


class Upstream:
    """Stand-in for Open-Meteo: counts calls and can be told how to answer."""

    def __init__(self) -> None:
        self.calls = 0
        self.requests: list[httpx.Request] = []
        self.failing = False
        # (lat, lon) as sent -> payload; None answers with the recorded forecast
        self.payload_for: Callable[[str, str], dict[str, Any]] | None = None
        self.air_quality: Upstream | None = None
        self.fail_on_call: int | None = None

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        self.requests.append(request)
        if self.failing or self.calls == self.fail_on_call:
            body = {"error": True, "reason": "unavailable"}
            return httpx.Response(503, json=body)
        latitudes = request.url.params["latitude"].split(",")
        longitudes = request.url.params["longitude"].split(",")
        payloads = [
            self.payload_for(lat, lon) if self.payload_for else RECORDED_FORECAST
            for lat, lon in zip(latitudes, longitudes, strict=True)
        ]
        # Open-Meteo sends a bare object for one location, a list for several
        body_out: Any = payloads[0] if len(payloads) == 1 else payloads
        return httpx.Response(200, json=body_out)


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
def open_session(db_session: AsyncSession) -> SessionFactory:
    """Factory for further sessions on the test's connection.

    What they write is rolled back with everything else. Unlike sessions on
    their own connections, their commits are also undone when the test's main
    session rolls back.
    """

    def open_session() -> AsyncSession:
        return AsyncSession(
            bind=db_session.bind,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

    return open_session


@pytest.fixture
def app(
    database_url: str, db_session: AsyncSession, open_session: SessionFactory
) -> FastAPI:
    """Application wired to the test's rolled-back session."""
    settings = Settings(
        environment="test",
        database_url=database_url,
        admin_token=ADMIN_TOKEN,
        run_events_poll_seconds=0.01,
    )
    app = create_app(settings)

    async def override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_session_factory] = lambda: open_session
    return app


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    """HTTP client that calls the application in-process."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


@pytest.fixture
async def upstream(app: FastAPI) -> AsyncIterator[Upstream]:
    """Route the application's forecast client to a stand-in for Open-Meteo."""
    upstream = Upstream()
    transport = httpx.MockTransport(upstream.handle)
    air_upstream = Upstream()
    air_upstream.payload_for = lambda _lat, _lon: CALM_AIR_QUALITY
    air_transport = httpx.MockTransport(air_upstream.handle)
    async with (
        httpx.AsyncClient(transport=transport) as http,
        httpx.AsyncClient(transport=air_transport) as air_http,
    ):
        forecast_client = OpenMeteoForecastClient(http, base_url="https://weather.test")
        air_quality_client = OpenMeteoAirQualityClient(
            air_http, base_url="https://air.test"
        )
        app.dependency_overrides[get_forecast_client] = lambda: forecast_client
        app.dependency_overrides[get_air_quality_client] = lambda: air_quality_client
        upstream.air_quality = air_upstream
        yield upstream
