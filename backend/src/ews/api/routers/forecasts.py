"""District forecast endpoint."""

import datetime as dt

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from ews.api.dependencies import ForecastClientDep, SessionDep, SettingsDep
from ews.districts.models import District
from ews.forecasts.service import current_forecast_snapshot
from ews.sources.errors import SourceError
from ews.sources.open_meteo import DailyForecast, parse_daily

router = APIRouter(prefix="/districts", tags=["forecasts"])


class ForecastOut(BaseModel):
    """Daily forecast for a district, with where and when it came from."""

    district_id: str
    source: str
    fetched_at: dt.datetime
    # True when the source could not be reached and an older forecast is shown
    stale: bool
    days: list[DailyForecast]


@router.get(
    "/{district_id}/forecast",
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Unknown district"},
        status.HTTP_502_BAD_GATEWAY: {
            "description": "Forecast source unavailable and nothing stored"
        },
    },
)
async def district_forecast(
    district_id: str,
    session: SessionDep,
    settings: SettingsDep,
    client: ForecastClientDep,
) -> ForecastOut:
    """Latest daily forecast for a district, refreshed when it is too old."""
    district = await session.get(District, district_id)
    if district is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown district: {district_id}",
        )

    try:
        snapshot, stale = await current_forecast_snapshot(
            session,
            client,
            district,
            max_age=dt.timedelta(seconds=settings.forecast_max_age_seconds),
            days=settings.forecast_days,
        )
    except SourceError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(
                "The forecast source is unavailable and no earlier forecast is "
                "stored for this district."
            ),
        ) from error
    await session.commit()

    return ForecastOut(
        district_id=district.id,
        source=snapshot.source,
        fetched_at=snapshot.fetched_at,
        stale=stale,
        days=parse_daily(snapshot.payload),
    )
