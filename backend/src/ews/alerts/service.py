"""Apply the alert lifecycle after a screening, and read alerts back."""

import datetime as dt
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ews.alerts.lifecycle import Action, ActiveAlert, certainty, decide, urgency
from ews.alerts.models import Alert
from ews.alerts.text import write_alert_text
from ews.districts.models import District
from ews.screening.rules import DailyValue, Signal

ENDED_STATUS = {
    Action.SUPERSEDE: "superseded",
    Action.CANCEL: "cancelled",
    Action.EXPIRE: "expired",
}


@dataclass(frozen=True)
class Screened:
    """One district's screening result within a run."""

    district_id: str
    snapshot_id: int
    days: Sequence[DailyValue]
    signals: Sequence[Signal]
    # Hazards successfully assessed by this source, including those with no signal
    assessed_hazards: frozenset[str]


def _evidence(signal: Signal, screened: Screened) -> list[dict[str, Any]]:
    """The forecast values behind a signal, each tied to its snapshot."""
    values = {day.date: getattr(day, signal.metric) for day in screened.days}
    return [
        {
            "snapshot_id": screened.snapshot_id,
            "metric": signal.metric,
            "unit": signal.unit,
            "date": date.isoformat(),
            "value": values[date],
            "threshold": signal.threshold,
        }
        for date in signal.days_over
    ]


async def apply_lifecycle(
    session: AsyncSession, run_id: int, screenings: Sequence[Screened]
) -> Counter[Action]:
    """Bring alerts into line with a run's screening results.

    For each district and hazard: issue an alert for a new signal, leave a
    matching alert alone, supersede one whose severity or window changed, and
    cancel or expire one whose signal has gone.

    Args:
        session: Session to write with; the caller commits
        run_id: The run the screenings belong to
        screenings: One entry per district screened in the run

    Returns:
        How many times each action was taken
    """
    name_rows = await session.execute(select(District.id, District.name_en))
    names = {district_id: name for district_id, name in name_rows}
    active_alerts = (
        await session.scalars(select(Alert).where(Alert.status == "active"))
    ).all()
    active_by_key = {(a.district_id, a.hazard): a for a in active_alerts}

    now = dt.datetime.now(dt.UTC)
    taken: Counter[Action] = Counter()

    for screened in screenings:
        if not screened.days:
            continue
        # The forecast's own first day, so the decision does not depend on the
        # server's clock or time zone
        today = screened.days[0].date
        signals = {signal.hazard: signal for signal in screened.signals}
        hazards = set(signals) | {
            hazard
            for district_id, hazard in active_by_key
            if district_id == screened.district_id
            and hazard in screened.assessed_hazards
        }

        for hazard in sorted(hazards):
            existing = active_by_key.get((screened.district_id, hazard))
            signal = signals.get(hazard)
            action = decide(
                ActiveAlert(existing.severity, existing.onset, existing.expires)
                if existing
                else None,
                signal,
                today,
            )
            taken[action] += 1

            if existing and action in ENDED_STATUS:
                existing.status = ENDED_STATUS[action]
                existing.ended_at = now

            if signal and action in (Action.ISSUE, Action.SUPERSEDE):
                text = write_alert_text(signal, names[screened.district_id])
                session.add(
                    Alert(
                        district_id=screened.district_id,
                        run_id=run_id,
                        hazard=hazard,
                        severity=signal.level,
                        urgency=urgency(signal.onset, today),
                        certainty=certainty(signal.onset, today),
                        onset=signal.onset,
                        expires=signal.expires,
                        headline_en=text.headline,
                        body_en=text.body,
                        instructions_en=text.instructions,
                        generated_by="rules",
                        evidence=_evidence(signal, screened),
                        status="active",
                        issued_at=now,
                        supersedes_id=existing.id if existing else None,
                    )
                )
    await session.flush()
    return taken


async def list_alerts(
    session: AsyncSession,
    *,
    status: str | None = None,
    province: str | None = None,
    hazard: str | None = None,
    severity: str | None = None,
    district_id: str | None = None,
    issued_since: dt.datetime | None = None,
    issued_until: dt.datetime | None = None,
    limit: int = 100,
) -> Sequence[tuple[Alert, District]]:
    """Alerts with their districts, newest first, narrowed by any filter given."""
    statement = (
        select(Alert, District)
        .join(District, District.id == Alert.district_id)
        .order_by(Alert.issued_at.desc(), Alert.id.desc())
        .limit(limit)
    )
    if status is not None:
        statement = statement.where(Alert.status == status)
    if province is not None:
        statement = statement.where(func.lower(District.province) == province.lower())
    if hazard is not None:
        statement = statement.where(Alert.hazard == hazard)
    if severity is not None:
        statement = statement.where(Alert.severity == severity)
    if district_id is not None:
        statement = statement.where(Alert.district_id == district_id)
    if issued_since is not None:
        statement = statement.where(Alert.issued_at >= issued_since)
    if issued_until is not None:
        statement = statement.where(Alert.issued_at <= issued_until)
    rows = await session.execute(statement)
    return [(alert, district) for alert, district in rows]


async def get_alert(
    session: AsyncSession, alert_id: int
) -> tuple[Alert, District, int | None] | None:
    """One alert, its district, and the id of the alert that replaced it."""
    row = (
        await session.execute(
            select(Alert, District)
            .join(District, District.id == Alert.district_id)
            .where(Alert.id == alert_id)
        )
    ).first()
    if row is None:
        return None
    alert, district = row
    superseded_by = await session.scalar(
        select(Alert.id).where(Alert.supersedes_id == alert_id)
    )
    return alert, district, superseded_by
