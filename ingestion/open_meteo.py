import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import requests

from domain.forecast import (
    DataQualityReport,
    DataStatus,
    ForecastRun,
    Location,
    freshness_windows,
)


class OpenMeteoProvider:
    """Fetch and validate a single location forecast from Open-Meteo."""

    DAILY_FIELDS = (
        "temperature_2m_max",
        "temperature_2m_min",
        "precipitation_sum",
        "precipitation_probability_max",
        "windspeed_10m_max",
        "windgusts_10m_max",
        "weathercode",
        "snowfall_sum",
        "uv_index_max",
    )

    def __init__(
        self,
        base_url: str,
        timeout: int,
        fresh_seconds: int,
        stale_seconds: int,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.fresh_seconds = fresh_seconds
        self.stale_seconds = stale_seconds
        self.session = session or requests.Session()

    def fetch(self, location: Location, forecast_days: int) -> ForecastRun:
        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "daily": list(self.DAILY_FIELDS),
            "timezone": location.timezone,
            "forecast_days": forecast_days,
            "current_weather": "true",
        }
        response = self.session.get(self.base_url, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        retrieved_at = datetime.now(UTC)
        quality = self._validate(payload, forecast_days)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        fresh_until, usable_until = freshness_windows(
            retrieved_at, self.fresh_seconds, self.stale_seconds
        )
        return ForecastRun(
            run_id=str(uuid4()),
            provider="open-meteo",
            location=location,
            requested_days=forecast_days,
            retrieved_at=retrieved_at,
            fresh_until=fresh_until,
            usable_until=usable_until,
            payload=payload,
            quality=quality,
            checksum=checksum,
            source_url=response.url,
        )

    def _validate(self, payload: dict, forecast_days: int) -> DataQualityReport:
        daily = payload.get("daily")
        if not isinstance(daily, dict):
            return DataQualityReport(
                DataStatus.INVALID, forecast_days, 0, issues=("daily data missing",)
            )
        dates = daily.get("time")
        if not isinstance(dates, list):
            return DataQualityReport(
                DataStatus.INVALID, forecast_days, 0, issues=("daily time missing",)
            )
        issues = []
        for field in self.DAILY_FIELDS:
            values = daily.get(field)
            if not isinstance(values, list) or len(values) != len(dates):
                issues.append(f"{field} length does not match daily time")
        returned_days = len(dates)
        if issues:
            status = DataStatus.INVALID
        elif returned_days < forecast_days:
            status = DataStatus.PARTIAL
            issues.append(
                f"provider returned {returned_days} of {forecast_days} requested days"
            )
        else:
            status = DataStatus.FRESH
        return DataQualityReport(
            status=status,
            expected_days=forecast_days,
            returned_days=returned_days,
            issues=tuple(issues),
        )
