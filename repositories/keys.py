import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CacheScope:
    province: str | None = None
    district: str | None = None
    forecast_days: int | None = None
    purpose: str = "unknown"


def parse_cache_key(cache_key: str) -> CacheScope:
    """Extract typed scope metadata from legacy cache keys."""
    patterns = (
        (r"^weather_(\d+)_([^_]+)_(.+)$", ("days", "province", "district")),
        (r"^forecast_([^_]+)_(.+)_(\d+)$", ("province", "district", "days")),
        (r"^(alerts|combined)_([^_]+)_(\d+)_(.+)$", None),
    )
    for pattern, groups in patterns:
        match = re.match(pattern, cache_key)
        if not match:
            continue
        if groups:
            values = dict(zip(groups, match.groups(), strict=True))
            return CacheScope(
                province=values["province"],
                district=values["district"],
                forecast_days=int(values["days"]),
                purpose=cache_key.split("_", 1)[0],
            )
        purpose, province, days, district = match.groups()
        return CacheScope(province, district, int(days), purpose)
    return CacheScope()
