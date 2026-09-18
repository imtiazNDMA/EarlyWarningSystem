from datetime import UTC, datetime, timedelta

import pandas as pd

from repositories.memory import InMemoryRepository


def test_raw_weather_round_trip_and_batch():
    repository = InMemoryRepository(cache_time=60)
    weather = {"daily": {"time": ["2026-09-18"], "temperature_2m_max": [36.0]}}

    repository.set_raw_weather_cache("weather_3_PUNJAB_LAHORE", weather)

    cached = repository.get_raw_weather_cache("weather_3_PUNJAB_LAHORE")
    batch = repository.get_raw_weather_cache_batch(
        ["weather_3_PUNJAB_LAHORE", "weather_3_PUNJAB_MULTAN"]
    )
    assert cached is not None
    assert cached[0] == weather
    assert cached[1].tzinfo is UTC
    assert batch["weather_3_PUNJAB_LAHORE"][0] == weather


def test_dataframe_round_trip():
    repository = InMemoryRepository(cache_time=60)
    dataframe = pd.DataFrame({"Date": ["2026-09-18"], "Max Temp (°C)": [36.0]})

    repository.set_weather_cache("forecast_PUNJAB_LAHORE_3", dataframe)

    pd.testing.assert_frame_equal(
        repository.get_weather_cache("forecast_PUNJAB_LAHORE_3"), dataframe
    )


def test_alert_round_trip_batch_and_all():
    repository = InMemoryRepository(cache_time=60)
    repository.save_alert("PUNJAB", "LAHORE", 3, '{"english":"Hot","urdu":"گرم"}')
    repository.save_alert("SINDH", "KARACHI", 3, "Legacy alert")

    assert repository.get_alert("PUNJAB", "LAHORE", 3) is not None
    assert repository.get_alerts_batch(
        [("PUNJAB", "LAHORE", 3), ("PUNJAB", "MULTAN", 3)]
    ) == {("PUNJAB", "LAHORE", 3): '{"english":"Hot","urdu":"گرم"}'}
    assert repository.get_all_alerts(3)["SINDH"]["KARACHI"] == "Legacy alert"


def test_expired_records_are_excluded_immediately():
    now = datetime(2026, 9, 18, tzinfo=UTC)
    repository = InMemoryRepository(cache_time=60, clock=lambda: now)
    repository.set_raw_weather_cache("weather_1_PUNJAB_LAHORE", {"daily": {}})
    repository.save_alert("PUNJAB", "LAHORE", 1, "alert")

    repository.clock = lambda: now + timedelta(seconds=60)

    assert repository.get_raw_weather_cache("weather_1_PUNJAB_LAHORE") is None
    assert repository.get_alert("PUNJAB", "LAHORE", 1) is None


def test_purge_removes_exact_scope_and_preserves_unrelated_records():
    repository = InMemoryRepository(cache_time=60)
    repository.set_raw_weather_cache("weather_3_PUNJAB_LAHORE", {"daily": {}})
    repository.set_weather_cache(
        "forecast_PUNJAB_LAHORE_3", pd.DataFrame({"Date": ["2026-09-18"]})
    )
    repository.set_raw_weather_cache("weather_3_PUNJAB_MULTAN", {"daily": {}})
    repository.save_alert("PUNJAB", "LAHORE", 3, "alert")
    repository.save_alert("PUNJAB", "MULTAN", 3, "other")

    count = repository.purge_cache("PUNJAB", ["LAHORE"], 3)

    assert count == 3
    assert repository.get_raw_weather_cache("weather_3_PUNJAB_LAHORE") is None
    assert repository.get_weather_cache("forecast_PUNJAB_LAHORE_3") is None
    assert repository.get_alert("PUNJAB", "LAHORE", 3) is None
    assert repository.get_raw_weather_cache("weather_3_PUNJAB_MULTAN") is not None
    assert repository.get_alert("PUNJAB", "MULTAN", 3) == "other"
