import numpy as np
import pytest

from app.errors import ApiError
from app.models import FinalizeRequest
from app.services import irradiance, load, optimizer, products, roof, simulate
from tests.test_roof import rect_lonlat


def fake_year_set():
    """Deterministic synthetic weather: 5 'years' with different yields. No network."""
    h = np.arange(8760) % 24
    base = np.where((h >= 6) & (h <= 17), 0.75 * np.sin(np.pi * (h - 6) / 12.0), 0.0)
    data = np.vstack([base * f for f in (0.90, 0.95, 1.0, 1.05, 1.10)])
    return irradiance.YearSet(years=["2001", "2002", "2003", "2004", "2005"], data=data, source="test", notes=[])


@pytest.fixture()
def big_roof():
    return roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(14, 10), roof_type="single_slope"))


def pkg_from_seed(n=8, with_battery=False):
    cat = products.list_products()
    panel = next(p for p in cat if p["id"] == "seed-panel-550")
    kwp = n * 0.55
    inv = simulate.pick_inverter(cat, kwp, hybrid=with_battery)
    bat = next(p for p in cat if p["id"] == "seed-bat-5") if with_battery else None
    return simulate.build_package(panel, n, inv, bat, 1 if bat else 0, label="t")


def test_scenario_years_are_ordered():
    ys = fake_year_set()
    sc = ys.scenario_years()
    assert sc["pessimistic"][0] == "2001" and sc["expected"][0] == "2003" and sc["optimistic"][0] == "2005"


def test_pick_inverter_respects_dc_ac_ratio_and_hybrid():
    cat = products.list_products()
    assert simulate.pick_inverter(cat, 4.4, hybrid=False)["inverter_ac_kw"] == 5   # 4.4/1.4 = 3.14 -> 5 kW (3 kW too small)
    assert simulate.pick_inverter(cat, 4.0, hybrid=False)["inverter_ac_kw"] == 3   # 4.0/3 = 1.33
    assert simulate.pick_inverter(cat, 4.0, hybrid=True)["hybrid"] is True
    assert simulate.pick_inverter(cat, 40.0, hybrid=False) is None


def test_build_package_capex_adds_up():
    p = pkg_from_seed(8)
    b = p["capex_breakdown"]
    assert p["kwp"] == pytest.approx(4.4)
    assert p["capex_php"] == pytest.approx(b["equipment"] + b["installation"] + b["permits_misc"])
    assert b["equipment"] == pytest.approx(8 * 8800 + p["inverter"]["price_php"])


def test_simulate_shape_and_ordering(big_roof):
    ld = load.estimate_load(monthly_kwh=450, template="balanced")
    res = simulate.simulate_package(pkg_from_seed(8), big_roof, ld, year_set=fake_year_set())
    assert res["hybrid"] is None and res["net_metering_off"]["hybrid"] is None
    sc = {s["name"]: s for s in res["on_grid"]["scenarios"]}
    assert set(sc) == {"pessimistic", "expected", "optimistic"}
    assert sc["pessimistic"]["year1_generation_kwh"] < sc["expected"]["year1_generation_kwh"] < sc["optimistic"]["year1_generation_kwh"]
    assert sc["pessimistic"]["net_profit_25y_php"] < sc["optimistic"]["net_profit_25y_php"]
    for s in sc.values():
        assert len(s["cashflow_cumulative_php"]) == 26
        assert s["cashflow_cumulative_php"][0] == -res["on_grid"]["capex_php"]
        assert 0 <= s["year1_self_consumption_pct"] <= 100
    assert res["grid_only"]["monthly_bill_php"] == pytest.approx(450 * 15.0615, rel=0.01)
    assert res["weather"]["years_used"]["expected"] == "2003"
    assert res["disclaimer"] and res["assumptions_used"]


def test_net_metering_off_never_beats_on(big_roof):
    ld = load.estimate_load(monthly_kwh=250, template="night_heavy")  # lots of exports at midday
    res = simulate.simulate_package(pkg_from_seed(10), big_roof, ld, year_set=fake_year_set())
    on = {s["name"]: s for s in res["on_grid"]["scenarios"]}
    off = {s["name"]: s for s in res["net_metering_off"]["on_grid"]["scenarios"]}
    for name in on:
        assert off[name]["year1_savings_php"] <= on[name]["year1_savings_php"] + 1e-6
        assert off[name]["net_profit_25y_php"] <= on[name]["net_profit_25y_php"] + 1e-6


def test_lower_export_credit_lowers_savings(big_roof):
    ld = load.estimate_load(monthly_kwh=250, template="night_heavy")
    hi = simulate.simulate_package(pkg_from_seed(10), big_roof, ld, year_set=fake_year_set(), export_credit_php_per_kwh=10.0)
    lo = simulate.simulate_package(pkg_from_seed(10), big_roof, ld, year_set=fake_year_set(), export_credit_php_per_kwh=2.0)
    assert lo["on_grid"]["scenarios"][1]["year1_savings_php"] < hi["on_grid"]["scenarios"][1]["year1_savings_php"]
    assert lo["export_credit_php_per_kwh"] == 2.0


def test_hybrid_variant_present_with_battery(big_roof):
    ld = load.estimate_load(monthly_kwh=450, template="night_heavy")
    res = simulate.simulate_package(pkg_from_seed(8, with_battery=True), big_roof, ld, year_set=fake_year_set())
    assert res["hybrid"] and res["on_grid"]
    assert res["hybrid"]["capex_php"] > res["on_grid"]["capex_php"]
    h, g = res["hybrid"]["scenarios"][1], res["on_grid"]["scenarios"][1]
    assert h["year1_self_consumption_pct"] >= g["year1_self_consumption_pct"]
    assert h["year1_import_kwh"] <= g["year1_import_kwh"]


def test_over_cap_system_is_rejected(big_roof):
    p = pkg_from_seed(8)
    p["ac_kw"] = 150
    with pytest.raises(ApiError) as e:
        simulate.simulate_package(p, big_roof, load.estimate_load(monthly_kwh=300), year_set=fake_year_set())
    assert e.value.code == "over_net_metering_cap"


def test_quick_eval_agrees_with_full_simulation_in_direction(big_roof):
    ld = load.estimate_load(monthly_kwh=450)
    ys = fake_year_set()
    _, series = ys.scenario_years()["expected"]
    p = pkg_from_seed(8)
    q = simulate.quick_eval(p, series, ld)
    full = simulate.simulate_package(p, big_roof, ld, year_set=ys)["on_grid"]["scenarios"][1]
    assert q["year1_savings_php"] == pytest.approx(full["year1_savings_php"], rel=0.02)
    assert q["net_25y_php"] == pytest.approx(full["net_profit_25y_php"], rel=0.15)


# ---- optimizer -------------------------------------------------------------------------------------------------
def run_opt(big_roof, goal, **kw):
    ld = load.estimate_load(monthly_kwh=450, template="balanced")
    return optimizer.optimize(big_roof, ld, goal=goal, year_set=fake_year_set(), **kw)


def test_cut_bill_picks_cheapest_that_meets_target(big_roof):
    res = run_opt(big_roof, "cut_bill", budget_max_php=400_000, goal_target_pct=40)
    best = res["packages"][0]
    assert res["target_met"] is True and best["quick"]["bill_reduction_pct"] >= 40
    assert best["package"]["capex_php"] <= 400_000
    assert best["package"]["label"] == "Best value"
    assert 1 <= len(res["packages"]) <= 3
    assert len({p["package"]["id"] for p in res["packages"]}) == len(res["packages"])


def test_cut_bill_unreachable_target_is_reported_not_hidden(big_roof):
    res = run_opt(big_roof, "cut_bill", budget_max_php=120_000, goal_target_pct=95)
    assert res["target_met"] is False and any("closest" in n for n in res["notes"])


def test_budget_is_a_hard_limit(big_roof):
    res = run_opt(big_roof, "max_savings_10y", budget_max_php=200_000)
    assert all(p["package"]["capex_php"] <= 200_000 for p in res["packages"])


def test_fastest_payback_beats_other_designs(big_roof):
    res = run_opt(big_roof, "fastest_payback", budget_max_php=500_000)
    paybacks = [p["quick"]["payback_years"] for p in res["packages"]]
    assert paybacks[0] is not None and paybacks[0] <= min(x for x in paybacks if x is not None) + 1e-9


def test_backup_requires_enough_battery(big_roof):
    res = run_opt(big_roof, "backup", budget_max_php=900_000, backup_hours=8)
    best = res["packages"][0]["package"]
    assert best["battery"] is not None
    usable = best["battery"]["battery_kwh"] * best["battery_count"] * 0.9
    assert usable >= 0.6 * 8 - 1e-9
    assert best["label"] == "Backup-ready"


def test_impossible_budget_gives_clear_error(big_roof):
    with pytest.raises(ApiError) as e:
        run_opt(big_roof, "cut_bill", budget_max_php=25_000, goal_target_pct=50)
    assert e.value.code == "no_feasible_design" and "budget" in e.value.message.lower()
    with pytest.raises(ApiError) as e:
        run_opt(big_roof, "backup", budget_max_php=60_000, backup_hours=8)
    assert e.value.code == "no_feasible_design"


def test_tiny_roof_gives_roof_too_small():
    tiny = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(2.5, 2.5)))
    with pytest.raises(ApiError) as e:
        run_opt(tiny, "cut_bill", budget_max_php=400_000, goal_target_pct=30)
    assert e.value.code == "roof_too_small"


def test_optimizer_is_deterministic(big_roof):
    a = run_opt(big_roof, "max_savings_10y", budget_max_php=450_000)
    b = run_opt(big_roof, "max_savings_10y", budget_max_php=450_000)
    assert [p["package"]["id"] for p in a["packages"]] == [p["package"]["id"] for p in b["packages"]]
