"""Hourly PV output per kWp for a location/orientation.

Source order: runtime cache -> bundled pre-downloaded files -> live PVGIS-ERA5 -> approximate typical year.
Output scales linearly with system size, so one series per (location, tilt, azimuth) serves any kWp.
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from ..config import BACKEND_DIR, get_settings
from .assumptions import A

log = logging.getLogger("sol.irradiance")

PVGIS_URL = "https://re.jrc.ec.europa.eu/api/v5_3/"  # v5_3 endpoint verified for Manila
BUNDLED_DIR = Path(BACKEND_DIR) / "data" / "pvgis_bundled"
FULL_RANGE = (2005, 2023)
LIVE_RANGE = (2010, 2023)  # shorter range for on-demand fetches (faster)
LIVE_TIMEOUT_S = 35  # a chat turn is capped at 75 s, so a slow PVGIS call falls back instead of stalling the user

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
_memory: dict[str, "YearSet"] = {}


@dataclass
class YearSet:
    years: list[str]
    data: np.ndarray  # (n_years, 8760) kW per kWp, local time, non-leap
    source: str  # PVGIS-ERA5 | approximate
    notes: list[str] = field(default_factory=list)
    is_approximate: bool = False

    def annual_yield(self) -> np.ndarray:
        return self.data.sum(axis=1)

    def scenario_years(self) -> dict[str, tuple[str, np.ndarray]]:
        """pessimistic = ~P10 yield year, expected = median year, optimistic = ~P90 year."""
        y = self.annual_yield()
        order = np.argsort(y)
        n = len(order)
        pick = {
            "pessimistic": order[int(round(0.1 * (n - 1)))],
            "expected": order[n // 2],
            "optimistic": order[int(round(0.9 * (n - 1)))],
        }
        return {k: (self.years[i], self.data[i]) for k, i in pick.items()}


def quantize(lat: float, lon: float, tilt: float, azimuth: float) -> tuple[float, float, int, int]:
    return round(lat, 1), round(lon, 1), int(round(tilt)), int(round(azimuth / 5.0) * 5) % 360


def cache_key(lat: float, lon: float, tilt: float, azimuth: float) -> str:
    qlat, qlon, qt, qa = quantize(lat, lon, tilt, azimuth)
    return f"{qlat:.1f}_{qlon:.1f}_t{qt}_a{qa}"


def _runtime_dir() -> Path:
    return get_settings().data_dir / "pvgis_cache"


def _save(path: Path, ys: YearSet) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.npz")
    np.savez_compressed(tmp, data=ys.data.astype(np.float32), years=np.array(ys.years), source=np.array(ys.source),
                        notes=np.array(ys.notes, dtype=object), approx=np.array(ys.is_approximate))
    tmp.replace(path)


def _load(path: Path) -> YearSet | None:
    try:
        with np.load(path, allow_pickle=True) as z:
            return YearSet(years=[str(y) for y in z["years"]], data=z["data"].astype(np.float64),
                           source=str(z["source"]), notes=[str(n) for n in z["notes"]],
                           is_approximate=bool(z["approx"]))
    except (OSError, ValueError, KeyError) as exc:
        log.warning("Could not read %s: %s", path, exc)
        return None


def series_from_pvgis(df: pd.DataFrame) -> tuple[list[str], np.ndarray]:
    """PVGIS hourly frame (UTC, W per kWp in column P) -> complete local (UTC+8) non-leap years."""
    s = df["P"].astype(float) / 1000.0
    idx = s.index.tz_convert("Asia/Manila").floor("h")
    s = pd.Series(s.to_numpy(), index=idx)
    s = s[~s.index.duplicated(keep="first")]
    years, rows = [], []
    for y, g in s.groupby(s.index.year):
        g = g[~((g.index.month == 2) & (g.index.day == 29))]
        if len(g) == 8760:
            years.append(str(y))
            rows.append(g.to_numpy())
    if not rows:
        raise ValueError("PVGIS returned no complete calendar year")
    return years, np.vstack(rows)


def fetch_pvgis(lat: float, lon: float, tilt: float, azimuth: float, *, year_range: tuple[int, int],
                timeout: float) -> YearSet:
    import pvlib

    df, _meta = pvlib.iotools.get_pvgis_hourly(
        lat, lon, start=year_range[0], end=year_range[1], raddatabase="PVGIS-ERA5", components=False,
        surface_tilt=tilt, surface_azimuth=azimuth,  # pvlib convention: clockwise from north, 180 = south
        pvcalculation=True, peakpower=1.0, loss=A("system_losses_pct"), url=PVGIS_URL, timeout=timeout,
    )
    years, data = series_from_pvgis(df)
    return YearSet(years=years, data=data, source="PVGIS-ERA5",
                   notes=[f"PVGIS-ERA5 modelled estimate, {years[0]} to {years[-1]} ({len(years)} complete years)."])


# Approximate monthly clear-sky fraction for Metro Manila (dry season sunnier than the wet season).
# Disclosed placeholder used only when PVGIS is unreachable and nothing is cached.
_CLOUD_FACTOR = np.array([0.80, 0.82, 0.82, 0.78, 0.68, 0.62, 0.58, 0.57, 0.60, 0.66, 0.70, 0.75])


def approximate_year_set(lat: float, lon: float, tilt: float, azimuth: float) -> YearSet:
    import pvlib

    times = pd.date_range("2021-01-01", periods=8760, freq="h", tz="Asia/Manila")
    loc = pvlib.location.Location(lat, lon, tz="Asia/Manila")
    sol = loc.get_solarposition(times + pd.Timedelta(minutes=30))
    sol.index = times
    cs = loc.get_clearsky(times + pd.Timedelta(minutes=30), model="ineichen", linke_turbidity=3.5)
    cs.index = times
    poa = pvlib.irradiance.get_total_irradiance(
        tilt, azimuth, sol["apparent_zenith"], sol["azimuth"], cs["dni"], cs["ghi"], cs["dhi"], albedo=0.2
    )["poa_global"].fillna(0.0).clip(lower=0.0).to_numpy()
    months = times.month.to_numpy() - 1
    poa = poa * _CLOUD_FACTOR[months]
    cell_temp = 30.0 + 0.03 * poa
    temp_factor = 1.0 - 0.0035 * (cell_temp - 25.0)
    base = poa / 1000.0 * (1.0 - A("system_losses_pct") / 100.0) * temp_factor
    base = np.clip(base, 0.0, 1.0)
    data = np.vstack([base * 0.93, base, base * 1.07])
    return YearSet(
        years=["approx_low", "approx_typical", "approx_high"], data=data, source="approximate", is_approximate=True,
        notes=["APPROXIMATE typical year (clear-sky model with a fixed cloud factor), used because PVGIS-ERA5 could not be reached. "
               "Low and high years are +/-7% of the typical year, not real weather years."],
    )


def get_year_set(lat: float, lon: float, tilt: float, azimuth: float, *, allow_live: bool | None = None,
                 year_range: tuple[int, int] = LIVE_RANGE) -> YearSet:
    key = cache_key(lat, lon, tilt, azimuth)
    if key in _memory:
        return _memory[key]
    with _locks_guard:
        lock = _locks.setdefault(key, threading.Lock())
    with lock:
        if key in _memory:
            return _memory[key]
        for path in (_runtime_dir() / f"{key}.npz", BUNDLED_DIR / f"{key}.npz"):
            if path.exists():
                ys = _load(path)
                if ys is not None:
                    _memory[key] = ys
                    return ys
        qlat, qlon, qt, qa = quantize(lat, lon, tilt, azimuth)
        live = get_settings().pvgis_live if allow_live is None else allow_live
        if live:
            try:
                ys = fetch_pvgis(qlat, qlon, qt, qa, year_range=year_range, timeout=LIVE_TIMEOUT_S)
                _save(_runtime_dir() / f"{key}.npz", ys)
                _memory[key] = ys
                return ys
            except Exception as exc:  # network, HTTP 4xx/5xx, parse problems
                log.warning("PVGIS fetch failed (%s: %s); using approximate year", exc.__class__.__name__, str(exc)[:120])
        ys = approximate_year_set(qlat, qlon, qt, qa)
        if live:
            ys.notes.append("PVGIS-ERA5 was unreachable when this was computed.")
        # Approximate sets are not written to disk: a later run should retry the real source.
        return ys


def clear_memory() -> None:
    _memory.clear()
