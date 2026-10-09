"""The ordered event log of a run: written as the run proceeds, read as a stream."""

import asyncio
import datetime as dt
import time
from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ews.cycles.models import Run, RunEvent
from ews.sources.errors import SourceError

# Opens a session of its own, so an event is committed apart from the run's work
SessionFactory = Callable[[], AsyncSession]

EventType = Literal[
    "run_started",
    "step_started",
    "step_finished",
    "step_failed",
    "source_fetched",
    "signal_raised",
    "error",
    "run_finished",
]


class RunRecorder:
    """Appends events to one run's log, each committed as soon as it happens.

    A run does its work in a single transaction that is rolled back on failure.
    Events are written through other sessions so they outlive that rollback and
    are visible to readers while the run is still in progress.
    """

    def __init__(self, open_session: SessionFactory, run_id: int) -> None:
        self._open_session = open_session
        self._run_id = run_id
        self._seq = 0

    async def emit(self, event_type: EventType, **payload: Any) -> None:
        """Append one event to the log."""
        self._seq += 1
        async with self._open_session() as session:
            session.add(
                RunEvent(
                    run_id=self._run_id,
                    seq=self._seq,
                    at=dt.datetime.now(dt.UTC),
                    type=event_type,
                    payload=payload,
                )
            )
            await session.commit()

    @asynccontextmanager
    async def step(self, name: str) -> AsyncIterator[dict[str, Any]]:
        """Log the start of a step and how it ended.

        Yields a dict; whatever the block puts in it is recorded when the step
        finishes. A failure is logged and re-raised. The log is public, so only
        a source's own account of its failure is recorded in full; any other
        error is recorded by type, since its message may describe internals.
        """
        await self.emit("step_started", step=name)
        outcome: dict[str, Any] = {}
        try:
            yield outcome
        except SourceError as error:
            await self.emit("step_failed", step=name, error=str(error))
            raise
        except Exception as error:
            await self.emit("step_failed", step=name, error=type(error).__name__)
            raise
        await self.emit("step_finished", step=name, **outcome)


class RunEventLog:
    """Hands out a recorder per run."""

    def __init__(self, open_session: SessionFactory) -> None:
        self._open_session = open_session

    def for_run(self, run_id: int) -> RunRecorder:
        return RunRecorder(self._open_session, run_id)


async def events_after(
    session: AsyncSession, run_id: int, after_seq: int
) -> Sequence[RunEvent]:
    """A run's events later than the given position, in order."""
    statement = (
        select(RunEvent)
        .where(RunEvent.run_id == run_id, RunEvent.seq > after_seq)
        .order_by(RunEvent.seq)
    )
    return (await session.scalars(statement)).all()


async def stream_events(
    open_session: SessionFactory,
    run_id: int,
    after_seq: int,
    poll_seconds: float,
    max_seconds: float,
) -> AsyncIterator[Sequence[RunEvent]]:
    """Yield a run's events in batches until the run has finished.

    A finished run is replayed in one batch. An active run yields a batch per
    poll, empty when nothing happened, so the caller can keep the connection
    alive. The stream also ends after ``max_seconds``, so a run that never
    finishes cannot hold a reader, and its polling, open for ever.
    """
    deadline = time.monotonic() + max_seconds
    while True:
        async with open_session() as session:
            # Status first: a run writes its last event before it is marked
            # finished, so a finished status means the events read next are all
            status = await session.scalar(select(Run.status).where(Run.id == run_id))
            events = await events_after(session, run_id, after_seq)
        yield events
        if events:
            after_seq = events[-1].seq
        if status != "running" or time.monotonic() >= deadline:
            return
        await asyncio.sleep(poll_seconds)
