"""
Tests for map_service.py
"""

from unittest.mock import MagicMock, patch

from services.map_service import MapService
from repositories.memory import InMemoryRepository


class TestMapService:
    """Test cases for MapService"""

    def setup_method(self):
        """Set up test fixtures"""
        self.service = MapService(InMemoryRepository())

    def test_init(self):
        """Test MapService initialization"""
        assert self.service is not None

    def test_map_uses_only_open_basemap_endpoints(self):
        """Generated maps expose the approved keyless basemap catalog."""
        map_html = self.service.create_map({}, 1)

        assert "tile.openstreetmap.org" in map_html
        assert "tile.opentopomap.org" in map_html
        assert "World_Imagery/MapServer/tile" in map_html
        assert "World_Light_Gray_Base/MapServer/tile" in map_html
        assert "api.mapbox.com" not in map_html
        assert "basemaps.cartocdn.com" not in map_html

    def test_unknown_basemap_falls_back_to_openstreetmap(self):
        """A stale browser basemap preference must not create a blank map."""
        map_html = self.service.create_map({}, 1, active_basemap="Mapbox Satellite")

        assert "tile.openstreetmap.org" in map_html

    @patch("services.map_service.folium.Map")
    @patch("services.map_service.gpd.read_file")
    def test_create_map_with_locations(self, mock_read_file, mock_map):
        """Test creating map with locations"""
        locations = {"Lahore": (31.5204, 74.3587), "Karachi": (24.8607, 67.0011)}

        # Mock GeoDataFrame
        mock_gdf = MagicMock()
        mock_gdf.to_json.return_value = '{"type": "FeatureCollection", "features": []}'
        mock_gdf.iterrows.return_value = []
        mock_read_file.return_value = mock_gdf

        # Mock Map instance
        mock_map_instance = MagicMock()
        mock_map_instance._repr_html_.return_value = "<div>Map HTML</div>"
        mock_map.return_value = mock_map_instance

        result = self.service.create_map(locations, 1)

        assert result is not None
        assert "Map HTML" in result

    def test_get_marker_color_no_data(self):
        """Test marker color with no forecast data"""
        color = self.service._get_marker_color(None)
        assert color == "blue"

    def test_get_marker_color_low_precipitation(self):
        """Test marker color with low precipitation"""
        forecast_data = [{"Precipitation (mm)": 3.0}]
        color = self.service._get_marker_color(forecast_data)
        assert color == "green"

    def test_get_marker_color_medium_precipitation(self):
        """Test marker color with medium precipitation"""
        forecast_data = [{"Precipitation (mm)": 15.0}]
        color = self.service._get_marker_color(forecast_data)
        assert color == "orange"

    def test_get_marker_color_high_precipitation(self):
        """Test marker color with high precipitation"""
        forecast_data = [{"Precipitation (mm)": 25.0}]
        color = self.service._get_marker_color(forecast_data)
        assert color == "red"

    def test_load_forecast_data_exists(self):
        """Test loading existing forecast data"""
        mock_data = {
            "daily": {
                "time": ["2024-01-01"],
                "temperature_2m_max": [25.0],
                "temperature_2m_min": [15.0],
                "precipitation_sum": [0.0],
                "precipitation_probability_max": [10],
                "windspeed_10m_max": [15.0],
                "windgusts_10m_max": [20.0],
                "snowfall_sum": [0.0],
                "uv_index_max": [5.0],
            },
            "current_weather": {"temperature": 20, "windspeed": 10},
        }

        self.service.repository.set_raw_weather_cache(
            "weather_1_PUNJAB_LAHORE", mock_data
        )

        result = self.service._load_forecast_data("PUNJAB", "LAHORE", 1)

        assert result is not None
        assert len(result) == 2  # Returns (forecast_data, current_weather)
        forecast_data, current_weather = result
        assert forecast_data is not None
        assert len(forecast_data) == 1
        assert current_weather is not None

    def test_load_forecast_data_not_exists(self):
        """Test loading non-existent forecast data"""
        result = self.service._load_forecast_data("PUNJAB", "NONEXISTENT", 1)

        assert result == (None, None)

    @patch("services.map_service.folium.Map")
    @patch("services.map_service.gpd.read_file")
    def test_create_map_caches_centroids(self, mock_read_file, mock_map):
        """Test that centroids are cached after first map creation"""
        locations = {"Lahore": (31.5204, 74.3587)}

        # Mock GeoDataFrame with centroid
        mock_gdf = MagicMock()
        mock_gdf.to_json.return_value = '{"type": "FeatureCollection", "features": []}'

        # Mock row iteration
        row_mock = MagicMock()
        row_mock.get.side_effect = lambda k: (
            "Lahore" if k in ["District", "DISTRICT"] else None
        )
        centroid_mock = MagicMock()
        centroid_mock.x = 74.0
        centroid_mock.y = 31.0
        row_mock.__getitem__.return_value = centroid_mock  # row["centroid"]

        mock_gdf.iterrows.return_value = [(0, row_mock)]
        projected_gdf = MagicMock()
        projected_centroids = MagicMock()
        projected_centroids.to_crs.return_value = [centroid_mock]
        projected_gdf.geometry.centroid = projected_centroids
        mock_gdf.to_crs.return_value = projected_gdf

        mock_read_file.return_value = mock_gdf

        # First call - should read file
        self.service.create_map(locations, 1)
        assert len(self.service._centroid_cache) > 0
        assert "Lahore" in self.service._centroid_cache
        mock_gdf.to_crs.assert_called_once_with(epsg=3857)
        projected_centroids.to_crs.assert_called_once_with(epsg=4326)
        assert mock_read_file.call_count == 1

        # Second call - should NOT read file
        self.service.create_map(locations, 1)
        assert mock_read_file.call_count == 1  # Still 1
