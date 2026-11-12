from app.services import installers
from app.services.agent import nlu

from test_agent_flow import reply


def test_region_for_picks_the_right_region():
    assert installers.region_for("I'm in Quezon City") == "NCR"  # not Quezon province
    assert installers.region_for("Lucena, Quezon") == "IV-A"
    assert installers.region_for("Angeles City, Pampanga") == "III"
    assert installers.region_for("Davao") == "XI" and installers.region_for("Cebu City") == "VII"
    assert installers.region_for("Narnia") is None


def test_installer_requests_route_to_the_table_but_how_to_choose_does_not():
    for q in ("can you suggest me some installer?", "Which solar installers are registered in Metro Manila?", "Show all solar installers in Metro Manila"):
        assert nlu.detect_intent(q) == "installers", q
    for q in ("What should I ask an installer?", "Does the DOE endorse the registered solar installers?"):
        assert nlu.detect_intent(q) == "docs", q


def test_table_has_contacts_links_and_the_no_endorsement_note():
    r = {"found": True, **installers.find("NCR")}
    assert r["total"] >= 40 and r["shown"] == installers.PAGE
    md = installers.table_markdown(r)
    assert "| Installer | Area | Phone | Email | Website | DOE lists |" in md
    assert "does not endorse" in md and "](https://" in md and "@" in md
    assert installers.find("NCR", show_all=True)["shown"] == r["total"]
    assert all(x["name"] for x in installers.find("XI")["rows"])


def test_chat_asks_where_first_then_shows_the_table(client):
    cid = "inst-conv-0001-0123456789"
    reply(client, "I want to install solar", cid=cid)
    ask = reply(client, "can you suggest me some installer?", cid=cid)["reply"]
    assert "Where is your home" in ask["text"] and "| Installer |" not in ask["text"]
    assert "I'm in Metro Manila" in [n["text"] for n in ask["next"]]
    shown = reply(client, "I'm in Metro Manila", cid=cid)["reply"]
    assert "| Installer | Area | Phone | Email | Website | DOE lists |" in shown["text"] and "does not endorse" in shown["text"]
    assert any(n["text"].startswith("Show all solar installers in Metro Manila") for n in shown["next"])
    every = reply(client, "Show all solar installers in Metro Manila", cid=cid)["reply"]
    assert every["text"].count("\n| ") > shown["text"].count("\n| ")
    unknown = reply(client, "Show solar installers somewhere else", cid=cid)["reply"]
    assert "Where is your home" in unknown["text"]
