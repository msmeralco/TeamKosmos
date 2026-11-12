"""Demo rewards: the solar owner's Passport and sample vouchers (see docs/superpowers/specs/2026-11-12-passport-vouchers-design.md).

Only accounts with a stored Passport id see anything. There is no confirm-install flow: the 'installed' fact is part of the
signed Passport body written by scripts/seed_owner.py.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time
from pathlib import Path

from cryptography.hazmat.primitives import serialization

from ..config import BACKEND_DIR
from ..db import get_repo
from ..errors import ApiError
from . import passport

VOUCHERS_PATH = Path(BACKEND_DIR) / "data" / "vouchers.json"


def _catalog() -> list[dict]:
    return json.loads(VOUCHERS_PATH.read_text(encoding="utf-8"))["vouchers"]


def _code(passport_id: str, voucher_id: str) -> str:
    raw = passport._private_key().private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    mac = hmac.new(hashlib.sha256(raw).digest(), f"{passport_id}:{voucher_id}".encode(), hashlib.sha256).hexdigest()[:8].upper()
    return f"{mac[:4]}-{mac[4:]}"


def _passport_view(passport_id: str) -> dict | None:
    try:
        rec = passport.get(passport_id)
    except ApiError:  # stored id is not in the active ledger (for example a different database)
        return None
    body, pkg = rec["body"], rec["body"].get("package", {})
    return {
        "id": rec["id"], "short_hash": rec["short_hash"], "created_at": rec["created_at"], "verify_path": rec["verify_path"],
        "installation": (body.get("inputs") or {}).get("installation"),
        "option": pkg.get("label") or "Selected option", "panels": pkg.get("panel_count"), "kwp": pkg.get("kwp"),
        "capex_php": pkg.get("capex_php"), "valid": passport.verify_stored(passport_id)["valid"],
    }


def issue_owner_passport(user: dict, *, reissue: bool = False) -> str:
    """Seed helper: issue a real, signed, installed Passport for a demo household. Returns 'kept', 'issued' or 'broken'."""
    from . import geo, load as load_svc, optimizer
    from .agent.tools import jsonable

    repo = get_repo()
    pid = repo.get_user_passport(user["id"])
    if pid and not reissue:
        view = _passport_view(pid)
        return "kept" if view and view["valid"] else "broken"
    roof = geo.roof_from_address(user["lat"], user["lon"])
    params = {"monthly_kwh": user["monthly_kwh"], "template": user["household_template"] or "balanced", "basis": "persona"}
    ld = load_svc.estimate_load(**params)
    res = jsonable(optimizer.optimize(roof, ld, budget_max_php=500_000, goal="max_savings_10y", system_type="on_grid"))
    item = res["packages"][0]
    inputs = {
        "roof": jsonable(roof.model_dump()), "load": {"params": params, "summary": ld.to_dict(include_hourly=False)},
        "budget_php": [0.0, 500_000], "goal": "max_savings_10y", "goal_target_pct": None, "backup_hours": None, "net_metering": True,
        "household": user["name"],
        "installation": {"installer": "Sample Solar Installer (demo)", "installed_on": time.strftime("%Y-%m-%d"), "sample": True},
    }
    rec = passport.issue(inputs=jsonable(inputs), package=item["package"], results=item["roi"])
    repo.set_user_passport(user["id"], rec["id"])
    return "issued"


def overview(user: dict) -> dict:
    pid = get_repo().get_user_passport(user["id"])
    view = _passport_view(pid) if pid else None
    if view is None:
        return {"passport": None, "vouchers": []}
    done = {r["voucher_id"]: r for r in get_repo().list_redemptions(user["id"])}
    vouchers = [{**v, "redeemed": v["id"] in done, "code": done[v["id"]]["code"] if v["id"] in done else None,
                 "redeemed_at": done[v["id"]]["redeemed_at"] if v["id"] in done else None} for v in _catalog()]
    return {"passport": view, "vouchers": vouchers}


def redeem(user: dict, voucher_id: str) -> dict:
    pid = get_repo().get_user_passport(user["id"])
    if not pid or _passport_view(pid) is None:
        raise ApiError("no_passport", "This account has no Solar Passport.", status=404)
    if voucher_id not in {v["id"] for v in _catalog()}:
        raise ApiError("not_found", "No voucher with that id.", status=404)
    if not get_repo().redeem_voucher(user["id"], voucher_id, _code(pid, voucher_id), time.time()):
        raise ApiError("already_redeemed", "This voucher has already been redeemed.", status=409)
    return overview(user)
