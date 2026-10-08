"""Tests for alerts produced by monitoring cycles and served by the API."""

import copy
from collections.abc import Callable
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ews.alerts.models import Alert
from tests.conftest import ADMIN_TOKEN, RECORDED_FORECAST, Upstream

ADMIN = {"X-Admin-Token": ADMIN_TOKEN}
LAHORE_LAT = "31.461437162052533"
KARACHI_CENTRAL_LAT = "24.946946806359648"

Answer = Callable[[str, str], dict[str, Any]]


def forecast(**daily: list[Any]) -> dict[str, Any]:
    """The recorded three-day forecast (8-10 October) with daily values replaced."""
    payload = copy.deepcopy(RECORDED_FORECAST)
    payload["daily"].update(daily)
    return payload


def only_in(latitude: str, payload: dict[str, Any]) -> Answer:
    """Answer with the payload at one location and calm weather elsewhere."""
    return lambda lat, _lon: payload if lat == latitude else RECORDED_FORECAST


SEVERE_RAIN = forecast(precipitation_sum=[0.0, 120.0, 60.0])
EXTREME_RAIN = forecast(precipitation_sum=[0.0, 160.0, 60.0])
STRONG_WIND = forecast(wind_gusts_10m_max=[65.0, 20.0, 20.0])
# The same calm weather, forecast from two days after the rain alert's window
CALM_LATER = forecast(time=["2026-10-12", "2026-10-13", "2026-10-14"])


async def run_cycle(
    client: AsyncClient, upstream: Upstream, answer: Answer | None
) -> None:
    upstream.payload_for = answer
    response = await client.post("/api/runs", headers=ADMIN)
    assert response.json()["status"] == "succeeded"


async def alerts(client: AsyncClient, **params: str) -> list[dict[str, Any]]:
    response = await client.get("/api/alerts", params=params)
    assert response.status_code == 200
    body: list[dict[str, Any]] = response.json()
    return body


class TestAlertLifecycle:
    """Test cases for alerts across successive cycles"""

    async def test_a_signal_issues_an_alert_with_its_evidence(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        await run_cycle(client, upstream, only_in(LAHORE_LAT, SEVERE_RAIN))

        (alert,) = await alerts(client)

        assert alert["district_id"] == "lahore"
        assert alert["district_name"] == "Lahore"
        assert alert["province"] == "Punjab"
        assert alert["hazard"] == "heavy_rain"
        assert alert["severity"] == "severe"
        assert alert["urgency"] == "expected"
        assert alert["certainty"] == "likely"
        assert alert["onset"] == "2026-10-09"
        assert alert["expires"] == "2026-10-10"
        assert alert["status"] == "active"
        assert alert["ended_at"] is None
        assert alert["supersedes_id"] is None
        assert alert["generated_by"] == "rules"
        assert alert["headline_en"] == "Severe heavy rain alert for Lahore"
        assert "peaks at 120 mm on 9 October" in alert["body_en"]
        assert alert["instructions_en"].startswith("Avoid low-lying areas")
        assert alert["headline_ur"] is None
        assert alert["body_ur"] is None
        assert alert["instructions_ur"] is None
        snapshot_id = alert["evidence"][0]["snapshot_id"]
        assert alert["evidence"] == [
            {
                "snapshot_id": snapshot_id,
                "metric": "precipitation_mm",
                "unit": "mm",
                "date": "2026-10-09",
                "value": 120.0,
                "threshold": 100.0,
            },
            {
                "snapshot_id": snapshot_id,
                "metric": "precipitation_mm",
                "unit": "mm",
                "date": "2026-10-10",
                "value": 60.0,
                "threshold": 100.0,
            },
        ]

    async def test_urdu_text_round_trips_without_ascii_escaping(
        self, client: AsyncClient, upstream: Upstream, db_session: AsyncSession
    ) -> None:
        await run_cycle(client, upstream, only_in(LAHORE_LAT, SEVERE_RAIN))
        alert = await db_session.scalar(select(Alert))
        assert alert is not None
        alert.headline_ur = "لاہور کے لیے شدید بارش کا انتباہ"
        alert.body_ur = "شدید بارش متوقع ہے۔"
        alert.instructions_ur = "نشیبی علاقوں سے دور رہیں۔"
        await db_session.flush()
        alert_id = alert.id
        db_session.expire(alert)

        stored = await db_session.get_one(Alert, alert_id)

        assert stored.headline_ur == "لاہور کے لیے شدید بارش کا انتباہ"
        assert stored.body_ur == "شدید بارش متوقع ہے۔"
        assert stored.instructions_ur == "نشیبی علاقوں سے دور رہیں۔"

    async def test_an_unchanged_signal_keeps_the_same_alert(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        await run_cycle(client, upstream, only_in(LAHORE_LAT, SEVERE_RAIN))
        (first,) = await alerts(client)
        await run_cycle(client, upstream, only_in(LAHORE_LAT, SEVERE_RAIN))

        (still,) = await alerts(client)

        assert still["id"] == first["id"]
        assert still["status"] == "active"

    async def test_a_changed_severity_supersedes_and_keeps_the_old_record(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        await run_cycle(client, upstream, only_in(LAHORE_LAT, SEVERE_RAIN))
        await run_cycle(client, upstream, only_in(LAHORE_LAT, EXTREME_RAIN))

        newer, older = await alerts(client)

        assert newer["severity"] == "extreme"
        assert newer["status"] == "active"
        assert newer["supersedes_id"] == older["id"]
        assert older["severity"] == "severe"
        assert older["status"] == "superseded"
        assert older["ended_at"] is not None

    async def test_a_signal_that_ends_early_cancels_the_alert(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        await run_cycle(client, upstream, only_in(LAHORE_LAT, SEVERE_RAIN))
        await run_cycle(client, upstream, None)

        (alert,) = await alerts(client)

        assert alert["status"] == "cancelled"
        assert alert["ended_at"] is not None

    async def test_an_alert_expires_once_its_window_has_passed(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        await run_cycle(client, upstream, only_in(LAHORE_LAT, SEVERE_RAIN))
        await run_cycle(client, upstream, lambda _lat, _lon: CALM_LATER)

        (alert,) = await alerts(client)

        assert alert["status"] == "expired"

    async def test_a_failed_cycle_leaves_alerts_as_they_were(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        await run_cycle(client, upstream, only_in(LAHORE_LAT, SEVERE_RAIN))
        upstream.failing = True
        await client.post("/api/runs", headers=ADMIN)

        (alert,) = await alerts(client)

        assert alert["status"] == "active"


class TestListAlerts:
    """Test cases for GET /api/alerts"""

    @pytest.fixture
    async def history(self, client: AsyncClient, upstream: Upstream) -> None:
        """Lahore: a superseded severe and an active extreme rain alert.
        Karachi Central: an active moderate wind alert."""

        def first(lat: str, _lon: str) -> dict[str, Any]:
            return SEVERE_RAIN if lat == LAHORE_LAT else RECORDED_FORECAST

        def second(lat: str, _lon: str) -> dict[str, Any]:
            if lat == LAHORE_LAT:
                return EXTREME_RAIN
            return STRONG_WIND if lat == KARACHI_CENTRAL_LAT else RECORDED_FORECAST

        await run_cycle(client, upstream, first)
        await run_cycle(client, upstream, second)

    @pytest.mark.usefixtures("history")
    async def test_lists_newest_first(self, client: AsyncClient) -> None:
        listed = await alerts(client)

        assert [(a["district_id"], a["status"]) for a in listed] == [
            # Both issued in the second cycle; ties go to the later record
            ("lahore", "active"),
            ("karachi-central", "active"),
            ("lahore", "superseded"),
        ]

    @pytest.mark.usefixtures("history")
    @pytest.mark.parametrize(
        ("params", "expected"),
        [
            ({"status": "active"}, 2),
            ({"status": "superseded"}, 1),
            ({"province": "sindh"}, 1),
            ({"province": "Punjab"}, 2),
            ({"hazard": "strong_wind"}, 1),
            ({"severity": "extreme"}, 1),
            ({"district_id": "lahore"}, 2),
            ({"status": "active", "province": "punjab"}, 1),
            ({"issued_since": "2100-01-01T00:00:00Z"}, 0),
            ({"issued_until": "2100-01-01T00:00:00Z"}, 3),
            ({"limit": "1"}, 1),
        ],
    )
    async def test_filters(
        self, client: AsyncClient, params: dict[str, str], expected: int
    ) -> None:
        assert len(await alerts(client, **params)) == expected

    async def test_rejects_an_unknown_status(self, client: AsyncClient) -> None:
        response = await client.get("/api/alerts", params={"status": "pending"})

        assert response.status_code == 422


class TestAlertDetail:
    """Test cases for GET /api/alerts/{id}"""

    async def test_returns_the_alert_and_what_replaced_it(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        await run_cycle(client, upstream, only_in(LAHORE_LAT, SEVERE_RAIN))
        await run_cycle(client, upstream, only_in(LAHORE_LAT, EXTREME_RAIN))
        newer, older = await alerts(client)

        old_detail = (await client.get(f"/api/alerts/{older['id']}")).json()
        new_detail = (await client.get(f"/api/alerts/{newer['id']}")).json()

        assert old_detail["superseded_by_id"] == newer["id"]
        assert old_detail["evidence"][0]["value"] == 120.0
        assert new_detail["superseded_by_id"] is None
        assert new_detail["evidence"][0]["value"] == 160.0

    async def test_unknown_alert_is_not_found(self, client: AsyncClient) -> None:
        response = await client.get("/api/alerts/999999")

        assert response.status_code == 404
