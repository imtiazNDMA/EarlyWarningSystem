"""
Map generation service using Folium
"""

import json
import logging
import os
from typing import Dict, Tuple
import folium
from folium.plugins import MarkerCluster
import geopandas as gpd
from config import Config
from utils.validation import sanitize_filename

logger = logging.getLogger(__name__)


class MapService:
    """Service for generating interactive maps"""

    def __init__(self):
        self.mapbox_token = Config.MAPBOX_TOKEN

    def create_map(
        self, locations: Dict[str, Tuple[float, float]], forecast_days: int = 1
    ) -> str:
        """
        Create an interactive map with weather data markers

        Args:
            locations: Dict of district_name -> (lat, lon)
            forecast_days: Number of forecast days for data display

        Returns:
            HTML representation of the map
        """
        if not self.mapbox_token:
            raise ValueError("Mapbox token not configured")

        tileurl = f"https://api.mapbox.com/v4/mapbox.satellite/{{z}}/{{x}}/{{y}}@2x.png?access_token={self.mapbox_token}"
        tile_a = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"

        if not locations:
            m = folium.Map(
                location=[33.6844, 73.0479],
                zoom_start=5,
                tiles=tileurl,
                attr="&copy; OpenStreetMap contributors",
            )
            return m._repr_html_()

        m = folium.Map(
            location=[33.6844, 73.0479],
            zoom_start=5,
            tiles=tileurl,
            attr="&copy; OpenStreetMap contributors",
        )

        # Add GeoJSON boundary layer
        try:
            districts_gpd = gpd.read_file("static/boundary/district.geojson")
            pakistan_boundary = json.loads(districts_gpd.to_json())

            gj = folium.GeoJson(
                pakistan_boundary,
                name="Pakistan District Boundary",
                style_function=lambda x: {
                    "color": "black",
                    "weight": 0.9,
                    "fillOpacity": 0.3,
                },
                tooltip=folium.features.GeoJsonTooltip(
                    fields=["DISTRICT"], aliases=["DISTRICT:"], localize=True
                ),
                highlight_function=lambda feature: {
                    "fillColor": "orange",
                    "color": "red",
                    "weight": 2,
                    "fillOpacity": 0.7,
                },
            ).add_to(m)

            # Add district labels
            for _, row in districts_gpd.iterrows():
                lon, lat = row.geometry.centroid.x, row.geometry.centroid.y
                folium.map.Marker(
                    [lat, lon],
                    icon=folium.DivIcon(
                        html=f"""
                        <div style="
                            font-size: 12px;
                            font-weight: bold;
                            color: black;
                            text-shadow: 1px 1px 1px white;
                            text-align: center;
                        ">
                        {row["DISTRICT"]}
                        </div>
                        """
                    ),
                ).add_to(m)

            m.fit_bounds(gj.get_bounds())

        except FileNotFoundError:
            logger.warning("Pakistan District Boundary file not found")
        except Exception as e:
            logger.error(f"Error loading boundary data: {e}")

        # Add weather markers
        cluster = MarkerCluster(name="clusters").add_to(m)

        # Find which province each district belongs to
        from models import PROVINCES

        district_to_province = {}
        for prov, districts in PROVINCES.items():
            for dist in districts:
                district_to_province[dist] = prov

        for district, (lat, lon) in locations.items():
            province = district_to_province.get(district, "Unknown")

            # Load forecast and alert data
            forecast_data, current_weather = self._load_forecast_data(province, district, forecast_days)
            alert_data = self._load_alert_data(province, district, forecast_days)

            # Build popup HTML
            popup_html = self._build_popup_html(
                district, province, forecast_days, forecast_data, alert_data, current_weather
            )

            # Set marker color based on precipitation
            color = self._get_marker_color(forecast_data)

            # Create marker
            folium.Marker(
                [lat, lon],
                popup=folium.Popup(
                    f"<div class='district-popup' style='font-size: 1.6em;' contenteditable='false'>{popup_html}</div>",
                    max_width=450,
                ),
                icon=folium.Icon(color=color, icon="info-sign"),
            ).add_to(cluster)

        return m._repr_html_()

    def _load_forecast_data(self, province: str, district: str, days: int) -> Tuple[list, dict]:
        """Load forecast data for popup display, trying all possible provinces if needed"""
        from models import PROVINCES
        
        # Try the provided province first
        provinces_to_try = [province]
        # Then try all other provinces that contain this district
        for p, districts in PROVINCES.items():
            if district in districts and p != province:
                provinces_to_try.append(p)

        for p in provinces_to_try:
            forecast_file = f"static/weatherdata/weather_{days}_{p}_{sanitize_filename(district)}.json"
            if os.path.exists(forecast_file):
                try:
                    with open(forecast_file, "r", encoding="utf-8") as f:
                        weather_data = json.load(f)
                        daily = weather_data.get("daily", {})
                        if not daily:
                            continue
                            
                        forecast_days_data = []
                        time_data = daily.get("time", [])
                        for i in range(min(days, len(time_data))):
                            day_data = {
                                "Date": time_data[i],
                                "Max Temp (°C)": daily.get("temperature_2m_max", [])[i],
                                "Min Temp (°C)": daily.get("temperature_2m_min", [])[i],
                                "Precipitation (mm)": daily.get("precipitation_sum", [])[i] or 0,
                                "Precipitation Chance (%)": daily.get("precipitation_probability_max", [])[i],
                                "Wind Speed (km/h)": daily.get("windspeed_10m_max", [])[i],
                                "Wind Gusts (km/h)": daily.get("windgusts_10m_max", [])[i],
                                "Snowfall (cm)": daily.get("snowfall_sum", [])[i] or 0,
                                "UV Index Max": daily.get("uv_index_max", [])[i],
                            }
                            forecast_days_data.append(day_data)

                        return forecast_days_data, weather_data.get("current_weather")
                except Exception as e:
                    logger.error(f"Error loading forecast for {district} in {p}: {e}")
        
        return None, None

    def _load_alert_data(self, province: str, district: str, days: int) -> str:
        """Load alert data for popup display, trying all possible provinces if needed"""
        from models import PROVINCES
        
        # Try the provided province first
        provinces_to_try = [province]
        # Then try all other provinces that contain this district
        for p, districts in PROVINCES.items():
            if district in districts and p != province:
                provinces_to_try.append(p)

        for p in provinces_to_try:
            alert_file = f"static/weatherdata/alert_{days}_{p}_{sanitize_filename(district)}.json"
            if os.path.exists(alert_file):
                try:
                    with open(alert_file, "r", encoding="utf-8") as f:
                        alert_data_json = json.load(f)
                        return alert_data_json.get("alert", "No alert available")
                except Exception as e:
                    logger.error(f"Error loading alert for {district} in {p}: {e}")
        
        return "No alert available"

    def _build_popup_html(
        self,
        district: str,
        province: str,
        forecast_days: int,
        forecast_data: list,
        alert_data: str,
        current_weather: dict = None,
    ) -> str:
        """Build HTML content for marker popup"""
        popup_html = f"""
        <div style="min-width: 450px;">
            <b>{district}</b><br>
            <i>Province: {province}</i><br>
        """

        if current_weather:
            temp = current_weather.get('temperature', 'N/A')
            wind = current_weather.get('windspeed', 'N/A')
            logger.info(f"Building popup for {district}: Current Temp={temp}, Wind={wind}")
            popup_html += f"""
            <div style="background-color: #e9ecef; padding: 8px; border-radius: 4px; margin: 8px 0; border-left: 4px solid #17a2b8;">
                <strong>Current Conditions:</strong><br>
                &#127777; <b>Temp:</b> {temp} °C<br>
                &#128168; <b>Wind:</b> {wind} km/h
            </div>
            """
        else:
            logger.warning(f"Building popup for {district}: Current weather data MISSING")
            # No debug message for user, just skip the box as before or show a subtle hint
            pass

        popup_html += f"""
            <small><em>Forecast for {forecast_days} day(s)</em></small>
            <br><br>
        """

        if forecast_data:
            for i, day_data in enumerate(forecast_data):
                if i > 0:  # Add separator between days
                    popup_html += "<hr style='margin: 10px 0;'>"

                precip = day_data["Precipitation (mm)"]
                popup_html += f"""
                    <b>Day {i + 1} - {day_data["Date"]}</b><br>
                    &#127777; <b>Max:</b> {day_data["Max Temp (°C)"]} °C<br>
                    &#127777; <b>Min:</b> {day_data["Min Temp (°C)"]} °C<br>
                    &#127783; <b>Precip:</b> {precip} mm<br>
                    &#127782; <b>Chance:</b> {day_data["Precipitation Chance (%)"]} %<br>
                    &#128168; <b>Wind:</b> {day_data["Wind Speed (km/h)"]} km/h<br>
                    &#127786; <b>Gusts:</b> {day_data["Wind Gusts (km/h)"]} km/h<br>
                    &#10052; <b>Snow:</b> {day_data["Snowfall (cm)"]} cm<br>
                    &#9728; <b>UV:</b> {day_data["UV Index Max"]}<br>
                """
                break  # Only show first day in popup for brevity

            popup_html += f"""
            <hr style='margin: 10px 0;'>
            <b>&#128276; Alert:</b> {alert_data}<br><br>
            <button onclick="window.parent.loadDistrictAlert('{province}', '{district}')"
                    style="background: #007bff; color: white; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer;">
            &#128203; View Detailed Alert
            </button>
            """
        else:
            popup_html += (
                "<em>No forecast data available. Click 'Get Forecast' first.</em>"
            )

        popup_html += "</div>"
        return popup_html

    def _get_marker_color(self, forecast_data: list) -> str:
        """Determine marker color based on precipitation"""
        if not forecast_data:
            return "blue"

        # Use max precipitation across all days
        max_precip = max([day["Precipitation (mm)"] for day in forecast_data])
        if max_precip <= 5:
            return "green"
        elif max_precip <= 20:
            return "orange"
        else:
            return "red"
