"""Run a monitoring cycle and read the signals of the latest one."""

import asyncio
import dataclasses
import datetime as dt
import logging
from collections.abc import Sequence
from typing import TypedDict, cast

import httpx
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ews.air_quality.service import ingest_all_air_quality
from ews.alerts.service import Screened, apply_lifecycle
from ews.analyst.agent import analyse
from ews.analyst.assessment import HazardAssessment, assessed_signal
from ews.analyst.tools import Toolbox
from ews.core.db import create_engine, create_session_factory
from ews.core.logging import bound_run_id, configure_logging
from ews.core.settings import Settings, get_settings
from ews.cycles.events import RunEventLog, RunRecorder
from ews.cycles.models import HazardSignal, Run
from ews.districts.models import District
from ews.forecasts.service import ingest_all_forecasts
from ews.llm.gateway import LLMGateway
from ews.screening.rules import LEVELS, DailyValue, HazardRule, Signal, screen
from ews.screening.thresholds import load_rules
from ews.sources.errors import SourceError
from ews.sources.models import SourceSnapshot
from ews.sources.open_meteo import SOURCE as FORECAST_SOURCE
from ews.sources.open_meteo import OpenMeteoForecastClient, parse_daily
from ews.sources.open_meteo_air_quality import SOURCE as AIR_QUALITY_SOURCE
from ews.sources.open_meteo_air_quality import OpenMeteoAirQualityClient
from ews.sources.open_meteo_air_quality import parse_daily as parse_air_quality_daily

logger = logging.getLogger(__name__)

SIGNAL_METRIC_FIELDS = {
    "metric",
    "unit",
    "peak_value",
    "peak_date",
    "threshold",
    "days_over",
}


class CycleState(TypedDict, total=False):
    """How far a run has got; what the graph checkpoints after each node.

    The data a run works on (snapshots, screenings) stays out of the state: it
    lives in the run's database transaction, which a checkpoint cannot restore.
    """

    district_count: int
    signal_count: int
    analysed: int
    alert_actions: dict[str, int]


async def run_cycle(
    session: AsyncSession,
    client: OpenMeteoForecastClient,
    air_quality_client: OpenMeteoAirQualityClient,
    settings: Settings,
    trigger: str,
    events: RunEventLog,
    rules: Sequence[HazardRule] | None = None,
    gateway: LLMGateway | None = None,
    checkpointer: BaseCheckpointSaver[str] | None = None,
) -> Run:
    """Fetch forecasts for every district, screen them and bring alerts up to date.

    The run is recorded whatever happens. If a source fails, nothing fetched
    during the run is kept and the run is marked failed with the reason, so the
    previous successful run's signals stay current. The run's event log is kept
    either way.

    Args:
        session: Session to write with; this function commits
        client: Forecast client
        air_quality_client: Air-quality client
        settings: Application settings
        trigger: What started the run, such as ``manual``
        events: Log the run records its steps in
        rules: Hazard rules; defaults to the packaged thresholds
        gateway: Model access for the analyst; without it alerts follow
            screening alone
        checkpointer: Where the graph saves its progress; defaults to memory
            that lasts as long as the run

    Returns:
        The finished run, succeeded or failed
    """
    run = Run(trigger=trigger, status="running", started_at=dt.datetime.now(dt.UTC))
    session.add(run)
    await session.commit()
    run_id = run.id
    recorder = events.for_run(run_id)
    cycle = _Cycle(
        session,
        client,
        air_quality_client,
        gateway,
        settings,
        run_id,
        rules or load_rules(),
        recorder,
    )

    with bound_run_id(run_id):
        await recorder.emit("run_started", trigger=trigger)
        try:
            graph = cycle.graph(checkpointer or InMemorySaver())
            state = cast(
                CycleState,
                await graph.ainvoke({}, {"configurable": {"thread_id": str(run_id)}}),
            )
        except SourceError as error:
            await session.rollback()
            logger.exception("Run failed")
            await recorder.emit("error", message=str(error))
            return await _finish(session, recorder, run_id, "failed", error=str(error))

        return await _finish(
            session,
            recorder,
            run_id,
            "succeeded",
            district_count=state["district_count"],
            signal_count=state["signal_count"],
        )


class _Cycle:
    """One run's work, as the nodes of the monitoring graph.

    Ingest, screening and the alert lifecycle are plain code; only the analyst
    uses the model.
    """

    def __init__(
        self,
        session: AsyncSession,
        client: OpenMeteoForecastClient,
        air_quality_client: OpenMeteoAirQualityClient,
        gateway: LLMGateway | None,
        settings: Settings,
        run_id: int,
        rules: Sequence[HazardRule],
        recorder: RunRecorder,
    ) -> None:
        self._session = session
        self._client = client
        self._air_quality_client = air_quality_client
        self._gateway = gateway
        self._settings = settings
        self._run_id = run_id
        self._rules = rules
        self._recorder = recorder
        self._snapshots: list[SourceSnapshot] = []
        self._air_snapshots: list[SourceSnapshot] = []
        self._districts: dict[str, District] = {}
        self._screenings: list[Screened] = []

    def graph(
        self, checkpointer: BaseCheckpointSaver[str]
    ) -> CompiledStateGraph[CycleState, None, CycleState, CycleState]:
        """Ingest, screen, analyse what was flagged, then apply the lifecycle."""
        builder = StateGraph(CycleState)
        builder.add_node("ingest", self._ingest)
        builder.add_node("screen", self._screen)
        builder.add_node("analyse", self._analyse)
        builder.add_node("apply_lifecycle", self._apply_lifecycle)
        builder.add_edge(START, "ingest")
        builder.add_edge("ingest", "screen")
        builder.add_conditional_edges(
            "screen", self._after_screening, ["analyse", "apply_lifecycle"]
        )
        builder.add_edge("analyse", "apply_lifecycle")
        builder.add_edge("apply_lifecycle", END)
        return builder.compile(checkpointer=checkpointer)

    def _after_screening(self, state: CycleState) -> str:
        """Only a run with signals, a model and room to analyse visits the analyst."""
        wanted = (
            state["signal_count"] > 0
            and self._gateway is not None
            and self._settings.analyst_max_signals > 0
        )
        return "analyse" if wanted else "apply_lifecycle"

    async def _ingest(self, state: CycleState) -> CycleState:  # noqa: ARG002
        """Store a snapshot per district from each source."""
        settings = self._settings
        async with self._recorder.step("fetch_forecasts") as outcome:
            self._snapshots = await ingest_all_forecasts(
                self._session,
                self._client,
                settings.forecast_batch_size,
                settings.forecast_days,
            )
            outcome["snapshots"] = len(self._snapshots)
            await self._recorder.emit(
                "source_fetched", source=FORECAST_SOURCE, snapshots=len(self._snapshots)
            )

        try:
            async with self._recorder.step("fetch_air_quality") as outcome:
                self._air_snapshots = await self._ingest_air_quality()
                outcome["snapshots"] = len(self._air_snapshots)
                await self._recorder.emit(
                    "source_fetched",
                    source=AIR_QUALITY_SOURCE,
                    snapshots=len(self._air_snapshots),
                )
        except SourceError as error:
            logger.warning("Run continues without air quality: %s", error)
        return {"district_count": len(self._snapshots)}

    async def _ingest_air_quality(self) -> list[SourceSnapshot]:
        """Store an air-quality snapshot per district, or none of them on a failure."""
        savepoint = await self._session.begin_nested()
        try:
            snapshots = await ingest_all_air_quality(
                self._session,
                self._air_quality_client,
                self._settings.forecast_batch_size,
                self._settings.air_quality_forecast_days,
            )
        except SourceError:
            await savepoint.rollback()
            raise
        await savepoint.commit()
        return snapshots

    async def _screen(self, state: CycleState) -> CycleState:  # noqa: ARG002
        """Store a signal per threshold a district's values reached."""
        districts = await self._session.scalars(select(District))
        self._districts = {district.id: district for district in districts}
        air_metric = "pm2_5_mean_ug_m3"
        weather_rules = [rule for rule in self._rules if rule.metric != air_metric]
        air_quality_rules = [rule for rule in self._rules if rule.metric == air_metric]

        async with self._recorder.step("screen_weather") as outcome:
            for snapshot in self._snapshots:
                await self._screen_snapshot(
                    snapshot, parse_daily(snapshot.payload), weather_rules
                )
            weather_signals = self._signal_count()
            outcome["signals"] = weather_signals

        if self._air_snapshots:
            async with self._recorder.step("screen_air_quality") as outcome:
                for snapshot in self._air_snapshots:
                    await self._screen_snapshot(
                        snapshot,
                        parse_air_quality_daily(snapshot.payload),
                        air_quality_rules,
                    )
                outcome["signals"] = self._signal_count() - weather_signals
        return {"signal_count": self._signal_count()}

    def _signal_count(self) -> int:
        return sum(len(screened.signals) for screened in self._screenings)

    async def _screen_snapshot(
        self,
        snapshot: SourceSnapshot,
        days: Sequence[DailyValue],
        rules: Sequence[HazardRule],
    ) -> None:
        """Screen one district's snapshot and store what it raised."""
        province = self._districts[snapshot.district_id].province
        signals = screen(days, province, rules)
        for signal in signals:
            self._session.add(
                HazardSignal(
                    run_id=self._run_id,
                    district_id=snapshot.district_id,
                    snapshot_id=snapshot.id,
                    hazard=signal.hazard,
                    level=signal.level,
                    onset=signal.onset,
                    expires=signal.expires,
                    metrics=signal.model_dump(
                        mode="json", include=SIGNAL_METRIC_FIELDS
                    ),
                )
            )
            await self._recorder.emit(
                "signal_raised",
                district_id=snapshot.district_id,
                hazard=signal.hazard,
                level=signal.level,
                snapshot_id=snapshot.id,
            )
        self._screenings.append(
            Screened(
                snapshot.district_id,
                snapshot.id,
                days,
                signals,
                frozenset(rule.hazard for rule in rules),
            )
        )

    async def _analyse(self, state: CycleState) -> CycleState:  # noqa: ARG002
        """Have the analyst judge the most severe signals; alerts follow its view."""
        gateway = self._gateway
        if gateway is None:
            return {"analysed": 0}
        settings = self._settings
        # Most severe first, then a stable order
        flagged = sorted(
            (
                (index, signal)
                for index, screened in enumerate(self._screenings)
                for signal in screened.signals
            ),
            key=lambda item: (
                -LEVELS.index(item[1].level),
                self._screenings[item[0]].district_id,
                item[1].hazard,
            ),
        )
        chosen = flagged[: settings.analyst_max_signals]
        analysed = 0

        async with self._recorder.step("analyse_signals") as outcome:
            available = await gateway.availability(
                settings.health_check_timeout_seconds
            )
            if not available.available:
                logger.warning("Analysis skipped: %s", available.message)
                await self._recorder.emit(
                    "analysis_skipped", reason="model unavailable", signals=len(flagged)
                )
                chosen = []
            elif len(flagged) > len(chosen):
                await self._recorder.emit(
                    "analysis_skipped",
                    reason="over the per-run limit",
                    signals=len(flagged) - len(chosen),
                )

            for index, signal in chosen:
                screened = self._screenings[index]
                analysis = await analyse(
                    gateway,
                    Toolbox(
                        self._session,
                        self._districts,
                        self._screenings,
                        screened.district_id,
                    ),
                    self._districts[screened.district_id],
                    signal,
                    (screened.days[0].date, screened.days[-1].date),
                    self._recorder,
                    max_steps=settings.analyst_max_steps,
                    time_budget_seconds=settings.analyst_time_budget_seconds,
                )
                if analysis.assessment is not None:
                    self._screenings[index] = _judged(
                        screened, signal, analysis.assessment
                    )
                    analysed += 1
            outcome["analysed"] = analysed
        return {"analysed": analysed}

    async def _apply_lifecycle(self, state: CycleState) -> CycleState:  # noqa: ARG002
        """Issue, keep, replace or end alerts to match the screenings."""
        async with self._recorder.step("apply_alert_lifecycle") as outcome:
            actions = await apply_lifecycle(
                self._session, self._run_id, self._screenings
            )
            outcome["actions"] = dict(actions)
        logger.info("Alert actions: %s", dict(actions))
        return {"alert_actions": {str(action): n for action, n in actions.items()}}


def _judged(
    screened: Screened, signal: Signal, assessment: HazardAssessment
) -> Screened:
    """A screening with one of its signals replaced by the analyst's view of it.

    A dismissed signal is dropped; its hazard stays assessed, so an alert that
    was active for it is ended.
    """
    judged = assessed_signal(signal, assessment)
    others = [other for other in screened.signals if other.hazard != signal.hazard]
    if judged is None:
        return dataclasses.replace(screened, signals=others)
    return dataclasses.replace(
        screened,
        signals=[*others, judged],
        judgements={
            **screened.judgements,
            signal.hazard: (assessment.urgency, assessment.certainty),
        },
    )


async def _finish(
    session: AsyncSession,
    recorder: RunRecorder,
    run_id: int,
    status: str,
    district_count: int = 0,
    signal_count: int = 0,
    error: str | None = None,
) -> Run:
    """Record how a run ended."""
    # Logged before the status is committed, so a reader that sees the run
    # finished can rely on its event log being complete
    await recorder.emit(
        "run_finished",
        status=status,
        district_count=district_count,
        signal_count=signal_count,
    )
    run = await session.get_one(Run, run_id)
    run.status = status
    run.finished_at = dt.datetime.now(dt.UTC)
    run.district_count = district_count
    run.signal_count = signal_count
    run.error = error
    await session.commit()
    logger.info(
        "Run %s: %s districts, %s signals", status, district_count, signal_count
    )
    return run


async def list_runs(session: AsyncSession, limit: int) -> Sequence[Run]:
    """Runs, newest first."""
    statement = select(Run).order_by(Run.started_at.desc(), Run.id.desc()).limit(limit)
    return (await session.scalars(statement)).all()


async def latest_successful_run(session: AsyncSession) -> Run | None:
    """The most recent run that finished successfully."""
    statement = (
        select(Run)
        .where(Run.status == "succeeded")
        .order_by(Run.finished_at.desc())
        .limit(1)
    )
    return (await session.scalars(statement)).first()


async def signals_of(session: AsyncSession, run: Run) -> Sequence[HazardSignal]:
    """Signals raised by a run, in a stable order."""
    statement = (
        select(HazardSignal)
        .where(HazardSignal.run_id == run.id)
        .order_by(HazardSignal.district_id, HazardSignal.hazard)
    )
    return (await session.scalars(statement)).all()


async def _run_against_configured_database() -> None:
    """Run one cycle using the configured database and the real source."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    open_session = create_session_factory(engine)
    try:
        async with (
            httpx.AsyncClient(timeout=settings.source_timeout_seconds) as http,
            open_session() as session,
        ):
            client = OpenMeteoForecastClient(http, settings.open_meteo_forecast_url)
            air_quality_client = OpenMeteoAirQualityClient(
                http, settings.open_meteo_air_quality_url
            )
            await run_cycle(
                session,
                client,
                air_quality_client,
                settings,
                trigger="command",
                events=RunEventLog(open_session),
                gateway=LLMGateway.from_settings(settings, http),
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    configure_logging(get_settings().log_level)
    asyncio.run(_run_against_configured_database())
