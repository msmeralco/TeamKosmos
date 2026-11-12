"""The deterministic brain of the conversation.

Code (not the LLM) decides which question comes next, validates every value, and builds the
clickable choices. The LLM only phrases things and extracts values through tool calls.
"""
from __future__ import annotations

import re
from typing import Any

from .. import limits
from ..assumptions import A
from ..load import bill_to_kwh
from .session import GOALS, SYSTEM_TYPES, TEMPLATES, Session

Suggestion = dict  # {"id", "label", "hint"?, "text"}

# ---- limits (validation) -------------------------------------------------------------
KWH_RANGE = (limits.KWH_MIN, limits.KWH_MAX)
BILL_RANGE = (300.0, 200_000.0)  # sanity bound for typos; the real bill limit follows from KWH_RANGE (see _bill_in_range)
BUDGET_RANGE = (0.0, 10_000_000.0)
TARGET_RANGE = (5.0, 100.0)
BACKUP_RANGE = (1.0, 48.0)


def php(n: float) -> str:
    return f"₱{n:,.0f}"


def norm(text: str) -> str:
    return re.sub(r"[^\w₱%.]+", " ", (text or "").lower()).strip()


# ---- static choice texts ---------------------------------------------------------------
ROOF_CHOICES = {
    "draw": ("Draw on the map", "Trace your installation site on the satellite map", "I'll draw my installation site on the map"),
    "sketch": ("Sketch on a canvas", "Draw with a metre scale on a blank canvas", "I'll sketch my installation site on a blank canvas"),
}
SYSTEM_CHOICES = {
    "on_grid": ("Grid-tied (on-grid)", "Panels plus the grid, no battery. Lowest cost", "I want a grid-tied (on-grid) system"),
    "off_grid": ("Off-grid", "Panels plus batteries, no utility connection", "I want an off-grid system"),
    "hybrid": ("Hybrid (solar + storage)", "Grid-connected with a battery for outages", "I want a hybrid system with a battery"),
}
SYSTEM_LABELS = {"on_grid": "Grid-tied (on-grid)", "off_grid": "Off-grid", "hybrid": "Hybrid (solar + storage)"}
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
    "roof": ("Change my installation site", "Redraw or sketch it again", "Change my installation site"),
    "load": ("Change my bill", "Use a different usage or bill", "Change my bill"),
    "system": ("Change system type", "Grid-tied, off-grid or hybrid", "Change my system type"),
    "budget": ("Change my budget", "Pick another budget range", "Change my budget"),
    "goal": ("Change my goal", "Pick another goal", "Change my goal"),
}
FOLLOW_UPS = {
    "net_metering_off": ("net metering off", "See results without net metering", "What if net metering is off?", "compare_net_metering"),
    "assumptions": ("Show the assumptions", "Every number with its source", "Show me the assumptions", "explain_assumptions"),
    "passport": ("Create my Solar Passport", "A signed record anyone can verify", "Create my Solar Passport", "issue_passport"),
    "fill_roof": ("Fill my whole site", "Preview panels on the entire installation site", "Show panels on my whole installation site", "toggle_roof_fill"),
    "my_design": ("Back to my design", "Show only the panels in my design", "Show my design again", "toggle_roof_fill"),
}
DEFAULT_GOAL = "max_savings_10y"
RUN_TEXT = "Yes, run the numbers"
CHANGE_TEXT = "I want to change something"
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
        return "roof_draw"
    if not p.load_confirmed or (p.monthly_kwh is None and p.monthly_bill_php is None):
        return "load"
    if p.system_type is None:
        return "system_type"
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


def _bill_problem(bill: float) -> str | None:
    """Why a bill cannot be sized, or None. The bill is converted to kWh exactly like the load model does."""
    kwh = bill_to_kwh(bill)
    if limits.KWH_MIN <= kwh <= limits.KWH_MAX:
        return None
    lo, hi = limits.bill_limits_php()
    side = "above" if kwh > limits.KWH_MAX else "below"
    return (f"A {php(bill)} monthly bill is about {kwh:,.0f} kWh, {side} what Sol can size for one home "
            f"({limits.KWH_MIN:,.0f} to {limits.KWH_MAX:,.0f} kWh, or a bill of about {php(lo)} to {php(hi)}). "
            "Please give a bill or usage inside that range")


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
        problem = _bill_problem(bill)
        if problem:  # a bill that would later fail the load model is refused now, with the real limits
            errors.append(problem)
            bill = None
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

    system = fields.get("system_type")
    if system is not None:
        if system not in SYSTEM_TYPES:
            errors.append(f"system_type must be one of {', '.join(SYSTEM_TYPES)}")
        elif system == "on_grid" and (p.goal == "backup" or fields.get("goal") == "backup"):
            errors.append("Blackout backup needs a battery, so it can't be a grid-tied system without storage. Pick hybrid or off-grid, or change the goal")
        else:
            p.system_type = system
            applied["system_type"] = system

    goal = fields.get("goal")
    if goal is not None:
        if goal == "backup" and p.system_type == "on_grid":
            errors.append("Blackout backup needs a battery, so it doesn't fit a grid-tied system. Change the system type to hybrid or off-grid first")
        elif goal in GOALS:
            if p.goal is not None and goal != p.goal:
                p.goal_target_pct = None
                p.backup_hours = None
            p.goal = goal
            applied["goal"] = goal
            session.pending.pop("goal_default", None)  # the user chose, so it is no longer a default
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
        if method in ("draw", "sketch"):
            if method != p.roof_method or p.roof is not None:
                p.roof = None
                session.pending.pop("candidates", None)
                session.pending.pop("candidate_texts", None)
            p.roof_method = method
            applied["roof_method"] = method
        else:
            errors.append("roof_method must be draw or sketch")

    if p.budget_max_php is not None and p.goal is None:
        # No goal question: aim for the biggest 10-year savings unless the user picks another one (Change something > goal).
        p.goal = DEFAULT_GOAL
        session.pending["goal_default"] = True

    changed = p.model_dump() != before
    if changed:
        # Inputs changed: any earlier analysis is stale and the summary must be re-confirmed.
        session.invalidate_results()
        # The user has made their change, so leave the "what would you like to change?" menu.
        session.pending.pop("changing", None)

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
    if slot == "roof_draw":
        if p.roof_method == "sketch":
            return [_s("roof_draw", "Draw on the map", "Trace on the satellite map", DRAW_INSTEAD_TEXT)]
        return [_s("roof_sketch", "Sketch on a canvas", "Use a metre scale instead", SKETCH_INSTEAD_TEXT)]
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
    if slot == "system_type":
        return [_s(f"sys_{k}", *v) for k, v in SYSTEM_CHOICES.items()]
    if slot == "budget":
        return [_s(bid, label, "Whole system, installed", f"My budget is {label[0].lower() + label[1:] if label.startswith('Under') else label}")
                for bid, _lo, _hi, label in BUDGETS]
    if slot == "goal":
        # Blackout backup needs a battery, so it is not offered for a grid-tied system.
        return [_s(f"goal_{k}", *v) for k, v in GOAL_CHOICES.items() if not (k == "backup" and p.system_type == "on_grid")]
    if slot == "goal_param":
        if p.goal == "cut_bill":
            return [_s(f"cut_{t}", f"Cut by {t}%", "Target bill reduction", f"Cut my bill by {t}%") for t in CUT_TARGETS]
        return [_s(f"backup_{h}", f"{h} hours", "Essential loads only", f"I need {h} hours of backup") for h in BACKUP_OPTIONS]
    if slot == "confirm":
        return [_s("run", "Run the numbers", "Simulate and compare options", RUN_TEXT),
                _s("change", "Change something", "Installation site, bill, budget or goal", CHANGE_TEXT)]
    if slot == "change":
        return [_s(f"chg_{k}", *v) for k, v in CHANGE_CHOICES.items()]
    if slot == "run":
        return [_s("run", "Run the numbers", "Simulate and compare options", RUN_TEXT)]
    if slot == "done":
        out = []
        for k, (label, hint, text, _tool) in FOLLOW_UPS.items():
            if k == "passport" and "passport" in session.results:
                continue
            filled = bool(session.pending.get("full_roof"))
            if (k == "fill_roof" and filled) or (k == "my_design" and not filled):
                continue
            out.append(_s(f"fu_{k}", label.capitalize() if k == "net_metering_off" else label, hint, text))
        out.append(_s("change", "Change something", "Installation site, bill, budget or goal", CHANGE_TEXT))
        return out
    return []


# ---- exact-match choice handling -----------------------------------------------------------
def _static_table() -> dict[str, tuple]:
    t: dict[str, tuple] = {}
    for k, v in ROOF_CHOICES.items():
        t[norm(v[2])] = ("update", {"roof_method": k})
    for k, v in SYSTEM_CHOICES.items():
        t[norm(v[2])] = ("update", {"system_type": k})
    t[norm(SKETCH_INSTEAD_TEXT)] = ("update", {"roof_method": "sketch"})
    t[norm(DRAW_INSTEAD_TEXT)] = ("update", {"roof_method": "draw"})
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
        elif payload == "system":
            p.system_type = None
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
        return "no installation site yet"
    src = {"osm": "from OpenStreetMap", "drawn": "drawn on the map", "sketch": "from your sketch"}.get(roof.get("source", ""), "")
    return f"about {roof.get('area_m2', 0):.0f} m² {src}".strip()


def summary_line(session: Session) -> str:
    p = session.profile
    load = f"about {p.monthly_kwh:g} kWh a month" if p.monthly_kwh else (f"a {php(p.monthly_bill_php)} monthly bill" if p.monthly_bill_php else "no usage yet")
    parts = [f"Installation site: {roof_label(p.roof)}.", f"Usage: {load}."]
    if p.system_type:
        parts.append(f"System: {SYSTEM_LABELS[p.system_type]}.")
    if p.budget_max_php is not None:
        parts.append(f"Budget: up to {php(p.budget_max_php)}." if not p.budget_min_php
                     else f"Budget: {php(p.budget_min_php)} to {php(p.budget_max_php)}.")
    if p.goal and not session.pending.get("goal_default"):
        parts.append(f"Goal: {goal_label(p)}.")
    return " ".join(parts)


def question_for(slot: str, session: Session, lang: str = "english") -> str:
    p = session.profile
    persona = session.persona
    tag = lang == "taglish"
    if slot == "roof_method":
        return ("Paano mo gustong ipakita ang installation site mo? Puwede mong i-drawing sa satellite map (may search box doon para hanapin ang lugar mo), o mag-sketch sa blank canvas."
                if tag else
                "How would you like to show me your installation site? You can draw it on the satellite map (use its search box to jump to your street), or sketch it on a blank canvas.")
    if slot == "roof_draw":
        if p.roof_method == "sketch":
            return ("Mag-sketch sa canvas sa kanan at maglagay ng isang totoong sukat para sa scale. Sabihin mo sa akin kapag tapos na."
                    if tag else "Sketch your installation site on the canvas panel on the right and enter one real measurement for the scale. Tell me when you're done.")
        return ("I-drawing ang installation site sa mapa sa kanan. Sabihin mo sa akin kapag tapos na."
                if tag else "Draw your installation site outline on the map panel on the right. Tell me when you're done.")
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
    if slot == "system_type":
        return (
            "Anong uri ng solar system ang gusto mo?\n\n"
            "- **Grid-tied (on-grid):** may koneksyon sa Meralco, walang battery. Pinakamura, pero namamatay kapag brownout.\n"
            "- **Off-grid:** solar at battery lang, walang koneksyon sa utility.\n"
            "- **Hybrid (solar + storage):** may koneksyon sa grid at may battery para may kuryente kapag brownout."
            if tag else
            "Which type of solar system do you want?\n\n"
            "- **Grid-tied (on-grid):** connected to the utility with no battery. Lowest cost, but it shuts off during a blackout.\n"
            "- **Off-grid:** solar and batteries only, with no utility connection.\n"
            "- **Hybrid (solar + storage):** connected to the grid, with a battery that keeps essentials on during blackouts."
        )
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
        # A summary, not a question: the buttons below carry the next step.
        goal_en = "I'll aim for the biggest 10-year savings unless you pick another goal. " if session.pending.get("goal_default") else ""
        goal_tl = "Ang target ko ay ang pinakamalaking matitipid sa 10 taon maliban kung pumili ka ng ibang goal. " if session.pending.get("goal_default") else ""
        return (summary_line(session) + (f" {goal_tl}Pindutin ang Run the numbers kapag handa ka na, o ang Change something para baguhin ang anuman sa itaas."
                                         if tag else f" {goal_en}Tap Run the numbers when you're ready, or Change something to edit anything above."))
    if slot == "change":
        return "Ano ang gusto mong baguhin?" if tag else "What would you like to change?"
    if slot == "run":
        return "Pinapatakbo ko na ang mga numero." if tag else "Running the numbers now."
    if slot == "done":
        return "May iba ka pa bang gustong tingnan?" if tag else "Anything else you'd like to check?"
    return ""


INTRO = {
    "english": ("Hi {first}! I'm Sol. I'll help you compare solar options for your home: I'll look at your installation site, your bill and your goal, "
                "then show sized options with a 10-year payback range. Every result is an estimate for a licensed installer to confirm."),
    "taglish": ("Hi {first}! Ako si Sol. Tutulungan kitang ihambing ang mga solar option para sa bahay mo: titingnan ko ang installation site, ang bill at ang goal mo, "
                "tapos magpapakita ako ng mga option na may 10-year payback range. Tantiya lang ang lahat ng resulta, kaya kailangan pa ring i-confirm ng licensed installer."),
}

# Tagalog function and question words. Words that are also common English words (at, may, man, no, to) are left out.
_TAGALOG_WORDS = frozenset("""
ano anong ang ng mga sa na ay ako ko mo ka ikaw siya kami tayo natin namin nila ninyo niyo kayo ito iyan iyon yan yun yung ayan ayun
dito diyan doon dun saan sino bakit kailan paano gaano ilan magkano alin nasaan
gusto ayaw kailangan pwede puwede dapat gagawin gumagana tulong sabihin paki pakisabi
hindi di wala meron mayroon oo opo po sige tama mali salamat
para kung kapag pag habang dahil kasi kaya pero tapos saka lang lamang naman din rin pa pala nga daw raw sana muna talaga siguro
ba bang
bahay bubong kuryente bayad buwan taon araw oras presyo mura mahal tipid matitipid ibawas
""".split())
_WORD = re.compile(r"[a-zñ']+", re.I)


def detect_style(user_text: str) -> str:
    """'english' or 'tagalog', judged from one message. A mixed message goes to whichever language has more words."""
    words = _WORD.findall((user_text or "").lower())
    if not words:
        return "english"
    tl = sum(1 for w in words if w in _TAGALOG_WORDS)
    return "tagalog" if tl and tl / len(words) >= 0.4 else "english"


def pick_language(session: Session, user_text: str) -> str:
    """Template language: 'english' or 'taglish' (the Tagalog templates, which keep the usual English solar terms)."""
    if session.language in ("english", "taglish"):
        return session.language
    return "english" if detect_style(user_text) == "english" else "taglish"
