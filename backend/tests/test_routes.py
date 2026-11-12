"""Forms path: the plain endpoints work without any LLM."""
import copy

import pytest

from tests.test_roof import rect_lonlat

RING = [list(p) for p in rect_lonlat(14, 10)]


def test_health_lists_everything(client):
    h = client.get("/api/health").json()
    assert h["db"]["active"] == "sqlite" and h["llm"]["mode"] == "scripted"


def test_roof_finalize_sketch_layout_flow(client):
    r = client.post("/api/roof/finalize", json={"polygon_lonlat": RING, "roof_type": "single_slope"})
    assert r.status_code == 200, r.text
    roof = r.json()
    assert roof["area_m2"] == pytest.approx(140, rel=0.01) and roof["azimuth_deg"] == pytest.approx(180)
    lay = client.post("/api/roof/layout", json={"roof": roof, "panel": {"length_m": 2.28, "width_m": 1.13}})
    assert lay.status_code == 200 and lay.json()["count"] >= 10
    sk = client.post("/api/roof/from-sketch", json={"points_px": [[0, 0], [280, 0], [280, 200], [0, 200]], "px_per_m": 20,
                                                    "scale_source": "user_measured", "anchor": {"lat": 14.676, "lon": 121.0437}})
    assert sk.status_code == 200 and sk.json()["area_m2"] == pytest.approx(140, rel=0.01)


def test_roof_validation_errors_use_the_standard_shape(client):
    r = client.post("/api/roof/finalize", json={"polygon_lonlat": [[1, 1], [2, 2]]})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_request"
    r = client.post("/api/roof/from-sketch", json={"points_px": [[0, 0], [1, 0], [2, 0]], "px_per_m": 20})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_polygon"
    r = client.post("/api/roof/from-sketch", json={"points_px": [[0, 0], [10, 0], [10, 10]], "px_per_m": 0})
    assert r.status_code == 422


def test_geocode_and_from_address_offline_demo(client):
    g = client.post("/api/geocode", json={"q": "pasig demo"}).json()
    assert g["candidates"][0]["source"] == "demo" and g["degraded"] is False  # answered locally, no network call
    assert client.post("/api/geocode", json={"q": "somewhere not in the demo set"}).json()["degraded"] is True  # network is off in tests
    c = g["candidates"][0]
    r = client.post("/api/roof/from-address", json={"lat": c["lat"], "lon": c["lon"]})
    assert r.status_code == 200 and r.json()["area_m2"] == pytest.approx(54, rel=0.02)
    r = client.post("/api/roof/from-address", json={"lat": 14.9, "lon": 121.9})
    assert r.status_code in (404, 503) and r.json()["detail"]["hint"]
    assert client.post("/api/geocode", json={"q": "x"}).status_code == 422


def test_load_estimate(client):
    r = client.post("/api/load/estimate", json={"monthly_kwh": 450, "template": "balanced"}).json()
    assert r["is_estimate"] is True and "hourly_kw" not in r and len(r["monthly_kwh"]) == 12
    r = client.post("/api/load/estimate", json={"bill_php": 6780, "include_hourly": True}).json()
    assert len(r["hourly_kw"]) == 8760 and r["basis"] == "bill"
    assert client.post("/api/load/estimate", json={}).status_code == 422
    assert client.post("/api/load/estimate", json={"monthly_kwh": 450, "bill_php": 5000}).status_code == 422
    assert client.post("/api/load/estimate", json={"monthly_kwh": 5}).status_code == 422


def test_products_and_assumptions(client):
    p = client.get("/api/products?category=battery").json()
    assert p["products"] and all(x["category"] == "battery" for x in p["products"]) and "Confirm with the seller" in p["note"]
    assert client.get("/api/products?category=toaster").status_code == 422
    a = client.get("/api/assumptions").json()["assumptions"]
    assert len(a) > 20 and all("source_url" in x and "as_of" in x for x in a)
    unv = client.get("/api/assumptions?verified=false").json()["assumptions"]
    assert any(x["key"] == "export_credit_php_per_kwh" for x in unv)


def test_products_search_stream_reports_fallback(client):
    r = client.post("/api/products/search")
    assert r.status_code == 200 and "event: source_failed" in r.text and "event: done" in r.text


def test_optimize_simulate_passport_end_to_end(client):
    roof = client.post("/api/roof/finalize", json={"polygon_lonlat": [list(p) for p in rect_lonlat(11, 8, 14.676, 121.0437)],
                                                    "roof_type": "flat"}).json()
    body = {"roof": roof, "monthly_kwh": 450, "template": "balanced", "budget_max_php": 400000,
            "goal": "max_savings_10y"}
    opt = client.post("/api/optimize", json=body)
    assert opt.status_code == 200, opt.text
    res = opt.json()
    assert res["weather_source"] == "PVGIS-ERA5"  # bundled data, no network
    best = res["packages"][0]
    assert best["package"]["capex_php"] <= 400000
    sim = client.post("/api/simulate", json={"roof": roof, "monthly_kwh": 450, "template": "balanced", "package": best["package"],
                                            "export_credit_php_per_kwh": 4.0})
    assert sim.status_code == 200, sim.text
    assert sim.json()["export_credit_php_per_kwh"] == 4.0 and len(sim.json()["on_grid"]["scenarios"]) == 3
    bad = copy.deepcopy(best["package"])
    del bad["inverter"]
    r = client.post("/api/simulate", json={"roof": roof, "monthly_kwh": 450, "package": bad})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_package"


def test_optimize_validation(client):
    roof = client.post("/api/roof/finalize", json={"polygon_lonlat": RING}).json()
    r = client.post("/api/optimize", json={"roof": roof, "monthly_kwh": 450, "budget_max_php": 400000, "goal": "cut_bill"})
    assert r.status_code == 422  # target percent missing
    r = client.post("/api/optimize", json={"roof": roof, "monthly_kwh": 450, "budget_max_php": 20000, "goal": "fastest_payback"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "no_feasible_design"


def test_passport_endpoints_and_paste_to_verify(client):
    cid = "conv-pass-00001-0123456789"
    for msg in ["reyes demo", "Yes, use 450 kWh per month", "My budget is ₱300,000 to ₱500,000", "I want the fastest payback", "Yes, run the numbers"]:
        assert client.post("/api/agent/chat?stream=false", data={"conversation_id": cid, "message": msg}).status_code == 200
    r = client.post("/api/passport", json={"session_id": cid})
    assert r.status_code == 200, r.text
    rec = r.json()
    assert client.get(f"/api/passport/{rec['id']}").json()["hash"] == rec["hash"]
    assert client.get(f"/api/passport/{rec['id']}/verify").json()["valid"] is True
    pasted = {k: rec[k] for k in ("body", "hash", "prev_hash", "signature")}
    assert client.post("/api/passport/verify", json=pasted).json()["valid"] is True
    pasted["body"]["package"]["capex_php"] += 1
    bad = client.post("/api/passport/verify", json=pasted).json()
    assert bad["valid"] is False
    assert {c["name"]: c["status"] for c in bad["checks"]}["integrity"] == "fail"
    assert client.post("/api/passport/verify", json={"nonsense": 1}).status_code == 422
    assert client.get("/api/passport/SOL-NOPE").status_code == 404
    assert "Not found" in client.get("/verify/SOL-NOPE").text
    assert client.post("/api/passport", json={"session_id": "conv-none-00001-0123456789"}).status_code == 404


def test_passport_requires_an_analysis(client):
    cid = "conv-pass-00002-0123456789"
    client.post("/api/agent/chat?stream=false", data={"conversation_id": cid, "message": "hello"})
    r = client.post("/api/passport", json={"session_id": cid})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "not_ready"


def test_cors_allows_the_vite_dev_origin(client):
    r = client.options("/api/agent/chat", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
    r = client.options("/api/agent/chat", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "POST"})
    assert "access-control-allow-origin" not in r.headers
