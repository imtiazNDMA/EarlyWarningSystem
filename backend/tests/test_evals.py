"""Behavior tests for replaying frozen scenarios through the rules baseline."""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from ews.evals.runner import BACKEND_ROOT, DEFAULT_SCENARIOS, evaluate


def test_evaluate_reports_detection_and_severity_metrics(tmp_path: Path) -> None:
    scenarios = tmp_path / "scenarios.yaml"
    scenarios.write_text(
        """
version: test-v1
scenarios:
  - id: detected-with-wrong-severity
    districts:
      - id: lahore
        province: Punjab
        source_payloads:
          open-meteo-forecast:
            daily:
              time: [2026-10-08]
              temperature_2m_max: [30]
              temperature_2m_min: [20]
              precipitation_sum: [100]
              precipitation_probability_max: [80]
              wind_speed_10m_max: [10]
              wind_gusts_10m_max: [20]
              weather_code: [61]
              snowfall_sum: [0]
              uv_index_max: [5]
        expected:
          - {hazard: heavy_rain, severity: extreme}
  - id: false-positive
    districts:
      - id: quetta
        province: Balochistan
        source_payloads:
          open-meteo-forecast:
            daily:
              time: [2026-10-08]
              temperature_2m_max: [30]
              temperature_2m_min: [20]
              precipitation_sum: [0]
              precipitation_probability_max: [0]
              wind_speed_10m_max: [10]
              wind_gusts_10m_max: [60]
              weather_code: [0]
              snowfall_sum: [0]
              uv_index_max: [5]
        expected: []
  - id: missed-hazard
    districts:
      - id: skardu
        province: Gilgit Baltistan
        source_payloads:
          open-meteo-forecast:
            daily:
              time: [2026-10-08]
              temperature_2m_max: [20]
              temperature_2m_min: [10]
              precipitation_sum: [0]
              precipitation_probability_max: [0]
              wind_speed_10m_max: [10]
              wind_gusts_10m_max: [20]
              weather_code: [0]
              snowfall_sum: [0]
              uv_index_max: [5]
        expected:
          - {hazard: heavy_snow, severity: moderate}
""",
        encoding="utf-8",
    )

    report = evaluate(scenarios)

    assert report.scenario_count == 3
    assert report.expected_hazards == 2
    assert report.predicted_hazards == 2
    assert report.true_positives == 1
    assert report.false_positives == 1
    assert report.false_negatives == 1
    assert report.hazard_precision == 0.5
    assert report.hazard_recall == 0.5
    assert report.severity_accuracy == 0.0
    assert report.texts_checked == 2
    assert report.groundedness == 1.0
    assert report.hold_rate == 0.0
    assert report.urdu_texts_checked == 0


RAIN_DAY = """
          open-meteo-forecast:
            daily:
              time: [2026-10-08]
              temperature_2m_max: [30]
              temperature_2m_min: [20]
              precipitation_sum: [100]
              precipitation_probability_max: [80]
              wind_speed_10m_max: [10]
              wind_gusts_10m_max: [20]
              weather_code: [61]
              snowfall_sum: [0]
              uv_index_max: [5]
"""


def test_evaluate_scores_recorded_urdu_against_the_rule_wording(
    tmp_path: Path,
) -> None:
    scenarios = tmp_path / "urdu.yaml"
    scenarios.write_text(
        f"""
version: urdu-v1
scenarios:
  - id: recorded-urdu
    districts:
      - id: lahore
        province: Punjab
        source_payloads: {RAIN_DAY}
        expected:
          - hazard: heavy_rain
            severity: severe
            urdu:
              headline: لاہور کے لیے شدید بارش کا انتباہ
              body: 8 اکتوبر کو بارش 100 ملی میٹر تک، جو 100 ملی میٹر کی شدید حد ہے۔
              instructions: نشیبی علاقوں سے دور رہیں۔
      - id: kasur
        province: Punjab
        source_payloads: {RAIN_DAY}
        expected:
          - hazard: heavy_rain
            severity: severe
            urdu:
              headline: Kasur کے لیے شدید بارش کا انتباہ
              body: 8 اکتوبر کو بارش 100 ملی میٹر تک، جو 100 ملی میٹر کی شدید حد ہے۔
              instructions: نشیبی علاقوں سے دور رہیں۔
      - id: multan
        province: Punjab
        source_payloads: {RAIN_DAY}
        expected:
          - hazard: heavy_rain
            severity: severe
            urdu:
              headline: ملتان کے لیے شدید رین کا انتباہ
              body: 8 اکتوبر کو 150 ملی میٹر تک، جو 100 ملی میٹر کی شدید حد ہے۔
              instructions: نشیبی علاقوں سے دور رہیں۔
""",
        encoding="utf-8",
    )

    report = evaluate(scenarios)

    assert report.severity_accuracy == 1.0
    assert report.urdu_texts_checked == 3
    assert report.urdu_glossary_compliance == pytest.approx(1 / 3)
    assert report.urdu_equivalence == pytest.approx(2 / 3)


def test_evaluate_rejects_duplicate_scenario_ids(tmp_path: Path) -> None:
    scenarios = tmp_path / "duplicates.yaml"
    scenarios.write_text(
        """
version: test-v1
scenarios:
  - {id: duplicate, districts: []}
  - {id: duplicate, districts: []}
""",
        encoding="utf-8",
    )

    with pytest.raises(ValidationError, match="scenario ids must be unique"):
        evaluate(scenarios)


def test_all_calm_metrics_are_undefined_instead_of_zero(tmp_path: Path) -> None:
    scenarios = tmp_path / "calm.yaml"
    scenarios.write_text(
        """
version: calm-v1
scenarios:
  - id: no-sources
    districts:
      - {id: lahore, province: Punjab, source_payloads: {}, expected: []}
""",
        encoding="utf-8",
    )

    report = evaluate(scenarios)

    assert report.hazard_precision is None
    assert report.hazard_recall is None
    assert report.severity_accuracy is None
    assert report.groundedness is None
    assert report.hold_rate is None
    assert report.urdu_glossary_compliance is None
    assert report.urdu_equivalence is None


@pytest.mark.eval
def test_recorded_rules_baseline() -> None:
    report = evaluate(DEFAULT_SCENARIOS)
    recorded = json.loads(
        (BACKEND_ROOT / "evals/reports/rules-baseline-v1.json").read_text(
            encoding="utf-8"
        )
    )

    assert report.scenario_count == 12
    assert report.expected_hazards == 10
    assert report.hazard_precision == 1.0
    assert report.hazard_recall == 1.0
    assert report.severity_accuracy == 1.0
    assert report.model_dump() == recorded
