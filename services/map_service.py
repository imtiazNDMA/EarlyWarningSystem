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
import database

logger = logging.getLogger(__name__)


class MapService:
    """Service for generating interactive maps"""

    def __init__(self):
        self.mapbox_token = Config.MAPBOX_TOKEN
        self._district_to_province = {}
        self._province_index_built = False

    def _build_province_index(self):
        """Build district-to-province index for O(1) lookups"""
        if self._province_index_built:
            return

        from models import PROVINCES

        for prov, districts in PROVINCES.items():
            for dist in districts:
                self._district_to_province[dist] = prov

        self._province_index_built = True
        logger.debug(
            f"Built province index with {len(self._district_to_province)} districts"
        )

    def create_map(
        self,
        locations: Dict[str, Tuple[float, float]],
        forecast_days: int = 1,
        active_basemap: str = "Mapbox Satellite",
        selected_districts: list = None,
        blinking_active: bool = True,
    ) -> str:
        """
        Create an interactive map with weather data markers

        Args:
            locations: Dict of district_name -> (lat, lon)
            forecast_days: Number of forecast days for data display
            active_basemap: Name of the basemap to show by default
            selected_districts: List of districts to highlight with animation
            blinking_active: Whether the blinking animation starts as active

        Returns:
            HTML representation of the map
        """
        if not self.mapbox_token:
            raise ValueError("Mapbox token not configured")

        if selected_districts is None:
            selected_districts = []

        tileurl = f"https://api.mapbox.com/v4/mapbox.satellite/{{z}}/{{x}}/{{y}}@2x.png?access_token={self.mapbox_token}"

        # Define multiple basemaps
        basemaps = {
            "Mapbox Satellite": folium.TileLayer(
                tiles=tileurl,
                attr="&copy; <a href='https://www.mapbox.com/about/maps/'>Mapbox</a>",
                name="Mapbox Satellite",
                overlay=False,
                control=True,
                show=(active_basemap == "Mapbox Satellite"),
            ),
            "OpenStreetMap": folium.TileLayer(
                tiles="openstreetmap",
                name="OpenStreetMap",
                overlay=False,
                control=True,
                show=(active_basemap == "OpenStreetMap"),
            ),
            "CartoDB Positron": folium.TileLayer(
                tiles="cartodbpositron",
                name="CartoDB Positron (Light)",
                overlay=False,
                control=True,
                show=(active_basemap == "CartoDB Positron (Light)"),
            ),
            "CartoDB Dark Matter": folium.TileLayer(
                tiles="cartodbdark_matter",
                name="CartoDB Dark Matter (Dark)",
                overlay=False,
                control=True,
                show=(active_basemap == "CartoDB Dark Matter (Dark)"),
            ),
            "OpenTopoMap": folium.TileLayer(
                tiles="https://{s}.tile.opentopomap.org/{z}/{x}/{y}.png",
                attr='Map data: &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors, <a href="http://viewfinderpanoramas.org">SRTM</a> | Map style: &copy; <a href="https://opentopomap.org">OpenTopoMap</a> (<a href="https://creativecommons.org/licenses/by-sa/3.0/">CC-BY-SA</a>)',
                name="OpenTopoMap (Topographic)",
                overlay=False,
                control=True,
                show=(active_basemap == "OpenTopoMap (Topographic)"),
            ),
        }

        if not locations:
            m = folium.Map(
                location=[33.6844, 73.0479],
                zoom_start=5,
                tiles=None,  # We will add tiles manually
            )
            for layer in basemaps.values():
                layer.add_to(m)
            folium.LayerControl().add_to(m)
            return m._repr_html_()

        m = folium.Map(
            location=[33.6844, 73.0479],
            zoom_start=5,
            tiles=None,  # We will add tiles manually
        )

        # Add all basemaps to the map
        for layer in basemaps.values():
            layer.add_to(m)

        # Add CSS for coolwarm palette animation with toggle support
        animation_css = """
        <style>
        @keyframes coolwarm-pulse {
            0% { fill: #3b4cc0 !important; stroke: #3b4cc0 !important; fill-opacity: 0.4; stroke-width: 1; }
            50% { fill: #b40426 !important; stroke: #b40426 !important; fill-opacity: 0.8; stroke-width: 3; }
            100% { fill: #3b4cc0 !important; stroke: #3b4cc0 !important; fill-opacity: 0.4; stroke-width: 1; }
        }
        .blinking-district {
            /* Animation is only active if .blinking-on class is on body */
            animation: none;
        }
        body.blinking-on .blinking-district {
            animation: coolwarm-pulse 4s ease-in-out infinite;
        }
        </style>
        """
        m.get_root().header.add_child(folium.Element(animation_css))

        # Add JS to notify parent of basemap changes and handle blinking toggle
        js_code = """
        <script>
        document.addEventListener('DOMContentLoaded', function() {
            var map = %s;
            
            // Set initial blinking state
            if (%s) {
                document.body.classList.add('blinking-on');
            }
            
            map.on('baselayerchange', function(e) {
                if (window.parent && window.parent.updateActiveBasemap) {
                    window.parent.updateActiveBasemap(e.name);
                }
            });
            
            // Global function for parent to toggle blinking
            window.toggleBlinking = function(active) {
                if (active) {
                    document.body.classList.add('blinking-on');
                } else {
                    document.body.classList.remove('blinking-on');
                }
            };
        });
        </script>
        """
        m.get_root().html.add_child(
            folium.Element(
                js_code % (m.get_name(), "true" if blinking_active else "false")
            )
        )

        # Add GeoJSON boundary layer
        try:
            districts_gpd = gpd.read_file("static/boundary/district.geojson")
            pakistan_boundary = json.loads(districts_gpd.to_json())

            # Normalize selected districts for comparison
            selected_districts_upper = [d.upper() for d in selected_districts]

            def get_style(feature):
                district_name = feature["properties"]["DISTRICT"].upper()
                is_selected = district_name in selected_districts_upper

                style = {
                    "color": "black",
                    "weight": 0.9,
                    "fillOpacity": 0.3,
                }

                if is_selected:
                    style["fillColor"] = "#3b4cc0"  # Start with cool blue
                    style["color"] = "#3b4cc0"
                    style["fillOpacity"] = 0.5

                return style

            gj = folium.GeoJson(
                pakistan_boundary,
                name="Pakistan District Boundary",
                style_function=get_style,
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

            # Apply blinking classes to selected districts
            if selected_districts:
                blinking_js = """
                <script>
                (function() {
                    var gjLayerName = '%s';
                    var selectedDistricts = %s;
                    
                    function applyBlinking() {
                        var gjLayer = window[gjLayerName];
                        if (!gjLayer) {
                            setTimeout(applyBlinking, 100);
                            return;
                        }
                        
                        gjLayer.eachLayer(function(layer) {
                            var district = layer.feature.properties.DISTRICT.toUpperCase();
                            if (selectedDistricts.includes(district)) {
                                var element = layer._path || (layer.getElement ? layer.getElement() : null);
                                if (element) {
                                    element.classList.add('blinking-district');
                                    // Randomize delay and duration for organic alternating effect
                                    var delay = (Math.random() * -4).toFixed(2) + 's'; 
                                    var duration = (3 + Math.random() * 2).toFixed(2) + 's';
                                    element.style.animationDelay = delay;
                                    element.style.animationDuration = duration;
                                }
                            }
                        });
                    }

                    if (document.readyState === 'complete') {
                        applyBlinking();
                    } else {
                        window.addEventListener('load', applyBlinking);
                        // Fallback for dynamic injection
                        setTimeout(applyBlinking, 500);
                    }
                })();
                </script>
                """
                m.get_root().html.add_child(
                    folium.Element(
                        blinking_js
                        % (gj.get_name(), json.dumps(selected_districts_upper))
                    )
                )

            # Hide static district names as they are visible on hover
            m.fit_bounds(gj.get_bounds())

        except FileNotFoundError:
            logger.warning("Pakistan District Boundary file not found")
        except Exception as e:
            logger.error(f"Error loading boundary data: {e}")

        # Add weather markers
        cluster = MarkerCluster(name="clusters").add_to(m)

        # Build and use district-to-province index for O(1) lookups
        self._build_province_index()
        district_to_province = self._district_to_province

        # Pre-load all forecast and alert data to eliminate O(n²) file I/O
        forecast_data_cache = {}
        alert_data_cache = {}
        current_weather_cache = {}

        logger.debug(f"Pre-loading data for {len(locations)} districts")

        # Load all forecast data in batch
        for district, (lat, lon) in locations.items():
            province = district_to_province.get(district, "Unknown")

            # Load forecast data once per district
            forecast_data, current_weather = self._load_forecast_data(
                province, district, forecast_days
            )
            forecast_data_cache[district] = forecast_data
            current_weather_cache[district] = current_weather

            # Load alert data once per district
            alert_data = self._load_alert_data(province, district, forecast_days)
            alert_data_cache[district] = alert_data

        logger.debug(
            f"Pre-loaded {len(forecast_data_cache)} forecast entries and {len(alert_data_cache)} alert entries"
        )

        for district, (lat, lon) in locations.items():
            province = district_to_province.get(district, "Unknown")

            # Use pre-loaded data instead of file I/O
            forecast_data = forecast_data_cache.get(district)
            current_weather = current_weather_cache.get(district)
            alert_data = alert_data_cache.get(district)

            # Build popup HTML
            popup_html = self._build_popup_html(
                district,
                province,
                forecast_days,
                forecast_data,
                alert_data,
                current_weather,
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

    def _load_forecast_data(
        self, province: str, district: str, days: int
    ) -> Tuple[list, dict]:
        """Load forecast data for popup display, trying all possible provinces if needed"""
        self._build_province_index()

        # Try the provided province first
        provinces_to_try = [province]
        # Then try the correct province for this district using index
        correct_province = self._district_to_province.get(district)
        if correct_province and correct_province != province:
            provinces_to_try.append(correct_province)

        for p in provinces_to_try:
            cache_key = f"weather_{days}_{p}_{sanitize_filename(district)}"
            cache_result = database.get_raw_weather_cache(cache_key)
            
            if cache_result:
                weather_data = cache_result[0]
                daily = weather_data.get("daily", {})
                if not daily:
                    continue

                try:
                    forecast_days_data = []
                    time_data = daily.get("time", [])
                    for i in range(min(days, len(time_data))):
                        day_data = {
                            "Date": time_data[i],
                            "Max Temp (°C)": daily.get("temperature_2m_max", [])[i],
                            "Min Temp (°C)": daily.get("temperature_2m_min", [])[i],
                            "Precipitation (mm)": daily.get(
                                "precipitation_sum", []
                            )[i]
                            or 0,
                            "Precipitation Chance (%)": daily.get(
                                "precipitation_probability_max", []
                            )[i],
                            "Wind Speed (km/h)": daily.get("windspeed_10m_max", [])[
                                i
                            ],
                            "Wind Gusts (km/h)": daily.get("windgusts_10m_max", [])[
                                i
                            ],
                            "Snowfall (cm)": daily.get("snowfall_sum", [])[i] or 0,
                            "UV Index Max": daily.get("uv_index_max", [])[i],
                        }
                        forecast_days_data.append(day_data)

                    return forecast_days_data, weather_data.get("current_weather")
                except Exception as e:
                    logger.error(f"Error processing forecast for {district} in {p}: {e}")

        return None, None

    def _load_alert_data(self, province: str, district: str, days: int) -> str:
        """Load alert data for popup display, trying all possible provinces if needed"""
        self._build_province_index()

        # Try the provided province first
        provinces_to_try = [province]
        # Then try the correct province for this district using index
        correct_province = self._district_to_province.get(district)
        if correct_province and correct_province != province:
            provinces_to_try.append(correct_province)

        for p in provinces_to_try:
            alert_text = database.get_alert(p, district, days)
            if alert_text:
                 return alert_text

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
            
            <div style="background: linear-gradient(135deg, #183B4E 0%, #224d64 100%); color: white; padding: 16px; border-radius: 12px; margin-bottom: 12px; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.4), 0 8px 10px -6px rgba(0, 0, 0, 0.4); border: 1px solid rgba(255, 255, 255, 0.15);">
                <div style="font-size: 0.9em; font-weight: bold; margin-bottom: 8px; text-transform: uppercase; letter-spacing: 1.2px; color: #b7e806;">Nowcasting</div>
        """

        if current_weather:
            temp = current_weather.get("temperature", "N/A")
            wind = current_weather.get("windspeed", "N/A")
            popup_html += f"""
                <div style="display: flex; align-items: center; gap: 20px; margin-bottom: 5px;">
                    <div style="font-size: 2.2em; font-weight: 700; color: #F3F3E0;">&#127777; {temp}°C</div>
                    <div style="font-size: 1em; opacity: 0.9; font-weight: 500;">
                        &#128168; {wind} km/h
                    </div>
                </div>
            """

        if forecast_data:
            today = forecast_data[0]
            snow_html = (
                f"<span>&#10052; {today['Snowfall (cm)']}cm</span>"
                if today.get("Snowfall (cm)", 0) > 0
                else ""
            )
            popup_html += f"""
                <div style="margin-top: 10px; padding-top: 10px; border-top: 1px solid rgba(255,255,255,0.2); font-size: 0.9em; color: #F3F3E0;">
                    <div style="display: flex; justify-content: space-between; margin-bottom: 6px; font-weight: 500;">
                        <span>H: {today["Max Temp (°C)"]}° | L: {today["Min Temp (°C)"]}°</span>
                        <span>&#127783; {today["Precipitation (mm)"]}mm</span>
                    </div>
                    <div style="display: flex; justify-content: space-between; flex-wrap: wrap; gap: 10px; opacity: 0.9;">
                        <span>&#127782; {today["Precipitation Chance (%)"]}%</span>
                        <span>&#127786; {today["Wind Gusts (km/h)"]} km/h</span>
                        <span>&#9728; UV: {today["UV Index Max"]}</span>
                        {snow_html}
                    </div>
                </div>
            """

        popup_html += "</div>"

        if forecast_data:
            has_alert = alert_data and alert_data != "No alert available"
            alert_attr = f'data-alert-text="{alert_data}"' if has_alert else ""
            
            button_style = "background: #b7e806; color: #183B4E;"
            button_text = "&#128203; View Detailed Alert"
            
            if has_alert:
                 button_style = "background: #ff4444; color: white; animation: pulse 2s infinite;"
                 button_text = "&#9888; CRITICAL ALERT - View Details"
            
            popup_html += f"""
            <div style="display: flex; justify-content: center; margin-top: 15px; flex-direction: column; align-items: center;">
                <button onclick="window.parent.loadDistrictAlert('{province}', '{district}')"
                        {alert_attr}
                        style="{button_style} border: none; padding: 10px 22px; border-radius: 25px; cursor: pointer; font-weight: 700; font-size: 0.95em; transition: all 0.3s ease; box-shadow: 0 4px 15px rgba(0,0,0, 0.3); border: 1px solid rgba(0,0,0,0.1);">
                {button_text}
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
