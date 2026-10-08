"""Fetch, store and read district forecasts."""

import asyncio
import datetime as dt
import logging
from itertools import batched
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ews.core.db import create_engine, create_session_factory
from ews.core.settings import get_settings
from ews.districts.models import District
from ews.sources.errors import SourceError
from ews.sources.models import SourceSnapshot
from ews.sources.open_meteo import SOURCE, OpenMeteoForecastClient

logger = logging.getLogger(__name__)


async def store_snapshot(
    session: AsyncSession,
    district_id: str,
    source: str,
    payload: dict[str, Any],
    fetched_at: dt.datetime,
) -> SourceSnapshot:
    """Add a snapshot to the session; the caller commits."""
    snapshot = SourceSnapshot(
        district_id=district_id, source=source, payload=payload, fetched_at=fetched_at
    )
    session.add(snapshot)
    await session.flush()
    return snapshot


async def latest_snapshot(
    session: AsyncSession, district_id: str, source: str
) -> SourceSnapshot | None:
    """The most recently fetched snapshot for a district and source."""
    statement = (
        select(SourceSnapshot)
        .where(
            SourceSnapshot.district_id == district_id, SourceSnapshot.source == source
        )
        .order_by(SourceSnapshot.fetched_at.desc())
        .limit(1)
    )
    return (await session.scalars(statement)).first()


async def current_forecast_snapshot(
    session: AsyncSession,
    client: OpenMeteoForecastClient,
    district: District,
    max_age: dt.timedelta,
    days: int,
) -> tuple[SourceSnapshot, bool]:
    """Return a forecast snapshot for the district, fetching if needed.

    A stored snapshot younger than ``max_age`` is returned as it is. Otherwise a
    new one is fetched and stored. If the source is down, the stored snapshot is
    returned and flagged stale rather than failing the request.

    Returns:
        The snapshot and whether it is stale; the caller commits

    Raises:
        SourceError: If the source fails and nothing is stored for the district
    """
    now = dt.datetime.now(dt.UTC)
    stored = await latest_snapshot(session, district.id, SOURCE)
    if stored is not None and now - stored.fetched_at < max_age:
        return stored, False

    try:
        (forecast,) = await client.fetch([(district.lat, district.lon)], days)
    except SourceError:
        if stored is None:
            raise
        logger.warning(
            "Serving forecast for %s fetched at %s because the source failed",
            district.id,
            stored.fetched_at.isoformat(),
        )
        return stored, True

    fresh = await store_snapshot(session, district.id, SOURCE, forecast.payload, now)
    return fresh, False


async def ingest_all_forecasts(
    session: AsyncSession, client: OpenMeteoForecastClient, batch_size: int, days: int
) -> list[SourceSnapshot]:
    """Fetch and store a forecast for every district, several per request.

    Args:
        session: Session to write with; the caller commits
        client: Forecast client
        batch_size: Districts per request
        days: Number of forecast days

    Returns:
        The stored snapshots, one per district

    Raises:
        SourceError: If any batch fails; nothing is committed by this function
    """
    districts = (await session.scalars(select(District).order_by(District.id))).all()
    stored: list[SourceSnapshot] = []
    for batch in batched(districts, batch_size):
        forecasts = await client.fetch([(d.lat, d.lon) for d in batch], days)
        fetched_at = dt.datetime.now(dt.UTC)
        for district, forecast in zip(batch, forecasts, strict=True):
            stored.append(
                await store_snapshot(
                    session, district.id, SOURCE, forecast.payload, fetched_at
                )
            )
    return stored


async def _ingest_into_configured_database() -> None:
    """Ingest forecasts for every district using the configured database."""
    settings = get_settings()
    engine = create_engine(settings.database_url)
    try:
        async with (
            httpx.AsyncClient(timeout=settings.source_timeout_seconds) as http,
            create_session_factory(engine)() as session,
        ):
            client = OpenMeteoForecastClient(http, settings.open_meteo_forecast_url)
            stored = await ingest_all_forecasts(
                session, client, settings.forecast_batch_size, settings.forecast_days
            )
            await session.commit()
    finally:
        await engine.dispose()
    logger.info("Stored %s forecast snapshots", len(stored))


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_ingest_into_configured_database())
