import sqlite3
import json
import logging
from typing import Optional, Dict, List, Any, Tuple
from datetime import datetime
import pandas as pd

logger = logging.getLogger(__name__)

DB_FILE = "weather.db"


def init_db():
    """Initialize the SQLite database with required tables"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            # Create weather cache table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS weather_cache (
                    cache_key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Create alerts table
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    province TEXT,
                    district TEXT,
                    forecast_days INTEGER,
                    alert_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (province, district, forecast_days)
                )
            """
            )

            conn.commit()
            logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")


def get_weather_cache(cache_key: str) -> Optional[pd.DataFrame]:
    """Retrieve weather data from cache"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT data FROM weather_cache WHERE cache_key = ?", (cache_key,))
            row = cursor.fetchone()

            if row:
                data_dict = json.loads(row[0])
                # Convert back to DataFrame
                # We expect data_dict to be suitable for pd.DataFrame.from_dict or similar
                # Ideally we stored it as records
                return pd.DataFrame.from_records(data_dict)
            return None
    except Exception as e:
        logger.error(f"Error retrieving weather cache for {cache_key}: {e}")
        return None


def get_raw_weather_cache(cache_key: str) -> Optional[Tuple[dict, datetime]]:
    """Retrieve raw JSON weather data from cache with timestamp"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT data, created_at FROM weather_cache WHERE cache_key = ?", (cache_key,)
            )
            row = cursor.fetchone()

            if row:
                data_dict = json.loads(row[0])
                created_at = datetime.fromisoformat(row[1]) if isinstance(row[1], str) else row[1]
                # SQLite timestamp might be string
                if isinstance(created_at, str):
                    try:
                        created_at = datetime.strptime(created_at, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        # Fallback or try ISO
                        pass
                return data_dict, created_at
            return None
    except Exception as e:
        logger.error(f"Error retrieving raw weather cache for {cache_key}: {e}")
        return None


def set_raw_weather_cache(cache_key: str, data: dict):
    """Save raw JSON weather data to cache"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            data_json = json.dumps(data)
            cursor.execute(
                """
                INSERT OR REPLACE INTO weather_cache (cache_key, data, created_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
                (cache_key, data_json),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Error saving raw weather cache for {cache_key}: {e}")


def set_weather_cache(cache_key: str, df: pd.DataFrame):
    """Save weather data to cache"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            # Serialize DataFrame to JSON string
            data_json = df.to_json(orient="records", date_format="iso")

            cursor.execute(
                """
                INSERT OR REPLACE INTO weather_cache (cache_key, data, created_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
            """,
                (cache_key, data_json),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Error saving weather cache for {cache_key}: {e}")


def save_alert(province: str, district: str, forecast_days: int, alert_text: str):
    """Save generated alert to database"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO alerts (province, district, forecast_days, alert_text, created_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (province, district, forecast_days, alert_text),
            )
            conn.commit()
    except Exception as e:
        logger.error(f"Error saving alert for {province}/{district}: {e}")


def get_alert(province: str, district: str, forecast_days: int) -> Optional[str]:
    """Retrieve alert from database"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT alert_text FROM alerts 
                WHERE province = ? AND district = ? AND forecast_days = ?
            """,
                (province, district, forecast_days),
            )
            row = cursor.fetchone()
            return row[0] if row else None
    except Exception as e:
        logger.error(f"Error retrieving alert for {province}/{district}: {e}")
        return None


def get_all_alerts(forecast_days: int) -> Dict[str, Dict[str, str]]:
    """Retrieve all alerts for a specific forecast duration"""
    alerts = {}
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT province, district, alert_text FROM alerts 
                WHERE forecast_days = ?
            """,
                (forecast_days,),
            )
            rows = cursor.fetchall()

            for province, district, alert_text in rows:
                if province not in alerts:
                    alerts[province] = {}
                alerts[province][district] = alert_text

        return alerts
    except Exception as e:
        logger.error(f"Error retrieving all alerts: {e}")
        return {}


def purge_cache_db(province: str, districts: List[str], forecast_days: int) -> int:
    """Delete alerts from database for specific districts"""
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()

            if not districts:
                # Delete all for province
                cursor.execute(
                    """
                    DELETE FROM alerts 
                    WHERE province = ? AND forecast_days = ?
                """,
                    (province, forecast_days),
                )
                # Also delete related weather cache? Weather cache keys are unstructured strings unfortunately
                # e.g. "forecast_Punjab_Lahore_1" or "alerts_Punjab_1_Lahore"
                # We can try to delete them using LIKE
                count = cursor.rowcount

                cursor.execute(
                    """
                    DELETE FROM weather_cache 
                    WHERE cache_key LIKE ? OR cache_key LIKE ?
                """,
                    (
                        f"forecast_{province}_%_{forecast_days}",
                        f"alerts_{province}_{forecast_days}_%",
                    ),
                )

                return count

            count = 0
            for district in districts:
                cursor.execute(
                    """
                    DELETE FROM alerts 
                    WHERE province = ? AND district = ? AND forecast_days = ?
                """,
                    (province, district, forecast_days),
                )
                count += cursor.rowcount

                # Try to clean up weather cache too
                # forecast_{province}_{district}_{days}
                # alerts_{province}_{forecast_days}_{district}
                cursor.execute(
                    """
                    DELETE FROM weather_cache 
                    WHERE cache_key = ? OR cache_key = ?
                """,
                    (
                        f"forecast_{province}_{district}_{forecast_days}",
                        f"alerts_{province}_{forecast_days}_{district}",
                    ),
                )

            conn.commit()
            return count
    except Exception as e:
        logger.error(f"Error purging cache from DB: {e}")
        return 0
