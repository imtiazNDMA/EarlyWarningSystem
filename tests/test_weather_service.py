"""
Tests for weather_service.py
"""

import pytest
import json
import os
from unittest.mock import patch, MagicMock
from services.weather_service import WeatherService
from datetime import datetime


class TestWeatherService:
    """Test cases for WeatherService"""

    def setup_method(self):
        """Set up test fixtures"""
        self.service = WeatherService()
        # Clean up any test files (legacy check, can remove if confirmed no usage)
        if os.path.exists("static/weatherdata"):
            for f in os.listdir("static/weatherdata"):
                if f.startswith("test_"):
                    os.remove(f"static/weatherdata/{f}")

    def teardown_method(self):
        """Clean up after tests"""
        pass

    def test_init(self):
        """Test WeatherService initialization"""
        assert self.service.base_url is not None
        assert self.service.cache_time > 0

    @patch("services.weather_service.database")
    def test_get_weather_forecast_cached(self, mock_db):
        """Test getting cached weather forecast"""
        # Create mock cached data
        mock_data = {"daily": {"time": ["2024-01-01"], "temperature_2m_max": [25.0]}}
        # Mock DB return: (data, created_at)
        mock_db.get_raw_weather_cache.return_value = (mock_data, datetime.now())

        result = self.service.get_weather_forecast("PUNJAB", "LAHORE", 1)

        assert result == mock_data
        mock_db.get_raw_weather_cache.assert_called_once()

    @patch("services.weather_service.database")
    def test_get_weather_forecast_not_found(self, mock_db):
        """Test weather forecast not found"""
        mock_db.get_raw_weather_cache.return_value = None
        result = self.service.get_weather_forecast("PUNJAB", "LAHORE", 1)
        assert result is None

    @patch("services.weather_service.requests.Session.get")
    @patch("services.weather_service.database")
    def test_get_bulk_weather_data_cache_hit(self, mock_db, mock_get):
        """Test bulk weather data with cache hit"""
        mock_data = {"daily": {"time": ["2024-01-01"], "temperature_2m_max": [25.0]}}
        
        # Mock cache hit for specific key
        def get_raw_side_effect(key):
            if "LAHORE" in key:
                return (mock_data, datetime.now())
            return None

        mock_db.get_raw_weather_cache.side_effect = get_raw_side_effect

        result = self.service.get_bulk_weather_data(
            "PUNJAB", {"LAHORE": (31.5204, 74.3587)}, 1
        )

        assert "LAHORE" in result
        assert result["LAHORE"] == mock_data
