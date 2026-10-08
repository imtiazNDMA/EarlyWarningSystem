"""Fetch, store and read district air-quality forecasts."""

import datetime as dt
from itertools import batched

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ews.districts.models import District
from ews.forecasts.service import latest_snapshot, store_snapshot
from ews.sources.models import SourceSnapshot
from ews.sources.open_meteo_air_quality import (
    SOURCE,
    OpenMeteoAirQualityClient,
    parse_daily,
)


async def ingest_all_air_quality(
    session: AsyncSession,
    client: OpenMeteoAirQualityClient,
    batch_size: int,
    days: int,
) -> list[SourceSnapshot]:
    """Fetch and store one PM2.5 forecast snapshot per district."""
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


async def latest_air_quality(
    session: AsyncSession, district_id: str
) -> tuple[SourceSnapshot, dt.date, float | None] | None:
    """Latest snapshot, first forecast date and PM2.5 for one district."""
    snapshot = await latest_snapshot(session, district_id, SOURCE)
    if snapshot is None:
        return None
    days = parse_daily(snapshot.payload)
    if not days:
        return None
    return snapshot, days[0].date, days[0].pm2_5_mean_ug_m3


async def latest_air_quality_all(
    session: AsyncSession,
) -> list[tuple[str, dt.date, dt.datetime, float | None]]:
    """Latest PM2.5 forecast value for every district that has one."""
    districts = (await session.scalars(select(District.id).order_by(District.id))).all()
    values = []
    for district_id in districts:
        current = await latest_air_quality(session, district_id)
        if current is not None:
            snapshot, date, value = current
            values.append((district_id, date, snapshot.fetched_at, value))
    return values
