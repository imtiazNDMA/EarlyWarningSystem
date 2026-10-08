"""Tests for the Open-Meteo air-quality client."""

import copy
import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from ews.screening.rules import screen
from ews.screening.thresholds import load_rules
from ews.sources.errors import SourceError
from ews.sources.open_meteo_air_quality import OpenMeteoAirQualityClient, parse_daily

RECORDED: list[dict[str, Any]] = json.loads(
    (
        Path(__file__).parent / "fixtures/open_meteo_air_quality_two_locations.json"
    ).read_text(encoding="utf-8")
)
SEVEN_DAY_WITH_NULLS: dict[str, Any] = json.loads(
    (
        Path(__file__).parent / "fixtures/open_meteo_air_quality_lahore_7day_nulls.json"
    ).read_text(encoding="utf-8")
)
LAHORE = (31.4614, 74.3552)
KARACHI = (24.9469, 67.0585)


def client_answering(
    body: Any, requests: list[httpx.Request] | None = None
) -> OpenMeteoAirQualityClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return httpx.Response(200, json=body)

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return OpenMeteoAirQualityClient(http, "https://air.test/v1/air-quality")


async def test_fetches_typed_daily_pm25_for_all_locations() -> None:
    requests: list[httpx.Request] = []
    client = client_answering(RECORDED, requests)

    lahore, karachi = await client.fetch([LAHORE, KARACHI], 5)

    assert requests[0].url.params["hourly"] == "pm2_5"
    assert requests[0].url.params["forecast_days"] == "5"
    assert len(lahore.days) == 5
    assert lahore.days[0].pm2_5_mean_ug_m3 == pytest.approx(72.55)
    assert all(day.pm2_5_mean_ug_m3 is not None for day in lahore.days)
    assert lahore.payload["hourly_units"]["pm2_5"] == "μg/m³"
    assert karachi.payload == RECORDED[1]


def test_discards_days_with_an_incomplete_hourly_series() -> None:
    days = parse_daily(SEVEN_DAY_WITH_NULLS)

    assert [day.date.isoformat() for day in days] == [
        "2026-10-08",
        "2026-10-09",
        "2026-10-10",
        "2026-10-11",
        "2026-10-12",
    ]


def test_partial_day_cannot_raise_a_signal() -> None:
    payload = copy.deepcopy(SEVEN_DAY_WITH_NULLS)
    payload["hourly"]["pm2_5"][:120] = [0.0] * 120
    rules = [rule for rule in load_rules() if rule.hazard == "poor_air_quality"]

    signals = screen(parse_daily(payload), "Punjab", rules)

    assert signals == []


def test_rejects_a_pm25_series_with_the_wrong_unit() -> None:
    payload = copy.deepcopy(RECORDED[0])
    payload["hourly_units"]["pm2_5"] = "µg/m³"

    with pytest.raises(SourceError, match="unit"):
        parse_daily(payload)


async def test_rejects_a_missing_pm25_series() -> None:
    client = client_answering({"hourly": {"time": ["2026-10-08T00:00"]}})

    with pytest.raises(SourceError, match="pm2_5"):
        await client.fetch([LAHORE], 1)
