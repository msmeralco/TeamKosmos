import json

import httpx
import pytest

from app.services import products
from app.services.scraper import extract, fetch, search, validate

JSONLD = """<html><head><script type="application/ld+json">%s</script></head><body></body></html>"""


def test_seed_catalog_loads_with_sources_and_nulls():
    items = products.list_products()
    cats = {p["category"] for p in items}
    assert cats == {"panel", "inverter", "battery"}
    panel = next(p for p in items if p["id"] == "seed-panel-550")
    assert panel["dims_m"] == [2.28, 1.13] and panel["watts"] == 550
    assert panel["embodied_carbon_kg"] is None  # shown as "not disclosed"
    assert panel["source_url"] == "seed:synthetic" and panel["synthetic"] is True and panel["freshness"] == "seed"
    assert [p["hybrid"] for p in items if p["id"] == "seed-hyb-5"] == [True]
    assert products.list_products("battery") and all(p["category"] == "battery" for p in products.list_products("battery"))


def test_seed_is_idempotent():
    products.ensure_seed()
    n = len(products.list_products())
    products.ensure_seed()
    assert len(products.list_products()) == n


def test_jsonld_extraction_and_validation():
    node = {"@type": "Product", "name": "Mono Solar Panel 550W", "brand": {"name": "Acme"},
            "offers": {"price": "8,800", "priceCurrency": "PHP"}, "url": "/p/1"}
    html = JSONLD % json.dumps({"@graph": [node]})
    raws = extract.extract(html, "https://shop.test", "panel", None)
    assert raws[0]["watts"] == 550 and raws[0]["price"] == 8800 and raws[0]["url"] == "https://shop.test/p/1"
    p, reason = validate.normalise(raws[0], source_name="shop")
    assert p and p["dims_m"] == [2.28, 1.13] and p["dims_estimated"] is True and p["id"].startswith("live-")


def test_selector_fallback():
    html = '<div class="c"><span class="t">Hybrid Inverter 5kW</span><b class="p">PHP 78,000.00</b><a href="/x">x</a></div>'
    sel = {"item": ".c", "name": ".t", "price": ".p", "link": "a"}
    raws = extract.extract(html, "https://shop.test", "inverter", sel)
    assert raws and raws[0]["inverter_ac_kw"] == 5 and raws[0]["hybrid"] is True and raws[0]["price"] == 78000
    assert validate.normalise(raws[0], source_name="s")[0] is not None


@pytest.mark.parametrize("raw,fragment", [
    ({"category": "panel", "brand": "A", "name": "P 550W", "price": 100.0, "url": "u", "method": "jsonld", "confidence": .9, "watts": 550}, "per watt"),
    ({"category": "panel", "brand": "A", "name": "Panel", "price": 8000.0, "url": "u", "method": "jsonld", "confidence": .9}, "without watts"),
    ({"category": "battery", "brand": "A", "name": "B 5kWh", "price": 5.0, "url": "u", "method": "jsonld", "confidence": .9, "battery_kwh": 5}, "per kWh"),
    ({"category": "panel", "brand": "A", "name": "P 550W", "price": 8000.0, "currency": "USD", "url": "u", "method": "jsonld", "confidence": .9, "watts": 550}, "currency"),
])
def test_validation_rejects_bad_rows(raw, fragment):
    p, reason = validate.normalise(raw, source_name="s")
    assert p is None and fragment in reason


def test_search_without_enabled_sources_reports_fallback():
    events = list(search.search())
    assert events[0]["event"] == "source_failed" and "cached" in events[0]["reason"]
    assert events[-1]["event"] == "done" and "Confirm with the seller" in events[-1]["note"]


def test_search_runs_enabled_source_and_stores(monkeypatch):
    src = {"name": "shop", "enabled": True, "robots_ok": True, "terms_ok": True, "base_url": "https://shop.test",
           "listings": {"panel": "/panels"}}
    monkeypatch.setattr(search, "load_sources", lambda: [src])
    node = {"@type": "Product", "name": "Mono 550W Panel", "brand": "Acme", "offers": {"price": 8800, "priceCurrency": "PHP"}}
    page = JSONLD % json.dumps(node)

    def handler(request):
        if request.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nAllow: /")
        return httpx.Response(200, text=page, headers={"content-type": "text/html"})

    monkeypatch.setattr(fetch, "MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(fetch, "client_factory", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    events = list(search.search(["panel"]))
    assert [e["event"] for e in events] == ["source_started", "product_found", "done"]
    live = [p for p in products.list_products("panel") if p["id"].startswith("live-")]
    assert len(live) == 1 and live[0]["freshness"] == "live"


def test_robots_disallow_and_unreachable_block_fetch(monkeypatch):
    monkeypatch.setattr(fetch, "client_factory", lambda: httpx.Client(transport=httpx.MockTransport(
        lambda r: httpx.Response(200, text="User-agent: *\nDisallow: /panels"))))
    assert fetch.allowed_by_robots("https://shop.test", "/panels") is False

    def boom(r):
        raise httpx.ConnectError("x")

    monkeypatch.setattr(fetch, "client_factory", lambda: httpx.Client(transport=httpx.MockTransport(boom)))
    assert fetch.allowed_by_robots("https://shop.test", "/panels") is False
