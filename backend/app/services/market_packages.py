"""Ready-made home solar packages that installers publish on their own websites (data/solar_packages.json).

Built by scripts/build_packages.py, which checks every price against the live page. These are published prices, not
quotes, and Sol has not vetted the installers. The table is built here from the data file, never written by the model.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from ..config import BACKEND_DIR

DATA = Path(BACKEND_DIR) / "data" / "solar_packages.json"
MAX_ROWS = 4


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


def _php(n: float) -> str:
    return f"₱{n:,.0f}"


GAP = 0.25  # a real package further than this share off the wanted size is not a good match, so made-up samples may fill in


def match(kwp: float | None = None, kind: str | None = None, region: str | None = None, limit: int = MAX_ROWS) -> dict:
    """Packages nearest the wanted size. kind: 'hybrid' (battery plus grid), 'grid-tied' or 'off-grid'.

    Real packages always rank first. Made-up samples are added only where real ones do not cover the request
    (no real package of that type, or none within 25% of the wanted size), and they are flagged synthetic.
    """
    d = _data()
    pk = d["packages"]
    if kwp:
        order = lambda p: (abs(p["kwp"] - kwp) / kwp, p["price_php"])  # noqa: E731
    else:  # no size yet: spread across the range, so the cheapest of each size band shows first
        order = lambda p: (round(p["kwp"] / 4), p["price_php"])  # noqa: E731
    in_area = [p for p in pk if region and region in p["regions"]]
    pool = in_area or pk
    typed = [p for p in pool if kind and p["type"] == kind]
    pool = typed or pool

    def pick(items: list[dict], room: int) -> list[dict]:
        out, seen = [], {}
        for p in sorted(items, key=order):  # at most two per installer, so one site does not fill the table
            if seen.get(p["installer"], 0) < 2:
                out.append(p)
                seen[p["installer"]] = seen.get(p["installer"], 0) + 1
            if len(out) == room:
                break
        return out

    rows = pick([p for p in pool if not p.get("synthetic")], limit)
    close = bool(rows) and (not kwp or abs(rows[0]["kwp"] - kwp) / kwp <= GAP)
    if not close or len(rows) < 3:
        extra = pick([p for p in pool if p.get("synthetic")], 2 if close else limit - len(rows))
        rows = sorted([*rows, *extra], key=order)[:limit]
    return {"found": bool(rows), "wanted_kwp": kwp, "kind": kind, "region": region, "in_your_area": bool(in_area), "type_matched": bool(typed),
            "has_sample": any(p.get("synthetic") for p in rows), "all_sample": bool(rows) and all(p.get("synthetic") for p in rows),
            "checked_on": d["checked_on"], "note": d["note"], "rows": rows}


def panel(kwp: float | None = None, kind: str | None = None, region: str | None = None,
          budget_min: float | None = None, budget_max: float | None = None, basis: str = "design") -> dict:
    """Every package in the data file for the side panel.

    Order: packages within the budget first (the budget maximum is the hard limit), then real before made-up, then the wanted type,
    then nearest the wanted size. basis says where the size came from: "design" (the recommended system) or "usage" (a rough guess).
    """
    d = _data()
    pk = d["packages"]
    in_area = [p for p in pk if region and region in p["regions"]]
    pool = in_area or pk
    gap = (lambda p: abs(p["kwp"] - kwp) / kwp) if kwp else (lambda p: 0.0)
    within = lambda p: budget_max is None or p["price_php"] <= budget_max  # noqa: E731
    rows = sorted(({**p, "within_budget": within(p)} for p in pool),
                  key=lambda p: (not p["within_budget"], p["synthetic"], 0 if not kind or p["type"] == kind else 1, gap(p), p["price_php"]))
    return {"wanted_kwp": kwp, "wanted_kind": kind, "basis": basis, "region": region, "in_your_area": bool(in_area), "budget_min": budget_min,
            "budget_max": budget_max, "checked_on": d["checked_on"], "note": d["note"], "rows": rows}


def _norm(s: str) -> str:
    return "".join(c for c in s.lower() if c.isalnum())


def find(text: str) -> dict | None:
    """The package a message is about, matched by its name (and installer when it is named). Longest name wins."""
    t = _norm(text)
    hits = [p for p in _data()["packages"] if _norm(p["name"]) in t]
    if not hits:
        return None
    named = [p for p in hits if _norm(p["installer"]) in t]
    return max(named or hits, key=lambda p: len(p["name"]))


def _fit(p: dict, budget_max: float | None, wanted_kwp: float | None, basis: str, system_kind: str | None) -> list[tuple[str, str]]:
    rows = []
    if budget_max is not None:
        gap = p["price_php"] - budget_max
        rows.append(("Your budget", f"Within your budget of up to {_php(budget_max)}" if gap <= 0 else f"{_php(gap)} over your budget of up to {_php(budget_max)}"))
    if wanted_kwp:
        r = p["kwp"] / wanted_kwp
        what = "your recommended system" if basis == "design" else "the rough size for your usage"
        rel = "Close to" if 0.7 <= r <= 1.3 else "Bigger than" if r > 1.3 else "Smaller than"
        rows.append(("Your size", f"{rel} {what} (about {wanted_kwp:g} kWp)"))
    if system_kind:
        rows.append(("Your system type", f"Matches your {system_kind} choice" if p["type"] == system_kind else f"Different from your {system_kind} choice: this one is {p['type']}"))
    return rows


def details_markdown(p: dict, *, budget_max: float | None = None, wanted_kwp: float | None = None, basis: str = "design",
                     system_kind: str | None = None, registry: str | None = None) -> str:
    """One package in full: price, parts, how it fits the user, the installer's published contacts, and what to ask. Built only from the data file."""
    bat = f"{p['battery_kwh']:g} kWh battery" if p.get("battery_kwh") else "no battery"
    kind = {"hybrid": "Hybrid: grid-connected with a battery", "grid-tied": "Grid-tied: no battery", "off-grid": "Off-grid: no utility connection"}[p["type"]]
    rows = [("Price", f"**{_php(p['price_php'])}** ({p['price_note']})"), ("Size", f"{p['kwp']:g} kWp"), ("Type", kind),
            ("Includes", f"{p['panels']}; {p['inverter']}; {bat}"), ("Serves", p["area"])]
    rows += _fit(p, budget_max, wanted_kwp, basis, system_kind)
    out = [f"### {p['name']}" + ("" if p.get("synthetic") else f" · {p['installer']}"), "", "| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in rows]
    if p.get("synthetic"):
        out += ["", "> This is a **made-up sample** with no installer behind it, so there is nobody to contact. Pick a package marked with an installer's name to get its contact details."]
        return "\n".join(out)
    c = p.get("contact") or {}
    contact = []
    if c.get("phones"):
        contact.append(("Phone", " · ".join(c["phones"])))
    if c.get("emails"):
        contact.append(("Email", " · ".join(c["emails"])))
    if c.get("viber"):
        contact.append(("Viber", c["viber"]))
    if p.get("link"):
        contact.append(("Website", f"[{p['link'].replace('https://', '').rstrip('/')}]({p['link']})"))
    social = [f"[{n}]({c[k]})" for k, n in (("facebook", "Facebook"), ("messenger", "Messenger"), ("whatsapp", "WhatsApp")) if c.get(k)]
    if social:
        contact.append(("Social", " · ".join(social)))
    if c.get("office"):
        contact.append(("Office", c["office"]))
    out += ["", f"**Contact {p['installer']}**", "", "| | |", "|---|---|"] + [f"| {k} | {v} |" for k, v in contact]
    ask = ["Is this price for exactly these parts, and what could change it after a site visit?",
           "Who files the Meralco application and the permits, and is that in the price?" if p["type"] != "off-grid" else "What permits does this need, and who handles them?",
           "What are the warranties on the panels, the inverter and the battery, and who answers a service call?",
           "Is mounting, wiring and installation included, and are there extra fees such as mobilization?"]
    out += ["", "**Before you call, ask:**", ""] + [f"- {q}" for q in ask]
    note = (f"The price is what {p['installer']} published, not a quote. Sol has not vetted this installer. "
            + (f"DOE registry: {registry}. " if registry else "") + "Get a written quote based on your own installation site and bill, and compare at least two.")
    out += ["", f"> {note}"]
    return "\n".join(out)


def table_markdown(r: dict) -> str:
    """Customer-facing table with photos, specs, published prices and links, built only from the data file."""
    if not r["rows"]:
        return "### Ready-made packages\n\nI don't have a published package near that size."
    want = f" near {r['wanted_kwp']:g} kWp" if r.get("wanted_kwp") else ""
    kind = {"hybrid": "with a battery", "grid-tied": "without a battery", "off-grid": "for an off-grid home"}.get(r.get("kind") or "", "")
    head = f"### Ready-made packages{want} {kind}".rstrip()
    where = "installers that serve your area" if r["in_your_area"] else "installers in other areas (none I have serve yours yet)"
    if r.get("all_sample"):
        intro = "I don't have a real published package for this, so these are **made-up samples** that show what to expect."
    elif r.get("has_sample"):
        intro = f"Real packages from {where}, as the installers publish them, plus **made-up samples** (marked *Sample*) for sizes I have no real package for."
    else:
        intro = f"Real packages from {where}, as the installers publish them."
    out = [head, "", intro, "",
           "| Photo | Package | Size | Includes | Price | Installer |", "|---|---|---|---|---|---|"]
    for p in r["rows"]:
        photo = f"![{p['installer']}]({p['photo']})" if p.get("photo") else "–"
        bat = f"{p['battery_kwh']:g} kWh battery" if p.get("battery_kwh") else "no battery"
        inc = f"{p['panels']}; {p['inverter']}; {bat}"
        who = f"*Sample* (made-up)" if p.get("synthetic") else f"[{p['installer']}]({p['link']})"
        out.append(f"| {photo} | **{p['name']}** | {p['kwp']:g} kWp | {inc} | **{_php(p['price_php'])}** ({p['price_note']}) | {who} |")
    notes = [f"Prices are what each installer published on its own website on {r['checked_on']}, not quotes. Sol has not vetted these installers. "
             "Ask for a written quote based on your own installation site and bill."]
    if r.get("has_sample"):
        notes.append("Rows marked Sample are invented to fill gaps. They are not offers from anyone, and their prices only follow the range of the real ones.")
    notes.append("A real photo shows the installer's work and a drawing is only an illustration, so neither is this exact package. "
                 "Where a size is calculated from panels × watts, it may differ slightly from the installer's own rounding.")
    out += ["", "> " + " ".join(notes)]
    return "\n".join(out)
