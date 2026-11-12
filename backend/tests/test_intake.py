import pytest

from helpers import user_row

from app.services.agent import intake
from app.services.agent.session import Session, load_session, save_session

ROOF = {"id": "r1", "source": "osm", "area_m2": 80.0}


def new_session(persona="reyes") -> Session:
    return load_session("s1", user_row(persona), "english")


def test_new_session_is_seeded_from_persona():
    s = new_session("maria")
    assert s.profile.monthly_kwh == 250
    assert s.profile.household_template == "night_heavy"
    assert s.profile.load_confirmed is False


def test_slot_order_walks_to_done():
    s = new_session()
    assert intake.next_slot(s) == "roof_method"
    intake.apply_updates(s, roof_method="address")
    assert intake.next_slot(s) == "roof_address"
    s.pending["candidates"] = [{"label": "A", "lat": 14.6, "lon": 121.0}]
    assert intake.next_slot(s) == "roof_pick"
    s.profile.roof = ROOF
    assert intake.next_slot(s) == "load"  # persona kWh must still be confirmed
    intake.apply_updates(s, confirm_load=True)
    assert intake.next_slot(s) == "system_type"
    intake.apply_updates(s, system_type="hybrid")
    assert intake.next_slot(s) == "budget"
    intake.apply_updates(s, budget_min_php=150000, budget_max_php=300000)
    assert intake.next_slot(s) == "confirm"  # no goal question: it defaults to the biggest 10-year savings
    assert s.profile.goal == "max_savings_10y" and s.pending["goal_default"] is True
    assert "Goal:" not in intake.summary_line(s) and "?" not in intake.question_for("confirm", s)
    intake.apply_updates(s, goal="cut_bill")  # the user can still choose one
    assert intake.next_slot(s) == "goal_param" and "goal_default" not in s.pending
    intake.apply_updates(s, goal_target_pct=70)
    assert intake.next_slot(s) == "confirm"
    intake.apply_updates(s, confirm_summary=True)
    assert intake.next_slot(s) == "run"
    s.results["analysis"] = {"ok": True}
    assert intake.next_slot(s) == "done"


def test_backup_goal_needs_hours_not_percent():
    s = new_session()
    s.profile.roof = ROOF
    intake.apply_updates(s, confirm_load=True, system_type="hybrid", budget_max_php=300000, goal="backup")
    assert intake.next_slot(s) == "goal_param"
    applied, errors = intake.apply_updates(s, goal_target_pct=50)
    assert errors and "cut my bill" in errors[0]
    intake.apply_updates(s, backup_hours=4)
    assert intake.next_slot(s) == "confirm"


@pytest.mark.parametrize(
    "fields,fragment",
    [
        ({"monthly_kwh": 5}, "between"),
        ({"monthly_kwh": "abc"}, "number"),
        ({"monthly_bill_php": 10}, "between"),
        ({"budget_min_php": 500000, "budget_max_php": 100000}, "above"),
        ({"budget_max_php": 5000}, "too low"),
        ({"goal": "get_rich"}, "goal must be"),
        ({"household_template": "weird"}, "household_template"),
        ({"roof_method": "teleport"}, "roof_method"),
    ],
)
def test_validation_rejects_bad_values(fields, fragment):
    s = new_session()
    before = s.profile.model_dump()
    applied, errors = intake.apply_updates(s, **fields)
    assert errors and fragment in errors[0]
    assert s.profile.model_dump() == before


def test_confirm_summary_requires_complete_profile():
    s = new_session()
    _, errors = intake.apply_updates(s, confirm_summary=True)
    assert errors


def test_typing_kwh_replaces_bill_and_confirms_load():
    s = new_session()
    intake.apply_updates(s, monthly_bill_php=6780)
    assert s.profile.monthly_kwh is None and s.profile.load_confirmed
    intake.apply_updates(s, monthly_kwh=500)
    assert s.profile.monthly_bill_php is None and s.profile.monthly_kwh == 500
    assert s.profile.load_source == "user"


def test_changing_inputs_invalidates_results_and_confirmation():
    s = new_session()
    s.profile.roof = ROOF
    intake.apply_updates(s, confirm_load=True, system_type="on_grid", budget_max_php=300000, goal="fastest_payback", confirm_summary=True)
    s.results["analysis"] = {"x": 1}
    intake.apply_updates(s, budget_max_php=400000)
    assert s.results == {} and s.profile.confirmed is False
    assert intake.next_slot(s) == "confirm"


def test_account_usage_change_reseeds_load_unless_user_typed():
    s = new_session("reyes")
    save_session(s)
    s2 = load_session("s1", user_row("wfh"), "english")  # same account id, household edited to 700 kWh
    assert s2.profile.monthly_kwh == 700 and s2.persona_id == "user-test-0001"
    intake.apply_updates(s2, monthly_kwh=333)
    save_session(s2)
    s3 = load_session("s1", user_row("maria"), "english")
    assert s3.profile.monthly_kwh == 333  # user-typed value is kept


def test_account_without_usage_asks_for_it():
    row = {**user_row("reyes"), "monthly_kwh": None, "household_name": None, "name": "New Person"}
    s = load_session("s2", row, "english")
    assert s.profile.monthly_kwh is None and s.persona.first == "New" and s.persona.monthly_kwh is None

def test_every_choice_text_round_trips_through_match_choice():
    s = new_session()
    s.profile.roof_method = "address"
    s.pending["candidates"] = [{"label": "123 Test St, Quezon City", "lat": 14.6, "lon": 121.0}]
    s.pending["candidate_texts"] = {"Use 123 Test St, Quezon City": 0}
    s.profile.roof = ROOF
    s.profile.goal = "cut_bill"
    s.results["analysis"] = {}
    for slot in ["roof_method", "roof_address", "roof_pick", "roof_draw", "load", "system_type", "budget", "goal", "goal_param",
                 "confirm", "change", "done"]:
        if slot == "roof_pick":
            s.profile.roof = None
        for sug in intake.choices_for(slot, s):
            assert set(sug) >= {"id", "label", "text"}
            assert intake.match_choice(s, sug["text"]) is not None, (slot, sug)
    s.profile.goal = "backup"
    for sug in intake.choices_for("goal_param", s):
        assert intake.match_choice(s, sug["text"]) is not None


def test_budget_choice_sets_range():
    s = new_session()
    for sug in intake.choices_for("budget", s):
        act = intake.match_choice(s, sug["text"])
        assert act["kind"] == "update" and act["payload"]["budget_max_php"] > 0
    act = intake.match_choice(s, "My budget is ₱150,000 to ₱300,000")
    assert act["payload"] == {"budget_min_php": 150000.0, "budget_max_php": 300000.0}


def test_unknown_text_is_not_a_choice():
    assert intake.match_choice(new_session(), "I want to install solar") is None


def test_change_flow_resets_only_that_slot():
    s = new_session()
    s.profile.roof = ROOF
    intake.apply_updates(s, confirm_load=True, system_type="on_grid", budget_max_php=300000, goal="fastest_payback", confirm_summary=True)
    assert intake.next_slot(s) == "run"
    intake.run_action(s, intake.match_choice(s, intake.CHANGE_TEXT))
    assert intake.next_slot(s) == "change"
    intake.run_action(s, intake.match_choice(s, "Change my budget"))
    assert intake.next_slot(s) == "budget"
    assert s.profile.roof is not None and s.profile.goal == "fastest_payback"


def test_language_pick():
    s = new_session()
    s.language = "auto"
    assert intake.pick_language(s, "gusto ko po mag solar sa bahay") == "taglish"
    assert intake.pick_language(s, "I want to install solar") == "english"
    s.language = "taglish"
    assert intake.pick_language(s, "hello") == "taglish"
