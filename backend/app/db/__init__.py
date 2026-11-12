"""Repository selection: Supabase when reachable, otherwise local SQLite."""
from __future__ import annotations

import logging
import threading

from ..config import get_settings
from .base import GENESIS_HASH, LedgerError, Repository, UserExists
from .sqlite_repo import SQLiteRepository

log = logging.getLogger("sol.db")

_lock = threading.Lock()
_repo: Repository | None = None
_status: dict = {"active": None, "requested": None, "fallback_reason": None}
_cache_repo: SQLiteRepository | None = None

__all__ = ["GENESIS_HASH", "LedgerError", "Repository", "UserExists", "get_repo", "get_cache", "db_status", "reset_repos"]


def _build_repo() -> tuple[Repository, dict]:
    s = get_settings()
    status = {"active": "sqlite", "requested": s.db_backend, "fallback_reason": None}
    if s.db_backend in ("auto", "supabase"):
        if not s.database_url:
            status["fallback_reason"] = "DATABASE_URL is not set"
            if s.db_backend == "supabase":
                log.warning("DB_BACKEND=supabase but DATABASE_URL is empty; using SQLite")
        else:
            try:
                from .pg_repo import PostgresRepository

                pg = PostgresRepository(s.database_url)
                pg.init_schema()
                status["active"] = "supabase"
                return pg, status
            except Exception as exc:  # network down, bad URL, bad password ...
                status["fallback_reason"] = f"{exc.__class__.__name__}: {str(exc)[:160]}"
                log.warning("Supabase unavailable (%s); falling back to SQLite", status["fallback_reason"])
    repo = SQLiteRepository(s.sqlite_path)
    repo.init_schema()
    return repo, status


def get_repo() -> Repository:
    global _repo, _status
    if _repo is None:
        with _lock:
            if _repo is None:
                _repo, _status = _build_repo()
    return _repo


def get_cache() -> SQLiteRepository:
    """Local cache (geocode, Overpass, PVGIS metadata). Always SQLite so it works offline."""
    global _cache_repo
    if _cache_repo is None:
        with _lock:
            if _cache_repo is None:
                repo = SQLiteRepository(get_settings().cache_path)
                repo.init_schema()
                _cache_repo = repo
    return _cache_repo


def db_status() -> dict:
    get_repo()
    return dict(_status)


def reset_repos() -> None:
    """Test helper: drop singletons so the next call re-reads settings."""
    global _repo, _cache_repo, _status
    with _lock:
        close = getattr(_repo, "close", None)
        if close:
            try:
                close()
            except Exception:  # pragma: no cover
                pass
        _repo = None
        _cache_repo = None
        _status = {"active": None, "requested": None, "fallback_reason": None}
