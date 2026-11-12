import pytest

from app.db import GENESIS_HASH, LedgerError, db_status, get_cache, get_repo, reset_repos
from app.db.sqlite_repo import SQLiteRepository


def test_health_reports_sqlite_and_scripted(client):
    body = client.get("/api/health").json()
    assert body["status"] == "ok"
    assert body["db"]["active"] == "sqlite"
    assert body["llm"]["mode"] == "scripted"
    assert body["contact_email_is_placeholder"] is False  # tests set a non-placeholder email


def test_unknown_route_uses_error_shape(client):
    r = client.get("/api/nope")
    assert r.status_code == 404
    assert r.json()["detail"]["code"] == "not_found"


def test_session_roundtrip_and_delete():
    repo = get_repo()
    assert repo.get_session("a") is None
    repo.save_session("a", {"x": 1, "nested": {"y": [1, 2]}})
    assert repo.get_session("a") == {"x": 1, "nested": {"y": [1, 2]}}
    repo.save_session("a", {"x": 2})
    assert repo.get_session("a") == {"x": 2}
    assert repo.delete_session("a") is True
    assert repo.delete_session("a") is False


def _rec(i):
    def make(prev):
        return {"id": f"r{i}", "body_json": f'{{"n":{i}}}', "hash": f"h{i}-{prev[:4]}", "signature": "sig",
                "created_at": "2026-11-12T00:00:00Z"}
    return make


def test_ledger_chain_and_append_only():
    repo = get_repo()
    first = repo.append_ledger(_rec(1))
    assert first["prev_hash"] == GENESIS_HASH
    second = repo.append_ledger(_rec(2))
    assert second["prev_hash"] == first["hash"]
    assert [r["id"] for r in repo.ledger_all()] == ["r1", "r2"]

    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(repo.path)) as conn:
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("UPDATE ledger SET body_json = 'x' WHERE id = 'r1'")
        with pytest.raises(sqlite3.DatabaseError):
            conn.execute("DELETE FROM ledger WHERE id = 'r1'")


def test_ledger_rejects_duplicate_id():
    repo = get_repo()
    repo.append_ledger(_rec(1))
    with pytest.raises(LedgerError):
        repo.append_ledger(_rec(1))
    assert len(repo.ledger_all()) == 1  # failed insert rolled back


def test_products_and_cache(tmp_path):
    repo = get_repo()
    repo.upsert_products([{"id": "p1", "category": "panel", "price_php": 1}, {"id": "b1", "category": "battery"}])
    repo.upsert_products([{"id": "p1", "category": "panel", "price_php": 2}])
    assert [p["price_php"] for p in repo.list_products("panel")] == [2]
    assert len(repo.list_products()) == 2

    cache = get_cache()
    assert cache.cache_get("k") is None
    cache.cache_set("k", {"v": 1}, ttl_s=100)
    assert cache.cache_get("k") == {"v": 1}
    cache.cache_set("old", 1, ttl_s=-1)
    assert cache.cache_get("old") is None


def test_auto_falls_back_when_database_url_missing(monkeypatch):
    monkeypatch.setenv("DB_BACKEND", "auto")
    monkeypatch.setenv("DATABASE_URL", "")
    from app.config import get_settings

    get_settings.cache_clear()
    reset_repos()
    assert db_status()["active"] == "sqlite"
    assert "DATABASE_URL" in db_status()["fallback_reason"]


def test_auto_falls_back_when_supabase_unreachable(monkeypatch):
    monkeypatch.setenv("DB_BACKEND", "auto")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@127.0.0.1:1/postgres")
    from app.config import get_settings

    get_settings.cache_clear()
    reset_repos()
    st = db_status()
    assert st["active"] == "sqlite"
    assert st["fallback_reason"]
    get_repo().save_session("x", {"ok": True})  # still fully usable


def test_sqlite_repo_creates_parent_dir(tmp_path):
    repo = SQLiteRepository(tmp_path / "deep" / "dir" / "x.db")
    repo.init_schema()
    assert repo.ping()
