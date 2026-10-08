"""District registry and boundary endpoints."""

from typing import Annotated, Any

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select

from ews.api.dependencies import SessionDep
from ews.districts.models import District
from ews.districts.registry import packaged_boundaries

router = APIRouter(prefix="/districts", tags=["districts"])


class DistrictOut(BaseModel):
    """A district in the registry."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    name_en: str
    name_ur: str | None
    province: str
    lat: float
    lon: float
    feature_id: str | None


@router.get("")
async def list_districts(
    session: SessionDep,
    province: Annotated[
        str | None, Query(description="Province name, case-insensitive")
    ] = None,
) -> list[DistrictOut]:
    """List districts, optionally limited to one province."""
    statement = select(District).order_by(District.province, District.name_en)
    if province is not None:
        statement = statement.where(func.lower(District.province) == province.lower())

    districts = (await session.scalars(statement)).all()
    if province is not None and not districts:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown province: {province}",
        )
    return [DistrictOut.model_validate(district) for district in districts]


@router.get("/geojson")
async def district_boundaries(session: SessionDep) -> dict[str, Any]:
    """Boundary polygons as GeoJSON, each tagged with the district it belongs to.

    Polygons with no district in the registry are included with a null
    ``district_id`` so the map has no holes.
    """
    districts = (await session.scalars(select(District))).all()
    by_feature = {d.feature_id: d for d in districts if d.feature_id is not None}

    features = []
    for feature in packaged_boundaries()["features"]:
        source = feature["properties"]
        district = by_feature.get(source["feature_id"])
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "feature_id": source["feature_id"],
                    "district_id": district.id if district else None,
                    "name_en": district.name_en
                    if district
                    else source["boundary_name"],
                    "province": district.province
                    if district
                    else source["boundary_province"],
                },
                "geometry": feature["geometry"],
            }
        )
    return {"type": "FeatureCollection", "features": features}
