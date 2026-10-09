"""Tests for the health endpoint."""

from collections.abc import AsyncIterator

import httpx
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.pool import NullPool

from ews.api.dependencies import get_llm_gateway, get_session
from ews.core.db import create_engine
from tests.conftest import Model, llm_gateway_answering

# Nothing listens on port 1, so connections are refused immediately
UNREACHABLE_DATABASE_URL = "postgresql+asyncpg://ews:ews@127.0.0.1:1/ews"


class TestHealth:
    """Test cases for GET /api/health"""

    async def test_reports_healthy_when_database_is_reachable(
        self, client: AsyncClient, model: Model
    ) -> None:
        model.loaded = True

        response = await client.get("/api/health")

        assert response.status_code == 200
        assert response.json() == {
            "status": "healthy",
            "checks": {
                "database": {"status": "pass", "message": "reachable"},
                "llm": {"status": "pass", "message": "lm_studio: qwen-test is loaded"},
            },
        }

    async def test_stays_healthy_when_the_llm_provider_is_down(
        self, app: FastAPI
    ) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        app.dependency_overrides[get_llm_gateway] = lambda: llm_gateway_answering(
            refuse
        )

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/api/health")

        body = response.json()
        assert response.status_code == 200
        assert body["status"] == "healthy"
        assert body["checks"]["llm"] == {
            "status": "fail",
            "message": "lm_studio: unreachable",
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
