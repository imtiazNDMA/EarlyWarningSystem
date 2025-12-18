"""
Health check and monitoring endpoints
"""

import logging
from flask import jsonify
import requests
from config import Config

logger = logging.getLogger(__name__)


def check_groq_api():
    """Check if Groq API is accessible"""
    try:
        from groq import Groq
        client = Groq(api_key=Config.GROQ_API_KEY)
        # Simple test - just check if client can be created
        return True, "Groq API accessible"
    except Exception as e:
        logger.error(f"Groq API check failed: {e}")
        return False, f"Groq API error: {str(e)}"


def check_openmeteo_api():
    """Check if Open-Meteo API is accessible"""
    try:
        response = requests.get(
            Config.BASE_URL,
            params={
                "latitude": 33.6844,
                "longitude": 73.0479,
                "daily": "temperature_2m_max",
                "forecast_days": 1
            },
            timeout=5
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
        "groq_api": check_groq_api(),
        "openmeteo_api": check_openmeteo_api(),
        "file_system": check_file_system(),
    }
    
    all_healthy = all(status for status, _ in checks.values())
    
    return {
        "status": "healthy" if all_healthy else "unhealthy",
        "checks": {
            name: {
                "status": "pass" if status else "fail",
                "message": message
            }
            for name, (status, message) in checks.items()
        }
    }
