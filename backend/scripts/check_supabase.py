"""Check the live Supabase connection and schema. Leaves no data behind.

Usage (from backend/):  python scripts/check_supabase.py
Covers: connection, idempotent schema, sessions, cache, products, the append-only ledger rules and row-level security.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import get_settings  # noqa: E402


def main() -> int:
    url = get_settings().database_url
    if not url:
        print("DATABASE_URL is not set in backend/.env")
        return 2
    import psycopg

    from app.db.pg_repo import PostgresRepository

    repo = PostgresRepository(url)
    try:
        repo.init_schema()
        print("ok  schema applied (idempotent)")

        sid = "selftest-session-0001"
        repo.save_session(sid, {"a": 1, "nested": {"x": [1, 2.5]}})
        assert repo.get_session(sid) == {"a": 1, "nested": {"x": [1, 2.5]}}
        repo.save_session(sid, {"a": 2})
        assert repo.get_session(sid) == {"a": 2}
        assert repo.delete_session(sid) is True and repo.get_session(sid) is None
        print("ok  sessions: save, update, read, delete")

        repo.cache_set("selftest", {"v": 1}, ttl_s=60)
        assert repo.cache_get("selftest") == {"v": 1}
        repo.cache_set("selftest", {"v": 1}, ttl_s=-1)
        assert repo.cache_get("selftest") is None
        print("ok  cache: ttl respected")

        repo.upsert_products([{"id": "selftest-p", "category": "panel", "price_php": 1}])
        assert [p["id"] for p in repo.list_products("panel")] == ["selftest-p"]
        with repo.pool.connection() as c:
            c.execute("delete from products where id = 'selftest-p'")
        print("ok  products")

        # Ledger rules, inside a transaction that is rolled back so nothing is stored.
        with repo.pool.connection() as c:
            c.execute("insert into ledger (id, body_json, prev_hash, hash, signature, created_at) values ('SELFTEST','{}','0','h','s','t')")
            blocked = {}
            for name, sql in (("update", "update ledger set body_json = 'x' where id = 'SELFTEST'"),
                              ("delete", "delete from ledger where id = 'SELFTEST'")):
                try:
                    with c.transaction():
                        c.execute(sql)
                    blocked[name] = False
                except psycopg.errors.RaiseException:
                    blocked[name] = True
            c.rollback()
        assert all(blocked.values()), blocked
        print("ok  ledger is append-only (UPDATE and DELETE are rejected)")

        with repo.pool.connection() as c:
            left = c.execute("select count(*) as n from ledger where id = 'SELFTEST'").fetchone()["n"]
            rls = {r["relname"]: r["relrowsecurity"] for r in c.execute(
                "select relname, relrowsecurity from pg_class where relname in ('sessions','products','ledger','cache')").fetchall()}
        assert left == 0, "test row was left in the ledger"
        assert all(rls.values()) and len(rls) == 4, rls
        print("ok  row-level security enabled on", ", ".join(sorted(rls)))
        print("\nSupabase is ready.")
        return 0
    except AssertionError as exc:
        print("FAILED:", exc)
        return 1
    finally:
        repo.close()


if __name__ == "__main__":
    sys.exit(main())
