"""Tests for the district registry endpoints and packaged data."""

from httpx import AsyncClient

from ews.districts.build import (
    PACKAGED_DIR,
    REPORT_PATH,
    build_from_sources,
    serialise_boundaries,
    serialise_districts,
)


class TestListDistricts:
    """Test cases for GET /api/districts"""

    async def test_returns_every_district(self, client: AsyncClient) -> None:
        response = await client.get("/api/districts")

        districts = response.json()
        assert response.status_code == 200
        assert len(districts) == 155
        assert {
            "id": "lahore",
            "name_en": "Lahore",
            "name_ur": None,
            "province": "Punjab",
            "lat": 31.461437162052533,
            "lon": 74.35523137379523,
            "feature_id": "lahore",
        } in districts

    async def test_filters_by_province_ignoring_case(self, client: AsyncClient) -> None:
        response = await client.get("/api/districts", params={"province": "punjab"})

        districts = response.json()
        assert len(districts) == 36
        assert {district["province"] for district in districts} == {"Punjab"}

    async def test_unknown_province_is_not_found(self, client: AsyncClient) -> None:
        response = await client.get("/api/districts", params={"province": "Atlantis"})

        assert response.status_code == 404
        assert response.json() == {"detail": "Unknown province: Atlantis"}


class TestDistrictBoundaries:
    """Test cases for GET /api/districts/geojson"""

    async def test_returns_every_boundary_feature(self, client: AsyncClient) -> None:
        response = await client.get("/api/districts/geojson")

        collection = response.json()
        assert response.status_code == 200
        assert collection["type"] == "FeatureCollection"
        assert len(collection["features"]) == 161

    async def test_features_carry_their_district(self, client: AsyncClient) -> None:
        response = await client.get("/api/districts/geojson")

        properties = {
            feature["properties"]["feature_id"]: feature["properties"]
            for feature in response.json()["features"]
        }
        assert properties["lahore"] == {
            "feature_id": "lahore",
            "district_id": "lahore",
            "name_en": "Lahore",
            "province": "Punjab",
        }
        # Spelled differently in the boundary file; joined by a reviewed override
        assert properties["d-g-khan"]["district_id"] == "dera-ghazi-khan"

    async def test_boundary_without_a_district_has_no_district_id(
        self, client: AsyncClient
    ) -> None:
        response = await client.get("/api/districts/geojson")

        properties = {
            feature["properties"]["feature_id"]: feature["properties"]
            for feature in response.json()["features"]
        }
        assert properties["fr-bannu"] == {
            "feature_id": "fr-bannu",
            "district_id": None,
            "name_en": "FR BANNU",
            "province": "FATA",
        }


class TestPackagedRegistry:
    """The generated files in the repository match what the sources produce."""

    def test_packaged_files_are_up_to_date(self) -> None:
        build = build_from_sources()

        def packaged(name: str) -> str:
            return (PACKAGED_DIR / name).read_text(encoding="utf-8")

        assert packaged("districts.json") == serialise_districts(build.districts)
        assert packaged("districts.geojson") == serialise_boundaries(build.boundaries)
        assert REPORT_PATH.read_text(encoding="utf-8") == build.report

    def test_every_district_has_a_boundary(self) -> None:
        build = build_from_sources()

        assert [d["id"] for d in build.districts if d["feature_id"] is None] == []
