"""
Tests for alert generation through the HTTP endpoints
"""

import json
import sqlite3
from unittest.mock import MagicMock

import pytest
from werkzeug.test import TestResponse

from app import app
from extensions import alert_service
from services import database
from services.weather_service import WeatherService
from utils.background import background_tasks

PROVINCE = "PUNJAB"
FORECAST_DAYS = 3

OPEN_METEO_RESPONSE = {
    "daily": {
        "time": ["2024-07-01", "2024-07-02", "2024-07-03"],
        "temperature_2m_max": [41.0, 40.5, 39.0],
        "temperature_2m_min": [29.0, 28.5, 28.0],
        "precipitation_sum": [0.0, 12.5, 60.0],
        "precipitation_probability_max": [5, 60, 90],
        "windspeed_10m_max": [15.0, 22.0, 30.0],
        "windgusts_10m_max": [25.0, 40.0, 55.0],
        "weathercode": [0, 61, 65],
        "snowfall_sum": [0.0, 0.0, 0.0],
        "uv_index_max": [11.0, 9.0, 6.0],
    }
}

OLD_LAHORE_ALERT = {"english": "Old advisory for Lahore.", "urdu": "پرانا پیغام"}
OLD_KASUR_ALERT = {"english": "Old advisory for Kasur.", "urdu": "پرانا پیغام"}
NEW_LAHORE_ALERT = {
    "english": "Heavy rain expected on 3 July.",
    "urdu": "تیز بارش متوقع ہے",
}


class AlertGenerationTestCase:
    """Shared fixtures: temporary database, fake weather API and fake LLM"""

    endpoint: str

    @pytest.fixture(autouse=True)
    def isolated_app(self, tmp_path, monkeypatch) -> None:
        """Use a temporary database and fake the weather API and the LLM"""
        monkeypatch.setattr(database, "DB_FILE", str(tmp_path / "test.db"))
        database.init_db()

        def fake_weather(self, province, districts, forecast_days, cache_time=None):
            return dict.fromkeys(districts, OPEN_METEO_RESPONSE)

        # Patch the class: restoring an instance attribute would leave a bound
        # method behind that shadows class-level patches in other tests
        monkeypatch.setattr(WeatherService, "get_bulk_weather_data", fake_weather)

        self.llm = MagicMock()
        monkeypatch.setattr(alert_service, "client", self.llm)

        app.config["TESTING"] = True
        self.client = app.test_client()

    def llm_replies(self, reply: dict | str) -> None:
        """Set the LLM's reply; a dict is sent as JSON text"""
        if isinstance(reply, dict):
            reply = json.dumps(reply, ensure_ascii=False)
        self.llm.invoke.return_value = MagicMock(content=reply)

    def save_existing_alerts(self, alerts: dict[str, dict]) -> None:
        """Store alerts as if an earlier generation had produced them"""
        alert_service.replace_district_alerts(
            alerts, FORECAST_DAYS, PROVINCE, list(alerts)
        )

    def generate(self, districts: list[str]) -> TestResponse:
        """Request alert generation for the given districts"""
        return self.client.post(
            self.endpoint,
            json={
                "province": PROVINCE,
                "districts": districts,
                "forecast_days": FORECAST_DAYS,
            },
        )

    def stored_alert(self, district: str) -> dict:
        """Fetch the alert the API serves for a district"""
        response = self.client.get(f"/get_alert/{PROVINCE}/{district}/{FORECAST_DAYS}")
        return json.loads(response.data)


class TestGenerateForecastAndAlerts(AlertGenerationTestCase):
    """Test cases for the combined forecast and alert generation endpoint"""

    endpoint = "/generate_forecast_and_alerts"

    def test_generated_alert_is_stored(self):
        """A valid model reply is saved and served for the district"""
        self.llm_replies({"LAHORE": NEW_LAHORE_ALERT})

        response = self.generate(["LAHORE"])

        assert response.status_code == 200
        assert json.loads(response.data)["status"] == "success"
        assert self.stored_alert("LAHORE")["alert"] == NEW_LAHORE_ALERT

    def test_new_alert_replaces_old_alert(self):
        """A valid model reply replaces the alert that was there"""
        self.save_existing_alerts({"LAHORE": OLD_LAHORE_ALERT})
        self.llm_replies({"LAHORE": NEW_LAHORE_ALERT})

        self.generate(["LAHORE"])

        assert self.stored_alert("LAHORE")["alert"] == NEW_LAHORE_ALERT

    def test_unparseable_reply_keeps_existing_alerts(self):
        """A model reply that cannot be parsed leaves old alerts in place"""
        self.save_existing_alerts({"LAHORE": OLD_LAHORE_ALERT})
        self.llm_replies("Sorry, I cannot produce that forecast.")

        response = self.generate(["LAHORE"])

        assert json.loads(response.data)["status"] == "error"
        assert response.status_code == 502
        assert self.stored_alert("LAHORE")["alert"] == OLD_LAHORE_ALERT

    def test_district_missing_from_reply_keeps_its_alert(self):
        """A district the model left out keeps its old alert"""
        self.save_existing_alerts(
            {"LAHORE": OLD_LAHORE_ALERT, "KASUR": OLD_KASUR_ALERT}
        )
        self.llm_replies({"LAHORE": NEW_LAHORE_ALERT})

        self.generate(["LAHORE", "KASUR"])

        assert self.stored_alert("LAHORE")["alert"] == NEW_LAHORE_ALERT
        assert self.stored_alert("KASUR")["alert"] == OLD_KASUR_ALERT

    def test_blank_alert_keeps_existing_alert(self):
        """A reply with no advisory text does not overwrite the old alert"""
        self.save_existing_alerts({"LAHORE": OLD_LAHORE_ALERT})
        self.llm_replies({"LAHORE": {"english": "", "urdu": ""}})

        response = self.generate(["LAHORE"])

        assert response.status_code == 502
        assert self.stored_alert("LAHORE")["alert"] == OLD_LAHORE_ALERT

    def test_summary_without_district_alerts_is_a_failure(self):
        """A reply with only the region summary is not a successful generation"""
        self.save_existing_alerts({"LAHORE": OLD_LAHORE_ALERT})
        self.llm_replies({"Region's Summary": NEW_LAHORE_ALERT})

        response = self.generate(["LAHORE"])

        assert response.status_code == 502
        assert self.stored_alert("LAHORE")["alert"] == OLD_LAHORE_ALERT

    def test_alert_for_unrequested_district_is_not_stored(self):
        """Keys in the reply that were not requested are ignored"""
        self.llm_replies({"LAHORE": NEW_LAHORE_ALERT, "KASUR": NEW_LAHORE_ALERT})

        self.generate(["LAHORE"])

        assert self.stored_alert("LAHORE")["alert"] == NEW_LAHORE_ALERT
        assert self.stored_alert("KASUR")["status"] == "no_data"


class TestGenerateAlertsInBackground(AlertGenerationTestCase):
    """Test cases for the background alert generation endpoint"""

    endpoint = "/generate_alerts"

    @pytest.fixture(autouse=True)
    def run_tasks_inline(self, monkeypatch) -> None:
        """Run background tasks on the calling thread so results are observable"""
        self.task_errors: list[Exception] = []

        def run_inline(task_id, func, *args, **kwargs):
            try:
                func(*args, **kwargs)
            except Exception as e:
                self.task_errors.append(e)

        monkeypatch.setattr(background_tasks, "run_task", run_inline)

    def test_generated_alert_is_stored(self):
        """A valid model reply is saved and served for the district"""
        self.llm_replies({"LAHORE": NEW_LAHORE_ALERT})

        self.generate(["LAHORE"])

        assert self.task_errors == []
        assert self.stored_alert("LAHORE")["alert"] == NEW_LAHORE_ALERT

    def test_unparseable_reply_keeps_existing_alerts(self):
        """A model reply that cannot be parsed fails the task and keeps old alerts"""
        self.save_existing_alerts({"LAHORE": OLD_LAHORE_ALERT})
        self.llm_replies("Sorry, I cannot produce that forecast.")

        self.generate(["LAHORE"])

        assert len(self.task_errors) == 1
        assert self.stored_alert("LAHORE")["alert"] == OLD_LAHORE_ALERT


class TestReplaceAlerts:
    """Test cases for replacing alerts in the database"""

    @pytest.fixture(autouse=True)
    def isolated_database(self, tmp_path, monkeypatch) -> None:
        """Use a temporary database"""
        monkeypatch.setattr(database, "DB_FILE", str(tmp_path / "test.db"))
        database.init_db()

    def test_failed_write_keeps_every_existing_alert(self):
        """If one alert cannot be written, none of the batch is replaced"""
        database.replace_alerts(
            PROVINCE, FORECAST_DAYS, {"LAHORE": "old lahore", "KASUR": "old kasur"}
        )
        unstorable = object()

        with pytest.raises(sqlite3.Error):
            database.replace_alerts(
                PROVINCE, FORECAST_DAYS, {"LAHORE": "new lahore", "KASUR": unstorable}
            )

        assert database.get_alert(PROVINCE, "LAHORE", FORECAST_DAYS) == "old lahore"
        assert database.get_alert(PROVINCE, "KASUR", FORECAST_DAYS) == "old kasur"
