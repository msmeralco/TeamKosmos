"""Hourly PV / battery / grid energy balance.

Per hour:  pv_ac = direct + charge + export     and     load = direct + discharge + import
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .load import MONTH_IDX


@dataclass(frozen=True)
class Inverter:
    ac_kw: float
    efficiency: float = 0.97  # 0..1
    max_dc_kw: float | None = None


@dataclass(frozen=True)
class Battery:
    usable_kwh: float
    max_kw: float
    round_trip_eff: float = 0.90  # 0..1


@dataclass
class DispatchResult:
    pv_ac: np.ndarray
    direct: np.ndarray
    charge: np.ndarray
    discharge: np.ndarray
    export: np.ndarray
    import_: np.ndarray
    soc: np.ndarray

    def _monthly(self, arr: np.ndarray) -> np.ndarray:
        return np.bincount(MONTH_IDX, weights=arr, minlength=12)

    @property
    def monthly_import(self) -> np.ndarray:
        return self._monthly(self.import_)

    @property
    def monthly_export(self) -> np.ndarray:
        return self._monthly(self.export)

    @property
    def monthly_generation(self) -> np.ndarray:
        return self._monthly(self.pv_ac)

    @property
    def generation_kwh(self) -> float:
        return float(self.pv_ac.sum())

    @property
    def export_kwh(self) -> float:
        return float(self.export.sum())

    @property
    def import_kwh(self) -> float:
        return float(self.import_.sum())

    @property
    def self_consumption_pct(self) -> float:
        g = self.generation_kwh
        return 0.0 if g <= 0 else 100.0 * (g - self.export_kwh) / g

    @property
    def battery_throughput_kwh(self) -> float:
        return float(self.discharge.sum())


def pv_ac_series(pv_dc_kw: np.ndarray, inverter: Inverter) -> np.ndarray:
    dc = pv_dc_kw if inverter.max_dc_kw is None else np.minimum(pv_dc_kw, inverter.max_dc_kw)
    return np.minimum(dc * inverter.efficiency, inverter.ac_kw)


def dispatch(pv_dc_kw: np.ndarray, load_kw: np.ndarray, inverter: Inverter, battery: Battery | None = None) -> DispatchResult:
    if pv_dc_kw.shape != (8760,) or load_kw.shape != (8760,):
        raise ValueError("pv and load must both have 8760 hourly values")
    pv_ac = pv_ac_series(pv_dc_kw, inverter)
    direct = np.minimum(pv_ac, load_kw)
    if battery is None or battery.usable_kwh <= 0:
        zeros = np.zeros(8760)
        return DispatchResult(pv_ac, direct, zeros, zeros, pv_ac - direct, load_kw - direct, zeros)

    eff = math.sqrt(max(1e-6, min(1.0, battery.round_trip_eff)))
    cap, pmax = battery.usable_kwh, battery.max_kw
    pv_l, load_l, direct_l = pv_ac.tolist(), load_kw.tolist(), direct.tolist()
    charge, discharge, export, import_, soc_arr = [0.0] * 8760, [0.0] * 8760, [0.0] * 8760, [0.0] * 8760, [0.0] * 8760
    soc = 0.0
    for t in range(8760):
        surplus = pv_l[t] - direct_l[t]
        deficit = load_l[t] - direct_l[t]
        if surplus > 0.0:
            if soc < cap:
                c = min(surplus, pmax, (cap - soc) / eff)
                soc += c * eff
                surplus -= c
                charge[t] = c
        elif deficit > 0.0 and soc > 0.0:
            d = min(deficit, pmax, soc * eff)
            soc -= d / eff
            deficit -= d
            discharge[t] = d
        export[t] = surplus
        import_[t] = deficit
        soc_arr[t] = soc
    return DispatchResult(pv_ac, direct, np.array(charge), np.array(discharge), np.array(export), np.array(import_), np.array(soc_arr))
