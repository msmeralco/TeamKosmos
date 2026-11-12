import numpy as np
import pandas as pd
import pytest

from app.db import get_repo
from app.db.pg_repo import MIGRATION
from app.services import irradiance, passport
from app.services.agent import runner


def test_bundled_pvgis_is_aligned_to_local_time_and_plausible():
    ys = irradiance.get_year_set(14.676, 121.0437, 12, 180, allow_live=False)
    assert ys.source == "PVGIS-ERA5" and not ys.is_approximate
    assert ys.data.shape[1] == 8760 and len(ys.years) >= 15
    mean_day = ys.data.mean(axis=0).reshape(365, 24).mean(axis=0)
    assert 10 <= int(mean_day.argmax()) <= 13          # peak around local noon, so UTC was converted to UTC+8
    assert mean_day[:5].max() == 0 and mean_day[19:].max() == 0   # no output at night
    yields = ys.annual_yield()
    assert 1100 < yields.min() and yields.max() < 1600  # kWh per kWp per year for Metro Manila
    assert (ys.data >= 0).all() and ys.data.max() <= 1.0


def test_scenario_years_spread_is_real_not_cosmetic():
    ys = irradiance.get_year_set(14.676, 121.0437, 12, 180, allow_live=False)
    sc = ys.scenario_years()
    y = {k: v[1].sum() for k, v in sc.items()}
    assert y["pessimistic"] < y["expected"] < y["optimistic"]
    assert sc["pessimistic"][0].isdigit()


def test_series_from_pvgis_converts_timezone_and_drops_feb_29():
    idx = pd.date_range("2019-12-31 16:00", "2024-01-01 15:00", freq="h", tz="UTC")  # PHT 2020-01-01 .. 2023-12-31 (leap 2020)
    df = pd.DataFrame({"P": np.where((idx.tz_convert("Asia/Manila").hour == 12), 800.0, 0.0)}, index=idx)
    years, data = irradiance.series_from_pvgis(df)
    assert years == ["2020", "2021", "2022", "2023"] and data.shape == (4, 8760)
    assert all(data[i].reshape(365, 24)[:, 12].min() == 0.8 for i in range(4))  # noon local, in kW per kWp
    assert data.sum() == pytest.approx(0.8 * 365 * 4)  # Feb 29, 2020 was dropped


def test_incomplete_years_are_discarded():
    idx = pd.date_range("2021-06-01", "2022-12-31 23:00", freq="h", tz="UTC")
    df = pd.DataFrame({"P": 100.0}, index=idx)
    with pytest.raises(ValueError):
        irradiance.series_from_pvgis(df.iloc[:2000])
    years, data = irradiance.series_from_pvgis(df)
    assert years == ["2022"]  # 2021 starts in June, so only the complete local year 2022 is kept
    assert data.shape == (1, 8760)


def test_unbundled_orientation_without_network_uses_labelled_approximation():
    ys = irradiance.get_year_set(14.6, 121.0, 33, 135, allow_live=False)
    assert ys.is_approximate and ys.source == "approximate"
    assert any("APPROXIMATE" in n for n in ys.notes)
    mean_day = ys.data[1].reshape(365, 24).mean(axis=0)
    assert 9 <= int(mean_day.argmax()) <= 13
    assert 1000 < ys.annual_yield()[1] < 1700


def test_live_failure_falls_back_to_approximation_and_is_not_cached_to_disk(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise TimeoutError("pvgis slow")

    monkeypatch.setattr(irradiance, "fetch_pvgis", boom)
    ys = irradiance.get_year_set(14.6, 121.0, 33, 135, allow_live=True)
    assert ys.is_approximate and any("unreachable" in n for n in ys.notes)
    cache_dir = tmp_path / "pvgis_cache"
    assert not cache_dir.exists() or not list(cache_dir.glob("*.npz"))  # a later run retries the real source


def test_live_success_is_cached_to_disk_and_reused(monkeypatch, tmp_path):
    calls = []

    def fake_fetch(lat, lon, tilt, az, *, year_range, timeout):
        calls.append((lat, lon, tilt, az))
        return irradiance.YearSet(years=["2020", "2021"], data=np.full((2, 8760), 0.1), source="PVGIS-ERA5", notes=[])

    monkeypatch.setattr(irradiance, "fetch_pvgis", fake_fetch)
    a = irradiance.get_year_set(14.6, 121.0, 33, 135, allow_live=True)
    irradiance.clear_memory()
    b = irradiance.get_year_set(14.6, 121.0, 33, 135, allow_live=True)
    assert len(calls) == 1 and (tmp_path / "pvgis_cache").exists()
    assert np.allclose(a.data, b.data, atol=1e-6) and b.source == "PVGIS-ERA5"


def test_cache_key_quantises_nearby_roofs_together():
    assert irradiance.cache_key(14.676, 121.0437, 12.2, 181) == irradiance.cache_key(14.7, 121.04, 12, 180)


# ---- hardening ---------------------------------------------------------------------------------------------------------
def test_migration_blocks_are_separable_and_non_empty():
    blocks = [b.strip() for b in MIGRATION.read_text(encoding="utf-8").split("\n--;;\n") if b.strip()]
    assert len(blocks) >= 10
    assert any("ledger_append_only" in b and "$$" in b for b in blocks)  # the function body stays in one block
    for b in blocks:
        assert b.count("$$") % 2 == 0


def test_rate_limiter():
    rl = runner.RateLimiter(limit=3, window_s=60)
    assert [rl.allow("a") for _ in range(4)] == [True, True, True, False]
    assert rl.allow("b") is True


def test_chat_rate_limit_returns_429(client, monkeypatch):
    monkeypatch.setattr(runner, "PER_CONVERSATION", runner.RateLimiter(limit=2, window_s=60))
    cid = "conv-rate-0123456789"
    codes = [client.post("/api/agent/chat?stream=false", data={"conversation_id": cid, "message": "hi"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
    r = client.post("/api/agent/chat?stream=false", data={"conversation_id": cid, "message": "hi"})
    assert r.json()["detail"]["code"] == "rate_limited"
    # a 429 must not leave the session locked
    other = client.post("/api/agent/chat?stream=false", data={"conversation_id": "conv-rate-other-012345", "message": "hi"})
    assert other.status_code == 200


def test_short_conversation_ids_are_refused(client):
    r = client.post("/api/agent/chat?stream=false", data={"conversation_id": "short-id", "message": "hi"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_conversation_id"


def test_change_menu_can_be_cancelled(client):
    cid = "conv-chg-0123456789"
    for m in ["reyes demo", "Yes, use 450 kWh per month", "My budget is ₱150,000 to ₱300,000", "I want the fastest payback", "I want to change something"]:
        out = client.post("/api/agent/chat?stream=false", data={"conversation_id": cid, "message": m}).json()
    assert out["reply"]["slot"] == "change"
    out = client.post("/api/agent/chat?stream=false", data={"conversation_id": cid, "message": "never mind"}).json()
    assert out["reply"]["slot"] == "confirm"


def test_passport_body_names_its_ledger(monkeypatch):
    from tests.test_simulate_optimize import fake_year_set, pkg_from_seed
    from app.models import FinalizeRequest
    from app.services import load, roof, simulate
    from tests.test_roof import rect_lonlat

    monkeypatch.setattr(irradiance, "get_year_set", lambda *a, **k: fake_year_set())
    r = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(14, 10), roof_type="single_slope"))
    pkg = pkg_from_seed(8)
    res = simulate.simulate_package(pkg, r, load.estimate_load(monthly_kwh=450), year_set=fake_year_set())
    rec = passport.issue(inputs={"roof": r.model_dump(mode="json"), "load": {"params": {"monthly_kwh": 450.0, "template": "balanced"}}},
                         package=pkg, results=res)
    assert rec["body"]["ledger"] == get_repo().kind == "sqlite"
    foreign = {k: rec[k] for k in ("body", "hash", "prev_hash", "signature")}
    foreign["body"] = dict(foreign["body"], id="SOL-ELSEWHERE", ledger="supabase")
    out = passport.verify_pasted(foreign)
    chain = next(c for c in out["checks"] if c["name"] == "chain")
    assert chain["status"] == "fail" and "supabase" in chain["detail"]
