"""Turn structured tool results into compact summaries and plain-text sentences.

Every number in these sentences comes straight from tool results (the LLM never computes anything).
"""
from __future__ import annotations

from ..readiness import readiness
from .intake import goal_label, php

CAVEAT = "These are estimates for a licensed installer to confirm, and prices are suggestions from demo or public listings, so confirm with the seller."


def _yrs(v) -> str:
    return "not within 25 years" if v is None else f"about {v:g} years"


def _headline_variant(roi: dict, net_metering: bool) -> tuple[str, dict]:
    src = roi if net_metering else roi["net_metering_off"]
    name = "hybrid" if src.get("hybrid") else "on_grid"
    return name, src[name]


def _scn(variant: dict) -> dict:
    return {s["name"]: s for s in variant["scenarios"]}


def summarize_analysis(optimize_res: dict, net_metering: bool = True, roof=None) -> dict:
    pkgs = []
    for item in optimize_res["packages"]:
        p, roi = item["package"], item["roi"]
        vname, variant = _headline_variant(roi, net_metering)
        sc = _scn(variant)
        bat = p.get("battery")
        pkgs.append({
            "label": p["label"], "package_id": p["id"], "variant": vname, "net_metering": net_metering,
            "kwp": p["kwp"], "panel_count": p["panel_count"],
            "panel": f"{p['panel']['brand']} {p['panel']['model']} ({p['panel']['watts']:g} W)",
            "inverter": f"{p['inverter']['brand']} {p['inverter']['model']} ({p['inverter']['inverter_ac_kw']:g} kW)",
            "battery": (f"{bat['brand']} {bat['model']} x{p['battery_count']}" if bat and vname == "hybrid" else None),
            "capex_php": variant["capex_php"],
            "grid_only_monthly_bill_php": roi["grid_only"]["monthly_bill_php"],
            "bill_reduction_pct_year1": sc["expected"]["bill_reduction_pct_year1"],
            "payback_years": {"bad_year": sc["pessimistic"]["payback_years"], "expected": sc["expected"]["payback_years"],
                              "best_case": sc["optimistic"]["payback_years"]},
            "net_profit_25y_php": {"bad_year": sc["pessimistic"]["net_profit_25y_php"], "expected": sc["expected"]["net_profit_25y_php"],
                                   "best_case": sc["optimistic"]["net_profit_25y_php"]},
            "year1_savings_php": sc["expected"]["year1_savings_php"],
            "lcoe_php_per_kwh": sc["expected"]["lcoe_php_per_kwh"],
            "year1_generation_kwh": sc["expected"]["year1_generation_kwh"],
            "co2_avoided_t_25y": sc["expected"]["co2_avoided_t_25y"],
        })
        if roof is not None:
            pkgs[-1]["readiness"] = readiness(roof, p, pkgs[-1], sc["expected"], net_metering)
    approx = optimize_res.get("weather_source") == "approximate"
    used = {a["key"]: a for a in optimize_res["packages"][0]["roi"].get("assumptions_used", [])}
    unverified = [k for k in ("export_credit_php_per_kwh", "install_cost_php_per_kw", "tariff_fixed_php_month")
                  if k in used and not used[k].get("verified")]
    return {
        "unverified_drivers": unverified,
        "install_cost_php_per_kw": used.get("install_cost_php_per_kw", {}).get("value"),
        "goal": optimize_res["goal"], "target_met": optimize_res.get("target_met"),
        "weather_source": optimize_res.get("weather_source"), "weather_is_approximate": approx,
        "packages": pkgs, "notes": optimize_res.get("notes", []),
        "export_credit_php_per_kwh": optimize_res["packages"][0]["roi"]["export_credit_php_per_kwh"],
        "caveat": CAVEAT,
    }


def analysis_text(s: dict) -> str:
    top = s["packages"][0]
    bat = f" with a {top['battery']} battery" if top["battery"] else ""
    pb, pf = top["payback_years"], top["net_profit_25y_php"]
    parts = [
        f"Here's what I'd suggest ({top['label']}): {top['panel_count']} panels, {top['kwp']:g} kWp in total, {top['inverter']}{bat}, about {php(top['capex_php'])} installed.",
        f"Your bill of roughly {php(top['grid_only_monthly_bill_php'])} a month could drop by about {top['bill_reduction_pct_year1']:g}% in year 1.",
        f"Payback is {_yrs(pb['expected'])} (best case {_yrs(pb['best_case'])}, bad weather year {_yrs(pb['bad_year'])}), and the 25-year net profit is about {php(pf['expected'])} (range {php(pf['bad_year'])} to {php(pf['best_case'])}).",
    ]
    if s.get("target_met") is False:
        parts.append("No option within your budget reaches your bill-cut target, so this is the closest one.")
    if len(s["packages"]) > 1:
        parts.append("I also have " + ", ".join(p["label"] for p in s["packages"][1:]) + " to compare.")
    top_checks = top.get("readiness", [])
    parts += [c["text"] for c in top_checks if c["status"] == "watch"]
    if top_checks:
        parts.append("Before you commit, also check the provider and the Meralco requirements; the Overview page lists all four checks.")
    if s.get("weather_is_approximate"):
        parts.append("Sunlight data is an approximate typical year because PVGIS could not be reached.")
    drivers = []
    if "export_credit_php_per_kwh" in s.get("unverified_drivers", []):
        drivers.append(f"the net-metering export credit (assumed at about {php(s['export_credit_php_per_kwh'])} per kWh)")
    if "install_cost_php_per_kw" in s.get("unverified_drivers", []):
        drivers.append(f"the installation cost (assumed at about {php(s['install_cost_php_per_kw'])} per kW)")
    if "tariff_fixed_php_month" in s.get("unverified_drivers", []):
        drivers.append("fixed monthly charges (not modelled, so a bill cut near 100% would be lower on a real bill)")
    if drivers:
        parts.append("These results lean on unverified placeholders: " + "; ".join(drivers) + ".")
    parts.append(s["caveat"])
    return " ".join(parts)


def compare_nm_text(r: dict) -> str:
    on, off = r["net_metering_on"], r["net_metering_off"]
    return (f"With net metering, the expected 25-year net profit is about {php(on['net_profit_25y_php']['expected'])} and payback is {_yrs(on['payback_years']['expected'])}. "
            f"Without it, profit falls to about {php(off['net_profit_25y_php']['expected'])} and payback is {_yrs(off['payback_years']['expected'])}. "
            f"Exports are credited at about {php(r['export_credit_php_per_kwh'])} per kWh, an editable approximation of Meralco's generation charge that still needs to be verified.")


def assumptions_text(r: dict) -> str:
    items = r["assumptions"][:8]
    lines = "; ".join(f"{a['key'].replace('_', ' ')}: {a['value']:g} {a['unit']}".strip() if isinstance(a["value"], (int, float)) else f"{a['key']}: {a['value']}" for a in items)
    facts = " ".join(r.get("facts", [])[:2])
    return f"{facts} Key assumptions: {lines}. Some are judgement or unverified placeholders, listed as such in the full list."


def passport_text(r: dict) -> str:
    return (f"Your Solar Passport is {r['id']} (hash {r['short_hash']}). Anyone can check it at {r['verify_path']}. "
            "It proves the record is unchanged and signed by Sol, not that your real roof matches the inputs.")


def roof_text(roof: dict) -> str:
    extra = " Please check the facing direction." if any("confirm" in n for n in roof.get("notes", [])) else ""
    return (f"I have your roof outline: about {roof['area_m2']:g} m², facing {roof['azimuth_deg']:g}° (180° is south), "
            f"with {roof['usable_area_m2']:g} m² usable after the edge setback.{extra}")


def docs_text(r: dict) -> str:
    """Scripted-mode answer: the best passage, trimmed to whole sentences, with its source."""
    if not r.get("passages"):
        return "I don't have a source for that, so I'd rather not guess. Meralco or your installer can confirm it."
    top = r["passages"][0]
    sents = [x for x in top["text"].replace("\n", " ").split(". ") if x.strip()]
    body = ". ".join(sents[:3]).strip()
    body += "" if body.endswith(".") else "."
    us = " (a US example, not Philippine rules)" if top.get("region") == "US" else ""
    return f"From {top['publisher'] or top['title']}{us}: {body} Source: {top['source_url']}" if top["source_url"] else f"{body}"


def render_tool_result(name: str, result: dict) -> str:
    """Plain sentence for a tool result (used by the scripted agent and the number-guard fallback)."""
    if not isinstance(result, dict) or result.get("error"):
        msg = str((result or {}).get("message") or (result or {}).get("error") or "that didn't work").rstrip(". ")
        hint = str((result or {}).get("hint") or "").strip()
        return f"I couldn't do that: {msg}." + (f" {hint}" if hint else "")
    if name == "run_analysis":
        return analysis_text(result["summary"])
    if name == "compare_net_metering":
        return compare_nm_text(result)
    if name == "search_docs":
        return docs_text(result)
    if name == "explain_assumptions":
        return assumptions_text(result)
    if name == "issue_passport":
        return passport_text(result)
    if name == "get_building_outline":
        if result.get("found"):
            return roof_text(result["roof"])
        return result.get("message", "I couldn't find a building outline there.") + " Let's draw it instead."
    if name == "geocode_address" and result.get("auto_selected") and result.get("roof"):
        return roof_text(result["roof"])
    if name == "geocode_address" and not result.get("candidates"):
        return result.get("message") or "I couldn't find that address."
    if name == "search_products":
        return result.get("message", "")
    if name == "update_profile":
        bits = []
        a = result.get("applied", {})
        if "monthly_kwh" in a:
            bits.append(f"Got it, about {a['monthly_kwh']:g} kWh a month.")
        if "monthly_bill_php" in a:
            bits.append(f"Noted, a {php(a['monthly_bill_php'])} monthly bill.")
        if a.get("load_confirmed") and "monthly_kwh" not in a and "monthly_bill_php" not in a:
            bits.append("Okay, I'll use that usage.")
        if "budget_max_php" in a:
            bits.append(f"Budget noted: up to {php(a['budget_max_php'])}.")
        if "goal" in a:
            bits.append("Goal noted.")
        if "goal_target_pct" in a:
            bits.append(f"Target: cut the bill by {a['goal_target_pct']:g}%.")
        if "backup_hours" in a:
            bits.append(f"Backup: {a['backup_hours']:g} hours.")
        if "net_metering" in a:
            bits.append("Net metering is on." if a["net_metering"] else "I'll show results without net metering.")
        for e in result.get("errors", []):
            bits.append(f"I couldn't use that: {e}.")
        return " ".join(bits)
    return ""


__all__ = ["summarize_analysis", "render_tool_result", "goal_label", "CAVEAT"]
