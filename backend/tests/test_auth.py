"""Accounts, tokens and per-user chat sessions."""
from __future__ import annotations

import pytest

from conftest import TEST_USER

CID = "conv-auth-0001-0123456789"
OTHER = {"name": "Other Person", "email": "other@sol-tests.dev", "password": "another-pass-1"}


def signup(c, body):
    r = c.post("/api/auth/signup", json=body)
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def chat(c, headers, text="hello", cid=CID):
    return c.post("/api/agent/chat?stream=false", data={"conversation_id": cid, "message": text}, headers=headers)


def test_signup_returns_token_and_user_without_hash(anon_client):
    r = anon_client.post("/api/auth/signup", json=TEST_USER)
    body = r.json()
    assert r.status_code == 201 and body["token"]
    assert body["user"]["email"] == TEST_USER["email"] and body["user"]["initials"] == "TF"
    assert "password" not in str(body).lower()
    assert body["user"]["household"]["monthlyKwh"] == 450


def test_password_is_stored_hashed(anon_client):
    from app.db import get_repo

    signup(anon_client, TEST_USER)
    row = get_repo().get_user_by_email(TEST_USER["email"])
    assert row["password_hash"].startswith("scrypt$") and TEST_USER["password"] not in row["password_hash"]


def test_login_roundtrip_and_me(anon_client):
    signup(anon_client, TEST_USER)
    r = anon_client.post("/api/auth/login", json={"email": TEST_USER["email"].upper(), "password": TEST_USER["password"]})
    assert r.status_code == 200
    me = anon_client.get("/api/auth/me", headers={"Authorization": f"Bearer {r.json()['token']}"})
    assert me.status_code == 200 and me.json()["user"]["name"] == "Test Family"


def test_wrong_password_and_unknown_email_look_the_same(anon_client):
    signup(anon_client, TEST_USER)
    a = anon_client.post("/api/auth/login", json={"email": TEST_USER["email"], "password": "nope-nope-nope"})
    b = anon_client.post("/api/auth/login", json={"email": "ghost@sol-tests.dev", "password": "nope-nope-nope"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json() and a.json()["detail"]["code"] == "invalid_credentials"


def test_repeated_failures_are_throttled(anon_client):
    signup(anon_client, TEST_USER)
    for _ in range(8):
        anon_client.post("/api/auth/login", json={"email": TEST_USER["email"], "password": "bad-password-1"})
    r = anon_client.post("/api/auth/login", json={"email": TEST_USER["email"], "password": TEST_USER["password"]})
    assert r.status_code == 429


@pytest.mark.parametrize("patch,code", [
    ({"email": "not-an-email"}, "invalid_email"),
    ({"password": "short"}, "weak_password"),
    ({"name": "  "}, "invalid_name"),
    ({"monthly_kwh": 5}, "invalid_kwh"),
])
def test_signup_validation(anon_client, patch, code):
    r = anon_client.post("/api/auth/signup", json={**OTHER, **patch})
    assert r.status_code == 422 and r.json()["detail"]["code"] == code


def test_duplicate_email_is_rejected(anon_client):
    signup(anon_client, TEST_USER)
    r = anon_client.post("/api/auth/signup", json={**TEST_USER, "email": TEST_USER["email"].upper()})
    assert r.status_code == 409 and r.json()["detail"]["code"] == "email_taken"


def test_logout_revokes_the_token(anon_client):
    h = signup(anon_client, TEST_USER)
    assert anon_client.post("/api/auth/logout", headers=h).status_code == 200
    assert anon_client.get("/api/auth/me", headers=h).status_code == 401


def test_expired_token_is_rejected(anon_client):
    from app.db import get_repo
    from app.services import auth

    h = signup(anon_client, TEST_USER)
    token = h["Authorization"].split()[1]
    repo = get_repo()
    row = repo.get_token(auth._digest(token))
    repo.delete_token(auth._digest(token))
    repo.create_token(auth._digest(token), row["user_id"], 1.0)  # long expired
    assert anon_client.get("/api/auth/me", headers=h).status_code == 401


@pytest.mark.parametrize("method,path", [
    ("post", "/api/agent/chat"), ("get", "/api/agent/sessions"), ("get", f"/api/agent/sessions/{CID}"),
    ("delete", f"/api/agent/sessions/{CID}"), ("get", f"/api/agent/sessions/{CID}/roof"),
])
def test_agent_routes_need_sign_in(anon_client, method, path):
    kw = {"data": {"conversation_id": CID, "message": "hi"}} if method == "post" else {}
    r = getattr(anon_client, method)(path, **kw)
    assert r.status_code == 401 and r.json()["detail"]["code"] == "unauthorized"


def test_garbage_token_is_rejected(anon_client):
    assert anon_client.get("/api/auth/me", headers={"Authorization": "Bearer nonsense"}).status_code == 401
    assert anon_client.get("/api/auth/me", headers={"Authorization": "Basic abc"}).status_code == 401


def test_patch_profile_updates_household(client):
    r = client.patch("/api/auth/me", json={"city": "Cebu City", "lat": 10.3157, "lon": 123.8854, "monthly_kwh": 320})
    h = r.json()["user"]["household"]
    assert r.status_code == 200 and h["city"] == "Cebu City" and h["monthlyKwh"] == 320
    assert client.patch("/api/auth/me", json={"lat": 10.0}).status_code == 422  # lat without lon


def test_sessions_are_listed_per_user_with_titles(client, anon_client):
    chat(client, {}, "I want solar for my house", cid="conv-aaaa-1111-0123456789")
    chat(client, {}, "hi there", cid="conv-bbbb-2222-0123456789")
    mine = client.get("/api/agent/sessions").json()["sessions"]
    assert [s["id"] for s in mine] == ["conv-bbbb-2222-0123456789", "conv-aaaa-1111-0123456789"]
    assert mine[1]["title"] == "I want solar for my house" and mine[0]["turnCount"] == 1
    other = signup(anon_client, OTHER)
    anon_client.headers.pop("Authorization", None)
    assert anon_client.get("/api/agent/sessions", headers=other).json()["sessions"] == []


def test_other_users_cannot_read_write_or_delete_a_session(client, anon_client):
    chat(client, {}, "hello", cid=CID)
    other = signup(anon_client, OTHER)
    anon_client.headers.pop("Authorization", None)
    for r in (anon_client.get(f"/api/agent/sessions/{CID}", headers=other),
              anon_client.get(f"/api/agent/sessions/{CID}/roof", headers=other),
              anon_client.delete(f"/api/agent/sessions/{CID}", headers=other),
              chat(anon_client, other, "let me in", cid=CID)):
        assert r.status_code == 404
    assert client.get(f"/api/agent/sessions/{CID}").status_code == 200  # still intact for the owner
    assert len(client.get(f"/api/agent/sessions/{CID}").json()["history"]) == 2


def test_new_account_without_usage_is_asked_for_it(anon_client):
    h = signup(anon_client, OTHER)
    m = chat(anon_client, h, "hello").json()
    assert "Hi Other!" in m["reply"]["text"] or "Other" in m["reply"]["text"]
    state = anon_client.get(f"/api/agent/sessions/{CID}", headers=h).json()
    assert state["profile"]["monthly_kwh"] is None


def test_deleting_a_session_removes_it_from_the_list(client):
    chat(client, {}, "hello", cid=CID)
    assert client.delete(f"/api/agent/sessions/{CID}").json() == {"deleted": True}
    assert client.get("/api/agent/sessions").json()["sessions"] == []
