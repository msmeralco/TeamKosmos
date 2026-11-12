import math

import pytest
from shapely.geometry import Polygon

from app.errors import ApiError
from app.models import FinalizeRequest, LatLon, PanelSpec, SketchRequest
from app.services import layout, roof

# A 10 m (E-W) x 6 m (N-S) rectangle near Quezon City, built from metre offsets.
LAT, LON = 14.676, 121.0437


def rect_lonlat(w_m=10.0, h_m=6.0, lat=LAT, lon=LON):
    epsg = roof.utm_epsg_for(lon, lat)
    x, y = roof.to_utm(lon, lat, epsg)
    pts = [(x - w_m / 2, y - h_m / 2), (x + w_m / 2, y - h_m / 2), (x + w_m / 2, y + h_m / 2), (x - w_m / 2, y + h_m / 2)]
    return [roof.from_utm(px, py, epsg) for px, py in pts]


def test_utm_zone_for_manila_is_51n():
    assert roof.utm_epsg_for(121.0, 14.6) == 32651


def test_finalize_area_within_one_percent():
    m = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(10, 6), roof_type="flat"))
    assert m.area_m2 == pytest.approx(60.0, rel=0.01)
    assert m.polygon_lonlat[0] == m.polygon_lonlat[-1]
    assert m.azimuth_deg == 180 and m.tilt_deg == 12
    assert m.confidence == "medium" and m.source == "drawn"
    assert sorted(round(e) for e in m.edges_m) == [6, 6, 10, 10]
    assert m.usable_area_m2 < m.area_m2  # setback + obstruction allowance


def test_setback_shrinks_usable_area():
    a = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(), setback_m=0.0))
    b = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(), setback_m=1.0))
    assert b.usable_area_m2 < a.usable_area_m2


def test_facing_and_explicit_azimuth_priority():
    r = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(), facing="SE"))
    assert r.azimuth_deg == 135
    r = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(), facing="SE", azimuth_deg=200))
    assert r.azimuth_deg == 200


def test_azimuth_guess_ew_ridge_faces_south_and_ns_ridge_ties_to_west():
    ew = Polygon([(-5, -3), (5, -3), (5, 3), (-5, 3)])
    assert roof.guess_azimuth(ew)[0] == pytest.approx(180)
    ns = Polygon([(-3, -5), (3, -5), (3, 5), (-3, 5)])
    az, notes = roof.guess_azimuth(ns)
    assert az == pytest.approx(270) and notes
    square = Polygon([(0, 0), (5, 0), (5, 5), (0, 5)])
    az, notes = roof.guess_azimuth(square)
    assert az == 180 and notes


def test_pitched_roof_guesses_azimuth():
    r = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(10, 6), roof_type="single_slope"))
    assert r.azimuth_deg == pytest.approx(180)
    assert r.tilt_deg == 20


def test_gable_uses_half_the_footprint():
    full = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(10, 6), roof_type="single_slope", setback_m=0))
    gable = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(10, 6), roof_type="gable", setback_m=0))
    assert gable.usable_area_m2 == pytest.approx(full.usable_area_m2 / 2, rel=0.05)


def test_invalid_polygons_are_rejected():
    bowtie = [(121.0, 14.6), (121.001, 14.601), (121.001, 14.6), (121.0, 14.601)]
    with pytest.raises(ApiError) as e:
        roof.finalize(FinalizeRequest(polygon_lonlat=bowtie))
    assert e.value.code == "invalid_polygon"
    tiny = [(121.0, 14.6), (121.0000001, 14.6), (121.0000001, 14.6000001)]
    with pytest.raises(ApiError):
        roof.finalize(FinalizeRequest(polygon_lonlat=tiny))
    with pytest.raises(ApiError):
        roof.finalize(FinalizeRequest(polygon_lonlat=[(121.0, 14.6), (121.0, 14.6), (121.0, 14.6)]))


def test_unusual_area_is_low_confidence():
    r = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(2.5, 2.5)))
    assert r.confidence == "low" and r.warnings


# ---- canvas sketch ----------------------------------------------------------------------
def test_sketch_scale_changes_area():
    pts = [(0, 0), (300, 0), (300, 180), (0, 180)]
    a = roof.sketch_to_roof(SketchRequest(points_px=pts, px_per_m=20, scale_source="user_measured"))
    assert a.area_m2 == pytest.approx(135.0, rel=0.001)
    b = roof.sketch_to_roof(SketchRequest(points_px=pts, px_per_m=30, scale_source="user_measured"))
    assert b.area_m2 == pytest.approx(60.0, rel=0.001)
    assert a.confidence == "medium" and a.source == "sketch"


def test_sketch_default_scale_is_low_confidence_and_manila_fallback_noted():
    r = roof.sketch_to_roof(SketchRequest(points_px=[(0, 0), (200, 0), (200, 120), (0, 120)], px_per_m=20))
    assert r.confidence == "low"
    assert any("Metro Manila" in n for n in r.notes)
    assert r.centroid.lat == pytest.approx(roof.MANILA.lat, abs=1e-4)


def test_sketch_is_placed_at_anchor():
    anchor = LatLon(lat=LAT, lon=LON)
    r = roof.sketch_to_roof(SketchRequest(points_px=[(0, 0), (200, 0), (200, 120), (0, 120)], px_per_m=20,
                                          scale_source="user_measured", anchor=anchor))
    assert r.centroid.lat == pytest.approx(LAT, abs=1e-6) and r.centroid.lon == pytest.approx(LON, abs=1e-6)
    # the lon/lat polygon encloses the anchor
    assert roof.point_in_roof(r, LON, LAT)


def test_sketch_y_axis_flip_and_north_rotation():
    # Canvas: wide rectangle (10 m x 4 m). With north_deg=0, up on the canvas is north.
    pts = [(0, 0), (200, 0), (200, 80), (0, 80)]
    r0 = roof.sketch_to_roof(SketchRequest(points_px=pts, px_per_m=20, scale_source="user_measured",
                                           anchor=LatLon(lat=LAT, lon=LON), roof_type="single_slope"))
    ext_e = max(x for x, _ in r0.polygon_m) - min(x for x, _ in r0.polygon_m)
    ext_n = max(y for _, y in r0.polygon_m) - min(y for _, y in r0.polygon_m)
    assert ext_e == pytest.approx(10, abs=0.01) and ext_n == pytest.approx(4, abs=0.01)
    assert r0.azimuth_deg == pytest.approx(180)  # long axis E-W -> faces south
    # north_deg=90: canvas-up points east, so the wide canvas axis (x) now runs north-south.
    r90 = roof.sketch_to_roof(SketchRequest(points_px=pts, px_per_m=20, scale_source="user_measured",
                                            anchor=LatLon(lat=LAT, lon=LON), north_deg=90, roof_type="single_slope"))
    ext_e = max(x for x, _ in r90.polygon_m) - min(x for x, _ in r90.polygon_m)
    ext_n = max(y for _, y in r90.polygon_m) - min(y for _, y in r90.polygon_m)
    assert ext_e == pytest.approx(4, abs=0.01) and ext_n == pytest.approx(10, abs=0.01)
    assert r90.area_m2 == pytest.approx(r0.area_m2, rel=1e-6)


def test_sketch_rejects_degenerate_input():
    with pytest.raises(ApiError):
        roof.sketch_to_roof(SketchRequest(points_px=[(0, 0), (10, 0), (20, 0)], px_per_m=20))  # collinear
    with pytest.raises(ApiError):
        roof.sketch_to_roof(SketchRequest(points_px=[(0, 0), (10, 0), (0, 10), (10, 10)], px_per_m=20))  # bowtie


# ---- layout -------------------------------------------------------------------------------
def test_layout_count_and_containment():
    r = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(10, 6), roof_type="single_slope", setback_m=0.5))
    res = layout.pack_panels(r, PanelSpec())
    assert 6 <= res["count"] <= 12
    assert res["count"] <= res["count_fit"]
    assert len(res["panels_m"]) == res["count"] == len(res["panels_lonlat"])
    usable = Polygon(r.usable_polygon_m).buffer(1e-6)
    for ring in res["panels_m"]:
        assert usable.contains(Polygon(ring))
    # no overlaps
    polys = [Polygon(p) for p in res["panels_m"]]
    for i in range(len(polys)):
        for j in range(i + 1, len(polys)):
            assert polys[i].intersection(polys[j]).area < 1e-6


def test_layout_flat_roof_uses_row_gap_and_fits_fewer():
    pitched = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(14, 10), roof_type="single_slope"))
    flat = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(14, 10), roof_type="flat"))
    assert layout.pack_panels(flat, PanelSpec())["count"] <= layout.pack_panels(pitched, PanelSpec())["count"]


def test_layout_empty_when_roof_too_small():
    r = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(2.5, 2.5)))
    res = layout.pack_panels(r, PanelSpec(length_m=2.28, width_m=1.13))
    assert res["count"] == 0 or res["count"] <= 1


def test_layout_rotated_roof_still_fits_panels():
    # rotate the 10x6 rectangle by 30 degrees in the lon/lat plane via the sketch path
    r = roof.sketch_to_roof(SketchRequest(points_px=[(0, 0), (200, 0), (200, 120), (0, 120)], px_per_m=20,
                                          scale_source="user_measured", north_deg=30, anchor=LatLon(lat=LAT, lon=LON),
                                          roof_type="single_slope"))
    res = layout.pack_panels(r, PanelSpec())
    assert res["count"] >= 6
    usable = Polygon(r.usable_polygon_m).buffer(1e-6)
    assert all(usable.contains(Polygon(p)) for p in res["panels_m"])
    assert math.isfinite(res["panels_lonlat"][0][0][0])
