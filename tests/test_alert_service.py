"""
Comprehensive tests for alert_service.py
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from services.alert_service import AlertService


class TestAlertService:
    """Test cases for AlertService"""

    def setup_method(self):
        """Set up test fixtures with mocks"""
        self.client_patcher = patch("services.alert_service.ChatOpenAI")
        self.mock_client_class = self.client_patcher.start()

        # Patch database
        self.db_patcher = patch("services.alert_service.database")
        self.mock_db = self.db_patcher.start()

        self.service = AlertService()

    def teardown_method(self):
        """Clean up patches"""
        self.client_patcher.stop()
        self.db_patcher.stop()

    def test_init(self):
        """Test AlertService initialization"""
        assert self.service.client is not None
        self.mock_client_class.assert_called_once_with(
            model="zai-org/glm-4.7-flash",
            base_url="http://127.0.0.1:1234/v1",
            api_key="lm-studio",
            temperature=0.2,
        )

    def test_parse_district_alerts_valid(self):
        """Test parsing valid district alerts"""
        llm_text = """
        {
            "Islamabad": {
                "english": "Expect sunny weather with highs of 25°C.",
                "urdu": "اسلام آباد: دھوپ نکلے گی اور درجہ حرارت 25 ڈگری سینٹی گریڈ تک جائے گا۔"
            },
            "Rawalpindi": {
                "english": "Partly cloudy with chance of light rain.",
                "urdu": "راولپنڈی: جزوی طور پر ابر آلود اور ہلکی بارش کا امکان ہے۔"
            },
            "Region's Summary": {
                "english": "Overall conditions are favorable.",
                "urdu": "مجموعی طور پر حالات سازگار ہیں۔"
            }
        }
        """

        alerts = self.service.parse_district_alerts(llm_text)

        assert len(alerts) == 3
        assert "Islamabad" in alerts
        assert "Rawalpindi" in alerts
        assert "sunny weather" in alerts["Islamabad"]["english"]
        assert "Partly cloudy" in alerts["Rawalpindi"]["english"]

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
        # Mock response
        mock_response = MagicMock()
        mock_response.content = "**Lahore Weather Alert** Test alert"

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

        alert_text = self.service.generate_alert("PUNJAB", forecasts, forecast_days=1)

        assert "Lahore" in alert_text
        assert self.service.client.invoke.called

    def test_generate_alert_reports_lm_studio_connection_failure(self):
        """Connection failures return an actionable LM Studio error."""
        self.service.client.invoke.side_effect = ConnectionRefusedError(
            "connection refused"
        )
        forecasts = {
            "Lahore": pd.DataFrame(
                {
                    "Date": ["2024-01-01"],
                    "Max Temp (°C)": [25.0],
                    "Min Temp (°C)": [15.0],
                }
            )
        }

        with pytest.raises(RuntimeError, match="Start LM Studio"):
            self.service.generate_alert("PUNJAB", forecasts, forecast_days=1)

        self.service.client.invoke.assert_called_once()

    def test_save_district_alerts(self):
        """Test saving district alerts to database"""
        alerts = {
            "Lahore": {"english": "Test alert for Lahore", "urdu": ""},
            "Karachi": {"english": "Test alert for Karachi", "urdu": ""},
        }

        self.service.save_district_alerts(alerts, 1, "PUNJAB")

        # Verify database.save_alert was called twice
        assert self.mock_db.save_alert.call_count == 2

        # JSON dumps for assertions
        import json

        lahore_json = json.dumps(alerts["Lahore"], ensure_ascii=False)
        karachi_json = json.dumps(alerts["Karachi"], ensure_ascii=False)

        # Check calls - order isn't guaranteed in dict so checking any_call is safer
        # But verifying args using call_args_list or assert_any_call
        self.mock_db.save_alert.assert_any_call("PUNJAB", "Lahore", 1, lahore_json)
        self.mock_db.save_alert.assert_any_call("PUNJAB", "Karachi", 1, karachi_json)

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
