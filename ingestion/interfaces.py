from typing import Protocol

from domain.forecast import ForecastRun, Location


class ForecastProvider(Protocol):
    def fetch(self, location: Location, forecast_days: int) -> ForecastRun: ...


class ForecastRunRepository(Protocol):
    def initialize_forecast_runs(self) -> None: ...

    def save_forecast_run(self, run: ForecastRun) -> bool: ...

    def get_latest_forecast_run(
        self, location_id: str, forecast_days: int
    ) -> ForecastRun | None: ...

    def acquire_refresh_lease(
        self, location_id: str, forecast_days: int, lease_seconds: int = 120
    ) -> bool: ...

    def release_refresh_lease(self, location_id: str, forecast_days: int) -> None: ...
