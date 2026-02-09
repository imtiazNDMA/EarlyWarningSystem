from flask import Blueprint, render_template, request, jsonify
import logging
from config import Config
from models import PROVINCES
from extensions import map_service
from utils.validation import validate_forecast_days, validate_province

# Initialize Blueprint
main_bp = Blueprint('main', __name__)
logger = logging.getLogger(__name__)

@main_bp.route("/", methods=["GET", "POST"])
def index():
    """
    Main dashboard route.

    Handles both GET (display form) and POST (process form submission).
    Renders the main template with map and form controls.

    Returns:
        Rendered HTML template
    """
    province = "PUNJAB"
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


@main_bp.route("/refresh_map/<int:forecast_days>")
def refresh_map(forecast_days):
    """Refresh the map with updated data"""
    # Validate forecast days
    if not validate_forecast_days(forecast_days):
        logger.warning(f"Invalid forecast days in refresh map request: {forecast_days}")
        return jsonify({"error": "Invalid forecast days"}), 400

    active_basemap = request.args.get("basemap", "Mapbox Satellite")
    selected_districts_str = request.args.get("districts", "")
    selected_districts = (
        selected_districts_str.split(",") if selected_districts_str else []
    )

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
        blinking_active=blinking_active,
    )
    return jsonify({"map_html": map_html})


@main_bp.route("/get_districts/<province>")
def get_districts(province):
    """Get districts for a specific province"""
    # Validate province
    if not validate_province(province):
        logger.warning(f"Invalid province in districts request: {province}")
        return jsonify({"error": "Invalid province"}), 400

    districts = PROVINCES.get(province, {})
    return jsonify({"province": province, "districts": list(districts.keys())})
