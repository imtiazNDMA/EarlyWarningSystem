from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from domain.forecast import (
    DataQualityReport,
    DataStatus,
    ForecastRun,
    Location,
)
from ingestion.coordinator import ForecastIngestionCoordinator
from ingestion.open_meteo import OpenMeteoProvider
from repositories.memory import InMemoryRepository

NOW = datetime(2026, 9, 18, 6, tzinfo=UTC)
LAHORE = Location("PK-PB-LHE", "PUNJAB", "LAHORE", 31.5204, 74.3587)


def build_run(
    *,
    retrieved_at: datetime = NOW,
    fresh_until: datetime | None = None,
    usable_until: datetime | None = None,
    checksum: str = "checksum-1",
) -> ForecastRun:
    return ForecastRun(
        run_id=f"run-{checksum}",
        provider="open-meteo",
        location=LAHORE,
        requested_days=3,
        retrieved_at=retrieved_at,
        fresh_until=fresh_until or retrieved_at + timedelta(hours=3),
        usable_until=usable_until or retrieved_at + timedelta(hours=9),
        payload={"daily": {"time": ["2026-09-18"] * 3}},
        quality=DataQualityReport(DataStatus.FRESH, 3, 3),
        checksum=checksum,
        source_url="https://api.open-meteo.com/v1/forecast",
    )


def test_fresh_run_avoids_provider_call():
    repository = InMemoryRepository()
    repository.save_forecast_run(build_run())
    provider = MagicMock()
    coordinator = ForecastIngestionCoordinator(provider, repository, clock=lambda: NOW)

    result = coordinator.get_forecast(LAHORE, 3)

    assert result.status == DataStatus.FRESH
    assert result.refresh_attempted is False
    provider.fetch.assert_not_called()


def test_stale_run_is_served_when_refresh_fails():
    repository = InMemoryRepository()
    repository.save_forecast_run(
        build_run(
            retrieved_at=NOW - timedelta(hours=4),
            fresh_until=NOW - timedelta(hours=1),
            usable_until=NOW + timedelta(hours=2),
        )
    )
    provider = MagicMock()
    provider.fetch.side_effect = ConnectionError("provider unavailable")
    coordinator = ForecastIngestionCoordinator(provider, repository, clock=lambda: NOW)

    result = coordinator.get_forecast(LAHORE, 3)

    assert result.status == DataStatus.STALE_USABLE
    assert result.available is True
    assert result.refresh_error == "provider unavailable"


def test_expired_run_is_not_served_when_refresh_fails():
    repository = InMemoryRepository()
    repository.save_forecast_run(
        build_run(
            retrieved_at=NOW - timedelta(hours=12),
            fresh_until=NOW - timedelta(hours=9),
            usable_until=NOW - timedelta(hours=3),
        )
    )
    provider = MagicMock()
    provider.fetch.side_effect = ConnectionError("provider unavailable")
    coordinator = ForecastIngestionCoordinator(provider, repository, clock=lambda: NOW)

    result = coordinator.get_forecast(LAHORE, 3)

    assert result.status == DataStatus.UNAVAILABLE
    assert result.available is False
    assert result.run is None


def test_concurrent_cache_miss_fetches_once():
    repository = InMemoryRepository()
    provider = MagicMock()
    provider.fetch.return_value = build_run()
    coordinator = ForecastIngestionCoordinator(provider, repository, clock=lambda: NOW)

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(lambda _: coordinator.get_forecast(LAHORE, 3), range(4))
        )

    assert provider.fetch.call_count == 1
    assert all(result.available for result in results)


def test_repository_deduplicates_unchanged_snapshot():
    repository = InMemoryRepository()

    assert repository.save_forecast_run(build_run(checksum="same")) is True
    assert repository.save_forecast_run(build_run(checksum="same")) is False


def test_unchanged_snapshot_renews_stored_freshness():
    repository = InMemoryRepository()
    old = build_run(
        retrieved_at=NOW - timedelta(hours=4),
        fresh_until=NOW - timedelta(hours=1),
        usable_until=NOW + timedelta(hours=2),
        checksum="same",
    )
    refreshed = build_run(checksum="same")
    repository.save_forecast_run(old)
    provider = MagicMock()
    provider.fetch.return_value = refreshed
    coordinator = ForecastIngestionCoordinator(provider, repository, clock=lambda: NOW)

    result = coordinator.get_forecast(LAHORE, 3)
    next_result = coordinator.get_forecast(LAHORE, 3)

    assert result.status == DataStatus.FRESH
    assert next_result.refresh_attempted is False
    assert provider.fetch.call_count == 1


def test_invalid_refresh_does_not_mask_stale_usable_run():
    repository = InMemoryRepository()
    old = build_run(
        retrieved_at=NOW - timedelta(hours=4),
        fresh_until=NOW - timedelta(hours=1),
        usable_until=NOW + timedelta(hours=2),
    )
    invalid = ForecastRun(
        **{
            **build_run(checksum="invalid").__dict__,
            "quality": DataQualityReport(DataStatus.INVALID, 3, 0),
        }
    )
    repository.save_forecast_run(old)
    provider = MagicMock()
    provider.fetch.return_value = invalid
    coordinator = ForecastIngestionCoordinator(provider, repository, clock=lambda: NOW)

    result = coordinator.get_forecast(LAHORE, 3)

    assert result.run == old
    assert result.status == DataStatus.STALE_USABLE
    assert result.refresh_error == "provider returned invalid data"
    assert repository.get_latest_forecast_run(LAHORE.location_id, 3) == old


def test_open_meteo_marks_short_horizon_partial():
    session = MagicMock()
    response = MagicMock()
    response.url = "https://api.open-meteo.com/v1/forecast?test=true"
    response.json.return_value = {
        "daily": {
            "time": ["2026-09-18", "2026-09-19"],
            **{field: [1, 1] for field in OpenMeteoProvider.DAILY_FIELDS},
        }
    }
    session.get.return_value = response
    provider = OpenMeteoProvider(
        "https://api.open-meteo.com/v1/forecast", 10, 3600, 7200, session
    )

    run = provider.fetch(LAHORE, 3)

    assert run.quality.status == DataStatus.PARTIAL
    assert run.quality.returned_days == 2
    assert run.quality.expected_days == 3


def test_open_meteo_accepts_complete_fifteen_day_horizon():
    session = MagicMock()
    response = MagicMock()
    response.url = "https://api.open-meteo.com/v1/forecast?forecast_days=15"
    dates = [f"2026-09-{day:02d}" for day in range(1, 16)]
    response.json.return_value = {
        "daily": {
            "time": dates,
            **{field: [1] * 15 for field in OpenMeteoProvider.DAILY_FIELDS},
        }
    }
    session.get.return_value = response
    provider = OpenMeteoProvider(
        "https://api.open-meteo.com/v1/forecast", 10, 3600, 7200, session
    )

    run = provider.fetch(LAHORE, 15)

    assert run.quality.status == DataStatus.FRESH
    assert run.quality.returned_days == 15
    assert run.requested_days == 15
    assert session.get.call_args.kwargs["params"]["forecast_days"] == 15
