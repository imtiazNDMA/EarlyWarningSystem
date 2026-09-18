"""
Health check and monitoring endpoints
"""

import logging

import requests
from flask import current_app, has_app_context
from pymongo import MongoClient

from config import Config

logger = logging.getLogger(__name__)


def check_mongodb_status():
    """Check that the configured MongoDB repository is reachable."""
    try:
        if has_app_context() and "repository" in current_app.extensions:
            current_app.extensions["repository"].ping()
        else:
            client = MongoClient(
                Config.MONGODB_URI,
                serverSelectionTimeoutMS=Config.MONGODB_TIMEOUT_MS,
            )
            client.admin.command("ping")
            client.close()
        return True, f"MongoDB database {Config.MONGODB_DATABASE} accessible"
    except Exception as e:
        logger.error(f"MongoDB status check failed: {e}")
        return False, f"MongoDB error: {str(e)}"


def check_lm_studio_status():
    """Check whether LM Studio exposes the configured model."""
    try:
        response = requests.get(f"{Config.LM_STUDIO_BASE_URL}/models", timeout=5)
        if response.status_code == 200:
            model_ids = [model.get("id") for model in response.json().get("data", [])]
            if Config.LM_STUDIO_MODEL in model_ids:
                return True, f"LM Studio model {Config.LM_STUDIO_MODEL} found"
            return False, f"LM Studio model {Config.LM_STUDIO_MODEL} NOT found"
        return False, f"LM Studio returned status {response.status_code}"
    except Exception as e:
        logger.error(f"LM Studio status check failed: {e}")
        return False, f"LM Studio error: {str(e)}"


def check_openmeteo_api():
    """Check if Open-Meteo API is accessible"""
    try:
        response = requests.get(
            Config.BASE_URL,
            params={
                "latitude": 33.6844,
                "longitude": 73.0479,
                "daily": "temperature_2m_max",
                "forecast_days": 1,
            },
            timeout=5,
        )
        if response.status_code == 200:
            return True, "Open-Meteo API accessible"
        else:
            return False, f"Open-Meteo API returned status {response.status_code}"
    except Exception as e:
        logger.error(f"Open-Meteo API check failed: {e}")
        return False, f"Open-Meteo API error: {str(e)}"


def check_file_system():
    """Check if file system is writable"""
    from pathlib import Path

    try:
        test_file = Path("static/weatherdata/.health_check")
        test_file.parent.mkdir(parents=True, exist_ok=True)
        test_file.write_text("test")
        test_file.unlink()
        return True, "File system writable"
    except Exception as e:
        logger.error(f"File system check failed: {e}")
        return False, f"File system error: {str(e)}"


def get_health_status():
    """
    Get overall health status of the application

    Returns:
        dict: Health status information
    """
    checks = {
        "mongodb_status": check_mongodb_status(),
        "lm_studio_status": check_lm_studio_status(),
        "openmeteo_api": check_openmeteo_api(),
        "file_system": check_file_system(),
    }

    all_healthy = all(status for status, _ in checks.values())

    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "checks": {
            name: {"status": "pass" if status else "fail", "message": message}
            for name, (status, message) in checks.items()
        },
    }
