import sqlite3
from unittest.mock import MagicMock

import pytest

from app import create_app
from extensions import get_service
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


def test_create_app_applies_config_and_initializes_database(tmp_path):
    database_path = tmp_path / "factory.db"

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(database_path),
            "CORS_ORIGINS": ["https://warnings.example"],
        },
        services=build_services(),
    )

    assert app.config["TESTING"] is True
    assert app.config["DATABASE_PATH"] == str(database_path)
    assert database_path.exists()

    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert {"weather_cache", "alerts"}.issubset(tables)


def test_factory_apps_use_isolated_database_paths(tmp_path):
    first_path = tmp_path / "first.db"
    second_path = tmp_path / "second.db"

    first_app = create_app(
        {"TESTING": True, "DATABASE_PATH": str(first_path)},
        services=build_services(),
    )
    second_app = create_app(
        {"TESTING": True, "DATABASE_PATH": str(second_path)},
        services=build_services(),
    )

    with first_app.app_context():
        assert first_app.config["DATABASE_PATH"] == str(first_path)
    with second_app.app_context():
        assert second_app.config["DATABASE_PATH"] == str(second_path)

    assert first_path.exists()
    assert second_path.exists()
    assert first_path != second_path


def test_factory_apps_keep_service_registries_isolated(tmp_path):
    first_services = build_services()
    second_services = build_services()
    first_app = create_app(
        {"TESTING": True, "DATABASE_PATH": str(tmp_path / "first-services.db")},
        services=first_services,
    )
    second_app = create_app(
        {"TESTING": True, "DATABASE_PATH": str(tmp_path / "second-services.db")},
        services=second_services,
    )

    with first_app.app_context():
        assert get_service("weather") is first_services["weather"]
    with second_app.app_context():
        assert get_service("weather") is second_services["weather"]


def test_background_app_context_uses_configured_database(tmp_path):
    database_path = tmp_path / "background.db"
    app = create_app(
        {"TESTING": True, "DATABASE_PATH": str(database_path)},
        services=build_services(),
    )

    with app.app_context():
        assert database.get_database_path() == str(database_path)


def test_factory_fails_when_database_cannot_be_initialized(tmp_path):
    invalid_path = tmp_path / "missing" / "weather.db"

    with pytest.raises(sqlite3.OperationalError):
        create_app(
            {"TESTING": True, "DATABASE_PATH": str(invalid_path)},
            services=build_services(),
        )


def test_routes_use_injected_services(tmp_path):
    services = build_services()
    services["weather"].get_bulk_weather_data.return_value = {
        "LAHORE": {"daily": {}}
    }
    app = create_app(
        {"TESTING": True, "DATABASE_PATH": str(tmp_path / "routes.db")},
        services=services,
    )

    response = app.test_client().post(
        "/generate_forecast",
        json={"province": "PUNJAB", "districts": ["LAHORE"], "forecast_days": 3},
    )

    assert response.status_code == 200
    services["weather"].get_bulk_weather_data.assert_called_once()


def test_health_route_uses_injected_check(tmp_path):
    services = build_services()
    app = create_app(
        {"TESTING": True, "DATABASE_PATH": str(tmp_path / "health.db")},
        services=services,
    )

    response = app.test_client().get("/health")

    assert response.status_code == 200
    assert response.get_json()["status"] == "healthy"
    services["health"].assert_called_once_with()
