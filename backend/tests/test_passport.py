import copy
import json

import pytest

from app.db import get_repo
from app.errors import ApiError
from app.models import FinalizeRequest
from app.services import load, passport, roof, simulate
from tests.test_roof import rect_lonlat
from tests.test_simulate_optimize import fake_year_set, pkg_from_seed


@pytest.fixture()
def issued(monkeypatch):
    # Deterministic fake weather so issuing and re-running match without any network.
    from app.services import irradiance

    monkeypatch.setattr(irradiance, "get_year_set", lambda *a, **k: fake_year_set())
    r = roof.finalize(FinalizeRequest(polygon_lonlat=rect_lonlat(14, 10), roof_type="single_slope"))
    ld = load.estimate_load(monthly_kwh=450, template="balanced")
    pkg = pkg_from_seed(8)
    res = simulate.simulate_package(pkg, r, ld, year_set=fake_year_set())
    inputs = {"roof": r.model_dump(mode="json"),
              "load": {"params": {"monthly_kwh": 450.0, "template": "balanced", "basis": "kwh_input"}},
              "budget_php": [0, 300000], "goal": "cut_bill"}
    return passport.issue(inputs=inputs, package=pkg, results=res)


def test_issue_and_verify_roundtrip(issued):
    assert issued["id"].startswith("SOL-") and issued["short_hash"] == issued["hash"][:12]
    out = passport.verify_stored(issued["id"])
    status = {c["name"]: c["status"] for c in out["checks"]}
    assert out["valid"] is True
    assert status["integrity"] == status["signature"] == status["chain"] == status["reproducible"] == "pass"
    assert status["sourced_inputs"] in ("pass", "n/a")  # n/a while placeholder assumptions remain unverified


def test_chain_links_consecutive_passports(issued, monkeypatch):
    second = passport.issue(inputs=issued["body"]["inputs"], package=issued["body"]["package"], results=issued["body"]["results"])
    assert second["prev_hash"] == issued["hash"]
    assert passport.verify_stored(issued["id"])["valid"] is True  # still valid after a successor was appended
    assert passport.verify_stored(second["id"])["valid"] is True


def test_paste_to_verify_detects_one_changed_digit(issued):
    record = {k: issued[k] for k in ("body", "hash", "prev_hash", "signature")}
    assert passport.verify_pasted(record)["valid"] is True
    tampered = copy.deepcopy(record)
    tampered["body"]["package"]["capex_php"] += 1  # change one digit-sized amount
    out = passport.verify_pasted(tampered)
    assert out["valid"] is False
    assert {c["name"]: c["status"] for c in out["checks"]}["integrity"] == "fail"


def test_forged_signature_and_forged_hash_fail(issued):
    rec = {k: issued[k] for k in ("body", "hash", "prev_hash", "signature")}
    bad_sig = dict(rec, signature="00" * 64)
    assert {c["name"]: c["status"] for c in passport.verify_pasted(bad_sig)["checks"]}["signature"] == "fail"
    # An attacker edits the body AND recomputes the hash but cannot sign it with Sol's key.
    forged = copy.deepcopy(rec)
    forged["body"]["package"]["capex_php"] = 1
    forged["hash"] = passport.compute_hash(passport.canonical(forged["body"]), forged["prev_hash"])
    out = passport.verify_pasted(forged)
    st = {c["name"]: c["status"] for c in out["checks"]}
    assert out["valid"] is False and st["signature"] == "fail" and st["chain"] == "fail"


def test_unknown_record_not_in_ledger_fails_chain(issued):
    rec = {k: issued[k] for k in ("body", "hash", "prev_hash", "signature")}
    rec["body"]["id"] = "SOL-NOTREAL"
    out = passport.verify_pasted(rec)
    assert out["valid"] is False


def test_stored_row_tampering_is_caught(issued):
    import sqlite3
    from contextlib import closing

    repo = get_repo()
    with closing(sqlite3.connect(repo.path)) as conn:
        conn.execute("DROP TRIGGER ledger_no_update")  # simulate someone with raw database access
        conn.execute("UPDATE ledger SET body_json = replace(body_json, '\"goal\":\"cut_bill\"', '\"goal\":\"backup\"')")
        conn.commit()
    out = passport.verify_stored(issued["id"])
    assert out["valid"] is False


def test_garbage_input_is_rejected():
    for bad in ({}, {"body": "x", "hash": "a", "prev_hash": "b", "signature": "c"}, {"body_json": "{not json", "hash": "a", "prev_hash": "b", "signature": "c"}):
        with pytest.raises(ApiError):
            passport.verify_pasted(bad)


def test_canonical_is_stable_and_rounds_floats():
    a = passport.canonical({"b": 1.0000001, "a": [1, 2.5]})
    b = passport.canonical({"a": [1, 2.5], "b": 1.0000002})  # different key order and float noise
    assert a == b == '{"a":[1,2.5],"b":1.0}'
    assert passport.canonical({"z": "₱"}) == '{"z":"₱"}'  # non-ASCII kept as UTF-8


def test_key_is_persisted_between_restarts(issued):
    pub = passport.public_key_hex()
    passport.reset_key_cache()
    assert passport.public_key_hex() == pub


def test_html_page_green_and_red(issued):
    assert "Verified" in passport.html_page(issued["id"])
    assert "Not found" in passport.html_page("SOL-NOPE")
