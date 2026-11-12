"""Cash flow, payback, NPV, IRR and LCOE (the model runs longer than the 10 years shown to users)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.optimize import brentq


@dataclass
class CashFlow:
    capex: float
    net: np.ndarray  # (years,) net cash flow per year (savings - O&M - replacements)
    cumulative: np.ndarray  # (years + 1,) index 0 = -capex
    om: np.ndarray
    replacements: np.ndarray


def build_cashflow(savings: np.ndarray, capex: float, *, om_pct_of_capex: float, inverter_price: float,
                   inverter_life: int, inverter_replacement_pct: float, battery_price: float,
                   battery_life: int) -> CashFlow:
    years = len(savings)
    om = np.full(years, capex * om_pct_of_capex / 100.0)
    repl = np.zeros(years)
    if inverter_life > 0 and inverter_price > 0:
        for y in range(inverter_life, years + 1, inverter_life):  # end of year `inverter_life`
            if y <= years:
                repl[y - 1] += inverter_price * inverter_replacement_pct / 100.0
    if battery_life > 0 and battery_price > 0:
        for y in range(battery_life, years + 1, battery_life):
            repl[y - 1] += battery_price
    net = savings - om - repl
    cumulative = np.concatenate([[-capex], -capex + np.cumsum(net)])
    return CashFlow(capex=capex, net=net, cumulative=cumulative, om=om, replacements=repl)


def payback_years(cumulative: np.ndarray) -> float | None:
    """First time cumulative cash flow reaches zero, linearly interpolated inside the year. None if never."""
    if cumulative[0] >= 0:
        return 0.0
    for y in range(1, len(cumulative)):
        if cumulative[y] >= 0:
            step = cumulative[y] - cumulative[y - 1]
            return float((y - 1) + (-cumulative[y - 1] / step if step > 0 else 1.0))
    return None


def npv(net: np.ndarray, capex: float, rate_pct: float) -> float:
    r = rate_pct / 100.0
    t = np.arange(1, len(net) + 1)
    return float(np.sum(net / (1.0 + r) ** t) - capex)


def irr_pct(net: np.ndarray, capex: float) -> float | None:
    f = lambda r: npv(net, capex, r * 100.0)  # noqa: E731
    lo, hi = -0.9, 2.0
    try:
        if f(lo) * f(hi) > 0:
            return None
        return float(brentq(f, lo, hi, xtol=1e-9) * 100.0)
    except (ValueError, RuntimeError):
        return None


def lcoe(capex: float, om: np.ndarray, replacements: np.ndarray, generation: np.ndarray, rate_pct: float) -> float | None:
    """PHP per kWh produced: (capex + PV of O&M and replacements) / PV of generation."""
    r = rate_pct / 100.0
    t = np.arange(1, len(generation) + 1)
    pv_gen = float(np.sum(generation / (1.0 + r) ** t))
    if pv_gen <= 0:
        return None
    pv_cost = capex + float(np.sum((om + replacements) / (1.0 + r) ** t))
    return pv_cost / pv_gen
