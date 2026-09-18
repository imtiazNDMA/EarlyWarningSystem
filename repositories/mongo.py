from datetime import UTC, datetime, timedelta

import pandas as pd
from pymongo import ASCENDING, MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

from domain.forecast import ForecastRun
from repositories.keys import parse_cache_key


class MongoRepository:
    """MongoDB adapter for cache and alert persistence."""

    def __init__(
        self,
        uri: str,
        database_name: str,
        cache_time: int = 43200,
        timeout_ms: int = 5000,
    ) -> None:
        self.cache_time = cache_time
        self.client = MongoClient(
            uri,
            serverSelectionTimeoutMS=timeout_ms,
            connectTimeoutMS=timeout_ms,
            tz_aware=True,
        )
        database = self.client[database_name]
        self.weather = database["weather_cache"]
        self.alerts = database["alerts"]
        self.forecast_runs = database["forecast_runs"]
        self.refresh_leases = database["forecast_refresh_leases"]

    def initialize(self) -> None:
        self.ping()
        self.weather.create_index(
            [("expires_at", ASCENDING)], expireAfterSeconds=0, name="ttl_weather_cache"
        )
        self.weather.create_index(
            [
                ("province", ASCENDING),
                ("forecast_days", ASCENDING),
                ("district", ASCENDING),
            ],
            name="weather_scope_lookup",
        )
        self.alerts.create_index(
            [
                ("province", ASCENDING),
                ("district", ASCENDING),
                ("forecast_days", ASCENDING),
            ],
            unique=True,
            name="uq_alert_scope",
        )
        self.alerts.create_index(
            [("expires_at", ASCENDING)], expireAfterSeconds=0, name="ttl_alerts"
        )
        self.initialize_forecast_runs()

    def initialize_forecast_runs(self) -> None:
        self.forecast_runs.create_index(
            [("run_id", ASCENDING)], unique=True, name="uq_forecast_run_id"
        )
        self.forecast_runs.create_index(
            [
                ("location.location_id", ASCENDING),
                ("requested_days", ASCENDING),
                ("retrieved_at", -1),
            ],
            name="latest_forecast_run",
        )
        self.forecast_runs.create_index(
            [
                ("location.location_id", ASCENDING),
                ("requested_days", ASCENDING),
                ("checksum", ASCENDING),
            ],
            unique=True,
            name="uq_forecast_snapshot",
        )
        self.refresh_leases.create_index(
            [("expires_at", ASCENDING)],
            expireAfterSeconds=0,
            name="ttl_forecast_refresh_leases",
        )

    def save_forecast_run(self, run: ForecastRun) -> bool:
        try:
            self.forecast_runs.insert_one(run.to_document())
            return True
        except DuplicateKeyError:
            self.forecast_runs.update_one(
                {
                    "location.location_id": run.location.location_id,
                    "requested_days": run.requested_days,
                    "checksum": run.checksum,
                },
                {
                    "$set": {
                        "retrieved_at": run.retrieved_at,
                        "fresh_until": run.fresh_until,
                        "usable_until": run.usable_until,
                        "source_url": run.source_url,
                    }
                },
            )
            return False

    def get_latest_forecast_run(
        self, location_id: str, forecast_days: int
    ) -> ForecastRun | None:
        document = self.forecast_runs.find_one(
            {
                "location.location_id": location_id,
                "requested_days": forecast_days,
            },
            sort=[("retrieved_at", -1)],
        )
        return ForecastRun.from_document(document) if document else None

    def acquire_refresh_lease(
        self, location_id: str, forecast_days: int, lease_seconds: int = 120
    ) -> bool:
        now = datetime.now(UTC)
        key = f"{location_id}:{forecast_days}"
        try:
            document = self.refresh_leases.find_one_and_update(
                {
                    "_id": key,
                    "$or": [
                        {"expires_at": {"$lte": now}},
                        {"expires_at": {"$exists": False}},
                    ],
                },
                {
                    "$set": {
                        "location_id": location_id,
                        "forecast_days": forecast_days,
                        "expires_at": now + timedelta(seconds=lease_seconds),
                    }
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            return document is not None
        except DuplicateKeyError:
            return False

    def release_refresh_lease(self, location_id: str, forecast_days: int) -> None:
        self.refresh_leases.delete_one({"_id": f"{location_id}:{forecast_days}"})

    def ping(self) -> None:
        self.client.admin.command("ping")

    def _times(self) -> tuple[datetime, datetime]:
        now = datetime.now(UTC)
        return now, now + timedelta(seconds=self.cache_time)

    def get_weather_cache(self, cache_key: str) -> pd.DataFrame | None:
        document = self.weather.find_one(
            {
                "_id": cache_key,
                "kind": "dataframe",
                "expires_at": {"$gt": datetime.now(UTC)},
            }
        )
        return (
            pd.DataFrame.from_records(document["payload"])
            if document is not None
            else None
        )

    def _weather_document(self, cache_key: str, payload, kind: str) -> dict:
        created_at, expires_at = self._times()
        scope = parse_cache_key(cache_key)
        return {
            "_id": cache_key,
            "kind": kind,
            "payload": payload,
            "created_at": created_at,
            "expires_at": expires_at,
            "province": scope.province,
            "district": scope.district,
            "forecast_days": scope.forecast_days,
            "purpose": scope.purpose,
            "schema_version": 1,
        }

    def set_weather_cache(self, cache_key: str, dataframe: pd.DataFrame) -> None:
        self.weather.replace_one(
            {"_id": cache_key},
            self._weather_document(
                cache_key, dataframe.to_dict(orient="records"), "dataframe"
            ),
            upsert=True,
        )

    def get_raw_weather_cache(self, cache_key: str):
        document = self.weather.find_one(
            {"_id": cache_key, "kind": "raw", "expires_at": {"$gt": datetime.now(UTC)}}
        )
        if document is None:
            return None
        return document["payload"], document["created_at"]

    def set_raw_weather_cache(self, cache_key: str, data: dict) -> None:
        self.weather.replace_one(
            {"_id": cache_key},
            self._weather_document(cache_key, data, "raw"),
            upsert=True,
        )

    def get_raw_weather_cache_batch(self, cache_keys: list[str]) -> dict:
        if not cache_keys:
            return {}
        documents = self.weather.find(
            {
                "_id": {"$in": cache_keys},
                "kind": "raw",
                "expires_at": {"$gt": datetime.now(UTC)},
            }
        )
        return {
            document["_id"]: (document["payload"], document["created_at"])
            for document in documents
        }

    def save_alert(
        self, province: str, district: str, forecast_days: int, alert_text: str
    ) -> None:
        created_at, expires_at = self._times()
        identity = {
            "province": province,
            "district": district,
            "forecast_days": forecast_days,
        }
        self.alerts.replace_one(
            identity,
            {
                **identity,
                "alert_text": alert_text,
                "created_at": created_at,
                "expires_at": expires_at,
                "schema_version": 1,
            },
            upsert=True,
        )

    def get_alert(self, province: str, district: str, forecast_days: int) -> str | None:
        document = self.alerts.find_one(
            {
                "province": province,
                "district": district,
                "forecast_days": forecast_days,
                "expires_at": {"$gt": datetime.now(UTC)},
            }
        )
        return document["alert_text"] if document else None

    def get_all_alerts(self, forecast_days: int) -> dict[str, dict[str, str]]:
        results: dict[str, dict[str, str]] = {}
        for document in self.alerts.find(
            {"forecast_days": forecast_days, "expires_at": {"$gt": datetime.now(UTC)}}
        ):
            results.setdefault(document["province"], {})[document["district"]] = (
                document["alert_text"]
            )
        return results

    def get_alerts_batch(self, keys: list[tuple[str, str, int]]) -> dict:
        if not keys:
            return {}
        clauses = [
            {"province": province, "district": district, "forecast_days": days}
            for province, district, days in set(keys)
        ]
        documents = self.alerts.find(
            {"$or": clauses, "expires_at": {"$gt": datetime.now(UTC)}}
        )
        return {
            (
                document["province"],
                document["district"],
                document["forecast_days"],
            ): document["alert_text"]
            for document in documents
        }

    def purge_cache(
        self, province: str, districts: list[str], forecast_days: int
    ) -> int:
        scope: dict = {"province": province, "forecast_days": forecast_days}
        if districts:
            scope["district"] = {"$in": districts}
        alert_result = self.alerts.delete_many(scope)
        weather_result = self.weather.delete_many(scope)
        return alert_result.deleted_count + weather_result.deleted_count

    def get_cache_stats(self) -> dict[str, int]:
        now = datetime.now(UTC)
        return {
            "weather_cache_count": self.weather.count_documents(
                {"expires_at": {"$gt": now}}
            ),
            "alerts_count": self.alerts.count_documents({"expires_at": {"$gt": now}}),
            "expired_weather_count": self.weather.count_documents(
                {"expires_at": {"$lte": now}}
            ),
            "expired_alerts_count": self.alerts.count_documents(
                {"expires_at": {"$lte": now}}
            ),
        }

    def cleanup_expired_cache(self) -> int:
        now = datetime.now(UTC)
        weather_result = self.weather.delete_many({"expires_at": {"$lte": now}})
        alert_result = self.alerts.delete_many({"expires_at": {"$lte": now}})
        return weather_result.deleted_count + alert_result.deleted_count
