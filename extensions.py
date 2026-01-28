import logging
from services.weather_service import WeatherService
from services.alert_service import AlertService
from services.map_service import MapService

logger = logging.getLogger(__name__)

# Initialize singletons
weather_service = WeatherService()
alert_service = AlertService()
map_service = MapService()
