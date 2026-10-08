"""Load hazard rules from the packaged threshold configuration."""

from functools import cache
from importlib import resources
from typing import Any

import yaml

from ews.screening.rules import HazardRule


def parse_rules(config: dict[str, Any]) -> list[HazardRule]:
    """Build validated rules from the configuration's contents.

    Raises:
        pydantic.ValidationError: If a rule is incomplete or inconsistent
    """
    return [
        HazardRule(
            hazard=hazard,
            metric=rule["metric"],
            unit=rule["unit"],
            levels=rule["levels"],
            province_levels={
                province.lower(): levels
                for province, levels in rule.get("provinces", {}).items()
            },
        )
        for hazard, rule in config["hazards"].items()
    ]


@cache
def load_rules() -> tuple[HazardRule, ...]:
    """The rules in ``ews/screening/data/thresholds.yaml``."""
    path = resources.files("ews.screening").joinpath("data", "thresholds.yaml")
    return tuple(parse_rules(yaml.safe_load(path.read_text(encoding="utf-8"))))
