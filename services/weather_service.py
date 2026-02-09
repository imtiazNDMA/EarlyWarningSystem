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
from services import database
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

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

        # Parallel fetching for uncached districts
        def fetch_single_district(district_info):
            """Fetch weather for a single district"""
            district_name, lat, lon, cache_key = district_info
            params = {
                "latitude": lat,
                "longitude": lon,
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
                if response.status_code == 200:
                    data = response.json()
                    return (district_name, data, cache_key, None)
                else:
                    return (district_name, None, cache_key, f"HTTP {response.status_code}")
            except Exception as e:
                return (district_name, None, cache_key, str(e))

        # Use ThreadPoolExecutor for parallel fetching (limit to 15 workers to avoid overwhelming API)
        logger.info(f"Fetching weather data for {len(uncached)} districts in parallel")
        with ThreadPoolExecutor(max_workers=15) as executor:
            futures = {executor.submit(fetch_single_district, info): info for info in uncached}
            
            for future in as_completed(futures):
                district_name, data, cache_key, error = future.result()
                if data:
                    try:
                        database.set_raw_weather_cache(cache_key, data)
                        cached_data[district_name] = data
                        logger.debug(f"Fetched and cached weather for {district_name}")
                    except Exception as e:
                        logger.error(f"Error saving weather data for {district_name}: {e}")
                else:
                    logger.error(f"Failed to fetch data for {district_name}: {error}")

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
