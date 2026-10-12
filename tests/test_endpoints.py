"""
Tests for Flask endpoints
"""

import json
from unittest.mock import patch

from app import app

# Complete 1-day payload: every key create_weather_dataframe reads must be present
# and every array must be the same length (pandas raises otherwise).
_ONE_DAY_DAILY = {
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
        # api_routes binds the name at import time, so patch the route module's
        # reference — patching utils.health_check alone leaves the real
        # implementation (and its outbound HTTP calls) in play.
        with patch("routes.api_routes.get_health_status") as mock_health:
            mock_health.return_value = {"status": "healthy", "checks": {}}

            response = self.client.get("/health")
            assert response.status_code == 200
            data = json.loads(response.data)
            assert data["status"] == "healthy"

    def test_get_districts_valid_province(self):
        """Test getting districts for valid province"""
        response = self.client.get("/get_districts/PUNJAB")
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
            data=json.dumps({"province": "PUNJAB", "districts": ["LAHORE"], "forecast_days": 3}),
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
            data=json.dumps({"province": "PUNJAB", "districts": districts, "forecast_days": 3}),
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

        response = self.client.get("/get_forecast/PUNJAB/LAHORE/3")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "forecast" in data

    def test_get_forecast_invalid_province(self):
        """Test getting forecast with invalid province"""
        response = self.client.get("/get_forecast/InvalidProvince/Lahore/3")
        assert response.status_code == 400

    @patch("services.weather_service.WeatherService.get_bulk_weather_data")
    def test_generate_forecast_no_districts(self, mock_weather):
        """Regression (F-02): an empty districts list must not raise NameError
        — weather_data is now computed on both branches."""
        mock_weather.return_value = {}

        response = self.client.post(
            "/generate_forecast",
            data=json.dumps({"province": "PUNJAB", "districts": [], "forecast_days": 3}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"

    @patch("services.alert_service.AlertService.save_district_alerts")
    @patch("services.alert_service.AlertService.purge_cache")
    @patch("services.alert_service.AlertService.parse_district_alerts")
    @patch("services.alert_service.AlertService.generate_alert")
    @patch("services.weather_service.WeatherService.get_bulk_weather_data")
    def test_generate_alerts_is_synchronous_without_task_id(
        self, mock_weather, mock_generate, mock_parse, mock_purge, mock_save
    ):
        """Regression (D1/F-09): /generate_alerts runs synchronously and must
        not return a task_id nobody polls."""
        mock_weather.return_value = {"LAHORE": {"daily": _ONE_DAY_DAILY}}
        mock_generate.return_value = '{"LAHORE": {}, "Region\'s Summary": {}}'
        mock_parse.return_value = {"LAHORE": {}, "Region's Summary": {}}
        mock_purge.return_value = 0

        response = self.client.post(
            "/generate_alerts",
            data=json.dumps({"province": "PUNJAB", "districts": ["LAHORE"], "forecast_days": 1}),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert "task_id" not in data
        assert mock_generate.called

    @patch("services.alert_service.AlertService.save_district_alerts")
    @patch("services.alert_service.AlertService.purge_cache")
    @patch("services.alert_service.AlertService.generate_alert")
    @patch("services.weather_service.WeatherService.get_bulk_weather_data")
    def test_generate_alerts_rejects_invalid_llm_json_without_purging_cache(
        self, mock_weather, mock_generate, mock_purge, mock_save
    ):
        """Malformed Qwen output must fail instead of reporting false success."""
        mock_weather.return_value = {"LAHORE": {"daily": _ONE_DAY_DAILY}}
        mock_generate.return_value = ""

        response = self.client.post(
            "/generate_alerts",
            data=json.dumps({"province": "PUNJAB", "districts": ["LAHORE"], "forecast_days": 1}),
            content_type="application/json",
        )

        assert response.status_code == 502
        assert response.get_json()["status"] == "error"
        mock_purge.assert_not_called()
        mock_save.assert_not_called()

    @patch("services.weather_service.WeatherService.get_bulk_weather_data")
    def test_combined_generation_returns_502_when_weather_fetch_fails(self, mock_weather):
        """Weather upstream failures need an error HTTP status for the browser."""
        mock_weather.return_value = {}

        response = self.client.post(
            "/generate_forecast_and_alerts",
            data=json.dumps({"province": "PUNJAB", "districts": ["LAHORE"], "forecast_days": 1}),
            content_type="application/json",
        )

        assert response.status_code == 502
        assert response.get_json()["status"] == "error"

    def test_favicon_request_does_not_return_404(self):
        """Browsers request /favicon.ico automatically; keep the console clean."""
        response = self.client.get("/favicon.ico")

        assert response.status_code in (200, 204)

    @patch("requests.sessions.Session.request")
    def test_health_endpoint_degrades_without_network(self, mock_request):
        """With outbound HTTP blocked, /health must return a well-formed
        degraded payload (503) instead of hanging or leaking an exception."""
        import requests as requests_lib

        mock_request.side_effect = requests_lib.ConnectionError("no network")

        response = self.client.get("/health")

        assert response.status_code in (200, 503)
        data = json.loads(response.data)
        assert data["status"] in ("healthy", "unhealthy")
        assert mock_request.called  # the real checks ran, offline

    @patch("routes.api_routes.get_health_status")
    def test_health_endpoint_uses_route_module_reference(self, mock_health):
        """F-03 regression guard: the route reads get_health_status from
        routes.api_routes (import-time binding). Patching utils.health_check
        alone does NOT affect the route — this documents why."""
        mock_health.return_value = {"status": "healthy", "checks": {}}

        response = self.client.get("/health")

        assert response.status_code == 200
        assert mock_health.called
