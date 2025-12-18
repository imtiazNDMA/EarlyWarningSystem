import pytest
import json
import os
from app import app
from services.weather_service import WeatherService
from services.alert_service import AlertService

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_purge_cache_endpoint(client):
    """Test the cache purge endpoint"""
    # Create dummy cache files
    os.makedirs("static/weatherdata", exist_ok=True)
    with open("static/weatherdata/weather_1_Punjab_Lahore.json", "w") as f:
        f.write("{}")
    with open("static/weatherdata/alert_1_Punjab_Lahore.json", "w") as f:
        f.write("{}")
        
    # Test purge request
    response = client.post('/purge_cache', json={
        "province": "Punjab",
        "districts": ["Lahore"],
        "forecast_days": 1
    })
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert data["weather_purged"] >= 1
    assert data["alerts_purged"] >= 1
    
    # Verify files are gone
    assert not os.path.exists("static/weatherdata/weather_1_Punjab_Lahore.json")
    assert not os.path.exists("static/weatherdata/alert_1_Punjab_Lahore.json")

def test_purge_cache_all_districts(client):
    """Test purging all districts in a province"""
    # Create dummy cache files
    os.makedirs("static/weatherdata", exist_ok=True)
    with open("static/weatherdata/weather_1_Punjab_Lahore.json", "w") as f:
        f.write("{}")
    with open("static/weatherdata/weather_1_Punjab_Multan.json", "w") as f:
        f.write("{}")
        
    # Test purge request with no districts (implies all)
    response = client.post('/purge_cache', json={
        "province": "Punjab",
        "forecast_days": 1
    })
    
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["status"] == "success"
    assert data["weather_purged"] >= 2
    
    # Verify files are gone
    assert not os.path.exists("static/weatherdata/weather_1_Punjab_Lahore.json")
    assert not os.path.exists("static/weatherdata/weather_1_Punjab_Multan.json")
