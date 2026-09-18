"""
Configuration management for Early Warnings Weather Dashboard
"""

import os
import secrets

from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class Config:
    """Application configuration"""

    # Flask Configuration
    SECRET_KEY = os.getenv("SECRET_KEY", "dev_secret_key_change_in_production")
    DEBUG = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    ENV = os.getenv("FLASK_ENV", "development")

    # Security Configuration
    MAX_CONTENT_LENGTH = int(
        os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)
    )  # 16MB default
    MAX_DISTRICTS_PER_REQUEST = int(os.getenv("MAX_DISTRICTS_PER_REQUEST", 100))

    # API Configuration
    LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL", "zai-org/glm-4.7-flash")
    LM_STUDIO_BASE_URL = os.getenv(
        "LM_STUDIO_BASE_URL", "http://127.0.0.1:1234/v1"
    ).rstrip("/")
    LM_STUDIO_API_KEY = os.getenv("LM_STUDIO_API_KEY", "lm-studio")
    BASE_URL = os.getenv("BASE_URL", "https://api.open-meteo.com/v1/forecast")
    API_TIMEOUT = int(os.getenv("API_TIMEOUT", 120))
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Karachi")
    FORECAST_FRESH_SECONDS = int(os.getenv("FORECAST_FRESH_SECONDS", 10800))
    FORECAST_STALE_SECONDS = int(os.getenv("FORECAST_STALE_SECONDS", 21600))

    # Application Configuration
    CACHE_TIME = int(os.getenv("CACHE_TIME", 43200))
    MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://127.0.0.1:27017")
    MONGODB_DATABASE = os.getenv("MONGODB_DATABASE", "early_warnings")
    MONGODB_TIMEOUT_MS = int(os.getenv("MONGODB_TIMEOUT_MS", 5000))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE = os.getenv("LOG_FILE", "app.log")

    # CORS Configuration
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

    # Validate required configuration
    @classmethod
    def validate(cls):
        """Validate required configuration values"""
        required = []
        missing = [key for key in required if not getattr(cls, key)]

        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}"
            )

        # Check for insecure secret key in production
        if (
            cls.ENV == "production"
            and cls.SECRET_KEY == "dev_secret_key_change_in_production"
        ):
            raise ValueError(
                "Cannot use default SECRET_KEY in production. Set a secure SECRET_KEY environment variable."
            )

        return True

    @classmethod
    def generate_secret_key(cls) -> str:
        """Generate a secure random secret key"""
        return secrets.token_hex(32)
