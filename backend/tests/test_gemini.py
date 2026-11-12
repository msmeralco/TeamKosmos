import pytest
from google.genai import types

from app.config import get_settings
from app.services.agent import gemini_provider, runner
from app.services.agent.gemini_provider import GeminiProvider, function_declarations
from app.services.agent.tools import TOOLS

CID = "conv-gem-00001-0123456789"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class FakeAPIError(Exception):
    def __init__(self, code):
        super().__init__(f"error {code}")
        self.code = code


def fn_call(name, **args):
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(
        role="model", parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))]))])


def text_resp(text):
    return types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part(text=text)]))])


class FakeModels:
    def __init__(self, script):
        self.script, self.calls = list(script), []

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": list(contents), "config": config})
        item = self.script.pop(0) if self.script else text_resp("")
        if isinstance(item, Exception):
            raise item
        return item


class FakeClient:
    def __init__(self, script):
        self.models = FakeModels(script)


@pytest.fixture(autouse=True)
def no_retry_delay(monkeypatch):
    monkeypatch.setattr(gemini_provider, "RETRY_DELAY_S", 0.0)


def use(script):
    fake = FakeClient(script)
    runner.set_provider_override(GeminiProvider(get_settings(), client=fake))
    return fake


def chat(client, text, cid=CID, **kw):
    r = client.post("/api/agent/chat?stream=false", data={"conversation_id": cid, "message": text,
                                                        "language": kw.pop("language", "auto")}, **kw)
    assert r.status_code == 200, r.text
    return r.json()


def test_function_calling_loop_updates_state_and_returns_text(client):
    fake = use([fn_call("update_profile", monthly_kwh=450), text_resp("Thanks, I noted about 450 kWh a month. Which roof should we use?")])
    msg = chat(client, "I use 450 kWh a month")
    assert msg["reply"]["text"].startswith("Thanks, I noted")
    assert [s["label"] for s in msg["steps"]] == ["Reading your message", "Saving your details"]
    assert client.get(f"/api/agent/sessions/{CID}").json()["profile"]["monthly_kwh"] == 450
    # the tool result is sent back to the model as a function response
    resp_part = fake.models.calls[1]["contents"][-1].parts[0].function_response
    assert resp_part.name == "update_profile" and resp_part.response["result"]["applied"]["monthly_kwh"] == 450
    assert "next_slot" in resp_part.response["result"]
    # the model's own function_call turn is preserved in the history it receives back
    assert fake.models.calls[1]["contents"][-2].role == "model"


def test_system_instruction_carries_state_language_and_rules(client):
    fake = use([text_resp("Hello! Which roof should we use?")])
    chat(client, "hi", language="taglish")
    system = fake.models.calls[0]["config"].system_instruction
    assert "Never calculate" in system and "Reply in Tagalog only" in system and "next_slot: roof_method" in system
    assert "first message" in system
    assert fake.models.calls[0]["config"].automatic_function_calling.disable is True


def test_transient_error_is_retried_once(client):
    fake = use([FakeAPIError(429), text_resp("Hi there. Which roof should we use?")])
    msg = chat(client, "hi")
    assert msg["reply"]["text"].startswith("Hi there") and len(fake.models.calls) == 2


def test_persistent_rate_limit_falls_back_to_scripted(client):
    fake = use([FakeAPIError(429), FakeAPIError(429)])
    msg = chat(client, "I want to install solar")
    assert len(fake.models.calls) == 2
    assert any(s["label"] == "Switching to quick mode" for s in msg["steps"])
    assert len(msg["reply"]["next"]) == 2 and "Sol" in msg["reply"]["text"]


def test_overload_503_is_not_retried_and_trips_the_breaker(client):
    fake = use([FakeAPIError(503), text_resp("should not be used")])
    msg = chat(client, "I want to install solar", cid="conv-503-a-0123456789")
    assert len(fake.models.calls) == 1  # a 503 already costs seconds: fail over, do not retry
    assert any(s["label"] == "Switching to quick mode" for s in msg["steps"]) and len(msg["reply"]["next"]) == 2
    # the next message skips Gemini entirely for a while, so it answers instantly
    msg2 = chat(client, "I'll draw my installation site on the map", cid="conv-503-a-0123456789")
    assert len(fake.models.calls) == 1 and "map" in msg2["reply"]["text"].lower()
    gemini_provider.reset_breakers()


def test_overloaded_main_model_falls_back_to_the_second_gemini_model(client, monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
    get_settings.cache_clear()
    fake = use([FakeAPIError(503), text_resp("Hi from the backup model. Which roof should we use?")])
    msg = chat(client, "hi", cid="conv-fb-0000-0123456789")
    assert [c["model"] for c in fake.models.calls] == ["gemini-3.5-flash-lite", "gemini-3.8-flash"]
    assert msg["reply"]["text"].startswith("Hi from the backup model")
    assert not any(s["label"] == "Switching to quick mode" for s in msg["steps"])  # still a Gemini answer
    chat(client, "hello again", cid="conv-fb-0000-0123456789")
    assert fake.models.calls[-1]["model"] == "gemini-3.8-flash"  # main model is skipped while its breaker is open
    assert [c["model"] for c in fake.models.calls].count("gemini-3.5-flash-lite") == 1


def test_both_models_down_drops_to_quick_mode(client, monkeypatch):
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash")
    get_settings.cache_clear()
    fake = use([FakeAPIError(503), FakeAPIError(503)])
    msg = chat(client, "I want to install solar", cid="conv-fb-0001-0123456789")
    assert len(fake.models.calls) == 2 and any(s["label"] == "Switching to quick mode" for s in msg["steps"])


def test_request_timeout_and_no_sdk_retries_are_configured(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "dummy-key-for-client-construction")
    get_settings.cache_clear()
    p = GeminiProvider(get_settings())
    opts = p.client._api_client._http_options
    assert opts.timeout == int(gemini_provider.REQUEST_TIMEOUT_S * 1000)
    assert opts.retry_options.attempts == 1


def test_bad_key_is_not_retried(client):
    fake = use([FakeAPIError(403)])
    msg = chat(client, "hi")
    assert len(fake.models.calls) == 1 and msg["reply"]["next"]


def test_tool_call_cap_per_turn(client):
    fake = use([fn_call("update_profile", net_metering=True) for _ in range(10)])
    msg = chat(client, "hi")
    executed = [s for s in msg["steps"] if s["label"] == "Saving your details"]
    assert len(executed) <= get_settings().max_tool_calls
    assert msg["reply"]["text"] and msg["reply"]["next"]  # still answers
    assert len(fake.models.calls) <= get_settings().max_tool_calls + 2


def test_unknown_tool_and_bad_arguments_are_reported_to_the_model(client):
    fake = use([fn_call("launch_rocket", x=1), fn_call("update_profile", monthly_kwh="lots"), text_resp("Sorry, could you give your usage in kWh? ")])
    chat(client, "hi")
    r1 = fake.models.calls[1]["contents"][-1].parts[0].function_response.response["result"]
    r2 = fake.models.calls[2]["contents"][-1].parts[0].function_response.response["result"]
    assert r1["error"] == "unknown_tool" and r2["error"] == "invalid_arguments"


def test_attachment_is_sent_as_image_part(client):
    fake = use([fn_call("record_bill_reading", kwh=420, amount_php=6500),
                text_resp("I read about 420 kWh and ₱6,500 on your bill. Is that right?")])
    msg = chat(client, "Attached files", files=[("files", ("bill.png", PNG, "image/png"))])
    user = fake.models.calls[0]["contents"][-1]
    assert user.parts[0].inline_data.mime_type == "image/png" and "attached files" in user.parts[1].text.lower()
    assert "420 kWh" in msg["reply"]["text"]  # numbers read from the image pass the guard via record_bill_reading
    state = client.get(f"/api/agent/sessions/{CID}").json()["profile"]
    assert state["monthly_kwh"] == 450  # reading alone does not change the profile


def test_numbers_not_from_tools_are_blocked(client):
    use([text_resp("Your panels will save you ₱88,888 a month, which is great.")])
    msg = chat(client, "hi")
    assert "88,888" not in msg["reply"]["text"] and msg["reply"]["next"]


def test_empty_model_response_falls_back_to_template(client):
    use([types.GenerateContentResponse(candidates=[])])
    msg = chat(client, "hi")
    assert "installation site" in msg["reply"]["text"].lower()


def test_history_is_sent_with_alternating_roles_starting_with_user(client):
    fake = use([text_resp("Hello. Which roof should we use?"), text_resp("Got it. Which roof should we use?")])
    chat(client, "hi")
    chat(client, "hello again")
    roles = [c.role for c in fake.models.calls[1]["contents"]]
    assert roles == ["user", "model", "user"]


def test_identical_requests_hit_the_cache(client):
    fake = use([text_resp("Hello. Which roof should we use?")])
    chat(client, "hi", cid="conv-cache-0001-0123456789")
    chat(client, "hi", cid="conv-cache-0002-0123456789")  # same persona, same first message, same state
    assert len(fake.models.calls) == 1


def test_function_declarations_cover_every_tool():
    decls = function_declarations(types)
    from app.services.agent.gemini_provider import HIDDEN_TOOLS

    assert {d.name for d in decls} == set(TOOLS) - HIDDEN_TOOLS  # the address lookup tools are not offered to the model
    by = {d.name: d for d in decls}
    goal = by["update_profile"].parameters.properties["goal"]
    assert goal.enum == ["cut_bill", "max_savings_10y", "fastest_payback", "backup"]
    assert "geocode_address" not in by and "get_building_outline" not in by
    assert by["update_profile"].parameters.properties["monthly_kwh"].type == "NUMBER"
    assert by["run_analysis"].parameters is None
    assert by["search_products"].parameters.properties["categories"].type == "ARRAY"


# ---- an LLM must not invent values or confirmations (seen live with gemini-3.5-flash-lite) ---------------------
def test_llm_cannot_invent_numbers_or_confirm_for_the_user(client):
    cid = "conv-ground-0123456789"
    chat(client, "reyes demo", cid=cid)
    chat(client, "Yes, use 450 kWh per month", cid=cid)
    chat(client, "I want a grid-tied (on-grid) system", cid=cid)
    chat(client, "My budget is ₱300,000 to ₱500,000", cid=cid)
    # the user only says which goal they want; the model also invents 50% and confirms the summary
    fake = use([fn_call("update_profile", goal="cut_bill", goal_target_pct=50, confirm_summary=True),
                text_resp("Okay, by how much do you want to cut your bill?")])
    msg = chat(client, "I want to cut my electricity bill", cid=cid)
    profile = client.get(f"/api/agent/sessions/{cid}").json()["profile"]
    assert profile["goal"] == "cut_bill"
    assert profile["goal_target_pct"] is None and profile["confirmed"] is False
    assert msg["reply"]["slot"] == "goal_param"
    result = fake.models.calls[1]["contents"][-1].parts[0].function_response.response["result"]
    assert len(result["rejected"]) == 2 and "ask the user" in result["message"].lower()


def test_llm_values_the_user_really_stated_are_accepted(client):
    cid = "conv-ground-0000000001"
    chat(client, "reyes demo", cid=cid)
    use([fn_call("update_profile", confirm_load=True, monthly_kwh=450, budget_max_php=300000),
         text_resp("Thanks. What matters most to you?")])
    chat(client, "yes use 450 kWh and my budget is 300k", cid=cid)
    p = client.get(f"/api/agent/sessions/{cid}").json()["profile"]
    assert p["monthly_kwh"] == 450 and p["budget_max_php"] == 300000 and p["load_confirmed"] is True


def test_llm_cannot_bypass_the_confirmation_step(client):
    cid = "conv-ground-0000000002"
    for m in ["reyes demo", "Yes, use 450 kWh per month", "I want a grid-tied (on-grid) system", "My budget is ₱300,000 to ₱500,000", "I want the fastest payback"]:
        chat(client, m, cid=cid)
    use([fn_call("update_profile", confirm_summary=True), fn_call("run_analysis"), text_resp("Done.")])
    chat(client, "hmm okay", cid=cid)  # not an agreement
    state = client.get(f"/api/agent/sessions/{cid}").json()
    assert state["nextSlot"] == "confirm" and state["summary"] is None
