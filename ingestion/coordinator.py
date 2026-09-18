import threading
import time
from collections.abc import Callable
from datetime import datetime

from domain.forecast import DataStatus, ForecastResult, ForecastRun, Location, utc_now
from ingestion.interfaces import ForecastProvider, ForecastRunRepository


class ForecastIngestionCoordinator:
    """Serve stored forecasts and refresh each location at most once concurrently."""

    def __init__(
        self,
        provider: ForecastProvider,
        repository: ForecastRunRepository,
        clock: Callable[[], datetime] = utc_now,
        ensemble_provider: ForecastProvider | None = None,
    ) -> None:
        self.provider = provider
        self.repository = repository
        self.clock = clock
        self.ensemble_provider = ensemble_provider
        self._locks: dict[tuple[str, int], threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def get_forecast(  # noqa: C901 - state policy is intentionally centralized.
        self, location: Location, forecast_days: int, force_refresh: bool = False
    ) -> ForecastResult:
        latest = self.repository.get_latest_forecast_run(
            location.location_id, forecast_days
        )
        now = self.clock()
        if (
            latest
            and latest.freshness_at(now) == DataStatus.FRESH
            and not force_refresh
        ):
            return ForecastResult(latest, DataStatus.FRESH, False)

        key = (location.location_id, forecast_days)
        lock = self._get_lock(key)
        with lock:
            latest = self.repository.get_latest_forecast_run(
                location.location_id, forecast_days
            )
            now = self.clock()
            if (
                latest
                and latest.freshness_at(now) == DataStatus.FRESH
                and not force_refresh
            ):
                return ForecastResult(latest, DataStatus.FRESH, False)

            if not self.repository.acquire_refresh_lease(
                location.location_id, forecast_days
            ):
                for _ in range(20):
                    time.sleep(0.1)
                    refreshed = self.repository.get_latest_forecast_run(
                        location.location_id, forecast_days
                    )
                    if refreshed and refreshed.freshness_at(self.clock()) in {
                        DataStatus.FRESH,
                        DataStatus.STALE_USABLE,
                    }:
                        return ForecastResult(
                            refreshed, refreshed.freshness_at(self.clock()), False
                        )
                if latest and latest.freshness_at(now) == DataStatus.STALE_USABLE:
                    return ForecastResult(latest, DataStatus.STALE_USABLE, False)
                return ForecastResult(
                    None, DataStatus.UNAVAILABLE, False, "refresh already in progress"
                )

            try:
                run = self.provider.fetch(location, forecast_days)
                if self.ensemble_provider is not None:
                    try:
                        ensemble_run = self.ensemble_provider.fetch(
                            location, forecast_days
                        )
                        if ensemble_run.corroboration is not None:
                            run = ForecastRun(
                                run_id=run.run_id,
                                provider=run.provider,
                                location=run.location,
                                requested_days=run.requested_days,
                                retrieved_at=run.retrieved_at,
                                fresh_until=run.fresh_until,
                                usable_until=run.usable_until,
                                payload=run.payload,
                                quality=run.quality,
                                checksum=run.checksum,
                                source_url=run.source_url,
                                schema_version=run.schema_version,
                                corroboration=ensemble_run.corroboration,
                            )
                    except Exception:  # noqa: S110 - ensemble is best-effort
                        pass
                run_status = run.freshness_at(self.clock())
                if run_status in {DataStatus.PARTIAL, DataStatus.INVALID}:
                    if latest and latest.freshness_at(self.clock()) in {
                        DataStatus.FRESH,
                        DataStatus.STALE_USABLE,
                    }:
                        return ForecastResult(
                            latest,
                            latest.freshness_at(self.clock()),
                            True,
                            f"provider returned {run_status.value} data",
                        )
                    return ForecastResult(run, run_status, True)
                self.repository.save_forecast_run(run)
                stored = self.repository.get_latest_forecast_run(
                    location.location_id, forecast_days
                )
                effective = stored or run
                return ForecastResult(
                    effective, effective.freshness_at(self.clock()), True
                )
            except Exception as error:
                if latest:
                    status = latest.freshness_at(now)
                    if status in {DataStatus.FRESH, DataStatus.STALE_USABLE}:
                        return ForecastResult(latest, status, True, str(error))
                return ForecastResult(None, DataStatus.UNAVAILABLE, True, str(error))
            finally:
                self.repository.release_refresh_lease(
                    location.location_id, forecast_days
                )

    def _get_lock(self, key: tuple[str, int]) -> threading.Lock:
        with self._locks_guard:
            lock = self._locks.setdefault(key, threading.Lock())
            if len(self._locks) > 1000:
                self._locks = {key: lock}
            return lock
