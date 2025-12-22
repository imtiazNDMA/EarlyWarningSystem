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
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 16 * 1024 * 1024))  # 16MB default
    MAX_DISTRICTS_PER_REQUEST = int(os.getenv("MAX_DISTRICTS_PER_REQUEST", 100))

    # API Configuration
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1")
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    MAPBOX_TOKEN = os.getenv("MAPBOX_TOKEN")
    BASE_URL = os.getenv("BASE_URL", "https://api.open-meteo.com/v1/forecast")
    API_TIMEOUT = int(os.getenv("API_TIMEOUT", 30))
    TIMEZONE = os.getenv("TIMEZONE", "Asia/Karachi")

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
        if cls.ENV == "production" and cls.SECRET_KEY == "dev_secret_key_change_in_production":
            raise ValueError(
                "Cannot use default SECRET_KEY in production. Set a secure SECRET_KEY environment variable."
            )

        return True

    @classmethod
    def generate_secret_key(cls) -> str:
        """Generate a secure random secret key"""
        return secrets.token_hex(32)


Config.validate()
