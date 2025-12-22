# Constants for Early Warnings Weather Dashboard

# Map display constants
MAP_DEFAULT_ZOOM = 5
MAP_DEFAULT_CENTER_LAT = 33.6844
MAP_DEFAULT_CENTER_LON = 73.0479
MAP_POPUP_MAX_WIDTH = 450

# Weather thresholds for marker colors
PRECIPITATION_LOW_THRESHOLD = 5  # mm
PRECIPITATION_MEDIUM_THRESHOLD = 20  # mm

# Validation limits
MIN_FORECAST_DAYS = 1
MAX_FORECAST_DAYS = 7

# File paths
WEATHER_DATA_DIR = "static/weatherdata"
BOUNDARY_DATA_DIR = "static/boundary"
DISTRICT_BOUNDARY_FILE = "static/boundary/pakistan_districts_fixed.geojson"

# Cache settings (in seconds)
DEFAULT_CACHE_TIME = 43200  # 12 hours

# API settings
DEFAULT_API_TIMEOUT = 30  # seconds
MAX_BULK_DISTRICTS = 100

# Error messages
ERROR_INVALID_PROVINCE = "Invalid province"
ERROR_INVALID_DISTRICT = "Invalid district"
ERROR_INVALID_FORECAST_DAYS = "Invalid forecast days"
ERROR_NO_FORECAST_DATA = "No forecast data available"
ERROR_NO_ALERT_DATA = "No alert generated yet"
ERROR_FAILED_TO_GENERATE = "Failed to generate. Please try again later."

# Weather code interpretations (Open-Meteo WMO codes)
WEATHER_CODE_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}
