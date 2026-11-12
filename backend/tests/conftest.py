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


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c
