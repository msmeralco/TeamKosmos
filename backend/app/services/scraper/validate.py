"""Reject implausible scraped products and normalise them to the Product contract."""
from __future__ import annotations

import hashlib
from datetime import datetime, timezone

from .extract import estimate_panel_dims

# Sanity windows in PHP. Anything outside is rejected (likely a parsing or currency error).
PANEL_PHP_PER_W = (8.0, 40.0)
INVERTER_PHP_PER_KW = (6_000.0, 60_000.0)
BATTERY_PHP_PER_KWH = (15_000.0, 90_000.0)


def normalise(raw: dict, *, source_name: str) -> tuple[dict | None, str]:
    """Return (product, '') or (None, reason)."""
    if raw.get("currency", "PHP") != "PHP":
        return None, f"unsupported currency {raw.get('currency')}"
    cat, price = raw["category"], float(raw["price"])
    p: dict = {
        "category": cat, "brand": raw["brand"], "model": raw["name"], "price_php": price,
        "source_url": raw["url"], "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "method": raw["method"], "confidence": raw["confidence"], "embodied_carbon_kg": None,
        "source_name": source_name,
    }
    if cat == "panel":
        watts = raw.get("watts")
        if not watts:
            return None, "panel without watts"
        lo, hi = PANEL_PHP_PER_W
        if not lo <= price / watts <= hi:
            return None, f"panel price per watt {price / watts:.1f} outside {lo}-{hi}"
        p.update(watts=watts, dims_m=estimate_panel_dims(watts), dims_estimated=True,
                 efficiency_pct=None, degradation_pct_per_year=None, warranty_years=None)
    elif cat == "inverter":
        kw = raw.get("inverter_ac_kw")
        if not kw:
            return None, "inverter without kW"
        lo, hi = INVERTER_PHP_PER_KW
        if not lo <= price / kw <= hi:
            return None, f"inverter price per kW {price / kw:.0f} outside {lo:.0f}-{hi:.0f}"
        p.update(inverter_ac_kw=kw, max_dc_kw=round(kw * 1.4, 2), hybrid=bool(raw.get("hybrid")))
    elif cat == "battery":
        kwh = raw.get("battery_kwh")
        if not kwh:
            return None, "battery without kWh"
        lo, hi = BATTERY_PHP_PER_KWH
        if not lo <= price / kwh <= hi:
            return None, f"battery price per kWh {price / kwh:.0f} outside {lo:.0f}-{hi:.0f}"
        p.update(battery_kwh=kwh, battery_max_kw=round(kwh / 2, 2), chemistry=None, cycles=None)
    else:
        return None, f"unknown category {cat}"
    p["id"] = "live-" + hashlib.sha1(f"{cat}|{p['brand']}|{p['model']}".encode()).hexdigest()[:12]
    return p, ""
