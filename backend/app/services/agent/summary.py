"""Turn structured tool results into compact summaries and plain-text sentences.

Every number in these sentences comes straight from tool results (the LLM never computes anything).
"""
from __future__ import annotations

import re

from ..readiness import readiness
from . import reply_format
from .intake import goal_label, php

CAVEAT = "These are estimates for a licensed installer to confirm, and prices are suggestions from demo or public listings, so confirm with the seller."


def within10(v):
    """Payback is only shown inside the 10-year window."""
    return v if v is not None and v <= 10 else None


def _yrs(v) -> str:
    return "not within 10 years" if v is None else f"about {v:g} years"


def _headline_variant(roi: dict, net_metering: bool) -> tuple[str, dict]:
    src = roi if net_metering else roi["net_metering_off"]
    name = "hybrid" if src.get("hybrid") else "on_grid"
    return name, src[name]


def _scn(variant: dict) -> dict:
    return {s["name"]: s for s in variant["scenarios"]}


SYSTEM_NAMES = {"on_grid": "Grid-tied (on-grid)", "off_grid": "Off-grid", "hybrid": "Hybrid (solar + storage)"}


def summarize_analysis(optimize_res: dict, net_metering: bool = True, system_type: str | None = None, roof=None) -> dict:
    if system_type == "off_grid":
        net_metering = False  # no utility connection, so no export credit
    capacity = optimize_res.get("roof_capacity_panels", {})
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
            "battery_kwh": (round(bat["battery_kwh"] * p["battery_count"], 1) if bat and vname == "hybrid" else None),
            "roof_capacity_panels": capacity.get(p["panel"]["id"]),
            "capex_php": variant["capex_php"],
            "grid_only_monthly_bill_php": roi["grid_only"]["monthly_bill_php"],
            "bill_reduction_pct_year1": sc["expected"]["bill_reduction_pct_year1"],
            "payback_years": {"bad_year": within10(sc["pessimistic"]["payback_years"]), "expected": within10(sc["expected"]["payback_years"]),
                              "best_case": within10(sc["optimistic"]["payback_years"])},
            "net_profit_10y_php": {"bad_year": sc["pessimistic"]["net_profit_10y_php"], "expected": sc["expected"]["net_profit_10y_php"],
                                   "best_case": sc["optimistic"]["net_profit_10y_php"]},
            "year1_savings_php": sc["expected"]["year1_savings_php"],
            "lcoe_php_per_kwh": sc["expected"]["lcoe_php_per_kwh"],
            "year1_generation_kwh": sc["expected"]["year1_generation_kwh"],
            "co2_avoided_t_10y": sc["expected"]["co2_avoided_t_10y"],
        })
        if roof is not None:
            pkgs[-1]["readiness"] = readiness(roof, p, pkgs[-1], sc["expected"], net_metering, system_type)
    approx = optimize_res.get("weather_source") == "approximate"
    used = {a["key"]: a for a in optimize_res["packages"][0]["roi"].get("assumptions_used", [])}
    unverified = [k for k in ("export_credit_php_per_kwh", "install_cost_php_per_kw", "tariff_fixed_php_month")
                  if k in used and not used[k].get("verified")]
    return {
        "system_type": system_type,
        "unverified_drivers": unverified,
        "install_cost_php_per_kw": used.get("install_cost_php_per_kw", {}).get("value"),
        "goal": optimize_res["goal"], "target_met": optimize_res.get("target_met"),
        "weather_source": optimize_res.get("weather_source"), "weather_is_approximate": approx,
        "packages": pkgs, "notes": optimize_res.get("notes", []),
        "export_credit_php_per_kwh": optimize_res["packages"][0]["roi"]["export_credit_php_per_kwh"],
        "caveat": CAVEAT,
    }


def analysis_text(s: dict) -> str:
    """One short lead sentence. The details are in analysis_markdown, which the app appends under it."""
    top = s["packages"][0]
    kind = SYSTEM_NAMES.get(s.get("system_type") or "", "")
    kind = f" {kind.lower()}" if kind else ""
    return (f"Here is what I'd suggest ({top['label']}): a{kind} system with {top['panel_count']} panels ({top['kwp']:g} kWp), "
            f"about {php(top['capex_php'])} installed.")


def _range(lo, hi, fmt) -> str:
    return f"{fmt(lo)} to {fmt(hi)}"


def _pb(v) -> str:
    return "over 10 years" if v is None else f"{v:g} years"


def analysis_markdown(s: dict) -> str:
    """Customer-facing results block (headline table, comparison table, caveats) built only from tool results."""
    top = s["packages"][0]
    off_grid = s.get("system_type") == "off_grid"
    pb, pf = top["payback_years"], top["net_profit_10y_php"]
    kind = SYSTEM_NAMES.get(s.get("system_type") or "") or ("Hybrid (solar + storage)" if top["battery"] else "Grid-tied (on-grid)")
    cap = top.get("roof_capacity_panels")
    rows = [
        ("System type", kind),
        ("Solar panels", f"{top['panel_count']} × {top['panel']} = **{top['kwp']:g} kWp**"),
    ]
    if cap:
        rows.append(("Site use", f"{top['panel_count']} of {cap} panel spots on your installation site"))
    rows.append(("Inverter", top["inverter"]))
    if top["battery"]:
        kwh = f" ({top['battery_kwh']:g} kWh)" if top.get("battery_kwh") else ""
        rows.append(("Battery", f"{top['battery']}{kwh}"))
    rows += [
        ("Installed cost", f"**{php(top['capex_php'])}**"),
        ("Bill today", f"about {php(top['grid_only_monthly_bill_php'])} a month"),
        ("Grid power replaced, year 1" if off_grid else "Bill cut, year 1", f"**about {top['bill_reduction_pct_year1']:g}%**"),
        ("Payback compared with grid bills" if off_grid else "Payback",
         f"**{_pb(pb['expected'])}** (best case {_pb(pb['best_case'])}, bad weather year {_pb(pb['bad_year'])})"),
        ("10-year net profit", f"**{php(pf['expected'])}** (range {_range(pf['bad_year'], pf['best_case'], php)})"),
    ]
    out = [f"### Recommended: {top['label']}", "", "| | |", "|---|---|"]
    out += [f"| {k} | {v} |" for k, v in rows]
    if len(s["packages"]) > 1:
        out += ["", "**Compare the options**", "", "| Option | Panels | Cost | Bill cut | Payback | 10-year profit |", "|---|---|---|---|---|---|"]
        for p in s["packages"]:
            extra = f" + {p['battery_kwh']:g} kWh battery" if p.get("battery_kwh") else ""
            out.append(f"| {p['label']}{extra} | {p['panel_count']} ({p['kwp']:g} kWp) | {php(p['capex_php'])} | "
                       f"{p['bill_reduction_pct_year1']:g}% | {_pb(p['payback_years']['expected'])} | {php(p['net_profit_10y_php']['expected'])} |")
    notes = _caveats(s)
    if notes:
        out += ["", "**Good to know**", ""] + [f"- {n}" for n in notes]
    out += ["", f"> {s['caveat']}"]
    return "\n".join(out)


def _caveats(s: dict) -> list[str]:
    parts: list[str] = []
    if s.get("target_met") is False:
        parts.append("No option within your budget reaches your bill-cut target, so this is the closest one.")
    for n in s.get("notes", []):
        if n.startswith(("Grid-tied", "Hybrid", "Off-grid")):
            parts.append(n)
    checks = s["packages"][0].get("readiness", [])
    parts += [c["text"] for c in checks if c["status"] == "watch"]
    if checks:
        parts.append("Before you commit, also check the provider and the requirements; the Overview page lists all four checks.")
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
    return parts


def compare_nm_text(r: dict) -> str:
    on, off = r["net_metering_on"], r["net_metering_off"]
    return (f"With net metering, the expected 10-year net profit is about {php(on['net_profit_10y_php']['expected'])} and payback is {_yrs(on['payback_years']['expected'])}. "
            f"Without it, profit falls to about {php(off['net_profit_10y_php']['expected'])} and payback is {_yrs(off['payback_years']['expected'])}. "
            f"Exports are credited at about {php(r['export_credit_php_per_kwh'])} per kWh, an editable approximation of Meralco's generation charge that still needs to be verified.")


def assumptions_text(r: dict) -> str:
    items = r["assumptions"][:8]
    lines = "; ".join(f"{a['key'].replace('_', ' ')}: {a['value']:g} {a['unit']}".strip() if isinstance(a["value"], (int, float)) else f"{a['key']}: {a['value']}" for a in items)
    facts = " ".join(r.get("facts", [])[:2])
    return f"{facts} Key assumptions: {lines}. Some are judgement or unverified placeholders, listed as such in the full list."


def passport_text(r: dict) -> str:
    if r.get("already_issued"):
        return f"Your Solar Passport {r['id']} was already created for this option, so I'm showing it again."
    return f"Your Solar Passport {r['id']} is ready."


_CHECK_NAMES = {"sourced_inputs": "Inputs have sources", "reproducible": "Results re-run and matched"}
_CHECK_STATUS = {"pass": "Passed", "fail": "Failed", "n/a": "Partly: some inputs are unverified placeholders"}


def passport_markdown(r: dict) -> str:
    """Customer-facing Solar Passport card, built only from the tool result."""
    when = ""
    if r.get("created_at"):
        try:
            from datetime import datetime

            when = datetime.fromisoformat(str(r["created_at"])).strftime("%d %b %Y")
        except ValueError:
            when = str(r["created_at"])[:10]
    rows = [("Passport ID", f"**{r['id']}**")]
    if when:
        rows.append(("Issued", when))
    if r.get("option"):
        size = f" · {r['panels']} panels, {r['kwp']:g} kWp" if r.get("panels") else ""
        rows.append(("Option recorded", f"{r['option']}{size}"))
    rows.append(("Fingerprint", r["short_hash"]))
    for name, status in (r.get("checks_at_issue") or {}).items():
        rows.append((_CHECK_NAMES.get(name, name.replace("_", " ").capitalize()), _CHECK_STATUS.get(status, str(status))))
    rows.append(("Verify it", f"[Open the verify page]({r['verify_path']})"))
    out = ["### Your Solar Passport", "", "| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows]
    out += [
        "", "**What it tells you**", "",
        "- The results have not been changed since they were created.",
        "- The record is signed by Sol, and anyone with the link can check it.",
        "", "**What it does not tell you**", "",
        "- It does not prove that your real installation site matches the details you gave.",
        "- The figures are still estimates for a licensed installer to confirm.",
        "", "You can find it again under **Saved records**, where you can also download it.",
    ]
    return "\n".join(out)


def roof_fill_text(r: dict) -> str:
    if r.get("mode") == "design":
        return f"The map is back to your design with {r['panels']} panels."
    return f"The map now shows panels on the whole installation site: {r['panels']} panels, about {r['kwp']:g} kWp."


def roof_fill_markdown(r: dict) -> str:
    """Preview card for the 'fill my whole roof' view."""
    if r.get("mode") != "full":
        return ""
    rows = [
        ("Panels that fit", f"**{r['panels']}** × {r['panel_model']}"),
        ("Total size", f"**{r['kwp']:g} kWp**"),
        ("Panel area", f"about {r['panel_area_m2']:g} m² of your {r['roof_area_m2']:g} m² installation site"),
        ("Rough cost", f"about **{php(r['rough_cost_php'])}** for panels, installation and permits"),
        ("Your design", f"{r['design_panels']} panels · {r['design_kwp']:g} kWp · {php(r['design_cost_php'])}"),
    ]
    if r.get("budget_max_php"):
        over = r.get("over_budget_php") or 0
        rows.append(("Your budget", f"{php(r['budget_max_php'])} (**{php(over)} over**)" if over else f"{php(r['budget_max_php'])} (within budget)"))
    out = ["### Whole-site preview", "", "| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows]
    notes = [
        "This is a layout preview, not a recommendation. Your design is sized to your bill and budget.",
        f"The inverters are not priced here. The largest inverter in the price list is {r['largest_inverter_kw']:g} kW, so a system this size needs several.",
    ]
    if r.get("above_net_metering_cap"):
        notes.append(f"A system above {r['net_metering_cap_kw']:g} kW is over the residential net-metering limit, so the utility would need to approve it separately.")
    out += ["", "**Good to know**", ""] + [f"- {n}" for n in notes]
    out += ["", "Choose **Back to my design** to return to the recommended layout."]
    return "\n".join(out)


def roof_text(roof: dict) -> str:
    extra = " Please check the facing direction." if any("confirm" in n for n in roof.get("notes", [])) else ""
    return (f"I have your installation site outline: about {roof['area_m2']:g} m², facing {roof['azimuth_deg']:g}° (180° is south), "
            f"with {roof['usable_area_m2']:g} m² usable after the edge setback.{extra}")


def recommend_text(r: dict) -> str:
    why = (f"That is about all your site has room for (up to {r['site_kwp']:g} kWp), though your usage could use about {r['usage_kwp']:g} kWp."
           if r["limit"] == "site" else f"That covers your usage, and your site has room for up to {r['site_kwp']:g} kWp.")
    lo, hi = r["price_low_php"], r["price_high_php"]
    span = php(lo) if lo == hi else f"{php(lo)} to {php(hi)}"
    price = (f"Published {r['system_kind']} packages near that size cost about {span}."
             if r["price_basis"] == "published" else
             f"I have no published package that close in size, so my rough estimate is {span}, and real quotes can differ.")
    return (f"For your installation site (about {r['usable_area_m2']:g} m² usable) and about {r['monthly_kwh']:g} kWh a month, I'd aim for a "
            f"**{r['system_kind']} system of about {r['kwp']:g} kWp**. {why}\n\n{price}\n\n"
            f"So **{r['budget_label']}** looks like the right budget range. This is a rough size, and running the numbers will fine-tune it.")


def docs_text(r: dict, intent: str | None = None) -> str:
    """Scripted-mode answer: the best passage shaped by the question (steps, direct answer, comparison, explanation)."""
    if not r.get("passages"):
        return "I don't have a source for that, so I'd rather not guess. Meralco or your installer can confirm it."
    top = r["passages"][0]
    who = top["publisher"] or top["title"]
    us = " (a US example, not Philippine rules)" if top.get("region") == "US" else ""
    body = reply_format.clean_passage(re.sub(r"^\s*(?:#{1,6}\s+|[-*•]\s+)", "", top["text"], flags=re.M))
    sents = [x for x in re.split(r"(?<=[.!?])\s+(?=[A-Z\"'(])", body) if x.strip()]
    points = [reply_format.shorten(x) for x in sents[:5 if intent == "steps" else 3]]
    if not points:
        return "I found a page on that, but its text is not readable enough to quote. Open the source below to read it."  \
            + (f"\n\n> Source: [{who}]({top['source_url']})" if top["source_url"] else "")
    return reply_format.passage_answer(points, who, us, top["source_url"], intent or "explain")


def installers_text(r: dict) -> str:
    if r.get("needs_location"):
        return r["message"]
    if not r.get("total"):
        return f"The DOE registry has no solar installers listed for {r['region_name']}. Tell me another area and I'll check it."
    return (f"I've opened the {r['total']} solar installers registered with the DOE in {r['region_name']} in the side panel. The DOE does not endorse them and "
            "I haven't vetted them, so compare at least two written quotes.")


def packages_text(r: dict) -> str:
    if not r.get("found"):
        return r.get("message", "I don't have a published package near that size.")
    area = "" if r.get("in_your_area") else " None of the installers I have serve your area yet, so these are from elsewhere."
    if r.get("all_sample"):
        return "I don't have a real published package for this, so the table shows made-up samples. They are not offers."
    sample = " Packages marked Sample are made-up." if r.get("has_sample") else ""
    return f"I've opened ready-made packages near that size in the side panel. Real ones show the prices installers publish on their own sites, not quotes.{sample}{area}"


def render_tool_result(name: str, result: dict, intent: str | None = None) -> str:
    """Plain sentence for a tool result (used by the scripted agent and the number-guard fallback)."""
    if not isinstance(result, dict) or result.get("error"):
        msg = str((result or {}).get("message") or (result or {}).get("error") or "that didn't work").rstrip(". ")
        hint = str((result or {}).get("hint") or "").strip()
        return f"I couldn't do that: {msg}." + (f" {hint}" if hint else "")
    if name == "run_analysis":
        return analysis_text(result["summary"])
    if name == "compare_net_metering":
        return compare_nm_text(result)
    if name == "export_plan":
        return (f"Your plan for **{result['label']}** is ready. It has your installation site, budget, the package and the numbers. "
                "Tap the button below to download it as a PDF.")
    if name == "recommend_budget":
        return recommend_text(result)
    if name == "search_docs":
        return docs_text(result, intent)
    if name == "find_installers":
        return installers_text(result)
    if name == "package_details":
        if not result.get("found"):
            return result.get("message", "I don't have a package with that name.")
        if result.get("synthetic"):
            return f"{result['name']} is a made-up sample, so there is nobody to contact. Here is what it shows."
        return f"Here are the details for {result['name']} from {result['installer']}, with how to contact them. The price is what they published, not a quote."
    if name == "find_packages":
        return packages_text(result)
    if name == "solar_brief":
        return "Here's a quick brief on going solar with Meralco."
    if name == "explain_assumptions":
        return assumptions_text(result)
    if name == "issue_passport":
        return passport_text(result)
    if name == "toggle_roof_fill":
        return roof_fill_text(result)
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
        if "system_type" in a:
            bits.append(f"Got it: {SYSTEM_NAMES[a['system_type']]}.")
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


__all__ = ["summarize_analysis", "analysis_markdown", "passport_markdown", "roof_fill_markdown", "render_tool_result", "goal_label", "CAVEAT"]
