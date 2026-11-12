import json
import time

import pytest

from app.services.agent import runner
from app.services.agent.providers import FakeProvider, ProviderUnavailable

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
CID = "conv-test-0001-0123456789"


def say(client, text="", cid=CID, **extra):
    data = {"conversation_id": cid, "message": text, "persona_id": extra.pop("persona", "reyes"), "language": extra.pop("language", "auto")}
    r = client.post("/api/agent/chat?stream=false", data=data, **extra)
    return r


def reply(client, text, cid=CID, **kw):
    r = say(client, text, cid, **kw)
    assert r.status_code == 200, r.text
    return r.json()


def texts(msg):
    return [n["text"] for n in msg["reply"]["next"]]


# ---- first contact -----------------------------------------------------------------------------------------
def test_first_message_greets_and_offers_three_roof_choices(client):
    msg = reply(client, "I want to install solar")
    assert msg["phase"] == "done" and msg["conversationId"] == CID
    assert msg["steps"][0]["id"] == "s0" and all(s["status"] == "done" for s in msg["steps"])
    r = msg["reply"]
    assert "Sol" in r["text"] and "roof" in r["text"].lower() and "estimate" in r["text"].lower()
    assert len(r["next"]) == 3 and r["hasMapArtifact"] is False
    assert {"id", "label", "text"} <= set(r["next"][0])
    assert "I'll type my address" in texts(msg)


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
    m = reply(client, "I'll type my address")
    assert "address" in m["reply"]["text"].lower()
    assert "I'll draw my roof on the map" in texts(m) or "I'll draw my roof on the map" in " ".join(texts(m))

    m = reply(client, "reyes demo")  # synthetic demo roof: found offline, auto-selected
    assert m["reply"]["hasMapArtifact"] is True
    assert "88" in m["reply"]["text"] and "kWh" in m["reply"]["text"]  # roof area, then the usage question
    assert any(n["text"] == "Yes, use 450 kWh per month" for n in m["reply"]["next"])
    assert any(c["type"] == "roof" for c in m["reply"]["cards"])

    m = reply(client, "Yes, use 450 kWh per month")
    assert "budget" in m["reply"]["text"].lower() and len(m["reply"]["next"]) == 4

    m = reply(client, "My budget is ₱300,000 to ₱500,000")
    assert m["reply"]["slot"] == "goal"

    m = reply(client, "I want to cut my electricity bill")
    assert m["reply"]["slot"] == "goal_param"
    m = reply(client, "Cut my bill by 50%")
    assert m["reply"]["slot"] == "confirm" and "Shall I run the numbers" in m["reply"]["text"]

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
    assert m["reply"]["slot"] == "confirm"


def test_details_given_in_passing_are_saved_and_acknowledged(client):
    reply(client, "hi, I want to install solar panels but I'm not sure where to start")
    m = reply(client, "I live in Quezon City, my monthly bill is around 7000 pesos and I have about 400k to spend")
    p = client.get(f"/api/agent/sessions/{CID}").json()["profile"]
    assert p["monthly_bill_php"] == 7000 and p["budget_max_php"] == 400000 and p["load_confirmed"] is True
    text = m["reply"]["text"]
    assert "7,000" in text and "400,000" in text  # it says what it understood...
    assert m["reply"]["slot"] == "roof_method" and len(m["reply"]["next"]) == 3  # ...and still asks about the roof


def test_address_typed_at_the_first_question_is_understood(client):
    m = reply(client, "My house is at reyes demo, Quezon City")
    assert client.get(f"/api/agent/sessions/{CID}").json()["profile"]["roof"] is not None


def test_unknown_address_falls_back_to_drawing_choices(client):
    reply(client, "I'll type my address")
    m = reply(client, "999 Nowhere Street, Atlantis")
    assert "not available right now" in m["reply"]["text"].lower() or "no match" in m["reply"]["text"].lower()
    assert any("draw" in t.lower() for t in texts(m))


def test_unrecognised_input_re_asks_without_losing_state(client):
    reply(client, "hello")
    m = reply(client, "asdf qwer")
    assert "didn't catch" in m["reply"]["text"].lower()
    assert m["reply"]["slot"] == "roof_method" and len(m["reply"]["next"]) == 3


def test_invalid_values_are_rejected_with_a_helpful_message(client):
    reply(client, "reyes demo")
    reply(client, "Yes, use 450 kWh per month")
    m = reply(client, "my budget is 5k")
    assert "too low" in m["reply"]["text"].lower()
    assert client.get(f"/api/agent/sessions/{CID}").json()["profile"]["budget_max_php"] is None


def test_change_something_flow(client):
    reply(client, "reyes demo")
    reply(client, "Yes, use 450 kWh per month")
    reply(client, "My budget is ₱150,000 to ₱300,000")
    reply(client, "I want the fastest payback")
    m = reply(client, "I want to change something")
    assert len(m["reply"]["next"]) == 4 and m["reply"]["slot"] == "change"
    m = reply(client, "Change my budget")
    assert m["reply"]["slot"] == "budget"


def test_infeasible_budget_is_explained_not_crashed(client):
    reply(client, "reyes demo")
    reply(client, "Yes, use 450 kWh per month")
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
    r = client.post("/api/agent/chat", data={"conversation_id": CID, "message": "reyes demo", "persona_id": "reyes", "language": "auto"})
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
    ({"conversation_id": CID, "message": "hi", "persona_id": "nobody"}, "invalid_persona"),
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
    assert "Sol" in m["reply"]["text"] and len(m["reply"]["next"]) == 3
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
    reply(client, "I'll draw my roof on the map")
    ring = [[121.0437, 14.6760], [121.04379, 14.6760], [121.04379, 14.67606], [121.0437, 14.67606]]
    r = client.post(f"/api/agent/sessions/{CID}/roof", json={"mode": "drawn", "polygon_lonlat": ring, "roof_type": "flat"})
    assert r.status_code == 200, r.text
    assert r.json()["nextSlot"] == "load" and r.json()["roof"]["source"] == "drawn"
    m = reply(client, "I've finished drawing my roof outline.")  # what the map panel sends by itself
    assert "roof outline" in m["reply"]["text"].lower() and m["reply"]["slot"] == "load"
    assert "didn't catch" not in m["reply"]["text"].lower()
    assert client.get(f"/api/agent/sessions/{CID}/roof").json()["needsRoof"] is False


def test_sketch_handoff_uses_geocoded_anchor_or_persona_city(client):
    reply(client, "I'll sketch my roof on a blank canvas")
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


def test_persona_switch_mid_conversation_updates_usage(client):
    reply(client, "hello", persona="reyes")
    m = reply(client, "reyes demo", persona="wfh")
    state = client.get(f"/api/agent/sessions/{CID}").json()
    assert state["personaId"] == "wfh" and state["profile"]["monthly_kwh"] == 700


def test_two_conversations_do_not_leak_state(client):
    reply(client, "reyes demo", cid="conv-aaaa-1111-0123456789")
    reply(client, "hello", cid="conv-bbbb-2222-0123456789")
    assert client.get("/api/agent/sessions/conv-aaaa-1111-0123456789").json()["profile"]["roof"] is not None
    assert client.get("/api/agent/sessions/conv-bbbb-2222-0123456789").json()["profile"]["roof"] is None
