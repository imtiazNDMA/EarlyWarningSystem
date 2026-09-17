import logging

from flask import Flask, current_app

from services.alert_service import AlertService
from services.map_service import MapService
from services.weather_service import WeatherService
from utils.health_check import get_health_status

logger = logging.getLogger(__name__)


def init_services(
    app: Flask,
    services: dict | None = None,
    config: dict | None = None,
) -> None:
    """Register application services, preserving explicitly injected adapters."""
    configured_services = dict(services or {})
    service_config = config or app.config
    if "weather" not in configured_services:
        configured_services["weather"] = WeatherService(service_config)
    if "alert" not in configured_services:
        configured_services["alert"] = AlertService(service_config)
    if "map" not in configured_services:
        configured_services["map"] = MapService(service_config)
    configured_services.setdefault("health", get_health_status)
    app.extensions["services"] = configured_services


def get_service(name: str):
    """Return a service registered for the current Flask application."""
    return current_app.extensions["services"][name]
