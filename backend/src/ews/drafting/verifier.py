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

from ews.alerts.text import AlertText
from ews.drafting.glossary import (
    HAZARD_TERMS_UR,
    LATIN_UNITS,
    SEVERITY_TERMS_UR,
    TRANSLITERATIONS,
    URDU_MONTHS,
)
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
# Urdu and Arabic digits, which Urdu text may use for the same numbers
_EASTERN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "0123456789" * 2)
_LATIN_WORD = re.compile(r"[A-Za-z]+")


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


def verify_urdu(urdu: AlertDraft, english: AlertText, facts: Facts) -> list[str]:
    """Return what is wrong with an alert's Urdu; an empty list means it may be used.

    The English has already been verified against the evidence, so the Urdu is
    checked against the English: it must state the same dates and numbers, and
    name the same hazard and severity in the glossary's terms.
    Each problem is worded so it can be handed back to the Urdu writer.
    """
    return [
        *glossary_problems(urdu),
        *equivalence_problems(urdu, english, facts),
    ]


def glossary_problems(urdu: AlertDraft) -> list[str]:
    """Where the Urdu departs from the glossary's script and vocabulary."""
    text = _joined(urdu)
    problems = [
        f'The Urdu transliterates an English weather word, "{written}"; use "{term}".'
        for written, term in TRANSLITERATIONS.items()
        if _mentions(text, [written])
    ]
    latin = dict.fromkeys(
        word for word in _LATIN_WORD.findall(text) if word.lower() not in LATIN_UNITS
    )
    problems += [
        f'The Urdu has the word "{word}" in Latin letters; write it in Urdu script.'
        for word in latin
    ]
    return problems


def equivalence_problems(
    urdu: AlertDraft, english: AlertText, facts: Facts
) -> list[str]:
    """Where the Urdu and the English make different claims."""
    text = _joined(urdu)
    return [
        *_check_equivalence(text, _joined(english)),
        *_check_urdu_hazards(text, facts),
        *_check_urdu_severity(text, _joined(english), facts),
    ]


def _joined(text: AlertDraft | AlertText) -> str:
    return " ".join((text.headline, text.body, text.instructions))


def _check_urdu_hazards(text: str, facts: Facts) -> list[str]:
    """The Urdu must name the assessed hazard, in a glossary term, and no other."""
    problems = []
    own = HAZARD_TERMS_UR.get(facts.hazard)
    if own and not _mentions(text, own):
        problems.append(
            f'The Urdu does not name the hazard; use the glossary term "{own[0]}".'
        )
    for hazard, terms in HAZARD_TERMS_UR.items():
        term = _mentions(text, terms) if hazard != facts.hazard else None
        if term:
            problems.append(
                f'The Urdu says "{term}", which names a hazard that was not assessed.'
            )
    return problems


def _check_urdu_severity(text: str, english: str, facts: Facts) -> list[str]:
    """The Urdu must state the severity if the English does, and no other."""
    own = SEVERITY_TERMS_UR[facts.severity]
    stated: list[Level] = []
    # Highest first: the word for extreme contains the word for severe
    for level in reversed(LEVELS):
        term = SEVERITY_TERMS_UR[level]
        if _mentions(text, [term]):
            stated.append(level)
            text = text.replace(term, " ")
    others = [
        f'The Urdu says "{SEVERITY_TERMS_UR[level]}", but the assessed severity is '
        f'{facts.severity}; use "{own}".'
        for level in stated
        if level != facts.severity
    ]
    if others or facts.severity in stated:
        return others
    if _mentions(english, [facts.severity]):
        return [f'The Urdu does not state the severity; use "{own}".']
    return []


def _in_english_notation(text: str) -> str:
    """Urdu text with its digits and month names written as English writes them."""
    text = text.translate(_EASTERN_DIGITS)
    for urdu_month, month in zip(URDU_MONTHS, MONTHS, strict=True):
        text = re.sub(rf"\b{urdu_month}\b", month, text)
    return text


def _claims(text: str) -> tuple[set[tuple[int, int]], set[float]]:
    """The dates, as month and day, and the other numbers a text states."""
    dates: set[tuple[int, int]] = set()

    def day_month(match: re.Match[str]) -> str:
        day, month, _year = match.groups()
        dates.add((MONTHS.index(month.lower()) + 1, int(day)))
        return " "

    def month_day(match: re.Match[str]) -> str:
        month, day, _year = match.groups()
        dates.add((MONTHS.index(month.lower()) + 1, int(day)))
        return " "

    def iso(match: re.Match[str]) -> str:
        _year, month, day = match.groups()
        dates.add((int(month), int(day)))
        return " "

    text = _ISO_DATE.sub(iso, text)
    text = _DAY_MONTH.sub(day_month, text)
    text = _MONTH_DAY.sub(month_day, text)
    numbers = {
        float(written.replace(",", ""))
        for written in _NUMBER.findall(_NAMED_QUANTITIES.sub(" ", text))
    }
    return dates, numbers


def _check_equivalence(urdu: str, english: str) -> list[str]:
    """The Urdu must state the dates and numbers the English states, and no others."""
    urdu_dates, urdu_numbers = _claims(_in_english_notation(urdu))
    dates, numbers = _claims(english)

    def day(date: tuple[int, int]) -> str:
        return f"{date[1]} {MONTHS[date[0] - 1].capitalize()}"

    return [
        *(
            f'The Urdu gives the date "{day(date)}", which the English does not.'
            for date in sorted(urdu_dates - dates)
        ),
        *(
            f'The Urdu leaves out the date "{day(date)}" given in the English.'
            for date in sorted(dates - urdu_dates)
        ),
        *(
            f"The Urdu gives the number {number:g}, which the English does not."
            for number in sorted(urdu_numbers - numbers)
        ),
        *(
            f"The Urdu leaves out the number {number:g} given in the English."
            for number in sorted(numbers - urdu_numbers)
        ),
    ]


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
