"""Replay frozen source payloads through the deterministic screening baseline."""

import argparse
import hashlib
import json
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Self

import yaml
from pydantic import BaseModel, model_validator

from ews.alerts.service import Screened, evidence_for
from ews.alerts.text import write_alert_text
from ews.drafting.verifier import AlertDraft, Facts, verify
from ews.screening.rules import DailyValue, HazardRule, Level, Signal, screen
from ews.screening.thresholds import load_rules
from ews.sources.open_meteo import DailyForecast
from ews.sources.open_meteo import parse_daily as parse_forecast
from ews.sources.open_meteo_air_quality import (
    DailyAirQuality,
)
from ews.sources.open_meteo_air_quality import (
    parse_daily as parse_air_quality,
)

BACKEND_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SCENARIOS = BACKEND_ROOT / "evals/scenarios/rules_baseline.yaml"


class ExpectedOutcome(BaseModel):
    """Hazard and severity expected for one district."""

    hazard: str
    severity: Level


class DistrictScenario(BaseModel):
    """Frozen source payloads and expected outcomes for one district."""

    id: str
    province: str
    source_payloads: dict[str, dict[str, Any]]
    expected: list[ExpectedOutcome]


class Scenario(BaseModel):
    """One independently scored monitoring situation."""

    id: str
    districts: list[DistrictScenario]


class ScenarioSet(BaseModel):
    """Scenario file consumed by the eval runner."""

    version: str
    scenarios: list[Scenario]

    @model_validator(mode="after")
    def identifiers_are_unique(self) -> Self:
        scenario_ids = [scenario.id for scenario in self.scenarios]
        if len(scenario_ids) != len(set(scenario_ids)):
            raise ValueError("scenario ids must be unique")
        for scenario in self.scenarios:
            district_ids = [district.id for district in scenario.districts]
            if len(district_ids) != len(set(district_ids)):
                raise ValueError(f"{scenario.id}: district ids must be unique")
            for district in scenario.districts:
                hazards = [outcome.hazard for outcome in district.expected]
                if len(hazards) != len(set(hazards)):
                    raise ValueError(
                        f"{scenario.id}/{district.id}: expected hazards must be unique"
                    )
        return self


class EvalReport(BaseModel):
    """Aggregate rules-baseline metrics for a scenario set."""

    system: str = "rules-only"
    scenario_set: str
    scenarios_sha256: str
    rules_sha256: str
    scenario_count: int
    district_count: int
    expected_hazards: int
    predicted_hazards: int
    true_positives: int
    false_positives: int
    false_negatives: int
    correct_severities: int
    hazard_precision: float | None
    hazard_recall: float | None
    severity_accuracy: float | None
    # Alert wording put through the verifier that gates publication: the share
    # with every number and date in the evidence, and the share that would be
    # held. Rule-based wording is never revised, so one is the other's complement
    texts_checked: int
    groundedness: float | None
    hold_rate: float | None


def _rules_for(fields: set[str], rules: Sequence[HazardRule]) -> list[HazardRule]:
    return [rule for rule in rules if rule.metric in fields]


def _screen_source(
    source: str,
    payload: dict[str, Any],
    province: str,
    rules: Sequence[HazardRule],
) -> tuple[Sequence[DailyValue], list[Signal]]:
    days: Sequence[DailyValue]
    if source == "open-meteo-forecast":
        days = parse_forecast(payload)
        source_rules = _rules_for(set(DailyForecast.model_fields), rules)
    elif source == "open-meteo-air-quality":
        days = parse_air_quality(payload)
        source_rules = _rules_for(set(DailyAirQuality.model_fields), rules)
    else:
        raise ValueError(f"Unsupported scenario source: {source}")
    return days, screen(days, province, source_rules)


def _wording_verifies(
    district_id: str, days: Sequence[DailyValue], signal: Signal
) -> bool:
    """Whether the rule-based alert text for a signal passes the verifier."""
    screened = Screened(district_id, 0, days, [signal], frozenset())
    text = write_alert_text(signal, district_id)
    facts = Facts(
        hazard=signal.hazard,
        severity=signal.level,
        onset=signal.onset,
        expires=signal.expires,
        evidence=evidence_for(signal, screened),
    )
    return not verify(AlertDraft(**vars(text)), facts)


def evaluate(path: Path) -> EvalReport:
    """Evaluate every scenario in ``path`` without network or database access."""
    scenario_bytes = path.read_bytes()
    scenario_set = ScenarioSet.model_validate(yaml.safe_load(scenario_bytes))
    rules = load_rules()
    serialized_rules = json.dumps(
        [rule.model_dump(mode="json") for rule in rules], sort_keys=True
    ).encode()
    expected: dict[tuple[str, str, str], Level] = {}
    predicted: dict[tuple[str, str, str], Level] = {}
    district_count = 0
    texts_checked = 0
    texts_verified = 0

    for scenario in scenario_set.scenarios:
        for district in scenario.districts:
            district_count += 1
            for outcome in district.expected:
                expected[(scenario.id, district.id, outcome.hazard)] = outcome.severity
            for source, payload in district.source_payloads.items():
                days, signals = _screen_source(
                    source, payload, district.province, rules
                )
                for signal in signals:
                    predicted[(scenario.id, district.id, signal.hazard)] = signal.level
                    texts_checked += 1
                    texts_verified += _wording_verifies(district.id, days, signal)

    expected_keys = set(expected)
    predicted_keys = set(predicted)
    matched = expected_keys & predicted_keys
    true_positives = len(matched)
    correct_severities = sum(expected[key] == predicted[key] for key in matched)

    return EvalReport(
        scenario_set=scenario_set.version,
        # Line endings differ between checkouts; the scenarios do not
        scenarios_sha256=hashlib.sha256(
            scenario_bytes.replace(b"\r\n", b"\n")
        ).hexdigest(),
        rules_sha256=hashlib.sha256(serialized_rules).hexdigest(),
        scenario_count=len(scenario_set.scenarios),
        district_count=district_count,
        expected_hazards=len(expected_keys),
        predicted_hazards=len(predicted_keys),
        true_positives=true_positives,
        false_positives=len(predicted_keys - expected_keys),
        false_negatives=len(expected_keys - predicted_keys),
        correct_severities=correct_severities,
        hazard_precision=(
            true_positives / len(predicted_keys) if predicted_keys else None
        ),
        hazard_recall=(true_positives / len(expected_keys) if expected_keys else None),
        severity_accuracy=(
            correct_severities / true_positives if true_positives else None
        ),
        texts_checked=texts_checked,
        groundedness=texts_verified / texts_checked if texts_checked else None,
        hold_rate=1 - texts_verified / texts_checked if texts_checked else None,
    )


def main() -> None:
    """Run the rules baseline and optionally save the JSON report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenarios", type=Path, default=DEFAULT_SCENARIOS)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = json.dumps(evaluate(args.scenarios).model_dump(), indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
