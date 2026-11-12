import json

import httpx
import pytest

from app.errors import ApiError
from app.services import geo

REAL_DEMO_PATH = geo.DEMO_PATH
NOMINATIM = [{"display_name": "12 Test St, Quezon City, Metro Manila, Philippines", "lat": "14.6760", "lon": "121.0437"},
             {"display_name": "Another place", "lat": "14.5", "lon": "121.0"}]


def square_way(lat=14.7, lon=121.1, half=0.00005, oid=1, tags=None):
    pts = [(lon - half, lat - half), (lon + half, lat - half), (lon + half, lat + half), (lon - half, lat + half), (lon - half, lat - half)]
    return {"type": "way", "id": oid, "tags": tags or {"building": "yes"}, "geometry": [{"lat": y, "lon": x} for x, y in pts]}


@pytest.fixture(autouse=True)
def fast_throttle(monkeypatch):
    monkeypatch.setattr(geo, "MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(geo, "DEMO_PATH", geo.DEMO_PATH.parent / "does_not_exist.geojson")
    yield
    monkeypatch.setattr(geo, "client_factory", None)


def install(monkeypatch, handler):
    calls = []

    def wrapped(request):
        calls.append(request)
        return handler(request)

    monkeypatch.setattr(geo, "client_factory", lambda: httpx.Client(transport=httpx.MockTransport(wrapped)))
    return calls


def test_geocode_uses_user_agent_and_caches(monkeypatch):
    calls = install(monkeypatch, lambda r: httpx.Response(200, json=NOMINATIM))
    first = geo.geocode("12 Test St Quezon City")
    assert [c["source"] for c in first["candidates"]] == ["nominatim", "nominatim"]
    assert first["cached"] is False
    second = geo.geocode("12 test st quezon city")  # same query, different case
    assert second["cached"] is True
    assert len(calls) == 1  # second answer came from cache
    assert "countrycodes=ph" in str(calls[0].url)


def test_geocode_degrades_instead_of_raising(monkeypatch):
    def boom(request):
        raise httpx.ConnectError("offline")

    install(monkeypatch, boom)
    out = geo.geocode("some address in manila")
    assert out["degraded"] is True and out["candidates"] == []


def test_geocode_bad_http_status_is_degraded(monkeypatch):
    install(monkeypatch, lambda r: httpx.Response(429, text="slow down"))
    assert geo.geocode("some address in manila")["degraded"] is True


def test_geocode_validates_query():
    with pytest.raises(ApiError):
        geo.geocode("  ")
    with pytest.raises(ApiError):
        geo.geocode("x" * 300)


def test_geocode_ignores_malformed_items(monkeypatch):
    install(monkeypatch, lambda r: httpx.Response(200, json=[{"display_name": "ok", "lat": "1", "lon": "2"}, {"nope": 1}]))
    assert len(geo.geocode("some address in manila")["candidates"]) == 1


def test_demo_roofs_work_offline(monkeypatch):
    monkeypatch.setattr(geo, "DEMO_PATH", REAL_DEMO_PATH)

    def boom(request):
        raise httpx.ConnectError("offline")

    install(monkeypatch, boom)
    out = geo.geocode("reyes demo")
    assert out["candidates"][0]["source"] == "demo"
    c = out["candidates"][0]
    roof = geo.roof_from_address(c["lat"], c["lon"])
    assert roof.area_m2 == pytest.approx(88, rel=0.02)
    assert any("synthetic" in n.lower() for n in roof.notes)


def test_overpass_picks_containing_building(monkeypatch):
    elements = [square_way(oid=1, half=0.00005), square_way(lat=14.7002, oid=2, half=0.00003)]
    install(monkeypatch, lambda r: httpx.Response(200, json={"elements": elements}))
    roof = geo.roof_from_address(14.7, 121.1)
    assert roof.source == "osm" and roof.confidence == "high"
    assert roof.area_m2 == pytest.approx(11.1 * 11.1, rel=0.1)  # ~0.0001 deg square
    assert roof.anchor and roof.anchor.lat == 14.7


def test_overpass_nearest_within_25m_else_404(monkeypatch):
    far = square_way(lat=14.7003, oid=3)  # ~33 m north
    install(monkeypatch, lambda r: httpx.Response(200, json={"elements": [far]}))
    with pytest.raises(ApiError) as e:
        geo.roof_from_address(14.7, 121.1)
    assert e.value.code == "no_building" and e.value.status == 404 and "Draw" in e.value.hint
    near = square_way(lat=14.70015, oid=4, half=0.00002)  # ~ edge within 25 m, point outside
    install(monkeypatch, lambda r: httpx.Response(200, json={"elements": [near]}))
    assert geo.roof_from_address(14.7000, 121.1001).source == "osm"


def test_overpass_down_gives_503_with_draw_hint_and_tries_mirror(monkeypatch):
    seen = []

    def handler(request):
        seen.append(str(request.url))
        raise httpx.ConnectTimeout("slow")

    install(monkeypatch, handler)
    with pytest.raises(ApiError) as e:
        geo.roof_from_address(14.71, 121.11)
    assert e.value.code == "lookup_unavailable" and e.value.status == 503
    assert len(set(seen)) >= 2  # fell through to the mirror


def test_overpass_result_is_cached(monkeypatch):
    calls = install(monkeypatch, lambda r: httpx.Response(200, json={"elements": [square_way()]}))
    geo.roof_from_address(14.7, 121.1)
    geo.roof_from_address(14.7, 121.1)
    assert len(calls) == 1


def test_overpass_ignores_open_ways_and_reads_roof_shape(monkeypatch):
    open_way = square_way(oid=5)
    open_way["geometry"] = open_way["geometry"][:-1]
    gable = square_way(oid=6, tags={"building": "house", "roof:shape": "gabled"})
    install(monkeypatch, lambda r: httpx.Response(200, json={"elements": [open_way, gable]}))
    roof = geo.roof_from_address(14.7, 121.1)
    assert roof.roof_type == "gable"
