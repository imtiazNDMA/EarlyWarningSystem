"""
Tests for Flask endpoints
"""

import json


class TestFlaskEndpoints:
    """Test cases for Flask endpoints"""

    def test_index_get(self, client):
        """Test GET request to index"""
        response = client.get("/")
        assert response.status_code == 200

    def test_health_check(self, client, services):
        """Test health check endpoint"""
        response = client.get("/health")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "healthy"
        services["health"].assert_called_once_with()

    def test_get_districts_valid_province(self, client):
        """Test getting districts for valid province"""
        response = client.get("/get_districts/PUNJAB")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "districts" in data
        assert len(data["districts"]) > 0

    def test_get_districts_invalid_province(self, client):
        """Test getting districts for invalid province"""
        response = client.get("/get_districts/InvalidProvince")
        assert response.status_code == 400

    def test_refresh_map_valid_days(self, client):
        """Test refreshing map with valid forecast days"""
        response = client.get("/refresh_map/3")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "map_html" in data

    def test_refresh_map_invalid_days(self, client):
        """Test refreshing map with invalid forecast days"""
        response = client.get("/refresh_map/10")
        assert response.status_code == 400

    def test_generate_forecast_success(self, client, services):
        """Test successful forecast generation"""
        services["weather"].get_bulk_weather_data.return_value = {
            "LAHORE": {"daily": {}}
        }

        response = client.post(
            "/generate_forecast",
            data=json.dumps(
                {"province": "PUNJAB", "districts": ["LAHORE"], "forecast_days": 3}
            ),
            content_type="application/json",
        )

        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["status"] == "success"
        assert data["requested_districts"] == 1
        assert data["available_districts"] == 1

    def test_generate_forecast_invalid_json(self, client):
        """Test forecast generation with invalid JSON"""
        response = client.post(
            "/generate_forecast", data="invalid json", content_type="application/json"
        )

        assert response.status_code == 400

    def test_generate_forecast_reports_partial_coverage(self, client, services):
        services["weather"].get_bulk_weather_data.return_value = {
            "LAHORE": {"daily": {}, "_meta": {"status": "stale_but_usable"}}
        }

        response = client.post(
            "/generate_forecast",
            json={
                "province": "PUNJAB",
                "districts": ["LAHORE", "MULTAN"],
                "forecast_days": 3,
            },
        )

        assert response.status_code == 206
        data = response.get_json()
        assert data["status"] == "partial"
        assert data["requested_districts"] == 2
        assert data["available_districts"] == 1
        assert data["data_statuses"] == ["stale_but_usable"]

    def test_generate_forecast_too_many_districts(self, client):
        """Test forecast generation with too many districts"""
        districts = [f"District{i}" for i in range(150)]

        response = client.post(
            "/generate_forecast",
            data=json.dumps(
                {"province": "PUNJAB", "districts": districts, "forecast_days": 3}
            ),
            content_type="application/json",
        )

        assert response.status_code == 400
        data = json.loads(response.data)
        assert "Too many districts" in data["message"]

    def test_get_forecast_success(self, client, services):
        """Test getting forecast for a district"""
        services["weather"].get_weather_forecast.return_value = {
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

        response = client.get("/get_forecast/PUNJAB/LAHORE/3")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert "forecast" in data

    def test_get_forecast_invalid_province(self, client):
        """Test getting forecast with invalid province"""
        response = client.get("/get_forecast/InvalidProvince/Lahore/3")
        assert response.status_code == 400
