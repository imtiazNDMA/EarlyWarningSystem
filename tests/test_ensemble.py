from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

from domain.forecast import (
    DataQualityReport,
    DataStatus,
    EnsembleCorroboration,
    ForecastRun,
    Location,
)
from ingestion.coordinator import ForecastIngestionCoordinator
from ingestion.ensemble import OpenMeteoEnsembleProvider
from repositories.memory import InMemoryRepository

NOW = datetime(2026, 9, 18, 6, tzinfo=UTC)
LAHORE = Location("PK-PB-LHE", "PUNJAB", "LAHORE", 31.5204, 74.3587)


def _deterministic_run(checksum: str = "det-1") -> ForecastRun:
    return ForecastRun(
        run_id=f"run-{checksum}",
        provider="open-meteo",
        location=LAHORE,
        requested_days=3,
        retrieved_at=NOW,
        fresh_until=NOW + timedelta(hours=3),
        usable_until=NOW + timedelta(hours=9),
        payload={"daily": {"time": ["2026-09-18"] * 3}},
        quality=DataQualityReport(DataStatus.FRESH, 3, 3),
        checksum=checksum,
        source_url="https://api.open-meteo.com/v1/forecast",
    )


def _ensemble_payload(hours: int = 72) -> dict:
    times = []
    for d in range(1, hours // 24 + 1):
        times.extend([f"2026-09-{d:02d}T{h:02d}:00" for h in range(24)])
    hourly = {"time": times}
    for field in ("temperature_2m", "relative_humidity_2m"):
        ecmwf_key = f"{field}_ecmwf_ifs025_ensemble"
        gefs_key = f"{field}_ncep_gefs_seamless"
        hourly[ecmwf_key] = [25.0 + i * 0.01 for i in range(hours)]
        hourly[gefs_key] = [24.5 + i * 0.01 for i in range(hours)]
        for m in range(1, 6):
            hourly[f"{field}_member{m:02d}_ecmwf_ifs025_ensemble"] = [
                25.0 + m * 0.1 + i * 0.01 for i in range(hours)
            ]
            hourly[f"{field}_member{m:02d}_ncep_gefs_seamless"] = [
                24.5 + m * 0.1 + i * 0.01 for i in range(hours)
            ]
    return {"hourly": hourly}


def test_ensemble_provider_fetches_valid_payload():
    session = MagicMock()
    response = MagicMock()
    response.url = "https://ensemble-api.open-meteo.com/v1/ensemble"
    response.json.return_value = _ensemble_payload(72)
    session.get.return_value = response
    provider = OpenMeteoEnsembleProvider(
        "https://ensemble-api.open-meteo.com/v1/ensemble", 30, 3600, 7200, session
    )

    run = provider.fetch(LAHORE, 3)

    assert run.quality.status == DataStatus.FRESH
    assert run.provider == "open-meteo-ensemble"
    assert run.corroboration is not None
    assert "ecmwf_ifs025_ensemble" in run.corroboration.models
    assert "ncep_gefs_seamless" in run.corroboration.models


def test_ensemble_provider_rejects_missing_hourly():
    session = MagicMock()
    response = MagicMock()
    response.url = "https://ensemble-api.open-meteo.com/v1/ensemble"
    response.json.return_value = {}
    session.get.return_value = response
    provider = OpenMeteoEnsembleProvider(
        "https://ensemble-api.open-meteo.com/v1/ensemble", 30, 3600, 7200, session
    )

    run = provider.fetch(LAHORE, 3)

    assert run.quality.status == DataStatus.INVALID
    assert any("ensemble hourly" in i for i in run.quality.issues)


def test_ensemble_provider_marks_short_horizon_partial():
    session = MagicMock()
    response = MagicMock()
    response.url = "https://ensemble-api.open-meteo.com/v1/ensemble"
    response.json.return_value = _ensemble_payload(48)
    session.get.return_value = response
    provider = OpenMeteoEnsembleProvider(
        "https://ensemble-api.open-meteo.com/v1/ensemble", 30, 3600, 7200, session
    )

    run = provider.fetch(LAHORE, 3)

    assert run.quality.status == DataStatus.PARTIAL


def test_spread_summary_computes_correctly():
    corroboration = EnsembleCorroboration(
        ensemble_payload={
            "hourly": {
                "time": ["2026-09-18T00:00", "2026-09-18T01:00"],
                "temperature_2m_member01_model": [20.0, 21.0],
                "temperature_2m_member02_model": [22.0, 23.0],
                "temperature_2m_member03_model": [24.0, 25.0],
            }
        },
        models=("model",),
        members_per_model={"model": 3},
        checksum="abc",
    )

    summary = corroboration.spread_summary("temperature_2m")

    assert summary["member_count"] == 3
    assert summary["mean"] > 0
    assert summary["spread"] > 0


def test_spread_summary_returns_zeros_for_missing_field():
    corroboration = EnsembleCorroboration(
        ensemble_payload={"hourly": {"time": ["2026-09-18T00:00"]}},
        models=(),
        members_per_model={},
        checksum="abc",
    )

    summary = corroboration.spread_summary("nonexistent_field")

    assert summary == {"mean": 0.0, "spread": 0.0, "member_count": 0}


def test_coordinator_attaches_corroboration():
    repository = InMemoryRepository()
    det_provider = MagicMock()
    det_provider.fetch.return_value = _deterministic_run()
    ens_provider = MagicMock()
    ens_run = ForecastRun(
        run_id="ens-1",
        provider="open-meteo-ensemble",
        location=LAHORE,
        requested_days=3,
        retrieved_at=NOW,
        fresh_until=NOW + timedelta(hours=3),
        usable_until=NOW + timedelta(hours=9),
        payload=_ensemble_payload(72),
        quality=DataQualityReport(DataStatus.FRESH, 3, 3),
        checksum="ens-checksum",
        source_url="https://ensemble-api.open-meteo.com/v1/ensemble",
        corroboration=EnsembleCorroboration(
            ensemble_payload=_ensemble_payload(72),
            models=("ecmwf_ifs025_ensemble", "ncep_gefs_seamless"),
            members_per_model={},
            checksum="ens-checksum",
        ),
    )
    ens_provider.fetch.return_value = ens_run
    coordinator = ForecastIngestionCoordinator(
        det_provider, repository, clock=lambda: NOW, ensemble_provider=ens_provider
    )

    result = coordinator.get_forecast(LAHORE, 3)

    assert result.run is not None
    assert result.run.corroboration is not None
    assert "ecmwf_ifs025_ensemble" in result.run.corroboration.models


def test_coordinator_still_works_when_ensemble_fails():
    repository = InMemoryRepository()
    det_provider = MagicMock()
    det_provider.fetch.return_value = _deterministic_run()
    ens_provider = MagicMock()
    ens_provider.fetch.side_effect = ConnectionError("ensemble unavailable")
    coordinator = ForecastIngestionCoordinator(
        det_provider, repository, clock=lambda: NOW, ensemble_provider=ens_provider
    )

    result = coordinator.get_forecast(LAHORE, 3)

    assert result.run is not None
    assert result.run.corroboration is None
    assert result.status == DataStatus.FRESH


def test_corroboration_roundtrip_through_document():
    corroboration = EnsembleCorroboration(
        ensemble_payload=_ensemble_payload(24),
        models=("ecmwf_ifs025_ensemble", "ncep_gefs_seamless"),
        members_per_model={"ecmwf_ifs025_ensemble": 5, "ncep_gefs_seamless": 5},
        checksum="test-checksum",
    )
    run = ForecastRun(
        run_id="roundtrip-1",
        provider="open-meteo",
        location=LAHORE,
        requested_days=1,
        retrieved_at=NOW,
        fresh_until=NOW + timedelta(hours=1),
        usable_until=NOW + timedelta(hours=3),
        payload={"daily": {}, "hourly": {}},
        quality=DataQualityReport(DataStatus.FRESH, 1, 1),
        checksum="det-checksum",
        source_url="https://api.open-meteo.com/v1/forecast",
        corroboration=corroboration,
    )

    doc = run.to_document()
    restored = ForecastRun.from_document(doc)

    assert restored.corroboration is not None
    assert restored.corroboration.models == (
        "ecmwf_ifs025_ensemble",
        "ncep_gefs_seamless",
    )
    assert restored.corroboration.members_per_model == {
        "ecmwf_ifs025_ensemble": 5,
        "ncep_gefs_seamless": 5,
    }
    assert restored.corroboration.checksum == "test-checksum"
