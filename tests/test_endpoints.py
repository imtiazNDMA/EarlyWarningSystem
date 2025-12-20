"""
Tests for Flask endpoints
"""

import pytest
import json
from unittest.mock import patch, MagicMock
from app import app


class TestFlaskEndpoints:
    """Test cases for Flask endpoints"""

    def setup_method(self):
        """Set up test fixtures"""
        self.app = app
        self.client = self.app.test_client()
        self.app.config["TESTING"] = True

    def test_index_get(self):
        """Test GET request to index"""
        response = self.client.get("/")
        assert response.status_code == 200

    def test_health_check(self):
        """Test health check endpoint"""
        with patch("health.get_health_status") as mock_health:
            mock_health.return_value = {"status": "healthy", "checks": {}}

            response = self.client.get("/health")
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["status"] == "healthy"

    def test_get_districts_valid_province(self):
        """Test getting districts for valid province"""
        response = self.client.get("/get_districts/Punjab")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "districts" in data
        assert len(data["districts"]) > 0

    def test_get_districts_invalid_province(self):
        """Test getting districts for invalid province"""
        response = self.client.get("/get_districts/InvalidProvince")
        assert response.status_code == 400

    def test_refresh_map_valid_days(self):
        """Test refreshing map with valid forecast days"""
        response = self.client.get("/refresh_map/3")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "map_html" in data

    def test_refresh_map_invalid_days(self):
        """Test refreshing map with invalid forecast days"""
        response = self.client.get("/refresh_map/10")
        assert response.status_code == 400

    @patch("services.weather_service.WeatherService.get_bulk_weather_data")
    def test_generate_forecast_success(self, mock_weather):
        """Test successful forecast generation"""
        mock_weather.return_value = {"Lahore": {"daily": {}}}

        response = self.client.post(
            "/generate_forecast",
            data=json.dumps(
                {"province": "Punjab", "districts": ["Lahore"], "forecast_days": 3}
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"

    def test_generate_forecast_invalid_json(self):
        """Test forecast generation with invalid JSON"""
        response = self.client.post(
            "/generate_forecast", data="invalid json", content_type="application/json"
        )

        assert response.status_code == 400

    def test_generate_forecast_too_many_districts(self):
        """Test forecast generation with too many districts"""
        districts = [f"District{i}" for i in range(150)]

        response = self.client.post(
            "/generate_forecast",
            data=json.dumps(
                {"province": "Punjab", "districts": districts, "forecast_days": 3}
            ),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "Too many districts" in data["message"]

    @patch("services.weather_service.WeatherService.get_weather_forecast")
    def test_get_forecast_success(self, mock_forecast):
        """Test getting forecast for a district"""
        mock_forecast.return_value = {
            "daily": {
                "time": ["2024-01-01"],
                "temperature_2m_max": [25.0],
                "temperature_2m_min": [15.0],
                "precipitation_sum": [0.0],
                "precipitation_probability_max": [10],
                "windspeed_10m_max": [15.0],
                "windgusts_10m_max": [20.0],
                "weathercode": [0],
                "snowfall_sum": [0.0],
                "uv_index_max": [5.0],
            }
        }

        response = self.client.get("/get_forecast/Punjab/Lahore/3")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "forecast" in data

    def test_get_forecast_invalid_province(self):
        """Test getting forecast with invalid province"""
        response = self.client.get("/get_forecast/InvalidProvince/Lahore/3")
        assert response.status_code == 400
