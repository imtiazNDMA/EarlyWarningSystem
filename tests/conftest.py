from unittest.mock import MagicMock

import pytest

from app import create_app


@pytest.fixture
def services() -> dict[str, MagicMock]:
    """Provide isolated application dependencies for endpoint tests."""
    map_service = MagicMock()
    map_service.create_map.return_value = "<div>test map</div>"

    return {
        "weather": MagicMock(),
        "alert": MagicMock(),
        "map": map_service,
        "health": MagicMock(return_value={"status": "healthy", "checks": {}}),
    }


@pytest.fixture
def app(tmp_path, services):
    """Create a test application backed by a temporary database."""
    return create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(tmp_path / "weather.db"),
            "CORS_ORIGINS": ["http://localhost"],
        },
        services=services,
    )


@pytest.fixture
def client(app):
    """Create a Flask test client for an isolated application."""
    return app.test_client()
