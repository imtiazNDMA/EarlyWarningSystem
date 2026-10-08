"""Decide what should happen to a district's alert for one hazard.

Pure logic with no I/O. Alerts are records: an alert is never edited when
conditions change, it is ended and, where needed, replaced by a new one.
"""

import datetime as dt
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from ews.screening.rules import Signal

Urgency = Literal["immediate", "expected", "future"]
Certainty = Literal["likely", "possible"]

# A hazard starting within this many days is "expected" and "likely"; further
# out it is "future" and "possible". A rule of thumb until an analyst judges it.
NEAR_TERM_DAYS = 2


class Action(StrEnum):
    """What to do with the alert for one district and hazard."""

    NONE = "none"
    ISSUE = "issue"
    KEEP = "keep"
    SUPERSEDE = "supersede"
    CANCEL = "cancel"
    EXPIRE = "expire"


@dataclass(frozen=True)
class ActiveAlert:
    """The parts of an active alert that the decision depends on."""

    severity: str
    onset: dt.date
    expires: dt.date


def decide(active: ActiveAlert | None, signal: Signal | None, today: dt.date) -> Action:
    """Compare the active alert, if any, with the latest signal, if any.

    Args:
        active: The active alert for this district and hazard
        signal: The signal from the latest screening for the same hazard
        today: First day of the forecast the signal was screened from

    Returns:
        ISSUE for a new signal; KEEP when the alert still describes the signal;
        SUPERSEDE when severity or the time window changed; CANCEL when the
        signal ended while the alert's window was still open; EXPIRE when the
        window has passed; NONE when there is neither alert nor signal
    """
    if active is None:
        return Action.ISSUE if signal is not None else Action.NONE

    if signal is None:
        return Action.EXPIRE if active.expires < today else Action.CANCEL

    # Forecast days that have passed drop off the front of the window; that
    # alone is not a change worth a new alert.
    onset_now = max(active.onset, today)
    unchanged = (
        signal.level == active.severity
        and signal.expires == active.expires
        and signal.onset == onset_now
    )
    return Action.KEEP if unchanged else Action.SUPERSEDE


def urgency(onset: dt.date, today: dt.date) -> Urgency:
    """How soon the hazard starts, in Common Alerting Protocol terms."""
    lead = (onset - today).days
    if lead <= 0:
        return "immediate"
    return "expected" if lead <= NEAR_TERM_DAYS else "future"


def certainty(onset: dt.date, today: dt.date) -> Certainty:
    """How sure a forecast-based alert is, judged by lead time alone."""
    return "likely" if (onset - today).days <= NEAR_TERM_DAYS else "possible"
