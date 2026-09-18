from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from domain.forecast import DataQualityReport, DataStatus, ForecastRun, Location
from repositories.memory import InMemoryRepository
from services.weather_service import WeatherService


CONFIG = {
    "BASE_URL": "https://api.open-meteo.com/v1/forecast",
    "CACHE_TIME": 43200,
    "TIMEZONE": "Asia/Karachi",
    "API_TIMEOUT": 10,
    "FORECAST_FRESH_SECONDS": 10800,
    "FORECAST_STALE_SECONDS": 21600,
}


def build_run(now: datetime) -> ForecastRun:
    return ForecastRun(
        run_id="run-1",
        provider="open-meteo",
        location=Location("PK:PUNJAB:LAHORE", "PUNJAB", "LAHORE", 31.5204, 74.3587),
        requested_days=1,
        retrieved_at=now,
        fresh_until=now + timedelta(hours=3),
        usable_until=now + timedelta(hours=9),
        payload={"daily": {"time": ["2026-09-18"], "temperature_2m_max": [36.0]}},
        quality=DataQualityReport(DataStatus.FRESH, 1, 1),
        checksum="checksum",
        source_url="https://api.open-meteo.com/v1/forecast",
    )


class TestWeatherService:
    def setup_method(self):
        self.repository = InMemoryRepository()
        self.service = WeatherService(CONFIG, self.repository)

    def test_init(self):
        assert self.service.base_url == CONFIG["BASE_URL"]
        assert self.service.repository is self.repository

    def test_get_weather_forecast_uses_fresh_stored_run(self):
        now = datetime.now(UTC)
        self.repository.save_forecast_run(build_run(now))
        self.service.ingestion.provider = MagicMock()

        result = self.service.get_weather_forecast("PUNJAB", "LAHORE", 1)

        assert result["daily"]["temperature_2m_max"] == [36.0]
        assert result["_meta"]["status"] == "fresh"
        assert result["_meta"]["run_id"] == "run-1"
        self.service.ingestion.provider.fetch.assert_not_called()

    def test_get_weather_forecast_fetches_when_missing(self):
        run = build_run(datetime.now(UTC))
        self.service.ingestion.provider = MagicMock()
        self.service.ingestion.provider.fetch.return_value = run

        result = self.service.get_weather_forecast("PUNJAB", "LAHORE", 1)

        assert result["_meta"]["refresh_attempted"] is True
        assert self.repository.get_latest_forecast_run("PK:PUNJAB:LAHORE", 1) == run

    def test_bulk_weather_uses_stored_run_without_api_call(self):
        self.repository.save_forecast_run(build_run(datetime.now(UTC)))
        self.service.ingestion.provider = MagicMock()

        result = self.service.get_bulk_weather_data(
            "PUNJAB", {"LAHORE": (31.5204, 74.3587)}, 1
        )

        assert result["LAHORE"]["_meta"]["status"] == "fresh"
        self.service.ingestion.provider.fetch.assert_not_called()

    def test_bulk_weather_force_refresh_calls_provider(self):
        old_run = build_run(datetime.now(UTC))
        new_run = ForecastRun(
            **{
                **old_run.__dict__,
                "run_id": "run-2",
                "checksum": "checksum-2",
                "retrieved_at": old_run.retrieved_at + timedelta(seconds=1),
            }
        )
        self.repository.save_forecast_run(old_run)
        self.service.ingestion.provider = MagicMock()
        self.service.ingestion.provider.fetch.return_value = new_run

        result = self.service.get_bulk_weather_data(
            "PUNJAB", {"LAHORE": (31.5204, 74.3587)}, 1, cache_time=0
        )

        assert result["LAHORE"]["_meta"]["run_id"] == "run-2"
        self.service.ingestion.provider.fetch.assert_called_once()
