"""
Comprehensive tests for alert_service.py
"""

import pytest
import json
from unittest.mock import patch, MagicMock
import pandas as pd
from services.alert_service import AlertService


class TestAlertService:
    """Test cases for AlertService"""

    def setup_method(self):
        """Set up test fixtures with mocks"""
        # Patch ChatOllama to avoid connection attempts
        self.ollama_patcher = patch("services.alert_service.ChatOllama")
        self.mock_ollama = self.ollama_patcher.start()

        # Patch database
        self.db_patcher = patch("services.alert_service.database")
        self.mock_db = self.db_patcher.start()

        self.service = AlertService()

    def teardown_method(self):
        """Clean up patches"""
        self.ollama_patcher.stop()
        self.db_patcher.stop()

    def test_init(self):
        """Test AlertService initialization"""
        assert self.service.client is not None
        assert self.mock_ollama.called

    def test_parse_district_alerts_valid(self):
        """Test parsing valid district alerts"""
        llm_text = """
        **Islamabad**: Expect sunny weather with highs of 25°C.
        **Rawalpindi**: Partly cloudy with chance of light rain.

        Region's Summary: Overall conditions are favorable.
        """

        alerts = self.service.parse_district_alerts(llm_text)

        assert len(alerts) == 2
        assert "Islamabad" in alerts
        assert "Rawalpindi" in alerts
        assert "sunny weather" in alerts["Islamabad"]
        assert "Partly cloudy" in alerts["Rawalpindi"]

    def test_parse_district_alerts_empty(self):
        """Test parsing empty alert text"""
        alerts = self.service.parse_district_alerts("")
        assert len(alerts) == 0

    def test_parse_district_alerts_no_matches(self):
        """Test parsing text with no district alerts"""
        llm_text = "This is just some random text without proper formatting."
        alerts = self.service.parse_district_alerts(llm_text)
        assert len(alerts) == 0

    def test_generate_alert_success(self):
        """Test successful alert generation"""
        # Mock the client instance returned by ChatOllama()
        mock_client = MagicMock()
        self.mock_ollama.return_value = mock_client

        # Mock response
        mock_response = MagicMock()
        mock_response.content = "**Lahore Weather Alert** Test alert"
        mock_client.invoke.return_value = mock_response

        # Re-init service to pick up the mock return value if needed
        # But self.service.client is already set to the return value of the previous mock run in setup?
        # AlertService init calls ChatOllama().
        # self.mock_ollama returned a MagicMock() by default.
        # So self.service.client IS that mock.
        # We just need to configure it.
        self.service.client.invoke.return_value = mock_response

        # Create test forecast data
        forecasts = {
            "Lahore": pd.DataFrame(
                {
                    "Date": ["2024-01-01"],
                    "Max Temp (°C)": [25.0],
                    "Min Temp (°C)": [15.0],
                    "Precipitation (mm)": [0.0],
                    "Precipitation Chance (%)": [10],
                    "Wind Speed (km/h)": [15.0],
                    "Wind Gusts (km/h)": [20.0],
                    "Weather Code": [0],
                    "Snowfall (cm)": [0.0],
                    "UV Index Max": [5.0],
                }
            )
        }

        alert_text = self.service.generate_alert("PUNJAB", forecasts)

        assert "Lahore" in alert_text
        assert self.service.client.invoke.called

    def test_save_district_alerts(self):
        """Test saving district alerts to database"""
        alerts = {
            "Lahore": "Test alert for Lahore",
            "Karachi": "Test alert for Karachi",
        }

        self.service.save_district_alerts(alerts, 1, "PUNJAB")

        # Verify database.save_alert was called twice
        assert self.mock_db.save_alert.call_count == 2

        # Check calls - order isn't guaranteed in dict so checking any_call is safer
        # But verifying args using call_args_list or assert_any_call
        self.mock_db.save_alert.assert_any_call("PUNJAB", "Lahore", 1, "Test alert for Lahore")
        self.mock_db.save_alert.assert_any_call("PUNJAB", "Karachi", 1, "Test alert for Karachi")

    def test_get_alert_found(self):
        """Test getting an existing alert from DB"""
        self.mock_db.get_alert.return_value = "Test alert content"

        result = self.service.get_alert("PUNJAB", "LAHORE", 1)
        assert result is not None
        self.mock_db.get_alert.assert_called_with("PUNJAB", "LAHORE", 1)

    def test_get_alert_not_found(self):
        """Test getting a non-existent alert from DB"""
        self.mock_db.get_alert.return_value = None

        result = self.service.get_alert("PUNJAB", "NONEXISTENT", 1)

        assert result is None

    def test_purge_cache(self):
        """Test purging cache via DB"""
        self.mock_db.purge_cache_db.return_value = 5

        count = self.service.purge_cache("PUNJAB", ["LAHORE"], 1)
        assert count == 5
        self.mock_db.purge_cache_db.assert_called_with("PUNJAB", ["LAHORE"], 1)
