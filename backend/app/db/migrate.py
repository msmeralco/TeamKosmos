"""Apply the Postgres schema to the database in DATABASE_URL.  Usage: python -m app.db.migrate"""
from __future__ import annotations

import sys

from ..config import get_settings


def main() -> int:
    s = get_settings()
    if not s.database_url:
        print("DATABASE_URL is not set (backend/.env). Nothing to migrate.")
        return 1
    from .pg_repo import PostgresRepository

    repo = PostgresRepository(s.database_url)
    try:
        repo.init_schema()
        print("Schema applied to Supabase Postgres.")
    finally:
        repo.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
