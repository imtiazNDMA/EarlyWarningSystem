"""Tests for monitoring cycles: triggering a run and reading its signals."""

import copy
from typing import Any

from fastapi import FastAPI
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ews.sources.models import SourceSnapshot
from tests.conftest import ADMIN_TOKEN, RECORDED_FORECAST, Upstream

ADMIN = {"X-Admin-Token": ADMIN_TOKEN}
LAHORE_LAT = "31.461437162052533"


def wet_in_lahore(lat: str, _lon: str) -> dict[str, Any]:
    """The recorded forecast, with heavy rain on two days in Lahore only."""
    payload = copy.deepcopy(RECORDED_FORECAST)
    if lat == LAHORE_LAT:
        payload["daily"]["precipitation_sum"] = [0.0, 120.0, 60.0]
    return payload


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
            select(SourceSnapshot.id).where(SourceSnapshot.district_id == "lahore")
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
