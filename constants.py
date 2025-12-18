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
DISTRICT_BOUNDARY_FILE = "static/boundary/district.geojson"

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
