"""Run a monitoring cycle and read the signals of the latest one."""

import asyncio
import datetime as dt
import logging
from collections.abc import Sequence

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ews.air_quality.service import ingest_all_air_quality
from ews.alerts.service import Screened, apply_lifecycle
from ews.core.db import create_engine, create_session_factory
from ews.core.logging import bound_run_id, configure_logging
from ews.core.settings import Settings, get_settings
from ews.cycles.events import RunEventLog, RunRecorder
from ews.cycles.models import HazardSignal, Run
from ews.districts.models import District
from ews.forecasts.service import ingest_all_forecasts
from ews.screening.rules import DailyValue, HazardRule, screen
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


async def run_cycle(
    session: AsyncSession,
    client: OpenMeteoForecastClient,
    air_quality_client: OpenMeteoAirQualityClient,
    settings: Settings,
    trigger: str,
    events: RunEventLog,
    rules: Sequence[HazardRule] | None = None,
) -> Run:
    """Fetch forecasts for every district, screen them and store the signals.

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

    Returns:
        The finished run, succeeded or failed
    """
    run = Run(trigger=trigger, status="running", started_at=dt.datetime.now(dt.UTC))
    session.add(run)
    await session.commit()
    run_id = run.id
    recorder = events.for_run(run_id)

    with bound_run_id(run_id):
        await recorder.emit("run_started", trigger=trigger)
        try:
            district_count, signal_count = await _ingest_and_screen(
                session,
                client,
                air_quality_client,
                settings,
                run_id,
                rules or load_rules(),
                recorder,
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
            district_count=district_count,
            signal_count=signal_count,
        )


async def _ingest_and_screen(
    session: AsyncSession,
    client: OpenMeteoForecastClient,
    air_quality_client: OpenMeteoAirQualityClient,
    settings: Settings,
    run_id: int,
    rules: Sequence[HazardRule],
    recorder: RunRecorder,
) -> tuple[int, int]:
    """Store a forecast per district and a signal per threshold reached."""
    weather_rules = [rule for rule in rules if rule.metric != "pm2_5_mean_ug_m3"]
    air_quality_rules = [rule for rule in rules if rule.metric == "pm2_5_mean_ug_m3"]
    rows = await session.execute(select(District.id, District.province))
    provinces = {district_id: province for district_id, province in rows}
    screenings: list[Screened] = []

    async with recorder.step("fetch_forecasts") as outcome:
        snapshots = await ingest_all_forecasts(
            session, client, settings.forecast_batch_size, settings.forecast_days
        )
        outcome["snapshots"] = len(snapshots)
        await recorder.emit(
            "source_fetched", source=FORECAST_SOURCE, snapshots=len(snapshots)
        )

    async with recorder.step("screen_weather") as outcome:
        for snapshot in snapshots:
            screenings.append(
                await _screen_snapshot(
                    session,
                    recorder,
                    run_id,
                    snapshot,
                    parse_daily(snapshot.payload),
                    provinces[snapshot.district_id],
                    weather_rules,
                )
            )
        outcome["signals"] = sum(len(screened.signals) for screened in screenings)

    try:
        async with recorder.step("fetch_air_quality") as outcome:
            air_snapshots = await _ingest_air_quality(
                session, air_quality_client, settings
            )
            outcome["snapshots"] = len(air_snapshots)
            await recorder.emit(
                "source_fetched",
                source=AIR_QUALITY_SOURCE,
                snapshots=len(air_snapshots),
            )
    except SourceError as error:
        logger.warning("Run continues without air quality: %s", error)
        air_snapshots = []

    if air_snapshots:
        async with recorder.step("screen_air_quality") as outcome:
            weather_signals = sum(len(screened.signals) for screened in screenings)
            for snapshot in air_snapshots:
                screenings.append(
                    await _screen_snapshot(
                        session,
                        recorder,
                        run_id,
                        snapshot,
                        parse_air_quality_daily(snapshot.payload),
                        provinces[snapshot.district_id],
                        air_quality_rules,
                    )
                )
            signal_count = sum(len(screened.signals) for screened in screenings)
            outcome["signals"] = signal_count - weather_signals

    async with recorder.step("apply_alert_lifecycle") as outcome:
        actions = await apply_lifecycle(session, run_id, screenings)
        outcome["actions"] = dict(actions)
    logger.info("Alert actions: %s", dict(actions))
    return len(snapshots), sum(len(screened.signals) for screened in screenings)


async def _ingest_air_quality(
    session: AsyncSession, client: OpenMeteoAirQualityClient, settings: Settings
) -> list[SourceSnapshot]:
    """Store an air-quality snapshot per district, or none of them on a failure."""
    savepoint = await session.begin_nested()
    try:
        snapshots = await ingest_all_air_quality(
            session,
            client,
            settings.forecast_batch_size,
            settings.air_quality_forecast_days,
        )
    except SourceError:
        await savepoint.rollback()
        raise
    await savepoint.commit()
    return snapshots


async def _screen_snapshot(
    session: AsyncSession,
    recorder: RunRecorder,
    run_id: int,
    snapshot: SourceSnapshot,
    days: Sequence[DailyValue],
    province: str,
    rules: Sequence[HazardRule],
) -> Screened:
    """Screen one district's snapshot and store a signal per threshold reached."""
    signals = screen(days, province, rules)
    for signal in signals:
        session.add(
            HazardSignal(
                run_id=run_id,
                district_id=snapshot.district_id,
                snapshot_id=snapshot.id,
                hazard=signal.hazard,
                level=signal.level,
                onset=signal.onset,
                expires=signal.expires,
                metrics=signal.model_dump(mode="json", include=SIGNAL_METRIC_FIELDS),
            )
        )
        await recorder.emit(
            "signal_raised",
            district_id=snapshot.district_id,
            hazard=signal.hazard,
            level=signal.level,
            snapshot_id=snapshot.id,
        )
    return Screened(
        snapshot.district_id,
        snapshot.id,
        days,
        signals,
        frozenset(rule.hazard for rule in rules),
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
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    configure_logging(get_settings().log_level)
    asyncio.run(_run_against_configured_database())
