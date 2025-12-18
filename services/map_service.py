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
        self, 
        locations: Dict[str, Tuple[float, float]], 
        forecast_days: int = 1,
        active_basemap: str = "Mapbox Satellite"
    ) -> str:
        """
        Create an interactive map with weather data markers

        Args:
            locations: Dict of district_name -> (lat, lon)
            forecast_days: Number of forecast days for data display
            active_basemap: Name of the basemap to show by default

        Returns:
            HTML representation of the map
        """
        if not self.mapbox_token:
            raise ValueError("Mapbox token not configured")

        tileurl = f"https://api.mapbox.com/v4/mapbox.satellite/{{z}}/{{x}}/{{y}}@2x.png?access_token={self.mapbox_token}"
        
        # Define multiple basemaps
        basemaps = {
            "Mapbox Satellite": folium.TileLayer(
                tiles=tileurl,
                attr="&copy; <a href='https://www.mapbox.com/about/maps/'>Mapbox</a>",
                name="Mapbox Satellite",
                overlay=False,
                control=True,
                show=(active_basemap == "Mapbox Satellite")
            ),
            "OpenStreetMap": folium.TileLayer(
                tiles="openstreetmap",
                name="OpenStreetMap",
                overlay=False,
                control=True,
                show=(active_basemap == "OpenStreetMap")
            ),
            "CartoDB Positron": folium.TileLayer(
                tiles="cartodbpositron",
                name="CartoDB Positron (Light)",
                overlay=False,
                control=True,
                show=(active_basemap == "CartoDB Positron (Light)")
            ),
            "CartoDB Dark Matter": folium.TileLayer(
                tiles="cartodbdark_matter",
                name="CartoDB Dark Matter (Dark)",
                overlay=False,
                control=True,
                show=(active_basemap == "CartoDB Dark Matter (Dark)")
            ),
            "OpenTopoMap": folium.TileLayer(
                tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
                attr='Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, <a href="http://viewfinderpanoramas.org">SRTM</a> | Map style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/">CC-BY-SA</a>)',
                name="OpenTopoMap (Topographic)",
                overlay=False,
                control=True,
                show=(active_basemap == "OpenTopoMap (Topographic)")
            )
        }

        if not locations:
            m = folium.Map(
                location=[33.6844, 73.0479],
                zoom_start=5,
                tiles=None # We will add tiles manually
            )
            for layer in basemaps.values():
                layer.add_to(m)
            folium.LayerControl().add_to(m)
            return m._repr_html_()

        m = folium.Map(
            location=[33.6844, 73.0479],
            zoom_start=5,
            tiles=None # We will add tiles manually
        )
        
        # Add all basemaps to the map
        for layer in basemaps.values():
            layer.add_to(m)

        # Add JS to notify parent of basemap changes
        js_code = """
        <script>
        document.addEventListener('DOMContentLoaded', function() {
            var map = %s;
            map.on('baselayerchange', function(e) {
                if (window.parent && window.parent.updateActiveBasemap) {
                    window.parent.updateActiveBasemap(e.name);
                }
            });
        });
        </script>
        """
        m.get_root().html.add_child(folium.Element(js_code % m.get_name()))

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

        folium.LayerControl().add_to(m)
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
        <div style="min-width: 300px; font-family: 'Inter', sans-serif;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                <b style="font-size: 1.2em; color: #333;">{district}</b>
                <span style="font-size: 0.8em; color: #666; background: #f0f0f0; padding: 2px 6px; border-radius: 10px;">{province}</span>
            </div>
            
            <div style="background: linear-gradient(135deg, #17a2b8 0%, #117a8b 100%); color: white; padding: 12px; border-radius: 8px; margin-bottom: 12px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <div style="font-size: 0.9em; font-weight: bold; margin-bottom: 5px; text-transform: uppercase; letter-spacing: 1px;">Nowcasting</div>
        """

        if current_weather:
            temp = current_weather.get('temperature', 'N/A')
            wind = current_weather.get('windspeed', 'N/A')
            popup_html += f"""
                <div style="display: flex; align-items: center; gap: 15px;">
                    <div style="font-size: 2em;">&#127777; {temp}°C</div>
                    <div style="font-size: 0.9em; opacity: 0.9;">
                        &#128168; {wind} km/h
                    </div>
                </div>
            """
        
        if forecast_data:
            today = forecast_data[0]
            snow_html = f"<span>&#10052; {today['Snowfall (cm)']}cm</span>" if today.get('Snowfall (cm)', 0) > 0 else ""
            popup_html += f"""
                <div style="margin-top: 8px; padding-top: 8px; border-top: 1px solid rgba(255,255,255,0.2); font-size: 0.85em;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 4px;">
                        <span>H: {today['Max Temp (°C)']}° | L: {today['Min Temp (°C)']}°</span>
                        <span>&#127783; {today['Precipitation (mm)']}mm</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 8px;">
                        <span>&#127782; {today['Precipitation Chance (%)']}%</span>
                        <span>&#127786; Gusts: {today['Wind Gusts (km/h)']}km/h</span>
                        <span>&#9728; UV: {today['UV Index Max']}</span>
                        {snow_html}
                    </div>
                </div>
            """
        
        popup_html += "</div>"

        if forecast_data:
            popup_html += f"""
            <div style="display: flex; justify-content: center; margin-top: 10px;">
                <button onclick="window.parent.loadDistrictAlert('{province}', '{district}')"
                        style="background: #007bff; color: white; border: none; padding: 8px 16px; border-radius: 20px; cursor: pointer; font-weight: 600; font-size: 0.9em; transition: all 0.3s ease; box-shadow: 0 2px 4px rgba(0,123,255,0.3);">
                &#128203; View Detailed Alert
                </button>
            </div>
            """
        else:
            popup_html += (
                "<div style='text-align: center; color: #666; font-style: italic; margin-top: 10px;'>"
                "No forecast data available. Click 'Get Forecast' first."
                "</div>"
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
