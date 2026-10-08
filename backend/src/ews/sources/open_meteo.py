"""Client for the Open-Meteo forecast API."""

import datetime as dt
import logging
from collections.abc import Sequence
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from ews.sources.errors import SourceError

logger = logging.getLogger(__name__)

SOURCE = "open-meteo-forecast"

# API variable -> field on DailyForecast
DAILY_VARIABLES = {
    "temperature_2m_max": "temperature_max_c",
    "temperature_2m_min": "temperature_min_c",
    "precipitation_sum": "precipitation_mm",
    "precipitation_probability_max": "precipitation_probability_pct",
    "wind_speed_10m_max": "wind_speed_max_kmh",
    "wind_gusts_10m_max": "wind_gusts_max_kmh",
    "weather_code": "weather_code",
    "snowfall_sum": "snowfall_cm",
    "uv_index_max": "uv_index_max",
}

Location = tuple[float, float]  # (lat, lon)


class DailyForecast(BaseModel):
    """One day of forecast for one location. Missing values are None."""

    date: dt.date
    temperature_max_c: float | None
    temperature_min_c: float | None
    precipitation_mm: float | None
    precipitation_probability_pct: float | None
    wind_speed_max_kmh: float | None
    wind_gusts_max_kmh: float | None
    weather_code: int | None
    snowfall_cm: float | None
    uv_index_max: float | None


class LocationForecast(BaseModel):
    """Forecast for one location: the raw payload and its parsed days."""

    payload: dict[str, Any]
    days: list[DailyForecast]


def parse_daily(payload: dict[str, Any]) -> list[DailyForecast]:
    """Turn one location's payload into typed days.

    Raises:
        SourceError: If a variable is missing or the values are unusable
    """
    daily = payload.get("daily")
    if not isinstance(daily, dict) or "time" not in daily:
        raise SourceError(SOURCE, "response has no daily block")

    missing = [name for name in DAILY_VARIABLES if name not in daily]
    if missing:
        raise SourceError(SOURCE, f"response is missing {', '.join(missing)}")

    try:
        return [
            DailyForecast(
                date=day,
                **{
                    field: daily[variable][index]
                    for variable, field in DAILY_VARIABLES.items()
                },
            )
            for index, day in enumerate(daily["time"])
        ]
    except (IndexError, TypeError, ValidationError) as error:
        raise SourceError(SOURCE, f"unusable daily values: {error}") from error


class OpenMeteoForecastClient:
    """Fetches daily forecasts, several locations per request."""

    def __init__(
        self, http: httpx.AsyncClient, base_url: str, timezone: str = "Asia/Karachi"
    ) -> None:
        self._http = http
        self._base_url = base_url
        self._timezone = timezone

    async def fetch(
        self, locations: Sequence[Location], days: int
    ) -> list[LocationForecast]:
        """Fetch forecasts for the locations in a single request.

        Args:
            locations: (lat, lon) pairs
            days: Number of forecast days

        Returns:
            One forecast per location, in the order given

        Raises:
            SourceError: On a network failure, an error status or a bad payload
        """
        try:
            return await self._fetch(locations, days)
        except SourceError:
            logger.exception(
                "Forecast fetch failed for %s location(s), first at %s",
                len(locations),
                locations[0] if locations else None,
            )
            raise

    async def _fetch(
        self, locations: Sequence[Location], days: int
    ) -> list[LocationForecast]:
        params = {
            "latitude": ",".join(str(lat) for lat, _ in locations),
            "longitude": ",".join(str(lon) for _, lon in locations),
            "daily": ",".join(DAILY_VARIABLES),
            "timezone": self._timezone,
            "forecast_days": str(days),
        }
        try:
            response = await self._http.get(self._base_url, params=params)
        except httpx.HTTPError as error:
            raise SourceError(SOURCE, f"request failed: {error}") from error

        if response.status_code != httpx.codes.OK:
            raise SourceError(
                SOURCE, f"HTTP {response.status_code}: {_error_reason(response)}"
            )

        try:
            body = response.json()
        except ValueError as error:
            raise SourceError(SOURCE, "response is not JSON") from error

        # One location comes back as an object, several as a list
        payloads = body if isinstance(body, list) else [body]
        if len(payloads) != len(locations):
            raise SourceError(
                SOURCE,
                f"asked for {len(locations)} locations but received {len(payloads)}",
            )
        return [
            LocationForecast(payload=payload, days=parse_daily(payload))
            for payload in payloads
        ]


def _error_reason(response: httpx.Response) -> str:
    """The API's own explanation when it sends one, else the start of the body."""
    try:
        reason = response.json().get("reason")
    except (ValueError, AttributeError):
        reason = None
    return str(reason or response.text[:200])
