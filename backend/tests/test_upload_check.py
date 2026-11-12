"""Sketch-canvas upload guardrail: POST /api/roof/check-upload."""
from __future__ import annotations

import pytest

from app.services import upload_check

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n" + b"0" * 64


@pytest.fixture(autouse=True)
def _clean():
    upload_check.LIMITER.reset()
    upload_check.set_classifier_override(None)
    yield
    upload_check.set_classifier_override(None)
    upload_check.LIMITER.reset()


def _post(client, data=PNG, name="roof.png", mime="image/png"):
    return client.post("/api/roof/check-upload", files={"file": (name, data, mime)})


def _verdict(category, relevant=True, confidence=0.9, reason="A roof."):
    return lambda att, settings: {"category": category, "solar_relevant": relevant, "confidence": confidence, "reason": reason}


@pytest.mark.parametrize("cat", ["roof_photo", "site_plan", "blueprint", "satellite_view"])
def test_on_topic_files_are_allowed(client, cat):
    upload_check.set_classifier_override(_verdict(cat))
    r = _post(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["allowed"] is True and body["verified"] is True and body["category"] == cat


def test_pdf_is_accepted(client):
    upload_check.set_classifier_override(_verdict("blueprint"))
    r = _post(client, PDF, "plan.pdf", "application/pdf")
    assert r.status_code == 200 and r.json()["allowed"] is True and r.json()["mime"] == "application/pdf"


def test_off_topic_file_is_rejected(client):
    upload_check.set_classifier_override(_verdict("other", relevant=False, reason="A plate of food."))
    body = _post(client).json()
    assert body["allowed"] is False and body["verified"] is True and "roof photo" in body["reason"]


def test_bill_points_to_chat(client):
    upload_check.set_classifier_override(_verdict("electricity_bill"))
    body = _post(client).json()
    assert body["allowed"] is False and "chat" in body["reason"]


def test_low_confidence_is_rejected(client):
    upload_check.set_classifier_override(_verdict("roof_photo", confidence=0.2))
    assert _post(client).json()["allowed"] is False


def test_gemini_error_fails_open(client):
    def boom(att, settings):
        raise RuntimeError("down")

    upload_check.set_classifier_override(boom)
    body = _post(client).json()
    assert body["allowed"] is True and body["verified"] is False


def test_malformed_model_output_fails_open(client):
    upload_check.set_classifier_override(lambda a, s: {"category": "nonsense"})
    body = _post(client).json()
    assert body["allowed"] is True and body["verified"] is False


def test_no_llm_configured_fails_open(client):
    body = _post(client).json()  # tests run with no Gemini key
    assert body["allowed"] is True and body["verified"] is False


def test_wrong_file_type_is_blocked_even_when_unverified(client):
    r = _post(client, b"MZ not an image", "x.exe", "application/octet-stream")
    assert r.status_code == 415 and r.json()["detail"]["code"] == "unsupported_file_type"


def test_empty_and_oversize_files_are_blocked(client, monkeypatch):
    assert _post(client, b"").status_code == 422
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "100")
    from app.config import get_settings

    get_settings.cache_clear()
    r = _post(client, PNG + b"0" * 200)
    assert r.status_code == 413 and r.json()["detail"]["code"] == "file_too_large"


def test_requires_sign_in(anon_client):
    r = anon_client.post("/api/roof/check-upload", files={"file": ("a.png", PNG, "image/png")})
    assert r.status_code == 401


def test_missing_file_is_a_422(client):
    assert client.post("/api/roof/check-upload").status_code == 422


def test_rate_limit(client):
    upload_check.set_classifier_override(_verdict("roof_photo"))
    codes = [_post(client).status_code for _ in range(upload_check.RATE_LIMIT + 1)]
    assert codes[:-1] == [200] * upload_check.RATE_LIMIT and codes[-1] == 429
