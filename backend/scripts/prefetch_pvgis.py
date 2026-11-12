"""Pre-download PVGIS-ERA5 hourly data for the accounts in the database (flat roof, 12 deg tilt, facing south).

Usage (from backend/):  python scripts/prefetch_pvgis.py [--tilt 12] [--azimuth 180] [--lat LAT --lon LON]
Writes data/pvgis_bundled/*.npz so the demo works offline. Each fetch takes about a minute.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import irradiance  # noqa: E402
from app.db import get_repo  # noqa: E402
from app.services.agent.personas import DEFAULT_LAT, DEFAULT_LON  # noqa: E402


def _account_points() -> list[tuple[float, float]]:
    """Locations of the accounts in the database (falls back to the default map centre)."""
    repo = get_repo()
    pts = [(u["lat"], u["lon"]) for u in repo.list_users() if u.get("lat") is not None and u.get("lon") is not None]
    return pts or [(DEFAULT_LAT, DEFAULT_LON)]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tilt", type=float, default=12)
    ap.add_argument("--azimuth", type=float, default=180)
    ap.add_argument("--lat", type=float)
    ap.add_argument("--lon", type=float)
    args = ap.parse_args()
    points = [(args.lat, args.lon)] if args.lat is not None and args.lon is not None else _account_points()
    seen, failed = set(), 0
    for lat, lon in points:
        key = irradiance.cache_key(lat, lon, args.tilt, args.azimuth)
        if key in seen:
            continue
        seen.add(key)
        path = irradiance.BUNDLED_DIR / f"{key}.npz"
        if path.exists():
            print(f"skip   {key} (already bundled)")
            continue
        qlat, qlon, qt, qa = irradiance.quantize(lat, lon, args.tilt, args.azimuth)
        print(f"fetch  {key} ...", flush=True)
        try:
            ys = irradiance.fetch_pvgis(qlat, qlon, qt, qa, year_range=irradiance.FULL_RANGE, timeout=180)
            irradiance._save(path, ys)
            print(f"saved  {path.name}: {len(ys.years)} years, median yield {sorted(ys.annual_yield())[len(ys.years)//2]:.0f} kWh/kWp")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"FAILED {key}: {exc.__class__.__name__}: {str(exc)[:160]}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
