import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import requests

from domain.forecast import (
    DataQualityReport,
    DataStatus,
    EnsembleCorroboration,
    ForecastRun,
    Location,
    freshness_windows,
)


class OpenMeteoEnsembleProvider:
    """Fetch ensemble forecasts from Open-Meteo for model corroboration."""

    ENSEMBLE_FIELDS = ("temperature_2m", "relative_humidity_2m")

    MODELS = ("ecmwf_ifs025_ensemble", "ncep_gefs_seamless")

    def __init__(
        self,
        base_url: str,
        timeout: int,
        fresh_seconds: int,
        stale_seconds: int,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.fresh_seconds = fresh_seconds
        self.stale_seconds = stale_seconds
        self.session = session or requests.Session()

    def fetch(self, location: Location, forecast_days: int) -> ForecastRun:
        params = {
            "latitude": location.latitude,
            "longitude": location.longitude,
            "hourly": list(self.ENSEMBLE_FIELDS),
            "models": list(self.MODELS),
            "timezone": location.timezone,
            "forecast_days": forecast_days,
        }
        response = self.session.get(self.base_url, params=params, timeout=self.timeout)
        response.raise_for_status()
        payload = response.json()
        retrieved_at = datetime.now(UTC)
        quality = self._validate(payload, forecast_days)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        checksum = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        fresh_until, usable_until = freshness_windows(
            retrieved_at, self.fresh_seconds, self.stale_seconds
        )
        corroboration = self._build_corroboration(payload, checksum)
        return ForecastRun(
            run_id=str(uuid4()),
            provider="open-meteo-ensemble",
            location=location,
            requested_days=forecast_days,
            retrieved_at=retrieved_at,
            fresh_until=fresh_until,
            usable_until=usable_until,
            payload=payload,
            quality=quality,
            checksum=checksum,
            source_url=response.url,
            corroboration=corroboration,
        )

    def _validate(self, payload: dict, forecast_days: int) -> DataQualityReport:
        hourly = payload.get("hourly")
        if not isinstance(hourly, dict):
            return DataQualityReport(
                DataStatus.INVALID,
                forecast_days,
                0,
                issues=("ensemble hourly data missing",),
            )
        times = hourly.get("time")
        if not isinstance(times, list):
            return DataQualityReport(
                DataStatus.INVALID,
                forecast_days,
                0,
                issues=("ensemble hourly time missing",),
            )
        issues: list[str] = []
        for field in self.ENSEMBLE_FIELDS:
            control_key = f"{field}_{'_'.join(self.MODELS[0].split('_')[:2])}"
            member_prefix = f"{field}_member"
            has_control = isinstance(hourly.get(control_key), list)
            has_members = any(
                k.startswith(member_prefix)
                for k in hourly
                if isinstance(hourly[k], list)
            )
            if not has_control and not has_members:
                issues.append(f"ensemble {field} has no control or member data")
        returned_hours = len(times)
        expected_hours = forecast_days * 24
        if issues:
            status = DataStatus.INVALID
        elif returned_hours < expected_hours:
            status = DataStatus.PARTIAL
            issues.append(
                f"ensemble returned {returned_hours} of {expected_hours} expected hours"
            )
        else:
            status = DataStatus.FRESH
        return DataQualityReport(
            status=status,
            expected_days=forecast_days,
            returned_days=forecast_days,
            issues=tuple(issues),
        )

    @staticmethod
    def _build_corroboration(
        payload: dict, checksum: str
    ) -> EnsembleCorroboration:
        hourly = payload.get("hourly", {})
        model_members: dict[str, int] = {}
        for key in hourly:
            if "_member" not in key or key == "time":
                continue
            parts = key.rsplit("_member", 1)
            if len(parts) != 2:
                continue
            suffix = parts[1]
            model_name = suffix.lstrip("0123456789").lstrip("_")
            if not model_name:
                continue
            model_members[model_name] = model_members.get(model_name, 0) + 1
        return EnsembleCorroboration(
            ensemble_payload=payload,
            models=tuple(sorted(model_members.keys())),
            members_per_model=model_members,
            checksum=checksum,
        )
