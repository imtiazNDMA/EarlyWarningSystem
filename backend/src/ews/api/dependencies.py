"""Request-scoped dependencies shared by the routers."""

import secrets
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from ews.core.settings import Settings
from ews.cycles.events import RunEventLog, SessionFactory
from ews.sources.open_meteo import OpenMeteoForecastClient
from ews.sources.open_meteo_air_quality import OpenMeteoAirQualityClient


def get_app_settings(request: Request) -> Settings:
    """Return the settings the application was created with."""
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """Yield a database session for the duration of one request."""
    async with request.app.state.session_factory() as session:
        yield session


def get_session_factory(request: Request) -> SessionFactory:
    """Return the factory for sessions that are not tied to one request."""
    factory: SessionFactory = request.app.state.session_factory
    return factory


def get_forecast_client(request: Request) -> OpenMeteoForecastClient:
    """Return the forecast client opened at application start-up."""
    client: OpenMeteoForecastClient = request.app.state.forecast_client
    return client


def get_air_quality_client(request: Request) -> OpenMeteoAirQualityClient:
    """Return the air-quality client opened at application start-up."""
    client: OpenMeteoAirQualityClient = request.app.state.air_quality_client
    return client


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


def require_admin(
    settings: SettingsDep,
    x_admin_token: Annotated[str | None, Header()] = None,
) -> None:
    """Allow the request only if it carries the configured admin token."""
    if not settings.admin_token:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Admin actions are disabled: no admin token is configured.",
        )
    supplied = (x_admin_token or "").encode()
    if not secrets.compare_digest(supplied, settings.admin_token.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid admin token is required.",
        )


SessionDep = Annotated[AsyncSession, Depends(get_session)]
ForecastClientDep = Annotated[OpenMeteoForecastClient, Depends(get_forecast_client)]
SessionFactoryDep = Annotated[SessionFactory, Depends(get_session_factory)]


def get_run_event_log(open_session: SessionFactoryDep) -> RunEventLog:
    """Return the log that monitoring cycles record their events in."""
    return RunEventLog(open_session)


RunEventLogDep = Annotated[RunEventLog, Depends(get_run_event_log)]
AirQualityClientDep = Annotated[
    OpenMeteoAirQualityClient, Depends(get_air_quality_client)
]
