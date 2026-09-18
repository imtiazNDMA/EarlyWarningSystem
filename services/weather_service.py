"""
Weather data service for fetching and caching weather information
"""

import logging
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import Config
from domain.forecast import Location
from ingestion.coordinator import ForecastIngestionCoordinator
from ingestion.open_meteo import OpenMeteoProvider
from models import PROVINCES
from repositories.base import Repository
from services import database
from utils.validation import sanitize_filename

logger = logging.getLogger(__name__)


class WeatherService:
    """Service for handling weather data operations"""

    def __init__(
        self, config: dict | None = None, repository: Repository | None = None
    ):
        service_config = config or Config
        self.base_url = service_config["BASE_URL"] if config else Config.BASE_URL
        self.cache_time = (
            service_config["CACHE_TIME"] if config else Config.CACHE_TIME
        )
        self.timezone = service_config["TIMEZONE"] if config else Config.TIMEZONE
        self.api_timeout = (
            service_config["API_TIMEOUT"] if config else Config.API_TIMEOUT
        )
        self.repository = repository
        self._district_to_province = {}
        self._province_index_built = False

        # Setup connection pooling for better performance
        self.session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=5,
            backoff_factor=2,
            status_forcelist=[429, 500, 502, 503, 504],
            respect_retry_after_header=True,
        )

        # Configure connection pooling
        adapter = HTTPAdapter(
            pool_connections=10,  # Number of connection pools
            pool_maxsize=20,  # Maximum number of connections in pool
            max_retries=retry_strategy,
        )

        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        if repository:
            provider = OpenMeteoProvider(
                self.base_url,
                self.api_timeout,
                service_config["FORECAST_FRESH_SECONDS"]
                if config
                else Config.FORECAST_FRESH_SECONDS,
                service_config["FORECAST_STALE_SECONDS"]
                if config
                else Config.FORECAST_STALE_SECONDS,
                self.session,
            )
            self.ingestion = ForecastIngestionCoordinator(provider, repository)
        else:
            self.ingestion = None

        logger.info("Connection pooling initialized with 10 pools, 20 max connections")

    def get_bulk_weather_data(
        self,
        province: str,
        districts: dict[str, tuple[float, float]],
        forecast_days: int,
        cache_time: int | None = None,
    ) -> dict[str, dict]:
        """
        Fetch weather data for multiple districts, using cache when available

        Args:
            province: Province name
            districts: Dict of district_name -> (lat, lon)
            forecast_days: Number of forecast days
            cache_time: Cache timeout in seconds (optional)

        Returns:
            Dict of district_name -> weather_data
        """
        if cache_time is None:
            cache_time = self.cache_time

        if not self.ingestion:
            return self._legacy_bulk_weather(
                province, districts, forecast_days, cache_time
            )

        force_refresh = cache_time == 0
        results = {}
        for district_name, (lat, lon) in districts.items():
            location = Location(
                location_id=f"PK:{province}:{sanitize_filename(district_name)}",
                province=province,
                district=district_name,
                latitude=lat,
                longitude=lon,
                timezone=self.timezone,
            )
            result = self.ingestion.get_forecast(
                location, forecast_days, force_refresh=force_refresh
            )
            if not result.available or not result.run:
                logger.error(
                    "Forecast unavailable for %s: %s",
                    district_name,
                    result.refresh_error or result.status.value,
                )
                continue
            payload = dict(result.run.payload)
            payload["_meta"] = self._metadata(result)
            results[district_name] = payload
        return results

    def _legacy_bulk_weather(
        self,
        province: str,
        districts: dict[str, tuple[float, float]],
        forecast_days: int,
        cache_time: int,
    ) -> dict[str, dict]:
        """Compatibility path for direct construction without a repository."""
        results = {}
        provider = OpenMeteoProvider(
            self.base_url, self.api_timeout, self.cache_time, self.cache_time, self.session
        )
        for district_name, (lat, lon) in districts.items():
            location = Location(
                f"PK:{province}:{sanitize_filename(district_name)}",
                province,
                district_name,
                lat,
                lon,
                self.timezone,
            )
            try:
                run = provider.fetch(location, forecast_days)
                results[district_name] = run.payload
            except Exception as error:
                logger.error("Failed to fetch data for %s: %s", district_name, error)
        return results

    def get_weather_forecast(
        self, province: str, district: str, days: int
    ) -> dict | None:
        """
        Get weather forecast for a specific district
        """
        if self.ingestion:
            coordinates = PROVINCES.get(province, {}).get(district)
            if not coordinates:
                return None
            location = Location(
                location_id=f"PK:{province}:{sanitize_filename(district)}",
                province=province,
                district=district,
                latitude=coordinates[0],
                longitude=coordinates[1],
                timezone=self.timezone,
            )
            result = self.ingestion.get_forecast(location, days)
            if not result.available or not result.run:
                return None
            payload = dict(result.run.payload)
            payload["_meta"] = self._metadata(result)
            return payload
        cache_key = f"weather_{days}_{province}_{sanitize_filename(district)}"
        cache_result = (
            self.repository.get_raw_weather_cache(cache_key)
            if self.repository
            else database.get_raw_weather_cache(cache_key)
        )
        if cache_result:
            return cache_result[0]

        return None

    @staticmethod
    def _metadata(result) -> dict:
        """Build public provenance and freshness metadata for a forecast run."""
        return {
            "run_id": result.run.run_id,
            "provider": result.run.provider,
            "retrieved_at": result.run.retrieved_at.isoformat(),
            "fresh_until": result.run.fresh_until.isoformat(),
            "usable_until": result.run.usable_until.isoformat(),
            "status": result.status.value,
            "quality_status": result.run.quality.status.value,
            "expected_days": result.run.quality.expected_days,
            "returned_days": result.run.quality.returned_days,
            "issues": list(result.run.quality.issues),
            "refresh_attempted": result.refresh_attempted,
            "refresh_error": result.refresh_error,
            "source_url": result.run.source_url,
        }

    def purge_cache(self, province: str, districts: list[str], days: int) -> int:
        """
        Purge cache for specific districts (Delegated to database)
        """
        if self.repository:
            return self.repository.purge_cache(province, districts, days)
        return database.purge_cache_db(province, districts, days)
