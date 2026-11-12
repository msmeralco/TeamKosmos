"""Build data/demo_outlines.geojson from real addresses you choose (OpenStreetMap building outlines).

Usage (from backend/):
  python scripts/build_demo_outlines.py --name "Reyes house" --address "12 Example St, Quezon City" [--alias "reyes"] ...
Repeat the --name/--address/--alias group for each address (they pair up in order). Existing entries are kept
unless --replace is given. Needs a real CONTACT_EMAIL in backend/.env (Nominatim rejects the placeholder).
Check each result in a browser: OSM may have no outline for an address.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402
from app.errors import ApiError  # noqa: E402
from app.services import geo  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", action="append", required=True)
    ap.add_argument("--address", action="append", required=True)
    ap.add_argument("--alias", action="append", default=[])
    ap.add_argument("--replace", action="store_true")
    args = ap.parse_args()
    if len(args.name) != len(args.address):
        print("Give one --name per --address.")
        return 2
    if get_settings().contact_email.endswith("@example.com"):
        print("Set CONTACT_EMAIL in backend/.env to a real address first (Nominatim rejects the placeholder).")
        return 2

    path = geo.DEMO_PATH
    features = [] if args.replace or not path.exists() else json.loads(path.read_text(encoding="utf-8")).get("features", [])
    failed = 0
    for i, (name, address) in enumerate(zip(args.name, args.address)):
        res = geo.geocode(address)
        real = [c for c in res["candidates"] if c["source"] == "nominatim"]
        if not real:
            print(f"NOT FOUND   {address}")
            failed += 1
            continue
        c = real[0]
        try:
            roof = geo.roof_from_address(c["lat"], c["lon"])
        except ApiError as exc:
            print(f"NO OUTLINE  {address}: {exc.message}")
            failed += 1
            continue
        aliases = [args.alias[i]] if i < len(args.alias) else []
        features.append({
            "type": "Feature",
            "properties": {"name": name, "aliases": aliases + [address], "synthetic": False, "roof_shape": roof.roof_type,
                           "note": "Outline from OpenStreetMap contributors (ODbL). Demo household data is synthetic."},
            "geometry": {"type": "Polygon", "coordinates": [[list(p) for p in roof.polygon_lonlat]]},
        })
        print(f"OK          {name}: {roof.area_m2:g} m2 at {c['lat']:.5f}, {c['lon']:.5f}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type": "FeatureCollection", "features": features}, indent=1), encoding="utf-8")
    print(f"Wrote {len(features)} outline(s) to {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
