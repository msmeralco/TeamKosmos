"""Storage interface. Two implementations: SQLite (local/offline) and Supabase Postgres."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

GENESIS_HASH = "0" * 64


class LedgerError(Exception):
    pass


class UserExists(Exception):
    pass


# Columns update_user may change (an allow list, because the names are interpolated into SQL).
# Household fields feed the chat agent.
USER_FIELDS = ("password_hash", "name", "household_name", "city", "lat", "lon", "monthly_kwh", "household_template")


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
    def save_session(self, session_id: str, state: dict, user_id: str | None = None, title: str | None = None) -> None:
        """Upsert. user_id and title are set on insert and kept when later saves omit them."""

    @abstractmethod
    def delete_session(self, session_id: str) -> bool: ...

    @abstractmethod
    def get_session_owner(self, session_id: str) -> str | None:
        """The user id that owns the session, or None when it has no owner or does not exist."""

    @abstractmethod
    def list_sessions(self, user_id: str, limit: int = 100) -> list[dict]:
        """[{id, title, turn_count, updated_at (epoch seconds)}] newest first."""

    # --- users and auth tokens -------------------------------------
    @abstractmethod
    def create_user(self, user: dict) -> None:
        """Insert a user row. Raises UserExists when the email is taken."""

    @abstractmethod
    def get_user(self, user_id: str) -> dict | None: ...

    @abstractmethod
    def get_user_by_email(self, email: str) -> dict | None: ...

    @abstractmethod
    def list_users(self) -> list[dict]: ...

    @abstractmethod
    def update_user(self, user_id: str, fields: dict) -> None: ...

    @abstractmethod
    def create_token(self, token_hash: str, user_id: str, expires_at: float) -> None: ...

    @abstractmethod
    def get_token(self, token_hash: str) -> dict | None:
        """{user_id, expires_at} or None."""

    @abstractmethod
    def delete_token(self, token_hash: str) -> None: ...

    @abstractmethod
    def purge_expired_tokens(self) -> None: ...

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
