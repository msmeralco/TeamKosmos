"""The deterministic brain of the conversation.

Code (not the LLM) decides which question comes next, validates every value, and builds the
clickable choices. The LLM only phrases things and extracts values through tool calls.
"""
from __future__ import annotations

import re
from typing import Any

from ..assumptions import A
from .session import GOALS, TEMPLATES, Session

Suggestion = dict  # {"id", "label", "hint"?, "text"}

# ---- limits (validation) -------------------------------------------------------------
KWH_RANGE = (30.0, 5000.0)
BILL_RANGE = (300.0, 200_000.0)
BUDGET_RANGE = (0.0, 10_000_000.0)
TARGET_RANGE = (5.0, 100.0)
BACKUP_RANGE = (1.0, 48.0)


def php(n: float) -> str:
    return f"₱{n:,.0f}"


def norm(text: str) -> str:
    return re.sub(r"[^\w₱%.]+", " ", (text or "").lower()).strip()


# ---- static choice texts ---------------------------------------------------------------
ROOF_CHOICES = {
    "address": ("Type my address", "I'll find the roof outline from OpenStreetMap", "I'll type my address"),
    "draw": ("Draw on the map", "Trace the roof on the satellite map", "I'll draw my roof on the map"),
    "sketch": ("Sketch on a canvas", "Draw with a metre scale on a blank canvas", "I'll sketch my roof on a blank canvas"),
}
BUDGETS = [
    ("b1", 0.0, 150_000.0, "Under ₱150,000"),
    ("b2", 150_000.0, 300_000.0, "₱150,000 to ₱300,000"),
    ("b3", 300_000.0, 500_000.0, "₱300,000 to ₱500,000"),
    ("b4", 500_000.0, 1_000_000.0, "₱500,000 or more"),
]
GOAL_CHOICES = {
    "cut_bill": ("Cut my bill", "Reach a target bill reduction", "I want to cut my electricity bill"),
    "max_savings_10y": ("Max 10-year savings", "Most money saved over ten years", "I want the biggest 10-year savings"),
    "fastest_payback": ("Fastest payback", "Get my money back soonest", "I want the fastest payback"),
    "backup": ("Blackout backup", "Keep essentials on during outages", "I want blackout backup"),
}
CUT_TARGETS = (50, 70, 90)
BACKUP_OPTIONS = (4, 8)
CHANGE_CHOICES = {
    "roof": ("Change my roof", "Pick a different address or drawing", "Change my roof"),
    "load": ("Change my bill", "Use a different usage or bill", "Change my bill"),
    "budget": ("Change my budget", "Pick another budget range", "Change my budget"),
    "goal": ("Change my goal", "Pick another goal", "Change my goal"),
}
FOLLOW_UPS = {
    "net_metering_off": ("net metering off", "See results without net metering", "What if net metering is off?", "compare_net_metering"),
    "assumptions": ("Show the assumptions", "Every number with its source", "Show me the assumptions", "explain_assumptions"),
    "passport": ("Create my Solar Passport", "A signed record anyone can verify", "Create my Solar Passport", "issue_passport"),
}
RUN_TEXT = "Yes, run the numbers"
CHANGE_TEXT = "I want to change something"
OTHER_ADDRESS_TEXT = "None of these, I'll draw it instead"
USE_ADDRESS_TEXT = "Use my address instead"
SKETCH_INSTEAD_TEXT = "I'll sketch it on a canvas instead"
DRAW_INSTEAD_TEXT = "I'll draw it on the map instead"


# ---- slot machine ----------------------------------------------------------------------
def next_slot(session: Session) -> str:
    p = session.profile
    if session.pending.get("changing"):
        return "change"
    if p.roof is None:
        if p.roof_method is None:
            return "roof_method"
        if p.roof_method == "address":
            return "roof_pick" if session.pending.get("candidates") else "roof_address"
        return "roof_draw"
    if not p.load_confirmed or (p.monthly_kwh is None and p.monthly_bill_php is None):
        return "load"
    if p.budget_max_php is None:
        return "budget"
    if p.goal is None:
        return "goal"
    if p.goal == "cut_bill" and p.goal_target_pct is None:
        return "goal_param"
    if p.goal == "backup" and p.backup_hours is None:
        return "goal_param"
    if not p.confirmed:
        return "confirm"
    if "analysis" not in session.results:
        return "run"
    return "done"


def _clear_for_change(session: Session) -> None:
    session.pending.pop("changing", None)
    session.invalidate_results()


def apply_updates(session: Session, **fields: Any) -> tuple[dict, list[str]]:
    """Validate and apply profile updates. Returns (applied, errors)."""
    p = session.profile
    applied: dict[str, Any] = {}
    errors: list[str] = []
    before = p.model_dump()

    def num(name: str, rng: tuple[float, float], label: str) -> float | None:
        raw = fields.get(name)
        if raw is None:
            return None
        try:
            value = float(raw)
        except (TypeError, ValueError):
            errors.append(f"{label} must be a number")
            return None
        if not rng[0] <= value <= rng[1]:
            errors.append(f"{label} must be between {rng[0]:g} and {rng[1]:g}")
            return None
        return value

    kwh = num("monthly_kwh", KWH_RANGE, "Monthly kWh")
    if kwh is not None:
        p.monthly_kwh, p.monthly_bill_php = kwh, None
        p.load_source = "bill_photo" if fields.get("load_source") == "bill_photo" else "user"
        p.load_confirmed = True
        applied["monthly_kwh"] = kwh
    bill = num("monthly_bill_php", BILL_RANGE, "Monthly bill")
    if bill is not None:
        p.monthly_bill_php, p.monthly_kwh = bill, None
        p.load_source = "bill_photo" if fields.get("load_source") == "bill_photo" else "user"
        p.load_confirmed = True
        applied["monthly_bill_php"] = bill

    tmpl = fields.get("household_template")
    if tmpl is not None:
        if tmpl in TEMPLATES:
            p.household_template = tmpl
            applied["household_template"] = tmpl
        else:
            errors.append(f"household_template must be one of {', '.join(TEMPLATES)}")

    if fields.get("confirm_load"):
        if p.monthly_kwh is None and p.monthly_bill_php is None:
            errors.append("There is no usage or bill to confirm yet")
        else:
            p.load_confirmed = True
            applied["load_confirmed"] = True

    bmin = num("budget_min_php", BUDGET_RANGE, "Budget minimum")
    bmax = num("budget_max_php", BUDGET_RANGE, "Budget maximum")
    if bmin is not None or bmax is not None:
        new_min = bmin if bmin is not None else (p.budget_min_php or 0.0)
        new_max = bmax if bmax is not None else p.budget_max_php
        if new_max is None:
            errors.append("Budget maximum is needed")
        elif new_min > new_max:
            errors.append("Budget minimum cannot be above the maximum")
        elif new_max < 20_000:
            errors.append("Budget maximum is too low for a solar system (minimum ₱20,000)")
        else:
            p.budget_min_php, p.budget_max_php = new_min, new_max
            applied["budget_min_php"], applied["budget_max_php"] = new_min, new_max

    goal = fields.get("goal")
    if goal is not None:
        if goal in GOALS:
            if p.goal is not None and goal != p.goal:
                p.goal_target_pct = None
                p.backup_hours = None
            p.goal = goal
            applied["goal"] = goal
        else:
            errors.append(f"goal must be one of {', '.join(GOALS)}")
    target = num("goal_target_pct", TARGET_RANGE, "Bill reduction target")
    if target is not None:
        if (p.goal or goal) == "cut_bill" or p.goal is None:
            p.goal_target_pct = target
            applied["goal_target_pct"] = target
        else:
            errors.append("A bill reduction target only applies to the 'cut my bill' goal")
    hours = num("backup_hours", BACKUP_RANGE, "Backup hours")
    if hours is not None:
        if (p.goal or goal) == "backup" or p.goal is None:
            p.backup_hours = hours
            applied["backup_hours"] = hours
        else:
            errors.append("Backup hours only apply to the 'blackout backup' goal")

    if fields.get("net_metering") is not None:
        p.net_metering = bool(fields["net_metering"])
        applied["net_metering"] = p.net_metering

    method = fields.get("roof_method")
    if method is not None:
        if method in ("address", "draw", "sketch"):
            if method != p.roof_method or p.roof is not None:
                p.roof = None
                session.pending.pop("candidates", None)
                session.pending.pop("candidate_texts", None)
            p.roof_method = method
            applied["roof_method"] = method
        else:
            errors.append("roof_method must be address, draw or sketch")

    changed = p.model_dump() != before
    if changed:
        # Inputs changed: any earlier analysis is stale and the summary must be re-confirmed.
        session.invalidate_results()

    if fields.get("confirm_summary"):
        slot_now = next_slot(session)
        if slot_now == "confirm":
            p.confirmed = True
            applied["confirmed"] = True
        elif slot_now == "run" and p.confirmed:
            applied["confirmed"] = True  # already confirmed; nothing to change
        else:
            errors.append("Not everything is filled in yet, so there is nothing to confirm")
    return applied, errors


# ---- choices -------------------------------------------------------------------------------
def _s(id_: str, label: str, hint: str, text: str) -> Suggestion:
    return {"id": id_, "label": label, "hint": hint, "text": text}


def choices_for(slot: str, session: Session) -> list[Suggestion]:
    p = session.profile
    if slot == "roof_method":
        return [_s(f"roof_{k}", *v) for k, v in ROOF_CHOICES.items()]
    if slot == "roof_address":
        return [
            _s("roof_draw", "Draw on the map", "Skip the lookup and trace it yourself", ROOF_CHOICES["draw"][2]),
            _s("roof_sketch", *ROOF_CHOICES["sketch"]),
        ]
    if slot == "roof_pick":
        out = []
        for i, c in enumerate((session.pending.get("candidates") or [])[:3]):
            out.append(_s(f"cand_{i}", str(c["label"])[:48], "Use this address", f"Use {str(c['label'])[:120]}"))
        out.append(_s("cand_none", "None of these", "Draw the roof instead", OTHER_ADDRESS_TEXT))
        return out
    if slot == "roof_draw":
        if p.roof_method == "draw":
            return [_s("roof_address", "Use my address", "Look up the outline instead", USE_ADDRESS_TEXT),
                    _s("roof_sketch", "Sketch on a canvas", "Use a metre scale instead", SKETCH_INSTEAD_TEXT)]
        return [_s("roof_address", "Use my address", "Look up the outline instead", USE_ADDRESS_TEXT),
                _s("roof_draw", "Draw on the map", "Trace on the satellite map", DRAW_INSTEAD_TEXT)]
    if slot == "load":
        out = []
        if p.monthly_kwh:
            out.append(_s("load_use", f"Use {p.monthly_kwh:g} kWh a month", "From the household profile",
                          f"Yes, use {p.monthly_kwh:g} kWh per month"))
        elif p.monthly_bill_php:
            out.append(_s("load_use", f"Use a {php(p.monthly_bill_php)} bill", "As you told me",
                          f"Yes, use my {php(p.monthly_bill_php)} monthly bill"))
        out.append(_s("load_bill", "I'll type my bill", "Pesos per month or kWh", "I'll type my monthly bill"))
        out.append(_s("load_photo", "Attach a bill photo", "I'll read it and ask you to confirm", "I'll attach a photo of my bill"))
        return out
    if slot == "budget":
        return [_s(bid, label, "Whole system, installed", f"My budget is {label[0].lower() + label[1:] if label.startswith('Under') else label}")
                for bid, _lo, _hi, label in BUDGETS]
    if slot == "goal":
        return [_s(f"goal_{k}", *v) for k, v in GOAL_CHOICES.items()]
    if slot == "goal_param":
        if p.goal == "cut_bill":
            return [_s(f"cut_{t}", f"Cut by {t}%", "Target bill reduction", f"Cut my bill by {t}%") for t in CUT_TARGETS]
        return [_s(f"backup_{h}", f"{h} hours", "Essential loads only", f"I need {h} hours of backup") for h in BACKUP_OPTIONS]
    if slot == "confirm":
        return [_s("run", "Run the numbers", "Simulate and compare options", RUN_TEXT),
                _s("change", "Change something", "Roof, bill, budget or goal", CHANGE_TEXT)]
    if slot == "change":
        return [_s(f"chg_{k}", *v) for k, v in CHANGE_CHOICES.items()]
    if slot == "run":
        return [_s("run", "Run the numbers", "Simulate and compare options", RUN_TEXT)]
    if slot == "done":
        out = []
        for k, (label, hint, text, _tool) in FOLLOW_UPS.items():
            if k == "passport" and "passport" in session.results:
                continue
            out.append(_s(f"fu_{k}", label.capitalize() if k == "net_metering_off" else label, hint, text))
        out.append(_s("change", "Change something", "Roof, bill, budget or goal", CHANGE_TEXT))
        return out
    return []


# ---- exact-match choice handling -----------------------------------------------------------
def _static_table() -> dict[str, tuple]:
    t: dict[str, tuple] = {}
    for k, v in ROOF_CHOICES.items():
        t[norm(v[2])] = ("update", {"roof_method": k})
    t[norm(USE_ADDRESS_TEXT)] = ("update", {"roof_method": "address"})
    t[norm(SKETCH_INSTEAD_TEXT)] = ("update", {"roof_method": "sketch"})
    t[norm(DRAW_INSTEAD_TEXT)] = ("update", {"roof_method": "draw"})
    t[norm(OTHER_ADDRESS_TEXT)] = ("update", {"roof_method": "draw"})
    t[norm("I'll type my monthly bill")] = ("note", "load_bill")
    t[norm("I'll attach a photo of my bill")] = ("note", "load_photo")
    for bid, lo, hi, label in BUDGETS:
        lab = label[0].lower() + label[1:] if label.startswith("Under") else label
        t[norm(f"My budget is {lab}")] = ("update", {"budget_min_php": lo, "budget_max_php": hi})
    for k, v in GOAL_CHOICES.items():
        t[norm(v[2])] = ("update", {"goal": k})
    for pct in CUT_TARGETS:
        t[norm(f"Cut my bill by {pct}%")] = ("update", {"goal": "cut_bill", "goal_target_pct": float(pct)})
    for h in BACKUP_OPTIONS:
        t[norm(f"I need {h} hours of backup")] = ("update", {"goal": "backup", "backup_hours": float(h)})
    t[norm(RUN_TEXT)] = ("update", {"confirm_summary": True})
    t[norm(CHANGE_TEXT)] = ("changing", None)
    for k, v in CHANGE_CHOICES.items():
        t[norm(v[2])] = ("change", k)
    for k, (_l, _h, text, tool) in FOLLOW_UPS.items():
        t[norm(text)] = ("tool", tool)
    return t


_TABLE = _static_table()
_USE_LOAD = re.compile(r"^yes use (?:my )?₱?[\d\s.]+?\s*(kwh per month|monthly bill)$")


def match_choice(session: Session, text: str) -> dict | None:
    """Return an action for a known suggestion text, or None. Does not mutate the session."""
    n = norm(text)
    if not n:
        return None
    if n in _TABLE:
        kind, payload = _TABLE[n]
        return {"kind": kind, "payload": payload}
    m = _USE_LOAD.match(n)
    if m:
        return {"kind": "update", "payload": {"confirm_load": True}}
    texts = session.pending.get("candidate_texts") or {}
    for cand_text, idx in texts.items():
        if norm(cand_text) == n:
            return {"kind": "pick", "payload": int(idx)}
    return None


def run_action(session: Session, action: dict) -> tuple[dict, list[str]]:
    """Apply a matched action to the session. Tool actions are returned for the caller to execute."""
    kind, payload = action["kind"], action["payload"]
    if kind == "update":
        return apply_updates(session, **payload)
    if kind == "changing":
        session.pending["changing"] = True
        return {"changing": True}, []
    if kind == "change":
        p = session.profile
        _clear_for_change(session)
        if payload == "roof":
            p.roof, p.roof_method = None, None
            session.pending.pop("candidates", None)
            session.pending.pop("candidate_texts", None)
        elif payload == "load":
            p.load_confirmed = False
        elif payload == "budget":
            p.budget_min_php = p.budget_max_php = None
        elif payload == "goal":
            p.goal = p.goal_target_pct = p.backup_hours = None
        return {"changed": payload}, []
    return {}, []


# ---- questions (templates; also the 'ask' hint given to the LLM) -----------------------------
def goal_label(p) -> str:
    if p.goal == "cut_bill":
        return f"cut your bill by {p.goal_target_pct:g}%" if p.goal_target_pct else "cut your bill"
    if p.goal == "backup":
        return f"blackout backup for {p.backup_hours:g} hours" if p.backup_hours else "blackout backup"
    return {"max_savings_10y": "the biggest 10-year savings", "fastest_payback": "the fastest payback"}.get(p.goal or "", "")


def roof_label(roof: dict | None) -> str:
    if not roof:
        return "no roof yet"
    src = {"osm": "from OpenStreetMap", "drawn": "drawn on the map", "sketch": "from your sketch"}.get(roof.get("source", ""), "")
    return f"about {roof.get('area_m2', 0):.0f} m² {src}".strip()


def summary_line(session: Session) -> str:
    p = session.profile
    load = f"about {p.monthly_kwh:g} kWh a month" if p.monthly_kwh else (f"a {php(p.monthly_bill_php)} monthly bill" if p.monthly_bill_php else "no usage yet")
    parts = [f"Roof: {roof_label(p.roof)}.", f"Usage: {load}."]
    if p.budget_max_php is not None:
        parts.append(f"Budget: up to {php(p.budget_max_php)}." if not p.budget_min_php
                     else f"Budget: {php(p.budget_min_php)} to {php(p.budget_max_php)}.")
    if p.goal:
        parts.append(f"Goal: {goal_label(p)}.")
    return " ".join(parts)


def question_for(slot: str, session: Session, lang: str = "english") -> str:
    p = session.profile
    persona = session.persona
    tag = lang == "taglish"
    if slot == "roof_method":
        return ("Paano mo gustong ipakita ang bubong mo? Puwede mong i-type ang address, i-drawing sa satellite map, o mag-sketch sa blank canvas."
                if tag else
                "How would you like to show me your roof? You can type your address and I'll look up the outline, draw it on the satellite map, or sketch it on a blank canvas.")
    if slot == "roof_address":
        return ("Ano ang address ng bahay? Mas maganda kung may kalye, barangay at lungsod."
                if tag else "What's the address of the house? A street, barangay and city works best.")
    if slot == "roof_pick":
        return "Alin dito ang bahay mo?" if tag else "I found a few matches. Which one is your home?"
    if slot == "roof_draw":
        if p.roof_method == "sketch":
            return ("Mag-sketch sa canvas sa kanan at maglagay ng isang totoong sukat para sa scale. Sabihin mo sa akin kapag tapos na."
                    if tag else "Sketch your roof on the canvas panel on the right and enter one real measurement for the scale. Tell me when you're done.")
        return ("I-drawing ang bubong sa mapa sa kanan. Sabihin mo sa akin kapag tapos na."
                if tag else "Draw your roof outline on the map panel on the right. Tell me when you're done.")
    if slot == "load":
        if p.monthly_kwh:
            est = p.monthly_kwh * A("tariff_php_per_kwh")
            return (f"Nakalagay sa profile ng {persona.name} ang mga {p.monthly_kwh:g} kWh kada buwan (mga {php(est)} sa kasalukuyang rate). Gamitin ko ba ito, o ibibigay mo ang totoong bill?"
                    if tag else
                    f"I have {persona.name} at about {p.monthly_kwh:g} kWh a month (roughly {php(est)} at today's rate). Should I use that, or do you want to give me your actual bill?")
        if p.monthly_bill_php:
            return f"Gagamitin ko ang {php(p.monthly_bill_php)} na buwanang bill. Okay ba?" if tag else f"I'll work from your {php(p.monthly_bill_php)} monthly bill. Is that right?"
        return ("Magkano ang buwanang bill mo sa kuryente, o ilang kWh ang konsumo mo?"
                if tag else "What's your monthly electricity bill in pesos, or your usage in kWh?")
    if slot == "budget":
        return ("Magkano ang budget mo para sa buong sistema, kasama ang pagkakabit?"
                if tag else "What budget range do you have in mind for the whole system, installed?")
    if slot == "goal":
        return "Ano ang pinakamahalaga sa iyo?" if tag else "What matters most to you?"
    if slot == "goal_param":
        if p.goal == "cut_bill":
            return "Gaano kalaki ang gusto mong ibawas sa bill?" if tag else "By how much do you want to cut your bill?"
        return "Ilang oras na backup ang kailangan mo kapag brownout?" if tag else "How many hours of backup do you want during a blackout?"
    if slot == "confirm":
        return (summary_line(session) + (" Tama ba ito? Patakbuhin ko na ba ang mga numero?" if tag else " Shall I run the numbers?"))
    if slot == "change":
        return "Ano ang gusto mong baguhin?" if tag else "What would you like to change?"
    if slot == "run":
        return "Pinapatakbo ko na ang mga numero." if tag else "Running the numbers now."
    if slot == "done":
        return "May iba ka pa bang gustong tingnan?" if tag else "Anything else you'd like to check?"
    return ""


INTRO = {
    "english": ("Hi {first}! I'm Sol. I'll help you compare solar options for your home: I'll look at your roof, your bill and your goal, "
                "then show sized options with a 25-year payback range. Every result is an estimate for a licensed installer to confirm."),
    "taglish": ("Hi {first}! Ako si Sol. Tutulungan kitang ihambing ang mga solar option para sa bahay mo: titingnan ko ang bubong, ang bill at ang goal mo, "
                "tapos magpapakita ako ng mga option na may 25-year payback range. Tantiya lang ang lahat ng resulta, kaya kailangan pa ring i-confirm ng licensed installer."),
}

_TAGLISH_HINTS = re.compile(
    r"\b(gusto|ko|ako|po|magkano|paano|bubong|kuryente|brownout|bahay|namin|natin|mo|ba|ang|sa|na|kasi|pwede|puwede|oo|hindi|sige|tama|salamat)\b", re.I)


def pick_language(session: Session, user_text: str) -> str:
    if session.language in ("english", "taglish"):
        return session.language
    return "taglish" if len(_TAGLISH_HINTS.findall(user_text or "")) >= 2 else "english"
