import pytest
import json
from unittest.mock import patch
from app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@patch("services.database.purge_cache_db")
def test_purge_cache_endpoint(mock_purge, client):
    """Test the cache purge endpoint"""
    mock_purge.return_value = 2


    response = client.post(
        "/purge_cache",
        json={"province": "PUNJAB", "districts": ["LAHORE"], "forecast_days": 1},
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert "purged_count" in data
    assert data["purged_count"] == 2
    mock_purge.assert_called_once()


@patch("services.database.purge_cache_db")
def test_purge_cache_all_districts(mock_purge, client):
    """Test purging all districts in a province"""
    mock_purge.return_value = 5

    response = client.post("/purge_cache", json={"province": "PUNJAB", "forecast_days": 1})

    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert "purged_count" in data
    assert data["purged_count"] == 5
    mock_purge.assert_called_once()
