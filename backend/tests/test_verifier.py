"""Tests for the alert draft verifier: pure checks against the evidence."""

import datetime as dt
from typing import Any

import pytest
from pydantic import ValidationError

from ews.alerts.text import write_alert_text
from ews.drafting.verifier import AlertDraft, Facts, verify
from ews.screening.rules import Signal

EVIDENCE = [
    {"snapshot_id": 7, "date": "2026-10-09", "value": 120.3, "threshold": 100.0},
    {"snapshot_id": 7, "date": "2026-10-10", "value": 60.0, "threshold": 100.0},
]
FACTS = Facts(
    hazard="heavy_rain",
    severity="severe",
    onset=dt.date(2026, 10, 9),
    expires=dt.date(2026, 10, 10),
    evidence=EVIDENCE,
)


def draft(**overrides: Any) -> AlertDraft:
    text = {
        "headline": "Severe heavy rain alert for Lahore",
        "body": "Rainfall is forecast to peak at 120 mm on 9 October, above the "
        "threshold of 100 mm, and to continue on 10 October.",
        "instructions": "Avoid low-lying areas and stream crossings.",
    }
    return AlertDraft(**{**text, **overrides})


class TestSchema:
    """Test cases for the structure a draft must have"""

    @pytest.mark.parametrize("field", ["headline", "body", "instructions"])
    def test_every_part_is_required_and_non_empty(self, field: str) -> None:
        with pytest.raises(ValidationError, match=field):
            draft(**{field: ""})

    def test_an_overlong_headline_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="headline"):
            draft(headline="Severe " * 30)


class TestGrounding:
    """Test cases for numbers and dates matching the evidence"""

    def test_a_grounded_draft_passes(self) -> None:
        assert verify(draft(), FACTS) == []

    def test_an_invented_number_is_rejected(self) -> None:
        problems = verify(draft(body="Up to 300 mm may fall on 9 October."), FACTS)

        assert problems == ["The number 300 is not in the evidence."]

    def test_rounding_within_tolerance_is_accepted(self) -> None:
        assert verify(draft(body="About 120 mm is forecast on 9 October."), FACTS) == []
        assert verify(draft(body="Exactly 120.3 mm on 9 October."), FACTS) == []

    def test_a_value_just_outside_tolerance_is_rejected(self) -> None:
        problems = verify(draft(body="About 122 mm is forecast."), FACTS)

        assert problems == ["The number 122 is not in the evidence."]

    def test_one_per_cent_tolerance_applies_to_large_values(self) -> None:
        facts = Facts(
            "heavy_rain",
            "severe",
            FACTS.onset,
            FACTS.expires,
            [{"date": "2026-10-09", "value": 1000.0, "threshold": 100.0}],
        )

        assert verify(draft(body="About 1,008 mm is forecast."), facts) == []
        assert verify(draft(body="About 1,020 mm is forecast."), facts) != []

    def test_a_count_of_days_is_accepted(self) -> None:
        assert verify(draft(body="Heavy rain is expected on 2 days."), FACTS) == []

    def test_a_date_outside_the_window_is_rejected(self) -> None:
        problems = verify(draft(body="Rain peaks at 120 mm on 14 October."), FACTS)

        assert problems == [
            'The date "14 October" is outside the alert window and the evidence.'
        ]

    @pytest.mark.parametrize(
        "written", ["9 October", "9th October", "October 9", "2026-10-09"]
    )
    def test_dates_are_recognised_however_they_are_written(self, written: str) -> None:
        assert verify(draft(body=f"Rain peaks at 120 mm on {written}."), FACTS) == []

    def test_a_date_in_another_year_is_rejected(self) -> None:
        problems = verify(draft(body="Rain peaks on 9 October 2025."), FACTS)

        assert len(problems) == 1
        assert "9 October 2025" in problems[0]

    def test_an_impossible_date_is_rejected(self) -> None:
        problems = verify(draft(body="Rain peaks on 31 September."), FACTS)

        assert problems == ['"31 September" is not a real date.']

    def test_a_pollutant_name_is_not_a_number(self) -> None:
        facts = Facts(
            "poor_air_quality",
            "severe",
            FACTS.onset,
            FACTS.expires,
            [{"date": "2026-10-09", "value": 180.0, "threshold": 150.0}],
        )
        text = draft(
            headline="Severe poor air quality alert for Lahore",
            body="Daily mean PM2.5 is forecast to reach 180 μg/m³ on 9 October.",
            instructions="Reduce time outdoors and wear a well-fitting mask.",
        )

        assert verify(text, facts) == []

    def test_every_problem_is_reported_at_once(self) -> None:
        problems = verify(
            draft(body="Up to 300 mm on 14 October, with extreme winds."), FACTS
        )

        assert len(problems) == 4


class TestConsistency:
    """Test cases for the text keeping to the assessed hazard and severity"""

    def test_another_hazard_is_rejected(self) -> None:
        problems = verify(
            draft(instructions="Stay indoors; strong winds are also likely."), FACTS
        )

        assert problems == [
            'The text mentions "winds", a hazard that was not assessed.'
        ]

    def test_a_word_inside_another_word_is_not_a_hazard(self) -> None:
        # "snowfall" must not be found in "rainfall", nor "wind" in "window"
        assert verify(draft(instructions="Keep every window closed."), FACTS) == []

    def test_a_different_severity_is_rejected(self) -> None:
        problems = verify(draft(headline="Extreme heavy rain alert for Lahore"), FACTS)

        assert problems == [
            'The text says "extreme", but the assessed severity is severe.'
        ]

    def test_a_consequence_of_the_hazard_is_allowed(self) -> None:
        text = draft(instructions="Expect urban flooding and travel disruption.")

        assert verify(text, FACTS) == []


class TestRuleBasedText:
    """Test cases for the baseline wording meeting the same bar"""

    def test_template_wording_passes_verification(self) -> None:
        signal = Signal(
            hazard="heavy_rain",
            level="severe",
            onset=dt.date(2026, 10, 9),
            expires=dt.date(2026, 10, 10),
            metric="precipitation_mm",
            unit="mm",
            peak_value=120.3,
            peak_date=dt.date(2026, 10, 9),
            threshold=100.0,
            days_over=[dt.date(2026, 10, 9), dt.date(2026, 10, 10)],
        )
        text = write_alert_text(signal, "Lahore")

        assert verify(AlertDraft(**vars(text)), FACTS) == []
