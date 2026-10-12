"""
Tests for AlertService.parse_district_alerts — the REAL implementation.

These tests import the production code path; they must never re-implement the
function under test.
"""

import pytest

from services.alert_service import AlertService


@pytest.fixture(scope="module")
def alert_service() -> AlertService:
    # AlertService.__init__ only constructs a ChatOpenAI client (no I/O).
    return AlertService()


class TestParseDistrictAlerts:
    """Cases for AlertService.parse_district_alerts"""

    def test_pure_json(self, alert_service):
        """Plain JSON object parses into district -> {english, urdu}"""
        text = """
        {
            "Lahore": {
                "english": "Heavy rain expected.",
                "urdu": "بھاری بارش متوقع ہے۔"
            },
            "Region's Summary": {
                "english": "Overall rainy.",
                "urdu": "مجموعی طور پر بارش۔"
            }
        }
        """
        parsed = alert_service.parse_district_alerts(text)

        assert "Lahore" in parsed
        assert parsed["Lahore"]["english"] == "Heavy rain expected."
        assert parsed["Lahore"]["urdu"] == "بھاری بارش متوقع ہے۔"
        assert "Region's Summary" in parsed
        assert parsed["Region's Summary"]["urdu"] == "مجموعی طور پر بارش۔"

    def test_markdown_fenced_json(self, alert_service):
        """```json fences plus surrounding prose are stripped"""
        text = """
        Here is the weather report:
        ```json
        {
            "Islamabad": {
                "english": "Sunny.",
                "urdu": "دھوپ۔"
            }
        }
        ```
        Authentication complete.
        """
        parsed = alert_service.parse_district_alerts(text)

        assert parsed["Islamabad"]["english"] == "Sunny."
        assert parsed["Islamabad"]["urdu"] == "دھوپ۔"

    def test_legacy_string_value(self, alert_service):
        """A bare string value is normalised to {english: str, urdu: ''}"""
        text = """
        {
            "Rawalpindi": "Legacy string format."
        }
        """
        parsed = alert_service.parse_district_alerts(text)

        assert parsed["Rawalpindi"]["english"] == "Legacy string format."
        assert parsed["Rawalpindi"]["urdu"] == ""

    def test_missing_language_keys_default_to_empty(self, alert_service):
        """A district object missing english/urdu gets empty strings"""
        text = '{"Peshawar": {"english": "Windy."}}'
        parsed = alert_service.parse_district_alerts(text)

        assert parsed["Peshawar"]["english"] == "Windy."
        assert parsed["Peshawar"]["urdu"] == ""

    def test_prose_around_json_is_ignored(self, alert_service):
        """Extra text before/after the object does not break extraction"""
        text = (
            'Sure! Here you go: {"Quetta": {"english": "Cold.", "urdu": "سرد۔"}} Hope that helps.'
        )
        parsed = alert_service.parse_district_alerts(text)

        assert parsed["Quetta"]["english"] == "Cold."

    @pytest.mark.parametrize(
        "bad_text",
        [
            "",  # empty
            "No JSON here at all.",  # no braces
            '{"Multan": {"english": "Unclosed',  # truncated JSON
            "{ not: valid json }",  # malformed
        ],
    )
    def test_invalid_input_returns_empty_dict(self, alert_service, bad_text):
        """Any unparseable input degrades to an empty dict, never raises"""
        assert alert_service.parse_district_alerts(bad_text) == {}

    def test_non_string_content_ignored(self, alert_service):
        """Non-dict, non-str district values are skipped, not crashing"""
        text = '{"Sialkot": 42, "Gujranwala": {"english": "ok", "urdu": "ٹھیک"}}'
        parsed = alert_service.parse_district_alerts(text)

        assert "Sialkot" not in parsed
        assert parsed["Gujranwala"]["english"] == "ok"

    def test_returns_empty_dict_on_none_like_input(self, alert_service):
        """Whitespace-only input yields {}"""
        assert alert_service.parse_district_alerts("   \n\t  ") == {}
