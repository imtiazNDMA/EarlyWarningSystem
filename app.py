from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import pandas as pd
import json
import logging
import os

# Import configuration and services
from config import Config
from models import PROVINCES
from constants import ERROR_INVALID_PROVINCE, ERROR_INVALID_DISTRICT, ERROR_INVALID_FORECAST_DAYS
from services.weather_service import WeatherService
from services.alert_service import AlertService
from services.map_service import MapService
from health import get_health_status
from utils.validation import (
    validate_api_request_data,
    validate_province,
    validate_district,
    validate_forecast_days,
    sanitize_filename,
)

# Configure logging
os.makedirs(os.path.dirname(Config.LOG_FILE) if os.path.dirname(Config.LOG_FILE) else ".", exist_ok=True)
logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler(Config.LOG_FILE), logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config["SECRET_KEY"] = Config.SECRET_KEY
app.config["MAX_CONTENT_LENGTH"] = Config.MAX_CONTENT_LENGTH

# Enable CORS with proper configuration
if Config.CORS_ORIGINS == ["*"]:
    logger.warning("CORS is configured to allow all origins. This is not recommended for production.")
    CORS(app)
else:
    CORS(app, origins=Config.CORS_ORIGINS)

# Initialize services
weather_service = WeatherService()
alert_service = AlertService()
map_service = MapService()


# Map creation is now handled by MapService


# AJAX endpoint to get forecast for a district
@app.route("/get_forecast/<province>/<district>/<int:days>")
def get_forecast(province, district, days):
    """
    Get weather forecast for a specific district.

    Args:
        province: Province name
        district: District name
        days: Number of forecast days

    Returns:
        JSON response with forecast data or error
    """
    # Validate parameters
    if not validate_province(province):
        logger.warning(f"Invalid province in forecast request: {province}")
        return jsonify({"error": "Invalid province"}), 400

    if not validate_district(district):
        logger.warning(f"Invalid district in forecast request: {district}")
        return jsonify({"error": "Invalid district"}), 400

    if not validate_forecast_days(days):
        logger.warning(f"Invalid forecast days in request: {days}")
        return jsonify({"error": "Invalid forecast days"}), 400

    data = weather_service.get_weather_forecast(province, district, days)
    if not data:
        return jsonify(
            {
                "district": district,
                "forecast": [],
                "error": "No forecast data available",
            }
        )

    # Convert to DataFrame format for display
    daily = data["daily"]
    df = pd.DataFrame(
        {
            "Date": daily["time"],
            "Max Temp (°C)": daily["temperature_2m_max"],
            "Min Temp (°C)": daily["temperature_2m_min"],
            "Precipitation (mm)": daily["precipitation_sum"],
            "Precipitation Chance (%)": daily["precipitation_probability_max"],
            "Wind Speed (km/h)": daily["windspeed_10m_max"],
            "Wind Gusts (km/h)": daily["windgusts_10m_max"],
            "Weather Code": daily["weathercode"],
            "Snowfall (cm)": daily["snowfall_sum"],
            "UV Index Max": daily["uv_index_max"],
        }
    )

    return jsonify(
        {
            "district": district,
            "forecast": df.to_dict("records") if not df.empty else [],
            "days": days,
        }
    )


@app.route("/get_alert/<province>/<district>/<int:days>")
def get_alert(province, district, days):
    # Validate parameters
    if not validate_province(province):
        logger.warning(f"Invalid province in alert request: {province}")
        return jsonify({"error": "Invalid province"}), 400

    if not validate_district(district):
        logger.warning(f"Invalid district in alert request: {district}")
        return jsonify({"error": "Invalid district"}), 400

    if not validate_forecast_days(days):
        logger.warning(f"Invalid forecast days in alert request: {days}")
        return jsonify({"error": "Invalid forecast days"}), 400

    data = alert_service.get_alert(province, district, days)
    if not data:
        return jsonify({"district": district, "alert": "⚠️ No alert generated yet."})
    return jsonify(data)


@app.route("/get_all_alerts/<int:days>")
def get_all_alerts(days):
    """Return all alerts for all provinces and districts"""
    # Validate forecast days
    if not validate_forecast_days(days):
        logger.warning(f"Invalid forecast days in get all alerts request: {days}")
        return jsonify({"error": "Invalid forecast days"}), 400
    all_alerts = {}

    for province in PROVINCES.keys():
        province_alerts = {}
        for district in PROVINCES[province].keys():
            filename = (
                f"static/weatherdata/alert_{days}_{province}_"
                f"{sanitize_filename(district)}.json"
            )
            try:
                with open(filename, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    province_alerts[district] = data.get(
                        "alert", "⚠️ No alert available"
                    )
            except FileNotFoundError:
                province_alerts[district] = "⚠️ No alert generated yet."

        all_alerts[province] = province_alerts

    return jsonify(all_alerts)


# AJAX endpoint to generate forecasts
@app.route("/generate_forecast", methods=["POST"])
def generate_forecast():
    """
    Generate weather forecasts for selected districts.

    Expects JSON payload with province, districts, and forecast_days.

    Returns:
        JSON response with success/error status
    """
    try:
        data = request.get_json()
        if not data:
            return (
                jsonify({"status": "error", "message": "Invalid JSON data"}),
                400,
            )

        # Validate input data
        is_valid, error_msg = validate_api_request_data(data)
        if not is_valid:
            logger.warning(f"Invalid forecast request: {error_msg}")
            return jsonify({"status": "error", "message": error_msg}), 400

        province = data.get("province", "Punjab")
        districts = data.get("districts", [])
        forecast_days = data.get("forecast_days", 1)
        
        # Validate district count
        if districts and len(districts) > Config.MAX_DISTRICTS_PER_REQUEST:
            return jsonify({
                "status": "error",
                "message": f"Too many districts. Maximum {Config.MAX_DISTRICTS_PER_REQUEST} allowed per request."
            }), 400

    except Exception as e:
        logger.error(f"Error parsing forecast request: {e}")
        return (
            jsonify({"status": "error", "message": "Invalid request format"}),
            400,
        )

    # Get selected districts or all districts in province
    if not districts:
        districts_to_fetch = PROVINCES[province]
    else:
        districts_to_fetch = {
            d: PROVINCES[province][d] for d in districts if d in PROVINCES[province]
        }

    weather_data = weather_service.get_bulk_weather_data(
        province, districts_to_fetch, forecast_days
    )

    # Return success status
    return jsonify(
        {
            "status": "success",
            "message": f"Forecast generated for {len(weather_data)} districts",
            "province": province,
            "forecast_days": forecast_days,
        }
    )


# AJAX endpoint to generate alerts
# AJAX endpoint to generate alerts
@app.route("/generate_alerts", methods=["POST"])
def generate_alerts():
    try:
        data = request.get_json()
        if not data:
            return (
                jsonify({"status": "error", "message": "Invalid JSON data"}),
                400,
            )

        # Validate input data
        is_valid, error_msg = validate_api_request_data(data)
        if not is_valid:
            logger.warning(f"Invalid alerts request: {error_msg}")
            return jsonify({"status": "error", "message": error_msg}), 400

        province = data.get("province", "Punjab")
        forecast_days = data.get("forecast_days", 1)

    except Exception as e:
        logger.error(f"Error parsing alerts request: {e}")
        return (
            jsonify({"status": "error", "message": "Invalid request format"}),
            400,
        )

    try:
        # First, ensure we have forecasts for all districts by generating them
        districts_to_fetch = PROVINCES[province]
        weather_data = weather_service.get_bulk_weather_data(
            province, districts_to_fetch, forecast_days
        )

        if not weather_data:
            return jsonify(
                {
                    "status": "error",
                    "message": (
                        "Failed to fetch weather data. Please check your "
                        "internet connection and try again."
                    ),
                }
            )

        # Convert to DataFrames
        forecasts = {}
        for d, data in weather_data.items():
            daily = data["daily"]
            # Ensure data is in list format for DataFrame
            df_data = {}
            for key in [
                "time",
                "temperature_2m_max",
                "temperature_2m_min",
                "precipitation_sum",
                "precipitation_probability_max",
                "windspeed_10m_max",
                "windgusts_10m_max",
                "weathercode",
                "snowfall_sum",
                "uv_index_max",
            ]:
                value = daily.get(key)
                if not isinstance(value, list):
                    value = [value]
                df_data[key] = value

            df = pd.DataFrame(
                {
                    "Date": df_data["time"],
                    "Max Temp (°C)": df_data["temperature_2m_max"],
                    "Min Temp (°C)": df_data["temperature_2m_min"],
                    "Precipitation (mm)": df_data["precipitation_sum"],
                    "Precipitation Chance (%)": df_data[
                        "precipitation_probability_max"
                    ],
                    "Wind Speed (km/h)": df_data["windspeed_10m_max"],
                    "Wind Gusts (km/h)": df_data["windgusts_10m_max"],
                    "Weather Code": df_data["weathercode"],
                    "Snowfall (cm)": df_data["snowfall_sum"],
                    "UV Index Max": df_data["uv_index_max"],
                }
            )
            forecasts[d] = df

        # Generate alerts using AlertService
        alert_text = alert_service.generate_alert(province, forecasts)
        alerts = alert_service.parse_district_alerts(alert_text)

        # Save district-level alerts
        alert_service.save_district_alerts(alerts, forecast_days, province)

        return jsonify(
            {
                "status": "success",
                "message": f"Alerts generated for {province}",
                "alert_text": alert_text,
                "province": province,
            }
        )

    except Exception as e:
        logger.error(f"Error in generate_alerts: {e}", exc_info=True)
        return jsonify(
            {
                "status": "error",
                "message": "Failed to generate alerts. Please try again later.",
            }
        )


@app.route("/", methods=["GET", "POST"])
def index():
    """
    Main dashboard route.

    Handles both GET (display form) and POST (process form submission).
    Renders the main template with map and form controls.

    Returns:
        Rendered HTML template
    """
    province = "Punjab"
    selected_districts = []
    forecast_days = 1

    if request.method == "POST":
        province = request.form.get("province", province)
        selected_districts = request.form.getlist("districts")
        forecast_days = int(request.form.get("forecast_days", 1))

    # Always create map with all districts
    all_districts = {
        district: coords
        for province_districts in PROVINCES.values()
        for district, coords in province_districts.items()
    }

    # Create basic map with current forecast days
    map_html = map_service.create_map(all_districts, forecast_days)

    return render_template(
        "index.html",
        provinces=PROVINCES.keys(),
        selected_province=province,
        province=province,
        districts=PROVINCES[province].keys(),
        selected_districts=selected_districts,
        selected_forecast_days=forecast_days,
        map_html=map_html,
        PROVINCES=PROVINCES,
    )


@app.route("/refresh_map/<int:forecast_days>")
def refresh_map(forecast_days):
    """Refresh the map with updated data"""
    # Validate forecast days
    if not validate_forecast_days(forecast_days):
        logger.warning(f"Invalid forecast days in refresh map request: {forecast_days}")
        return jsonify({"error": "Invalid forecast days"}), 400
    
    active_basemap = request.args.get("basemap", "Mapbox Satellite")
    selected_districts_str = request.args.get("districts", "")
    selected_districts = selected_districts_str.split(",") if selected_districts_str else []
    
    # Get blinking state (default to True)
    blinking_active = request.args.get("blinking", "true").lower() == "true"
    
    all_districts = {
        district: coords
        for province_districts in PROVINCES.values()
        for district, coords in province_districts.items()
    }

    map_html = map_service.create_map(
        all_districts, 
        forecast_days, 
        active_basemap=active_basemap,
        selected_districts=selected_districts,
        blinking_active=blinking_active
    )
    return jsonify({"map_html": map_html})


@app.route("/get_districts/<province>")
def get_districts(province):
    """Get districts for a specific province"""
    # Validate province
    if not validate_province(province):
        logger.warning(f"Invalid province in districts request: {province}")
        return jsonify({"error": "Invalid province"}), 400

    districts = PROVINCES.get(province, {})
    return jsonify({"province": province, "districts": list(districts.keys())})


# Combined endpoint to generate forecasts and alerts
@app.route("/generate_forecast_and_alerts", methods=["POST"])
def generate_forecast_and_alerts():
    try:
        data = request.get_json()
        if not data:
            return (
                jsonify({"status": "error", "message": "Invalid JSON data"}),
                400,
            )

        # Validate input data
        is_valid, error_msg = validate_api_request_data(data)
        if not is_valid:
            logger.warning(f"Invalid combined request: {error_msg}")
            return jsonify({"status": "error", "message": error_msg}), 400

        province = data.get("province", "Punjab")
        districts = data.get("districts", [])
        forecast_days = data.get("forecast_days", 1)

    except Exception as e:
        logger.error(f"Error parsing combined request: {e}")
        return (
            jsonify({"status": "error", "message": "Invalid request format"}),
            400,
        )

    try:
        # Get selected districts or all districts in province
        if not districts:
            districts_to_fetch = PROVINCES[province]
        else:
            districts_to_fetch = {
                d: PROVINCES[province][d] for d in districts if d in PROVINCES[province]
            }

        # Generate forecasts
        weather_data = weather_service.get_bulk_weather_data(
            province, districts_to_fetch, forecast_days
        )

        if not weather_data:
            return jsonify(
                {"status": "error", "message": "Failed to fetch weather data."}
            )

        # Convert to DataFrames for alert generation
        forecasts = {}
        for d, data in weather_data.items():
            daily = data["daily"]
            # Ensure all values are lists (handle scalar values from legacy cache)
            for key in daily:
                if not isinstance(daily[key], list):
                    daily[key] = [daily[key]]
            
            df = pd.DataFrame(
                {
                    "Date": daily["time"],
                    "Max Temp (°C)": daily["temperature_2m_max"],
                    "Min Temp (°C)": daily["temperature_2m_min"],
                    "Precipitation (mm)": daily["precipitation_sum"],
                    "Precipitation Chance (%)": daily["precipitation_probability_max"],
                    "Wind Speed (km/h)": daily["windspeed_10m_max"],
                    "Wind Gusts (km/h)": daily["windgusts_10m_max"],
                    "Weather Code": daily["weathercode"],
                    "Snowfall (cm)": daily["snowfall_sum"],
                    "UV Index Max": daily["uv_index_max"],
                }
            )
            forecasts[d] = df

        # Generate alerts
        alert_text = alert_service.generate_alert(province, forecasts)
        alerts = alert_service.parse_district_alerts(alert_text)

        # Save district-level alerts
        alert_service.save_district_alerts(alerts, forecast_days, province)

        return jsonify(
            {
                "status": "success",
                "message": f"Forecasts and alerts generated for {len(weather_data)} districts in {province}",
                "alert_text": alert_text,
                "province": province,
            }
        )

    except Exception as e:
        logger.error(f"Error in generate_forecast_and_alerts: {e}", exc_info=True)
        return jsonify(
            {
                "status": "error",
                "message": "Failed to generate forecasts and alerts. Please try again later.",
            }
        )


@app.route("/get_district_alert/<province>/<district>/<int:days>")
def get_district_alert(province, district, days):
    """Get alert for a specific district"""
    # Validate parameters
    if not validate_province(province):
        logger.warning(f"Invalid province in district alert request: {province}")
        return jsonify({"error": "Invalid province"}), 400

    if not validate_district(district):
        logger.warning(f"Invalid district in district alert request: {district}")
        return jsonify({"error": "Invalid district"}), 400

    if not validate_forecast_days(days):
        logger.warning(f"Invalid forecast days in district alert request: {days}")
        return jsonify({"error": "Invalid forecast days"}), 400

    data = alert_service.get_alert(province, district, days)
    if not data:
        return jsonify(
            {
                "district": district,
                "province": province,
                "alert": "⚠️ No alert generated yet. Please generate alerts first.",
                "status": "error",
            }
        )

    return jsonify(
        {
            "district": district,
            "province": province,
            "alert": data.get("alert", "⚠️ No alert available"),
            "status": "success",
        }
    )

    return jsonify(
        {
            "district": district,
            "province": province,
            "alert": data.get("alert", "⚠️ No alert available"),
            "status": "success",
        }
    )


@app.route("/purge_cache", methods=["POST"])
def purge_cache():
    """Purge cache for selected districts"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"status": "error", "message": "Invalid JSON data"}), 400
            
        province = data.get("province")
        districts = data.get("districts", [])
        forecast_days = data.get("forecast_days", 1)
        
        if not validate_province(province):
            return jsonify({"status": "error", "message": "Invalid province"}), 400
            
        # If no districts provided, purge all for the province
        if not districts:
            districts = list(PROVINCES.get(province, {}).keys())
            
        weather_count = weather_service.purge_cache(province, districts, forecast_days)
        alert_count = alert_service.purge_cache(province, districts, forecast_days)
        
        return jsonify({
            "status": "success",
            "message": f"Cache purged successfully. Deleted {weather_count} weather and {alert_count} alert files.",
            "weather_purged": weather_count,
            "alerts_purged": alert_count
        })
        
    except Exception as e:
        logger.error(f"Error purging cache: {e}")
        return jsonify({"status": "error", "message": "Failed to purge cache"}), 500
@app.route("/health")
def health_check():
    """Health check endpoint for monitoring"""
    health_status = get_health_status()
    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code


if __name__ == "__main__":
    app.run(debug=True, port=5000)
