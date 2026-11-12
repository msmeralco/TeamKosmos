"""Accounts: password hashing (scrypt), opaque login tokens stored as SHA-256 hashes, and the current-user dependency."""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import threading
import time
import uuid
from dataclasses import dataclass

from fastapi import Header

from ..db import UserExists, get_repo
from ..errors import ApiError
from . import limits

TOKEN_TTL_S = 30 * 24 * 3600
MIN_PASSWORD = 8
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
TEMPLATES = ("night_heavy", "balanced", "day_heavy")
_SCRYPT = {"n": 2**14, "r": 8, "p": 1}
_DUMMY_HASH: str | None = None


# ---- passwords ----------------------------------------------------------------------------------------------------
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, dklen=32, **_SCRYPT)
    return "scrypt${n}${r}${p}${}${}".format(base64.b64encode(salt).decode(), base64.b64encode(digest).decode(), **_SCRYPT)


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt, expected = base64.b64decode(salt_b64), base64.b64decode(digest_b64)
        actual = hashlib.scrypt(password.encode(), salt=salt, dklen=len(expected), n=int(n), r=int(r), p=int(p))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(actual, expected)


# ---- login throttle -----------------------------------------------------------------------------------------------
class _Throttle:
    """Blocks an email after repeated failures so passwords cannot be guessed quickly."""

    def __init__(self, limit: int = 8, window_s: float = 300.0):
        self.limit, self.window_s = limit, window_s
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = [t for t in self._fails.get(key, []) if now - t < self.window_s]
            self._fails[key] = hits
            return len(hits) >= self.limit

    def fail(self, key: str) -> None:
        with self._lock:
            self._fails.setdefault(key, []).append(time.monotonic())

    def clear(self, key: str | None = None) -> None:
        with self._lock:
            if key is None:
                self._fails.clear()
            else:
                self._fails.pop(key, None)


THROTTLE = _Throttle()


# ---- users --------------------------------------------------------------------------------------------------------
def normalize_email(email: str) -> str:
    e = (email or "").strip().lower()
    if not EMAIL_RE.match(e) or len(e) > 254:
        raise ApiError("invalid_email", "Enter a valid email address.", status=422)
    return e


def check_password(password: str) -> None:
    if len(password or "") < MIN_PASSWORD:
        raise ApiError("weak_password", f"Password must be at least {MIN_PASSWORD} characters.", status=422)
    if len(password) > 200:
        raise ApiError("invalid_password", "Password is too long.", status=422)


def public_user(u: dict) -> dict:
    """What the frontend may see. Never includes the password hash."""
    name = u["name"]
    parts = [w for w in re.split(r"\s+", name.strip()) if w]
    initials = "".join(w[0] for w in parts[:2]).upper() or name[:1].upper()
    return {
        "id": u["id"], "email": u["email"], "name": name, "initials": initials,
        "household": {
            "name": u.get("household_name") or name, "city": u.get("city"), "lat": u.get("lat"), "lon": u.get("lon"),
            "monthlyKwh": u.get("monthly_kwh"), "template": u.get("household_template"),
        },
    }


def validate_household(fields: dict) -> dict:
    """Clean the optional household fields. Unknown keys are dropped, bad values raise a 422."""
    out: dict = {}
    for key in ("household_name", "city"):
        if fields.get(key) is not None:
            val = str(fields[key]).strip()
            out[key] = val[:80] or None
    if fields.get("household_template") is not None:
        if fields["household_template"] not in TEMPLATES:
            raise ApiError("invalid_template", f"household_template must be one of {', '.join(TEMPLATES)}.", status=422)
        out["household_template"] = fields["household_template"]
    if fields.get("monthly_kwh") is not None:
        kwh = float(fields["monthly_kwh"])
        if not limits.KWH_MIN <= kwh <= limits.KWH_MAX:
            raise ApiError("invalid_kwh", f"Monthly usage must be between {limits.KWH_MIN:,.0f} and {limits.KWH_MAX:,.0f} kWh.", status=422)
        out["monthly_kwh"] = kwh
    lat, lon = fields.get("lat"), fields.get("lon")
    if lat is not None or lon is not None:
        if lat is None or lon is None or not (-90 <= float(lat) <= 90 and -180 <= float(lon) <= 180):
            raise ApiError("invalid_location", "Provide a valid latitude and longitude.", status=422)
        out["lat"], out["lon"] = float(lat), float(lon)
    return out


def create_user(*, email: str, password: str, name: str, **household) -> dict:
    email = normalize_email(email)
    name = (name or "").strip()
    if not name or len(name) > 80:
        raise ApiError("invalid_name", "Enter your name (up to 80 characters).", status=422)
    check_password(password)
    extra = validate_household(household)
    user = {
        "id": uuid.uuid4().hex, "email": email, "password_hash": hash_password(password), "name": name,
        "household_name": None, "city": None, "lat": None, "lon": None, "monthly_kwh": None, "household_template": None,
        "created_at": time.time(), **extra,
    }
    try:
        get_repo().create_user(user)
    except UserExists:
        raise ApiError("email_taken", "An account with that email already exists.", hint="Sign in instead.", status=409) from None
    return user


def authenticate(email: str, password: str) -> dict:
    global _DUMMY_HASH
    key = (email or "").strip().lower()
    if THROTTLE.blocked(key):
        raise ApiError("too_many_attempts", "Too many failed sign-in attempts.", hint="Wait a few minutes and try again.", status=429)
    user = get_repo().get_user_by_email(key)
    if user is None:  # spend the same time as a real check so response timing does not reveal which emails exist
        _DUMMY_HASH = _DUMMY_HASH or hash_password(secrets.token_hex(8))
        verify_password(password or "", _DUMMY_HASH)
    ok = user is not None and verify_password(password or "", user["password_hash"])
    if not ok:
        THROTTLE.fail(key)
        raise ApiError("invalid_credentials", "Incorrect email or password.", status=401)
    THROTTLE.clear(key)
    return user


# ---- tokens -------------------------------------------------------------------------------------------------------
def _digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def issue_token(user_id: str) -> str:
    repo = get_repo()
    repo.purge_expired_tokens()
    token = secrets.token_urlsafe(32)
    repo.create_token(_digest(token), user_id, time.time() + TOKEN_TTL_S)
    return token


def revoke_token(token: str) -> None:
    get_repo().delete_token(_digest(token))


def _bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, value = authorization.partition(" ")
    return value.strip() if scheme.lower() == "bearer" and value.strip() else None


@dataclass
class AuthContext:
    user: dict
    token: str


def _unauthorized() -> ApiError:
    return ApiError("unauthorized", "Please sign in.", status=401)


def require_auth(authorization: str | None = Header(default=None)) -> AuthContext:
    """FastAPI dependency: resolves the Bearer token to a user or raises 401."""
    token = _bearer(authorization)
    if not token:
        raise _unauthorized()
    repo = get_repo()
    row = repo.get_token(_digest(token))
    if not row or row["expires_at"] < time.time():
        raise _unauthorized()
    user = repo.get_user(row["user_id"])
    if not user:
        raise _unauthorized()
    return AuthContext(user=user, token=token)
