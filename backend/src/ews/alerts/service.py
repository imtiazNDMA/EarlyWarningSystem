"""Apply the alert lifecycle after a screening, and read alerts back."""

import datetime as dt
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ews.alerts.lifecycle import (
    Action,
    ActiveAlert,
    Certainty,
    Urgency,
    certainty,
    decide,
    urgency,
)
from ews.alerts.models import Alert
from ews.alerts.text import AlertText, write_alert_text
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
    # Hazard -> urgency and certainty as an analyst judged them; a hazard not
    # listed here gets both from lead time alone
    judgements: Mapping[str, tuple[Urgency, Certainty]] = field(default_factory=dict)


def evidence_for(signal: Signal, screened: Screened) -> list[dict[str, Any]]:
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


@dataclass(frozen=True)
class Planned:
    """What the lifecycle decided for one district and hazard, before it is done."""

    screened: Screened
    hazard: str
    action: Action
    existing: Alert | None
    signal: Signal | None
    # First day of the forecast the decision was made against
    today: dt.date

    @property
    def key(self) -> tuple[str, str]:
        return self.screened.district_id, self.hazard

    @property
    def needs_text(self) -> bool:
        """Whether carrying this out writes a new alert."""
        return self.signal is not None and self.action in (
            Action.ISSUE,
            Action.SUPERSEDE,
        )


@dataclass(frozen=True)
class Authored:
    """An alert's wording, who wrote it, and why it is held back if it is."""

    text: AlertText
    # "rules" for templates, "model" for the drafter
    generated_by: str
    # Checks the wording failed; a held alert is stored but never active
    held_reasons: list[str] | None = None
    # The same wording in Urdu; without it the alert is published in English alone
    urdu: AlertText | None = None


async def plan_lifecycle(
    session: AsyncSession, screenings: Sequence[Screened]
) -> list[Planned]:
    """Decide, without changing anything, what each screening means for alerts.

    For each district and hazard: issue an alert for a new signal, leave a
    matching alert alone, supersede one whose severity or window changed, and
    cancel or expire one whose signal has gone.
    """
    active_alerts = (
        await session.scalars(select(Alert).where(Alert.status == "active"))
    ).all()
    active_by_key = {(a.district_id, a.hazard): a for a in active_alerts}
    plan: list[Planned] = []

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
            plan.append(Planned(screened, hazard, action, existing, signal, today))
    return plan


async def apply_plan(
    session: AsyncSession,
    run_id: int,
    plan: Sequence[Planned],
    authored: Mapping[tuple[str, str], Authored] | None = None,
) -> Counter[Action]:
    """Carry out a lifecycle plan.

    Args:
        session: Session to write with; the caller commits
        run_id: The run the plan belongs to
        plan: Decisions from ``plan_lifecycle``
        authored: Wording by district and hazard for the alerts being written;
            an alert with none gets rule-based wording, in English alone.
            Wording that is held is stored as a held alert, and the alert it
            would have replaced stays active.

    Returns:
        How many times each action was taken
    """
    name_rows = await session.execute(select(District.id, District.name_en))
    names = {district_id: name for district_id, name in name_rows}
    now = dt.datetime.now(dt.UTC)
    taken: Counter[Action] = Counter()

    for planned in plan:
        signal, existing = planned.signal, planned.existing
        wording = (authored or {}).get(planned.key) if planned.needs_text else None
        held = wording is not None and wording.held_reasons is not None
        taken[Action.HOLD if held else planned.action] += 1

        if existing and planned.action in ENDED_STATUS and not held:
            existing.status = ENDED_STATUS[planned.action]
            existing.ended_at = now

        if signal is None or not planned.needs_text:
            continue
        screened = planned.screened
        if wording is None:
            wording = Authored(
                write_alert_text(signal, names[screened.district_id]), "rules"
            )
        judged_urgency, judged_certainty = screened.judgements.get(
            planned.hazard,
            (
                urgency(signal.onset, planned.today),
                certainty(signal.onset, planned.today),
            ),
        )
        session.add(
            Alert(
                district_id=screened.district_id,
                run_id=run_id,
                hazard=planned.hazard,
                severity=signal.level,
                urgency=judged_urgency,
                certainty=judged_certainty,
                onset=signal.onset,
                expires=signal.expires,
                headline_en=wording.text.headline,
                body_en=wording.text.body,
                instructions_en=wording.text.instructions,
                headline_ur=wording.urdu.headline if wording.urdu else None,
                body_ur=wording.urdu.body if wording.urdu else None,
                instructions_ur=wording.urdu.instructions if wording.urdu else None,
                generated_by=wording.generated_by,
                evidence=evidence_for(signal, screened),
                status="held" if held else "active",
                held_reasons=wording.held_reasons,
                issued_at=now,
                # A held alert replaces nothing
                supersedes_id=existing.id if existing and not held else None,
            )
        )
    await session.flush()
    return taken


async def apply_lifecycle(
    session: AsyncSession, run_id: int, screenings: Sequence[Screened]
) -> Counter[Action]:
    """Bring alerts into line with a run's screenings, with rule-based wording."""
    return await apply_plan(session, run_id, await plan_lifecycle(session, screenings))


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
