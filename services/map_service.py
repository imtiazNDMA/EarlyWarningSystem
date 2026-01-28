"""
Map generation service using Folium
"""

import json
import logging

from typing import Dict, Tuple
import folium
import geopandas as gpd
from config import Config
from utils.validation import sanitize_filename
from services import database

logger = logging.getLogger(__name__)


class MapService:
    """Service for generating interactive maps"""

    def __init__(self):
        self.mapbox_token = Config.MAPBOX_TOKEN
        self._district_to_province = {}
        self._province_index_built = False
        self._centroid_cache: Dict[str, Tuple[float, float]] = {}

        self._boundary_gdf = None

        # District name normalization mapping (models.py name -> GeoJSON name)
        self._district_aliases = {
            # PUNJAB
            "DERA GHAZI KHAN": "Dera_Ghazi_Khan",
            "LAYYAH": "Dera_Ghazi_Khan",  # Layyah is administratively close to DG Khan
            "MANDI BAHAUDDIN": "Mandi_Bahauddin",
            "NANKANA SAHIB": "Nankana_Sahib",
            "RAHIM YAR KHAN": "Rahim_Yar_Khan",
            "TOBA TEK SINGH": "Toba_Tek_Singh",
            # SINDH - Karachi districts
            "KARACHI CENTRAL": "Central_Karachi",
            "KARACHI EAST": "East_Karachi",
            "KARACHI SOUTH": "South_Karachi",
            "KARACHI WEST": "West_Karachi",
            "KORANGI": "Korangi_Karachi",
            "MALIR": "Malir_Karachi",
            "MIRPURKHAS": "Mirpur_Khas",
            "NAUSHAHRO FEROZ": "Naushahro_Feroze",
            "SHAHDAD KOT": "Kambar_Shahdad_Kot",
            "Shaheed BENAZIRABAD": "Shaheed_Benazir_Abad",
            "TANDO ALLAHYAR": "Tando_Allahyar",
            "TANDO MUHMAMMAD KHAN": "Tando_Muhammad_Khan",
            "UMERKOT": "Umer_Kot",
            # KHYBER PAKHTUNKHWA
            "BAJAUR AGENCY": "Mansehra",  # Bajaur is part of Mansehra division
            "BATTAGRAM": "Mansehra",  # Battagram is close to Mansehra
            "DERA ISMAIL KHAN": "D_I_Khan",
            "LAKKI MARWAT": "Lakki_Marwat",
            "LOWER DIR": "Lower_Dir",
            "LOWER KOHISTAN": "Kohistan_Lower",
            "SOUTH WAZIRASTAN": "South_Waziristan",
            "NORTH WAZIRASTAN": "North_Waziristan",
            "TORDHER": "Tor_Ghar",
            "UPPER DIR": "Upper_Dir",
            "UPPER KOHISTAN": "Kohistan_Upper",
            # BALOCHISTAN
            "DERA BUGTI": "Dera_Bugti",
            "JAFFARABAD": "Jaffarabad",  # Note spelling difference
            "KILLA ABDULLAH": "Killa_Abdullah",
            "KILLA SAIFULLAH": "Killa_Saifullah",
            "LEHRI": "Lasbela",  # Lehri is part of Lasbela district
            "KACHHI": "Nasirabad",  # Kachhi is also known as Nasirabad
            # GILGIT BALTISTAN
            "DIAMIR": "Diamir",
            "SKARDU": "Skardu",  # Roundu is part of Skardu
            # AZAD KASHMIR
            "HATTIAN BALA": "Jhelum_Valley",  # Hattian Bala is part of Jhelum Valley
        }

    def _build_province_index(self):
        """Build district-to-province index for O(1) lookups"""
        if self._province_index_built:
            return

        from models import PROVINCES

        for prov, districts in PROVINCES.items():
            for dist in districts:
                self._district_to_province[dist] = prov

        self._province_index_built = True
        logger.debug(f"Built province index with {len(self._district_to_province)} districts")

    def _get_boundary_gdf(self):
        """Lazy load boundary GeoDataFrame"""
        if self._boundary_gdf is None:
            try:
                self._boundary_gdf = gpd.read_file("static/boundary/district.geojson")
            except Exception as e:
                logger.error(f"Error loading boundary file: {e}")
                return None
        return self._boundary_gdf

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
            folium.Element(js_code % (m.get_name(), "true" if blinking_active else "false"))
        )

        # 1. Pre-load all forecast and alert data
        self._build_province_index()
        district_to_province = self._district_to_province
        
        actual_locations = locations.copy()
        
        # Load and cache centroids if not already done (still needed for initial zoom/bounds if no GeoJSON)
        if not self._centroid_cache:
            try:
                districts_gpd = self._get_boundary_gdf()
                if districts_gpd is not None:
                    for centroid, (_, row) in zip(districts_gpd.geometry.centroid, districts_gpd.iterrows()):
                        geojson_district = row.get("District") or row.get("DISTRICT", "")
                        if geojson_district:
                            self._centroid_cache[geojson_district] = (centroid.y, centroid.x)
            except Exception as e:
                logger.warning(f"Error loading centroids from GeoJSON: {e}")

        # Update locations with cached centroids
        if self._centroid_cache:
            for district in actual_locations.keys():
                if district in self._centroid_cache:
                    actual_locations[district] = self._centroid_cache[district]
                else:
                    geojson_name = self._district_aliases.get(district)
                    if geojson_name and geojson_name in self._centroid_cache:
                        actual_locations[district] = self._centroid_cache[geojson_name]

        forecast_data_cache = {}
        alert_data_cache = {}
        current_weather_cache = {}
        
        weather_cache_keys = []
        alert_query_tuples = []
        
        for district in actual_locations.keys():
            province = district_to_province.get(district, "Unknown")
            cache_key = f"weather_{forecast_days}_{province}_{sanitize_filename(district)}"
            weather_cache_keys.append(cache_key)
            alert_query_tuples.append((province, district, forecast_days))

        weather_batch = database.get_raw_weather_cache_batch(weather_cache_keys)
        alerts_batch = database.get_alerts_batch(alert_query_tuples)

        for district in actual_locations.keys():
            province = district_to_province.get(district, "Unknown")
            cache_key = f"weather_{forecast_days}_{province}_{sanitize_filename(district)}"
            
            if cache_key in weather_batch:
                weather_data, _ = weather_batch[cache_key]
                current_weather_cache[district] = weather_data.get("current_weather")
                daily = weather_data.get("daily", {})
                if daily:
                    try:
                        forecast_days_data = []
                        time_data = daily.get("time", [])
                        for i in range(min(forecast_days, len(time_data))):
                            forecast_days_data.append({
                                "Date": time_data[i],
                                "Max Temp (°C)": daily.get("temperature_2m_max", [])[i],
                                "Min Temp (°C)": daily.get("temperature_2m_min", [])[i],
                                "Precipitation (mm)": daily.get("precipitation_sum", [])[i] or 0,
                                "Precipitation Chance (%)": daily.get("precipitation_probability_max", [])[i],
                                "Wind Speed (km/h)": daily.get("windspeed_10m_max", [])[i],
                                "Wind Gusts (km/h)": daily.get("windgusts_10m_max", [])[i],
                                "Snowfall (cm)": daily.get("snowfall_sum", [])[i] or 0,
                                "UV Index Max": daily.get("uv_index_max", [])[i],
                            })
                        forecast_data_cache[district] = forecast_days_data
                    except: forecast_data_cache[district] = None
                else: forecast_data_cache[district] = None
            else:
                forecast_data_cache[district] = None
                current_weather_cache[district] = None
            
            alert_key = (province, district, forecast_days)
            alert_data_cache[district] = alerts_batch.get(alert_key, "No alert available")

        # 2. Add GeoJSON boundary layer with integrated popups
        try:
            districts_gpd = self._get_boundary_gdf()
            if districts_gpd is None:
                raise FileNotFoundError("Boundary file not loaded")
                
            pakistan_boundary = json.loads(districts_gpd.to_json())

            # Normalize selected districts
            selected_districts_normalized = []
            for d in selected_districts:
                normalized = self._district_aliases.get(d, d).replace(" ", "_").upper()
                selected_districts_normalized.append(normalized)

            def get_style(feature):
                props = feature["properties"]
                district_name = props.get("District") or props.get("DISTRICT") or ""
                district_name_normalized = district_name.replace(" ", "_").upper()
                is_selected = district_name_normalized in selected_districts_normalized

                style = {"color": "black", "weight": 0.9, "fillOpacity": 0.3}
                if is_selected:
                    style.update({"fillColor": "#3b4cc0", "color": "#3b4cc0", "fillOpacity": 0.5})
                return style

            for feature in pakistan_boundary["features"]:
                props = feature["properties"]
                district = props.get("District", props.get("DISTRICT", "Unknown"))
                province = props.get("Province", props.get("PROVINCE", "Unknown"))
                
                # Attach Tooltip
                feature["properties"]["tooltip"] = f"{district} ({province.replace('_', ' ')})"
                
                # Attach Popup HTML (Nowcasting)
                # Find the corresponding data in our model (handle potential name diffs)
                model_district = district
                # Reverse alias check or just check if it exists in cache
                if model_district not in forecast_data_cache:
                    # Slow fallback for direct match or alias
                    found = False
                    for d, aliased in self._district_aliases.items():
                        if aliased == district:
                            model_district = d
                            found = True
                            break
                    if not found and district not in forecast_data_cache:
                        model_district = district # Default back

                popup_html = self._build_popup_html(
                    model_district,
                    province.replace('_', ' '),
                    forecast_days,
                    forecast_data_cache.get(model_district),
                    alert_data_cache.get(model_district),
                    current_weather_cache.get(model_district),
                )
                feature["properties"]["nowcast_html"] = f"<div class='district-popup' style='font-size: 1.2rem;' contenteditable='false'>{popup_html}</div>"

            gj = folium.GeoJson(
                pakistan_boundary,
                name="Pakistan District Boundary",
                style_function=get_style,
                tooltip=folium.GeoJsonTooltip(fields=["tooltip"], aliases=[""], localize=False),
                popup=folium.GeoJsonPopup(fields=["nowcast_html"], labels=False, max_width=450),
                highlight_function=lambda feature: {
                    "fillColor": "orange",
                    "color": "red",
                    "weight": 2,
                    "fillOpacity": 0.7,
                },
            ).add_to(m)

            if selected_districts:
                blinking_js = """
                <script>
                (function() {
                    var gjLayerName = '%s';
                    var selectedDistricts = %s;
                    function applyBlinking() {
                        var gjLayer = window[gjLayerName];
                        if (!gjLayer) { setTimeout(applyBlinking, 100); return; }
                        gjLayer.eachLayer(function(layer) {
                            var props = layer.feature.properties;
                            var district = (props.District || props.DISTRICT || '');
                            var districtNormalized = district.replace(/ /g, '_').toUpperCase();
                            if (selectedDistricts.includes(districtNormalized)) {
                                var element = layer._path || (layer.getElement ? layer.getElement() : null);
                                if (element) {
                                    element.classList.add('blinking-district');
                                    element.style.animationDelay = (Math.random() * -4).toFixed(2) + 's'; 
                                    element.style.animationDuration = (3 + Math.random() * 2).toFixed(2) + 's';
                                }
                            }
                        });
                    }
                    if (document.readyState === 'complete') { applyBlinking(); } 
                    else { window.addEventListener('load', applyBlinking); setTimeout(applyBlinking, 500); }
                })();
                </script>
                """
                m.get_root().html.add_child(folium.Element(blinking_js % (gj.get_name(), json.dumps(selected_districts_normalized))))

            m.fit_bounds(gj.get_bounds())

        except Exception as e:
            logger.error(f"Error building map geometry/popups: {e}")

        folium.LayerControl().add_to(m)
        return m._repr_html_()

    def _load_forecast_data(self, province: str, district: str, days: int) -> Tuple[list, dict]:
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
                current_weather = weather_data.get("current_weather")
                daily = weather_data.get("daily", {})

                # If we have current weather but no daily data, return current weather with None forecast
                if not daily and current_weather:
                    return None, current_weather

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
                            "Precipitation (mm)": daily.get("precipitation_sum", [])[i] or 0,
                            "Precipitation Chance (%)": daily.get(
                                "precipitation_probability_max", []
                            )[i],
                            "Wind Speed (km/h)": daily.get("windspeed_10m_max", [])[i],
                            "Wind Gusts (km/h)": daily.get("windgusts_10m_max", [])[i],
                            "Snowfall (cm)": daily.get("snowfall_sum", [])[i] or 0,
                            "UV Index Max": daily.get("uv_index_max", [])[i],
                        }
                        forecast_days_data.append(day_data)

                    return forecast_days_data, current_weather
                except Exception as e:
                    logger.error(f"Error processing forecast for {district} in {p}: {e}")
                    # If forecast processing failed but we have current weather, return it
                    if current_weather:
                        return None, current_weather

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

        # Always try to show current weather if available
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
        else:
            # Show placeholder if no current weather
            popup_html += """
                <div style="display: flex; align-items: center; gap: 20px; margin-bottom: 5px;">
                    <div style="font-size: 1.5em; font-weight: 700; color: #F3F3E0; opacity: 0.6;">&#127777; --°C</div>
                    <div style="font-size: 1em; opacity: 0.6; font-weight: 500;">
                        &#128168; -- km/h
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

            # Determine if this is a critical alert based on weather conditions
            is_critical = self._is_critical_weather_alert(forecast_data)

            if has_alert and is_critical:
                button_style = "background: #ff4444; color: white; animation: pulse 2s infinite;"
                button_text = "&#9888; CRITICAL ALERT"
            elif has_alert:
                button_style = "background: #ff8c00; color: white;"
                button_text = "&#128203; View Weather Alert"
            else:
                button_style = "background: #b7e806; color: #183B4E;"
                button_text = "&#128203; View Detailed Alert"

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
            # Show message about forecast data availability
            if current_weather:
                popup_html += (
                    "<div style='text-align: center; color: #666; font-style: italic; margin-top: 10px;'>"
                    "Forecast data not available. Click 'Get Forecast' to load predictions."
                    "</div>"
                )
            else:
                popup_html += (
                    "<div style='text-align: center; color: #666; font-style: italic; margin-top: 10px;'>"
                    "No weather data available. Click 'Get Forecast' first."
                    "</div>"
                )

        popup_html += "</div>"
        return popup_html

    def _is_critical_weather_alert(self, forecast_data: list) -> bool:
        """Determine if weather conditions warrant a critical alert"""
        if not forecast_data:
            return False

        # Check for critical weather conditions
        for day in forecast_data:
            precip = day.get("Precipitation (mm)", 0)
            precip_chance = day.get("Precipitation Chance (%)", 0)
            wind_gusts = day.get("Wind Gusts (km/h)", 0)
            snowfall = day.get("Snowfall (cm)", 0)
            uv_index = day.get("UV Index Max", 0)

            # Critical conditions:
            # - Heavy precipitation (>20mm)
            # - Very high precipitation chance (>90%)
            # - Extreme wind (>50 km/h gusts)
            # - Significant snowfall (>5cm)
            # - Extreme UV (>10)
            if (
                precip > 20
                or precip_chance > 90
                or wind_gusts > 50
                or snowfall > 5
                or uv_index > 10
            ):
                return True

        return False

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
