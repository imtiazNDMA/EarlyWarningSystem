"""
Health check and monitoring endpoints
"""

import logging

import requests

from config import Config

logger = logging.getLogger(__name__)


def check_llm_status():
    """Check if the OpenAI-compatible LLM server is up and serving the model"""
    base_url = Config.LLM_BASE_URL.rstrip("/")
    try:
        response = requests.get(f"{base_url}/models", timeout=5)
        if response.status_code != 200:
            return False, f"LLM server returned status {response.status_code}"

        model_ids = [m.get("id") for m in response.json().get("data", [])]
        if Config.LLM_MODEL in model_ids:
            return True, f"LLM server reachable, model {Config.LLM_MODEL} loaded"

        available = ", ".join(model_ids) or "none"
        return (
            True,
            f"LLM server reachable, model {Config.LLM_MODEL} NOT loaded (available: {available})",
        )
    except Exception as e:
        logger.error(f"LLM status check failed: {e}")
        return False, f"LLM server unreachable: {e}"


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
        "llm_status": check_llm_status(),
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
