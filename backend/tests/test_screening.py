"""Tests for hazard screening rules and the packaged thresholds."""

from datetime import date
from typing import Any

import pytest
from pydantic import ValidationError

from ews.screening.rules import HazardRule, screen
from ews.screening.thresholds import load_rules, parse_rules
from ews.sources.open_meteo import DailyForecast

RAIN = HazardRule(
    hazard="heavy_rain",
    metric="precipitation_mm",
    unit="mm",
    levels={"moderate": 50, "severe": 100, "extreme": 150},
)
HEAT = HazardRule(
    hazard="heatwave",
    metric="temperature_max_c",
    unit="°C",
    levels={"moderate": 42, "severe": 45, "extreme": 48},
    province_levels={"gilgit baltistan": {"moderate": 35, "severe": 38, "extreme": 41}},
)


def day(day_of_month: int, **values: float | None) -> DailyForecast:
    """A calm October day, with the given values replaced."""
    calm: dict[str, Any] = {
        "temperature_max_c": 30.0,
        "temperature_min_c": 20.0,
        "precipitation_mm": 0.0,
        "precipitation_probability_pct": 0.0,
        "wind_speed_max_kmh": 10.0,
        "wind_gusts_max_kmh": 20.0,
        "weather_code": 0,
        "snowfall_cm": 0.0,
        "uv_index_max": 5.0,
    }
    return DailyForecast(date=date(2026, 10, day_of_month), **{**calm, **values})


class TestScreen:
    """Test cases for screen"""

    def test_calm_forecast_raises_no_signal(self) -> None:
        assert screen([day(8), day(9)], "Punjab", [RAIN, HEAT]) == []

    @pytest.mark.parametrize(
        ("rainfall", "level"),
        [
            (49.9, None),
            (50.0, "moderate"),
            (99.9, "moderate"),
            (100.0, "severe"),
            (149.9, "severe"),
            (150.0, "extreme"),
            (400.0, "extreme"),
        ],
    )
    def test_level_is_reached_at_the_threshold_itself(
        self, rainfall: float, level: str | None
    ) -> None:
        signals = screen([day(8, precipitation_mm=rainfall)], "Punjab", [RAIN])

        assert [signal.level for signal in signals] == ([level] if level else [])

    def test_signal_reports_what_triggered_it(self) -> None:
        days = [
            day(8),
            day(9, precipitation_mm=60.0),
            day(10, precipitation_mm=120.0),
            day(11, precipitation_mm=20.0),
        ]

        (signal,) = screen(days, "Punjab", [RAIN])

        assert signal.hazard == "heavy_rain"
        assert signal.level == "severe"
        assert signal.metric == "precipitation_mm"
        assert signal.unit == "mm"
        assert signal.peak_value == 120.0
        assert signal.peak_date == date(2026, 10, 10)
        assert signal.threshold == 100
        assert signal.days_over == [date(2026, 10, 9), date(2026, 10, 10)]

    def test_window_spans_first_to_last_day_over_the_lowest_threshold(self) -> None:
        days = [
            day(8, precipitation_mm=55.0),
            day(9),
            day(10, precipitation_mm=70.0),
            day(11),
        ]

        (signal,) = screen(days, "Punjab", [RAIN])

        assert signal.onset == date(2026, 10, 8)
        assert signal.expires == date(2026, 10, 10)

    def test_each_hazard_is_screened_separately(self) -> None:
        days = [day(8, precipitation_mm=160.0, temperature_max_c=46.0)]

        signals = screen(days, "Punjab", [RAIN, HEAT])

        assert {(s.hazard, s.level) for s in signals} == {
            ("heavy_rain", "extreme"),
            ("heatwave", "severe"),
        }

    def test_missing_values_are_ignored(self) -> None:
        days = [day(8, precipitation_mm=None), day(9, precipitation_mm=None)]

        assert screen(days, "Punjab", [RAIN]) == []

    def test_province_thresholds_replace_the_national_ones(self) -> None:
        days = [day(8, temperature_max_c=39.0)]

        assert screen(days, "Punjab", [HEAT]) == []
        (signal,) = screen(days, "Gilgit Baltistan", [HEAT])
        assert signal.level == "severe"
        assert signal.threshold == 38


class TestThresholdConfiguration:
    """Test cases for the threshold configuration file"""

    def test_packaged_file_defines_the_four_weather_hazards(self) -> None:
        rules = {rule.hazard: rule for rule in load_rules()}

        assert set(rules) == {"heavy_rain", "heatwave", "strong_wind", "heavy_snow"}
        assert rules["heavy_rain"].levels == {
            "moderate": 50,
            "severe": 100,
            "extreme": 150,
        }

    def test_levels_must_increase(self) -> None:
        config = {
            "hazards": {
                "heavy_rain": {
                    "metric": "precipitation_mm",
                    "unit": "mm",
                    "levels": {"moderate": 100, "severe": 50, "extreme": 150},
                }
            }
        }

        with pytest.raises(ValidationError, match="increase"):
            parse_rules(config)

    def test_metric_must_be_a_forecast_value(self) -> None:
        config = {
            "hazards": {
                "locusts": {
                    "metric": "swarm_density",
                    "unit": "per km²",
                    "levels": {"moderate": 1, "severe": 2, "extreme": 3},
                }
            }
        }

        with pytest.raises(ValidationError, match="swarm_density"):
            parse_rules(config)
