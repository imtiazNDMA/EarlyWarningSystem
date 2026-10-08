"""Tests for alert lifecycle decisions and rule-based alert text."""

from datetime import date

import pytest

from ews.alerts.lifecycle import Action, ActiveAlert, certainty, decide, urgency
from ews.alerts.text import write_alert_text
from ews.screening.rules import Level, Signal

TODAY = date(2026, 10, 8)


def signal(
    level: Level = "severe",
    onset: date = date(2026, 10, 9),
    expires: date = date(2026, 10, 10),
) -> Signal:
    return Signal(
        hazard="heavy_rain",
        level=level,
        onset=onset,
        expires=expires,
        metric="precipitation_mm",
        unit="mm",
        peak_value=120.0,
        peak_date=date(2026, 10, 9),
        threshold=100.0,
        days_over=[date(2026, 10, 9), date(2026, 10, 10)],
    )


def active(
    severity: str = "severe",
    onset: date = date(2026, 10, 9),
    expires: date = date(2026, 10, 10),
) -> ActiveAlert:
    return ActiveAlert(severity=severity, onset=onset, expires=expires)


class TestDecide:
    """Test cases for decide"""

    def test_nothing_to_do_without_an_alert_or_a_signal(self) -> None:
        assert decide(None, None, TODAY) is Action.NONE

    def test_issues_when_a_signal_has_no_active_alert(self) -> None:
        assert decide(None, signal(), TODAY) is Action.ISSUE

    def test_keeps_an_alert_the_signal_still_matches(self) -> None:
        assert decide(active(), signal(), TODAY) is Action.KEEP

    def test_supersedes_when_severity_changes(self) -> None:
        assert decide(active(), signal(level="extreme"), TODAY) is Action.SUPERSEDE
        assert decide(active(), signal(level="moderate"), TODAY) is Action.SUPERSEDE

    def test_supersedes_when_the_window_ends_on_a_different_day(self) -> None:
        later = signal(expires=date(2026, 10, 12))

        assert decide(active(), later, TODAY) is Action.SUPERSEDE

    def test_supersedes_when_onset_moves(self) -> None:
        earlier = signal(onset=date(2026, 10, 8))

        assert decide(active(), earlier, TODAY) is Action.SUPERSEDE

    def test_keeps_when_onset_only_moved_because_past_days_dropped_off(self) -> None:
        """An alert for 9-10 Oct, screened again on the 10th, starts on the 10th."""
        today = date(2026, 10, 10)
        remaining = signal(onset=today, expires=date(2026, 10, 10))

        assert decide(active(), remaining, today) is Action.KEEP

    def test_cancels_when_the_signal_ends_before_the_window_has_passed(self) -> None:
        assert decide(active(), None, TODAY) is Action.CANCEL
        assert decide(active(), None, date(2026, 10, 10)) is Action.CANCEL

    def test_expires_once_the_window_has_passed(self) -> None:
        assert decide(active(), None, date(2026, 10, 11)) is Action.EXPIRE


class TestUrgencyAndCertainty:
    """Test cases for urgency and certainty"""

    @pytest.mark.parametrize(
        ("onset", "expected_urgency", "expected_certainty"),
        [
            (date(2026, 10, 7), "immediate", "likely"),  # already under way
            (date(2026, 10, 8), "immediate", "likely"),
            (date(2026, 10, 9), "expected", "likely"),
            (date(2026, 10, 10), "expected", "likely"),
            (date(2026, 10, 11), "future", "possible"),
            (date(2026, 10, 14), "future", "possible"),
        ],
    )
    def test_follow_the_lead_time(
        self, onset: date, expected_urgency: str, expected_certainty: str
    ) -> None:
        assert urgency(onset, TODAY) == expected_urgency
        assert certainty(onset, TODAY) == expected_certainty


class TestWriteAlertText:
    """Test cases for write_alert_text"""

    def test_states_the_peak_the_threshold_and_the_period(self) -> None:
        text = write_alert_text(signal(), "Lahore")

        assert text.headline == "Severe heavy rain alert for Lahore"
        assert text.body == (
            "Forecast rainfall peaks at 120 mm on 9 October, at or above the severe "
            "threshold of 100 mm. The lowest alert threshold is met on 2 days, "
            "from 9 October to 10 October."
        )
        assert text.instructions.startswith("Avoid low-lying areas")

    def test_single_day_reads_naturally(self) -> None:
        one_day = signal(onset=date(2026, 10, 9), expires=date(2026, 10, 9))
        one_day = one_day.model_copy(update={"days_over": [date(2026, 10, 9)]})

        text = write_alert_text(one_day, "Lahore")

        assert text.body.endswith("The lowest alert threshold is met on 9 October.")

    def test_unknown_hazard_still_gets_readable_text(self) -> None:
        dust = signal().model_copy(update={"hazard": "dust_storm", "metric": "aod"})

        text = write_alert_text(dust, "Quetta")

        assert text.headline == "Severe dust storm alert for Quetta"
        assert "Forecast aod peaks at" in text.body
        assert text.instructions == "Follow advice from local authorities."
