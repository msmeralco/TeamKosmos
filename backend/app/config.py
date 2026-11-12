"""Runtime settings, read from environment variables / backend/.env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")


def _env(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None else value.strip()


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    raw = _env(name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    # LLM
    gemini_api_key: str
    gemini_model: str
    gemini_fallback_model: str  # tried when the main model is overloaded; empty disables it
    agent_mode: str  # auto | scripted
    # Database
    database_url: str
    db_backend: str  # auto | sqlite | supabase
    sqlite_path: Path
    cache_path: Path
    data_dir: Path
    # HTTP / CORS
    cors_origins: tuple[str, ...]
    contact_email: str
    http_timeout_s: float
    # Agent limits
    turn_timeout_s: float
    max_upload_bytes: int
    max_files: int
    max_tool_calls: int
    # External data
    nominatim_url: str
    overpass_urls: tuple[str, ...]
    pvgis_live: bool
    signing_key_path: Path

    @property
    def user_agent(self) -> str:
        return f"Sol-Hackathon/1.0 ({self.contact_email})"

    @property
    def llm_configured(self) -> bool:
        return bool(self.gemini_api_key) and self.agent_mode != "scripted"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    data_dir = Path(_env("DATA_DIR", str(BACKEND_DIR / "data")))
    origins = _env("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173")
    overpass = _env(
        "OVERPASS_URLS",
        "https://overpass-api.de/api/interpreter,https://overpass.kumi.systems/api/interpreter",
    )
    return Settings(
        gemini_api_key=_env("GEMINI_API_KEY"),
        # [VERIFY] the exact model name on your key with scripts/verify_gemini.py
        gemini_model=_env("GEMINI_MODEL", "gemini-3.5-flash-lite"),
        gemini_fallback_model=_env("GEMINI_FALLBACK_MODEL", "gemini-3.8-flash"),
        agent_mode=_env("AGENT_MODE", "auto").lower(),
        database_url=_env("DATABASE_URL"),
        db_backend=_env("DB_BACKEND", "auto").lower(),
        sqlite_path=Path(_env("SQLITE_PATH", str(data_dir / "sol.db"))),
        cache_path=Path(_env("CACHE_PATH", str(data_dir / "cache.db"))),
        data_dir=data_dir,
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        # Placeholder on purpose: set CONTACT_EMAIL before using Nominatim/Overpass for real.
        contact_email=_env("CONTACT_EMAIL", "your-email@example.com"),
        http_timeout_s=_env_float("HTTP_TIMEOUT_S", 8.0),
        turn_timeout_s=_env_float("TURN_TIMEOUT_S", 75.0),
        max_upload_bytes=_env_int("MAX_UPLOAD_BYTES", 5 * 1024 * 1024),
        max_files=_env_int("MAX_FILES", 6),
        max_tool_calls=_env_int("MAX_TOOL_CALLS", 4),
        nominatim_url=_env("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search"),
        overpass_urls=tuple(u.strip() for u in overpass.split(",") if u.strip()),
        pvgis_live=_env_bool("PVGIS_LIVE", True),
        signing_key_path=Path(_env("PASSPORT_SIGNING_KEY", str(data_dir / "passport_ed25519.key"))),
    )
