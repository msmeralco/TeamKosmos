"""Small rule-based language understanding for the scripted (no-LLM) agent."""
from __future__ import annotations

import re

_MULT = {"k": 1_000.0, "thousand": 1_000.0, "m": 1_000_000.0, "mil": 1_000_000.0, "million": 1_000_000.0}
_UNITS = r"kwh|kw|kwp|%|percent|hours?|hrs?|hr|oras|years?|yrs?|months?|m2|sqm|panels?"
_NUM = re.compile(
    rf"(?P<cur>₱|php\s*|p(?=\d)|pesos?\s*)?(?P<num>\d[\d,]*(?:\.\d+)?)(?P<suf>(?:k|m)\b|\s*(?:thousand|million|mil)\b)?\s*(?P<unit>(?:{_UNITS})\b|%)?",
    re.I)
_KWH = re.compile(r"(\d[\d,]*(?:\.\d+)?)\s*kwh", re.I)
_PCT = re.compile(r"(\d{1,3}(?:\.\d+)?)\s*(?:%|percent)", re.I)
_HOURS = re.compile(r"(\d{1,2}(?:\.\d+)?)\s*(?:hours?|hrs?|hr|oras)\b", re.I)


def _f(s: str) -> float:
    return float(s.replace(",", ""))


def amounts(text: str) -> list[float]:
    """Money-like numbers: with a peso sign, a k/m suffix, or a value of at least 1000, and no kWh/%/hours unit."""
    out = []
    for m in _NUM.finditer(text):
        if m.group("unit"):
            continue
        val = _f(m.group("num")) * _MULT.get((m.group("suf") or "").strip().lower(), 1.0)
        if m.group("cur") or m.group("suf") or val >= 1000:
            out.append(val)
    return out


def kwh_value(text: str) -> float | None:
    m = _KWH.search(text)
    return _f(m.group(1)) if m else None


def percent(text: str) -> float | None:
    m = _PCT.search(text)
    return float(m.group(1)) if m else None


def hours(text: str) -> float | None:
    m = _HOURS.search(text)
    return float(m.group(1)) if m else None


def goal_from(text: str) -> str | None:
    t = text.lower()
    if re.search(r"payback|pay back|recover|return on|roi|balik", t):
        return "fastest_payback"
    if re.search(r"backup|back-up|blackout|brownout|outage|power cut|walang kuryente", t):
        return "backup"
    if re.search(r"10[- ]?year|ten[- ]year|most (?:money|savings)|biggest.*saving|max(?:imum|imize)?.*saving|long[- ]term saving", t):
        return "max_savings_10y"
    if re.search(r"(cut|reduce|lower|bawas|ibaba|slash).*(bill|kuryente|electric)|(bill|kuryente).*(cut|reduce|lower|bawas)", t):
        return "cut_bill"
    return None


def method_from(text: str) -> str | None:
    t = text.lower()
    if re.search(r"sketch|canvas|blank", t):
        return "sketch"
    if re.search(r"\bdraw|\btrace|\bmap\b|drawing|i-drawing|iguhit", t):
        return "draw"
    if re.search(r"address|type|search|look ?up|i-type", t):
        return "address"
    return None


def looks_like_address(text: str) -> bool:
    t = text.strip().lower()
    if len(t) < 8:
        return False
    return bool(re.search(r"\b(st|street|ave|avenue|rd|road|blvd|brgy|barangay|village|subdivision|city|quezon|pasig|makati|manila|taguig|mandaluyong|marikina)\b", t)) or ("," in t and re.search(r"\d", t) is not None)


AFFIRM = re.compile(r"^(?:yes|yeah|yep|yup|ok(?:ay)?|sure|go|go ahead|proceed|correct|right|that'?s right|oo|opo|sige|tama|ayos|run(?: it| the numbers)?)\b", re.I)
NEGATE = re.compile(r"^(?:no|nope|nah|not|hindi|wrong|mali|change)\b", re.I)


def is_affirm(text: str) -> bool:
    return bool(AFFIRM.match(text.strip()))


def is_negate(text: str) -> bool:
    return bool(NEGATE.match(text.strip()))


# Rules, fees, process and how-solar-works questions go to the document library.
_DOCS = re.compile(r"permit|\bfees?\b|zero[- ]?export|micro[- ]?solar|\bmss\b|sgf|inspect|cfei|apply|application|requirement|installer|provider|"
                   r"transformer|hosting|blackout|brownout|outage|warranty|degrad|net[- ]?metering|\bmeter\b|inverter|battery|batteries|"
                   r"\bdoe\b|\berc\b|pvgis|how long do", re.I)
_QUESTION = re.compile(r"\?|^\s*(?:what|how|why|when|who|where|do|does|can|could|is|are|will|should|paano|ano)\b", re.I)


def detect_intent(text: str) -> str | None:
    t = text.lower()
    if re.search(r"passport|verify|verification|sign(?:ed)? record", t):
        return "passport"
    if re.search(r"net[- ]?metering.*(off|without|disable|no\b)|without net[- ]?metering|what if.*net[- ]?metering|compare.*net[- ]?metering", t):
        return "nm_compare"
    if re.search(r"assumption|where do .* come from|\bsources?\b", t):
        return "explain"
    if re.search(r"\bprices?\b|how much (?:is|are|for|does|do) .*(?:panel|inverter|batter|brand)|panel brand|equipment|product", t):
        return "products"
    if _DOCS.search(t) and _QUESTION.search(t):
        return "docs"
    if re.search(r"explain|what is|what's|what are|how does|how do|paano|bakit|ano ang|ano po|\?$", t):
        return "ask"
    return None


# ---- several requests in one message ---------------------------------------------------------------------
# Actions the user can ask for besides giving details. They are always carried out in this order, because the later
# ones need the earlier ones: the numbers must be run before they can be compared, filled or turned into a passport.
ACTION_ORDER = ("run", "nm_compare", "fill_roof", "passport")
_ACTION_PATTERNS = {
    "run": re.compile(r"\brun (?:the |my )?(?:numbers?|analysis|simulation)\b|\brun (?:it|this)\b|\banaly[sz]e (?:it|this|my|the)\b|\bsimulate\b|"
                      r"\bcompare (?:the |my |all )?(?:packages?|options?)\b|\bshow (?:me )?(?:the |my )?(?:results?|options)\b|\bi-?run\b|\bpatakbuhin\b", re.I),
    "nm_compare": re.compile(r"net[- ]?metering.*(?:compare|off|without)|(?:compare|without|what if).*net[- ]?metering", re.I),
    "fill_roof": re.compile(r"\b(?:whole|entire|full) roof\b|\bfill (?:my |the )?roof\b", re.I),
    "passport": re.compile(r"passport", re.I),
}
_HOLD = re.compile(r"\b(?:don'?t|do not|not yet|wait|hold on|hold off|huwag|wag muna)\b", re.I)


def requested_actions(text: str) -> list[str]:
    """Actions asked for in one message, in the order they must be carried out. Empty if the user said to wait."""
    if _HOLD.search(text):
        return []
    return [a for a in ACTION_ORDER if _ACTION_PATTERNS[a].search(text)]


def has_run_command(text: str) -> bool:
    """True when the message itself tells Sol to run the numbers (so it counts as the user's go-ahead)."""
    return "run" in requested_actions(text)


_BUDGET_WORDS = re.compile(r"\b(budget|afford|spend|up to|at most|under|below|hanggang)\b", re.I)
_BILL_WORDS = re.compile(r"\b(bill|kuryente|electric(?:ity)?|meralco|monthly)\b", re.I)
_CLAUSES = re.compile(r"[;,]|\band\s+(?=(?:my|i|the)\b)", re.I)


def _money_fields(text: str, slot: str) -> dict:
    """Budget and bill amounts, decided clause by clause so 'my bill is 6k, budget 300k' works."""
    out: dict = {}
    for clause in _CLAUSES.split(text):
        amts = amounts(clause)
        if not amts:
            continue
        is_budget = bool(_BUDGET_WORDS.search(clause)) or (slot == "budget" and not _BILL_WORDS.search(clause))
        is_bill = bool(_BILL_WORDS.search(clause)) or slot == "load"
        if is_budget and "budget_max_php" not in out:
            lo, hi = 0.0, max(amts)
            if len(amts) >= 2:
                lo, hi = min(amts), max(amts)
            elif re.search(r"at least|more than|above|over|or more|minimum", clause, re.I):
                lo, hi = amts[0], amts[0] * 2
            out["budget_min_php"], out["budget_max_php"] = lo, hi
        elif is_bill and "monthly_bill_php" not in out:
            out["monthly_bill_php"] = amts[0]
    return out


def extract(text: str, slot: str, goal: str | None) -> dict:
    """Fields for update_profile from free text. `goal` is the goal already on the profile (if any)."""
    t = text.lower()
    out: dict = {}
    kwh = kwh_value(text)
    if kwh is not None:
        out["monthly_kwh"] = kwh
    out.update(_money_fields(text, slot))
    g = goal_from(text)
    if g:
        out["goal"] = g
    eff_goal = g or goal
    pct = percent(text)
    if pct is not None and eff_goal in (None, "cut_bill"):
        out["goal_target_pct"] = pct
        if slot in ("goal", "goal_param"):
            out.setdefault("goal", "cut_bill")
    hrs = hours(text)
    if hrs is not None and eff_goal in (None, "backup"):
        out["backup_hours"] = hrs
        if slot in ("goal", "goal_param"):
            out.setdefault("goal", "backup")
    if re.search(r"net[- ]?metering.*\b(off|disabled?)\b|without net[- ]?metering|no net[- ]?metering", t):
        out["net_metering"] = False
    elif re.search(r"net[- ]?metering.*\bon\b|with net[- ]?metering", t):
        out["net_metering"] = True
    if re.search(r"off[- ]?grid", t):
        out["system_type"] = "off_grid"
    elif re.search(r"hybrid|solar[- ]?plus[- ]?(?:storage|battery)|with (?:a )?batter", t):
        out["system_type"] = "hybrid"
    elif re.search(r"on[- ]?grid|grid[- ]?(?:tied|tie|connected)", t):
        out["system_type"] = "on_grid"
    if re.search(r"night|gabi", t) and "heavy" in t:
        out["household_template"] = "night_heavy"
    elif re.search(r"work(?:ing)? from home|wfh|day[- ]?heavy|home all day", t):
        out["household_template"] = "day_heavy"
    if slot == "load" and is_affirm(text) and not out:
        out["confirm_load"] = True
    if slot == "confirm" and is_affirm(text) and not out:
        out["confirm_summary"] = True
    return out
