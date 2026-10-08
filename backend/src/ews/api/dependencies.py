"""Request-scoped dependencies shared by the routers."""

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from ews.core.settings import Settings
from ews.sources.open_meteo import OpenMeteoForecastClient


def get_app_settings(request: Request) -> Settings:
    """Return the settings the application was created with."""
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a database session for the duration of one request."""
    async with request.app.state.session_factory() as session:
        yield session


def get_forecast_client(request: Request) -> OpenMeteoForecastClient:
    """Return the forecast client opened at application start-up."""
    client: OpenMeteoForecastClient = request.app.state.forecast_client
    return client


SettingsDep = Annotated[Settings, Depends(get_app_settings)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
ForecastClientDep = Annotated[OpenMeteoForecastClient, Depends(get_forecast_client)]
