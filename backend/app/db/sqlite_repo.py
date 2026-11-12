"""SQLite implementation: offline fallback, test database and local cache."""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Callable

from .base import GENESIS_HASH, LedgerError, Repository

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    state TEXT NOT NULL,
    updated_at REAL NOT NULL
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

    def save_session(self, session_id: str, state: dict) -> None:
        with self._lock, closing(self._connect()) as conn:
            conn.execute(
                "INSERT INTO sessions (id, state, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET state = excluded.state, updated_at = excluded.updated_at",
                (session_id, _dumps(state), time.time()),
            )
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
