"""Client for daily PM2.5 forecasts from Open-Meteo Air Quality."""

import datetime as dt
import logging
from collections.abc import Sequence
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from ews.sources.errors import SourceError
from ews.sources.open_meteo import Location, _error_reason

logger = logging.getLogger(__name__)

SOURCE = "open-meteo-air-quality"
HOURLY_VARIABLE = "pm2_5"
PM25_UNIT = "μg/m³"


class DailyAirQuality(BaseModel):
    """One day of PM2.5 forecast for one location."""

    date: dt.date
    pm2_5_mean_ug_m3: float | None


class LocationAirQuality(BaseModel):
    """Air-quality forecast for one location, raw and parsed."""

    payload: dict[str, Any]
    days: list[DailyAirQuality]


def parse_daily(payload: dict[str, Any]) -> list[DailyAirQuality]:
    """Aggregate complete local days of hourly PM2.5 into daily means."""
    hourly = payload.get("hourly")
    if not isinstance(hourly, dict) or "time" not in hourly:
        raise SourceError(SOURCE, "response has no hourly block")
    if HOURLY_VARIABLE not in hourly:
        raise SourceError(SOURCE, f"response is missing {HOURLY_VARIABLE}")
    hourly_units = payload.get("hourly_units")
    if (
        not isinstance(hourly_units, dict)
        or hourly_units.get(HOURLY_VARIABLE) != PM25_UNIT
    ):
        raise SourceError(SOURCE, f"unexpected {HOURLY_VARIABLE} unit")
    try:
        by_day: dict[dt.date, list[float | None]] = {}
        for timestamp, value in zip(
            hourly["time"], hourly[HOURLY_VARIABLE], strict=True
        ):
            day = dt.datetime.fromisoformat(timestamp).date()
            by_day.setdefault(day, []).append(
                float(value) if value is not None else None
            )
        days = []
        for day, values in by_day.items():
            if len(values) != 24 or any(value is None for value in values):
                continue
            complete_values = [value for value in values if value is not None]
            days.append(
                DailyAirQuality(
                    date=day,
                    pm2_5_mean_ug_m3=sum(complete_values) / len(complete_values),
                )
            )
        return days
    except (IndexError, TypeError, ValueError, ValidationError) as error:
        raise SourceError(SOURCE, f"unusable daily values: {error}") from error


class OpenMeteoAirQualityClient:
    """Fetch daily PM2.5 forecasts for several locations per request."""

    def __init__(
        self, http: httpx.AsyncClient, base_url: str, timezone: str = "Asia/Karachi"
    ) -> None:
        self._http = http
        self._base_url = base_url
        self._timezone = timezone

    async def fetch(
        self, locations: Sequence[Location], days: int
    ) -> list[LocationAirQuality]:
        params = {
            "latitude": ",".join(str(lat) for lat, _ in locations),
            "longitude": ",".join(str(lon) for _, lon in locations),
            "hourly": HOURLY_VARIABLE,
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
        payloads = body if isinstance(body, list) else [body]
        if len(payloads) != len(locations):
            raise SourceError(
                SOURCE,
                f"asked for {len(locations)} locations but received {len(payloads)}",
            )
        try:
            return [
                LocationAirQuality(payload=payload, days=parse_daily(payload))
                for payload in payloads
            ]
        except SourceError:
            logger.exception("Air-quality response could not be parsed")
            raise
