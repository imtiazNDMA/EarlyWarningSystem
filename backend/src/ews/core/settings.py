"""Typed application settings, read from EWS_* environment variables."""

from functools import lru_cache
from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
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
    open_meteo_air_quality_url: str = (
        "https://air-quality-api.open-meteo.com/v1/air-quality"
    )
    source_timeout_seconds: float = 30.0
    forecast_days: int = 7
    air_quality_forecast_days: int = 5
    # A stored forecast older than this is refreshed when it is next requested
    forecast_max_age_seconds: int = 3 * 60 * 60
    # Districts per request when fetching forecasts for all of them
    forecast_batch_size: int = 50

    # Language model. Unset values take the provider's default in ews.llm.gateway
    llm_provider: Literal["lm_studio", "groq"] = "lm_studio"
    llm_base_url: str | None = None
    # LM Studio answers with whichever model is loaded when this is unset
    llm_model: str | None = None
    # Required for Groq; LM Studio ignores it
    llm_api_key: SecretStr | None = None
    llm_temperature: float = Field(default=0.2, ge=0)
    # Budget for one model request, including waits on a rate limit
    llm_timeout_seconds: float = Field(default=120.0, gt=0)
    llm_max_concurrency: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def groq_needs_a_key(self) -> Self:
        key = self.llm_api_key.get_secret_value() if self.llm_api_key else ""
        if self.llm_provider == "groq" and not key:
            raise ValueError(
                "EWS_LLM_API_KEY is required when EWS_LLM_PROVIDER is groq"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings, loaded once."""
    return Settings()
