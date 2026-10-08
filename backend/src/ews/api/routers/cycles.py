"""Monitoring cycle endpoints: trigger a run and read the current signals."""

import datetime as dt
from typing import cast

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict

from ews.api.dependencies import (
    AirQualityClientDep,
    ForecastClientDep,
    SessionDep,
    SettingsDep,
    require_admin,
)
from ews.cycles.models import HazardSignal
from ews.cycles.service import latest_successful_run, run_cycle, signals_of
from ews.screening.rules import Level

router = APIRouter(tags=["cycles"])


class RunOut(BaseModel):
    """A monitoring cycle and how it ended."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    trigger: str
    status: str
    started_at: dt.datetime
    finished_at: dt.datetime | None
    district_count: int
    signal_count: int
    error: str | None


class SignalOut(BaseModel):
    """A hazard threshold reached in a district's forecast."""

    district_id: str
    hazard: str
    level: Level
    onset: dt.date
    expires: dt.date
    metric: str
    unit: str
    peak_value: float
    peak_date: dt.date
    threshold: float
    days_over: list[dt.date]
    # The stored forecast this signal was screened from
    snapshot_id: int

    @classmethod
    def from_record(cls, signal: HazardSignal) -> "SignalOut":
        return cls(
            district_id=signal.district_id,
            hazard=signal.hazard,
            level=cast(Level, signal.level),
            onset=signal.onset,
            expires=signal.expires,
            snapshot_id=signal.snapshot_id,
            **signal.metrics,
        )


class CurrentSignals(BaseModel):
    """The latest successful cycle and the signals it raised."""

    run: RunOut | None
    signals: list[SignalOut]


@router.post(
    "/runs",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_admin)],
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Missing or wrong admin token"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "No admin token is configured"
        },
    },
)
async def trigger_run(
    session: SessionDep,
    settings: SettingsDep,
    client: ForecastClientDep,
    air_quality_client: AirQualityClientDep,
) -> RunOut:
    """Run a monitoring cycle now and return how it ended.

    The response is 201 even when the cycle fails, because the run is recorded
    either way; check ``status`` and ``error``.
    """
    run = await run_cycle(
        session, client, air_quality_client, settings, trigger="manual"
    )
    return RunOut.model_validate(run)


@router.get("/signals")
async def current_signals(session: SessionDep) -> CurrentSignals:
    """Hazard signals from the latest successful cycle."""
    run = await latest_successful_run(session)
    if run is None:
        return CurrentSignals(run=None, signals=[])
    signals = await signals_of(session, run)
    return CurrentSignals(
        run=RunOut.model_validate(run),
        signals=[SignalOut.from_record(signal) for signal in signals],
    )
