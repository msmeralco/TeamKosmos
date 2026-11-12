"""One place for the household-size limits, so the chat, the load model and signup all agree.

Sol sizes a system for a single home. A monthly bill is converted to kWh with the tariff, so the bill range follows
from the kWh range instead of being a second, unrelated number.
"""
from __future__ import annotations

from .assumptions import A

KWH_MIN = 30.0
KWH_MAX = 5000.0


def bill_limits_php() -> tuple[float, float]:
    """The monthly bills (pesos) that convert to a supported kWh figure."""
    tariff, fixed = A("tariff_php_per_kwh"), A("tariff_fixed_php_month")
    return KWH_MIN * tariff + fixed, KWH_MAX * tariff + fixed


def usage_hint() -> str:
    lo, hi = bill_limits_php()
    return (f"Sol sizes one home at {KWH_MIN:,.0f} to {KWH_MAX:,.0f} kWh a month (a bill of about ₱{lo:,.0f} to ₱{hi:,.0f}). "
            "Give a figure inside that range.")
