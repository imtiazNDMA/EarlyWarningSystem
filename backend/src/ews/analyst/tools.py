"""Read-only tools the analyst can call while investigating one district."""

import datetime as dt
import json
import math
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ews.alerts.models import Alert
from ews.alerts.service import Screened
from ews.districts.models import District
from ews.sources.open_meteo_air_quality import PM25_UNIT, DailyAirQuality
from ews.sources.open_meteo_air_quality import SOURCE as AIR_QUALITY_SOURCE

EARTH_RADIUS_KM = 6371.0


class GetForecast(BaseModel):
    """Daily weather forecast for this district: rain, temperature, wind and snow."""

    days: int = Field(default=7, ge=1, le=16, description="Days to return, from today")


class GetAirQuality(BaseModel):
    """Daily PM2.5 air-quality forecast for this district, and any signal it raised."""

    days: int = Field(default=5, ge=1, le=7, description="Days to return, from today")


class GetNeighbouringSignals(BaseModel):
    """Hazard signals raised this run in the districts nearest to this one."""

    limit: int = Field(default=6, ge=1, le=10, description="How many districts")


class GetAlertHistory(BaseModel):
    """Alerts issued for this district recently, including ones that have ended."""

    days: int = Field(default=30, ge=1, le=365, description="How far back to look")


class GetDistrictProfile(BaseModel):
    """This district's name, province and location."""


@dataclass(frozen=True)
class ToolResult:
    """What a tool returned, as text for the model."""

    ok: bool
    content: str


def definition(name: str, arguments: type[BaseModel]) -> dict[str, Any]:
    """A tool definition in chat-completions form, from its arguments model."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": (arguments.__doc__ or "").strip(),
            "parameters": arguments.model_json_schema(),
        },
    }


def _distance_km(a: District, b: District) -> float:
    """Great-circle distance between two districts' forecast points."""
    lat_a, lat_b = math.radians(a.lat), math.radians(b.lat)
    half_lat = (lat_b - lat_a) / 2
    half_lon = math.radians(b.lon - a.lon) / 2
    chord = (
        math.sin(half_lat) ** 2
        + math.cos(lat_a) * math.cos(lat_b) * math.sin(half_lon) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(chord))


def _is_air_quality(screened: Screened) -> bool:
    """Whether a screening is of the air-quality source's days."""
    return any(isinstance(day, DailyAirQuality) for day in screened.days)


class Toolbox:
    """The tools for one district, reading this run's screenings and the database.

    The district is fixed when the toolbox is built, so the model cannot ask
    about another one, and nothing here writes.
    """

    def __init__(
        self,
        session: AsyncSession,
        districts: Mapping[str, District],
        screenings: Sequence[Screened],
        district_id: str,
    ) -> None:
        self._session = session
        self._districts = districts
        self._screenings = screenings
        self._district = districts[district_id]
        self._tools: dict[
            str, tuple[type[BaseModel], Callable[[Any], Awaitable[object]]]
        ] = {
            "get_forecast": (GetForecast, self._forecast),
            "get_air_quality": (GetAirQuality, self._air_quality),
            "get_neighbouring_signals": (GetNeighbouringSignals, self._neighbours),
            "get_alert_history": (GetAlertHistory, self._alert_history),
            "get_district_profile": (GetDistrictProfile, self._profile),
        }

    @property
    def definitions(self) -> list[dict[str, Any]]:
        return [
            definition(name, arguments) for name, (arguments, _) in self._tools.items()
        ]

    async def run(self, name: str, arguments: dict[str, Any] | None) -> ToolResult:
        """Run a tool; a bad name or bad arguments come back as a failed result."""
        if name not in self._tools:
            return ToolResult(False, f"Unknown tool: {name}")
        model, handler = self._tools[name]
        try:
            parsed = model.model_validate(arguments)
        except ValidationError as error:
            problems = error.errors(include_url=False, include_input=False)
            return ToolResult(False, f"Invalid arguments: {json.dumps(problems)}")
        return ToolResult(
            True, json.dumps(await handler(parsed), default=str, ensure_ascii=False)
        )

    async def _forecast(self, arguments: GetForecast) -> object:
        return [
            {
                "snapshot_id": screened.snapshot_id,
                "days": [
                    day.model_dump(mode="json")
                    for day in screened.days[: arguments.days]
                ],
            }
            for screened in self._screenings
            if screened.district_id == self._district.id
            and not _is_air_quality(screened)
        ]

    async def _air_quality(self, arguments: GetAirQuality) -> object:
        screened = next(
            (
                screened
                for screened in self._screenings
                if screened.district_id == self._district.id
                and _is_air_quality(screened)
            ),
            None,
        )
        result: dict[str, object] = {
            "source": AIR_QUALITY_SOURCE,
            "measure": "daily mean PM2.5",
            "unit": PM25_UNIT,
            "snapshot_id": screened.snapshot_id if screened else None,
            "days": [
                day.model_dump(mode="json") for day in screened.days[: arguments.days]
            ]
            if screened
            else [],
            "signals": [
                signal.model_dump(
                    mode="json",
                    include={
                        "hazard",
                        "level",
                        "onset",
                        "expires",
                        "peak_value",
                        "threshold",
                    },
                )
                for signal in screened.signals
            ]
            if screened
            else [],
        }
        if screened is None:
            # The source can fail without failing the run
            result["note"] = (
                "No air-quality data was read for this district in this run."
            )
        return result

    async def _neighbours(self, arguments: GetNeighbouringSignals) -> object:
        nearest = sorted(
            (
                (_distance_km(self._district, other), other)
                for other in self._districts.values()
                if other.id != self._district.id
            ),
            key=lambda pair: pair[0],
        )[: arguments.limit]
        return [
            {
                "district": other.name_en,
                "province": other.province,
                "distance_km": round(distance),
                "signals": [
                    signal.model_dump(
                        mode="json",
                        include={"hazard", "level", "onset", "expires", "peak_value"},
                    )
                    for screened in self._screenings
                    if screened.district_id == other.id
                    for signal in screened.signals
                ],
            }
            for distance, other in nearest
        ]

    async def _alert_history(self, arguments: GetAlertHistory) -> object:
        since = dt.datetime.now(dt.UTC) - dt.timedelta(days=arguments.days)
        alerts = await self._session.scalars(
            select(Alert)
            .where(Alert.district_id == self._district.id, Alert.issued_at >= since)
            .order_by(Alert.issued_at.desc())
            .limit(20)
        )
        return [
            {
                "hazard": alert.hazard,
                "severity": alert.severity,
                "status": alert.status,
                "onset": alert.onset,
                "expires": alert.expires,
                "issued_at": alert.issued_at,
            }
            for alert in alerts
        ]

    async def _profile(self, _arguments: GetDistrictProfile) -> object:
        return {
            "id": self._district.id,
            "name": self._district.name_en,
            "province": self._district.province,
            "latitude": round(self._district.lat, 3),
            "longitude": round(self._district.lon, 3),
        }
