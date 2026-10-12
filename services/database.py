import json
import logging
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from datetime import datetime

import pandas as pd

from config import Config

logger = logging.getLogger(__name__)

DB_FILE = "weather.db"


@contextmanager
def get_db_connection() -> Generator[sqlite3.Connection, None, None]:
    """
    Context manager for database connections.
    Handles connection creation, committing, and closing.
    """
    conn = None
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10.0)
        # WAL lets readers proceed during writes; with Flask threads plus a
        # worker pool writing concurrently, the default rollback journal
        # surfaces as "database is locked" under load.
        conn.execute("PRAGMA journal_mode=WAL;")
        # How long a blocked connection waits on a lock before raising.
        conn.execute("PRAGMA busy_timeout=5000;")
        yield conn
        conn.commit()
    except sqlite3.Error as e:
        if conn:
            conn.rollback()
        logger.error(f"Database error: {e}")
        raise
    except Exception as e:
        if conn:
            conn.rollback()
        logger.error(f"Unexpected error during database operation: {e}")
        raise
    finally:
        if conn:
            conn.close()


def init_db():
    """Initialize the SQLite database with required tables"""
    try:
        # We don't use the context manager here because we might need specific setup logic
        # or to ensure specific PRAGMAs that stick (they persist on the file anyway).
        with sqlite3.connect(DB_FILE) as conn:
            # Persist WAL on the database file (set once, survives across connections)
            conn.execute("PRAGMA journal_mode=WAL;")
            cursor = conn.cursor()

            # Create weather cache table with additional indexes for performance
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS weather_cache (
                    cache_key TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL
                )
            """
            )

            # Add index for faster cache expiration checks
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_weather_cache_expires_at
                ON weather_cache(expires_at)
                """
            )

            # Create alerts table with additional indexes
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS alerts (
                    province TEXT,
                    district TEXT,
                    forecast_days INTEGER,
                    alert_text TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    PRIMARY KEY (province, district, forecast_days)
                )
            """
            )

            # Add index for faster alert lookups by province and forecast_days
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_alerts_province_days
                ON alerts(province, forecast_days)
                """
            )

            # Add index for faster alert lookups by expiration
            cursor.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_alerts_expires_at
                ON alerts(expires_at)
                """
            )

            conn.commit()
            logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")


def get_weather_cache(cache_key: str) -> pd.DataFrame | None:
    """Retrieve weather data from cache, checking expiration"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT data, created_at FROM weather_cache
                WHERE cache_key = ? AND expires_at > CURRENT_TIMESTAMP
                """,
                (cache_key,),
            )
            row = cursor.fetchone()

            if row:
                data_json, _ = row
                try:
                    data_dict = json.loads(data_json)
                    # Convert back to DataFrame
                    return pd.DataFrame.from_records(data_dict)
                except Exception as e:
                    logger.warning(f"Error parsing weather cache data for {cache_key}: {e}")
                    # This CM commits at the end, so the same cursor can delete now.
                    cursor.execute("DELETE FROM weather_cache WHERE cache_key = ?", (cache_key,))
            return None
    except Exception:
        # Error logged in context manager
        return None


def get_raw_weather_cache(cache_key: str) -> tuple[dict, datetime] | None:
    """Retrieve raw JSON weather data from cache with timestamp"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT data, created_at FROM weather_cache
                WHERE cache_key = ? AND expires_at > CURRENT_TIMESTAMP
                """,
                (cache_key,),
            )
            row = cursor.fetchone()

            if row:
                data_dict = json.loads(row[0])
                created_at = datetime.fromisoformat(row[1]) if isinstance(row[1], str) else row[1]
                return data_dict, created_at
            return None
    except Exception:
        return None


def get_stale_raw_weather_cache(cache_key: str) -> tuple[dict, datetime] | None:
    """Retrieve cached weather regardless of expiry for upstream-failure fallback."""
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT data, created_at FROM weather_cache WHERE cache_key = ?",
                (cache_key,),
            ).fetchone()
            if not row:
                return None

            created_at = datetime.fromisoformat(row[1]) if isinstance(row[1], str) else row[1]
            return json.loads(row[0]), created_at
    except Exception:
        return None


def set_raw_weather_cache(cache_key: str, data: dict):
    """Save raw JSON weather data to cache with expiration"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            data_json = json.dumps(data)
            expires_at = datetime.now().replace(microsecond=0) + pd.Timedelta(
                seconds=Config.CACHE_TIME
            )

            cursor.execute(
                """
                INSERT OR REPLACE INTO weather_cache (cache_key, data, created_at, expires_at)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?)
            """,
                (cache_key, data_json, expires_at),
            )
    except Exception as e:
        # Cache writes are best-effort: a failure must never fail the request.
        logger.warning(f"Failed to write weather cache for {cache_key}: {e}")


def set_weather_cache(cache_key: str, df: pd.DataFrame):
    """Save weather data to cache with expiration"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # Serialize DataFrame to JSON string
            data_json = df.to_json(orient="records", date_format="iso")
            expires_at = datetime.now().replace(microsecond=0) + pd.Timedelta(
                seconds=Config.CACHE_TIME
            )

            cursor.execute(
                """
                INSERT OR REPLACE INTO weather_cache (cache_key, data, created_at, expires_at)
                VALUES (?, ?, CURRENT_TIMESTAMP, ?)
            """,
                (cache_key, data_json, expires_at),
            )
    except Exception as e:
        # Cache writes are best-effort: a failure must never fail the request.
        logger.warning(f"Failed to write weather cache for {cache_key}: {e}")


def save_alert(province: str, district: str, forecast_days: int, alert_text: str):
    """Save generated alert to database with expiration"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            expires_at = datetime.now().replace(microsecond=0) + pd.Timedelta(
                seconds=Config.CACHE_TIME
            )

            cursor.execute(
                """
                INSERT OR REPLACE INTO alerts
                    (province, district, forecast_days, alert_text, created_at, expires_at)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?)
            """,
                (province, district, forecast_days, alert_text, expires_at),
            )
    except Exception as e:
        # Alert persistence is best-effort: never fail the generating request.
        logger.warning(f"Failed to save alert for {province}/{district}: {e}")


def get_alert(province: str, district: str, forecast_days: int) -> str | None:
    """Retrieve alert from database, checking cache expiration"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT alert_text FROM alerts
                WHERE province = ? AND district = ? AND forecast_days = ?
                  AND expires_at > CURRENT_TIMESTAMP
            """,
                (province, district, forecast_days),
            )
            row = cursor.fetchone()
            if row:
                return row[0]
            return None
    except Exception:
        return None


def get_all_alerts(forecast_days: int) -> dict[str, dict[str, str]]:
    """Retrieve all alerts for a specific forecast duration, checking cache expiration"""
    alerts = {}
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT province, district, alert_text FROM alerts
                WHERE forecast_days = ? AND expires_at > CURRENT_TIMESTAMP
            """,
                (forecast_days,),
            )
            rows = cursor.fetchall()

            for province, district, alert_text in rows:
                if province not in alerts:
                    alerts[province] = {}
                alerts[province][district] = alert_text

        return alerts
    except Exception:
        logger.error("Error retrieving all alerts")
        return {}


def purge_cache_db(province: str, districts: list[str], forecast_days: int) -> int:
    """Delete alerts from database for specific districts"""
    try:
        with get_db_connection() as conn:
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
                count = cursor.rowcount

                # Also delete related weather cache
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

            return count
    except Exception:
        return 0


def get_raw_weather_cache_batch(
    cache_keys: list[str],
) -> dict[str, tuple[dict, datetime]]:
    """Retrieve multiple raw JSON weather data from cache in a single query"""
    results = {}
    if not cache_keys:
        return results

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            # SQLite allows many parameters, but it's safe to batch them if > 999
            # For now assuming < 999 keys
            placeholders = ",".join(["?"] * len(cache_keys))
            select_sql = "SELECT cache_key, data, created_at FROM weather_cache"
            # noqa below: only "?" placeholders are interpolated, every value is a bound param.
            where_sql = f"cache_key IN ({placeholders}) AND expires_at > CURRENT_TIMESTAMP"  # noqa: S608
            query = f"{select_sql} WHERE {where_sql}"  # noqa: S608
            cursor.execute(query, cache_keys)
            rows = cursor.fetchall()

            for key, data_json, created_at_str in rows:
                try:
                    data_dict = json.loads(data_json)
                    created_at = (
                        datetime.fromisoformat(created_at_str)
                        if isinstance(created_at_str, str)
                        else created_at_str
                    )
                    results[key] = (data_dict, created_at)
                except Exception as e:
                    logger.warning(f"Error parsing batch weather cache for {key}: {e}")
                    continue

            return results
    except Exception:
        return results


def get_alerts_batch(
    province_district_days: list[tuple[str, str, int]],
) -> dict[tuple[str, str, int], str]:
    """Retrieve multiple alerts in a single query"""
    results = {}
    if not province_district_days:
        return results

    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Build the query with a composite-key IN clause (SQLite tuple syntax).
            # Many ORs are slow; a temporary table would be the next step at scale.
            # noqa below: only "?" placeholders are interpolated, values are bound params.
            tuple_values = ",".join(["(?, ?, ?)"] * len(province_district_days))
            where_sql = f"(province, district, forecast_days) IN (VALUES {tuple_values})"  # noqa: S608
            select_sql = "SELECT province, district, forecast_days, alert_text FROM alerts"
            query = f"{select_sql} WHERE {where_sql} AND expires_at > CURRENT_TIMESTAMP"  # noqa: S608

            # Flatten params
            params = []
            for item in province_district_days:
                params.extend(item)

            try:
                cursor.execute(query, params)
            except sqlite3.OperationalError:
                # Fallback to OR syntax if strict tuple syntax fails on older SQLite
                logger.warning("Tuple syntax failed, falling back to OR conditions")
                conditions = []
                params = []
                for province, district, days in province_district_days:
                    conditions.append("(province = ? AND district = ? AND forecast_days = ?)")
                    params.extend([province, district, days])

                or_sql = " OR ".join(conditions)
                query = f"{select_sql} WHERE {or_sql} AND expires_at > CURRENT_TIMESTAMP"  # noqa: S608
                cursor.execute(query, params)

            rows = cursor.fetchall()

            for province, district, forecast_days, alert_text in rows:
                results[(province, district, forecast_days)] = alert_text

            return results
    except Exception:
        return results


def get_cache_stats() -> dict[str, int]:
    """Get cache statistics for monitoring"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Get weather cache count
            cursor.execute(
                "SELECT COUNT(*) FROM weather_cache WHERE expires_at > CURRENT_TIMESTAMP"
            )
            weather_count = cursor.fetchone()[0]

            # Get alerts count
            cursor.execute("SELECT COUNT(*) FROM alerts WHERE expires_at > CURRENT_TIMESTAMP")
            alerts_count = cursor.fetchone()[0]

            # Get expired records count (for cleanup statistics)
            cursor.execute(
                "SELECT COUNT(*) FROM weather_cache WHERE expires_at <= CURRENT_TIMESTAMP"
            )
            expired_weather_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM alerts WHERE expires_at <= CURRENT_TIMESTAMP")
            expired_alerts_count = cursor.fetchone()[0]

            return {
                "weather_cache_count": weather_count,
                "alerts_count": alerts_count,
                "expired_weather_count": expired_weather_count,
                "expired_alerts_count": expired_alerts_count,
            }
    except Exception:
        return {
            "weather_cache_count": 0,
            "alerts_count": 0,
            "expired_weather_count": 0,
            "expired_alerts_count": 0,
        }


def cleanup_expired_cache():
    """Remove expired cache entries"""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()

            # Delete expired weather cache entries
            cursor.execute("DELETE FROM weather_cache WHERE expires_at <= CURRENT_TIMESTAMP")
            weather_deleted = cursor.rowcount

            # Delete expired alerts
            cursor.execute("DELETE FROM alerts WHERE expires_at <= CURRENT_TIMESTAMP")
            alerts_deleted = cursor.rowcount

            logger.info(
                f"Cleaned up {weather_deleted} expired weather cache entries "
                f"and {alerts_deleted} expired alerts"
            )
            return weather_deleted + alerts_deleted
    except Exception:
        return 0
