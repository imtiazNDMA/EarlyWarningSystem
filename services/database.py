"""Application-scoped persistence access.

Callers use these functions while the composition root supplies the concrete
repository adapter. This compatibility module keeps persistence concerns out of
route and domain logic during the MongoDB migration.
"""

from flask import current_app

from repositories.base import Repository


def get_repository() -> Repository:
    """Return the repository registered for the current application."""
    return current_app.extensions["repository"]


def init_db() -> None:
    get_repository().initialize()


def get_weather_cache(cache_key: str):
    return get_repository().get_weather_cache(cache_key)


def set_weather_cache(cache_key: str, dataframe) -> None:
    get_repository().set_weather_cache(cache_key, dataframe)


def get_raw_weather_cache(cache_key: str):
    return get_repository().get_raw_weather_cache(cache_key)


def set_raw_weather_cache(cache_key: str, data: dict) -> None:
    get_repository().set_raw_weather_cache(cache_key, data)


def get_raw_weather_cache_batch(cache_keys: list[str]) -> dict:
    return get_repository().get_raw_weather_cache_batch(cache_keys)


def save_alert(
    province: str, district: str, forecast_days: int, alert_text: str
) -> None:
    get_repository().save_alert(province, district, forecast_days, alert_text)


def get_alert(province: str, district: str, forecast_days: int):
    return get_repository().get_alert(province, district, forecast_days)


def get_all_alerts(forecast_days: int) -> dict:
    return get_repository().get_all_alerts(forecast_days)


def get_alerts_batch(keys: list[tuple[str, str, int]]) -> dict:
    return get_repository().get_alerts_batch(keys)


def purge_cache_db(province: str, districts: list[str], forecast_days: int) -> int:
    return get_repository().purge_cache(province, districts, forecast_days)


def get_cache_stats() -> dict[str, int]:
    return get_repository().get_cache_stats()


def cleanup_expired_cache() -> int:
    return get_repository().cleanup_expired_cache()
