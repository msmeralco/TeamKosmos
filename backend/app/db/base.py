"""Storage interface. Two implementations: SQLite (local/offline) and Supabase Postgres."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

GENESIS_HASH = "0" * 64


class LedgerError(Exception):
    pass


class Repository(ABC):
    kind: str = "abstract"

    # --- lifecycle -------------------------------------------------
    @abstractmethod
    def init_schema(self) -> None: ...

    @abstractmethod
    def ping(self) -> bool: ...

    # --- sessions --------------------------------------------------
    @abstractmethod
    def get_session(self, session_id: str) -> dict | None: ...

    @abstractmethod
    def save_session(self, session_id: str, state: dict) -> None: ...

    @abstractmethod
    def delete_session(self, session_id: str) -> bool: ...

    # --- products --------------------------------------------------
    @abstractmethod
    def upsert_products(self, products: list[dict]) -> None: ...

    @abstractmethod
    def list_products(self, category: str | None = None) -> list[dict]: ...

    # --- append-only ledger (Solar Passport) ------------------------
    @abstractmethod
    def append_ledger(self, make_record: Callable[[str], dict]) -> dict:
        """Atomically read the last hash, call make_record(prev_hash) and append the result.

        make_record must return {id, body_json, hash, signature, created_at}.
        """

    @abstractmethod
    def get_ledger(self, record_id: str) -> dict | None: ...

    @abstractmethod
    def ledger_all(self) -> list[dict]: ...

    # --- small key/value cache -------------------------------------
    @abstractmethod
    def cache_get(self, key: str) -> Any | None: ...

    @abstractmethod
    def cache_set(self, key: str, value: Any, ttl_s: float | None = None) -> None: ...
