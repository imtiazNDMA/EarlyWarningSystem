import pandas as pd
import logging
from services import database

logger = logging.getLogger(__name__)

def create_weather_dataframe(daily: dict, cache_key: str | None = None) -> pd.DataFrame:
    """Create weather DataFrame with SQLite caching"""
    if cache_key:
        cached_df = database.get_weather_cache(cache_key)
        if cached_df is not None:
            logger.debug(f"Using SQLite cached DataFrame for {cache_key}")
            return cached_df

    df = pd.DataFrame(
        {
            "Date": daily.get("time", []),
            "Max Temp (°C)": daily.get("temperature_2m_max", []),
            "Min Temp (°C)": daily.get("temperature_2m_min", []),
            "Precipitation (mm)": daily.get("precipitation_sum", []),
            "Precipitation Chance (%)": daily.get("precipitation_probability_max", []),
            "Wind Speed (km/h)": daily.get("windspeed_10m_max", []),
            "Wind Gusts (km/h)": daily.get("windgusts_10m_max", []),
            "Weather Code": daily.get("weathercode", []),
            "Snowfall (cm)": daily.get("snowfall_sum", []),
            "UV Index Max": daily.get("uv_index_max", []),
        }
    )

    # Cache if key provided
    if cache_key:
        database.set_weather_cache(cache_key, df)
        logger.debug(f"Cached DataFrame to SQLite for {cache_key}")

    return df
