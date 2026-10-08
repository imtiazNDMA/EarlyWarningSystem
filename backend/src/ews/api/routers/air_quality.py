"""Latest district PM2.5 forecasts."""

import datetime as dt

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ews.air_quality.service import latest_air_quality, latest_air_quality_all
from ews.api.dependencies import SessionDep

router = APIRouter(tags=["air quality"])


class AirQualityOut(BaseModel):
    """Latest daily mean PM2.5 forecast for a district."""

    district_id: str
    date: dt.date
    pm2_5_mean_ug_m3: float | None
    fetched_at: dt.datetime


def _out(
    district_id: str, fetched_at: dt.datetime, value: float | None, date: dt.date
) -> AirQualityOut:
    return AirQualityOut(
        district_id=district_id,
        date=date,
        pm2_5_mean_ug_m3=value,
        fetched_at=fetched_at,
    )


@router.get("/air-quality")
async def all_air_quality(session: SessionDep) -> list[AirQualityOut]:
    """Latest PM2.5 value for every district with stored air-quality data."""
    rows = await latest_air_quality_all(session)
    return [
        _out(district_id, fetched_at, value, date)
        for district_id, date, fetched_at, value in rows
    ]


@router.get(
    "/districts/{district_id}/air-quality",
    responses={status.HTTP_404_NOT_FOUND: {"description": "No air-quality data"}},
)
async def district_air_quality(district_id: str, session: SessionDep) -> AirQualityOut:
    """Latest PM2.5 forecast for one district."""
    current = await latest_air_quality(session, district_id)
    if current is None:
        raise HTTPException(status_code=404, detail="No air-quality data is available.")
    snapshot, date, value = current
    return _out(district_id, snapshot.fetched_at, value, date)
