"""Usage limits that agree everywhere, and several requests in one message (scripted agent, fully offline)."""
from __future__ import annotations

import pytest

from app.db import get_repo
from app.services import limits
from app.services.agent import intake, nlu
from app.services.agent.session import Session, save_session
from app.services.agent.tools import _user_agreed
from test_agent_flow import CID, reply, texts
from test_guard_tools import make_ctx, ready_session


def to_confirm(client):
    """Walk the chat to the summary question (Reyes demo roof, 450 kWh, on-grid, budget, cut the bill by 50%)."""
    for msg in ["hi", "reyes demo", "Yes, use 450 kWh per month", "I want a grid-tied (on-grid) system",
                "My budget is ₱300,000 to ₱500,000", "I want to cut my electricity bill", "Cut my bill by 50%"]:
        m = reply(client, msg)
    assert m["reply"]["slot"] == "confirm"
    return m


def profile(client):
    return client.get(f"/api/agent/sessions/{CID}").json()["profile"]


def stored_session() -> Session:
    return Session.model_validate(get_repo().get_session(CID))


# ---- one set of limits ------------------------------------------------------------------------------------------
def test_bill_limit_follows_the_kwh_limit():
    lo, hi = limits.bill_limits_php()
    assert intake._bill_problem(hi - 1) is None and intake._bill_problem(lo + 1) is None
    assert "above" in intake._bill_problem(hi + 100)
    assert "below" in intake._bill_problem(lo - 10)


def test_too_big_bill_is_refused_immediately_with_the_real_limits(client):
    to_confirm(client)
    m = reply(client, "my monthly bill is 93000")
    text = m["reply"]["text"]
    assert "6,175 kWh" in text and "5,000" in text and "I couldn't use that" in text
    assert profile(client)["monthly_kwh"] == 450  # nothing was overwritten
    assert m["reply"]["slot"] == "confirm"  # and it did not run on a bad value


def test_usage_that_cannot_be_sized_opens_the_change_menu_instead_of_looping(client):
    to_confirm(client)
    s = stored_session()  # simulate a value that got past the checks, e.g. an old saved profile
    s.profile.monthly_kwh, s.profile.monthly_bill_php = 6175.0, None
    save_session(s)
    m = reply(client, "Yes, run the numbers")
    r = m["reply"]
    assert "outside the supported range" in r["text"] and "5,000" in r["text"]
    assert r["slot"] == "change"
    assert "Change my bill" in texts(m) and "Yes, run the numbers" not in texts(m)


def test_signup_and_chat_use_the_same_minimum(anon_client):
    from conftest import TEST_USER

    r = anon_client.post("/api/auth/signup", json={**TEST_USER, "monthly_kwh": limits.KWH_MIN - 1})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_kwh"


# ---- reading the message --------------------------------------------------------------------------------------------
def test_monthly_amount_is_a_bill():
    assert nlu.extract("the monthly is now 34k and make run the numbers", "confirm", None) == {"monthly_bill_php": 34000.0}
    assert nlu.extract("my monthly budget is 300k", "budget", None)["budget_max_php"] == 300000.0


@pytest.mark.parametrize("text,expected", [
    ("run the numbers", ["run"]),
    ("run the numbers and compare net metering", ["run", "nm_compare"]),
    ("create my passport, compare net metering and run the analysis", ["run", "nm_compare", "passport"]),  # always dependency order
    ("compare packages", ["run"]),
    ("don't run the numbers yet", []),
    ("what is net metering?", []),
])
def test_requested_actions_come_back_in_a_safe_order(text, expected):
    assert nlu.requested_actions(text) == expected


def test_llm_confirmation_inside_a_run_request_is_accepted_but_not_otherwise():
    ctx, _ = make_ctx(text="the monthly is now 34k and run the numbers")
    assert _user_agreed(ctx) is True
    ctx, _ = make_ctx(text="the monthly is now 34k")
    assert _user_agreed(ctx) is False
    ctx, _ = make_ctx(text="don't run the numbers yet, my bill is 34k")
    assert _user_agreed(ctx) is False


# ---- several requests, one message ---------------------------------------------------------------------------------
def test_new_value_and_run_in_one_message(client):
    to_confirm(client)
    m = reply(client, "the monthly is now 34k and make run the numbers")
    assert m["reply"]["slot"] == "done"
    assert profile(client)["monthly_bill_php"] == 34000
    assert any(c["type"] == "analysis" for c in m["reply"]["cards"])
    labels = [s["label"] for s in m["steps"]]
    assert labels.index("Saving your details") < labels.index("Running the numbers")  # details first, then the run


def test_run_and_follow_ups_in_one_message(client):
    to_confirm(client)
    m = reply(client, "run the numbers, compare net metering and create my passport")
    kinds = {c["type"] for c in m["reply"]["cards"]}
    assert {"analysis", "passport"} <= kinds
    text = m["reply"]["text"]
    assert "without it" in text.lower() and "SOL-" in text
    labels = [s["label"] for s in m["steps"]]
    assert labels.index("Running the numbers") < labels.index("Comparing net metering")


def test_a_failed_step_stops_the_chain_and_the_rest_waits(client):
    to_confirm(client)
    m = reply(client, "my bill is 93000, run the numbers and compare net metering")
    r = m["reply"]
    assert "I couldn't use that" in r["text"] and "stopped" in r["text"].lower()
    assert not any(c["type"] == "analysis" for c in r["cards"])
    assert not any(s["label"] == "Running the numbers" for s in m["steps"])  # nothing ran on the bad value
    assert stored_session().pending.get("queued") == ["nm_compare"]

    # the user fixes the value, confirms, and the waiting request is finished by itself
    reply(client, "my monthly bill is 20000")
    m = reply(client, "Yes, run the numbers")
    assert any(c["type"] == "analysis" for c in m["reply"]["cards"])
    assert "without it" in m["reply"]["text"].lower()
    assert stored_session().pending.get("queued") is None


def test_missing_details_are_asked_for_and_the_request_is_remembered(client):
    reply(client, "hi")
    reply(client, "reyes demo")
    m = reply(client, "Yes, use 450 kWh per month")
    assert m["reply"]["slot"] == "system_type"
    m = reply(client, "run the numbers and compare net metering")
    assert "can't run the numbers yet" in m["reply"]["text"] and m["reply"]["slot"] == "system_type"
    assert not any(c["type"] == "analysis" for c in m["reply"]["cards"])
    assert stored_session().pending.get("queued") == ["nm_compare"]

    for msg in ["I want a grid-tied (on-grid) system", "My budget is ₱300,000 to ₱500,000", "I want to cut my electricity bill", "Cut my bill by 50%"]:
        reply(client, msg)
    m = reply(client, "Yes, run the numbers")
    assert "without it" in m["reply"]["text"].lower()


def test_cancel_drops_waiting_requests(client):
    to_confirm(client)
    reply(client, "my bill is 93000 and compare net metering and run the numbers")
    assert stored_session().pending.get("queued")
    m = reply(client, "never mind")
    assert stored_session().pending.get("queued") is None and "dropped" in m["reply"]["text"]


def test_run_command_in_the_change_menu_still_leaves_the_menu(client):
    to_confirm(client)
    reply(client, "I want to change something")
    m = reply(client, "just run the numbers")
    assert m["reply"]["slot"] == "done"


def test_asking_again_when_numbers_exist_does_not_rerun(client):
    to_confirm(client)
    reply(client, "Yes, run the numbers")
    m = reply(client, "run the numbers")
    assert not any(s["label"] == "Running the numbers" for s in m["steps"])
    assert "up to date" in m["reply"]["text"]
