"""
Weather data service for fetching and caching weather information
"""

import os
import time
import json
import requests
import logging
from typing import Dict, List, Optional, Tuple
import pandas as pd
from config import Config
from utils.validation import sanitize_filename
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import database
from datetime import datetime

logger = logging.getLogger(__name__)


class WeatherService:
    """Service for handling weather data operations"""

    def __init__(self):
        self.base_url = Config.BASE_URL
        self.cache_time = Config.CACHE_TIME
        os.makedirs("static/weatherdata", exist_ok=True)
        # SQLite is now used for caching
        self._district_to_province = {}
        self._province_index_built = False

        # Setup connection pooling for better performance
        self.session = requests.Session()

        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[500, 502, 503, 504],
        )

        # Configure connection pooling
        adapter = HTTPAdapter(
            pool_connections=10,  # Number of connection pools
            pool_maxsize=20,  # Maximum number of connections in pool
            max_retries=retry_strategy,
        )

        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        logger.info("Connection pooling initialized with 10 pools, 20 max connections")

    def get_bulk_weather_data(
        self,
        province: str,
        districts: Dict[str, Tuple[float, float]],
        forecast_days: int,
        cache_time: Optional[int] = None,
    ) -> Dict[str, dict]:
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

        uncached = []
        cached_data = {}

        current_time = time.time()
        for district_name, (lat, lon) in districts.items():
            sanitized_district = sanitize_filename(district_name)
            cache_key = f"weather_{forecast_days}_{province}_{sanitized_district}"

            # Check DB cache
            cache_result = database.get_raw_weather_cache(cache_key)

            hit = False
            if cache_result:
                data, created_at = cache_result
                # Calculate age
                age = 9999999
                if isinstance(created_at, datetime):
                    age = (datetime.now() - created_at).total_seconds()
                elif isinstance(created_at, str):
                    try:
                        dt = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                        age = (datetime.now() - dt).total_seconds()
                    except:
                        pass

                if age < cache_time:
                    cached_data[district_name] = data
                    hit = True

            if not hit:
                uncached.append((district_name, lat, lon, cache_key))

        if not uncached:
            return cached_data

        # Try bulk request
        lats = ",".join(str(lat) for (_, lat, _, _) in uncached)
        lons = ",".join(str(lon) for (_, _, lon, _) in uncached)

        params = {
            "latitude": lats,
            "longitude": lons,
            "daily": [
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "precipitation_probability_max",
                "windspeed_10m_max",
                "windgusts_10m_max",
                "weathercode",
                "snowfall_sum",
                "uv_index_max",
            ],
            "timezone": Config.TIMEZONE,
            "forecast_days": forecast_days,
            "current_weather": "true",
        }

        try:
            response = self.session.get(self.base_url, params=params, timeout=Config.API_TIMEOUT)
            bulk = response.json() if response.status_code == 200 else None
        except Exception as e:
            logger.error(f"Bulk request failed: {e}")
            bulk = None

        def _save(district_name: str, payload: dict, cache_key: str):
            """Save data to cache DB"""
            try:
                database.set_raw_weather_cache(cache_key, payload)
                cached_data[district_name] = payload
            except Exception as e:
                logger.error(f"Error saving weather data for {district_name}: {e}")

        if isinstance(bulk, list):
            for i, item in enumerate(bulk):
                if i >= len(uncached):
                    break
                district_name, lat, lon, cache_key = uncached[i]
                if "daily" in item:
                    _save(district_name, item, cache_key)

        elif isinstance(bulk, dict) and "daily" in bulk:
            # Single location response
            if len(uncached) == 1:
                district_name, lat, lon, cache_key = uncached[0]
                _save(district_name, bulk, cache_key)
            else:
                # Fallback for unexpected structure - use individual requests
                logger.info(
                    "Bulk response structure unexpected, falling back to individual requests"
                )
                for district_name, lat, lon, cache_key in uncached:
                    params["latitude"], params["longitude"] = lat, lon
                    try:
                        response = self.session.get(
                            self.base_url, params=params, timeout=Config.API_TIMEOUT
                        )
                        if response.status_code == 200:
                            data = response.json()
                            _save(district_name, data, cache_key)
                        else:
                            logger.error(
                                f"Failed to fetch data for {district_name}: HTTP {response.status_code}"
                            )
                    except Exception as e:
                        logger.error(f"Failed individual request for {district_name}: {e}")

        else:
            # Fallback to individual requests
            logger.info("Bulk request failed, falling back to individual requests")
            for district_name, lat, lon, cache_key in uncached:
                params["latitude"], params["longitude"] = lat, lon
                try:
                    response = self.session.get(
                        self.base_url, params=params, timeout=Config.API_TIMEOUT
                    )
                    if response.status_code == 200:
                        data = response.json()
                        _save(district_name, data, cache_key)
                    else:
                        logger.error(
                            f"Failed to fetch data for {district_name}: HTTP {response.status_code}"
                        )
                except Exception as e:
                    logger.error(f"Failed individual request for {district_name}: {e}")

        return cached_data

    def get_weather_forecast(self, province: str, district: str, days: int) -> Optional[dict]:
        """
        Get weather forecast for a specific district
        """
        cache_key = f"weather_{days}_{province}_{sanitize_filename(district)}"
        cache_result = database.get_raw_weather_cache(cache_key)

        if cache_result:
            return cache_result[0]

        return None

    def purge_cache(self, province: str, districts: List[str], days: int) -> int:
        """
        Purge cache for specific districts (Delegated to database)
        """
        return database.purge_cache_db(province, districts, days)
