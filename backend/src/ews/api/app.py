"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from ews.api.routers import air_quality, alerts, cycles, districts, forecasts, health
from ews.core.db import create_engine, create_session_factory
from ews.core.logging import configure_logging
from ews.core.settings import Settings, get_settings
from ews.llm.gateway import LLMGateway
from ews.sources.open_meteo import OpenMeteoForecastClient
from ews.sources.open_meteo_air_quality import OpenMeteoAirQualityClient


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the database engine and HTTP client at start-up; close at shutdown."""
    settings: Settings = app.state.settings
    configure_logging(settings.log_level)

    engine = create_engine(settings.database_url)
    app.state.session_factory = create_session_factory(engine)
    http = httpx.AsyncClient(timeout=settings.source_timeout_seconds)
    app.state.forecast_client = OpenMeteoForecastClient(
        http, settings.open_meteo_forecast_url
    )
    app.state.air_quality_client = OpenMeteoAirQualityClient(
        http, settings.open_meteo_air_quality_url
    )
    # The gateway sets its own timeout on each request
    app.state.llm_gateway = LLMGateway.from_settings(settings, http)
    try:
        yield
    finally:
        await http.aclose()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Args:
        settings: Configuration to use; defaults to the environment's settings

    Returns:
        The configured application. Nothing connects to the database until the
        application starts.
    """
    app = FastAPI(title="Early Warning System API", lifespan=lifespan)
    app.state.settings = settings or get_settings()

    # The boundary GeoJSON is large and compresses well
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    app.include_router(health.router, prefix="/api")
    app.include_router(districts.router, prefix="/api")
    app.include_router(forecasts.router, prefix="/api")
    app.include_router(air_quality.router, prefix="/api")
    app.include_router(cycles.router, prefix="/api")
    app.include_router(alerts.router, prefix="/api")
    return app
