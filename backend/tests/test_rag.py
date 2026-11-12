from app.services import rag
from app.services.agent import nlu

from test_agent_flow import reply


def test_every_source_file_has_a_link_and_a_kind():
    lib = rag.library()
    assert len(lib) >= 10
    for p in rag.CORPUS_DIR.glob("*.md"):
        text = p.read_text(encoding="utf-8")
        assert text.startswith("---") and "kind:" in text and "source_url:" in text, p.name


def test_search_prefers_meralco_and_cites_the_source():
    top = rag.search("Do I need a building permit for a micro solar system?")[0]
    assert top["kind"] in ("meralco", "policy") and top["source_url"].startswith("https://www.")
    assert "1,500" in " ".join(h["text"] for h in rag.search("how much is the ERC Certificate of Compliance application fee"))


def test_off_topic_and_unsourced_questions_return_nothing():
    assert rag.search("best pizza in manila") == []
    assert rag.search("which installer is the best")[0]["kind"] == "installer"  # the honest "no vetted list" note ranks first


def test_synonyms_bridge_wording():
    assert any("outage" in h["text"].lower() for h in rag.search("what happens to my solar during a blackout"))


def test_only_questions_go_to_the_library():
    assert nlu.detect_intent("Do I need a permit for zero export?") == "docs"
    assert nlu.detect_intent("I want backup for a blackout") != "docs"
    assert nlu.detect_intent("Show me the assumptions") == "explain"
    assert nlu.detect_intent("How much is a Huawei inverter in Manila?") == "products"


def test_chat_answers_a_rules_question_from_sources(client):
    r = reply(client, "I want to install solar", cid="rag-conv-0001-0123456789")
    r = reply(client, "How much does net metering application cost?", cid="rag-conv-0001-0123456789")
    text = r["reply"]["text"]
    assert "meralco.com.ph" in text


def test_registry_lists_firms_with_the_no_endorsement_warning():
    hits = rag.search("which solar installers are registered in Metro Manila with the DOE")
    text = " ".join(h["text"] for h in hits)
    assert "MSpectrum" in text or "Aces Solar" in text
    assert any("does not endorse" in h["text"] for h in rag.search("does the DOE endorse the registered solar installers"))


def test_every_follow_up_question_routes_to_the_library_and_finds_an_answer():
    from app.services.agent import followups

    asked = {q for qs in followups.FOLLOW.values() for _, q in qs} | {t for _, t in followups.after_analysis(
        {"system_type": None, "packages": [{"readiness": [{"id": "size", "status": "watch"}], "battery": None}]})}
    for q in asked:
        assert nlu.detect_intent(q) in ("docs", "installers"), q
        assert nlu.detect_intent(q) == "installers" or rag.search(q), q
    assert set(followups.FOLLOW) <= {m["id"] for m in rag.library()}


def test_pills_follow_the_topic_and_do_not_repeat(client):
    cid = "pill-conv-0001-0123456789"
    reply(client, "I want to install solar", cid=cid)
    first = reply(client, "Do I need a building permit for a micro solar system?", cid=cid)["reply"]["next"]
    ids = [n["id"] for n in first]
    assert {"roof_draw", "roof_sketch"} <= set(ids) and "roof_address" not in ids and len(first) <= 5
    extra = [n for n in first if n["id"].startswith("q_")]
    assert extra and all(n["text"] != "Do I need a building permit for a micro solar system?" for n in extra)
    again = reply(client, extra[0]["text"], cid=cid)["reply"]["next"]
    assert extra[0]["text"] not in [n["text"] for n in again]
