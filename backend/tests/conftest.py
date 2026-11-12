"""Shared fixtures: every test runs offline against a temp SQLite database with no Gemini key and no real network."""
from __future__ import annotations

import os

import httpx
import pytest


def _offline_client() -> httpx.Client:
    def refuse(request):
        raise httpx.ConnectError("network disabled in tests")

    return httpx.Client(transport=httpx.MockTransport(refuse))


@pytest.fixture(autouse=True)
def isolated_env(tmp_path, monkeypatch, request):
    if request.node.get_closest_marker("live"):
        if os.environ.get("RUN_LIVE") != "1":
            pytest.skip("live test (set RUN_LIVE=1)")
        yield
        return

    monkeypatch.setenv("GEMINI_API_KEY", "")
    monkeypatch.setenv("DATABASE_URL", "")
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("AGENT_MODE", "scripted")
    monkeypatch.setenv("GEMINI_FALLBACK_MODEL", "")  # tests that exercise the fallback model set it explicitly
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "sol.db"))
    monkeypatch.setenv("CACHE_PATH", str(tmp_path / "cache.db"))
    monkeypatch.setenv("PASSPORT_SIGNING_KEY", str(tmp_path / "key.pem"))
    monkeypatch.setenv("PVGIS_LIVE", "0")
    monkeypatch.setenv("CONTACT_EMAIL", "tests@sol-tests.dev")

    from app.config import get_settings
    from app.db import reset_repos
    from app.services import geo, irradiance
    from app.services.agent import gemini_provider, runner
    from app.services.scraper import fetch

    get_settings.cache_clear()
    reset_repos()
    irradiance.clear_memory()
    gemini_provider.clear_cache()
    runner.LOCKS.clear()
    runner.PER_CONVERSATION.reset()
    runner.GLOBAL.reset()
    runner.set_provider_override(None)
    monkeypatch.setattr(geo, "client_factory", _offline_client)
    monkeypatch.setattr(geo, "MIN_INTERVAL_S", 0.0)
    monkeypatch.setattr(fetch, "client_factory", _offline_client)
    monkeypatch.setattr(fetch, "MIN_INTERVAL_S", 0.0)
    yield
    runner.set_provider_override(None)
    runner.LOCKS.clear()
    reset_repos()
    get_settings.cache_clear()


TEST_USER = {"name": "Test Family", "email": "family@sol-tests.dev", "password": "correct-horse-9",
             "household_name": "Test Family", "city": "Quezon City", "lat": 14.676, "lon": 121.0437,
             "monthly_kwh": 450, "household_template": "balanced"}


def _new_client():
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.services import auth

    auth.THROTTLE.clear()
    return TestClient(create_app())


@pytest.fixture()
def anon_client():
    """A client with no credentials."""
    with _new_client() as c:
        yield c


@pytest.fixture()
def client():
    """A separate client signed in as TEST_USER (a 450 kWh balanced household in Quezon City)."""
    with _new_client() as c:
        r = c.post("/api/auth/signup", json=TEST_USER)
        assert r.status_code == 201, r.text
        c.headers["Authorization"] = f"Bearer {r.json()['token']}"
        yield c