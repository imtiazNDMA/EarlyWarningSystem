"""
Configuration management for Early Warnings Weather Dashboard
"""

import os
import secrets

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Known-insecure development default; rejected outright when ENV=production.
DEFAULT_SECRET_KEY = "dev_secret_key_change_in_production"  # noqa: S105


class Config:
    """Application configuration"""

    # Flask Configuration
    SECRET_KEY = os.getenv("SECRET_KEY", DEFAULT_SECRET_KEY)
    DEBUG = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    ENV = os.getenv("FLASK_ENV", "development")

    # Security Configuration
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))  # 16MB default
    MAX_DISTRICTS_PER_REQUEST = int(os.getenv("MAX_DISTRICTS_PER_REQUEST", 100))

    # API Configuration
    MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")
    BASE_URL = os.getenv("BASE_URL", "https://api.open-meteo.com/v1/forecast")
    API_TIMEOUT = int(os.getenv("API_TIMEOUT", 120))
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Karachi")

    # LLM Configuration (OpenAI-compatible server: LM Studio / vLLM / llama.cpp)
    # Legacy LM_STUDIO_* names are still honoured so existing .env files keep working.
    LLM_MODEL = os.getenv("LLM_MODEL") or os.getenv("LM_STUDIO_MODEL", "qwen/qwen3.8-27b")
    LLM_BASE_URL = os.getenv("LLM_BASE_URL") or os.getenv(
        "LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1"
    )
    # LM Studio and vLLM accept (and mostly ignore) any non-empty key,
    # but the OpenAI client refuses to build without one.
    LLM_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("LM_STUDIO_API_KEY") or "lm-studio"  # noqa: S105
    LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    LLM_TIMEOUT = int(os.getenv("LLM_TIMEOUT", "180"))
    LLM_MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "2"))

    # Application Configuration
    CACHE_TIME = int(os.getenv("CACHE_TIME", 43200))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "app.log")

    # CORS Configuration
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

    # Validate required configuration
    @classmethod
    def validate(cls):
        """Validate required configuration values"""
        required = ["MAPBOX_TOKEN"]
        missing = [key for key in required if not getattr(cls, key)]

        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        # Check for insecure secret key in production
        if cls.ENV == "production" and cls.SECRET_KEY == DEFAULT_SECRET_KEY:
            raise ValueError(
                "Cannot use default SECRET_KEY in production. Set a secure SECRET_KEY "
                "environment variable."
            )

        return True

    @classmethod
    def generate_secret_key(cls) -> str:
        """Generate a secure random secret key"""
        return secrets.token_hex(32)


Config.validate()
