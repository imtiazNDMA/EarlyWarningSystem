"""Check an alert draft against the facts it was written from.

Pure logic with no I/O. There is no human approval step, so these checks are the
only gate between a model's wording and publication.
"""

import datetime as dt
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from ews.screening.rules import LEVELS, Level

# A stated number matches an evidence value within half a unit or one per cent,
# whichever is larger, so "120 mm" is accepted for 120.3
ABSOLUTE_TOLERANCE = 0.5
RELATIVE_TOLERANCE = 0.01

# Words that name each hazard. A draft may use its own hazard's words only
HAZARD_TERMS: dict[str, tuple[str, ...]] = {
    "heavy_rain": ("rain", "rains", "rainfall", "downpour", "downpours"),
    "heatwave": ("heatwave", "heatwaves", "heat wave", "heat waves"),
    "strong_wind": ("wind", "winds", "gust", "gusts", "gale", "gales"),
    "heavy_snow": ("snow", "snowfall", "blizzard"),
    "poor_air_quality": ("air quality", "smog", "pollution", "haze"),
    "riverine_flood": ("river flood", "river flooding", "riverine flood"),
    "earthquake": ("earthquake", "earthquakes", "tremor", "tremors", "aftershock"),
}

MONTHS = (
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
)
_MONTH = "|".join(MONTHS)
_DAY_MONTH = re.compile(
    rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH})\b(?:,?\s+(\d{{4}}))?", re.IGNORECASE
)
_MONTH_DAY = re.compile(
    rf"\b({_MONTH})\s+(\d{{1,2}})(?:st|nd|rd|th)?\b(?:,?\s+(\d{{4}}))?", re.IGNORECASE
)
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
# Names that contain digits but state no quantity
_NAMED_QUANTITIES = re.compile(r"\bPM\s?(?:2\.5|10)\b", re.IGNORECASE)
_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")


class AlertDraft(BaseModel):
    """The wording of an alert as the drafter must return it."""

    headline: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=700)
    instructions: str = Field(min_length=1, max_length=500)


@dataclass(frozen=True)
class Facts:
    """What a draft is allowed to say: the assessment and the evidence behind it."""

    hazard: str
    severity: Level
    onset: dt.date
    expires: dt.date
    # Evidence rows as stored on an alert: date, value and threshold among them
    evidence: Sequence[Mapping[str, Any]]


def verify(draft: AlertDraft, facts: Facts) -> list[str]:
    """Return what is wrong with a draft; an empty list means it may be published.

    Checks that every date and number in the text is in the evidence, and that
    the text names no other hazard and no other severity than the assessment's.
    Each problem is worded so it can be handed back to the drafter.
    """
    text = " ".join((draft.headline, draft.body, draft.instructions))
    remaining, date_problems = _check_dates(text, facts)
    return [
        *date_problems,
        *_check_numbers(remaining, facts),
        *_check_hazards(text, facts),
        *_check_severity(text, facts),
    ]


def _evidence_dates(facts: Facts) -> set[dt.date]:
    dates = {dt.date.fromisoformat(str(row["date"])) for row in facts.evidence}
    day = facts.onset
    while day <= facts.expires:
        dates.add(day)
        day += dt.timedelta(days=1)
    return dates


def _check_dates(text: str, facts: Facts) -> tuple[str, list[str]]:
    """Check every date; return the text with the dates removed, and the problems."""
    allowed = _evidence_dates(facts)
    problems: list[str] = []

    def check(written: str, year: str | None, month: int, day: int) -> None:
        try:
            # A date written without a year is read as the alert's own year
            date = dt.date(int(year) if year else facts.onset.year, month, day)
        except ValueError:
            problems.append(f'"{written}" is not a real date.')
            return
        if date not in allowed:
            problems.append(
                f'The date "{written}" is outside the alert window and the evidence.'
            )

    def day_month(match: re.Match[str]) -> str:
        day, month, year = match.groups()
        check(match.group(0), year, MONTHS.index(month.lower()) + 1, int(day))
        return " "

    def month_day(match: re.Match[str]) -> str:
        month, day, year = match.groups()
        check(match.group(0), year, MONTHS.index(month.lower()) + 1, int(day))
        return " "

    def iso(match: re.Match[str]) -> str:
        year, month, day = match.groups()
        check(match.group(0), year, int(month), int(day))
        return " "

    text = _ISO_DATE.sub(iso, text)
    text = _DAY_MONTH.sub(day_month, text)
    text = _MONTH_DAY.sub(month_day, text)
    return text, problems


def _check_numbers(text: str, facts: Facts) -> list[str]:
    """Every number must be an evidence value, a threshold or a count of days."""
    values = [
        float(row[field])
        for row in facts.evidence
        for field in ("value", "threshold")
        if row.get(field) is not None
    ]
    day_counts = {
        len({row["date"] for row in facts.evidence}),
        (facts.expires - facts.onset).days + 1,
    }
    problems = []
    for written in _NUMBER.findall(_NAMED_QUANTITIES.sub(" ", text)):
        number = float(written.replace(",", ""))
        grounded = any(
            abs(number - value)
            <= max(ABSOLUTE_TOLERANCE, RELATIVE_TOLERANCE * abs(value))
            for value in values
        )
        if not grounded and number not in day_counts:
            problems.append(f"The number {written} is not in the evidence.")
    return problems


def _mentions(text: str, terms: Sequence[str]) -> str | None:
    """The first of the terms the text uses as a whole word, if any."""
    for term in terms:
        if re.search(rf"\b{re.escape(term)}\b", text, re.IGNORECASE):
            return term
    return None


def _check_hazards(text: str, facts: Facts) -> list[str]:
    """The text must not name a hazard other than the one assessed."""
    problems = []
    for hazard, terms in HAZARD_TERMS.items():
        if hazard == facts.hazard:
            continue
        term = _mentions(text, terms)
        if term:
            problems.append(
                f'The text mentions "{term}", a hazard that was not assessed.'
            )
    return problems


def _check_severity(text: str, facts: Facts) -> list[str]:
    """The text must not use another severity level's word."""
    others = [level for level in LEVELS if level != facts.severity]
    term = _mentions(text, others)
    if term is None:
        return []
    return [f'The text says "{term}", but the assessed severity is {facts.severity}.']
