"""Solar Passport: canonical JSON, hash chain, Ed25519 signature, verification (see plan section 7.11).

hash = SHA256(canonical_body || prev_hash);  signature = Ed25519(hash).  The ledger is append-only.
The Passport verifies the RECORD (unchanged, signed by Sol, sourced inputs, reproducible), not the household's real roof.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

from ..config import BACKEND_DIR, get_settings
from ..db import GENESIS_HASH, get_repo
from ..errors import ApiError
from ..models import RoofModel
from . import load as load_svc
from . import simulate

DISCLOSURE = ("Demo data is synthetic and every result is an estimate for a licensed installer to confirm. "
              "This Passport verifies the record (unchanged, signed, sourced, reproducible), not the household's real roof or usage.")
FLOAT_DIGITS = 6
_key_lock = threading.Lock()
_key_cache: dict[str, Ed25519PrivateKey] = {}


# ---- canonical form + hashing -----------------------------------------------------------------------------
def _round(obj):
    if isinstance(obj, float):
        return round(obj, FLOAT_DIGITS)
    if isinstance(obj, dict):
        return {str(k): _round(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round(v) for v in obj]
    return obj


def canonical(body: dict) -> str:
    return json.dumps(_round(body), sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(body_json: str, prev_hash: str) -> str:
    return hashlib.sha256((body_json + prev_hash).encode("utf-8")).hexdigest()


# ---- signing key ---------------------------------------------------------------------------------------------
def _private_key() -> Ed25519PrivateKey:
    path = Path(get_settings().signing_key_path)
    key = str(path)
    with _key_lock:
        if key in _key_cache:
            return _key_cache[key]
        if path.exists():
            pk = serialization.load_pem_private_key(path.read_bytes(), password=None)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            pk = Ed25519PrivateKey.generate()
            path.write_bytes(pk.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                              serialization.NoEncryption()))
        _key_cache[key] = pk  # type: ignore[assignment]
        return pk  # type: ignore[return-value]


def public_key_hex() -> str:
    return _private_key().public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw).hex()


def sign(hash_hex: str) -> str:
    return _private_key().sign(hash_hex.encode("ascii")).hex()


def signature_valid(hash_hex: str, signature_hex: str) -> bool:
    try:
        pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public_key_hex()))
        pub.verify(bytes.fromhex(signature_hex), hash_hex.encode("ascii"))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False


def reset_key_cache() -> None:
    _key_cache.clear()


# ---- body construction -----------------------------------------------------------------------------------------
def model_version() -> str:
    try:
        out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=Path(BACKEND_DIR).parent, capture_output=True,
                             text=True, timeout=3)
        return out.stdout.strip() or "unversioned"
    except (OSError, subprocess.SubprocessError):
        return "unversioned"


def _sourced_check(assumptions: list[dict]) -> dict:
    missing = [a["key"] for a in assumptions if not a.get("source_url") and not a.get("note")]
    unverified = [a["key"] for a in assumptions if not a.get("verified")]
    if missing:
        return {"name": "sourced_inputs", "method": "Every assumption carries a source or a disclosed note.",
                "status": "fail", "detail": f"No source or note: {', '.join(missing)}"}
    if unverified:
        return {"name": "sourced_inputs",
                "method": "Every assumption carries a source or a disclosed note; unverified placeholders are listed.",
                "status": "n/a", "detail": f"{len(unverified)} assumptions are judgement or unverified placeholders: {', '.join(unverified[:12])}"}
    return {"name": "sourced_inputs", "method": "Every assumption has a source URL and an as-of date.", "status": "pass", "detail": ""}


def _key_numbers(roi: dict) -> list[float]:
    nums: list[float] = []
    for variant in ("on_grid", "hybrid"):
        for sc in (roi.get(variant) or {}).get("scenarios", []):
            nums += [sc["year1_savings_php"], sc["net_profit_25y_php"], sc["year1_generation_kwh"]]
    return nums


def _reproduce(inputs: dict, package: dict, results: dict) -> dict:
    try:
        roof = RoofModel.model_validate(inputs["roof"])
        ld = load_svc.estimate_load(**inputs["load"]["params"])
        redo = simulate.simulate_package(package, roof, ld, years=results.get("years"),
                                         export_credit_php_per_kwh=results.get("export_credit_php_per_kwh"),
                                         tariff_php_per_kwh=results.get("tariff_php_per_kwh"))
        a, b = _key_numbers(results), _key_numbers(redo)
        ok = len(a) == len(b) and all(abs(x - y) <= 1.0 for x, y in zip(a, b))
        return {"name": "reproducible", "method": "Re-ran the engine on the stored inputs and compared savings, profit and generation.",
                "status": "pass" if ok else "fail", "detail": "" if ok else "Results differ from the stored record."}
    except Exception as exc:  # noqa: BLE001 - verification must never crash the endpoint
        return {"name": "reproducible", "method": "Re-ran the engine on the stored inputs.", "status": "n/a",
                "detail": f"Could not re-run: {exc.__class__.__name__}"}


def issue(*, inputs: dict, package: dict, results: dict) -> dict:
    """Create, sign and append a Passport. inputs = {roof, load: {params, summary}, budget_php, goal, ...}."""
    pid = "SOL-" + uuid.uuid4().hex[:10].upper()
    created = datetime.now(timezone.utc).isoformat(timespec="seconds")
    assumptions = results.get("assumptions_used", [])
    body = {
        # The ledger a record lives in is part of the signed body: a record issued while the app was running on the
        # local SQLite fallback is NOT in the Supabase chain, and verification says so instead of failing silently.
        "id": pid, "created_at": created, "model_version": model_version(), "disclosure": DISCLOSURE,
        "ledger": get_repo().kind,
        "inputs": inputs, "assumptions": assumptions, "package": package, "results": results,
        "verification": {"checks": [_sourced_check(assumptions), _reproduce(inputs, package, results)]},
    }
    body_json = canonical(body)

    def make(prev_hash: str) -> dict:
        h = compute_hash(body_json, prev_hash)
        return {"id": pid, "body_json": body_json, "hash": h, "signature": sign(h), "created_at": created}

    rec = get_repo().append_ledger(make)
    return _public(rec, body)


def _public(rec: dict, body: dict | None = None) -> dict:
    return {
        "id": rec["id"], "created_at": rec["created_at"], "hash": rec["hash"], "prev_hash": rec["prev_hash"],
        "signature": rec["signature"], "public_key": public_key_hex(), "short_hash": rec["hash"][:12],
        "verify_path": f"/verify/{rec['id']}", "body": body if body is not None else json.loads(rec["body_json"]),
    }


def get(record_id: str) -> dict:
    rec = get_repo().get_ledger(record_id)
    if not rec:
        raise ApiError("not_found", "No Solar Passport with that id.", status=404)
    return _public(rec)


# ---- verification ------------------------------------------------------------------------------------------------------
def _check(name: str, ok: bool | None, detail: str = "") -> dict:
    return {"name": name, "status": "n/a" if ok is None else ("pass" if ok else "fail"), "detail": detail}


def verify_values(*, body: dict, claimed_hash: str, prev_hash: str, signature: str) -> dict:
    """Core verification used by both the stored-record and paste-to-verify paths."""
    body_json = canonical(body)
    recomputed = compute_hash(body_json, prev_hash)
    checks = [
        _check("integrity", recomputed == claimed_hash,
               "" if recomputed == claimed_hash else "The record's contents no longer match its hash."),
        _check("signature", signature_valid(claimed_hash, signature),
               "" if signature_valid(claimed_hash, signature) else "The signature is not valid for this hash."),
    ]
    rows = get_repo().ledger_all()
    pos = next((i for i, r in enumerate(rows) if r["id"] == body.get("id")), None)
    if pos is None:
        where = body.get("ledger")
        here = get_repo().kind
        extra = f" It was issued on the '{where}' ledger and this server is using '{here}'." if where and where != here else ""
        checks.append(_check("chain", False, "This record is not in Sol's ledger." + extra))
    else:
        expected_prev = rows[pos - 1]["hash"] if pos > 0 else GENESIS_HASH
        ok = rows[pos]["hash"] == claimed_hash and rows[pos]["prev_hash"] == prev_hash == expected_prev
        if ok and pos + 1 < len(rows):
            ok = rows[pos + 1]["prev_hash"] == claimed_hash
        checks.append(_check("chain", ok, "" if ok else "The chain link to neighbouring records does not hold."))
    stored_checks = {c["name"]: c for c in (body.get("verification", {}) or {}).get("checks", [])}
    src = stored_checks.get("sourced_inputs") or _sourced_check(body.get("assumptions", []))
    checks.append({"name": "sourced_inputs", "status": src["status"], "detail": src.get("detail", "")})
    try:
        redo = _reproduce(body["inputs"], body["package"], body["results"])
    except (KeyError, TypeError):
        redo = {"status": "fail", "detail": "The record is missing its inputs."}
    checks.append({"name": "reproducible", "status": redo["status"], "detail": redo.get("detail", "")})
    hard = [c for c in checks if c["name"] in ("integrity", "signature", "chain")]
    valid = all(c["status"] == "pass" for c in hard) and all(c["status"] != "fail" for c in checks)
    return {"valid": valid, "checks": checks, "id": body.get("id"), "short_hash": claimed_hash[:12],
            "public_key": public_key_hex(), "disclosure": DISCLOSURE}


def verify_stored(record_id: str) -> dict:
    rec = get_repo().get_ledger(record_id)
    if not rec:
        raise ApiError("not_found", "No Solar Passport with that id.", status=404)
    body = json.loads(rec["body_json"])
    out = verify_values(body=body, claimed_hash=rec["hash"], prev_hash=rec["prev_hash"], signature=rec["signature"])
    # Integrity must also hold against the stored text, not only its re-canonicalised form.
    if canonical(body) != rec["body_json"]:
        out["valid"] = False
        for c in out["checks"]:
            if c["name"] == "integrity":
                c.update(status="fail", detail="The stored text is not in canonical form.")
    out["passport"] = _public(rec, body)
    return out


def verify_pasted(record: dict) -> dict:
    """Paste-to-verify: the pasted record is checked against Sol's own key and ledger, never its own claims."""
    try:
        body = record["body"] if "body" in record else json.loads(record["body_json"])
        claimed, prev, sig = str(record["hash"]), str(record["prev_hash"]), str(record["signature"])
    except (KeyError, TypeError, ValueError):
        raise ApiError("invalid_record", "The pasted text is not a Solar Passport record.",
                       hint="Paste the full downloaded JSON.", status=422)
    if not isinstance(body, dict):
        raise ApiError("invalid_record", "The pasted record has no body.", status=422)
    return verify_values(body=body, claimed_hash=claimed, prev_hash=prev, signature=sig)


def html_page(record_id: str) -> str:
    """Minimal no-JS verify page for /verify/{id} (green or red)."""
    try:
        res = verify_stored(record_id)
    except ApiError:
        return ("<!doctype html><meta charset=utf-8><title>Sol Passport</title>"
                "<body style='font-family:system-ui;max-width:640px;margin:3rem auto'>"
                "<h1 style='color:#b00020'>Not found</h1><p>No Solar Passport with that id.</p>")
    ok = res["valid"]
    rows = "".join(f"<li><b>{c['name']}</b>: {c['status']}{(' - ' + c['detail']) if c['detail'] else ''}</li>" for c in res["checks"])
    colour, word = ("#1b7f3b", "Verified") if ok else ("#b00020", "Verification failed")
    return (f"<!doctype html><meta charset=utf-8><title>Sol Passport {res['id']}</title>"
            f"<body style='font-family:system-ui;max-width:640px;margin:3rem auto;line-height:1.5'>"
            f"<h1 style='color:{colour}'>{word}</h1><p>Solar Passport <code>{res['id']}</code> · hash <code>{res['short_hash']}</code></p>"
            f"<ul>{rows}</ul><p><small>Public key: <code>{res['public_key']}</code></small></p><p><small>{res['disclosure']}</small></p>")
