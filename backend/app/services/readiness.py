"""Meralco's "four things to know before investing", checked for one suggested option.

status: "ok" = Sol checked it and found no concern, "watch" = Sol's own numbers show a concern,
"confirm" = Sol cannot check it, so the customer or installer must. Texts use only numbers from this
function's inputs and ASSUMPTIONS.yaml, so the number guard can trace them.
"""
from __future__ import annotations

from ..models import RoofModel
from .assumptions import A

_BASE = "https://www.meralco.com.ph/residential/energy-solutions/solar-and-renewables"
SRC_NM = f"{_BASE}/solar-net-metering"
SRC_APPLY = f"{_BASE}/re-net-metering-application"
SRC_DER = f"{_BASE}/distributed-energy-resources"


def _peso(x: float) -> str:
    return f"₱{x:,.0f}"


def _size(raw: dict, sc: dict, net_metering: bool) -> dict:
    ac, used = raw["ac_kw"], sc["year1_self_consumption_pct"]
    watch, host = A("self_consumption_watch_pct"), A("hosting_capacity_smallest_kw")
    parts = [f"About {used:g}% of the solar power is used at home. The rest is exported " + ("at a lower credit than the retail rate." if net_metering else "with no credit, since net metering is off.")]
    bad = used < watch
    if bad:
        parts.append("A smaller system or a battery may suit your daytime use better.")
    if ac > host:
        bad = True
        parts.append(f"The {ac:g} kW inverter is above the {host:g} kW indicative limit for the smallest shared transformers, so Meralco's study may approve less.")
    return {"id": "size", "title": "Right size", "status": "watch" if bad else "ok", "text": " ".join(parts), "source": SRC_APPLY}


def _location(roof: RoofModel) -> dict:
    issues = []
    off = abs((roof.azimuth_deg - 180 + 180) % 360 - 180)
    if off > A("azimuth_watch_deg"):
        issues.append(f"The roof faces {roof.azimuth_deg:g}° (180° is south), {off:g}° off south, which cuts output.")
    if roof.confidence == "low":
        issues.append("The roof outline is low confidence.")
    if roof.scale_source == "default_grid":
        issues.append("The sketch scale was not measured, so the roof size is a guess.")
    checked = f"Sol checked the outline ({roof.usable_area_m2:g} m² usable), direction and tilt."
    tail = "It cannot see structure, roof condition or shading from a map. Your installer must check those before install."
    return {"id": "location", "title": "Right location", "status": "watch" if issues else "confirm",
            "text": " ".join([*issues, checked, tail]), "source": SRC_NM}


def _provider(pkg: dict) -> dict:
    parts = [f"{pkg['panel']}, {pkg['inverter']}"] + ([pkg["battery"]] if pkg.get("battery") else [])
    text = ("Ask each installer to quote these exact parts: " + "; ".join(parts) + ". "
            "Check that they follow technical standards, document the equipment, handle permits, and give written warranty and after-sales terms.")
    return {"id": "provider", "title": "Right provider", "status": "confirm", "text": text, "source": SRC_NM}


def _requirements(pkg: dict, net_metering: bool) -> dict:
    if net_metering:
        text = ("To export and earn credits you apply for Net Metering: Meralco's study, inspection, your city's electrical permit and "
                f"Certificate of Final Electrical Inspection, then the agreement and commissioning. Expect an ERC fee of {_peso(A('erc_coc_fee_php'))} "
                f"and a meter cost difference of up to {_peso(A('meter_cost_diff_cap_php'))}.")
        src = SRC_APPLY
    elif pkg["kwp"] <= A("micro_solar_max_kwp"):
        text = ("Without net metering, a Micro Solar System fits at this size: you notify Meralco after installing, and no building permit "
                "or ERC Certificate of Compliance is needed. Credits for exports need a separate Net Metering application.")
        src = SRC_DER
    else:
        text = ("Without net metering, this is a Zero-Export system: you notify Meralco after installing, need a building permit, "
                "and must fit an export limiter such as reverse power protection.")
        src = SRC_DER
    return {"id": "requirements", "title": "Know the requirements", "status": "confirm", "text": text, "source": src}


def readiness(roof: RoofModel, raw: dict, pkg: dict, expected: dict, net_metering: bool) -> list[dict]:
    """raw = optimizer package, pkg = its summary entry (display strings), expected = expected-scenario result."""
    return [_size(raw, expected, net_metering), _location(roof), _provider(pkg), _requirements(pkg, net_metering)]
