"""Tests for the Open-Meteo air-quality client."""

import json
from pathlib import Path
from typing import Any

import httpx
import pytest

from ews.sources.errors import SourceError
from ews.sources.open_meteo_air_quality import OpenMeteoAirQualityClient

RECORDED: list[dict[str, Any]] = json.loads(
    (
        Path(__file__).parent / "fixtures/open_meteo_air_quality_two_locations.json"
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

    lahore, karachi = await client.fetch([LAHORE, KARACHI], 3)

    assert requests[0].url.params["hourly"] == "pm2_5"
    assert requests[0].url.params["forecast_days"] == "3"
    assert lahore.days[0].pm2_5_mean_ug_m3 == 18.0
    assert lahore.days[1].pm2_5_mean_ug_m3 == 155.5
    assert lahore.days[2].pm2_5_mean_ug_m3 is None
    assert karachi.payload == RECORDED[1]


async def test_rejects_a_missing_pm25_series() -> None:
    client = client_answering({"hourly": {"time": ["2026-10-08T00:00"]}})

    with pytest.raises(SourceError, match="pm2_5"):
        await client.fetch([LAHORE], 1)
