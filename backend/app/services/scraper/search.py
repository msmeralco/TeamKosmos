"""Live product search as a stream of progress events.

Events: source_started, product_found, source_failed, done.  Falls back to cached/seed rows and says so.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

import yaml

from .. import products as catalog
from . import extract as extract_mod
from . import fetch, validate

SOURCES_PATH = Path(__file__).with_name("sources.yaml")


def load_sources() -> list[dict]:
    try:
        data = yaml.safe_load(SOURCES_PATH.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return []
    return [s for s in data.get("sources", []) if s.get("enabled") and s.get("robots_ok") and s.get("terms_ok")]


def search(categories: list[str] | None = None) -> Iterator[dict]:
    cats = categories or ["panel", "inverter", "battery"]
    sources = load_sources()
    found = 0
    if not sources:
        yield {"event": "source_failed", "source": "(none)",
               "reason": "No retailer source has been enabled and hand-checked yet, so cached and seed prices are used."}
    for src in sources:
        yield {"event": "source_started", "source": src["name"]}
        stored: list[dict] = []
        try:
            for cat in cats:
                path = (src.get("listings") or {}).get(cat)
                if not path:
                    continue
                if not fetch.allowed_by_robots(src["base_url"], path):
                    raise fetch.FetchError(f"robots.txt does not allow {path}")
                html = fetch.fetch_html(src["base_url"].rstrip("/") + path)
                for raw in extract_mod.extract(html, src["base_url"], cat, src.get("selectors")):
                    product, reason = validate.normalise(raw, source_name=src["name"])
                    if product is None:
                        yield {"event": "product_rejected", "source": src["name"], "name": raw.get("name"), "reason": reason}
                        continue
                    stored.append(product)
                    found += 1
                    yield {"event": "product_found", "source": src["name"], "product": product}
        except fetch.FetchError as exc:
            yield {"event": "source_failed", "source": src["name"], "reason": str(exc)[:200]}
        if stored:
            catalog.store_products(stored)
    cached = catalog.list_products()
    yield {"event": "done", "found_live": found,
           "catalog_size": len(cached),
           "note": "Suggested prices from public listings or cached/seed data. Confirm with the seller."}
