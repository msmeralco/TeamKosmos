"""Household load estimate: monthly kWh -> typical-year hourly kW (8760 values, local time, non-leap)."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..errors import ApiError
from .assumptions import A

TEMPLATES = ("night_heavy", "balanced", "day_heavy")

# Relative hourly shapes (hour 0..23). Synthetic, disclosed as assumptions, normalised per month.
SHAPES: dict[str, dict[str, list[float]]] = {
    "night_heavy": {
        "weekday": [0.45, 0.40, 0.38, 0.38, 0.40, 0.55, 0.80, 0.70, 0.45, 0.35, 0.33, 0.33, 0.35, 0.33, 0.33, 0.35, 0.50, 0.90, 1.40, 1.60, 1.50, 1.30, 0.90, 0.60],
        "weekend": [0.50, 0.45, 0.42, 0.42, 0.42, 0.50, 0.65, 0.80, 0.80, 0.70, 0.65, 0.65, 0.70, 0.65, 0.65, 0.65, 0.75, 1.00, 1.40, 1.55, 1.45, 1.25, 0.90, 0.65],
    },
    "balanced": {
        "weekday": [0.45, 0.40, 0.38, 0.38, 0.42, 0.70, 1.20, 1.30, 0.90, 0.70, 0.65, 0.65, 0.75, 0.70, 0.65, 0.70, 0.85, 1.20, 1.50, 1.60, 1.45, 1.20, 0.85, 0.60],
        "weekend": [0.50, 0.45, 0.42, 0.42, 0.45, 0.60, 0.85, 1.10, 1.20, 1.10, 1.05, 1.05, 1.10, 1.00, 0.95, 0.95, 1.05, 1.30, 1.50, 1.55, 1.40, 1.15, 0.85, 0.60],
    },
    "day_heavy": {
        "weekday": [0.50, 0.45, 0.42, 0.42, 0.45, 0.60, 0.85, 1.00, 1.20, 1.35, 1.40, 1.40, 1.35, 1.40, 1.45, 1.40, 1.30, 1.30, 1.45, 1.50, 1.30, 1.05, 0.80, 0.60],
        "weekend": [0.50, 0.45, 0.42, 0.42, 0.45, 0.60, 0.80, 0.95, 1.10, 1.25, 1.30, 1.30, 1.30, 1.30, 1.30, 1.25, 1.20, 1.25, 1.40, 1.45, 1.30, 1.05, 0.80, 0.60],
    },
}
# Hotter months use more power. Normalised to mean 1 so the annual total equals 12 x the monthly figure.
_SEASON_RAW = np.array([0.92, 0.92, 0.98, 1.08, 1.14, 1.10, 1.02, 1.00, 0.98, 0.98, 0.94, 0.94])
SEASON = _SEASON_RAW / _SEASON_RAW.mean()

_INDEX = pd.date_range("2021-01-01", periods=8760, freq="h")  # a non-leap year
MONTH_IDX = _INDEX.month.to_numpy() - 1
HOUR_IDX = _INDEX.hour.to_numpy()
WEEKEND = (_INDEX.dayofweek.to_numpy() >= 5)
DAYS_IN_MONTH = np.array([31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31])


@dataclass
class LoadProfile:
    monthly_kwh: np.ndarray  # 12
    hourly_kw: np.ndarray  # 8760
    template: str
    basis: str
    base_monthly_kwh: float

    def to_dict(self, include_hourly: bool = True) -> dict:
        d = {
            "monthly_kwh": [round(float(v), 3) for v in self.monthly_kwh],
            "template": self.template,
            "basis": self.basis,
            "base_monthly_kwh": round(self.base_monthly_kwh, 3),
            "annual_kwh": round(float(self.hourly_kw.sum()), 3),
            "is_estimate": True,
        }
        if include_hourly:
            d["hourly_kw"] = [round(float(v), 5) for v in self.hourly_kw]
        return d


def bill_to_kwh(bill_php: float, tariff: float | None = None, fixed: float | None = None) -> float:
    tariff = A("tariff_php_per_kwh") if tariff is None else tariff
    fixed = A("tariff_fixed_php_month") if fixed is None else fixed
    return max(0.0, (bill_php - fixed) / tariff)


def estimate_load(*, monthly_kwh: float | None = None, bill_php: float | None = None,
                  template: str = "balanced", basis: str | None = None) -> LoadProfile:
    if template not in TEMPLATES:
        raise ApiError("invalid_template", f"template must be one of {', '.join(TEMPLATES)}", status=422)
    if (monthly_kwh is None) == (bill_php is None):
        raise ApiError("invalid_request", "Give either monthly_kwh or bill_php.", status=422)
    if monthly_kwh is None:
        basis = basis or "bill"
        base = bill_to_kwh(float(bill_php))  # type: ignore[arg-type]
    else:
        basis = basis or "kwh_input"
        base = float(monthly_kwh)
    if not 30 <= base <= 5000:
        raise ApiError("invalid_load", f"Monthly usage of {base:.0f} kWh is outside the supported range (30 to 5000).", status=422)

    monthly = base * SEASON
    rng = np.random.default_rng(20261112 + int(round(base)))
    noise = rng.lognormal(mean=0.0, sigma=0.06, size=8760)
    shape = np.where(
        WEEKEND,
        np.array(SHAPES[template]["weekend"])[HOUR_IDX],
        np.array(SHAPES[template]["weekday"])[HOUR_IDX],
    )
    w = shape * noise
    hourly = np.zeros(8760)
    for m in range(12):
        sel = MONTH_IDX == m
        hourly[sel] = w[sel] / w[sel].sum() * monthly[m]
    return LoadProfile(monthly_kwh=monthly, hourly_kw=hourly, template=template, basis=basis, base_monthly_kwh=base)


def from_profile(profile) -> LoadProfile:
    """Build the load from a session Profile (monthly kWh or bill, template)."""
    tmpl = profile.household_template or "balanced"
    if profile.monthly_kwh is not None:
        return estimate_load(monthly_kwh=profile.monthly_kwh, template=tmpl,
                             basis="persona" if profile.load_source == "persona" else "kwh_input")
    if profile.monthly_bill_php is not None:
        return estimate_load(bill_php=profile.monthly_bill_php, template=tmpl, basis="bill")
    raise ApiError("no_load", "There is no usage or bill yet.", status=422)
