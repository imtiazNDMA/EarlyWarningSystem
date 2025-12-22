"""
Tests for weather_service.py
"""

import pytest
import json
import os
from unittest.mock import patch, mock_open
from services.weather_service import WeatherService


class TestWeatherService:
    """Test cases for WeatherService"""

    def setup_method(self):
        """Set up test fixtures"""
        self.service = WeatherService()
        # Clean up any test files
        for f in os.listdir("static/weatherdata"):
            if f.startswith("test_"):
                os.remove(f"static/weatherdata/{f}")

    def teardown_method(self):
        """Clean up after tests"""
        # Clean up test files
        for f in os.listdir("static/weatherdata"):
            if f.startswith("test_"):
                os.remove(f"static/weatherdata/{f}")

    def test_init(self):
        """Test WeatherService initialization"""
        assert self.service.base_url is not None
        assert self.service.cache_time > 0

    @patch("requests.get")
    def test_get_weather_forecast_cached(self, mock_get):
        """Test getting cached weather forecast"""
        # Create mock cached data
        mock_data = {"daily": {"time": ["2024-01-01"], "temperature_2m_max": [25.0]}}

        # Mock file operations
        with patch("builtins.open", mock_open(read_data=json.dumps(mock_data))):
            with patch("os.path.exists", return_value=True):
                result = self.service.get_weather_forecast("PUNJAB", "LAHORE", 1)

        assert result == mock_data

    @patch("requests.get")
    def test_get_weather_forecast_not_found(self, mock_get):
        """Test weather forecast not found"""
        with patch("os.path.exists", return_value=False):
            result = self.service.get_weather_forecast("PUNJAB", "LAHORE", 1)

        assert result is None

    @patch("requests.get")
    @patch("os.path.exists")
    @patch("os.path.getmtime")
    def test_get_bulk_weather_data_cache_hit(self, mock_mtime, mock_exists, mock_get):
        """Test bulk weather data with cache hit"""
        mock_exists.return_value = True
        mock_mtime.return_value = 1000000000  # Old enough to be cached

        mock_data = {"daily": {"time": ["2024-01-01"], "temperature_2m_max": [25.0]}}

        with patch("builtins.open", mock_open(read_data=json.dumps(mock_data))):
            result = self.service.get_bulk_weather_data("PUNJAB", {"LAHORE": (31.5204, 74.3587)}, 1)

        assert "Lahore" in result
        assert result["Lahore"] == mock_data
