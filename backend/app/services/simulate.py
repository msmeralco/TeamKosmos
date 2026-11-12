"""Package construction and the ROI simulation (modelled over 25 years internally, shown over 10) (3 scenarios, net metering on/off, grid / on-grid / hybrid)."""
from __future__ import annotations

from typing import Any

import numpy as np

from ..errors import ApiError
from ..models import RoofModel
from . import billing, finance, irradiance
from .assumptions import A, assumption_record
from .dispatch import Battery, Inverter, dispatch
from .load import LoadProfile

SCENARIOS = ("pessimistic", "expected", "optimistic")
DISCLAIMER = ("Estimates for planning only, based on modelled weather and a synthetic household. "
              "A licensed installer must confirm the design, price and Meralco net-metering terms.")


# ---- packages -------------------------------------------------------------------------------------------
def pick_inverter(catalog: list[dict], kwp: float, hybrid: bool) -> dict | None:
    """Smallest inverter keeping DC/AC <= max ratio and DC input within the unit's limit.

    Choosing the smallest unit already lands inside [dc_ac_ratio_min, dc_ac_ratio_max] whenever the catalog has one.
    When the catalog has a gap (for example 4.4 kWp, where 3 kW is too small and 5 kW gives 0.88), the next size up
    is used rather than dropping the candidate."""
    need_ac = kwp / A("dc_ac_ratio_max")
    options = [p for p in catalog if p["category"] == "inverter" and bool(p.get("hybrid")) == hybrid
               and p["inverter_ac_kw"] >= need_ac - 1e-9 and (p.get("max_dc_kw") or 1e9) >= kwp - 1e-9
               and p["inverter_ac_kw"] <= A("net_metering_cap_kw")]
    return min(options, key=lambda p: (p["inverter_ac_kw"], p["price_php"])) if options else None


def build_package(panel: dict, count: int, inverter: dict, battery: dict | None = None, battery_count: int = 0,
                  label: str = "") -> dict:
    kwp = count * panel["watts"] / 1000.0
    panels_cost = count * panel["price_php"]
    battery_cost = battery_count * battery["price_php"] if battery else 0.0
    equipment = panels_cost + inverter["price_php"] + battery_cost
    installation = A("install_cost_php_per_kw") * kwp
    permits = A("permits_misc_php")
    return {
        "id": f"{panel['id']}x{count}+{inverter['id']}" + (f"+{battery['id']}x{battery_count}" if battery else ""),
        "label": label, "panel": panel, "panel_count": count, "inverter": inverter,
        "battery": battery, "battery_count": battery_count if battery else 0,
        "kwp": round(kwp, 3), "ac_kw": inverter["inverter_ac_kw"],
        "capex_php": round(equipment + installation + permits, 2),
        "capex_breakdown": {"equipment": round(equipment, 2), "installation": round(installation, 2),
                            "permits_misc": round(permits, 2), "battery_equipment": round(battery_cost, 2)},
    }


def _inverter_model(pkg: dict) -> Inverter:
    inv = pkg["inverter"]
    return Inverter(ac_kw=inv["inverter_ac_kw"], efficiency=A("inverter_efficiency_pct") / 100.0, max_dc_kw=inv.get("max_dc_kw"))


def _battery_model(pkg: dict) -> Battery | None:
    if not pkg.get("battery") or not pkg.get("battery_count"):
        return None
    b, n = pkg["battery"], pkg["battery_count"]
    return Battery(usable_kwh=b["battery_kwh"] * n * A("battery_usable_dod_pct") / 100.0,
                   max_kw=b["battery_max_kw"] * n, round_trip_eff=A("battery_round_trip_eff_pct") / 100.0)


def _degradation(pkg: dict) -> float:
    d = pkg["panel"].get("degradation_pct_per_year")
    return (A("degradation_pct_per_year") if d is None else float(d)) / 100.0


def _lerp_years(first: np.ndarray, last: np.ndarray, years: int) -> np.ndarray:
    t = (np.arange(years) / max(1, years - 1))[:, None]
    return first[None, :] + (last - first)[None, :] * t


def _variant_eval(pkg: dict, battery: Battery | None, series: np.ndarray, load: LoadProfile, *, years: int,
                  capex: float, name: str, weather_year: str, tariff: float, credit: float, net_metering: bool,
                  fixed: float) -> dict:
    d = _degradation(pkg)
    kwp = pkg["kwp"]
    inv = _inverter_model(pkg)
    r1 = dispatch(series * kwp, load.hourly_kw, inv, battery)
    rN = dispatch(series * kwp * (1.0 - d) ** (years - 1), load.hourly_kw, inv, battery)
    imp = _lerp_years(r1.monthly_import, rN.monthly_import, years)
    exp = _lerp_years(r1.monthly_export, rN.monthly_export, years)
    gen = np.linspace(r1.generation_kwh, rN.generation_kwh, years)
    bills = billing.annual_bills(
        imp, exp, load.monthly_kwh, tariff=tariff, tariff_growth_pct=A(f"tariff_growth_pct_{name}"),
        export_credit=credit, export_credit_growth_pct=A(f"export_credit_growth_pct_{name}"),
        fixed_php_month=fixed, net_metering=net_metering)
    battery_price = pkg["capex_breakdown"].get("battery_equipment", 0.0) if battery else 0.0
    cf = finance.build_cashflow(
        bills.savings, capex, om_pct_of_capex=A("om_pct_of_capex_per_year"), inverter_price=pkg["inverter"]["price_php"],
        inverter_life=int(A("inverter_life_years")), inverter_replacement_pct=A("inverter_replacement_pct_of_price"),
        battery_price=battery_price, battery_life=int(A("battery_life_years")))
    disc = A("discount_rate_pct")
    irr = finance.irr_pct(cf.net, capex)
    pay = finance.payback_years(cf.cumulative)
    lc = finance.lcoe(capex, cf.om, cf.replacements, gen, disc)
    return {
        "name": name, "weather_year": weather_year, "net_metering": net_metering,
        "year1_generation_kwh": round(r1.generation_kwh, 1),
        "year1_self_consumption_pct": round(r1.self_consumption_pct, 1),
        "year1_export_kwh": round(r1.export_kwh, 1),
        "year1_import_kwh": round(r1.import_kwh, 1),
        "baseline_year1_bill_php": round(float(bills.baseline[0]), 0),
        "year1_bill_php": round(float(bills.solar[0]), 0),
        "year1_savings_php": round(float(bills.savings[0]), 0),
        "bill_reduction_pct_year1": round(100.0 * float(bills.savings[0]) / float(bills.baseline[0]), 1) if bills.baseline[0] else 0.0,
        "payback_years": None if pay is None else round(pay, 1),
        "net_profit_25y_php": round(float(cf.cumulative[-1]), 0),  # internal: Passport records verify against it, never shown
        "net_profit_10y_php": round(float(cf.cumulative[min(10, len(cf.cumulative) - 1)]), 0),
        "npv_php": round(finance.npv(cf.net, capex, disc), 0),
        "irr_pct": None if irr is None else round(irr, 1),
        "lcoe_php_per_kwh": None if lc is None else round(lc, 2),
        "cashflow_cumulative_php": [round(float(v), 0) for v in cf.cumulative],
        "co2_avoided_t_10y": round(float(gen[:10].sum()) * A("grid_emission_factor_kg_per_kwh") / 1000.0, 1),
        "battery_throughput_kwh_year1": round(r1.battery_throughput_kwh, 1),
        "capex_php": round(capex, 0),
        "_baseline_total": float(bills.baseline.sum()),
        "_baseline_y1": float(bills.baseline[0]),
    }


def simulate_package(pkg: dict, roof: RoofModel, load: LoadProfile, *, years: int | None = None,
                     export_credit_php_per_kwh: float | None = None, tariff_php_per_kwh: float | None = None,
                     year_set: irradiance.YearSet | None = None) -> dict:
    years = years or int(A("analysis_years"))
    if pkg["ac_kw"] > A("net_metering_cap_kw"):
        raise ApiError("over_net_metering_cap", f"A {pkg['ac_kw']:g} kW system is above the {A('net_metering_cap_kw'):g} kW residential cap.", status=422)
    ys = year_set or irradiance.get_year_set(roof.centroid.lat, roof.centroid.lon, roof.tilt_deg, roof.azimuth_deg)
    scen_years = ys.scenario_years()
    tariff = A("tariff_php_per_kwh") if tariff_php_per_kwh is None else float(tariff_php_per_kwh)
    credit = A("export_credit_php_per_kwh") if export_credit_php_per_kwh is None else float(export_credit_php_per_kwh)
    fixed = A("tariff_fixed_php_month")
    battery = _battery_model(pkg)
    bat_cost = pkg["capex_breakdown"].get("battery_equipment", 0.0)
    variants: dict[str, tuple[Battery | None, float]] = {"on_grid": (None, pkg["capex_php"] - bat_cost)}
    if battery is not None:
        variants["hybrid"] = (battery, pkg["capex_php"])

    out: dict[str, Any] = {"on_grid": None, "hybrid": None, "net_metering_off": {"on_grid": None, "hybrid": None}}
    grid_only = None
    for vname, (bat, capex) in variants.items():
        on_list, off_list = [], []
        for s in SCENARIOS:
            wy, series = scen_years[s]
            on = _variant_eval(pkg, bat, series, load, years=years, capex=capex, name=s, weather_year=wy,
                               tariff=tariff, credit=credit, net_metering=True, fixed=fixed)
            off = _variant_eval(pkg, bat, series, load, years=years, capex=capex, name=s, weather_year=wy,
                                tariff=tariff, credit=credit, net_metering=False, fixed=fixed)
            on_list.append(on)
            off_list.append(off)
            if grid_only is None and s == "expected":
                grid_only = {"monthly_bill_php": round(on["_baseline_y1"] / 12.0, 0)}
        out[vname] = {"package_id": pkg["id"], "capex_php": round(capex, 0), "scenarios": on_list}
        out["net_metering_off"][vname] = {"package_id": pkg["id"], "capex_php": round(capex, 0), "scenarios": off_list}
    for v in (out["on_grid"], out["hybrid"], out["net_metering_off"]["on_grid"], out["net_metering_off"]["hybrid"]):
        for sc in (v or {}).get("scenarios", []):
            sc.pop("_baseline_total", None)
            sc.pop("_baseline_y1", None)

    keys = ["tariff_php_per_kwh", "tariff_fixed_php_month", "export_credit_php_per_kwh", "degradation_pct_per_year",
            "system_losses_pct", "inverter_efficiency_pct", "battery_round_trip_eff_pct", "battery_usable_dod_pct",
            "battery_life_years", "inverter_life_years", "inverter_replacement_pct_of_price", "om_pct_of_capex_per_year",
            "install_cost_php_per_kw", "permits_misc_php", "discount_rate_pct", "grid_emission_factor_kg_per_kwh",
            "net_metering_cap_kw", "dc_ac_ratio_max"]
    keys += [f"{p}_{s}" for s in SCENARIOS for p in ("tariff_growth_pct", "export_credit_growth_pct")]
    used = []
    for k in keys:
        if k == "tariff_php_per_kwh":
            used.append(assumption_record(k, tariff))
        elif k == "export_credit_php_per_kwh":
            used.append(assumption_record(k, credit))
        else:
            used.append(assumption_record(k))
    out.update(
        package_id=pkg["id"], grid_only=grid_only, years=years,
        weather={"source": ys.source, "approximate": ys.is_approximate, "notes": ys.notes,
                 "years_used": {s: scen_years[s][0] for s in SCENARIOS}},
        export_credit_php_per_kwh=credit, tariff_php_per_kwh=tariff,
        assumptions_used=used, disclaimer=DISCLAIMER,
        scenario_definitions={
            "pessimistic": "Low-yield weather year (~10th percentile), tariff and export-credit growth at the pessimistic rates.",
            "expected": "Median weather year, expected growth rates.",
            "optimistic": "High-yield weather year (~90th percentile), optimistic growth rates.",
        },
    )
    return out


# ---- fast evaluation used by the optimizer ------------------------------------------------------------------
def quick_eval(pkg: dict, series: np.ndarray, load: LoadProfile, *, tariff: float | None = None,
               credit: float | None = None, capex: float | None = None, years: int = 25) -> dict:
    """Year-1 dispatch only; later years scale generation by degradation (lost output first costs self-consumption)."""
    tariff = A("tariff_php_per_kwh") if tariff is None else tariff
    credit = A("export_credit_php_per_kwh") if credit is None else credit
    capex = pkg["capex_php"] if capex is None else capex
    d = _degradation(pkg)
    battery = _battery_model(pkg)
    r1 = dispatch(series * pkg["kwp"], load.hourly_kw, _inverter_model(pkg), battery)
    g = (1.0 - d) ** np.arange(years)
    used_m = r1.monthly_generation - r1.monthly_export
    imp = r1.monthly_import[None, :] + (1.0 - g)[:, None] * used_m[None, :]
    exp = r1.monthly_export[None, :] * g[:, None]
    bills = billing.annual_bills(
        imp, exp, load.monthly_kwh, tariff=tariff, tariff_growth_pct=A("tariff_growth_pct_expected"), export_credit=credit,
        export_credit_growth_pct=A("export_credit_growth_pct_expected"), fixed_php_month=A("tariff_fixed_php_month"),
        net_metering=True)
    bat_cost = pkg["capex_breakdown"].get("battery_equipment", 0.0)
    cf = finance.build_cashflow(
        bills.savings, capex, om_pct_of_capex=A("om_pct_of_capex_per_year"), inverter_price=pkg["inverter"]["price_php"],
        inverter_life=int(A("inverter_life_years")), inverter_replacement_pct=A("inverter_replacement_pct_of_price"),
        battery_price=bat_cost, battery_life=int(A("battery_life_years")))
    pay = finance.payback_years(cf.cumulative)
    return {
        "bill_reduction_pct": 100.0 * float(bills.savings[0]) / float(bills.baseline[0]) if bills.baseline[0] else 0.0,
        "savings_10y_php": float(cf.cumulative[10] + capex) if years >= 10 else 0.0,
        "net_10y_php": float(cf.cumulative[10]) if years >= 10 else 0.0,
        "net_25y_php": float(cf.cumulative[-1]),
        "payback_years": pay,
        "year1_savings_php": float(bills.savings[0]),
        "usable_battery_kwh": battery.usable_kwh if battery else 0.0,
    }
