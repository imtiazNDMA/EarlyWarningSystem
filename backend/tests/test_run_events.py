"""Tests for run recording: the run list, the event log and its stream."""

import datetime as dt
import json
import logging
from typing import Any

import httpx
import pytest
from httpx import AsyncClient
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from ews.core.db import create_session_factory
from ews.core.logging import RunIdFilter, bound_run_id
from ews.core.settings import Settings
from ews.cycles.events import (
    RunEventLog,
    SessionFactory,
    events_after,
    stream_events,
)
from ews.cycles.models import Run, RunEvent
from ews.cycles.service import run_cycle
from ews.sources.errors import SourceError
from ews.sources.models import SourceSnapshot
from ews.sources.open_meteo import OpenMeteoForecastClient
from ews.sources.open_meteo_air_quality import OpenMeteoAirQualityClient
from tests.conftest import ADMIN_TOKEN, Upstream
from tests.test_cycles import wet_in_lahore

ADMIN = {"X-Admin-Token": ADMIN_TOKEN}


def parse_stream(body: str) -> list[dict[str, Any]]:
    """The messages of a Server-Sent Events body, comments left out."""
    messages = []
    for block in body.strip().split("\n\n"):
        fields = dict(
            line.split(": ", 1)
            for line in block.split("\n")
            if not line.startswith(":")
        )
        if fields:
            messages.append(
                {
                    "id": fields.get("id"),
                    "event": fields.get("event", "message"),
                    "data": json.loads(fields["data"]),
                }
            )
    return messages


async def events_of(client: AsyncClient, run_id: int) -> list[dict[str, Any]]:
    """The events a client receives for a run, without the closing message."""
    response = await client.get(f"/api/runs/{run_id}/events")
    assert response.status_code == 200
    *events, end = parse_stream(response.text)
    assert end["event"] == "end"
    return [message["data"] for message in events]


def summary(event: dict[str, Any]) -> tuple[str, str | None]:
    """An event's type and the step or source it concerns."""
    payload = event["payload"]
    return event["type"], payload.get("step") or payload.get("source")


class TestRuns:
    """Test cases for GET /api/runs and GET /api/runs/{id}"""

    async def test_lists_runs_newest_first(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        first = (await client.post("/api/runs", headers=ADMIN)).json()
        upstream.failing = True
        second = (await client.post("/api/runs", headers=ADMIN)).json()

        runs = (await client.get("/api/runs")).json()

        assert [run["id"] for run in runs] == [second["id"], first["id"]]
        assert [run["status"] for run in runs] == ["failed", "succeeded"]
        assert runs[1] == first

    async def test_limit_caps_the_list(
        self,
        client: AsyncClient,
        upstream: Upstream,  # noqa: ARG002
    ) -> None:
        await client.post("/api/runs", headers=ADMIN)
        latest = (await client.post("/api/runs", headers=ADMIN)).json()

        runs = (await client.get("/api/runs", params={"limit": 1})).json()

        assert [run["id"] for run in runs] == [latest["id"]]

    async def test_returns_one_run(
        self,
        client: AsyncClient,
        upstream: Upstream,  # noqa: ARG002
    ) -> None:
        run = (await client.post("/api/runs", headers=ADMIN)).json()

        response = await client.get(f"/api/runs/{run['id']}")

        assert response.status_code == 200
        assert response.json() == run

    async def test_unknown_run_is_not_found(self, client: AsyncClient) -> None:
        run = await client.get("/api/runs/999999")
        events = await client.get("/api/runs/999999/events")

        assert run.status_code == 404
        assert events.status_code == 404


class TestRunEvents:
    """Test cases for GET /api/runs/{id}/events"""

    async def test_replays_a_finished_run_in_order(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        upstream.payload_for = wet_in_lahore
        run = (await client.post("/api/runs", headers=ADMIN)).json()

        events = await events_of(client, run["id"])

        assert [summary(event) for event in events] == [
            ("run_started", None),
            ("step_started", "fetch_forecasts"),
            ("source_fetched", "open-meteo-forecast"),
            ("step_finished", "fetch_forecasts"),
            ("step_started", "fetch_air_quality"),
            ("source_fetched", "open-meteo-air-quality"),
            ("step_finished", "fetch_air_quality"),
            ("step_started", "screen_weather"),
            ("signal_raised", None),
            ("step_finished", "screen_weather"),
            ("step_started", "screen_air_quality"),
            ("step_finished", "screen_air_quality"),
            ("step_started", "analyse_signals"),
            ("analysis_skipped", None),
            ("step_finished", "analyse_signals"),
            ("step_started", "write_urdu"),
            ("urdu_skipped", None),
            ("step_finished", "write_urdu"),
            ("step_started", "apply_alert_lifecycle"),
            ("step_finished", "apply_alert_lifecycle"),
            ("run_finished", None),
        ]
        assert [event["seq"] for event in events] == list(range(1, 22))

    async def test_events_carry_what_happened(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        upstream.payload_for = wet_in_lahore
        run = (await client.post("/api/runs", headers=ADMIN)).json()

        events = await events_of(client, run["id"])

        payloads = {summary(event): event["payload"] for event in events}
        assert payloads[("run_started", None)] == {"trigger": "manual"}
        assert payloads[("source_fetched", "open-meteo-forecast")]["snapshots"] == 155
        signal = payloads[("signal_raised", None)]
        assert signal["district_id"] == "lahore"
        assert signal["hazard"] == "heavy_rain"
        assert signal["level"] == "severe"
        assert payloads[("step_finished", "screen_weather")]["signals"] == 1
        assert payloads[("step_finished", "apply_alert_lifecycle")]["actions"] == {
            "issue": 1
        }
        assert payloads[("run_finished", None)] == {
            "status": "succeeded",
            "district_count": 155,
            "signal_count": 1,
        }
        started = dt.datetime.fromisoformat(run["started_at"])
        assert dt.datetime.fromisoformat(events[0]["at"]) >= started

    async def test_is_served_as_an_event_stream(
        self,
        client: AsyncClient,
        upstream: Upstream,  # noqa: ARG002
    ) -> None:
        run = (await client.post("/api/runs", headers=ADMIN)).json()

        response = await client.get(f"/api/runs/{run['id']}/events")

        assert response.headers["content-type"].startswith("text/event-stream")
        first = parse_stream(response.text)[0]
        assert first["id"] == "1"
        assert first["event"] == "message"

    async def test_resumes_after_the_last_event_a_client_saw(
        self,
        client: AsyncClient,
        upstream: Upstream,  # noqa: ARG002
    ) -> None:
        run = (await client.post("/api/runs", headers=ADMIN)).json()
        everything = await events_of(client, run["id"])

        response = await client.get(
            f"/api/runs/{run['id']}/events", headers={"Last-Event-ID": "3"}
        )

        *resumed, _end = parse_stream(response.text)
        assert [message["data"] for message in resumed] == everything[3:]

    async def test_a_source_that_fails_without_stopping_the_run_is_logged(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        assert upstream.air_quality is not None
        upstream.air_quality.failing = True
        run = (await client.post("/api/runs", headers=ADMIN)).json()

        events = await events_of(client, run["id"])

        failed = next(event for event in events if event["type"] == "step_failed")
        assert failed["payload"]["step"] == "fetch_air_quality"
        assert "HTTP 503" in failed["payload"]["error"]
        assert ("step_started", "screen_air_quality") not in map(summary, events)
        assert events[-1]["payload"]["status"] == "succeeded"

    async def test_a_failed_run_ends_with_its_error(
        self, client: AsyncClient, upstream: Upstream
    ) -> None:
        upstream.failing = True
        run = (await client.post("/api/runs", headers=ADMIN)).json()

        events = await events_of(client, run["id"])

        error, finished = events[-2:]
        assert error["type"] == "error"
        assert "HTTP 503" in error["payload"]["message"]
        assert finished["payload"]["status"] == "failed"


class TestLiveStream:
    """Test cases for stream_events while a run is still in progress"""

    async def test_yields_events_as_they_are_recorded_until_the_run_finishes(
        self, db_session: AsyncSession, open_session: SessionFactory
    ) -> None:
        run = Run(
            trigger="manual", status="running", started_at=dt.datetime.now(dt.UTC)
        )
        db_session.add(run)
        await db_session.commit()
        recorder = RunEventLog(open_session).for_run(run.id)
        await recorder.emit("run_started", trigger="manual")
        stream = stream_events(
            open_session, run.id, after_seq=0, poll_seconds=0.01, max_seconds=60
        )

        first = await anext(stream)
        idle = await anext(stream)
        await recorder.emit("step_started", step="fetch_forecasts")
        second = await anext(stream)
        await recorder.emit("run_finished", status="succeeded")
        run.status = "succeeded"
        await db_session.commit()
        last = await anext(stream)

        assert [event.type for event in first] == ["run_started"]
        assert list(idle) == []
        assert [event.type for event in second] == ["step_started"]
        assert [event.type for event in last] == ["run_finished"]
        with pytest.raises(StopAsyncIteration):
            await anext(stream)

    async def test_gives_up_on_a_run_that_never_finishes(
        self, db_session: AsyncSession, open_session: SessionFactory
    ) -> None:
        run = Run(
            trigger="manual", status="running", started_at=dt.datetime.now(dt.UTC)
        )
        db_session.add(run)
        await db_session.commit()

        batches = [
            batch
            async for batch in stream_events(
                open_session, run.id, after_seq=0, poll_seconds=0.01, max_seconds=0.05
            )
        ]

        assert batches
        assert all(len(batch) == 0 for batch in batches)


class TestStepFailures:
    """Test cases for what the public log says about a failed step"""

    async def events_of_failed_step(
        self, db_session: AsyncSession, open_session: SessionFactory, error: Exception
    ) -> list[RunEvent]:
        run = Run(
            trigger="manual", status="running", started_at=dt.datetime.now(dt.UTC)
        )
        db_session.add(run)
        await db_session.commit()
        recorder = RunEventLog(open_session).for_run(run.id)

        with pytest.raises(type(error)):
            async with recorder.step("fetch_forecasts"):
                raise error

        return list(await events_after(db_session, run.id, 0))

    async def test_a_source_failure_is_recorded_with_its_message(
        self, db_session: AsyncSession, open_session: SessionFactory
    ) -> None:
        _, failed = await self.events_of_failed_step(
            db_session, open_session, SourceError("open-meteo-forecast", "HTTP 503")
        )

        assert failed.payload == {
            "step": "fetch_forecasts",
            "error": "open-meteo-forecast: HTTP 503",
        }

    async def test_any_other_failure_is_recorded_by_type_only(
        self, db_session: AsyncSession, open_session: SessionFactory
    ) -> None:
        _, failed = await self.events_of_failed_step(
            db_session,
            open_session,
            RuntimeError("password authentication failed for user ews"),
        )

        assert failed.payload == {"step": "fetch_forecasts", "error": "RuntimeError"}


class TestEventsOutliveARollback:
    """Test cases for the event log on its own connections, with real commits"""

    async def test_a_failed_run_keeps_its_whole_log_and_none_of_its_data(
        self, engine: AsyncEngine
    ) -> None:
        upstream = Upstream()
        upstream.failing = True
        open_session = create_session_factory(engine)
        run_id = None
        try:
            async with (
                httpx.AsyncClient(
                    transport=httpx.MockTransport(upstream.handle)
                ) as http,
                open_session() as session,
            ):
                run = await run_cycle(
                    session,
                    OpenMeteoForecastClient(http, base_url="https://weather.test"),
                    OpenMeteoAirQualityClient(http, base_url="https://air.test"),
                    Settings(_env_file=None),
                    trigger="manual",
                    events=RunEventLog(open_session),
                )
                run_id = run.id

            async with open_session() as session:
                events = (
                    await session.scalars(
                        select(RunEvent)
                        .where(RunEvent.run_id == run_id)
                        .order_by(RunEvent.seq)
                    )
                ).all()
                snapshots = await session.scalar(
                    select(func.count()).select_from(SourceSnapshot)
                )

            assert run.status == "failed"
            assert [(event.type, event.payload.get("step")) for event in events] == [
                ("run_started", None),
                ("step_started", "fetch_forecasts"),
                ("step_failed", "fetch_forecasts"),
                ("error", None),
                ("run_finished", None),
            ]
            assert snapshots == 0
        finally:
            # These rows were really committed, so the usual rollback misses them
            async with open_session() as session:
                await session.execute(delete(RunEvent).where(RunEvent.run_id == run_id))
                await session.execute(delete(Run).where(Run.id == run_id))
                await session.commit()


class TestRunIdInLogs:
    """Test cases for log lines carrying the run id"""

    def test_records_inside_a_run_carry_its_id(self) -> None:
        record = logging.LogRecord(
            "ews", logging.INFO, __file__, 1, "hello", None, None
        )

        with bound_run_id(42):
            RunIdFilter().filter(record)

        assert record.run_id == 42  # type: ignore[attr-defined]

    def test_records_outside_a_run_carry_a_placeholder(self) -> None:
        record = logging.LogRecord(
            "ews", logging.INFO, __file__, 1, "hello", None, None
        )

        RunIdFilter().filter(record)

        assert record.run_id == "-"  # type: ignore[attr-defined]

    async def test_a_cycle_logs_under_its_run_id(
        self,
        client: AsyncClient,
        upstream: Upstream,  # noqa: ARG002
        caplog: pytest.LogCaptureFixture,
    ) -> None:
        caplog.handler.addFilter(RunIdFilter())

        with caplog.at_level(logging.INFO, logger="ews.cycles.service"):
            run = (await client.post("/api/runs", headers=ADMIN)).json()

        records = [r for r in caplog.records if r.name == "ews.cycles.service"]
        assert records
        assert {record.run_id for record in records} == {run["id"]}  # type: ignore[attr-defined]
