"""Panel packing inside the usable roof polygon (greedy grid in the roof's principal frame)."""
from __future__ import annotations

import math

import numpy as np
import shapely
from shapely.geometry import Polygon

from ..models import PanelSpec, RoofModel
from .roof import from_utm, ring_bearing_axis

PANEL_GAP_M = 0.02
FLAT_ROW_GAP_M = 0.3


def _rotate(poly: Polygon, angle_deg: float) -> Polygon:
    return shapely.affinity.rotate(poly, angle_deg, origin=(0, 0))


def _grid_boxes(poly: Polygon, a: float, b: float, step_x: float, step_y: float, off_x: float, off_y: float):
    minx, miny, maxx, maxy = poly.bounds
    xs = np.arange(minx + off_x, maxx - a + 1e-9, step_x)
    ys = np.arange(miny + off_y, maxy - b + 1e-9, step_y)
    if len(xs) == 0 or len(ys) == 0:
        return np.empty((0, 4))
    gx, gy = np.meshgrid(xs, ys)
    gx, gy = gx.ravel(), gy.ravel()
    return np.column_stack([gx, gy, gx + a, gy + b])


def pack_panels(roof: RoofModel, panel: PanelSpec) -> dict:
    usable = Polygon(roof.usable_polygon_m)
    result = {
        "count_fit": 0, "count": 0, "orientation": None, "panel": panel.model_dump(),
        "panels_m": [], "panels_lonlat": [], "notes": [],
        "obstruction_factor": roof.obstruction_factor,
    }
    if usable.is_empty or usable.area < panel.length_m * panel.width_m:
        result["notes"].append("No panels fit inside the usable area.")
        return result

    angle, _, _ = ring_bearing_axis(usable)
    rot = _rotate(usable, 90 - angle)  # long axis -> x
    shapely.prepare(rot)
    flat = roof.roof_type == "flat"
    cos_t = math.cos(math.radians(roof.tilt_deg)) if flat else 1.0
    row_gap = FLAT_ROW_GAP_M if flat else PANEL_GAP_M

    best: tuple[int, str, np.ndarray] | None = None
    for orient, (a, b) in {"landscape": (panel.length_m, panel.width_m), "portrait": (panel.width_m, panel.length_m)}.items():
        # Simplification: treat y (across the roof's long axis) as the slope direction, so on tilted
        # flat-roof racks the footprint along y is the panel dimension times cos(tilt).
        foot_b = b * cos_t if flat else b
        foot_a = a
        step_x = foot_a + PANEL_GAP_M
        step_y = foot_b + row_gap
        for off_x, off_y in ((0, 0), (step_x / 2, 0), (0, step_y / 2), (step_x / 2, step_y / 2)):
            boxes = _grid_boxes(rot, foot_a, foot_b, step_x, step_y, off_x, off_y)
            if not len(boxes):
                continue
            geoms = shapely.box(boxes[:, 0], boxes[:, 1], boxes[:, 2], boxes[:, 3])
            ok = shapely.contains(rot, geoms)
            n = int(ok.sum())
            if best is None or n > best[0]:
                best = (n, orient, boxes[ok])
    if best is None or best[0] == 0:
        result["notes"].append("No panels fit inside the usable area.")
        return result

    n_fit, orient, boxes = best
    cap = int(math.floor(n_fit * roof.obstruction_factor))
    # Order panels by distance from the roof centre: capping keeps the most compact block, and callers can
    # take the first N panels for a smaller system.
    cx, cy = rot.centroid.x, rot.centroid.y
    centres = np.column_stack([(boxes[:, 0] + boxes[:, 2]) / 2 - cx, (boxes[:, 1] + boxes[:, 3]) / 2 - cy])
    order = np.argsort(np.hypot(centres[:, 0], centres[:, 1]), kind="stable")[:cap]
    boxes = boxes[order]
    result.update(count_fit=n_fit, count=len(boxes), orientation=orient)

    ox, oy = roof.origin_utm
    for x0, y0, x1, y1 in boxes:
        ring = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        back = shapely.affinity.rotate(Polygon(ring), -(90 - angle), origin=(0, 0))
        pts = [(float(x), float(y)) for x, y in back.exterior.coords]
        result["panels_m"].append(pts)
        ll = [from_utm(x + ox, y + oy, roof.utm_epsg) for x, y in pts]
        result["panels_lonlat"].append([(lon, lat) for lon, lat in ll])
    if roof.roof_type == "flat":
        result["notes"].append("Flat surface: row spacing uses a fixed 0.3 m gap between tilted rows (simplified, not a shading study).")
    result["notes"].append(f"Panel count is capped at {roof.obstruction_factor:.0%} of what fits, to leave room for vents and tanks.")
    return result


def panel_capacity(roof: RoofModel, length_m: float, width_m: float) -> int:
    """Max panel count for a given panel size (used by the optimizer)."""
    return pack_panels(roof, PanelSpec(length_m=length_m, width_m=width_m))["count"]


__all__ = ["pack_panels", "panel_capacity"]
