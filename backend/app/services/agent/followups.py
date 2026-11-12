"""Smarter suggestion pills: after a rules answer, offer the next questions the document library can answer.

Pills are built from code, never from the model, so each one is a question we know has a sourced answer.
"""
from __future__ import annotations

from .. import installers
from . import intake

# source file id -> (pill label, question sent when tapped). Every question must route to search_docs (see tests).
FOLLOW: dict[str, list[tuple[str, str]]] = {
    "solar-brief": [("Cost to apply", "How much does it cost to apply for net metering?"), ("Micro solar permit", "Do I need a building permit for a micro solar system?"),
                    ("During a blackout", "What happens to my solar during a blackout?")],
    "meralco-solar-hub": [("Who can apply?", "Who can apply for net metering?"), ("What is zero export?", "What is a zero export solar system?")],
    "meralco-net-metering": [("Cost to apply", "How much does it cost to apply for net metering?"), ("Do credits expire?", "Do net metering credits expire?"),
                             ("During a blackout", "What happens to my solar during a blackout?")],
    "meralco-nm-application": [("Application steps", "What are the steps to apply for net metering?"), ("The ERC fee", "How much is the ERC Certificate of Compliance application fee?"),
                               ("Transformer limit", "How many kW can my transformer host?")],
    "meralco-der": [("Micro solar permit", "Do I need a building permit for a micro solar system?"), ("Battery allowed?", "Can I add a battery to a net metering system?")],
    "ph-own-use-solar-rules": [("Notify Meralco?", "Do I need to notify Meralco about a micro solar system?"), ("Credits for exports?", "Do exports from a micro solar system earn bill credits?")],
    "choosing-an-installer": [("Registered installers", "Which solar installers are registered in Metro Manila?"), ("What to ask them", "What should I ask an installer?")],
    "doe-solar-pv-installer-registry": [("Does the DOE endorse them?", "Does the DOE endorse the registered solar installers?"), ("What to ask them", "What should I ask an installer?")],
    "installer-mspectrum": [("Registered installers", "Which solar installers are registered in Metro Manila?"), ("What to ask them", "What should I ask an installer?")],
    "doe-us-storage-basics": [("Battery and net metering", "Can I add a battery to a net metering system?"), ("During a blackout", "What happens to my solar during a blackout?")],
    "doe-us-performance": [("Panel warranty", "What is the typical panel warranty?"), ("Panel degradation", "What is the yearly panel degradation?")],
    "doe-us-pv-basics": [("Panel warranty", "What is the typical panel warranty?"), ("Cost to apply", "How much does it cost to apply for net metering?")],
    "doe-us-how-solar-works": [("During a blackout", "What happens to my solar during a blackout?"), ("Cost to apply", "How much does it cost to apply for net metering?")],
    "doe-us-homeowners-guide": [("What to ask them", "What should I ask an installer?"), ("Application steps", "What are the steps to apply for net metering?")],
    "pvgis-manual": [("Panel degradation", "What is the yearly panel degradation?"), ("Application steps", "What are the steps to apply for net metering?")],
    "huawei-hybrid-inverter": [("Battery allowed?", "Can I add a battery to a net metering system?"), ("Panel warranty", "What is the typical panel warranty?")],
    "jinko-tiger-neo": [("Panel degradation", "What is the yearly panel degradation?"), ("Battery allowed?", "Can I add a battery to a net metering system?")],
}
LOW_PRIORITY = ("fu_assumptions", "fu_net_metering_off", "fu_fill_roof")  # dropped first when pills overflow; the roof toggle that applies now is never listed


def _pill(label: str, text: str) -> dict:
    return intake._s("q_" + intake.norm(text).replace(" ", "_")[:40], label, "Ask Sol", text)


def after_analysis(summary: dict | None) -> list[tuple[str, str]]:
    """Questions raised by the readiness warnings of the top option."""
    if not summary or not summary.get("packages"):
        return []
    top, out = summary["packages"][0], []
    size = next((c for c in top.get("readiness", []) if c["id"] == "size"), None)
    if size and size["status"] == "watch" and not top.get("battery") and summary.get("system_type") != "off_grid":
        out.append(("Would a battery help?", "Can I add a battery to a net metering system?"))
    if summary.get("system_type") == "off_grid":
        out.append(("Permit for off-grid?", "Do I need a building permit for a zero export solar system?"))
    else:
        out.append(("What I need to do", "What are the steps to apply for net metering?"))
    out.append(("What to ask installers", "What should I ask an installer?"))
    return out


AREA_PILLS = [("Metro Manila", "I'm in Metro Manila"), ("Central Luzon", "I'm in Central Luzon"), ("CALABARZON", "I'm in CALABARZON"),
              ("Somewhere else", "Somewhere else")]


def installer_pills(ctx, limit: int) -> list[dict] | None:
    """Pills while choosing an area for installers (replace the intake pills), or the ones after the table."""
    res = [r for r in ctx.results_of("find_installers") if isinstance(r, dict)]
    if not res:
        return None
    r = res[-1]
    if r.get("needs_location"):
        city = r.get("household_city")
        out = [_pill(f"I'm in {city}", f"I'm in {city}")] if city and installers.region_for(city) else []
        out += [_pill(lbl, txt) for lbl, txt in AREA_PILLS]
        return out[:limit]
    return []


def suggestions(ctx, base: list[dict], limit: int) -> list[dict]:
    """Intake/follow-up pills first, then up to two topic-aware questions the user has not asked yet."""
    away = installer_pills(ctx, limit)
    if away:  # waiting for the user's area: the area choices are the only sensible pills
        return away
    s = ctx.session
    asked = {intake.norm(h["text"]) for h in s.history[-14:] if h["role"] == "user"} | {intake.norm(ctx.user_text or "")}
    cands: list[tuple[str, str]] = []
    docs = [r for r in ctx.results_of("search_docs") if isinstance(r, dict) and r.get("passages")]
    if docs:
        for ps in docs[-1]["passages"][:3]:
            cands += FOLLOW.get(ps.get("id", ""), [])
    for res in ctx.results_of("run_analysis")[-1:]:
        if isinstance(res, dict):
            cands += after_analysis(res.get("summary"))
    if ctx.results_of("solar_brief"):
        cands += FOLLOW["solar-brief"]
    info = [r for r in ctx.results_of("package_details") if isinstance(r, dict) and r.get("found")]
    if info:
        cands += [("What to ask them", "What should I ask an installer?"), ("Back to the packages", "Show me real ready-made packages")]
        if not info[-1].get("synthetic"):
            cands.append(("Find other installers", "Can you suggest me some installers?"))
    pk = [r for r in ctx.results_of("find_packages") if isinstance(r, dict) and r.get("found")]
    if pk:
        cands += [("Without a battery" if pk[-1].get("kind") != "grid-tied" else "With a battery",
                   "Show real packages without a battery" if pk[-1].get("kind") != "grid-tied" else "Show real packages with a battery"),
                  ("Find installers", "Can you suggest me some installers?")]
    if ctx.results_of("run_analysis") and not pk:
        cands.append(("Real packages", "Show me real ready-made packages"))
    inst = [r for r in ctx.results_of("find_installers") if isinstance(r, dict) and r.get("found")]
    if inst:  # after the table: show-all first, then how to compare, then another area
        r = inst[-1]
        if r["total"] > r["shown"]:
            cands.append((f"Show all {r['total']}", f"Show all solar installers in {r['region_name']}"))
        cands += [("What to ask them", "What should I ask an installer?"), ("Another area", "Show solar installers somewhere else")]
    if not cands and "summary" in s.results and intake.next_slot(s) == "done":
        cands += after_analysis(s.results["summary"])
    seen, fu = set(), []
    for label, text in cands:
        n = intake.norm(text)
        if n in asked or n in seen:
            continue
        seen.add(n)
        fu.append(_pill(label, text))
    if "summary" in s.results and intake.next_slot(s) == "done" and not inst and intake.norm("Can I export my plan?") not in asked:
        fu = [_pill("Export my plan", "Can I export my plan?")] + [x for x in fu if x["id"] != "q_can_i_export_my_plan"]  # an action, not a library question
    out = base + fu[: 3 if inst else 2]
    for lid in LOW_PRIORITY:
        if len(out) <= limit:
            break
        out = [x for x in out if x["id"] != lid]
    return out[:limit]
