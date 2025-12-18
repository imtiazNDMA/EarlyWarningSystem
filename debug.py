#!/usr/bin/env python3
import os
import sys

print("=== Debugging Script ===")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")

# Test environment variables
print("\n=== Environment Variables ===")
from dotenv import load_dotenv

load_dotenv()

groq_key = os.getenv("GROQ_API_KEY")
mapbox_key = os.getenv("MAPBOX_TOKEN")

print(f"GROQ_API_KEY loaded: {bool(groq_key)}")
print(f"MAPBOX_TOKEN loaded: {bool(mapbox_key)}")

if groq_key:
    print(f"GROQ_API_KEY starts with: {groq_key[:10]}...")
if mapbox_key:
    print(f"MAPBOX_TOKEN starts with: {mapbox_key[:10]}...")

# Test config
print("\n=== Config Test ===")
try:
    from config import Config

    print("Config imported successfully")
    print(f"Config.GROQ_API_KEY: {bool(Config.GROQ_API_KEY)}")
    print(f"Config.MAPBOX_TOKEN: {bool(Config.MAPBOX_TOKEN)}")
except Exception as e:
    print(f"Config error: {e}")
    import traceback

    traceback.print_exc()

# Test models
print("\n=== Models Test ===")
try:
    from models import PROVINCES

    print("Models imported successfully")
    print(f"Number of provinces: {len(PROVINCES)}")
    print(f"Punjab districts: {len(PROVINCES.get('Punjab', {}))}")
except Exception as e:
    print(f"Models error: {e}")
    import traceback

    traceback.print_exc()

# Test services
print("\n=== Services Test ===")
try:
    from services.weather_service import WeatherService

    print("Weather service imported")
    weather_svc = WeatherService()
    print("Weather service initialized")
except Exception as e:
    print(f"Weather service error: {e}")
    import traceback

    traceback.print_exc()

try:
    from services.alert_service import AlertService

    print("Alert service imported")
    alert_svc = AlertService()
    print("Alert service initialized")
except Exception as e:
    print(f"Alert service error: {e}")
    import traceback

    traceback.print_exc()

print("\n=== All tests completed ===")
