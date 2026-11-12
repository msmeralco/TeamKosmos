"""Product catalog: synthetic seed data + prices from the scraper pipeline, stored via the repository.

The seed catalog is SYNTHETIC demo data (source_url 'seed:synthetic'). Replace it with hand-collected,
sourced prices before real use. Every product carries source, timestamp, method and confidence.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from ..config import BACKEND_DIR
from ..db import get_repo

SEED_PATH = Path(BACKEND_DIR) / "data" / "seed_catalog.csv"
SEED_TIME = "2026-11-12T00:00:00+08:00"
FRESH_HOURS = 24

_FLOAT = {"price_php", "watts", "length_m", "width_m", "efficiency_pct", "degradation_pct_per_year", "inverter_ac_kw",
          "max_dc_kw", "battery_kwh", "battery_max_kw", "embodied_carbon_kg"}
_INT = {"warranty_years", "cycles"}


def load_seed(path: Path | None = None) -> list[dict]:
    out: list[dict] = []
    with open(path or SEED_PATH, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            p: dict = {"id": row["id"], "category": row["category"], "brand": row["brand"], "model": row["model"]}
            for k, v in row.items():
                if k in p or v in ("", None):
                    continue
                if k in _FLOAT:
                    p[k] = float(v)
                elif k in _INT:
                    p[k] = int(float(v))
                elif k == "hybrid":
                    p[k] = v.strip().lower() == "true"
                else:
                    p[k] = v
            if p["category"] == "panel":
                p["dims_m"] = [p.pop("length_m"), p.pop("width_m")]
            p.setdefault("embodied_carbon_kg", None)  # None -> shown as "not disclosed"
            p.update(source_url="seed:synthetic", fetched_at=SEED_TIME, method="seed", confidence=0.5, synthetic=True)
            out.append(p)
    return out


def ensure_seed() -> None:
    repo = get_repo()
    existing = {p["id"] for p in repo.list_products()}
    missing = [p for p in load_seed() if p["id"] not in existing]
    if missing:
        repo.upsert_products(missing)


def _freshness(p: dict, now: datetime) -> tuple[bool, str]:
    if p.get("method") == "seed":
        return False, "seed"
    try:
        age_h = (now - datetime.fromisoformat(p["fetched_at"])).total_seconds() / 3600
    except (KeyError, ValueError):
        return True, "cached"
    return (age_h > FRESH_HOURS), ("live" if age_h <= FRESH_HOURS else "cached")


def list_products(category: str | None = None) -> list[dict]:
    ensure_seed()
    now = datetime.now(timezone.utc)
    out = []
    for p in get_repo().list_products(category):
        stale, fresh = _freshness(p, now)
        out.append({**p, "stale": stale, "freshness": fresh})
    return out


def store_products(products: list[dict]) -> None:
    get_repo().upsert_products(products)
