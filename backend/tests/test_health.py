"""Tests for the health endpoint."""

from collections.abc import AsyncIterator

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import NullPool

from ews.api.dependencies import get_session
from ews.core.db import create_engine

# Nothing listens on port 1, so connections are refused immediately
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://ews:ews@127.0.0.1:1/ews"


class TestHealth:
    """Test cases for GET /api/health"""

    async def test_reports_healthy_when_database_is_reachable(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/health")

        assert response.status_code == 200
        assert response.json() == {
            "status": "healthy",
            "checks": {"database": {"status": "pass", "message": "reachable"}},
        }

    async def test_reports_unhealthy_when_database_is_unreachable(
        self, app: FastAPI
    ) -> None:
        engine = create_engine(UNREACHABLE_DATABASE_URL, poolclass=NullPool)

        async def unreachable_session() -> AsyncIterator[AsyncSession]:
            async with AsyncSession(engine) as session:
                yield session

        app.dependency_overrides[get_session] = unreachable_session

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/health")

        body = response.json()
        assert response.status_code == 503
        assert body["status"] == "unhealthy"
        assert body["checks"]["database"]["status"] == "fail"
