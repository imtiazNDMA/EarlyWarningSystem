"""Monitoring cycle endpoints: trigger and inspect runs, read current signals."""

import datetime as dt
from collections.abc import AsyncIterator
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict

from ews.api.dependencies import (
    AirQualityClientDep,
    ForecastClientDep,
    RunEventLogDep,
    SessionDep,
    SessionFactoryDep,
    SettingsDep,
    require_admin,
)
from ews.cycles.events import EventType, SessionFactory, stream_events
from ews.cycles.models import HazardSignal, Run
from ews.cycles.service import (
    latest_successful_run,
    list_runs,
    run_cycle,
    signals_of,
)
from ews.screening.rules import Level

router = APIRouter(tags=["cycles"])


class RunOut(BaseModel):
    """A monitoring cycle and how it ended."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    trigger: str
    status: Literal["running", "succeeded", "failed"]
    started_at: dt.datetime
    finished_at: dt.datetime | None
    district_count: int
    signal_count: int
    error: str | None


class RunEventOut(BaseModel):
    """One entry in a run's event log; the ``data`` of each streamed message."""

    model_config = ConfigDict(from_attributes=True)

    # Position within the run, from 1
    seq: int
    at: dt.datetime
    type: EventType
    # Details that depend on the type, such as ``step`` or ``district_id``
    payload: dict[str, Any]


class EventStreamResponse(StreamingResponse):
    """Server-Sent Events."""

    media_type = "text/event-stream"


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
    events: RunEventLogDep,
) -> RunOut:
    """Run a monitoring cycle now and return how it ended.

    The response is 201 even when the cycle fails, because the run is recorded
    either way; check ``status`` and ``error``.
    """
    run = await run_cycle(
        session, client, air_quality_client, settings, trigger="manual", events=events
    )
    return RunOut.model_validate(run)


@router.get("/runs")
async def runs(
    session: SessionDep, limit: Annotated[int, Query(ge=1, le=200)] = 50
) -> list[RunOut]:
    """Monitoring cycles, newest first."""
    return [RunOut.model_validate(run) for run in await list_runs(session, limit)]


UNKNOWN_RUN: dict[int | str, dict[str, Any]] = {
    status.HTTP_404_NOT_FOUND: {"description": "Unknown run"}
}


async def _known_run(session: SessionDep, run_id: int) -> Run:
    run = await session.get(Run, run_id)
    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown run: {run_id}"
        )
    return run


@router.get("/runs/{run_id}", responses=UNKNOWN_RUN)
async def run_detail(run: Annotated[Run, Depends(_known_run)]) -> RunOut:
    """One monitoring cycle."""
    return RunOut.model_validate(run)


async def _server_sent(
    open_session: SessionFactory,
    run_id: int,
    after_seq: int,
    poll_seconds: float,
    max_seconds: float,
) -> AsyncIterator[str]:
    """Format a run's events as Server-Sent Events, closing with an ``end`` event."""
    async for batch in stream_events(
        open_session, run_id, after_seq, poll_seconds, max_seconds
    ):
        if not batch:
            # A comment: ignored by clients, but shows the connection is alive
            yield ": waiting\n\n"
        for event in batch:
            data = RunEventOut.model_validate(event).model_dump_json()
            yield f"id: {event.seq}\ndata: {data}\n\n"
    # Without this a browser treats the close as a drop and reconnects
    yield "event: end\ndata: {}\n\n"


@router.get(
    "/runs/{run_id}/events",
    response_class=EventStreamResponse,
    responses={
        **UNKNOWN_RUN,
        status.HTTP_200_OK: {
            "model": RunEventOut,
            "description": "A stream of messages, each carrying one event as JSON, "
            "then a final message of type `end`",
        },
    },
)
async def run_events(
    run: Annotated[Run, Depends(_known_run)],
    open_session: SessionFactoryDep,
    settings: SettingsDep,
    last_event_id: Annotated[int | None, Header()] = None,
) -> EventStreamResponse:
    """The run's event log as Server-Sent Events.

    A finished run is replayed at once; an active run streams events as they
    happen. A client that reconnects with ``Last-Event-ID`` resumes after it.
    """
    return EventStreamResponse(
        _server_sent(
            open_session,
            run.id,
            last_event_id or 0,
            settings.run_events_poll_seconds,
            settings.run_events_max_stream_seconds,
        ),
        # Stops nginx holding events back to fill a buffer
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
