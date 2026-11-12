"""Loader for ASSUMPTIONS.yaml. Every number the engine uses comes from here."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from ..config import BACKEND_DIR

PATH = Path(BACKEND_DIR) / "ASSUMPTIONS.yaml"


@lru_cache(maxsize=1)
def _load() -> dict[str, dict[str, Any]]:
    with open(PATH, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}
    return {k: dict(v) for k, v in raw.items()}


def A(key: str) -> float:
    """Numeric assumption value."""
    return float(_load()[key]["value"])


def assumption_record(key: str, value: float | None = None) -> dict:
    item = _load()[key]
    return {
        "key": key,
        "value": item["value"] if value is None else value,
        "unit": item.get("unit", ""),
        "source_url": item.get("source_url", ""),
        "as_of": str(item.get("as_of", "")),
        "verified": bool(item.get("verified", False)),
        "note": item.get("note", ""),
    }


def all_assumptions() -> list[dict]:
    return [assumption_record(k) for k in _load()]


def clear_cache() -> None:
    _load.cache_clear()
