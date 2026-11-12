import json
import time

import pytest

from app.services.agent import runner
from app.services.agent.providers import FakeProvider, ProviderUnavailable

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
CID = "conv-test-0001-0123456789"


def say(client, text="", cid=CID, **extra):
    data = {"conversation_id": cid, "message": text, "language": extra.pop("language", "auto")}
    r = client.post("/api/agent/chat?stream=false", data=data, **extra)
    return r


def reply(client, text, cid=CID, **kw):
    r = say(client, text, cid, **kw)
    assert r.status_code == 200, r.text
    return r.json()


def texts(msg):
    return [n["text"] for n in msg["reply"]["next"]]


# ---- first contact -----------------------------------------------------------------------------------------
def test_first_message_greets_and_offers_two_roof_choices(client):
    msg = reply(client, "I want to install solar")
    assert msg["phase"] == "done" and msg["conversationId"] == CID
    assert msg["steps"][0]["id"] == "s0" and all(s["status"] == "done" for s in msg["steps"])
    r = msg["reply"]
    assert "Sol" in r["text"] and "installation site" in r["text"].lower() and "estimate" in r["text"].lower()
    assert len(r["next"]) == 2 and r["hasMapArtifact"] is False
    assert {"id", "label", "text"} <= set(r["next"][0])
    assert texts(msg) == ["I'll draw my installation site on the map", "I'll sketch my installation site on a blank canvas"]
    assert "address" not in " ".join(texts(msg)).lower() and "search box" in r["text"]  # no typed-address option; the map has the search


def test_reply_shape_matches_frontend_types(client):
    msg = reply(client, "hello")
    assert set(msg["reply"]) >= {"text", "hasMapArtifact", "next"}
    assert isinstance(msg["reply"]["text"], str) and isinstance(msg["reply"]["hasMapArtifact"], bool)
    for step in msg["steps"]:
        assert set(step) == {"id", "label", "status"} and step["status"] in ("running", "done")


def test_taglish_language_is_honoured(client):
    msg = reply(client, "gusto ko po mag solar", language="taglish")
    assert "Ako si Sol" in msg["reply"]["text"]


# ---- the whole conversation, offline ---------------------------------------------------------------------------
def test_full_conversation_from_vague_request_to_passport(client):
    reply(client, "I want to install solar")
    m = reply(client, "reyes demo")  # a named synthetic demo site loads straight away (no address step any more)
    assert m["reply"]["hasMapArtifact"] is True
    assert "88" in m["reply"]["text"] and "kWh" in m["reply"]["text"]  # roof area, then the usage question
    assert any(n["text"] == "Yes, use 450 kWh per month" for n in m["reply"]["next"])
    assert any(c["type"] == "roof" for c in m["reply"]["cards"])

    m = reply(client, "Yes, use 450 kWh per month")
    assert m["reply"]["slot"] == "system_type" and "Off-grid" in m["reply"]["text"] and "**Hybrid" in m["reply"]["text"]
    assert [n["label"] for n in m["reply"]["next"]] == ["Grid-tied (on-grid)", "Off-grid", "Hybrid (solar + storage)"]

    m = reply(client, "I want a grid-tied (on-grid) system")
    assert "budget" in m["reply"]["text"].lower() and len(m["reply"]["next"]) == 4

    m = reply(client, "My budget is ₱300,000 to ₱500,000")
    txt = m["reply"]["text"]
    assert m["reply"]["slot"] == "confirm" and "Budget: ₱300,000 to ₱500,000." in txt and "biggest 10-year savings" in txt
    assert "?" not in txt and "What matters most" not in txt  # a summary, not a question
    assert "Run the numbers" in [n["label"] for n in m["reply"]["next"]]

    m = reply(client, "I want to cut my electricity bill")  # choosing a goal is still possible
    assert m["reply"]["slot"] == "goal_param"
    m = reply(client, "Cut my bill by 50%")
    assert m["reply"]["slot"] == "confirm" and "Goal: cut your bill by 50%." in m["reply"]["text"] and "biggest 10-year savings" not in m["reply"]["text"]

    m = reply(client, "Yes, run the numbers")
    r = m["reply"]
    assert r["slot"] == "done"
    assert "payback" in r["text"].lower() and "licensed installer" in r["text"] and "₱" in r["text"]
    assert any(c["type"] == "analysis" for c in r["cards"])
    assert any(s["label"] == "Running the numbers" for s in m["steps"])
    summary = next(c for c in r["cards"] if c["type"] == "analysis")["data"]
    top = summary["packages"][0]
    assert top["capex_php"] <= 500_000
    assert top["payback_years"]["best_case"] is None or top["payback_years"]["bad_year"] is None or top["payback_years"]["best_case"] <= top["payback_years"]["bad_year"]
    assert "Create my Solar Passport" in texts(m)
    assert "Can I export my plan?" in texts(m)  # the export is offered as a pill once there is something to export

    ex = client.get(f"/api/agent/sessions/{CID}/export?package_index=0")
    assert ex.status_code == 200 and ex.headers["content-type"] == "application/pdf" and ".pdf" in ex.headers["content-disposition"]
    assert ex.content.startswith(b"%PDF") and ex.content.count(b"/Type /Page\n") >= 1
    from app.db import get_repo
    from app.services import export as export_svc
    from app.services.agent.session import Session

    sess = Session.model_validate(get_repo().get_session(CID))
    d = export_svc.plan_data(sess, 0)
    area = dict(d["area"])
    assert area["Roof area"].startswith("88") and dict(d["inputs"])["Budget"] == "₱300,000 to ₱500,000" and "cut your bill by 50%" in dict(d["inputs"])["Goal"]
    assert dict(d["chosen"])["Solar panels"].startswith(f"{top['panel_count']} ×") and dict(d["chosen"])["Installed cost"] == f"₱{round(top['capex_php']):,}"
    assert "10-year net profit" in dict(d["numbers"]) and "25-year" not in str(d) and "25 years" not in str(d)
    raw = export_svc.plan_pdf(sess, 0, compress=False)[1]  # uncompressed, so the text can be found in the file itself
    assert b"Installation area" in raw and b"10 years" in raw
    assert client.get(f"/api/agent/sessions/{CID}/export?package_index=9").status_code == 422

    m = reply(client, "can i export my details")  # asked in chat: a download card, not "I didn't catch that"
    assert "didn't catch" not in m["reply"]["text"] and "ready" in m["reply"]["text"]
    card = next(c for c in m["reply"]["cards"] if c["type"] == "export")["data"]
    assert card["package_index"] == 0 and card["label"] == top["label"]

    m = reply(client, "Tell me more about Starter 3 kWp from Triple30 Renewables")  # picking a package offers the export too
    assert any(c["type"] == "export" for c in m["reply"]["cards"])
    sess = Session.model_validate(get_repo().get_session(CID))
    picked = export_svc.plan_data(sess, 0)["picked"]
    assert picked and dict(picked["rows"])["Package"] == "Starter 3 kWp" and dict(picked["rows"])["From"] == "Triple30 Renewables"

    m = reply(client, "What if net metering is off?")
    assert "without it" in m["reply"]["text"].lower()

    m = reply(client, "Create my Solar Passport")
    assert "SOL-" in m["reply"]["text"]
    pid = next(c for c in m["reply"]["cards"] if c["type"] == "passport")["data"]["id"]
    ver = client.get(f"/api/passport/{pid}/verify").json()
    assert ver["valid"] is True
    assert "Verified" in client.get(f"/verify/{pid}").text

    state = client.get(f"/api/agent/sessions/{CID}").json()
    assert state["nextSlot"] == "done" and state["passport"]["id"] == pid
    roof = client.get(f"/api/agent/sessions/{CID}/roof").json()
    assert roof["roof"]["area_m2"] == pytest.approx(88, rel=0.02)
    assert roof["layout"]["count"] == top["panel_count"] and len(roof["layout"]["panels_lonlat"]) == top["panel_count"]


def test_several_answers_in_one_message(client):
    reply(client, "hi")
    reply(client, "reyes demo")  # roof via address even from the first question
    m = reply(client, "use 450 kWh a month, my budget is 300k, I want the fastest payback")
    st = client.get(f"/api/agent/sessions/{CID}").json()["profile"]
    assert st["monthly_kwh"] == 450 and st["budget_max_php"] == 300000 and st["goal"] == "fastest_payback"
    assert m["reply"]["slot"] == "system_type"  # everything else was understood; only the system type is missing


def test_details_given_in_passing_are_saved_and_acknowledged(client):
    reply(client, "hi, I want to install solar panels but I'm not sure where to start")
    m = reply(client, "I live in Quezon City, my monthly bill is around 7000 pesos and I have about 400k to spend")
    p = client.get(f"/api/agent/sessions/{CID}").json()["profile"]
    assert p["monthly_bill_php"] == 7000 and p["budget_max_php"] == 400000 and p["load_confirmed"] is True
    text = m["reply"]["text"]
    assert "7,000" in text and "400,000" in text  # it says what it understood...
    assert m["reply"]["slot"] == "roof_method" and len(m["reply"]["next"]) == 2  # ...and still asks about the roof


def test_address_typed_at_the_first_question_is_understood(client):
    m = reply(client, "My house is at reyes demo, Quezon City")
    assert client.get(f"/api/agent/sessions/{CID}").json()["profile"]["roof"] is not None


def test_a_typed_address_points_to_the_map_search_box(client):
    reply(client, "I want to install solar")
    m = reply(client, "999 Nowhere Street, Atlantis")
    assert "search box" in m["reply"]["text"].lower() and m["reply"]["slot"] == "roof_draw" and m["reply"]["hasMapArtifact"] is True
    assert client.get(f"/api/agent/sessions/{CID}").json()["profile"]["roof"] is None  # nothing was looked up


def test_unrecognised_input_re_asks_without_losing_state(client):
    reply(client, "hello")
    m = reply(client, "asdf qwer")
    assert "didn't catch" in m["reply"]["text"].lower()
    assert m["reply"]["slot"] == "roof_method" and len(m["reply"]["next"]) == 2


def test_invalid_values_are_rejected_with_a_helpful_message(client):
    reply(client, "reyes demo")
    reply(client, "Yes, use 450 kWh per month")
    reply(client, "I want a grid-tied (on-grid) system")
    m = reply(client, "my budget is 5k")
    assert "too low" in m["reply"]["text"].lower()
    assert client.get(f"/api/agent/sessions/{CID}").json()["profile"]["budget_max_php"] is None


def test_change_something_flow(client):
    reply(client, "reyes demo")
    reply(client, "Yes, use 450 kWh per month")
    reply(client, "I want a grid-tied (on-grid) system")
    reply(client, "My budget is ₱150,000 to ₱300,000")
    reply(client, "I want the fastest payback")
    m = reply(client, "I want to change something")
    assert len(m["reply"]["next"]) == 5 and m["reply"]["slot"] == "change"
    m = reply(client, "Change my budget")
    assert m["reply"]["slot"] == "budget"


def test_infeasible_budget_is_explained_not_crashed(client):
    reply(client, "reyes demo")
    reply(client, "Yes, use 450 kWh per month")
    reply(client, "I want a grid-tied (on-grid) system")
    reply(client, "my budget is 30000")
    reply(client, "I want to cut my electricity bill")
    reply(client, "Cut my bill by 70%")
    m = reply(client, "Yes, run the numbers")
    assert "could not find a design" in m["reply"]["text"].lower() or "couldn't do that" in m["reply"]["text"].lower()
    assert m["reply"]["next"]  # still offers a way forward


# ---- streaming ------------------------------------------------------------------------------------------------------
def parse_sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        if block.startswith(":"):
            continue
        ev = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((ev["event"], json.loads(ev["data"])))
    return events


def test_sse_event_order_and_stable_step_ids(client):
    r = client.post("/api/agent/chat", data={"conversation_id": CID, "message": "reyes demo", "language": "auto"})
    assert r.headers["content-type"].startswith("text/event-stream")
    evs = parse_sse(r.text)
    names = [e[0] for e in evs]
    assert names[0] == "turn" and names[-2:] == ["reply", "done"]
    steps = [e[1] for e in evs if e[0] == "step"]
    ids = [s["id"] for s in steps]
    assert ids[0] == "s0" and set(ids) == set(ids)
    for sid in set(ids):
        seq = [s["status"] for s in steps if s["id"] == sid]
        assert seq == ["running", "done"]
    assert evs[-2][1]["text"]


def test_stream_false_matches_streamed_final_payload(client):
    a = client.post("/api/agent/chat", data={"conversation_id": "conv-aaaa-0001-0123456789", "message": "I want to install solar"}).text
    b = client.post("/api/agent/chat?stream=false", data={"conversation_id": "conv-bbbb-0001-0123456789", "message": "I want to install solar"}).json()
    streamed = [e for e in parse_sse(a) if e[0] == "reply"][0][1]
    assert streamed["text"] == b["reply"]["text"] and streamed["next"] == b["reply"]["next"]


# ---- request validation --------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("data,code", [
    ({"conversation_id": "x", "message": "hi"}, "invalid_conversation_id"),
    ({"conversation_id": CID, "message": "hi", "language": "klingon"}, "invalid_language"),
    ({"conversation_id": CID, "message": "   "}, "empty_message"),
    ({"conversation_id": CID, "message": "x" * 4001}, "message_too_long"),
])
def test_bad_requests(client, data, code):
    r = client.post("/api/agent/chat?stream=false", data=data)
    assert r.status_code == 422 and r.json()["detail"]["code"] == code


def test_missing_conversation_id_uses_error_shape(client):
    r = client.post("/api/agent/chat?stream=false", data={"message": "hi"})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_request"


def test_busy_conversation_returns_409_before_streaming(client):
    token = runner.LOCKS.acquire(CID, 60)
    assert token
    r = client.post("/api/agent/chat", data={"conversation_id": CID, "message": "hi"})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "turn_in_progress"
    runner.LOCKS.release(CID, token)
    assert client.post("/api/agent/chat?stream=false", data={"conversation_id": CID, "message": "hi"}).status_code == 200


def test_stale_lock_is_recovered():
    token = runner.LOCKS.acquire(CID, 0.05)
    time.sleep(0.1)
    assert runner.LOCKS.acquire(CID, 0.05)  # old holder is considered stuck
    assert token


# ---- attachments ------------------------------------------------------------------------------------------------------------
def test_attachment_in_scripted_mode_explains_limit_and_keeps_going(client):
    m = reply(client, "Attached files", files=[("files", ("bill.png", PNG, "image/png"))])
    assert "can't read photos" in m["reply"]["text"].lower() and m["reply"]["next"]


def test_files_only_message_is_accepted(client):
    r = client.post("/api/agent/chat?stream=false", data={"conversation_id": CID, "message": ""},
                    files=[("files", ("bill.png", PNG, "image/png"))])
    assert r.status_code == 200


def test_bad_attachments_rejected(client):
    r = client.post("/api/agent/chat?stream=false", data={"conversation_id": CID, "message": "x"},
                    files=[("files", ("a.exe", b"MZ\x90\x00", "image/png"))])
    assert r.status_code == 415 and r.json()["detail"]["code"] == "unsupported_file_type"
    many = [("files", (f"{i}.png", PNG, "image/png")) for i in range(7)]
    r = client.post("/api/agent/chat?stream=false", data={"conversation_id": CID, "message": "x"}, files=many)
    assert r.status_code == 422 and r.json()["detail"]["code"] == "too_many_files"


def test_oversize_attachment_rejected(client, monkeypatch):
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "100")
    from app.config import get_settings

    get_settings.cache_clear()
    r = client.post("/api/agent/chat?stream=false", data={"conversation_id": CID, "message": "x"},
                    files=[("files", ("big.png", PNG + b"\x00" * 200, "image/png"))])
    assert r.status_code == 413


def test_uploaded_files_are_not_persisted(client, tmp_path):
    reply(client, "see photo", files=[("files", ("bill.png", PNG, "image/png"))])
    state = json.dumps(client.get(f"/api/agent/sessions/{CID}").json())
    assert "PNG" not in state and "bill.png" not in state
    assert not list(tmp_path.glob("*.png"))


# ---- provider failures ------------------------------------------------------------------------------------------------------
def test_llm_unavailable_falls_back_to_scripted_with_a_step(client):
    runner.set_provider_override(FakeProvider([("raise", ProviderUnavailable("429"))]))
    m = reply(client, "I want to install solar")
    assert "Sol" in m["reply"]["text"] and len(m["reply"]["next"]) == 2
    assert any(s["label"] == "Switching to quick mode" for s in m["steps"])


def test_provider_crash_still_returns_a_reply(client):
    runner.set_provider_override(FakeProvider([("raise", RuntimeError("boom"))]))
    m = reply(client, "hello")
    assert m["reply"]["text"] and m["phase"] == "done"
    assert m["reply"]["next"]  # choices still present


def test_turn_timeout_returns_reply_and_frees_the_session(client, monkeypatch):
    monkeypatch.setenv("TURN_TIMEOUT_S", "0.4")
    from app.config import get_settings

    get_settings.cache_clear()
    runner.set_provider_override(FakeProvider([("sleep", 1.0), ("text", "late")]))
    m = reply(client, "hello")
    assert "too long" in m["reply"]["text"].lower()
    runner.set_provider_override(None)
    for _ in range(40):  # the abandoned worker releases the lock when it finishes
        r = say(client, "hello again")
        if r.status_code == 200:
            break
        time.sleep(0.1)
    assert r.status_code == 200


# ---- number guard ----------------------------------------------------------------------------------------------------------------
def test_guard_replaces_text_with_untraceable_numbers(client):
    runner.set_provider_override(FakeProvider([("tool", "update_profile", {"monthly_kwh": 450}),
                                               ("text", "Great, your savings will be ₱99,999 every month!")]))
    m = reply(client, "I use 450 kWh")
    assert "99,999" not in m["reply"]["text"]
    state = client.get(f"/api/agent/sessions/{CID}").json()
    assert state["guardEvents"] and "99,999" in state["guardEvents"][0]["untraced"][0]


def test_guard_allows_numbers_from_tool_results_and_user(client):
    runner.set_provider_override(FakeProvider([("tool", "update_profile", {"monthly_kwh": 450}),
                                               ("text", "Thanks, I noted about 450 kWh a month. Which roof will we use?")]))
    m = reply(client, "I use 450 kWh")
    assert "Which roof will we use" in m["reply"]["text"]


# ---- roof hand-off from the map panel ---------------------------------------------------------------------------------------------
def test_drawn_roof_handoff_is_acknowledged_next_turn(client):
    reply(client, "I'll draw my installation site on the map")
    ring = [[121.0437, 14.6760], [121.04379, 14.6760], [121.04379, 14.67606], [121.0437, 14.67606]]
    r = client.post(f"/api/agent/sessions/{CID}/roof", json={"mode": "drawn", "polygon_lonlat": ring, "roof_type": "flat"})
    assert r.status_code == 200, r.text
    assert r.json()["nextSlot"] == "load" and r.json()["roof"]["source"] == "drawn"
    m = reply(client, "I've finished drawing my installation site outline.")  # what the map panel sends by itself
    assert "installation site outline" in m["reply"]["text"].lower() and m["reply"]["slot"] == "load"
    assert "didn't catch" not in m["reply"]["text"].lower()
    assert client.get(f"/api/agent/sessions/{CID}/roof").json()["needsRoof"] is False


def test_sketch_handoff_uses_geocoded_anchor_or_persona_city(client):
    reply(client, "I'll sketch my installation site on a blank canvas")
    pts = [[0, 0], [220, 0], [220, 160], [0, 160]]
    r = client.post(f"/api/agent/sessions/{CID}/roof", json={"mode": "sketch", "points_px": pts, "px_per_m": 20,
                                                              "scale_source": "user_measured", "north_deg": 15})
    assert r.status_code == 200, r.text
    roof = r.json()["roof"]
    assert roof["source"] == "sketch" and roof["area_m2"] == pytest.approx(88, rel=0.01)
    assert roof["centroid"]["lat"] == pytest.approx(14.676, abs=0.001)  # Reyes persona city (Quezon City)


def test_roof_handoff_validation(client):
    r = client.post(f"/api/agent/sessions/{CID}/roof", json={"mode": "drawn", "polygon_lonlat": [[1, 1], [2, 2]]})
    assert r.status_code == 422
    r = client.post(f"/api/agent/sessions/{CID}/roof", json={"mode": "nope"})
    assert r.status_code == 422
    bowtie = [[121.0, 14.6], [121.001, 14.601], [121.001, 14.6], [121.0, 14.601]]
    r = client.post(f"/api/agent/sessions/{CID}/roof", json={"mode": "drawn", "polygon_lonlat": bowtie})
    assert r.status_code == 422 and r.json()["detail"]["code"] == "invalid_polygon"


def test_roof_handoff_blocked_while_turn_running(client):
    token = runner.LOCKS.acquire(CID, 60)
    r = client.post(f"/api/agent/sessions/{CID}/roof", json={"mode": "address", "lat": 14.6, "lon": 121.0})
    assert r.status_code == 409
    runner.LOCKS.release(CID, token)


# ---- sessions ----------------------------------------------------------------------------------------------------------------------------
def test_session_lifecycle(client):
    assert client.get(f"/api/agent/sessions/{CID}").status_code == 404
    reply(client, "hello")
    s = client.get(f"/api/agent/sessions/{CID}").json()
    assert s["turnCount"] == 1 and s["history"][0]["role"] == "user"
    assert client.delete(f"/api/agent/sessions/{CID}").json() == {"deleted": True}
    assert client.get(f"/api/agent/sessions/{CID}").status_code == 404
    assert client.get("/api/agent/sessions/bad!").status_code == 422


def test_delete_is_refused_while_a_turn_is_running(client):
    reply(client, "hello")
    token = runner.LOCKS.acquire(CID, 60)
    r = client.delete(f"/api/agent/sessions/{CID}")
    assert r.status_code == 409 and r.json()["detail"]["code"] == "turn_in_progress"
    runner.LOCKS.release(CID, token)
    assert client.delete(f"/api/agent/sessions/{CID}").json() == {"deleted": True}


def test_editing_the_account_household_updates_usage_in_an_open_chat(client):
    reply(client, "hello")
    assert client.patch("/api/auth/me", json={"monthly_kwh": 700, "household_template": "day_heavy"}).status_code == 200
    reply(client, "reyes demo")
    state = client.get(f"/api/agent/sessions/{CID}").json()
    assert state["profile"]["monthly_kwh"] == 700 and state["profile"]["household_template"] == "day_heavy"

def test_two_conversations_do_not_leak_state(client):
    reply(client, "reyes demo", cid="conv-aaaa-1111-0123456789")
    reply(client, "hello", cid="conv-bbbb-2222-0123456789")
    assert client.get("/api/agent/sessions/conv-aaaa-1111-0123456789").json()["profile"]["roof"] is not None
    assert client.get("/api/agent/sessions/conv-bbbb-2222-0123456789").json()["profile"]["roof"] is None


# ---- system type and rich results -------------------------------------------------------------------------------------
@pytest.mark.parametrize("choice,kind", [
    ("I want a grid-tied (on-grid) system", "on_grid"),
    ("I want a hybrid system with a battery", "hybrid"),
    ("I want an off-grid system", "off_grid"),
])
def test_system_type_shapes_the_design_and_the_results_are_rich_text(client, choice, kind):
    for m in ["reyes demo", "Yes, use 450 kWh per month", choice, "My budget is ₱300,000 to ₱500,000",
              "I want the fastest payback", "Yes, run the numbers"]:
        out = reply(client, m)
    assert client.get(f"/api/agent/sessions/{CID}").json()["profile"]["system_type"] == kind
    r = out["reply"]
    assert r["slot"] == "done"
    assert "| Solar panels |" in r["text"] and "| Installed cost |" in r["text"] and "**Good to know**" in r["text"]
    top = next(c for c in r["cards"] if c["type"] == "analysis")["data"]["packages"][0]
    assert (top["battery"] is None) == (kind == "on_grid")
    if kind == "off_grid":
        assert "Grid power replaced" in r["text"] and "installer has to confirm" in r["text"]


def test_backup_goal_is_not_offered_for_a_grid_tied_system(client):
    reply(client, "reyes demo")
    reply(client, "Yes, use 450 kWh per month")
    reply(client, "I want a grid-tied (on-grid) system")
    m = reply(client, "My budget is ₱300,000 to ₱500,000")
    assert m["reply"]["slot"] == "confirm" and "Blackout backup" not in [n["label"] for n in m["reply"]["next"]]
    m = reply(client, "I want blackout backup")
    assert m["reply"]["slot"] == "confirm" and "battery" in m["reply"]["text"].lower()  # refused: it needs a battery


def test_system_type_is_understood_from_free_text(client):
    reply(client, "reyes demo")
    reply(client, "Yes, use 450 kWh per month")
    m = reply(client, "we want solar plus storage, a hybrid please")
    assert client.get(f"/api/agent/sessions/{CID}").json()["profile"]["system_type"] == "hybrid"
    assert m["reply"]["slot"] == "budget"


def test_roof_layout_returns_the_unused_spots_for_the_map(client):
    for m in ["reyes demo", "Yes, use 450 kWh per month", "I want a grid-tied (on-grid) system",
              "My budget is ₱150,000 to ₱300,000", "I want the fastest payback", "Yes, run the numbers"]:
        reply(client, m)
    lay = client.get(f"/api/agent/sessions/{CID}/roof").json()["layout"]
    assert lay["capacity"] == lay["count"] + len(lay["spots_lonlat"]) and lay["capacity"] >= lay["count"] > 0


def _run_to_results(client):
    for m in ["reyes demo", "Yes, use 450 kWh per month", "I want a grid-tied (on-grid) system",
              "My budget is ₱150,000 to ₱300,000", "I want the fastest payback", "Yes, run the numbers"]:
        out = reply(client, m)
    return out


def test_passport_reply_is_a_clean_card_and_is_issued_once(client):
    _run_to_results(client)
    m = reply(client, "Create my Solar Passport")
    text = m["reply"]["text"]
    assert text.count("SOL-") >= 1 and "### Your Solar Passport" in text and "| Passport ID |" in text
    assert "[Open the verify page](/verify/SOL-" in text and "**What it does not tell you**" in text
    assert "I have your installation site outline" not in text
    first = next(c for c in m["reply"]["cards"] if c["type"] == "passport")["data"]["id"]
    m = reply(client, "Create my Solar Passport")  # asking again must not sign a second record
    assert next(c for c in m["reply"]["cards"] if c["type"] == "passport")["data"]["id"] == first
    assert "already created" in m["reply"]["text"]


def test_fill_whole_roof_preview_and_back(client):
    _run_to_results(client)
    design = client.get(f"/api/agent/sessions/{CID}/roof").json()["layout"]
    m = reply(client, "Show panels on my whole installation site")
    assert "### Whole-site preview" in m["reply"]["text"] and "Back to my design" in [n["label"] for n in m["reply"]["next"]]
    full = client.get(f"/api/agent/sessions/{CID}/roof").json()["layout"]
    assert full["full_roof"] is True and full["count"] == design["capacity"] and full["spots_lonlat"] == []
    m = reply(client, "Show my design again")
    back = client.get(f"/api/agent/sessions/{CID}/roof").json()["layout"]
    assert back["full_roof"] is False and back["count"] == design["count"]
    assert "Fill my whole site" in [n["label"] for n in m["reply"]["next"]]


def test_after_a_failed_run_changing_the_budget_leaves_the_change_menu(client):
    for m in ["reyes demo", "Yes, use 450 kWh per month", "I want a grid-tied (on-grid) system", "my budget is 30000",
              "I want the fastest payback", "Yes, run the numbers"]:
        out = reply(client, m)
    assert out["reply"]["slot"] == "change"
    out = reply(client, "increase and make it 400k")
    assert out["reply"]["slot"] == "confirm"  # not "What would you like to change?" again
    out = reply(client, "go")
    assert out["reply"]["slot"] == "done" and "| Installed cost |" in out["reply"]["text"]


def test_saying_nothing_or_go_in_the_change_menu_does_not_loop(client):
    for m in ["reyes demo", "Yes, use 450 kWh per month", "I want a grid-tied (on-grid) system", "My budget is ₱300,000 to ₱500,000",
              "I want the fastest payback", "I want to change something"]:
        out = reply(client, m)
    assert out["reply"]["slot"] == "change"
    out = reply(client, "nothing")
    assert out["reply"]["slot"] == "confirm"
    reply(client, "I want to change something")
    out = reply(client, "just run the numbers")
    assert out["reply"]["slot"] == "done"


def test_results_come_with_real_published_packages_near_the_recommended_size(client):
    out = _run_to_results(client)["reply"]
    card = next(c for c in out["cards"] if c["type"] == "packages")["data"]
    assert card["open"] is False and "| Photo |" not in out["text"]  # a link in the chat only; the side panel opens when asked
    assert card["wanted_kind"] == "grid-tied" and card["wanted_kwp"] > 0 and len(card["rows"]) >= 20
    assert card["basis"] == "design" and card["budget_max"] == 300000
    order = [(not r["within_budget"], r["synthetic"]) for r in card["rows"]]
    assert order == sorted(order)  # within the budget first, and real before made-up inside each group
    assert all(r["photo"] for r in card["rows"])


# ---- the reply must ask about the step Sol is really on --------------------------------------------------------------------------------
def test_off_slot_question_detector():
    from app.services.agent.guard import off_slot_question as off
    jump = "Great! Since your sketch is ready, how much is your typical monthly electricity bill in pesos, or how many kWh do you use each month?"
    assert off(jump, "roof_draw") and off(jump, "roof_method")  # the sketch was never received
    assert not off(jump, "load")  # the same question is fine once the bill is the open step
    assert not off("Got it, about 450 kWh a month. What is your budget?", "budget")  # a recap before the right question
    assert not off("Thanks! That helps a lot.", "load")  # no question at all
    assert not off("Do you want to use 250 kWh a month or type your bill?", "load")


def test_model_that_skips_ahead_is_replaced_and_pills_match(client):
    reply(client, "I'll sketch my installation site on a blank canvas")  # Sol now waits for the sketch (slot roof_draw)
    runner.set_provider_override(FakeProvider([("text", "Great! Since your sketch is ready, how much is your typical monthly electricity bill in pesos, "
                                                         "or how many kWh do you use each month?")]))
    m = reply(client, "my sketch is ready")["reply"]
    assert m["slot"] == "roof_draw"
    assert "monthly electricity bill" not in m["text"] and "installation site" in m["text"].lower()
    assert {"roof_draw"} <= {n["id"] for n in m["next"]}  # the pills now fit what the reply says
    state = client.get(f"/api/agent/sessions/{CID}").json()
    assert state["guardEvents"][-1]["off_slot"] == "roof_draw"


def test_packages_open_in_the_side_panel_as_soon_as_the_budget_is_set(client):
    for m in ["reyes demo", "Yes, use 450 kWh per month", "I want a grid-tied (on-grid) system"]:
        out = reply(client, m)
        assert not [c for c in out["reply"]["cards"] if c["type"] == "packages"]  # no budget yet, so nothing to match
    out = reply(client, "My budget is ₱150,000 to ₱300,000")["reply"]
    card = next(c for c in out["cards"] if c["type"] == "packages")["data"]
    assert card["open"] is True and card["basis"] == "usage" and card["budget_max"] == 300000 and card["wanted_kind"] == "grid-tied"
    assert 2 < card["wanted_kwp"] < 6  # roughly 450 kWh a month
    within = [r for r in card["rows"] if r["within_budget"]]
    assert within and all(r["price_php"] <= 300000 for r in within)
    assert [r["within_budget"] for r in card["rows"]] == sorted((r["within_budget"] for r in card["rows"]), reverse=True)
    again = reply(client, "I want the fastest payback")["reply"]
    assert not [c for c in again["cards"] if c["type"] == "packages"]  # offered once, not on every turn
    final = reply(client, "Yes, run the numbers")["reply"]
    fresh = next(c for c in final["cards"] if c["type"] == "packages")["data"]
    assert fresh["basis"] == "design" and fresh["open"] is False  # refreshed to the real design, offered as a link


def test_a_new_budget_offers_packages_again(client):
    for m in ["reyes demo", "Yes, use 450 kWh per month", "I want a grid-tied (on-grid) system", "My budget is ₱150,000 to ₱300,000"]:
        reply(client, m)
    out = reply(client, "My budget is ₱500,000 or more")["reply"]
    card = next(c for c in out["cards"] if c["type"] == "packages")["data"]
    assert card["open"] is True and card["budget_min"] == 500000


def test_recommend_question_is_answered_from_the_site_and_usage(client):
    for text in ("I want to install solar", "reyes demo", "Yes, use 450 kWh per month", "I want a grid-tied (on-grid) system"):
        reply(client, text)
    m = reply(client, "what do you recommend")
    txt = m["reply"]["text"]
    assert "didn't catch" not in txt and "63" in txt and "kWp" in txt and "₱150,000 to ₱300,000" in txt
    assert m["reply"]["slot"] == "budget" and txt.rstrip().endswith("installed?")  # it then asks the budget question again
