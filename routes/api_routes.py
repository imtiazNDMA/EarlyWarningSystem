from flask import Blueprint, request, jsonify
import logging
import time
from models import PROVINCES
from extensions import weather_service, alert_service
from services import database
from utils.formatting import create_weather_dataframe
from utils.background import background_tasks
from utils.validation import (
    validate_api_request_data,
    validate_province,
    validate_district,
    validate_forecast_days,
)
from utils.health_check import get_health_status

# Initialize Blueprint
api_bp = Blueprint("api", __name__)
logger = logging.getLogger(__name__)


@api_bp.route("/get_forecast/<province>/<district>/<int:days>")
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
    print("Daily data for DataFrame creation:", data)
    if not data:
        return jsonify(
            {
                "district": district,
                "forecast": [],
                "error": "No forecast data available",
            }
        )

    # Convert to DataFrame format for display with caching
    #daily = data["daily"]
    if isinstance(data, dict) and data.get("_source") == "openweathermap":
        daily = data["main"]
    else:
        daily = data.get("daily")
    print(data)
    cache_key = f"forecast_{province}_{district}_{days}"
    df = create_weather_dataframe(daily, cache_key)

    return jsonify(
        {
            "district": district,
            "forecast": df.to_dict("records") if not df.empty else [],
            "days": days,
        }
    )


@api_bp.route("/get_alert/<province>/<district>/<int:days>")
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


@api_bp.route("/get_all_alerts/<int:days>")
def get_all_alerts(days):
    """Return all alerts for all provinces and districts - optimized with SQLite"""
    # Validate forecast days
    if not validate_forecast_days(days):
        logger.warning(f"Invalid forecast days in get all alerts request: {days}")
        return jsonify({"error": "Invalid forecast days"}), 400

    # Initialize all provinces with empty alerts
    all_alerts = {}
    for province in PROVINCES.keys():
        all_alerts[province] = {}
        for district in PROVINCES[province].keys():
            all_alerts[province][district] = "⚠️ No alert generated yet."

    # Fetch alerts from SQLite
    db_alerts = database.get_all_alerts(days)

    # Merge DB alerts into the response structure
    for province, districts_data in db_alerts.items():
        if province in all_alerts:
            for district, alert_text in districts_data.items():
                if district in all_alerts[province]:
                    all_alerts[province][district] = alert_text

    return jsonify(all_alerts)


@api_bp.route("/generate_forecast", methods=["POST"])
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
            province, districts_to_fetch, forecast_days, cache_time=0
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


@api_bp.route("/generate_alerts", methods=["POST"])
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
        districts = data.get("districts", [])
        forecast_days = data.get("forecast_days", 1)

    except Exception as e:
        logger.error(f"Error parsing alerts request: {e}")
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

        # Define the background task function
        def generate_alerts_task():
            """Background task for generating alerts"""
            weather_data = weather_service.get_bulk_weather_data(
                province, districts_to_fetch, forecast_days, cache_time=0
            )

            if not weather_data:
                logger.error("Failed to fetch weather data for alert generation")
                return None

            # Convert to DataFrames
            forecasts = {}
            for d, data in weather_data.items():
                #daily = data["daily"]
                if isinstance(data, dict) and data.get("_source") == "openweathermap":
                    daily = data
                else:
                    daily = data.get("daily")
                # Normalize data to ensure all values are lists for DataFrame creation
                normalized_daily = {}
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
                    normalized_daily[key] = (
                        value if isinstance(value, list) else [value]
                    )

                cache_key = f"alerts_{province}_{forecast_days}_{d}"
                df = create_weather_dataframe(normalized_daily, cache_key)
                forecasts[d] = df

            # Generate alerts using AlertService
            alert_text = alert_service.generate_alert(province, forecasts)
            alerts = alert_service.parse_district_alerts(alert_text)

            # Purge old alerts before saving new ones to ensure fresh data
            alert_service.purge_cache(province, list(forecasts.keys()), forecast_days)

            # Save district-level alerts
            alert_service.save_district_alerts(alerts, forecast_days, province)

            return {
                "status": "success",
                "message": f"Alerts generated for {province}",
                "alert_text": alert_text,
                "province": province,
            }

        # Start background task
        task_id = f"alerts_{province}_{forecast_days}_{time.time()}"
        background_tasks.run_task(task_id, generate_alerts_task)

        return jsonify(
            {
                "status": "processing",
                "message": f"Alert generation started for {province}. This may take a few minutes.",
                "task_id": task_id,
                "province": province,
            }
        )

    except Exception as e:
        logger.error(f"Error in generate_alerts: {e}", exc_info=True)
        return jsonify(
            {
                "status": "error",
                "message": "Failed to start alert generation. Please try again later.",
            }
        )


@api_bp.route("/generate_forecast_and_alerts", methods=["POST"])
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
            province, districts_to_fetch, forecast_days, cache_time=0
        )

        if not weather_data:
            return jsonify(
                {"status": "error", "message": "Failed to fetch weather data."}
            )

        # Convert to DataFrames for alert generation
        forecasts = {}
        for d, data in weather_data.items():
            #daily = data["daily"]
            if isinstance(data, dict) and data.get("_source") == "openweathermap":
                daily = data
            else:
                daily = data.get("daily")
            # Ensure all values are lists (handle scalar values from legacy cache)
            for key in daily:
                if not isinstance(daily[key], list):
                    daily[key] = [daily[key]]

            cache_key = f"combined_{province}_{forecast_days}_{d}"
            df = create_weather_dataframe(daily, cache_key)
            forecasts[d] = df

        # Generate alerts
        alert_text = alert_service.generate_alert(province, forecasts)
        alerts = alert_service.parse_district_alerts(alert_text)

        # Purge old alerts before saving new ones to ensure fresh data
        alert_service.purge_cache(province, list(forecasts.keys()), forecast_days)

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

    except Exception as ex:
        return jsonify({"status": "error", "ollama": "error", "message": str(ex)}), 503


@api_bp.route("/purge_cache", methods=["POST"])
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

        # Database purge handles both alerts and weather cache
        purged_count = database.purge_cache_db(province, districts, forecast_days)

        return jsonify(
            {
                "status": "success",
                "message": f"Cache purged successfully. Deleted approx {purged_count} records.",
                "purged_count": purged_count,
            }
        )

    except Exception as e:
        logger.error(f"Error purging cache: {e}")
        return jsonify({"status": "error", "message": "Failed to purge cache"}), 500


@api_bp.route("/health")
def health_check():
    """Health check endpoint for monitoring"""
    health_status = get_health_status()
    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code
