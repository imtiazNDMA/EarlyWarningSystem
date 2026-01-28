"""
Tests for map_service.py
"""

import pytest
from unittest.mock import patch, MagicMock
from services.map_service import MapService


class TestMapService:
    """Test cases for MapService"""

    def setup_method(self):
        """Set up test fixtures"""
        self.service = MapService()

    def test_init(self):
        """Test MapService initialization"""
        assert self.service.mapbox_token is not None

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

    @patch("services.map_service.database")
    def test_load_forecast_data_exists(self, mock_db):
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
            "current_weather": {"temperature": 20, "windspeed": 10}
        }
        
        # Mock DB return: (data, created_at)
        mock_db.get_raw_weather_cache.return_value = (mock_data, "2024-01-01 12:00:00")

        result = self.service._load_forecast_data("PUNJAB", "LAHORE", 1)

        assert result is not None
        assert len(result) == 2  # Returns (forecast_data, current_weather)
        forecast_data, current_weather = result
        assert forecast_data is not None
        assert len(forecast_data) == 1
        assert current_weather is not None

    @patch("services.map_service.database")
    def test_load_forecast_data_not_exists(self, mock_db):
        """Test loading non-existent forecast data"""
        mock_db.get_raw_weather_cache.return_value = None

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
        row_mock.get.side_effect = lambda k: "Lahore" if k in ["District", "DISTRICT"] else None
        centroid_mock = MagicMock()
        centroid_mock.x = 74.0
        centroid_mock.y = 31.0
        row_mock.__getitem__.return_value = centroid_mock # row["centroid"]
        
        mock_gdf.iterrows.return_value = [(0, row_mock)]
        mock_gdf.geometry.centroid = [centroid_mock] # list of centroids matching iterrows count
        
        mock_read_file.return_value = mock_gdf
        
        # First call - should read file
        self.service.create_map(locations, 1)
        assert len(self.service._centroid_cache) > 0
        assert "Lahore" in self.service._centroid_cache
        assert mock_read_file.call_count == 1
        
        # Second call - should NOT read file
        self.service.create_map(locations, 1)
        assert mock_read_file.call_count == 1  # Still 1
