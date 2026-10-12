"""
Comprehensive tests for alert_service.py
"""

from unittest.mock import MagicMock, patch

import pandas as pd

from services.alert_service import AlertService


class TestAlertService:
    """Test cases for AlertService"""

    def setup_method(self):
        """Set up test fixtures with mocks"""
        # Patch ChatOpenAI so __init__ never opens a socket to the LM Studio server
        self.llm_patcher = patch("services.alert_service.ChatOpenAI")
        self.mock_llm = self.llm_patcher.start()

        # Patch database
        self.db_patcher = patch("services.alert_service.database")
        self.mock_db = self.db_patcher.start()

        self.service = AlertService()

    def teardown_method(self):
        """Clean up patches"""
        self.llm_patcher.stop()
        self.db_patcher.stop()

    def test_init(self):
        """Test AlertService initialization"""
        assert self.service.client is not None
        assert self.mock_llm.called

    def test_init_uses_configured_openai_endpoint(self):
        """Regression: the client must target the configured OpenAI-compatible
        server (LM Studio), not a hardcoded Ollama endpoint."""
        from config import Config

        _, kwargs = self.mock_llm.call_args

        assert kwargs["model"] == Config.LLM_MODEL
        assert kwargs["base_url"] == Config.LLM_BASE_URL
        assert kwargs["api_key"] == Config.LLM_API_KEY
        assert kwargs["temperature"] == Config.LLM_TEMPERATURE
        assert kwargs["timeout"] == Config.LLM_TIMEOUT
        assert kwargs["max_retries"] == Config.LLM_MAX_RETRIES

    def test_init_wired_to_chat_openai_not_ollama(self):
        """The import-time symbol must be langchain_openai.ChatOpenAI."""
        import services.alert_service as alert_module

        assert getattr(alert_module, "ChatOpenAI", None) is not None
        assert not hasattr(alert_module, "ChatOllama")

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

    def test_parse_district_alerts_handles_unclosed_thinking_block(self):
        """Qwen may omit the closing think tag while still returning valid JSON."""
        llm_text = '<think>reasoning interrupted\n{"Lahore": {"english": "Clear.", "urdu": "صاف۔"}}'

        alerts = self.service.parse_district_alerts(llm_text)

        assert alerts["Lahore"]["english"] == "Clear."

    def test_generate_alert_success(self):
        """Test successful alert generation"""
        mock_response = MagicMock()
        mock_response.content = "**Lahore Weather Alert** Test alert"
        # setup_method patched ChatOpenAI, so self.service.client IS the mock.
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

    @staticmethod
    def _forecasts(rows: int) -> dict:
        return {
            "Lahore": pd.DataFrame(
                {
                    "Date": [f"2024-01-0{i + 1}" for i in range(rows)],
                    "Max Temp (°C)": [25.0] * rows,
                    "Min Temp (°C)": [15.0] * rows,
                    "Precipitation (mm)": [0.0] * rows,
                    "Weather Code": [0] * rows,
                }
            )
        }

    def _capture_prompt(self) -> str:
        """HumanMessage content from the last client.invoke() call"""
        messages = self.service.client.invoke.call_args[0][0]
        return messages[1].content

    def test_generate_alert_prompt_contains_forecast_days(self):
        """Regression (F-01): the prompt must interpolate forecast_days, not
        leave a bare name that raises NameError at f-string build time."""
        mock_response = MagicMock()
        mock_response.content = "{}"
        self.service.client.invoke.return_value = mock_response

        self.service.generate_alert("PUNJAB", self._forecasts(3), forecast_days=3)

        prompt = self._capture_prompt()
        assert "forecast_days" not in prompt, "uninterpolated placeholder in prompt"
        assert "FULL 3-DAY PERIOD" in prompt

    def test_generate_alert_derives_forecast_days_from_dataframe(self):
        """When forecast_days is omitted it must fall back to the frame length."""
        mock_response = MagicMock()
        mock_response.content = "{}"
        self.service.client.invoke.return_value = mock_response

        self.service.generate_alert("PUNJAB", self._forecasts(5))

        prompt = self._capture_prompt()
        assert "forecast_days" not in prompt
        assert "FULL 5-DAY PERIOD" in prompt

    def test_generate_alert_empty_forecasts_defaults_to_one_day(self):
        """No frames at all still builds a valid prompt (no NameError)."""
        mock_response = MagicMock()
        mock_response.content = "{}"
        self.service.client.invoke.return_value = mock_response

        self.service.generate_alert("PUNJAB", {})

        prompt = self._capture_prompt()
        assert "FULL 1-DAY PERIOD" in prompt


class TestCleanLLMResponse:
    """Qwen3-class models may wrap reasoning in tags and fence the JSON."""

    # Built by concatenation: writing the literal markers inline in source has
    # repeatedly backfired (backtick / tag markers getting mangled on write).
    THINK_OPEN = "<" + "think>"
    THINK_CLOSE = "</" + "think>"

    @staticmethod
    def _fenced(payload):
        return "```json\n" + payload + "\n```"

    @classmethod
    def _think(cls, prose, payload):
        return cls.THINK_OPEN + prose + cls.THINK_CLOSE + "\n" + cls._fenced(payload)

    def test_strips_json_fence(self):
        raw = self._fenced('{"Lahore": {"english": "x", "urdu": "y"}}')
        cleaned = AlertService.clean_llm_response(raw)
        assert cleaned == '{"Lahore": {"english": "x", "urdu": "y"}}'

    def test_strips_thinking_block(self):
        raw = self.THINK_OPEN + "reason about Lahore" + self.THINK_CLOSE + '\n{"a": 1}'
        cleaned = AlertService.clean_llm_response(raw)
        assert "reason about Lahore" not in cleaned
        assert cleaned == '{"a": 1}'

    def test_thinking_block_then_fence(self):
        raw = self._think("plan the district order", '{"ok": true}')
        assert AlertService.clean_llm_response(raw) == '{"ok": true}'

    def test_plain_json_untouched(self):
        assert AlertService.clean_llm_response('{"a": 1}') == '{"a": 1}'

    def test_generate_alert_returns_parsable_json(self):
        """End-to-end: raw reasoning + fence in, parseable advisory out."""
        with patch("services.alert_service.ChatOpenAI"), patch("services.alert_service.database"):
            service = AlertService()

        payload = (
            '{"Lahore": {"english": "Rain expected.", "urdu": "BARSH"}, '
            '"Region\'s Summary": {"english": "Mixed.", "urdu": "MIX"}}'
        )
        service.client = MagicMock()
        service.client.invoke.return_value = MagicMock(
            content=self._think("district order first", payload)
        )

        text = service.generate_alert("PUNJAB", {}, forecast_days=1)
        alerts = service.parse_district_alerts(text)

        assert alerts["Lahore"]["english"] == "Rain expected."
        assert alerts["Lahore"]["urdu"] == "BARSH"
