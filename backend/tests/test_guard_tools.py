import httpx
import pytest

from app.config import get_settings
from app.services import geo
from app.services.agent import guard, intake
from app.services.agent.session import load_session
from app.services.agent.tools import TurnContext, jsonable


def allowed(*sources):
    return guard.Allowed(list(sources))


# ---- guard ----------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("text", [
    "Your bill is about ₱6,780 a month.",          # 6777.68 rounded to tens
    "That is roughly 7k a month.",                 # k-rounding
    "Payback is about 5 years.",                   # 5.2 rounded
    "You could cut the bill by 52%.",              # 51.6 rounded
    "Over the 25-year life and a 10-year view.",   # projection constants
    "I have two options and 3 questions.",         # bare small counts
    "As of 2026 the rate is ₱15.06 per kWh.",      # a year and a sourced rate
    "About 1.2 million pesos over 25 years.",
])
def test_guard_passes_traceable_text(text):
    a = allowed({"bill": 6777.68, "payback": 5.2, "cut": 51.6, "rate": 15.0615, "profit": 1_200_000, "x": 450})
    assert guard.check_text(text, a) == []


@pytest.mark.parametrize("text,fragment", [
    ("Your bill is about ₱7,500 a month.", "7,500"),
    ("Payback is about 9 years.", "9"),
    ("You will save 80% on your bill.", "80"),
    ("The system is 12.5 kWp.", "12.5"),
    ("That costs ₱250,000 installed.", "250,000"),
    ("About 3 million pesos.", "3 million"),
])
def test_guard_blocks_invented_numbers(text, fragment):
    a = allowed({"bill": 6777.68, "payback": 5.2, "cut": 51.6, "kwp": 4.4, "capex": 180000, "profit": 1_200_000})
    bad = guard.check_text(text, a)
    assert bad and any(fragment in b for b in bad)


def test_guard_collects_numbers_from_strings_and_nested_results():
    a = allowed({"panel": "DemoSolar DS-550M (550 W)", "list": [{"v": 1234.5}]})
    assert guard.check_text("A 550 W panel, around 1,234 kWh.", a) == []


# ---- tools -----------------------------------------------------------------------------------------------------------
def make_ctx(persona="reyes", text=""):
    s = load_session("conv-tools-001-0123456789", persona, "english")
    events = []
    ctx = TurnContext(s, text, "english", [], events.append, get_settings())
    return ctx, events


def ready_session(ctx):
    r = geo.roof_from_address(14.676, 121.0437)  # synthetic demo roof
    s = ctx.session
    s.profile.roof, s.profile.roof_method = r.model_dump(mode="json"), "address"
    intake.apply_updates(s, confirm_load=True, budget_max_php=450000, goal="cut_bill", goal_target_pct=40, confirm_summary=True)
    assert intake.next_slot(s) == "run"


def test_call_cap_unknown_tool_and_bad_args():
    ctx, events = make_ctx()
    assert ctx.call_tool("nope", {})["error"] == "unknown_tool"
    assert ctx.call_tool("update_profile", {"monthly_kwh": "abc"})["error"] == "invalid_arguments"
    for _ in range(10):
        ctx.call_tool("update_profile", {"net_metering": True})
    assert ctx.calls_made == get_settings().max_tool_calls
    assert ctx.call_tool("update_profile", {})["error"] == "tool_call_limit"
    steps = [e["data"] for e in events if e["event"] == "step"]
    ids = [s["id"] for s in steps]
    assert len(set(ids)) == len(ids) / 2  # every step id appears exactly twice: running then done


def test_tool_bug_does_not_crash_the_turn(monkeypatch):
    from app.services.agent import tools

    def boom(ctx, a):
        raise RuntimeError("bug")

    monkeypatch.setitem(tools.TOOLS, "update_profile", tools.Tool("update_profile", "x", tools.UpdateProfileArgs, boom, "Saving"))
    ctx, _ = make_ctx()
    assert ctx.call_tool("update_profile", {})["error"] == "tool_failed"


def test_cancelled_turn_stops_calling_tools():
    ctx, _ = make_ctx()
    ctx.cancelled.set()
    assert ctx.call_tool("update_profile", {})["error"] == "cancelled" and ctx.calls_made == 0


def test_geocode_single_candidate_auto_selects_and_sets_roof():
    ctx, _ = make_ctx()
    out = ctx.call_tool("geocode_address", {"query": "reyes demo"})
    assert out["auto_selected"] and out["found"] and out["roof"]["area_m2"] == pytest.approx(88, rel=0.02)
    assert ctx.session.profile.roof and ctx.flags["open_map"] is True
    assert ctx.session.pending["anchor"]["lat"] == pytest.approx(14.676, abs=0.01)


def test_geocode_multiple_candidates_then_pick(monkeypatch):
    items = [{"display_name": "A Street, Quezon City", "lat": "14.6760", "lon": "121.0437"},
             {"display_name": "B Street, Quezon City", "lat": "14.5764", "lon": "121.0851"}]
    monkeypatch.setattr(geo, "client_factory", lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json=items))))
    ctx, _ = make_ctx()
    out = ctx.call_tool("geocode_address", {"query": "street quezon city"})
    assert len(out["candidates"]) == 2 and out["next_slot"] == "roof_pick"
    assert intake.match_choice(ctx.session, "Use A Street, Quezon City") == {"kind": "pick", "payload": 0}
    assert ctx.call_tool("get_building_outline", {"candidate_index": 9})["error"] == "invalid_candidate"


def test_outline_failure_switches_to_drawing(monkeypatch):
    monkeypatch.setattr(geo, "client_factory", lambda: httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={"elements": []}))))
    ctx, _ = make_ctx()
    out = ctx.call_tool("get_building_outline", {"lat": 14.9, "lon": 121.9})
    assert out["found"] is False and out["next_slot"] == "roof_draw" and ctx.flags["open_map"]
    assert ctx.session.profile.roof_method == "draw"


def test_run_analysis_requires_complete_inputs_then_runs():
    ctx, _ = make_ctx()
    assert ctx.call_tool("run_analysis", {})["error"] == "not_ready"
    ready_session(ctx)
    out = ctx.call_tool("run_analysis", {})
    assert "summary" in out and out["next_slot"] == "done"
    top = out["summary"]["packages"][0]
    assert top["capex_php"] <= 450000 and top["panel_count"] >= 2
    assert ctx.session.results["analysis"]["selected_index"] == 0
    assert any(c["type"] == "analysis" for c in ctx.cards)


def test_compare_net_metering_and_what_if_credit():
    ctx, _ = make_ctx()
    assert ctx.call_tool("compare_net_metering", {})["error"] == "not_ready"
    ready_session(ctx)
    ctx.call_tool("run_analysis", {})
    base = ctx.call_tool("compare_net_metering", {})
    assert base["net_metering_on"]["net_profit_25y_php"]["expected"] >= base["net_metering_off"]["net_profit_25y_php"]["expected"]
    low = ctx.call_tool("compare_net_metering", {"export_credit_php_per_kwh": 1.0})
    assert low["export_credit_php_per_kwh"] == 1.0
    assert low["net_metering_on"]["net_profit_25y_php"]["expected"] <= base["net_metering_on"]["net_profit_25y_php"]["expected"]
    ctx.calls_made = 0  # the per-turn cap is tested separately
    assert ctx.call_tool("compare_net_metering", {"package_index": 99})["error"] == "invalid_package"
    assert ctx.call_tool("compare_net_metering", {"export_credit_php_per_kwh": 99})["error"] == "invalid_arguments"


def test_explain_assumptions_topics():
    ctx, _ = make_ctx()
    net = ctx.call_tool("explain_assumptions", {"topic": "net metering"})
    keys = {a["key"] for a in net["assumptions"]}
    assert "export_credit_php_per_kwh" in keys and any("banked" in f for f in net["facts"])
    allr = ctx.call_tool("explain_assumptions", {})
    assert allr["count"] > 20 and all({"unit", "source_url", "as_of", "verified"} <= set(a) for a in allr["assumptions"])


def test_passport_tool_needs_analysis_and_returns_verifiable_id():
    ctx, _ = make_ctx()
    assert ctx.call_tool("issue_passport", {})["error"] == "not_ready"
    ready_session(ctx)
    ctx.call_tool("run_analysis", {})
    out = ctx.call_tool("issue_passport", {})
    assert out["id"].startswith("SOL-") and out["checks_at_issue"]["reproducible"] == "pass"


def test_record_bill_reading_validates_and_does_not_touch_profile():
    ctx, _ = make_ctx()
    assert ctx.call_tool("record_bill_reading", {})["recorded"] is False
    assert ctx.call_tool("record_bill_reading", {"kwh": 99999})["recorded"] is False
    ok = ctx.call_tool("record_bill_reading", {"kwh": 420, "amount_php": 6500})
    assert ok["recorded"] and ctx.session.pending["bill_read"]["kwh"] == 420
    assert ctx.session.profile.monthly_kwh == 450


def test_search_products_reports_demo_fallback():
    ctx, _ = make_ctx()
    out = ctx.call_tool("search_products", {})
    assert out["found_live"] == 0 and out["freshness_counts"]["seed"] >= 10 and "confirm with the seller" in out["message"].lower()


def test_jsonable_handles_numpy():
    import numpy as np

    out = jsonable({"a": np.float64(1.5), "b": np.arange(3), "c": [np.int64(2)]})
    assert out == {"a": 1.5, "b": [0, 1, 2], "c": [2]}
