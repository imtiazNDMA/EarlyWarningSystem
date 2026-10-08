"""Tests for monitoring cycles: triggering a run and reading its signals."""

import copy
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ews.sources.models import SourceSnapshot
from tests.conftest import (
    ADMIN_TOKEN,
    RECORDED_AIR_QUALITY,
    RECORDED_FORECAST,
    Upstream,
)

ADMIN = {"X-Admin-Token": ADMIN_TOKEN}
LAHORE_LAT = "31.461437162052533"


def wet_in_lahore(lat: str, _lon: str) -> dict[str, Any]:
    """The recorded forecast, with heavy rain on two days in Lahore only."""
    payload = copy.deepcopy(RECORDED_FORECAST)
    if lat == LAHORE_LAT:
        payload["daily"]["precipitation_sum"] = [0.0, 120.0, 60.0]
    return payload


def polluted_lahore(lat: str, _lon: str) -> dict[str, Any]:
    payload = copy.deepcopy(RECORDED_AIR_QUALITY)
    if lat == LAHORE_LAT:
        payload["hourly"]["pm2_5"] = [60.0, 60.0, 180.0, 80.0]
    return dict(payload)


class TestTriggerRun:
    """Test cases for POST /api/runs"""

    async def test_requires_the_admin_token(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        missing = await client.post("/api/runs")
        wrong = await client.post("/api/runs", headers={"X-Admin-Token": "guess"})

        assert missing.status_code == 401
        assert wrong.status_code == 401
        assert upstream.calls == 0

    async def test_is_unavailable_when_no_admin_token_is_configured(
        self, app: FastAPI, client: AsyncClient, upstream: Upstream
    ) -> None:
        app.state.settings.admin_token = None

        response = await client.post("/api/runs", headers={"X-Admin-Token": ""})

        assert response.status_code == 503
        assert upstream.calls == 0

    async def test_runs_a_cycle_over_every_district(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        upstream.payload_for = wet_in_lahore

        response = await client.post("/api/runs", headers=ADMIN)

        run = response.json()
        assert response.status_code == 201
        assert run["status"] == "succeeded"
        assert run["trigger"] == "manual"
        assert run["district_count"] == 155
        assert run["signal_count"] == 1
        assert run["error"] is None
        assert run["finished_at"] is not None

    async def test_failed_source_is_recorded_on_the_run(
        self, client: AsyncClient, upstream: Upstream, db_session: AsyncSession
    ) -> None:
        upstream.failing = True

        response = await client.post("/api/runs", headers=ADMIN)

        run = response.json()
        assert response.status_code == 201
        assert run["status"] == "failed"
        assert "HTTP 503" in run["error"]
        snapshots = await db_session.scalar(
            select(func.count()).select_from(SourceSnapshot)
        )
        assert snapshots == 0

    async def test_air_quality_failure_does_not_stop_weather_cycle(
        self, client: AsyncClient, upstream: Upstream, db_session: AsyncSession
    ) -> None:
        upstream.payload_for = wet_in_lahore
        assert upstream.air_quality is not None
        upstream.air_quality.failing = True

        run = (await client.post("/api/runs", headers=ADMIN)).json()

        assert run["status"] == "succeeded"
        assert run["signal_count"] == 1
        sources = set(await db_session.scalars(select(SourceSnapshot.source)))
        assert sources == {"open-meteo-forecast"}

    async def test_partial_air_quality_failure_rolls_back_every_batch(
        self, client: AsyncClient, upstream: Upstream, db_session: AsyncSession
    ) -> None:
        assert upstream.air_quality is not None
        upstream.air_quality.fail_on_call = 2

        run = (await client.post("/api/runs", headers=ADMIN)).json()

        assert run["status"] == "succeeded"
        air_snapshots = await db_session.scalar(
            select(func.count())
            .select_from(SourceSnapshot)
            .where(SourceSnapshot.source == "open-meteo-air-quality")
        )
        assert air_snapshots == 0

    async def test_air_quality_signal_uses_its_snapshot(
        self, client: AsyncClient, upstream: Upstream, db_session: AsyncSession
    ) -> None:
        assert upstream.air_quality is not None
        upstream.air_quality.payload_for = polluted_lahore

        run = (await client.post("/api/runs", headers=ADMIN)).json()
        signals = (await client.get("/api/signals")).json()["signals"]

        assert run["status"] == "succeeded"
        assert run["district_count"] == 155
        assert signals == [
            {
                "district_id": "lahore",
                "hazard": "poor_air_quality",
                "level": "severe",
                "onset": "2026-10-08",
                "expires": "2026-10-10",
                "metric": "pm2_5_mean_ug_m3",
                "unit": "µg/m³",
                "peak_value": 180.0,
                "peak_date": "2026-10-09",
                "threshold": 150.0,
                "days_over": ["2026-10-08", "2026-10-09", "2026-10-10"],
                "snapshot_id": signals[0]["snapshot_id"],
            }
        ]
        source = await db_session.scalar(
            select(SourceSnapshot.source).where(
                SourceSnapshot.id == signals[0]["snapshot_id"]
            )
        )
        assert source == "open-meteo-air-quality"


class TestAirQuality:
    async def test_lists_latest_values_and_district_detail(
        self,
        client: AsyncClient,
        upstream: Upstream,  # noqa: ARG002
    ) -> None:
        await client.post("/api/runs", headers=ADMIN)

        all_values = (await client.get("/api/air-quality")).json()
        district = (await client.get("/api/districts/lahore/air-quality")).json()

        assert len(all_values) == 155
        assert district["district_id"] == "lahore"
        assert district["date"] == "2026-10-08"
        assert district["pm2_5_mean_ug_m3"] == 18.0
        assert district in all_values


class TestCurrentSignals:
    """Test cases for GET /api/signals"""

    async def test_is_empty_before_any_cycle(self, client: AsyncClient) -> None:
        response = await client.get("/api/signals")

        assert response.status_code == 200
        assert response.json() == {"run": None, "signals": []}

    async def test_returns_signals_from_the_latest_cycle(
        self, client: AsyncClient, upstream: Upstream, db_session: AsyncSession
    ) -> None:
        upstream.payload_for = wet_in_lahore
        run = (await client.post("/api/runs", headers=ADMIN)).json()

        body = (await client.get("/api/signals")).json()

        snapshot_id = await db_session.scalar(
            select(SourceSnapshot.id).where(
                SourceSnapshot.district_id == "lahore",
                SourceSnapshot.source == "open-meteo-forecast",
            )
        )
        assert body["run"]["id"] == run["id"]
        assert body["signals"] == [
            {
                "district_id": "lahore",
                "hazard": "heavy_rain",
                "level": "severe",
                "onset": "2026-10-09",
                "expires": "2026-10-10",
                "metric": "precipitation_mm",
                "unit": "mm",
                "peak_value": 120.0,
                "peak_date": "2026-10-09",
                "threshold": 100.0,
                "days_over": ["2026-10-09", "2026-10-10"],
                "snapshot_id": snapshot_id,
            }
        ]

    async def test_a_new_cycle_replaces_the_current_signals(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        upstream.payload_for = wet_in_lahore
        await client.post("/api/runs", headers=ADMIN)
        upstream.payload_for = None
        calm = (await client.post("/api/runs", headers=ADMIN)).json()

        body = (await client.get("/api/signals")).json()

        assert body["run"]["id"] == calm["id"]
        assert body["signals"] == []

    async def test_a_failed_cycle_leaves_the_current_signals_in_place(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        upstream.payload_for = wet_in_lahore
        succeeded = (await client.post("/api/runs", headers=ADMIN)).json()
        upstream.failing = True
        await client.post("/api/runs", headers=ADMIN)

        body = (await client.get("/api/signals")).json()

        assert body["run"]["id"] == succeeded["id"]
        assert [signal["district_id"] for signal in body["signals"]] == ["lahore"]
