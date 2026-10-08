"""Tests for building the district registry from coordinates and boundaries."""

from typing import Any

import pytest

from ews.districts.build import build_registry


def square(west: float, south: float, size: float = 1.0) -> dict[str, Any]:
    """A square MultiPolygon with its south-west corner at the given point."""
    east, north = west + size, south + size
    ring = [[west, south], [east, south], [east, north], [west, north], [west, south]]
    return {"type": "MultiPolygon", "coordinates": [[ring]]}


def feature(district: str, province: str, geometry: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "Feature",
        "properties": {"DISTRICT": district, "PROVINCE": province},
        "geometry": geometry,
    }


def collection(*features: dict[str, Any]) -> dict[str, Any]:
    return {"type": "FeatureCollection", "features": list(features)}


class TestBuildRegistry:
    """Test cases for build_registry"""

    def test_district_matches_boundary_with_the_same_name(self) -> None:
        build = build_registry(
            coordinates={"PUNJAB": {"LAHORE": [0.5, 0.5]}},
            boundaries=collection(feature("Lahore", "PUNJAB", square(0, 0))),
            overrides={},
        )

        assert build.districts == [
            {
                "id": "lahore",
                "name_en": "Lahore",
                "name_ur": None,
                "province": "Punjab",
                "lat": 0.5,
                "lon": 0.5,
                "feature_id": "lahore",
            }
        ]

    def test_boundary_features_carry_a_feature_id(self) -> None:
        build = build_registry(
            coordinates={"PUNJAB": {"LAHORE": [0.5, 0.5]}},
            boundaries=collection(feature("LAHORE", "PUNJAB", square(0, 0))),
            overrides={},
        )

        properties = build.boundaries["features"][0]["properties"]
        assert properties == {
            "feature_id": "lahore",
            "boundary_name": "LAHORE",
            "boundary_province": "PUNJAB",
        }

    def test_unmatched_district_gets_no_boundary_and_is_reported(self) -> None:
        """A district is never attached to a polygon with a different name."""
        build = build_registry(
            coordinates={"PUNJAB": {"DERA GHAZI KHAN": [0.5, 0.5]}},
            boundaries=collection(feature("D G KHAN", "PUNJAB", square(0, 0))),
            overrides={},
        )

        assert build.districts[0]["feature_id"] is None
        assert "DERA GHAZI KHAN" in build.report
        # The polygon containing the district's coordinates is offered as a hint
        assert "D G KHAN" in build.report

    def test_override_attaches_a_district_to_a_named_boundary(self) -> None:
        build = build_registry(
            coordinates={"PUNJAB": {"DERA GHAZI KHAN": [0.5, 0.5]}},
            boundaries=collection(feature("D G KHAN", "PUNJAB", square(0, 0))),
            overrides={"DERA GHAZI KHAN": "D G KHAN"},
        )

        assert build.districts[0]["feature_id"] == "d-g-khan"
        assert "DERA GHAZI KHAN" in build.report

    def test_override_naming_a_missing_boundary_is_an_error(self) -> None:
        with pytest.raises(ValueError, match="NOWHERE"):
            build_registry(
                coordinates={"PUNJAB": {"LAHORE": [0.5, 0.5]}},
                boundaries=collection(feature("LAHORE", "PUNJAB", square(0, 0))),
                overrides={"LAHORE": "NOWHERE"},
            )

    def test_two_districts_cannot_share_a_boundary(self) -> None:
        with pytest.raises(ValueError, match="LAHORE"):
            build_registry(
                coordinates={"PUNJAB": {"LAHORE": [0.5, 0.5], "KASUR": [0.6, 0.6]}},
                boundaries=collection(feature("LAHORE", "PUNJAB", square(0, 0))),
                overrides={"KASUR": "LAHORE"},
            )

    def test_boundary_without_a_district_is_reported(self) -> None:
        build = build_registry(
            coordinates={"PUNJAB": {"LAHORE": [0.5, 0.5]}},
            boundaries=collection(
                feature("LAHORE", "PUNJAB", square(0, 0)),
                feature("FR BANNU", "FATA", square(5, 5)),
            ),
            overrides={},
        )

        assert "FR BANNU" in build.report
        assert len(build.boundaries["features"]) == 2

    def test_coordinates_outside_the_matched_boundary_are_reported(self) -> None:
        build = build_registry(
            coordinates={"BALOCHISTAN": {"SIBI": [9.0, 9.0]}},
            boundaries=collection(feature("SIBI", "BALOCHISTAN", square(0, 0))),
            overrides={},
        )

        assert build.districts[0]["feature_id"] == "sibi"
        assert "outside" in build.report
        assert "SIBI" in build.report

    def test_province_disagreement_is_reported(self) -> None:
        build = build_registry(
            coordinates={"KHYBER PAKHTUNKHWA": {"KHYBER AGENCY": [0.5, 0.5]}},
            boundaries=collection(feature("KHYBER AGENCY", "FATA", square(0, 0))),
            overrides={},
        )

        assert build.districts[0]["province"] == "Khyber Pakhtunkhwa"
        assert "FATA" in build.report

    def test_duplicate_district_names_are_an_error(self) -> None:
        with pytest.raises(ValueError, match="LAHORE"):
            build_registry(
                coordinates={
                    "PUNJAB": {"LAHORE": [0.5, 0.5]},
                    "SINDH": {"Lahore": [5.5, 5.5]},
                },
                boundaries=collection(feature("LAHORE", "PUNJAB", square(0, 0))),
                overrides={},
            )

    def test_boundary_coordinates_are_rounded(self) -> None:
        geometry = square(0.123456789, 0.987654321)
        build = build_registry(
            coordinates={"PUNJAB": {"LAHORE": [1.5, 0.6]}},
            boundaries=collection(feature("LAHORE", "PUNJAB", geometry)),
            overrides={},
        )

        ring = build.boundaries["features"][0]["geometry"]["coordinates"][0][0]
        assert ring[0] == [0.1235, 0.9877]
