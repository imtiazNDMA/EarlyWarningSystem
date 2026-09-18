from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any


class DataStatus(StrEnum):
    FRESH = "fresh"
    STALE_USABLE = "stale_but_usable"
    EXPIRED = "expired"
    PARTIAL = "partial"
    INVALID = "invalid"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True)
class Location:
    location_id: str
    province: str
    district: str
    latitude: float
    longitude: float
    timezone: str = "Asia/Karachi"


@dataclass(frozen=True)
class DataQualityReport:
    status: DataStatus
    expected_days: int
    returned_days: int
    missing_dates: tuple[str, ...] = ()
    issues: tuple[str, ...] = ()


@dataclass(frozen=True)
class EnsembleCorroboration:
    ensemble_payload: dict[str, Any]
    models: tuple[str, ...]
    members_per_model: dict[str, int]
    checksum: str

    def spread_summary(self, field: str) -> dict[str, float]:
        hourly = self.ensemble_payload.get("hourly", {})
        member_values = []
        for key, values in hourly.items():
            if key.startswith(f"{field}_member") and isinstance(values, list):
                non_null = [v for v in values if v is not None]
                if non_null:
                    member_values.append(non_null)
        if not member_values:
            return {"mean": 0.0, "spread": 0.0, "member_count": 0}
        min_len = min(len(v) for v in member_values)
        trimmed = [v[:min_len] for v in member_values]
        avgs = [sum(row) / len(row) for row in zip(*trimmed, strict=True)]
        overall_mean = sum(avgs) / len(avgs) if avgs else 0.0
        overall_spread = max(avgs) - min(avgs) if avgs else 0.0
        return {
            "mean": round(overall_mean, 2),
            "spread": round(overall_spread, 2),
            "member_count": len(member_values),
        }

    def member_count(self, model: str) -> int:
        hourly = self.ensemble_payload.get("hourly", {})
        return sum(
            1
            for key in hourly
            if "_member" in key
            and key.endswith(model)
            and isinstance(hourly[key], list)
        )


@dataclass(frozen=True)
class ForecastRun:
    run_id: str
    provider: str
    location: Location
    requested_days: int
    retrieved_at: datetime
    fresh_until: datetime
    usable_until: datetime
    payload: dict[str, Any]
    quality: DataQualityReport
    checksum: str
    source_url: str
    schema_version: int = 1
    corroboration: EnsembleCorroboration | None = None

    def freshness_at(self, now: datetime) -> DataStatus:
        if self.quality.status in {DataStatus.INVALID, DataStatus.PARTIAL}:
            return self.quality.status
        if now <= self.fresh_until:
            return DataStatus.FRESH
        if now <= self.usable_until:
            return DataStatus.STALE_USABLE
        return DataStatus.EXPIRED

    def to_document(self) -> dict[str, Any]:
        document = asdict(self)
        document["quality"]["status"] = self.quality.status.value
        return document

    @classmethod
    def from_document(cls, document: dict[str, Any]) -> "ForecastRun":
        location = Location(**document["location"])
        quality_data = document["quality"]
        quality = DataQualityReport(
            status=DataStatus(quality_data["status"]),
            expected_days=quality_data["expected_days"],
            returned_days=quality_data["returned_days"],
            missing_dates=tuple(quality_data.get("missing_dates", ())),
            issues=tuple(quality_data.get("issues", ())),
        )
        corroboration_data = document.get("corroboration")
        corroboration = None
        if isinstance(corroboration_data, dict) and corroboration_data.get(
            "ensemble_payload"
        ):
            corroboration = EnsembleCorroboration(
                ensemble_payload=corroboration_data["ensemble_payload"],
                models=tuple(corroboration_data.get("models", ())),
                members_per_model=corroboration_data.get("members_per_model", {}),
                checksum=corroboration_data.get("checksum", ""),
            )
        return cls(
            run_id=document["run_id"],
            provider=document["provider"],
            location=location,
            requested_days=document["requested_days"],
            retrieved_at=document["retrieved_at"],
            fresh_until=document["fresh_until"],
            usable_until=document["usable_until"],
            payload=document["payload"],
            quality=quality,
            checksum=document["checksum"],
            source_url=document["source_url"],
            schema_version=document.get("schema_version", 1),
            corroboration=corroboration,
        )


@dataclass(frozen=True)
class ForecastResult:
    run: ForecastRun | None
    status: DataStatus
    refresh_attempted: bool
    refresh_error: str | None = None

    @property
    def available(self) -> bool:
        return self.run is not None and self.status not in {
            DataStatus.EXPIRED,
            DataStatus.INVALID,
            DataStatus.UNAVAILABLE,
        }


def utc_now() -> datetime:
    return datetime.now(UTC)


def freshness_windows(
    retrieved_at: datetime, fresh_seconds: int, stale_seconds: int
) -> tuple[datetime, datetime]:
    fresh_until = retrieved_at + timedelta(seconds=fresh_seconds)
    return fresh_until, fresh_until + timedelta(seconds=stale_seconds)
