"""Deterministic hazard screening: forecast values against thresholds.

Pure logic with no I/O. This is the first stage of a monitoring cycle and decides
which districts need attention.
"""

import datetime as dt
from collections.abc import Sequence
from typing import Any, Literal, Protocol, Self, get_args

from pydantic import BaseModel, model_validator

from ews.sources.open_meteo import DailyForecast
from ews.sources.open_meteo_air_quality import DailyAirQuality

Level = Literal["moderate", "severe", "extreme"]
LEVELS: tuple[Level, ...] = get_args(Level)  # lowest first

Thresholds = dict[Level, float]
SUPPORTED_METRICS = set(DailyForecast.model_fields) | set(DailyAirQuality.model_fields)


class DailyValue(Protocol):
    """A dated daily source record whose metric is selected by a rule."""

    date: dt.date

    def __getattribute__(self, name: str) -> Any: ...


def _check_levels(levels: Thresholds, where: str) -> None:
    """Every level must be present and each must be higher than the one before."""
    missing = [level for level in LEVELS if level not in levels]
    if missing:
        raise ValueError(f"{where} is missing levels: {', '.join(missing)}")
    values = [levels[level] for level in LEVELS]
    if values != sorted(set(values)):
        raise ValueError(f"{where} thresholds must increase from moderate to extreme")


class HazardRule(BaseModel):
    """Thresholds for one hazard on one forecast value."""

    hazard: str
    # Field of DailyForecast the thresholds apply to
    metric: str
    unit: str
    levels: Thresholds
    # Lower-cased province name -> thresholds used there instead
    province_levels: dict[str, Thresholds] = {}

    @model_validator(mode="after")
    def _validate(self) -> Self:
        if self.metric not in SUPPORTED_METRICS:
            raise ValueError(f"{self.hazard}: {self.metric} is not a forecast value")
        _check_levels(self.levels, self.hazard)
        for province, levels in self.province_levels.items():
            _check_levels(levels, f"{self.hazard} in {province}")
        return self

    def levels_for(self, province: str) -> Thresholds:
        """The thresholds that apply in a province."""
        return self.province_levels.get(province.lower(), self.levels)


class Signal(BaseModel):
    """A hazard threshold reached somewhere in a district's forecast."""

    hazard: str
    level: Level
    # First and last forecast day at or above the lowest threshold
    onset: dt.date
    expires: dt.date
    metric: str
    unit: str
    peak_value: float
    peak_date: dt.date
    # Threshold of the level that was reached
    threshold: float
    days_over: list[dt.date]


def screen(
    days: Sequence[DailyValue], province: str, rules: Sequence[HazardRule]
) -> list[Signal]:
    """Screen one district's forecast against every rule.

    A level is reached when a value is at or above its threshold. Each hazard
    yields at most one signal, at the highest level reached on any day.

    Args:
        days: The district's daily forecast
        province: The district's province, for province-specific thresholds
        rules: Hazard rules to apply

    Returns:
        One signal per hazard that reached at least the lowest level
    """
    signals = []
    for rule in rules:
        levels = rule.levels_for(province)
        over = [
            (day.date, value)
            for day in days
            if (value := getattr(day, rule.metric)) is not None
            and value >= levels["moderate"]
        ]
        if not over:
            continue

        peak_date, peak_value = max(over, key=lambda item: item[1])
        level = next(lv for lv in reversed(LEVELS) if peak_value >= levels[lv])
        dates = [date for date, _ in over]
        signals.append(
            Signal(
                hazard=rule.hazard,
                level=level,
                onset=min(dates),
                expires=max(dates),
                metric=rule.metric,
                unit=rule.unit,
                peak_value=peak_value,
                peak_date=peak_date,
                threshold=levels[level],
                days_over=dates,
            )
        )
    return signals
