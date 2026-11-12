import pytest
from fastapi.testclient import TestClient

from app.db import get_repo
from app.main import create_app
from app.services import auth, irradiance, passport, rewards
from tests.helpers import HOUSEHOLDS
from tests.test_simulate_optimize import fake_year_set


def _signup(client, key, email):
    h = {k: v for k, v in HOUSEHOLDS[key].items()}
    r = client.post("/api/auth/signup", json={**h, "email": email, "password": "password123"})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(irradiance, "get_year_set", lambda *a, **k: fake_year_set())
    return TestClient(create_app())


def test_regular_account_sees_nothing(client):
    h = _signup(client, "reyes", "plain@sol-tests.dev")
    assert client.get("/api/rewards", headers=h).json() == {"passport": None, "vouchers": []}
    assert client.post("/api/rewards/site-survey/redeem", headers=h).status_code == 404


def test_owner_passport_verifies_and_voucher_redeems_once(client):
    h = _signup(client, "reyes", "owner@sol-tests.dev")
    user = get_repo().get_user_by_email(auth.normalize_email("owner@sol-tests.dev"))
    assert rewards.issue_owner_passport(user) == "issued"
    assert rewards.issue_owner_passport(user) == "kept"  # idempotent: no second Passport

    ov = client.get("/api/rewards", headers=h).json()
    assert ov["passport"]["valid"] is True
    assert ov["passport"]["installation"]["sample"] is True
    assert passport.verify_stored(ov["passport"]["id"])["valid"] is True
    assert all(not v["redeemed"] and v["code"] is None for v in ov["vouchers"])

    first = client.post("/api/rewards/site-survey/redeem", headers=h)
    assert first.status_code == 200
    done = next(v for v in first.json()["vouchers"] if v["id"] == "site-survey")
    assert done["redeemed"] and done["code"]
    again = client.post("/api/rewards/site-survey/redeem", headers=h)
    assert again.status_code == 409
    after = next(v for v in client.get("/api/rewards", headers=h).json()["vouchers"] if v["id"] == "site-survey")
    assert after["code"] == done["code"] and after["redeemed_at"] == done["redeemed_at"]
    assert client.post("/api/rewards/nope/redeem", headers=h).status_code == 404
