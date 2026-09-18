from unittest.mock import MagicMock

import pytest

from app import create_app
from repositories.memory import InMemoryRepository


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
def repository():
    """Create an isolated persistence adapter for each test."""
    return InMemoryRepository(cache_time=43200)


@pytest.fixture
def app(services, repository):
    """Create a test application backed by in-memory persistence."""
    return create_app(
        {
            "TESTING": True,
            "CORS_ORIGINS": ["http://localhost"],
        },
        services=services,
        repository=repository,
    )


@pytest.fixture
def client(app):
    """Create a Flask test client for an isolated application."""
    return app.test_client()
