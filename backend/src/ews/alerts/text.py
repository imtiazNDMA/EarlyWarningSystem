"""Rule-based alert text, written from a signal by template.

Pure logic with no I/O. This is the baseline wording that model-written alerts
will later replace and be compared against.
"""

import datetime as dt
from dataclasses import dataclass

from ews.screening.rules import Signal

HAZARD_NAMES = {
    "heavy_rain": "heavy rain",
    "heatwave": "heatwave",
    "strong_wind": "strong wind",
    "heavy_snow": "heavy snow",
}

METRIC_NAMES = {
    "precipitation_mm": "rainfall",
    "temperature_max_c": "maximum temperature",
    "wind_gusts_max_kmh": "wind gusts",
    "snowfall_cm": "snowfall",
}

INSTRUCTIONS = {
    "heavy_rain": (
        "Avoid low-lying areas and stream crossings. Expect possible urban "
        "flooding and travel disruption."
    ),
    "heatwave": (
        "Limit outdoor activity in the afternoon, drink water regularly, and "
        "check on older people and children."
    ),
    "strong_wind": (
        "Secure loose objects and stay clear of weak structures, trees and power lines."
    ),
    "heavy_snow": (
        "Avoid unnecessary travel on mountain roads and prepare for road closures."
    ),
}
DEFAULT_INSTRUCTIONS = "Follow advice from local authorities."


@dataclass(frozen=True)
class AlertText:
    """The wording of an alert."""

    headline: str
    body: str
    instructions: str


def _day(date: dt.date) -> str:
    """A date as people say it: 9 October."""
    return f"{date.day} {date:%B}"


def write_alert_text(signal: Signal, district_name: str) -> AlertText:
    """Write an alert's wording from the signal that triggered it.

    Every number in the text comes straight from the signal.

    Args:
        signal: The hazard signal
        district_name: The district's display name
    """
    hazard = HAZARD_NAMES.get(signal.hazard, signal.hazard.replace("_", " "))
    metric = METRIC_NAMES.get(signal.metric, signal.metric)
    days = len(signal.days_over)
    if days == 1:
        period = f"on {_day(signal.onset)}"
    else:
        period = f"on {days} days, from {_day(signal.onset)} to {_day(signal.expires)}"

    return AlertText(
        headline=f"{signal.level.capitalize()} {hazard} alert for {district_name}",
        body=(
            f"Forecast {metric} peaks at {signal.peak_value:g} {signal.unit} on "
            f"{_day(signal.peak_date)}, at or above the {signal.level} threshold of "
            f"{signal.threshold:g} {signal.unit}. "
            f"The lowest alert threshold is met {period}."
        ),
        instructions=INSTRUCTIONS.get(signal.hazard, DEFAULT_INSTRUCTIONS),
    )
