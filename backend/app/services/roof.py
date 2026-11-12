"""Roof geometry: projection, validation, azimuth guess, usable polygon, canvas sketch conversion."""
from __future__ import annotations

import math
import uuid
from functools import lru_cache

from pyproj import Transformer
from shapely.geometry import MultiPolygon, Point, Polygon
from shapely.validation import explain_validity

from ..errors import ApiError
from ..models import FinalizeRequest, LatLon, RoofModel, SketchRequest
from .assumptions import A

FACING_DEG = {"N": 0.0, "NE": 45.0, "E": 90.0, "SE": 135.0, "S": 180.0, "SW": 225.0, "W": 270.0, "NW": 315.0}
MANILA = LatLon(lat=14.5995, lon=120.9842)
MIN_AREA_M2, MAX_AREA_M2 = 8.0, 1500.0  # outside this range the roof is flagged low confidence
HARD_MIN_AREA_M2, HARD_MAX_AREA_M2 = 2.0, 50_000.0  # outside this range the polygon is rejected


def utm_epsg_for(lon: float, lat: float) -> int:
    zone = int((lon + 180) // 6) + 1
    return (32600 if lat >= 0 else 32700) + zone


@lru_cache(maxsize=16)
def _transformers(epsg: int) -> tuple[Transformer, Transformer]:
    fwd = Transformer.from_crs(4326, epsg, always_xy=True)
    inv = Transformer.from_crs(epsg, 4326, always_xy=True)
    return fwd, inv


def to_utm(lon: float, lat: float, epsg: int) -> tuple[float, float]:
    return _transformers(epsg)[0].transform(lon, lat)


def from_utm(x: float, y: float, epsg: int) -> tuple[float, float]:
    """Returns (lon, lat)."""
    return _transformers(epsg)[1].transform(x, y)


def _closed(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = [(float(x), float(y)) for x, y in ring]
    if pts and pts[0] != pts[-1]:
        pts.append(pts[0])
    return pts


def _largest(geom) -> Polygon | None:
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, Polygon):
        return geom
    if isinstance(geom, MultiPolygon):
        return max(geom.geoms, key=lambda g: g.area)
    parts = [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]
    return max(parts, key=lambda g: g.area) if parts else None


def ring_bearing_axis(poly: Polygon) -> tuple[float, float, float]:
    """Return (long_axis_bearing_deg in [0,180), long_len, short_len) of the minimum rotated rectangle."""
    mrr = poly.minimum_rotated_rectangle
    c = list(mrr.exterior.coords)
    e1 = (c[1][0] - c[0][0], c[1][1] - c[0][1])
    e2 = (c[2][0] - c[1][0], c[2][1] - c[1][1])
    l1, l2 = math.hypot(*e1), math.hypot(*e2)
    long_vec, long_len, short_len = (e1, l1, l2) if l1 >= l2 else (e2, l2, l1)
    bearing = math.degrees(math.atan2(long_vec[0], long_vec[1])) % 180.0
    return bearing, long_len, short_len


def _ang_dist(a: float, b: float) -> float:
    return abs((a - b + 180.0) % 360.0 - 180.0)


def guess_azimuth(poly: Polygon) -> tuple[float, list[str]]:
    """Roof plane faces perpendicular to the long axis, whichever side is closest to south."""
    bearing, long_len, short_len = ring_bearing_axis(poly)
    if short_len <= 0 or long_len / short_len < 1.15:
        return 180.0, ["Roof is nearly square, so the facing direction was assumed to be south. Please confirm it."]
    cands = [(bearing + 90.0) % 360.0, (bearing + 270.0) % 360.0]
    d = [_ang_dist(c, 180.0) for c in cands]
    if abs(d[0] - d[1]) < 1e-6:
        west = min(cands, key=lambda c: _ang_dist(c, 270.0))
        return west, ["The long axis runs north-south, so the roof faces east or west. West was assumed. Please confirm it."]
    return cands[d.index(min(d))], []


def _half_plane(poly: Polygon, azimuth_deg: float) -> Polygon | None:
    """Gable approximation: keep the half of the footprint on the side the chosen azimuth faces."""
    cx, cy = poly.centroid.x, poly.centroid.y
    nx, ny = math.sin(math.radians(azimuth_deg)), math.cos(math.radians(azimuth_deg))
    ux, uy = -ny, nx  # along the ridge
    big = 10_000.0
    half = Polygon([
        (cx + ux * big, cy + uy * big),
        (cx - ux * big, cy - uy * big),
        (cx - ux * big + nx * big, cy - uy * big + ny * big),
        (cx + ux * big + nx * big, cy + uy * big + ny * big),
    ])
    return _largest(poly.intersection(half))


def _edges(ring: list[tuple[float, float]]) -> list[float]:
    return [round(math.hypot(b[0] - a[0], b[1] - a[1]), 3) for a, b in zip(ring[:-1], ring[1:])]


def build_roof(
    poly_utm: Polygon,
    epsg: int,
    *,
    source: str,
    roof_type: str,
    tilt_deg: float | None,
    azimuth_deg: float | None,
    facing: str,
    setback_m: float | None,
    anchor: LatLon | None = None,
    scale_source: str | None = None,
    notes: list[str] | None = None,
    force_low: bool = False,
) -> RoofModel:
    """Core builder. poly_utm is in UTM metres (any origin)."""
    notes = list(notes or [])
    warnings: list[str] = []
    if not poly_utm.is_valid:
        raise ApiError("invalid_polygon", f"The outline is not a valid shape ({explain_validity(poly_utm)}).",
                       hint="Redraw it without crossing edges.", status=422)
    area = poly_utm.area
    if area < HARD_MIN_AREA_M2 or area > HARD_MAX_AREA_M2:
        raise ApiError("invalid_area", f"The outline covers {area:.1f} m², which is not a plausible roof.",
                       hint="Check the scale or redraw the outline.", status=422)
    confidence = {"osm": "high", "drawn": "medium", "sketch": "medium", "photo": "low"}[source]
    if source == "sketch" and scale_source != "user_measured":
        confidence = "low"
        warnings.append("The scale was not measured. Enter one real measurement to improve accuracy.")
    if area < MIN_AREA_M2 or area > MAX_AREA_M2:
        confidence = "low"
        warnings.append(f"A roof area of {area:.0f} m² looks unusual. Please check the outline and scale.")
    if force_low:
        confidence = "low"

    cx, cy = poly_utm.centroid.x, poly_utm.centroid.y
    local = Polygon([(x - cx, y - cy) for x, y in poly_utm.exterior.coords])
    clon, clat = from_utm(cx, cy, epsg)

    # Azimuth: explicit value > facing choice > geometry guess (flat roofs default to south).
    if azimuth_deg is not None:
        az = float(azimuth_deg) % 360.0
    elif facing != "auto":
        az = FACING_DEG[facing]
    elif roof_type == "flat":
        az = 180.0
    else:
        az, extra = guess_azimuth(local)
        notes.extend(extra)
    if roof_type == "flat" and azimuth_deg is None and facing == "auto":
        notes.append("Flat roof: panels are assumed to face south on tilted racks.")

    tilt = float(tilt_deg) if tilt_deg is not None else (A("default_tilt_flat_deg") if roof_type == "flat" else A("default_tilt_pitched_deg"))
    setback = float(setback_m) if setback_m is not None else A("setback_m")
    obstruction = A("usable_fraction_obstruction")

    plane = local
    if roof_type == "gable":
        half = _half_plane(local, az)
        if half is None:
            half = local
        plane = half
        notes.append("Gable roof: modelled as one plane using the half of the footprint that faces the chosen direction.")
    elif roof_type == "single_slope":
        notes.append("Single-slope roof: one plane over the whole footprint.")

    usable = _largest(plane.buffer(-setback, join_style=2)) if setback > 0 else plane
    if usable is None or usable.is_empty:
        warnings.append("The roof is too small after the edge setback, so no panels fit.")
        usable = Polygon()
    usable_ring = _closed(list(usable.exterior.coords)) if not usable.is_empty else []
    usable_area = usable.area if not usable.is_empty else 0.0

    ring_m = _closed(list(local.exterior.coords))
    ring_ll = [from_utm(x + cx, y + cy, epsg) for x, y in ring_m]
    return RoofModel(
        id=uuid.uuid4().hex[:12],
        source=source,  # type: ignore[arg-type]
        polygon_lonlat=_closed([(lon, lat) for lon, lat in ring_ll]),
        polygon_m=ring_m,
        area_m2=round(area, 2),
        roof_type=roof_type,  # type: ignore[arg-type]
        tilt_deg=tilt,
        azimuth_deg=round(az, 2),
        setback_m=setback,
        usable_fraction=round(min(1.0, usable_area * obstruction / area), 4) if area else 0.0,
        obstruction_factor=obstruction,
        usable_polygon_m=usable_ring,
        usable_area_m2=round(usable_area * obstruction, 2),
        confidence=confidence,  # type: ignore[arg-type]
        notes=notes,
        warnings=warnings,
        edges_m=_edges(ring_m),
        anchor=anchor,
        centroid=LatLon(lat=clat, lon=clon),
        origin_utm=(cx, cy),
        utm_epsg=epsg,
        scale_source=scale_source,
    )


def _clean_ring(ring: list[tuple[float, float]]) -> list[tuple[float, float]]:
    pts = [(float(x), float(y)) for x, y in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    dedup: list[tuple[float, float]] = []
    for p in pts:
        if not dedup or p != dedup[-1]:
            dedup.append(p)
    if len(dedup) < 3:
        raise ApiError("invalid_polygon", "An outline needs at least 3 distinct points.", status=422)
    return dedup


def roof_from_lonlat(ring_lonlat: list[tuple[float, float]], *, source: str, req: FinalizeRequest | None = None,
                     notes: list[str] | None = None, anchor: LatLon | None = None) -> RoofModel:
    req = req or FinalizeRequest(polygon_lonlat=ring_lonlat)
    pts = _clean_ring(ring_lonlat)
    for lon, lat in pts:
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ApiError("invalid_polygon", "Coordinates must be [longitude, latitude] in degrees.", status=422)
    lon0 = sum(p[0] for p in pts) / len(pts)
    lat0 = sum(p[1] for p in pts) / len(pts)
    epsg = utm_epsg_for(lon0, lat0)
    poly = Polygon([to_utm(lon, lat, epsg) for lon, lat in pts])
    return build_roof(
        poly, epsg, source=source, roof_type=req.roof_type, tilt_deg=req.tilt_deg, azimuth_deg=req.azimuth_deg,
        facing=req.facing, setback_m=req.setback_m, anchor=anchor, notes=notes,
    )


def finalize(req: FinalizeRequest) -> RoofModel:
    return roof_from_lonlat(req.polygon_lonlat, source="drawn", req=req)


def sketch_to_roof(req: SketchRequest) -> RoofModel:
    """Canvas pixels -> metres -> rotate by north_deg -> place the centroid at the anchor."""
    pts_px = _clean_ring([tuple(p) for p in req.points_px])
    theta = math.radians(req.north_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    en: list[tuple[float, float]] = []
    for x_px, y_px in pts_px:
        x = x_px / req.px_per_m
        y = -y_px / req.px_per_m  # canvas y points down
        en.append((x * cos_t + y * sin_t, -x * sin_t + y * cos_t))
    poly_local = Polygon(en)
    notes: list[str] = []
    anchor = req.anchor
    if anchor is None:
        anchor = MANILA
        notes.append("No location was given for this sketch, so Metro Manila was assumed for the sunlight data.")
    epsg = utm_epsg_for(anchor.lon, anchor.lat)
    ax, ay = to_utm(anchor.lon, anchor.lat, epsg)
    c = poly_local.centroid
    poly_utm = Polygon([(x - c.x + ax, y - c.y + ay) for x, y in poly_local.exterior.coords])
    return build_roof(
        poly_utm, epsg, source="sketch", roof_type=req.roof_type, tilt_deg=req.tilt_deg,
        azimuth_deg=req.azimuth_deg, facing=req.facing, setback_m=req.setback_m,
        anchor=anchor, scale_source=req.scale_source, notes=notes,
    )


def poly_from_ring(ring: list[tuple[float, float]]) -> Polygon:
    return Polygon(ring) if ring else Polygon()


def point_in_roof(roof: RoofModel, lon: float, lat: float) -> bool:
    x, y = to_utm(lon, lat, roof.utm_epsg)
    return Polygon([(px + roof.origin_utm[0], py + roof.origin_utm[1]) for px, py in roof.polygon_m]).contains(Point(x, y))


__all__ = ["finalize", "sketch_to_roof", "roof_from_lonlat", "build_roof", "guess_azimuth", "utm_epsg_for",
           "to_utm", "from_utm"]
