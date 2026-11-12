"""Supabase (Postgres) implementation. Connects with a plain Postgres URL (use the session pooler)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .base import GENESIS_HASH, LedgerError, Repository

MIGRATION = Path(__file__).resolve().parent.parent.parent / "migrations" / "001_init.sql"
LEDGER_LOCK_KEY = 74_201_001


class PostgresRepository(Repository):
    kind = "supabase"

    def __init__(self, url: str, *, connect_timeout: int = 5):
        from psycopg.rows import dict_row
        from psycopg_pool import ConnectionPool

        self.pool = ConnectionPool(
            url,
            min_size=1,
            max_size=4,
            open=False,
            timeout=connect_timeout + 10,
            kwargs={
                "row_factory": dict_row,
                "connect_timeout": connect_timeout,
                # Supabase's transaction-mode pooler does not support prepared statements.
                "prepare_threshold": None,
            },
        )
        self.pool.open(wait=True, timeout=connect_timeout + 10)

    def close(self) -> None:
        self.pool.close()

    # --- lifecycle -------------------------------------------------
    def init_schema(self) -> None:
        blocks = [b.strip() for b in MIGRATION.read_text(encoding="utf-8").split("\n--;;\n")]
        with self.pool.connection() as conn:
            for block in blocks:
                if block:
                    conn.execute(block)

    def ping(self) -> bool:
        try:
            with self.pool.connection() as conn:
                conn.execute("select 1")
            return True
        except Exception:
            return False

    # --- sessions --------------------------------------------------
    def get_session(self, session_id: str) -> dict | None:
        with self.pool.connection() as conn:
            row = conn.execute("select state from sessions where id = %s", (session_id,)).fetchone()
        return row["state"] if row else None

    def save_session(self, session_id: str, state: dict) -> None:
        from psycopg.types.json import Jsonb

        with self.pool.connection() as conn:
            conn.execute(
                "insert into sessions (id, state, updated_at) values (%s, %s, now()) "
                "on conflict (id) do update set state = excluded.state, updated_at = now()",
                (session_id, Jsonb(state)),
            )

    def delete_session(self, session_id: str) -> bool:
        with self.pool.connection() as conn:
            cur = conn.execute("delete from sessions where id = %s", (session_id,))
            return cur.rowcount > 0

    # --- products --------------------------------------------------
    def upsert_products(self, products: list[dict]) -> None:
        from psycopg.types.json import Jsonb

        with self.pool.connection() as conn:
            for p in products:
                conn.execute(
                    "insert into products (id, category, data, updated_at) values (%s, %s, %s, now()) "
                    "on conflict (id) do update set category = excluded.category, "
                    "data = excluded.data, updated_at = now()",
                    (p["id"], p["category"], Jsonb(p)),
                )

    def list_products(self, category: str | None = None) -> list[dict]:
        with self.pool.connection() as conn:
            if category:
                rows = conn.execute("select data from products where category = %s order by id", (category,))
            else:
                rows = conn.execute("select data from products order by id")
            return [r["data"] for r in rows.fetchall()]

    # --- ledger ----------------------------------------------------
    def append_ledger(self, make_record: Callable[[str], dict]) -> dict:
        try:
            with self.pool.connection() as conn:
                conn.execute("select pg_advisory_xact_lock(%s)", (LEDGER_LOCK_KEY,))
                row = conn.execute("select hash from ledger order by seq desc limit 1").fetchone()
                prev_hash = row["hash"] if row else GENESIS_HASH
                rec = make_record(prev_hash)
                conn.execute(
                    "insert into ledger (id, body_json, prev_hash, hash, signature, created_at) "
                    "values (%s, %s, %s, %s, %s, %s)",
                    (rec["id"], rec["body_json"], prev_hash, rec["hash"], rec["signature"], rec["created_at"]),
                )
        except LedgerError:
            raise
        except Exception as exc:
            if exc.__class__.__module__.startswith("psycopg"):
                raise LedgerError(str(exc)) from exc
            raise
        return {**rec, "prev_hash": prev_hash}

    def get_ledger(self, record_id: str) -> dict | None:
        with self.pool.connection() as conn:
            return conn.execute("select * from ledger where id = %s", (record_id,)).fetchone()

    def ledger_all(self) -> list[dict]:
        with self.pool.connection() as conn:
            return list(conn.execute("select * from ledger order by seq").fetchall())

    # --- cache -----------------------------------------------------
    def cache_get(self, key: str) -> Any | None:
        with self.pool.connection() as conn:
            row = conn.execute("select value, expires_at from cache where key = %s", (key,)).fetchone()
        if not row:
            return None
        if row["expires_at"] is not None and row["expires_at"] < time.time():
            return None
        return row["value"]

    def cache_set(self, key: str, value: Any, ttl_s: float | None = None) -> None:
        from psycopg.types.json import Jsonb

        expires = time.time() + ttl_s if ttl_s else None
        with self.pool.connection() as conn:
            conn.execute(
                "insert into cache (key, value, expires_at) values (%s, %s, %s) "
                "on conflict (key) do update set value = excluded.value, expires_at = excluded.expires_at",
                (key, Jsonb(value), expires),
            )
