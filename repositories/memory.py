from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime, timedelta

import pandas as pd

from domain.forecast import ForecastRun
from repositories.keys import parse_cache_key


class InMemoryRepository:
    """Deterministic repository adapter for tests and local simulations."""

    def __init__(
        self,
        cache_time: int = 43200,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.cache_time = cache_time
        self.clock = clock or (lambda: datetime.now(UTC))
        self.weather: dict[str, dict] = {}
        self.alerts: dict[tuple[str, str, int], dict] = {}
        self.forecast_runs: dict[str, ForecastRun] = {}
        self.forecast_snapshots: dict[tuple[str, int, str], str] = {}
        self.refresh_leases: set[tuple[str, int]] = set()

    def initialize(self) -> None:
        return None

    def initialize_forecast_runs(self) -> None:
        return None

    def save_forecast_run(self, run: ForecastRun) -> bool:
        snapshot_key = (
            run.location.location_id,
            run.requested_days,
            run.checksum,
        )
        existing_id = self.forecast_snapshots.get(snapshot_key)
        if existing_id:
            existing = self.forecast_runs[existing_id]
            self.forecast_runs[existing_id] = ForecastRun(
                **{
                    **existing.__dict__,
                    "retrieved_at": run.retrieved_at,
                    "fresh_until": run.fresh_until,
                    "usable_until": run.usable_until,
                    "source_url": run.source_url,
                }
            )
            return False
        self.forecast_runs[run.run_id] = run
        self.forecast_snapshots[snapshot_key] = run.run_id
        return True

    def get_latest_forecast_run(
        self, location_id: str, forecast_days: int
    ) -> ForecastRun | None:
        matches = [
            run
            for run in self.forecast_runs.values()
            if run.location.location_id == location_id
            and run.requested_days == forecast_days
        ]
        return max(matches, key=lambda run: run.retrieved_at) if matches else None

    def acquire_refresh_lease(
        self, location_id: str, forecast_days: int, lease_seconds: int = 120
    ) -> bool:
        del lease_seconds
        key = (location_id, forecast_days)
        if key in self.refresh_leases:
            return False
        self.refresh_leases.add(key)
        return True

    def release_refresh_lease(self, location_id: str, forecast_days: int) -> None:
        self.refresh_leases.discard((location_id, forecast_days))

    def ping(self) -> None:
        return None

    def _times(self) -> tuple[datetime, datetime]:
        now = self.clock()
        return now, now + timedelta(seconds=self.cache_time)

    def _active(self, document: dict) -> bool:
        return document["expires_at"] > self.clock()

    def get_weather_cache(self, cache_key: str) -> pd.DataFrame | None:
        document = self.weather.get(cache_key)
        if not document or not self._active(document):
            return None
        return pd.DataFrame.from_records(deepcopy(document["payload"]))

    def set_weather_cache(self, cache_key: str, dataframe: pd.DataFrame) -> None:
        created_at, expires_at = self._times()
        self.weather[cache_key] = {
            "payload": dataframe.to_dict(orient="records"),
            "created_at": created_at,
            "expires_at": expires_at,
            "scope": parse_cache_key(cache_key),
        }

    def get_raw_weather_cache(self, cache_key: str):
        document = self.weather.get(cache_key)
        if not document or not self._active(document):
            return None
        return deepcopy(document["payload"]), document["created_at"]

    def set_raw_weather_cache(self, cache_key: str, data: dict) -> None:
        created_at, expires_at = self._times()
        self.weather[cache_key] = {
            "payload": deepcopy(data),
            "created_at": created_at,
            "expires_at": expires_at,
            "scope": parse_cache_key(cache_key),
        }

    def get_raw_weather_cache_batch(self, cache_keys: list[str]) -> dict:
        return {
            key: value
            for key in cache_keys
            if (value := self.get_raw_weather_cache(key)) is not None
        }

    def save_alert(
        self, province: str, district: str, forecast_days: int, alert_text: str
    ) -> None:
        created_at, expires_at = self._times()
        self.alerts[(province, district, forecast_days)] = {
            "alert_text": alert_text,
            "created_at": created_at,
            "expires_at": expires_at,
        }

    def get_alert(self, province: str, district: str, forecast_days: int) -> str | None:
        document = self.alerts.get((province, district, forecast_days))
        if not document or not self._active(document):
            return None
        return document["alert_text"]

    def get_all_alerts(self, forecast_days: int) -> dict[str, dict[str, str]]:
        results: dict[str, dict[str, str]] = {}
        for (province, district, days), document in self.alerts.items():
            if days == forecast_days and self._active(document):
                results.setdefault(province, {})[district] = document["alert_text"]
        return results

    def get_alerts_batch(self, keys: list[tuple[str, str, int]]) -> dict:
        return {
            key: value for key in keys if (value := self.get_alert(*key)) is not None
        }

    def purge_cache(
        self, province: str, districts: list[str], forecast_days: int
    ) -> int:
        district_set = set(districts)
        alert_keys = [
            key
            for key in self.alerts
            if key[0] == province
            and key[2] == forecast_days
            and (not district_set or key[1] in district_set)
        ]
        weather_keys = [
            key
            for key, document in self.weather.items()
            if document["scope"].province == province
            and document["scope"].forecast_days == forecast_days
            and (not district_set or document["scope"].district in district_set)
        ]
        for key in alert_keys:
            del self.alerts[key]
        for key in weather_keys:
            del self.weather[key]
        return len(alert_keys) + len(weather_keys)

    def get_cache_stats(self) -> dict[str, int]:
        now = self.clock()
        return {
            "weather_cache_count": sum(
                document["expires_at"] > now for document in self.weather.values()
            ),
            "alerts_count": sum(
                document["expires_at"] > now for document in self.alerts.values()
            ),
            "expired_weather_count": sum(
                document["expires_at"] <= now for document in self.weather.values()
            ),
            "expired_alerts_count": sum(
                document["expires_at"] <= now for document in self.alerts.values()
            ),
        }

    def cleanup_expired_cache(self) -> int:
        now = self.clock()
        weather_keys = [
            key for key, value in self.weather.items() if value["expires_at"] <= now
        ]
        alert_keys = [
            key for key, value in self.alerts.items() if value["expires_at"] <= now
        ]
        for key in weather_keys:
            del self.weather[key]
        for key in alert_keys:
            del self.alerts[key]
        return len(weather_keys) + len(alert_keys)
