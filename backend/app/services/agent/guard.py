"""Number guard: every number in the model's final text must come from a tool result, the profile, or the user.

If a number cannot be traced, the caller replaces the text with a template built from the tool results.
"""
from __future__ import annotations

import bisect
import re
from typing import Any, Iterable

_TOKEN = re.compile(
    r"(?<![\w.,])(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?P<suf>\s?(?:k|m|million|thousand)\b)?",
    re.I)
_AFTER_UNIT = re.compile(r"^\s?(?:%|percent|kwh|kwp|kw\b|years?|yrs?|-year|hours?|hrs?|months?|pesos?|php|m2|m²|panels?|kg|tonnes?|t\b)", re.I)
_BEFORE_CUR = re.compile(r"(?:₱|php\s?|\bp)\s*$", re.I)
_MULT = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6}
# Numbers that may appear without being in a tool result: the projection horizons used throughout the product.
CONSTANTS = {10.0, 12.0, 24.0, 25.0}


def _numbers_in_text(text: str) -> list[float]:
    out = []
    for m in _TOKEN.finditer(text):
        v = float(m.group("num").replace(",", ""))
        suf = (m.group("suf") or "").strip().lower()
        out.append(v * _MULT.get(suf, 1.0))
    return out


def collect_numbers(obj: Any, acc: list[float] | None = None) -> list[float]:
    acc = [] if acc is None else acc
    if isinstance(obj, bool) or obj is None:
        return acc
    if isinstance(obj, (int, float)):
        acc.append(float(obj))
    elif isinstance(obj, str):
        acc.extend(_numbers_in_text(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_numbers(v, acc)
    return acc


class Allowed:
    """Sorted pool of allowed values with tolerance matching."""

    def __init__(self, sources: Iterable[Any]):
        vals: list[float] = []
        for s in sources:
            collect_numbers(s, vals)
        vals += list(CONSTANTS)
        vals += [-v for v in vals]  # a loss may be quoted as a positive amount
        self.values = sorted(vals)

    def matches(self, x: float, unit: float) -> bool:
        """x matches if some allowed value is within 1% or half of the precision shown (unit)."""
        lo = bisect.bisect_left(self.values, x - max(abs(x) * 0.02, unit) - 1e-9)
        for v in self.values[lo:]:
            if v > x + max(abs(x) * 0.02, unit) + 1e-9:
                break
            if abs(v - x) <= max(abs(v) * 0.01, 0.5 * unit) + 1e-9:
                return True
        return False


def check_text(text: str, allowed: Allowed) -> list[str]:
    """Return the list of numeric tokens that could not be traced (empty means the text passes)."""
    bad = []
    for m in _TOKEN.finditer(text):
        raw = m.group("num")
        value = float(raw.replace(",", ""))
        suf = (m.group("suf") or "").strip().lower()
        mult = _MULT.get(suf, 1.0)
        decimals = len(raw.split(".")[1]) if "." in raw else 0
        unit = (10 ** -decimals) * mult
        x = value * mult
        before = text[max(0, m.start() - 4):m.start()]
        after = text[m.end():m.end() + 14]
        tied = bool(_BEFORE_CUR.search(before)) or bool(_AFTER_UNIT.match(after)) or bool(suf)
        if x in CONSTANTS:
            continue
        if not tied and "." not in raw and x <= 10:
            continue  # a bare small count like "two options" or "step 3"
        if 2000 <= x <= 2100 and "," not in raw and not tied:
            continue  # a year
        if not allowed.matches(x, unit):
            bad.append(m.group(0).strip())
    return bad
