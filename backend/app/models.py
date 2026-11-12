"""Shared API contracts (see context/IMPLEMENTATION_PLAN.md section 5).

Conventions: compass degrees clockwise from north (0=N, 90=E, 180=S, 270=W). Local metre frames use
x = east, y = north, origin at the roof centroid. All rings are closed (first point == last point).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

Ring = list[tuple[float, float]]
RoofType = Literal["flat", "single_slope", "gable"]
Facing = Literal["auto", "N", "NE", "E", "SE", "S", "SW", "W", "NW"]


class LatLon(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class RoofModel(BaseModel):
    id: str
    source: Literal["osm", "drawn", "sketch", "photo"]
    polygon_lonlat: Ring
    polygon_m: Ring
    area_m2: float
    roof_type: RoofType
    tilt_deg: float
    azimuth_deg: float
    setback_m: float
    usable_fraction: float  # usable polygon area / roof area, after setback and obstruction allowance
    obstruction_factor: float  # cap applied to the panel count by the layout step
    usable_polygon_m: Ring
    usable_area_m2: float
    confidence: Literal["high", "medium", "low"]
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    edges_m: list[float] = Field(default_factory=list)
    anchor: LatLon | None = None
    centroid: LatLon
    origin_utm: tuple[float, float]
    utm_epsg: int
    scale_source: str | None = None


class FinalizeRequest(BaseModel):
    polygon_lonlat: Ring = Field(min_length=3, max_length=500)
    roof_type: RoofType = "flat"
    tilt_deg: float | None = Field(default=None, ge=0, le=60)
    azimuth_deg: float | None = Field(default=None, ge=0, lt=360)
    facing: Facing = "auto"
    setback_m: float | None = Field(default=None, ge=0, le=5)


class SketchRequest(BaseModel):
    points_px: list[tuple[float, float]] = Field(min_length=3, max_length=500)
    px_per_m: float = Field(gt=0)
    scale_source: Literal["default_grid", "user_measured"] = "default_grid"
    north_deg: float = Field(default=0, ge=-360, le=360)
    facing: Facing = "auto"
    azimuth_deg: float | None = Field(default=None, ge=0, lt=360)
    anchor: LatLon | None = None
    roof_type: RoofType = "flat"
    tilt_deg: float | None = Field(default=None, ge=0, le=60)
    setback_m: float | None = Field(default=None, ge=0, le=5)

    @field_validator("points_px")
    @classmethod
    def _finite(cls, v):
        for x, y in v:
            if abs(x) > 1e6 or abs(y) > 1e6:
                raise ValueError("canvas coordinates out of range")
        return v


class FromAddressRequest(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class PanelSpec(BaseModel):
    length_m: float = Field(default=2.28, gt=0.3, le=4)
    width_m: float = Field(default=1.13, gt=0.3, le=3)


class LayoutRequest(BaseModel):
    roof: RoofModel
    panel: PanelSpec = Field(default_factory=PanelSpec)
