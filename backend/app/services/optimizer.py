"""Goal-driven package search inside budget and roof limits (see context/IMPLEMENTATION_PLAN.md 7.8).

Candidates are scored with a fast year-1 evaluation on the expected weather year; the finalists then get the
full 3-scenario simulation. Budget minimum is only a guide: the hard limit is the budget maximum.
"""
from __future__ import annotations

import math
from typing import Any

from ..errors import ApiError
from ..models import RoofModel
from . import irradiance, layout, products, simulate
from .assumptions import A
from .load import LoadProfile

GOAL_LABELS = {"cut_bill": "Best value", "max_savings_10y": "Max savings", "fastest_payback": "Fastest payback",
               "backup": "Backup-ready"}


def _objective(goal: str, q: dict, capex: float, target_pct: float | None, system_type: str | None = None) -> tuple:
    """Smaller tuple is better."""
    pay = q["payback_years"] if q["payback_years"] is not None else 1e9
    if system_type == "off_grid":
        # Off-grid: the most independence from the utility the budget buys, then the lowest cost.
        return (-round(q["bill_reduction_pct"]), capex, -q["net_25y_php"])
    if goal == "cut_bill":
        met = q["bill_reduction_pct"] >= (target_pct or 0.0)
        return (0 if met else 1, capex if met else -q["bill_reduction_pct"], -q["net_25y_php"])
    if goal == "max_savings_10y":
        return (-q["net_10y_php"], pay)
    if goal == "fastest_payback":
        return (pay, -q["net_25y_php"])
    return (capex, -q["net_25y_php"])  # backup: cheapest design that meets the battery constraint


def optimize(roof: RoofModel, load: LoadProfile, *, budget_max_php: float, goal: str, goal_target_pct: float | None = None,
             backup_hours: float | None = None, budget_min_php: float | None = None,
             year_set: irradiance.YearSet | None = None, top: int = 3, system_type: str | None = None) -> dict:
    catalog = products.list_products()
    panels = [p for p in catalog if p["category"] == "panel"]
    batteries = [p for p in catalog if p["category"] == "battery"]
    if not panels:
        raise ApiError("empty_catalog", "There are no solar panels in the catalog.", status=500)

    ys = year_set or irradiance.get_year_set(roof.centroid.lat, roof.centroid.lon, roof.tilt_deg, roof.azimuth_deg)
    _, series = ys.scenario_years()["expected"]
    need_backup_kwh = 0.0
    if goal == "backup":
        hours = backup_hours or A("backup_hours_default")
        need_backup_kwh = A("backup_essential_load_kw") * hours

    caps = {p["id"]: layout.panel_capacity(roof, *p["dims_m"]) for p in panels}
    if max(caps.values()) == 0:
        raise ApiError("roof_too_small", "No solar panel fits on the usable part of this installation site.",
                       hint="Check the outline and scale, or reduce the edge setback.", status=422)

    evaluated: dict[tuple, dict] = {}
    rejected = {"over_budget": 0, "battery_too_small": 0, "no_inverter": 0}

    def evaluate(panel: dict, n: int, bat: dict | None, bn: int) -> dict | None:
        key = (panel["id"], n, bat["id"] if bat else None, bn)
        if key in evaluated:
            return evaluated[key]
        if n < 1 or n > caps[panel["id"]]:
            return None
        kwp = n * panel["watts"] / 1000.0
        inv = simulate.pick_inverter(catalog, kwp, hybrid=bat is not None)
        if inv is None:
            rejected["no_inverter"] += 1
            return None
        pkg = simulate.build_package(panel, n, inv, bat, bn)
        if pkg["capex_php"] > budget_max_php:
            rejected["over_budget"] += 1
            return None
        q = simulate.quick_eval(pkg, series, load)
        if goal == "backup" and q["usable_battery_kwh"] + 1e-9 < need_backup_kwh:
            rejected["battery_too_small"] += 1
            return None
        item = {"pkg": pkg, "q": q, "obj": _objective(goal, q, pkg["capex_php"], goal_target_pct, system_type)}
        evaluated[key] = item
        return item

    # Grid-tied: never a battery. Hybrid and off-grid: always a battery (so are backup designs).
    needs_battery = goal == "backup" or system_type in ("hybrid", "off_grid")
    battery_opts: list[tuple[dict | None, int]] = [(None, 0)]
    if system_type != "on_grid":
        battery_opts += [(b, c) for b in batteries for c in (1, 2, 3)]
    for panel in panels:
        cap = caps[panel["id"]]
        if cap == 0:
            continue
        for bat, bn in battery_opts:
            if needs_battery and bat is None:
                continue
            step = 2 if bat is None else 4
            ns = sorted(set(list(range(2, cap + 1, step)) + [cap]))
            for n in ns:
                evaluate(panel, n, bat, bn)

    if not evaluated:
        reasons = []
        if rejected["over_budget"]:
            reasons.append("every option is over the budget")
        if rejected["battery_too_small"]:
            reasons.append("no battery combination covers the backup need")
        if rejected["no_inverter"]:
            reasons.append("no catalog inverter fits")
        raise ApiError("no_feasible_design", "I could not find a design that fits: " + ("; ".join(reasons) or "nothing fits the limits") + ".",
                       hint="Try a higher budget, a smaller backup need, or check the installation site size.", status=422)

    # Refine around the best few: try n +/- 1 on the same parts.
    best5 = sorted(evaluated.values(), key=lambda it: it["obj"])[:5]
    by_id = {p["id"]: p for p in panels}
    for it in best5:
        pk = it["pkg"]
        for dn in (-1, 1):
            evaluate(by_id[pk["panel"]["id"]], pk["panel_count"] + dn, pk["battery"], pk["battery_count"])

    ranked = sorted(evaluated.values(), key=lambda it: it["obj"])
    best = ranked[0]
    finalists = [(GOAL_LABELS.get(goal, "Best value"), best)]
    has_bat = best["pkg"]["battery"] is not None
    alt = next((it for it in ranked[1:] if (it["pkg"]["battery"] is not None) != has_bat), None)
    if alt is not None:
        finalists.append(("With battery" if not has_bat else "Without battery", alt))
    if goal != "max_savings_10y":
        top_profit = max(evaluated.values(), key=lambda it: it["q"]["net_25y_php"])
        if all(top_profit["pkg"]["id"] != f[1]["pkg"]["id"] for f in finalists):
            finalists.append(("Max savings", top_profit))
    finalists = finalists[:top]

    packages = []
    for label, it in finalists:
        pkg = dict(it["pkg"], label=label)
        roi = simulate.simulate_package(pkg, roof, load, year_set=ys)
        packages.append({"package": pkg, "roi": roi, "quick": {k: (round(v, 1) if isinstance(v, float) else v) for k, v in it["q"].items()}})

    target_met = None
    if goal == "cut_bill":
        target_met = best["q"]["bill_reduction_pct"] >= (goal_target_pct or 0.0)
    notes = [f"{len(evaluated)} designs were checked against your budget, installation site and goal."]
    type_notes = {
        "on_grid": "Grid-tied: no battery, so the system switches off during a blackout.",
        "hybrid": "Hybrid: a battery stores solar power for the evening and keeps essentials on during a blackout.",
        "off_grid": ("Off-grid: shown as the design that replaces the most grid power within your budget. A true off-grid system must also "
                     "be sized for the cloudiest days, often with a generator, so an installer has to confirm it."),
    }
    if system_type in type_notes:
        notes.append(type_notes[system_type])
    if budget_min_php:
        notes.append("The budget minimum is a guide only. The budget maximum is the hard limit.")
    if target_met is False:
        notes.append(f"No design within budget reaches a {goal_target_pct:g}% bill cut. The closest option is shown.")
    return {"goal": goal, "system_type": system_type, "goal_target_pct": goal_target_pct, "backup_hours": backup_hours, "target_met": target_met,
            "candidates_checked": len(evaluated), "roof_capacity_panels": {pid: c for pid, c in caps.items()},
            "weather_source": ys.source, "packages": packages, "notes": notes}
