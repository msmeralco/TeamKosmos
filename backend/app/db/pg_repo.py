"""Supabase (Postgres) implementation. Connects with a plain Postgres URL (use the session pooler)."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from .base import GENESIS_HASH, USER_FIELDS, LedgerError, Repository, UserExists

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent.parent / "migrations"
MIGRATION = MIGRATIONS_DIR / "001_init.sql"  # the base schema; init_schema applies every *.sql in order
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
        blocks = [b.strip() for f in sorted(MIGRATIONS_DIR.glob("*.sql")) for b in f.read_text(encoding="utf-8").split("\n--;;\n")]
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

    def save_session(self, session_id: str, state: dict, user_id: str | None = None, title: str | None = None) -> None:
        from psycopg.types.json import Jsonb

        with self.pool.connection() as conn:
            conn.execute(
                "insert into sessions (id, state, updated_at, user_id, title) values (%s, %s, now(), %s, %s) "
                "on conflict (id) do update set state = excluded.state, updated_at = now(), "
                "user_id = coalesce(sessions.user_id, excluded.user_id), title = coalesce(sessions.title, excluded.title)",
                (session_id, Jsonb(state), user_id, title),
            )

    def get_session_owner(self, session_id: str) -> str | None:
        with self.pool.connection() as conn:
            row = conn.execute("select user_id from sessions where id = %s", (session_id,)).fetchone()
        return row["user_id"] if row else None

    def list_sessions(self, user_id: str, limit: int = 100) -> list[dict]:
        with self.pool.connection() as conn:
            rows = conn.execute(
                "select id, title, extract(epoch from updated_at) as updated_at, state->>'turn_count' as turn_count "
                "from sessions where user_id = %s order by updated_at desc limit %s", (user_id, limit)).fetchall()
        return [{"id": r["id"], "title": r["title"] or "New chat", "turn_count": int(r["turn_count"] or 0),
                 "updated_at": float(r["updated_at"])} for r in rows]

    # --- users and tokens --------------------------------------------
    def create_user(self, user: dict) -> None:
        from psycopg.errors import UniqueViolation

        try:
            with self.pool.connection() as conn:
                conn.execute(
                    "insert into users (id, email, password_hash, name, household_name, city, lat, lon, monthly_kwh, "
                    "household_template, created_at) values (%(id)s, %(email)s, %(password_hash)s, %(name)s, "
                    "%(household_name)s, %(city)s, %(lat)s, %(lon)s, %(monthly_kwh)s, %(household_template)s, %(created_at)s)", user)
        except UniqueViolation as exc:
            raise UserExists(user["email"]) from exc

    def get_user(self, user_id: str) -> dict | None:
        with self.pool.connection() as conn:
            return conn.execute("select * from users where id = %s", (user_id,)).fetchone()

    def get_user_by_email(self, email: str) -> dict | None:
        with self.pool.connection() as conn:
            return conn.execute("select * from users where email = %s", (email,)).fetchone()

    def list_users(self) -> list[dict]:
        with self.pool.connection() as conn:
            return list(conn.execute("select * from users order by created_at").fetchall())

    def update_user(self, user_id: str, fields: dict) -> None:
        cols = [k for k in fields if k in USER_FIELDS]
        if not cols:
            return
        sets = ", ".join(f"{c} = %s" for c in cols)  # column names come from the USER_FIELDS allow list
        with self.pool.connection() as conn:
            conn.execute(f"update users set {sets} where id = %s", [fields[c] for c in cols] + [user_id])

    def create_token(self, token_hash: str, user_id: str, expires_at: float) -> None:
        with self.pool.connection() as conn:
            conn.execute("insert into auth_tokens (token_hash, user_id, expires_at) values (%s, %s, %s)", (token_hash, user_id, expires_at))

    def get_token(self, token_hash: str) -> dict | None:
        with self.pool.connection() as conn:
            return conn.execute("select user_id, expires_at from auth_tokens where token_hash = %s", (token_hash,)).fetchone()

    def delete_token(self, token_hash: str) -> None:
        with self.pool.connection() as conn:
            conn.execute("delete from auth_tokens where token_hash = %s", (token_hash,))

    def purge_expired_tokens(self) -> None:
        with self.pool.connection() as conn:
            conn.execute("delete from auth_tokens where expires_at < %s", (time.time(),))

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
