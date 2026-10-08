"""Tests for the district forecast endpoint and forecast ingestion."""

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ews.api.dependencies import get_forecast_client
from ews.forecasts.service import ingest_all_forecasts, store_snapshot
from ews.sources.models import SourceSnapshot
from ews.sources.open_meteo import SOURCE, OpenMeteoForecastClient

FIXTURES = Path(__file__).parent / "fixtures"
LAHORE_PAYLOAD: dict[str, Any] = json.loads(
    (FIXTURES / "open_meteo_forecast_two_locations.json").read_text(encoding="utf-8")
)[0]


class Upstream:
    """Stand-in for Open-Meteo: counts calls and can be switched to fail."""

    def __init__(self) -> None:
        self.calls = 0
        self.failing = False

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.calls += 1
        if self.failing:
            return httpx.Response(503, json={"error": True, "reason": "unavailable"})
        locations = len(request.url.params["latitude"].split(","))
        if locations == 1:
            return httpx.Response(200, json=LAHORE_PAYLOAD)
        return httpx.Response(200, json=[LAHORE_PAYLOAD] * locations)


@pytest.fixture
async def upstream(app: FastAPI) -> AsyncIterator[Upstream]:
    """Route the application's forecast client to the stand-in."""
    upstream = Upstream()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(upstream.handle)
    ) as http:
        forecast_client = OpenMeteoForecastClient(http, base_url="https://weather.test")
        app.dependency_overrides[get_forecast_client] = lambda: forecast_client
        yield upstream


class TestDistrictForecast:
    """Test cases for GET /api/districts/{id}/forecast"""

    @pytest.mark.usefixtures("upstream")
    async def test_fetches_and_returns_the_forecast(self, client: AsyncClient) -> None:
        response = await client.get("/api/districts/lahore/forecast")

        body = response.json()
        assert response.status_code == 200
        assert body["district_id"] == "lahore"
        assert body["source"] == "open-meteo-forecast"
        assert body["stale"] is False
        assert body["days"][0] == {
            "date": "2026-10-08",
            "temperature_max_c": 32.0,
            "temperature_min_c": 23.1,
            "precipitation_mm": 0.0,
            "precipitation_probability_pct": 37.0,
            "wind_speed_max_kmh": 9.9,
            "wind_gusts_max_kmh": 22.3,
            "weather_code": 0,
            "snowfall_cm": 0.0,
            "uv_index_max": 6.2,
        }
        assert len(body["days"]) == 3

    @pytest.mark.usefixtures("upstream")
    async def test_fetch_is_stored_as_a_snapshot(
        self, client: AsyncClient, db_session: AsyncSession
    ) -> None:
        await client.get("/api/districts/lahore/forecast")

        snapshot = (await db_session.scalars(select(SourceSnapshot))).one()
        assert snapshot.district_id == "lahore"
        assert snapshot.source == SOURCE
        assert snapshot.payload == LAHORE_PAYLOAD
        assert datetime.now(UTC) - snapshot.fetched_at < timedelta(minutes=1)

    async def test_recent_snapshot_is_reused(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        await client.get("/api/districts/lahore/forecast")
        await client.get("/api/districts/lahore/forecast")

        assert upstream.calls == 1

    async def test_old_snapshot_is_refreshed(
        self, client: AsyncClient, upstream: Upstream, db_session: AsyncSession
    ) -> None:
        yesterday = datetime.now(UTC) - timedelta(days=1)
        await store_snapshot(db_session, "lahore", SOURCE, LAHORE_PAYLOAD, yesterday)

        response = await client.get("/api/districts/lahore/forecast")

        assert upstream.calls == 1
        assert response.json()["stale"] is False

    async def test_old_snapshot_is_served_when_the_source_is_down(
        self, client: AsyncClient, upstream: Upstream, db_session: AsyncSession
    ) -> None:
        yesterday = datetime.now(UTC) - timedelta(days=1)
        await store_snapshot(db_session, "lahore", SOURCE, LAHORE_PAYLOAD, yesterday)
        upstream.failing = True

        response = await client.get("/api/districts/lahore/forecast")

        body = response.json()
        assert response.status_code == 200
        assert body["stale"] is True
        assert datetime.fromisoformat(body["fetched_at"]) == yesterday
        assert len(body["days"]) == 3

    async def test_source_down_with_no_snapshot_is_a_bad_gateway(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        upstream.failing = True

        response = await client.get("/api/districts/lahore/forecast")

        assert response.status_code == 502
        assert response.json() == {
            "detail": "The forecast source is unavailable and no earlier forecast "
            "is stored for this district."
        }

    async def test_unknown_district_is_not_found(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        response = await client.get("/api/districts/atlantis/forecast")

        assert response.status_code == 404
        assert upstream.calls == 0


class TestIngestAllForecasts:
    """Test cases for ingest_all_forecasts"""

    async def test_stores_a_snapshot_for_every_district_in_batches(
        self, upstream: Upstream, db_session: AsyncSession
    ) -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(upstream.handle)
        ) as http:
            forecast_client = OpenMeteoForecastClient(http, base_url="https://w.test")

            stored = await ingest_all_forecasts(
                db_session, forecast_client, batch_size=50, days=3
            )

        count = await db_session.scalar(
            select(func.count()).select_from(SourceSnapshot)
        )
        assert stored == 155
        assert count == 155
        assert upstream.calls == 4  # 155 districts in batches of 50
