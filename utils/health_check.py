"""
Health check and monitoring endpoints
"""

import logging
from flask import jsonify
import requests
from config import Config

logger = logging.getLogger(__name__)


def check_ollama_status():
    """Check if Ollama is accessible and model is loaded"""
    try:
        response = requests.get(f"{Config.OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            models = response.json().get("models", [])
            model_names = [m.get("name") for m in models]
            if any(Config.OLLAMA_MODEL in name for name in model_names):
                return True, f"Ollama accessible, model {Config.OLLAMA_MODEL} found"
            else:
                return (
                    True,
                    f"Ollama accessible, but model {Config.OLLAMA_MODEL} NOT found",
                )
        else:
            return False, f"Ollama returned status {response.status_code}"
    except Exception as e:
        logger.error(f"Ollama status check failed: {e}")
        return False, f"Ollama error: {str(e)}"


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
    import os

    try:
        test_file = "static/weatherdata/.health_check"
        os.makedirs("static/weatherdata", exist_ok=True)
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
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
        "ollama_status": check_ollama_status(),
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
