"""Tests for the Open-Meteo forecast client, against a recorded response."""

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest

from ews.sources.errors import SourceError
from ews.sources.open_meteo import OpenMeteoForecastClient

FIXTURES = Path(__file__).parent / "fixtures"
RECORDED: list[dict[str, Any]] = json.loads(
    (FIXTURES / "open_meteo_forecast_two_locations.json").read_text(encoding="utf-8")
)

LAHORE = (31.4614, 74.3552)
KARACHI = (24.9469, 67.0585)

Handler = Callable[[httpx.Request], httpx.Response]


def client_answering(
    handler: Handler, requests: list[httpx.Request] | None = None
) -> OpenMeteoForecastClient:
    """A client whose HTTP calls are answered by the handler."""

    def record(request: httpx.Request) -> httpx.Response:
        if requests is not None:
            requests.append(request)
        return handler(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return OpenMeteoForecastClient(http, base_url="https://weather.test/v1/forecast")


def answer(status: int, body: Any) -> Handler:
    """A handler that always sends the same JSON response."""
    return lambda _request: httpx.Response(status, json=body)


class TestFetch:
    """Test cases for OpenMeteoForecastClient.fetch"""

    async def test_requests_all_locations_in_one_call(self) -> None:
        requests: list[httpx.Request] = []
        client = client_answering(answer(200, RECORDED), requests)

        await client.fetch([LAHORE, KARACHI], days=3)

        assert len(requests) == 1
        params = requests[0].url.params
        assert params["latitude"] == "31.4614,24.9469"
        assert params["longitude"] == "74.3552,67.0585"
        assert params["forecast_days"] == "3"
        assert params["timezone"] == "Asia/Karachi"

    async def test_returns_typed_days_for_each_location_in_order(self) -> None:
        client = client_answering(answer(200, RECORDED))

        lahore, karachi = await client.fetch([LAHORE, KARACHI], days=3)

        assert [day.date for day in lahore.days] == [
            date(2026, 10, 8),
            date(2026, 10, 9),
            date(2026, 10, 10),
        ]
        last = lahore.days[2]
        assert last.temperature_max_c == 28.0
        assert last.temperature_min_c == 22.3
        assert last.precipitation_mm == 0.3
        assert last.precipitation_probability_pct == 14
        assert last.wind_speed_max_kmh == 22.7
        assert last.wind_gusts_max_kmh == 51.1
        assert last.weather_code == 51
        assert last.snowfall_cm == 0.0
        assert last.uv_index_max == 6.1
        assert karachi.payload == RECORDED[1]

    async def test_single_location_response_is_an_object_not_a_list(self) -> None:
        client = client_answering(answer(200, RECORDED[0]))

        (lahore,) = await client.fetch([LAHORE], days=3)

        assert lahore.payload == RECORDED[0]
        assert len(lahore.days) == 3

    async def test_missing_values_become_none(self) -> None:
        payload = json.loads(json.dumps(RECORDED[0]))
        payload["daily"]["uv_index_max"] = [None, None, None]
        client = client_answering(answer(200, payload))

        (lahore,) = await client.fetch([LAHORE], days=3)

        assert lahore.days[0].uv_index_max is None

    async def test_error_status_raises_with_the_reason(self) -> None:
        body = {"error": True, "reason": "Minutely API request limit exceeded"}
        client = client_answering(answer(429, body))

        with pytest.raises(SourceError, match=r"429.*request limit exceeded"):
            await client.fetch([LAHORE], days=3)

    async def test_network_failure_raises(self) -> None:
        def refuse(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        client = client_answering(refuse)

        with pytest.raises(SourceError, match="connection refused"):
            await client.fetch([LAHORE], days=3)

    async def test_wrong_number_of_locations_raises(self) -> None:
        client = client_answering(answer(200, RECORDED))

        with pytest.raises(SourceError, match=r"3 locations.*2"):
            await client.fetch([LAHORE, KARACHI, LAHORE], days=3)

    async def test_malformed_payload_raises(self) -> None:
        client = client_answering(answer(200, {"daily": {"time": ["2026-10-08"]}}))

        with pytest.raises(SourceError, match="temperature_2m_max"):
            await client.fetch([LAHORE], days=3)
