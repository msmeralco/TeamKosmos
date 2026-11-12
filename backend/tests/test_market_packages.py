import json
from pathlib import Path

from app.services import market_packages
from app.services.agent import nlu

from test_agent_flow import reply


def test_every_package_has_a_source_link_price_and_size():
    d = json.loads(market_packages.DATA.read_text(encoding="utf-8"))
    assert len(d["packages"]) >= 20
    for p in d["packages"]:
        assert p["price_php"] > 50_000 and p["kwp"] > 0 and p["photo"]  # every package has a photo or a drawing
        if p["synthetic"]:
            assert p["link"] is None and "made-up" in p["installer"].lower() and p["type"] in ("grid-tied", "off-grid")
        else:
            assert p["link"].startswith("https://") and p["type"] == ("hybrid" if p["battery_kwh"] else "grid-tied")
        assert p["photo"].startswith(("https://", "/packages/"))
        if p["photo"].startswith("/packages/"):
            assert (Path(__file__).resolve().parents[2] / "frontend" / "public" / p["photo"].lstrip("/")).exists(), p["photo"]


def test_match_prefers_size_type_and_area_and_caps_one_installer():
    r = market_packages.match(6.2, "hybrid", "NCR")
    assert r["found"] and r["in_your_area"] and r["type_matched"] and len(r["rows"]) <= market_packages.MAX_ROWS
    assert all(p["type"] == "hybrid" and "NCR" in p["regions"] for p in r["rows"])
    assert abs(r["rows"][0]["kwp"] - 6.2) < 0.5
    assert max(sum(1 for p in r["rows"] if p["installer"] == n) for n in {p["installer"] for p in r["rows"]}) <= 2
    nobatt = market_packages.match(5.0, "grid-tied", "NCR")
    assert all(p["battery_kwh"] is None for p in nobatt["rows"])


def test_table_has_photos_prices_links_and_the_not_a_quote_note():
    md = market_packages.table_markdown(market_packages.match(6.2, "hybrid", "NCR"))
    assert "| Photo | Package | Size | Includes | Price | Installer |" in md
    assert "![" in md and "](https://" in md and "not quotes" in md and "₱" in md


def test_package_requests_route_to_real_packages_but_run_the_numbers_does_not():
    for q in ("Compare on-grid and hybrid solar packages", "Show me real ready-made packages", "how much are solar packages", "Show real packages without a battery"):
        assert nlu.detect_intent(q) == "packages", q
    for q in ("compare the packages", "run the numbers", "Can you suggest me some installers?"):
        assert nlu.detect_intent(q) != "packages", q
    assert nlu.battery_wish("Show real packages without a battery") is False and nlu.battery_wish("hybrid packages") is True


def test_chat_shows_real_packages_on_request_and_after_the_analysis(client):
    cid = "pkg-conv-0001-0123456789"
    reply(client, "I want to install solar", cid=cid)
    r = reply(client, "Compare on-grid and hybrid solar packages", cid=cid)["reply"]
    card = next(c for c in r["cards"] if c["type"] == "packages")["data"]
    assert card["open"] is True and len(card["rows"]) >= 20 and "side panel" in r["text"] and "not quotes" in r["text"]
    assert any(n["text"].startswith("Show real packages") for n in r["next"])


def test_samples_only_fill_gaps_and_are_always_labeled():
    covered = market_packages.match(6.2, "hybrid", "NCR")  # plenty of real hybrid packages at this size
    assert not any(p["synthetic"] for p in covered["rows"][:1]) and covered["rows"][0]["synthetic"] is False
    off = market_packages.match(5.0, "off-grid", "NCR")  # nobody publishes off-grid packages
    assert off["found"] and off["all_sample"] and all(p["type"] == "off-grid" for p in off["rows"])
    md = market_packages.table_markdown(off)
    assert "made-up samples" in md and "*Sample* (made-up)" in md and "not offers" in md
    gap = market_packages.match(7.0, "grid-tied", "NCR")  # real grid-tied packages are 5 kWp or 10 kWp, both over 25% away
    assert any(p["synthetic"] for p in gap["rows"]) and any(not p["synthetic"] for p in gap["rows"])
    assert "Rows marked Sample are invented" in market_packages.table_markdown(gap)


def test_panel_lists_everything_real_first_with_the_wanted_type_leading():
    r = market_packages.panel(6.2, "hybrid", "NCR")
    rows = r["rows"]
    assert len(rows) >= 25 and r["in_your_area"] and all("NCR" in p["regions"] for p in rows)
    assert [p["synthetic"] for p in rows] == sorted(p["synthetic"] for p in rows)
    real = [p for p in rows if not p["synthetic"]]
    assert real[0]["type"] == "hybrid" and abs(real[0]["kwp"] - 6.2) < 0.2
    assert market_packages.panel(None, None, None)["rows"]  # no size or area yet still lists everything


def test_find_matches_a_package_by_name_and_installer():
    p = market_packages.find("Tell me more about the 6kW System from PTG Solar")
    assert p and p["installer"] == "PTG Solar" and p["name"] == "6kW System"
    assert market_packages.find("tell me more about the 6KW Hybrid System by Skyelight Solar")["installer"] == "Skyelight Solar"  # same name, other installer
    assert market_packages.find("Tell me more about the Sample off-grid 5 kWp package")["synthetic"] is True
    assert market_packages.find("what is the weather") is None


def test_every_real_installer_has_published_contacts():
    d = json.loads(market_packages.DATA.read_text(encoding="utf-8"))
    for p in d["packages"]:
        if p["synthetic"]:
            assert p["contact"] is None
        else:
            c = p["contact"]
            assert c and (c.get("phones") or c.get("emails")), p["installer"]


def test_details_have_price_fit_contacts_and_questions():
    p = market_packages.find("6kW System PTG Solar")
    md = market_packages.details_markdown(p, budget_max=300000, wanted_kwp=3.0, basis="usage", system_kind="grid-tied", registry="not listed")
    assert "### 6kW System · PTG Solar" in md and "₱237,912" in md and "Within your budget of up to ₱300,000" in md
    assert "Bigger than the rough size for your usage" in md and "Different from your grid-tied choice" in md
    assert "**Contact PTG Solar**" in md and "+63 966 552 5258" in md and "quotes@ptgsolarph.com" in md and "](https://ptgsolarph.com/)" in md
    assert "Before you call, ask" in md and "not a quote" in md and "DOE registry: not listed" in md
    over = market_packages.details_markdown(market_packages.find("Premium 10 kWp Triple30"), budget_max=300000)
    assert "over your budget" in over
    fake = market_packages.details_markdown(market_packages.find("Sample off-grid 5 kWp"))
    assert "made-up sample" in fake and "Contact" not in fake


def test_chat_gives_package_details_with_contacts_when_asked(client):
    cid = "info-conv-0001-0123456789"
    for m in ["I want to install solar", "reyes demo", "Yes, use 450 kWh per month", "I want a grid-tied (on-grid) system", "My budget is ₱150,000 to ₱300,000"]:
        reply(client, m, cid=cid)
    r = reply(client, "Tell me more about the 6kW System from PTG Solar", cid=cid)["reply"]
    assert "### 6kW System · PTG Solar" in r["text"] and "+63 966 552 5258" in r["text"] and "Within your budget" in r["text"]
    assert "not a quote" in r["text"] and any(n["text"] == "What should I ask an installer?" for n in r["next"])
    assert "Installation site:" not in r["text"] and "Tap Run the numbers" not in r["text"]  # no summary recap while reading one package
    s = reply(client, "Tell me more about the Sample off-grid 3 kWp package", cid=cid)["reply"]
    assert "made-up" in s["text"] and "Contact PTG" not in s["text"]
