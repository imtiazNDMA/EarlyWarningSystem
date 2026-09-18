from unittest.mock import MagicMock

import pytest

from app import create_app
from extensions import get_service
from repositories.memory import InMemoryRepository
from services import database


def build_services() -> dict[str, MagicMock]:
    """Create lightweight service doubles for application factory tests."""
    map_service = MagicMock()
    map_service.create_map.return_value = "<div>test map</div>"
    return {
        "weather": MagicMock(),
        "alert": MagicMock(),
        "map": map_service,
        "health": MagicMock(return_value={"status": "healthy", "checks": {}}),
    }


def create_test_app(repository=None, services=None):
    return create_app(
        {"TESTING": True, "CORS_ORIGINS": ["https://warnings.example"]},
        services=services or build_services(),
        repository=repository or InMemoryRepository(),
    )


def test_create_app_applies_config_and_initializes_repository():
    repository = MagicMock()

    app = create_test_app(repository=repository)

    assert app.config["TESTING"] is True
    assert app.extensions["repository"] is repository
    repository.initialize.assert_called_once_with()


def test_factory_apps_use_isolated_repositories():
    first_repository = InMemoryRepository()
    second_repository = InMemoryRepository()
    first_app = create_test_app(repository=first_repository)
    second_app = create_test_app(repository=second_repository)

    with first_app.app_context():
        assert database.get_repository() is first_repository
    with second_app.app_context():
        assert database.get_repository() is second_repository


def test_factory_apps_keep_service_registries_isolated():
    first_services = build_services()
    second_services = build_services()
    first_app = create_test_app(services=first_services)
    second_app = create_test_app(services=second_services)

    with first_app.app_context():
        assert get_service("weather") is first_services["weather"]
    with second_app.app_context():
        assert get_service("weather") is second_services["weather"]


def test_factory_fails_when_repository_cannot_initialize():
    repository = MagicMock()
    repository.initialize.side_effect = RuntimeError("MongoDB unavailable")

    with pytest.raises(RuntimeError, match="MongoDB unavailable"):
        create_test_app(repository=repository)


def test_routes_use_injected_services():
    services = build_services()
    services["weather"].get_bulk_weather_data.return_value = {
        "LAHORE": {"daily": {}}
    }
    app = create_test_app(services=services)

    response = app.test_client().post(
        "/generate_forecast",
        json={"province": "PUNJAB", "districts": ["LAHORE"], "forecast_days": 3},
    )

    assert response.status_code == 200
    services["weather"].get_bulk_weather_data.assert_called_once()


def test_health_route_uses_injected_check():
    services = build_services()
    app = create_test_app(services=services)

    response = app.test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "healthy"
    services["health"].assert_called_once_with()
