"""Typed application settings, read from EWS_* environment variables."""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration.

    Every field has a default suited to local development, so importing the
    application never fails because a variable is unset.
    """

    model_config = SettingsConfigDict(
        env_prefix="EWS_", env_file=".env", extra="ignore"
    )

    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "postgresql+asyncpg://ews:ews@localhost:5434/ews"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    health_check_timeout_seconds: float = 3.0
    # Required in the X-Admin-Token header to trigger work; admin actions
    # are disabled while this is unset
    admin_token: str | None = None

    # Forecast source
    open_meteo_forecast_url: str = "https://api.open-meteo.com/v1/forecast"
    source_timeout_seconds: float = 30.0
    forecast_days: int = 7
    # A stored forecast older than this is refreshed when it is next requested
    forecast_max_age_seconds: int = 3 * 60 * 60
    # Districts per request when fetching forecasts for all of them
    forecast_batch_size: int = 50


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loaded once."""
    return Settings()
