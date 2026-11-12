"""Extract products from a listing page: JSON-LD first, then CSS selectors."""
from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

_WATTS = re.compile(r"(\d{3,4})\s*-?\s*w(?:att)?s?\b", re.I)
_KW = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*kw(?!h)", re.I)
_KWH = re.compile(r"(\d+(?:\.\d+)?)\s*-?\s*kwh", re.I)
_PRICE = re.compile(r"(\d[\d,]*(?:\.\d+)?)")

# Typical module sizes when the page does not state dimensions (flagged as estimated).
def estimate_panel_dims(watts: float) -> list[float]:
    if watts <= 460:
        return [1.91, 1.13]
    if watts <= 600:
        return [2.28, 1.13]
    return [2.38, 1.13]


def parse_price(text: str | float | None) -> float | None:
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    m = _PRICE.search(str(text).replace("\xa0", " "))
    return float(m.group(1).replace(",", "")) if m else None


def _spec_from_name(name: str, category: str) -> dict:
    spec: dict = {}
    if category == "panel":
        m = _WATTS.search(name)
        if m:
            spec["watts"] = float(m.group(1))
    elif category == "inverter":
        m = _KW.search(name)
        if m:
            spec["inverter_ac_kw"] = float(m.group(1))
        spec["hybrid"] = "hybrid" in name.lower()
    elif category == "battery":
        m = _KWH.search(name)
        if m:
            spec["battery_kwh"] = float(m.group(1))
    return spec


def _product_nodes(data):
    if isinstance(data, list):
        for d in data:
            yield from _product_nodes(d)
    elif isinstance(data, dict):
        t = data.get("@type")
        types = t if isinstance(t, list) else [t]
        if "Product" in types:
            yield data
        for key in ("@graph", "itemListElement", "item"):
            if key in data:
                yield from _product_nodes(data[key])


def extract_jsonld(html: str, base_url: str, category: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        for node in _product_nodes(data):
            offers = node.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = parse_price(offers.get("price"))
            name = str(node.get("name", "")).strip()
            if not name or price is None:
                continue
            currency = str(offers.get("priceCurrency", "PHP")).upper()
            brand = node.get("brand")
            brand = brand.get("name") if isinstance(brand, dict) else brand
            out.append({"name": name, "brand": str(brand or name.split()[0]), "price": price, "currency": currency,
                        "url": urljoin(base_url, str(node.get("url") or offers.get("url") or "")),
                        "category": category, "method": "jsonld", "confidence": 0.9, **_spec_from_name(name, category)})
    return out


def extract_selectors(html: str, base_url: str, category: str, sel: dict) -> list[dict]:
    if not sel or not sel.get("item"):
        return []
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for item in soup.select(sel["item"]):
        name_el = item.select_one(sel.get("name", "")) if sel.get("name") else None
        price_el = item.select_one(sel.get("price", "")) if sel.get("price") else None
        link_el = item.select_one(sel.get("link", "a")) if sel.get("link", "a") else None
        if not name_el or not price_el:
            continue
        price = parse_price(price_el.get_text(" ", strip=True))
        name = name_el.get_text(" ", strip=True)
        if price is None or not name:
            continue
        href = link_el.get("href") if link_el else ""
        out.append({"name": name, "brand": name.split()[0], "price": price, "currency": "PHP",
                    "url": urljoin(base_url, href or ""), "category": category, "method": "selector",
                    "confidence": 0.7, **_spec_from_name(name, category)})
    return out


def extract(html: str, base_url: str, category: str, selectors: dict | None) -> list[dict]:
    return extract_jsonld(html, base_url, category) or extract_selectors(html, base_url, category, selectors or {})
