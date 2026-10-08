"""Build the district registry from the coordinate table and a boundary file.

A district is attached to a boundary only when their names match exactly (ignoring
case and punctuation) or when an explicit, reviewed override says so. Everything
else is written to a report for the owner; nothing is matched by guesswork.

Run ``python -m ews.districts.build`` from ``backend/`` to regenerate the packaged
registry, the boundary file and the report from the files in ``data/source``.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

COORDINATE_PRECISION = 4  # decimal degrees; about 11 metres

BACKEND_ROOT = Path(__file__).resolve().parents[3]
SOURCE_DIR = BACKEND_ROOT / "data" / "source"
REPORT_PATH = BACKEND_ROOT / "data" / "district_mismatch_report.md"
PACKAGED_DIR = Path(__file__).resolve().parent / "data"

Point = tuple[float, float]  # (lon, lat)


@dataclass(frozen=True)
class RegistryBuild:
    """Result of a registry build."""

    districts: list[dict[str, Any]]
    boundaries: dict[str, Any]
    report: str


def slugify(name: str) -> str:
    """Turn a name into a stable lower-case identifier."""
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def normalise(name: str) -> str:
    """Reduce a name to upper-case letters and digits for exact comparison."""
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def _ring_contains(ring: list[list[float]], point: Point) -> bool:
    """Ray-casting test for a point inside a closed ring."""
    x, y = point
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:], strict=False):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def geometry_contains(geometry: dict[str, Any], point: Point) -> bool:
    """Whether a Polygon or MultiPolygon contains the point, honouring holes."""
    polygons = (
        [geometry["coordinates"]]
        if geometry["type"] == "Polygon"
        else geometry["coordinates"]
    )
    for outer, *holes in polygons:
        if _ring_contains(outer, point) and not any(
            _ring_contains(hole, point) for hole in holes
        ):
            return True
    return False


def _round_ring(ring: list[list[float]]) -> list[list[float]]:
    """Round a ring's coordinates and drop the repeats rounding creates."""
    rounded: list[list[float]] = []
    for x, y, *_ in ring:
        point = [round(x, COORDINATE_PRECISION), round(y, COORDINATE_PRECISION)]
        if not rounded or rounded[-1] != point:
            rounded.append(point)
    return rounded


def _round_geometry(geometry: dict[str, Any]) -> dict[str, Any]:
    """Reduce coordinate precision; rings that collapse to a sliver are dropped."""
    polygons = (
        [geometry["coordinates"]]
        if geometry["type"] == "Polygon"
        else geometry["coordinates"]
    )
    rounded_polygons = []
    for polygon in polygons:
        rings = [ring for ring in map(_round_ring, polygon) if len(ring) >= 4]
        if rings:
            rounded_polygons.append(rings)
    return {"type": "MultiPolygon", "coordinates": rounded_polygons}


def _build_features(boundaries: dict[str, Any]) -> list[dict[str, Any]]:
    """Give every boundary feature a unique feature_id and trimmed properties."""
    features = []
    seen: dict[str, str] = {}
    for source in boundaries["features"]:
        name = source["properties"]["DISTRICT"]
        feature_id = slugify(name)
        if feature_id in seen:
            raise ValueError(
                f"Boundary names {seen[feature_id]!r} and {name!r} share the "
                f"feature id {feature_id!r}"
            )
        seen[feature_id] = name
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "feature_id": feature_id,
                    "boundary_name": name,
                    "boundary_province": source["properties"]["PROVINCE"],
                },
                "geometry": _round_geometry(source["geometry"]),
            }
        )
    return features


def _table(headers: list[str], rows: list[list[str]]) -> list[str]:
    """Render a markdown table, or a placeholder when there are no rows."""
    if not rows:
        return ["None.", ""]
    lines = [
        "| " + " | ".join(headers) + " |",
        "|" + "|".join(" --- " for _ in headers) + "|",
    ]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return [*lines, ""]


def build_registry(  # noqa: C901 - one pass over the districts, read top to bottom
    coordinates: dict[str, dict[str, list[float]]],
    boundaries: dict[str, Any],
    overrides: dict[str, str],
) -> RegistryBuild:
    """Join the coordinate table to the boundary file.

    Args:
        coordinates: Province name -> district name -> [lat, lon]
        boundaries: GeoJSON FeatureCollection with DISTRICT and PROVINCE properties
        overrides: District name -> boundary DISTRICT name, for reviewed cases
            where the two files spell the same district differently

    Returns:
        The registry rows, the cleaned boundary collection and a markdown report

    Raises:
        ValueError: If names collide, an override names an unknown district or a
            missing boundary, or two districts claim the same boundary
    """
    features = _build_features(boundaries)
    by_name = {normalise(f["properties"]["boundary_name"]): f for f in features}

    known_districts = {name for names in coordinates.values() for name in names}
    for name, target in overrides.items():
        if name not in known_districts:
            raise ValueError(f"Override names an unknown district: {name!r}")
        if normalise(target) not in by_name:
            raise ValueError(
                f"Override for {name!r} names a boundary that does not exist: "
                f"{target!r}"
            )

    districts: list[dict[str, Any]] = []
    claimed: dict[str, str] = {}  # feature_id -> district name
    district_ids: dict[str, str] = {}

    via_override: list[list[str]] = []
    unmatched: list[list[str]] = []
    province_differs: list[list[str]] = []
    outside: list[list[str]] = []

    for province, province_districts in coordinates.items():
        for name, (lat, lon) in province_districts.items():
            district_id = slugify(name)
            if district_id in district_ids:
                raise ValueError(
                    f"District names {district_ids[district_id]!r} and {name!r} "
                    f"share the id {district_id!r}"
                )
            district_ids[district_id] = name
            point: Point = (lon, lat)

            matched = by_name.get(normalise(name))
            if name in overrides:
                # An explicit override wins over a same-name match
                matched = by_name[normalise(overrides[name])]
                contains = geometry_contains(matched["geometry"], point)
                via_override.append(
                    [
                        name,
                        province,
                        matched["properties"]["boundary_name"],
                        "yes" if contains else "NO",
                    ]
                )

            feature_id = None
            if matched is None:
                candidates = [
                    f["properties"]["boundary_name"]
                    for f in features
                    if geometry_contains(f["geometry"], point)
                ]
                unmatched.append([name, province, ", ".join(candidates) or "none"])
            else:
                feature_id = matched["properties"]["feature_id"]
                if feature_id in claimed:
                    raise ValueError(
                        f"Districts {claimed[feature_id]!r} and {name!r} both "
                        f"claim the boundary {matched['properties']['boundary_name']!r}"
                    )
                claimed[feature_id] = name

                boundary_province = matched["properties"]["boundary_province"]
                if normalise(boundary_province) != normalise(province):
                    province_differs.append([name, province, boundary_province])
                if not geometry_contains(matched["geometry"], point):
                    outside.append([name, province, f"{lat}, {lon}"])

            districts.append(
                {
                    "id": district_id,
                    "name_en": name.title(),
                    "name_ur": None,
                    "province": province.title(),
                    "lat": lat,
                    "lon": lon,
                    "feature_id": feature_id,
                }
            )

    unused = [
        [f["properties"]["boundary_name"], f["properties"]["boundary_province"]]
        for f in features
        if f["properties"]["feature_id"] not in claimed
    ]

    exact = len(claimed) - len(via_override)
    report = [
        "# District registry: boundary match report",
        "",
        "Generated by `python -m ews.districts.build`. Do not edit by hand; change",
        "the files in `data/source` and rebuild.",
        "",
        f"- Districts: {len(districts)}",
        f"- Boundary features: {len(features)}",
        f"- Matched by exact name: {exact}",
        f"- Matched by reviewed override: {len(via_override)}",
        f"- Districts with no boundary: {len(unmatched)}",
        f"- Boundary features with no district: {len(unused)}",
        "",
        "## Matched by override (confirm each one)",
        "",
        "These districts are spelled differently in the two files. Each pairing",
        "comes from `data/source/boundary_overrides.json`. The last column says",
        "whether the district's own coordinates fall inside the boundary.",
        "",
        *_table(
            ["District", "Province", "Boundary name", "Coordinates inside"],
            via_override,
        ),
        "## Districts with no boundary",
        "",
        "These districts are in the registry but are not drawn on the map. To",
        "attach one, add an override after checking the candidate.",
        "",
        *_table(
            ["District", "Province", "Boundaries containing its coordinates"],
            unmatched,
        ),
        "## Boundary features with no district",
        "",
        "These polygons are drawn on the map but have no forecasts or alerts.",
        "",
        *_table(["Boundary name", "Boundary province"], unused),
        "## Province differs between the two files",
        "",
        "The registry uses the province from the coordinate table.",
        "",
        *_table(
            ["District", "Coordinate table province", "Boundary file province"],
            province_differs,
        ),
        "## Coordinates outside the matched boundary",
        "",
        "The name matches, but the district's forecast point lies outside its own",
        "polygon. Check the coordinates.",
        "",
        *_table(["District", "Province", "Coordinates (lat, lon)"], outside),
    ]

    return RegistryBuild(
        districts=districts,
        boundaries={"type": "FeatureCollection", "features": features},
        report="\n".join(report).rstrip("\n") + "\n",
    )


def build_from_sources() -> RegistryBuild:
    """Build the registry from the committed source files."""

    def read(name: str) -> Any:
        return json.loads((SOURCE_DIR / name).read_text(encoding="utf-8"))

    return build_registry(
        coordinates=read("district_coordinates.json"),
        boundaries=read("district_boundaries.geojson"),
        overrides=read("boundary_overrides.json"),
    )


def serialise_districts(districts: list[dict[str, Any]]) -> str:
    """Registry file content: readable, one district per block."""
    return json.dumps(districts, ensure_ascii=False, indent=2) + "\n"


def serialise_boundaries(boundaries: dict[str, Any]) -> str:
    """Boundary file content: compact, since it is large and not hand-edited."""
    return json.dumps(boundaries, ensure_ascii=False, separators=(",", ":")) + "\n"


def main() -> None:
    """Regenerate the packaged registry, boundary file and report."""
    build = build_from_sources()
    PACKAGED_DIR.mkdir(parents=True, exist_ok=True)
    outputs = {
        PACKAGED_DIR / "districts.json": serialise_districts(build.districts),
        PACKAGED_DIR / "districts.geojson": serialise_boundaries(build.boundaries),
        REPORT_PATH: build.report,
    }
    for path, content in outputs.items():
        path.write_text(content, encoding="utf-8", newline="\n")
        print(f"wrote {path.relative_to(BACKEND_ROOT)} ({len(content):,} characters)")  # noqa: T201


if __name__ == "__main__":
    main()
