"""SQLite implementation: offline fallback, test database and local cache."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

from .base import GENESIS_HASH, USER_FIELDS, LedgerError, Repository, UserExists

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    name TEXT NOT NULL,
    household_name TEXT,
    city TEXT,
    lat REAL,
    lon REAL,
    monthly_kwh REAL,
    household_template TEXT,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_tokens (
    token_hash TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS products (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,
    data TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS ledger (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    id TEXT NOT NULL UNIQUE,
    body_json TEXT NOT NULL,
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL,
    signature TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS user_passports (
    user_id TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    passport_id TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS voucher_redemptions (
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    voucher_id TEXT NOT NULL,
    code TEXT NOT NULL,
    redeemed_at REAL NOT NULL,
    PRIMARY KEY (user_id, voucher_id)
);
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    expires_at REAL
);
CREATE TRIGGER IF NOT EXISTS ledger_no_update BEFORE UPDATE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
CREATE TRIGGER IF NOT EXISTS ledger_no_delete BEFORE DELETE ON ledger
BEGIN SELECT RAISE(ABORT, 'ledger is append-only'); END;
"""


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


class SQLiteRepository(Repository):
    kind = "sqlite"

    def __init__(self, path: str | Path):
        self.path = str(path)
        self._lock = threading.RLock()
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        return conn

    # --- lifecycle -------------------------------------------------
    def init_schema(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.executescript(SCHEMA)
            cols = {r["name"] for r in conn.execute("PRAGMA table_info(sessions)")}
            for col in ("user_id", "title"):  # databases created before auth existed
                if col not in cols:
                    conn.execute(f"ALTER TABLE sessions ADD COLUMN {col} TEXT")
            conn.execute("CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions (user_id, updated_at)")
            conn.commit()

    def ping(self) -> bool:
        try:
            with closing(self._connect()) as conn:
                conn.execute("SELECT 1")
            return True
        except sqlite3.Error:
            return False

    # --- sessions --------------------------------------------------
    def get_session(self, session_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT state FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return json.loads(row["state"]) if row else None

    def save_session(self, session_id: str, state: dict, user_id: str | None = None, title: str | None = None) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO sessions (id, state, updated_at, user_id, title) VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at, "
                "user_id = COALESCE(sessions.user_id, excluded.user_id), title = COALESCE(sessions.title, excluded.title)",
                (session_id, _dumps(state), time.time(), user_id, title),
            )
            conn.commit()

    def get_session_owner(self, session_id: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT user_id FROM sessions WHERE id = ?", (session_id,)).fetchone()
        return row["user_id"] if row else None

    def list_sessions(self, user_id: str, limit: int = 100) -> list[dict]:
        with closing(self._connect()) as conn:
            rows = conn.execute(
                "SELECT id, title, updated_at, json_extract(state, '$.turn_count') AS turn_count "
                "FROM sessions WHERE user_id = ? ORDER BY updated_at DESC LIMIT ?", (user_id, limit)).fetchall()
        return [{"id": r["id"], "title": r["title"] or "New chat", "turn_count": r["turn_count"] or 0, "updated_at": r["updated_at"]} for r in rows]

    # --- users and tokens --------------------------------------------
    def create_user(self, user: dict) -> None:
        try:
            with self._lock, closing(self._connect()) as conn:
                conn.execute(
                    "INSERT INTO users (id, email, password_hash, name, household_name, city, lat, lon, monthly_kwh, "
                    "household_template, created_at) VALUES (:id, :email, :password_hash, :name, :household_name, :city, "
                    ":lat, :lon, :monthly_kwh, :household_template, :created_at)", user)
                conn.commit()
        except sqlite3.IntegrityError as exc:
            raise UserExists(user["email"]) from exc

    def get_user(self, user_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_user_by_email(self, email: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict]:
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM users ORDER BY created_at")]

    def update_user(self, user_id: str, fields: dict) -> None:
        cols = [k for k in fields if k in USER_FIELDS]
        if not cols:
            return
        sets = ", ".join(f"{c} = ?" for c in cols)
        with self._lock, closing(self._connect()) as conn:
            conn.execute(f"UPDATE users SET {sets} WHERE id = ?", [fields[c] for c in cols] + [user_id])
            conn.commit()

    # --- rewards ---------------------------------------------------
    def set_user_passport(self, user_id: str, passport_id: str) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute("INSERT INTO user_passports (user_id, passport_id) VALUES (?, ?) "
                         "ON CONFLICT(user_id) DO UPDATE SET passport_id = excluded.passport_id", (user_id, passport_id))
            conn.commit()

    def get_user_passport(self, user_id: str) -> str | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT passport_id FROM user_passports WHERE user_id = ?", (user_id,)).fetchone()
        return row["passport_id"] if row else None

    def redeem_voucher(self, user_id: str, voucher_id: str, code: str, at: float) -> bool:
        with self._lock, closing(self._connect()) as conn:
            cur = conn.execute("INSERT OR IGNORE INTO voucher_redemptions (user_id, voucher_id, code, redeemed_at) VALUES (?, ?, ?, ?)",
                               (user_id, voucher_id, code, at))
            conn.commit()
            return cur.rowcount == 1

    def list_redemptions(self, user_id: str) -> list[dict]:
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute(
                "SELECT voucher_id, code, redeemed_at FROM voucher_redemptions WHERE user_id = ?", (user_id,))]

    def create_token(self, token_hash: str, user_id: str, expires_at: float) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute("INSERT INTO auth_tokens (token_hash, user_id, expires_at) VALUES (?, ?, ?)", (token_hash, user_id, expires_at))
            conn.commit()

    def get_token(self, token_hash: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT user_id, expires_at FROM auth_tokens WHERE token_hash = ?", (token_hash,)).fetchone()
        return dict(row) if row else None

    def delete_token(self, token_hash: str) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute("DELETE FROM auth_tokens WHERE token_hash = ?", (token_hash,))
            conn.commit()

    def purge_expired_tokens(self) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute("DELETE FROM auth_tokens WHERE expires_at < ?", (time.time(),))
            conn.commit()

    def delete_session(self, session_id: str) -> bool:
        with self._lock, closing(self._connect()) as conn:
            cur = conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            conn.commit()
            return cur.rowcount > 0

    # --- products --------------------------------------------------
    def upsert_products(self, products: list[dict]) -> None:
        now = time.time()
        with self._lock, closing(self._connect()) as conn:
            for p in products:
                conn.execute(
                    "INSERT INTO products (id, category, data, updated_at) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(id) DO UPDATE SET category = excluded.category, data = excluded.data, "
                    "updated_at = excluded.updated_at",
                    (p["id"], p["category"], _dumps(p), now),
                )
            conn.commit()

    def list_products(self, category: str | None = None) -> list[dict]:
        with closing(self._connect()) as conn:
            if category:
                rows = conn.execute("SELECT data FROM products WHERE category = ? ORDER BY id", (category,))
            else:
                rows = conn.execute("SELECT data FROM products ORDER BY id")
            return [json.loads(r["data"]) for r in rows.fetchall()]

    # --- ledger ----------------------------------------------------
    def append_ledger(self, make_record: Callable[[str], dict]) -> dict:
        with self._lock, closing(self._connect()) as conn:
            conn.execute("BEGIN IMMEDIATE")
            try:
                row = conn.execute("SELECT hash FROM ledger ORDER BY seq DESC LIMIT 1").fetchone()
                prev_hash = row["hash"] if row else GENESIS_HASH
                rec = make_record(prev_hash)
                conn.execute(
                    "INSERT INTO ledger (id, body_json, prev_hash, hash, signature, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (rec["id"], rec["body_json"], prev_hash, rec["hash"], rec["signature"], rec["created_at"]),
                )
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise LedgerError(str(exc)) from exc
            except Exception:
                conn.rollback()
                raise
        return {**rec, "prev_hash": prev_hash}

    def get_ledger(self, record_id: str) -> dict | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT * FROM ledger WHERE id = ?", (record_id,)).fetchone()
        return dict(row) if row else None

    def ledger_all(self) -> list[dict]:
        with closing(self._connect()) as conn:
            return [dict(r) for r in conn.execute("SELECT * FROM ledger ORDER BY seq")]

    # --- cache -----------------------------------------------------
    def cache_get(self, key: str) -> Any | None:
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT value, expires_at FROM cache WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        if row["expires_at"] is not None and row["expires_at"] < time.time():
            return None
        return json.loads(row["value"])

    def cache_set(self, key: str, value: Any, ttl_s: float | None = None) -> None:
        expires = time.time() + ttl_s if ttl_s else None
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO cache (key, value, expires_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value, expires_at = excluded.expires_at",
                (key, _dumps(value), expires),
            )
            conn.commit()
