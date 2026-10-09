"""The analyst's judgement of a screening signal, and what it does to the signal.

Pure logic with no I/O.
"""

import datetime as dt
from typing import Literal, Self

from pydantic import BaseModel, Field, model_validator

from ews.alerts.lifecycle import Certainty, Urgency
from ews.screening.rules import LEVELS, Level, Signal

Decision = Literal["confirm", "upgrade", "downgrade", "dismiss"]


class HazardAssessment(BaseModel):
    """What the analyst concluded about one district's signal for one hazard."""

    # False dismisses the signal: the evidence does not support a warning
    supported: bool
    severity: Level
    urgency: Urgency
    certainty: Certainty
    # First and last day the hazard is expected
    onset: dt.date
    expires: dt.date
    # Why, in two or three sentences
    reasoning: str = Field(min_length=1, max_length=1200)
    # The values or tool results the judgement rests on
    evidence: list[str] = Field(max_length=8)

    @model_validator(mode="after")
    def window_is_ordered(self) -> Self:
        if self.onset > self.expires:
            raise ValueError("onset must not be after expires")
        return self


def decision_of(signal: Signal, assessment: HazardAssessment) -> Decision:
    """How an assessment compares with the signal that screening raised."""
    if not assessment.supported:
        return "dismiss"
    change = LEVELS.index(assessment.severity) - LEVELS.index(signal.level)
    if change == 0:
        return "confirm"
    return "upgrade" if change > 0 else "downgrade"


def upgrade_problem(signal: Signal, assessment: HazardAssessment) -> str | None:
    """Why an assessment may not raise the severity, if it does.

    Screening already gives a signal the highest level its values reach, so a
    higher one cannot rest on those values. With a real model, allowing it for
    compound events turned pairs of marginal signals into severe alerts, so the
    thresholds are a ceiling: the analyst may lower a severity but not raise it.
    """
    if decision_of(signal, assessment) != "upgrade":
        return None
    return (
        "severity may not be raised above the screening level, which is already "
        f"the highest the forecast values reach. Submit {signal.level} or lower."
    )


def assessed_signal(signal: Signal, assessment: HazardAssessment) -> Signal | None:
    """The signal as the analyst judged it, or None when it was dismissed.

    Severity and the time window follow the assessment. The measured values
    stay as screening found them, since they are what the alert cites.
    """
    if not assessment.supported:
        return None
    return signal.model_copy(
        update={
            "level": assessment.severity,
            "onset": assessment.onset,
            "expires": assessment.expires,
        }
    )
