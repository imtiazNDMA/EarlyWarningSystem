"""Alert endpoints."""

import datetime as dt
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from ews.alerts.lifecycle import Certainty, Urgency
from ews.alerts.models import Alert
from ews.alerts.service import get_alert, list_alerts
from ews.api.dependencies import SessionDep
from ews.districts.models import District
from ews.screening.rules import Level

router = APIRouter(prefix="/alerts", tags=["alerts"])

AlertStatus = Literal["active", "superseded", "cancelled", "expired"]


class EvidenceOut(BaseModel):
    """One forecast value that justifies an alert."""

    # The stored source payload the value was read from
    snapshot_id: int
    metric: str
    unit: str
    date: dt.date
    value: float
    threshold: float


class AlertOut(BaseModel):
    """An alert and the district it was issued for."""

    id: int
    district_id: str
    district_name: str
    province: str
    hazard: str
    severity: Level
    urgency: Urgency
    certainty: Certainty
    onset: dt.date
    expires: dt.date
    headline_en: str
    body_en: str
    instructions_en: str
    headline_ur: str | None
    body_ur: str | None
    instructions_ur: str | None
    generated_by: str
    evidence: list[EvidenceOut]
    status: AlertStatus
    issued_at: dt.datetime
    ended_at: dt.datetime | None
    supersedes_id: int | None
    run_id: int

    @classmethod
    def fields_from(cls, alert: Alert, district: District) -> dict[str, object]:
        """Field values for an alert record and its district."""
        return {
            "id": alert.id,
            "district_id": district.id,
            "district_name": district.name_en,
            "province": district.province,
            "hazard": alert.hazard,
            "severity": alert.severity,
            "urgency": alert.urgency,
            "certainty": alert.certainty,
            "onset": alert.onset,
            "expires": alert.expires,
            "headline_en": alert.headline_en,
            "body_en": alert.body_en,
            "instructions_en": alert.instructions_en,
            "headline_ur": alert.headline_ur,
            "body_ur": alert.body_ur,
            "instructions_ur": alert.instructions_ur,
            "generated_by": alert.generated_by,
            "evidence": alert.evidence,
            "status": alert.status,
            "issued_at": alert.issued_at,
            "ended_at": alert.ended_at,
            "supersedes_id": alert.supersedes_id,
            "run_id": alert.run_id,
        }


class AlertDetail(AlertOut):
    """An alert, plus the alert that replaced it if it was superseded."""

    superseded_by_id: int | None


@router.get("")
async def alerts(
    session: SessionDep,
    status: Annotated[AlertStatus | None, Query()] = None,
    province: Annotated[str | None, Query(description="Case-insensitive")] = None,
    hazard: Annotated[str | None, Query()] = None,
    severity: Annotated[Level | None, Query()] = None,
    district_id: Annotated[str | None, Query()] = None,
    issued_since: Annotated[dt.datetime | None, Query()] = None,
    issued_until: Annotated[dt.datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
) -> list[AlertOut]:
    """Alerts, newest first. With no filters this is the full alert history."""
    rows = await list_alerts(
        session,
        status=status,
        province=province,
        hazard=hazard,
        severity=severity,
        district_id=district_id,
        issued_since=issued_since,
        issued_until=issued_until,
        limit=limit,
    )
    return [
        AlertOut.model_validate(AlertOut.fields_from(alert, district))
        for alert, district in rows
    ]


@router.get(
    "/{alert_id}",
    responses={status.HTTP_404_NOT_FOUND: {"description": "Unknown alert"}},
)
async def alert_detail(alert_id: int, session: SessionDep) -> AlertDetail:
    """One alert with its evidence."""
    found = await get_alert(session, alert_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown alert: {alert_id}"
        )
    alert, district, superseded_by_id = found
    return AlertDetail.model_validate(
        {
            **AlertOut.fields_from(alert, district),
            "superseded_by_id": superseded_by_id,
        }
    )
