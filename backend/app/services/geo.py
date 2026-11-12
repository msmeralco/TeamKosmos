"""Address search (Nominatim) and building outline lookup (Overpass), with cache, throttle and demo fallback.

Nominatim policy: max 1 request/second, identifying User-Agent, cache results, no autocomplete.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
from pathlib import Path
from typing import Callable

import httpx
from shapely.geometry import Point, Polygon

from ..config import BACKEND_DIR, get_settings
from ..db import get_cache
from ..errors import ApiError
from ..models import RoofModel
from . import roof as roof_svc

log = logging.getLogger("sol.geo")

DEMO_PATH = Path(BACKEND_DIR) / "data" / "demo_outlines.geojson"
MIN_INTERVAL_S = 1.1  # Nominatim: absolute maximum of 1 request per second
GEOCODE_TTL_S = 24 * 3600
OUTLINE_TTL_S = 7 * 24 * 3600
NEAREST_MAX_M = 25.0

# Tests replace this to inject an httpx.MockTransport.
client_factory: Callable[[], httpx.Client] | None = None

_throttle_lock = threading.Lock()
_last_request = 0.0


class LookupUnavailable(Exception):
    """The remote service could not be reached (as opposed to 'no result')."""


def _client() -> httpx.Client:
    if client_factory:
        return client_factory()
    s = get_settings()
    return httpx.Client(timeout=s.http_timeout_s, headers={"User-Agent": s.user_agent})


def _throttle() -> None:
    global _last_request
    with _throttle_lock:
        wait = _last_request + MIN_INTERVAL_S - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        _last_request = time.monotonic()


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).strip()


# ---- demo outlines (checked before any network call) -----------------------------------------
def load_demo() -> list[dict]:
    try:
        data = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out = []
    for f in data.get("features", []):
        geom = f.get("geometry") or {}
        if geom.get("type") != "Polygon" or not geom.get("coordinates"):
            continue
        props = f.get("properties") or {}
        out.append({
            "name": props.get("name", "Demo roof"),
            "aliases": props.get("aliases", []),
            "synthetic": bool(props.get("synthetic", False)),
            "roof_shape": props.get("roof_shape"),
            "ring": [tuple(p[:2]) for p in geom["coordinates"][0]],
        })
    return out


def _demo_centroid(entry: dict) -> tuple[float, float]:
    ring = entry["ring"]
    return sum(p[0] for p in ring) / len(ring), sum(p[1] for p in ring) / len(ring)


def has_demo_match(query: str) -> bool:
    return bool(_demo_matches(query))


def _demo_matches(query: str) -> list[dict]:
    q = _norm(query)
    hits = []
    if len(q) < 3:
        return hits
    for e in load_demo():
        names = [_norm(e["name"])] + [_norm(a) for a in e["aliases"]]
        if any(n and (n in q or q in n) for n in names):
            lon, lat = _demo_centroid(e)
            hits.append({"label": e["name"] + (" (synthetic demo roof)" if e["synthetic"] else ""),
                         "lat": lat, "lon": lon, "source": "demo"})
    return hits


# ---- geocoding ----------------------------------------------------------------------------------
def geocode(q: str) -> dict:
    q = (q or "").strip()
    if len(q) < 3 or len(q) > 200:
        raise ApiError("invalid_query", "Type at least 3 characters of the address.", status=422)
    demo = _demo_matches(q)
    if demo:  # a synthetic demo roof was asked for by name: no need to bother Nominatim
        return {"candidates": demo, "degraded": False, "cached": False}
    cache = get_cache()
    key = f"geocode:{_norm(q)}"
    hit = cache.cache_get(key)
    if hit is not None:
        return {"candidates": demo + hit, "degraded": False, "cached": True}
    s = get_settings()
    params = {"q": q, "format": "jsonv2", "countrycodes": "ph", "limit": 5}
    try:
        _throttle()
        with _client() as c:
            resp = c.get(s.nominatim_url, params=params)
        resp.raise_for_status()
        items = resp.json()
        cands = []
        for it in items[:5]:
            try:
                cands.append({"label": str(it["display_name"]), "lat": float(it["lat"]), "lon": float(it["lon"]),
                              "source": "nominatim"})
            except (KeyError, TypeError, ValueError):
                continue
    except (httpx.HTTPError, ValueError) as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status in (403, 429):
            log.warning("Nominatim refused the request (HTTP %s). Set CONTACT_EMAIL in backend/.env to a real address "
                        "and keep to 1 request per second.", status)
        else:
            log.warning("Nominatim failed: %s", exc)
        return {"candidates": demo, "degraded": True, "cached": False}
    cache.cache_set(key, cands, ttl_s=GEOCODE_TTL_S)
    return {"candidates": demo + cands, "degraded": False, "cached": False}


# ---- building outline -----------------------------------------------------------------------------
def _meters(lon: float, lat: float, epsg: int) -> tuple[float, float]:
    return roof_svc.to_utm(lon, lat, epsg)


def _pick_way(ways: list[dict], lat: float, lon: float) -> dict | None:
    epsg = roof_svc.utm_epsg_for(lon, lat)
    px, py = _meters(lon, lat, epsg)
    pt = Point(px, py)
    best, best_d = None, None
    for w in ways:
        ring = w["ring"]
        if len(ring) < 4:
            continue
        try:
            poly = Polygon([_meters(x, y, epsg) for x, y in ring])
        except ValueError:
            continue
        if not poly.is_valid or poly.is_empty:
            continue
        if poly.contains(pt):
            return w
        d = poly.distance(pt)
        if d <= NEAREST_MAX_M and (best_d is None or d < best_d):
            best, best_d = w, d
    return best


def _demo_outline(lat: float, lon: float) -> dict | None:
    ways = [{"ring": e["ring"], "tags": {"roof:shape": e["roof_shape"]} if e["roof_shape"] else {},
             "name": e["name"], "synthetic": e["synthetic"]} for e in load_demo()]
    return _pick_way(ways, lat, lon)


def _fetch_overpass(lat: float, lon: float) -> list[dict]:
    s = get_settings()
    query = f'[out:json][timeout:15];way(around:{NEAREST_MAX_M:g},{lat:.6f},{lon:.6f})["building"];out geom;'
    last_exc: Exception | None = None
    for url in s.overpass_urls:
        try:
            _throttle()
            with _client() as c:
                resp = c.post(url, data={"data": query})
            resp.raise_for_status()
            elements = resp.json().get("elements", [])
            ways = []
            for el in elements:
                geom = el.get("geometry")
                if el.get("type") != "way" or not geom:
                    continue
                ring = [(float(g["lon"]), float(g["lat"])) for g in geom]
                if ring and ring[0] != ring[-1]:
                    continue  # open way, not a building outline
                ways.append({"ring": ring, "tags": el.get("tags", {}), "osm_id": el.get("id")})
            return ways
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
            last_exc = exc
            log.warning("Overpass %s failed: %s", url, exc)
    raise LookupUnavailable(str(last_exc))


_ROOF_SHAPE = {"flat": "flat", "gabled": "gable", "skillion": "single_slope", "hipped": "gable", "pyramidal": "gable"}


def roof_from_address(lat: float, lon: float) -> RoofModel:
    """Outline lookup order: demo outlines, cache, Overpass. Raises ApiError with a 'draw it' hint on failure."""
    demo = _demo_outline(lat, lon)
    cache = get_cache()
    key = f"overpass:{lat:.5f},{lon:.5f}"
    if demo is not None:
        way, source_note = demo, "Demo outline (synthetic), not a real building."
    else:
        cached = cache.cache_get(key)
        if cached is not None:
            ways = cached
        else:
            try:
                ways = _fetch_overpass(lat, lon)
            except LookupUnavailable:
                raise ApiError("lookup_unavailable", "The map data service did not answer in time.",
                               hint="Draw the roof on the map instead.", status=503)
            cache.cache_set(key, ways, ttl_s=OUTLINE_TTL_S)
        way = _pick_way([{**w, "ring": [tuple(p) for p in w["ring"]]} for w in ways], lat, lon)
        source_note = "Outline from OpenStreetMap contributors (ODbL)."
    if way is None:
        raise ApiError("no_building", "I could not find a building outline at that spot.",
                       hint="Draw the roof on the map instead.", status=404)
    shape = _ROOF_SHAPE.get(str((way.get("tags") or {}).get("roof:shape", "")).lower(), "flat")
    from ..models import FinalizeRequest, LatLon

    req = FinalizeRequest(polygon_lonlat=way["ring"], roof_type=shape)  # type: ignore[arg-type]
    model = roof_svc.roof_from_lonlat(way["ring"], source="drawn" if demo is not None else "osm", req=req,
                                      notes=[source_note], anchor=LatLon(lat=lat, lon=lon))
    return model
