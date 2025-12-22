import sys
import os
import json
import sqlite3
import logging
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath("d:/projects/EarlyWarningSystem"))

from services.map_service import MapService
import database

# Configure logging
logging.basicConfig(level=logging.DEBUG)


def test_integration():
    print("Starting integration test...")

    # 1. Setup Data in DB
    province = "IntegrationTestProv"
    district = "TestDistrict"
    days = 1

    # Clear matching data first
    with sqlite3.connect("weather.db") as conn:
        conn.execute("DELETE FROM alerts WHERE province=?", (province,))
        conn.execute("DELETE FROM weather_cache WHERE cache_key LIKE ?", (f"%{province}%",))
        conn.commit()

    # Insert Alert
    alert_text = "CRITICAL INTEGRATION TEST ALERT"
    database.save_alert(province, district, days, alert_text)
    print(f"Saved alert: {alert_text}")

    # Verify DB direct
    saved_alert = database.get_alert(province, district, days)
    print(f"Direct DB verify: {saved_alert}")
    if saved_alert != alert_text:
        print("CRITICAL: DB Save failed!")
        exit(1)

    # Insert Weather
    weather_data = {
        "daily": {
            "time": [datetime.now().strftime("%Y-%m-%d")],
            "temperature_2m_max": [35.0],
            "temperature_2m_min": [25.0],
            "precipitation_sum": [15.0],
            "precipitation_probability_max": [80],
            "windspeed_10m_max": [20.0],
            "windgusts_10m_max": [30.0],
            "snowfall_sum": [0.0],
            "uv_index_max": [8.0],
        },
        "current_weather": {"temperature": 30.0, "windspeed": 10.0},
    }
    # Key format from WeatherService: weather_{days}_{province}_{sanitized_district}
    # sanitize_filename("TestDistrict") -> "TestDistrict"
    cache_key = f"weather_{days}_{province}_{district}"
    database.set_raw_weather_cache(cache_key, weather_data)
    print(f"Saved weather data for key: {cache_key}")

    # 2. Test MapService
    map_service = MapService()
    # Mock lookup
    map_service._district_to_province[district] = province

    locations = {district: (33.6, 73.0)}

    print("Generating map...")
    map_html = map_service.create_map(locations, forecast_days=days)

    # 3. Assertions
    if alert_text in map_html:
        print("SUCCESS: Alert text found in Map HTML.")
    else:
        print("FAILURE: Alert text NOT found in Map HTML.")
        # print(map_html[:1000]) # Debug
        exit(1)

    if "35.0" in map_html:  # Max temp
        print("SUCCESS: Weather data (Max Temp) found in Map HTML.")
    else:
        print("FAILURE: Weather data NOT found in Map HTML.")
        exit(1)

    print("Integration test passed!")


if __name__ == "__main__":
    test_integration()
