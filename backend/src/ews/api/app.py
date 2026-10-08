"""FastAPI application factory."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from ews.api.routers import districts, health
from ews.core.db import create_engine, create_session_factory
from ews.core.logging import configure_logging
from ews.core.settings import Settings, get_settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Open the database engine at start-up and dispose it at shutdown."""
    settings: Settings = app.state.settings
    configure_logging(settings.log_level)

    engine = create_engine(settings.database_url)
    app.state.session_factory = create_session_factory(engine)
    try:
        yield
    finally:
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
    return app
