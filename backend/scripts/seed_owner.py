"""Issue the demo solar owner's signed, installed Solar Passport (run once per database, after seed_users.py).

Usage (from backend/):  python scripts/seed_owner.py [--email dela.cruz@sol.test] [--reissue]

Re-running keeps a Passport that still verifies. If the stored one is missing or fails verification, it warns and only
issues a new one with --reissue. Redeemed vouchers are kept.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import db_status, get_repo  # noqa: E402
from app.services import auth, rewards  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", default="dela.cruz@sol.test")
    ap.add_argument("--reissue", action="store_true")
    args = ap.parse_args()
    print(f"Database: {db_status()['active']}")
    user = get_repo().get_user_by_email(auth.normalize_email(args.email))
    if user is None:
        print(f"No account {args.email}. Run scripts/seed_users.py first.")
        return 1
    status = rewards.issue_owner_passport(user, reissue=args.reissue)
    if status == "broken":
        print("The stored Passport is missing or fails verification. Re-run with --reissue to issue a new one.")
        return 1
    print("Passport already in place." if status == "kept" else "Issued a new Solar Passport.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
