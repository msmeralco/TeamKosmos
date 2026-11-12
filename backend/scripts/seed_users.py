"""Create real accounts from data/seed_users.json in the configured database (Supabase or SQLite).

Usage (from backend/):  python scripts/seed_users.py [--file data/seed_users.json] [--reset-passwords]

Passwords are never stored in the repo. Set SEED_PASSWORD to use another password for every seeded account;
otherwise new accounts get the demo password "password". Existing accounts are left alone
unless --reset-passwords is given.
"""
from __future__ import annotations

import argparse
import json
import os
import secrets
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import db_status, get_repo  # noqa: E402
from app.services import auth  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=str(Path(__file__).resolve().parent.parent / "data" / "seed_users.json"))
    ap.add_argument("--reset-passwords", action="store_true")
    args = ap.parse_args()

    users = json.loads(Path(args.file).read_text(encoding="utf-8"))
    shared = os.environ.get("SEED_PASSWORD", "password").strip()
    repo = get_repo()
    print(f"Database: {db_status()['active']}")
    for u in users:
        email = auth.normalize_email(u["email"])
        existing = repo.get_user_by_email(email)
        password = shared or secrets.token_urlsafe(9)
        household = {k: u.get(k) for k in ("household_name", "city", "lat", "lon", "monthly_kwh", "household_template")}
        if existing is None:
            auth.create_user(email=email, password=password, name=u["name"], **household)
            print(f"created  {email}  password: {password}")
        else:
            repo.update_user(existing["id"], {"name": u["name"], **auth.validate_household(household)})
            if args.reset_passwords:
                auth.check_password(password)
                repo.update_user(existing["id"], {"password_hash": auth.hash_password(password)})
                print(f"reset    {email}  password: {password}")
            else:
                print(f"exists   {email}  (household updated, password unchanged)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
