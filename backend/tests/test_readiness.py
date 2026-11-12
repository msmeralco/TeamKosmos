from types import SimpleNamespace as NS

from app.services.readiness import readiness

PKG = {"panel": "P (600 W)", "inverter": "I (3 kW)", "battery": None, "kwp": 3.0}


def _run(ac_kw=3.0, used=80.0, net_metering=True, kwp=3.0, azimuth=180.0, confidence="high", scale="user_measured"):
    roof = NS(azimuth_deg=azimuth, confidence=confidence, scale_source=scale, usable_area_m2=40.0)
    out = readiness(roof, {"ac_kw": ac_kw}, {**PKG, "kwp": kwp}, {"year1_self_consumption_pct": used}, net_metering)
    return {c["id"]: c for c in out}


def test_clean_option_has_nothing_to_watch():
    r = _run()
    assert [c["status"] for c in r.values()] == ["ok", "confirm", "confirm", "confirm"]


def test_size_flags_low_self_use_and_transformer_limit():
    assert _run(used=20.0)["size"]["status"] == "watch"
    assert "7 kW" in _run(ac_kw=8.0)["size"]["text"]


def test_location_flags_poor_facing_and_unmeasured_sketch():
    r = _run(azimuth=90.0, scale="default_grid")["location"]
    assert r["status"] == "watch" and "off south" in r["text"] and "not measured" in r["text"]


def test_requirements_follow_export_choice():
    assert "Net Metering" in _run()["requirements"]["text"]
    assert "Micro Solar" in _run(net_metering=False, kwp=1.0)["requirements"]["text"]
    assert "Zero-Export" in _run(net_metering=False, kwp=3.0)["requirements"]["text"]
