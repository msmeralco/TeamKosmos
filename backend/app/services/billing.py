"""Monthly bill model with net-metering credits (see context/IMPLEMENTATION_PLAN.md section 7.6).

Net metering ON: exported kWh earn a credit at the export rate (an approximation of the blended generation
cost, NOT the retail rate). Credits are banked month to month and offset energy charges only. Fixed charges
are never offset and unused credit is never paid out.   [VERIFY] the method against a real Meralco bill.
Net metering OFF: exports earn nothing.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass
class BillResult:
    baseline: np.ndarray  # (years,) bill without solar
    solar: np.ndarray  # (years,) bill with solar
    credit_used: np.ndarray  # (years,) PHP of credit that offset energy charges
    final_bank: float  # unused credit left at the end of the horizon (forfeited)

    @property
    def savings(self) -> np.ndarray:
        return self.baseline - self.solar


def annual_bills(
    monthly_import: np.ndarray,  # (years, 12) kWh
    monthly_export: np.ndarray,  # (years, 12) kWh
    monthly_load: np.ndarray,  # (12,) kWh
    *,
    tariff: float,
    tariff_growth_pct: float,
    export_credit: float,
    export_credit_growth_pct: float,
    fixed_php_month: float,
    net_metering: bool,
) -> BillResult:
    years = monthly_import.shape[0]
    baseline = np.zeros(years)
    solar = np.zeros(years)
    credit_used = np.zeros(years)
    bank = 0.0
    for y in range(years):
        r = tariff * (1.0 + tariff_growth_pct / 100.0) ** y
        e = min(r, export_credit * (1.0 + export_credit_growth_pct / 100.0) ** y)  # never above retail
        for m in range(12):
            baseline[y] += fixed_php_month + monthly_load[m] * r
            energy = monthly_import[y, m] * r
            if net_metering:
                available = bank + monthly_export[y, m] * e
                applied = min(available, energy)
                bank = available - applied
            else:
                applied = 0.0
            credit_used[y] += applied
            solar[y] += fixed_php_month + energy - applied
    return BillResult(baseline=baseline, solar=solar, credit_used=credit_used, final_bank=bank)
