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
        """Set up test fixtures"""
        self.service = AlertService()

    def test_init(self):
        """Test AlertService initialization"""
        assert self.service.client is not None

    def test_parse_district_alerts_valid(self):
        """Test parsing valid district alerts"""
        llm_text = """
        **Islamabad Weather Alert** Expect sunny weather with highs of 25°C.
        **Rawalpindi Weather Alert** Partly cloudy with chance of light rain.
        
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

    @patch('services.alert_service.ChatOllama')
    def test_generate_alert_success(self, mock_ollama):
        """Test successful alert generation"""
        # Mock the Ollama response
        mock_response = MagicMock()
        mock_response.content = "**Lahore Weather Alert** Test alert"
        
        mock_client = MagicMock()
        mock_client.invoke.return_value = mock_response
        mock_ollama.return_value = mock_client
        
        # Create test service with mocked client
        service = AlertService()
        service.client = mock_client
        
        # Create test forecast data
        forecasts = {
            "Lahore": pd.DataFrame({
                "Date": ["2024-01-01"],
                "Max Temp (°C)": [25.0],
                "Min Temp (°C)": [15.0],
                "Precipitation (mm)": [0.0],
                "Precipitation Chance (%)": [10],
                "Wind Speed (km/h)": [15.0],
                "Wind Gusts (km/h)": [20.0],
                "Weather Code": [0],
                "Snowfall (cm)": [0.0],
                "UV Index Max": [5.0]
            })
        }
        
        alert_text = service.generate_alert("Punjab", forecasts)
        
        assert "Lahore" in alert_text
        assert mock_client.invoke.called

    @patch('builtins.open', create=True)
    @patch('os.makedirs')
    def test_save_district_alerts(self, mock_makedirs, mock_open):
        """Test saving district alerts to files"""
        alerts = {
            "Lahore": "Test alert for Lahore",
            "Karachi": "Test alert for Karachi"
        }
        
        self.service.save_district_alerts(alerts, 1, "Punjab")
        
        # Verify makedirs was called
        mock_makedirs.assert_called()
        
        # Verify files were written
        assert mock_open.call_count >= 2

    @patch('builtins.open', create=True)
    @patch('os.path.exists')
    def test_get_alert_found(self, mock_exists, mock_open):
        """Test getting an existing alert"""
        mock_exists.return_value = True
        mock_data = {"district": "Lahore", "alert": "Test alert"}
        mock_open.return_value.__enter__.return_value.read.return_value = json.dumps(mock_data)
        
        result = self.service.get_alert("Punjab", "Lahore", 1)
        
        assert result is not None
        assert result["district"] == "Lahore"

    @patch('os.path.exists')
    def test_get_alert_not_found(self, mock_exists):
        """Test getting a non-existent alert"""
        mock_exists.return_value = False
        
        result = self.service.get_alert("Punjab", "NonExistent", 1)
        
        assert result is None
