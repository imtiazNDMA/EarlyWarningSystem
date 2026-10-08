"""Run a monitoring cycle and read the signals of the latest one."""

import asyncio
import datetime as dt
import logging
from collections.abc import Sequence

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ews.core.db import create_engine, create_session_factory
from ews.core.settings import Settings, get_settings
from ews.cycles.models import HazardSignal, Run
from ews.districts.models import District
from ews.forecasts.service import ingest_all_forecasts
from ews.screening.rules import HazardRule, screen
from ews.screening.thresholds import load_rules
from ews.sources.errors import SourceError
from ews.sources.open_meteo import OpenMeteoForecastClient, parse_daily

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
    settings: Settings,
    trigger: str,
    rules: Sequence[HazardRule] | None = None,
) -> Run:
    """Fetch forecasts for every district, screen them and store the signals.

    The run is recorded whatever happens. If a source fails, nothing fetched
    during the run is kept and the run is marked failed with the reason, so the
    previous successful run's signals stay current.

    Args:
        session: Session to write with; this function commits
        client: Forecast client
        settings: Application settings
        trigger: What started the run, such as ``manual``
        rules: Hazard rules; defaults to the packaged thresholds

    Returns:
        The finished run, succeeded or failed
    """
    run = Run(trigger=trigger, status="running", started_at=dt.datetime.now(dt.UTC))
    session.add(run)
    await session.commit()
    run_id = run.id

    try:
        district_count, signal_count = await _ingest_and_screen(
            session, client, settings, run_id, rules or load_rules()
        )
    except SourceError as error:
        await session.rollback()
        logger.exception("Run %s failed", run_id)
        return await _finish(session, run_id, "failed", error=str(error))

    return await _finish(
        session,
        run_id,
        "succeeded",
        district_count=district_count,
        signal_count=signal_count,
    )


async def _ingest_and_screen(
    session: AsyncSession,
    client: OpenMeteoForecastClient,
    settings: Settings,
    run_id: int,
    rules: Sequence[HazardRule],
) -> tuple[int, int]:
    """Store a forecast per district and a signal per threshold reached."""
    snapshots = await ingest_all_forecasts(
        session, client, settings.forecast_batch_size, settings.forecast_days
    )
    rows = await session.execute(select(District.id, District.province))
    provinces = {district_id: province for district_id, province in rows}

    signal_count = 0
    for snapshot in snapshots:
        days = parse_daily(snapshot.payload)
        for signal in screen(days, provinces[snapshot.district_id], rules):
            session.add(
                HazardSignal(
                    run_id=run_id,
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
            signal_count += 1
    return len(snapshots), signal_count


async def _finish(
    session: AsyncSession,
    run_id: int,
    status: str,
    district_count: int = 0,
    signal_count: int = 0,
    error: str | None = None,
) -> Run:
    """Record how a run ended."""
    run = await session.get_one(Run, run_id)
    run.status = status
    run.finished_at = dt.datetime.now(dt.UTC)
    run.district_count = district_count
    run.signal_count = signal_count
    run.error = error
    await session.commit()
    logger.info(
        "Run %s %s: %s districts, %s signals",
        run_id,
        status,
        district_count,
        signal_count,
    )
    return run


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
    try:
        async with (
            httpx.AsyncClient(timeout=settings.source_timeout_seconds) as http,
            create_session_factory(engine)() as session,
        ):
            client = OpenMeteoForecastClient(http, settings.open_meteo_forecast_url)
            await run_cycle(session, client, settings, trigger="command")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_run_against_configured_database())
