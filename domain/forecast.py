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
