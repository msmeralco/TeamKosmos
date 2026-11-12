"""End-to-end smoke test: runs the three demo personas through the chat API and prints a one-page table.

Usage (from backend/):
  python scripts/demo_run.py                      # in-process, temp database, no network, no Gemini
  python scripts/demo_run.py --base-url http://127.0.0.1:8000   # against a running server
Exit code is non-zero if any scenario fails.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HOUSEHOLDS = {  # signed up as fresh accounts for every run
    "reyes": {"household_name": "Reyes Family", "city": "Quezon City", "lat": 14.676, "lon": 121.0437, "monthly_kwh": 450, "household_template": "balanced"},
    "maria": {"household_name": "Ate Maria", "city": "Pasig City", "lat": 14.5764, "lon": 121.0851, "monthly_kwh": 250, "household_template": "night_heavy"},
    "wfh": {"household_name": "WFH Couple", "city": "Makati City", "lat": 14.5547, "lon": 121.0244, "monthly_kwh": 700, "household_template": "day_heavy"},
}
SCENARIOS = [
    ("reyes", "Reyes Family", ["I want to install solar", "reyes demo", "Yes, use 450 kWh per month",
                                "My budget is ₱300,000 to ₱500,000", "I want to cut my electricity bill", "Cut my bill by 50%", "Yes, run the numbers"]),
    ("maria", "Ate Maria", ["I want to install solar", "pasig demo", "Yes, use 250 kWh per month",
                             "My budget is ₱150,000 to ₱300,000", "I want the fastest payback", "Yes, run the numbers"]),
    ("wfh", "WFH Couple", ["I want to install solar", "makati demo", "Yes, use 700 kWh per month",
                            "My budget is ₱500,000 or more", "I want the biggest 10-year savings", "Yes, run the numbers"]),
]


def make_client(base_url: str | None):
    if base_url:
        import httpx

        return httpx.Client(base_url=base_url, timeout=120)
    import os

    tmp = tempfile.mkdtemp(prefix="sol-demo-")
    os.environ.update({"DATA_DIR": tmp, "SQLITE_PATH": f"{tmp}/sol.db", "CACHE_PATH": f"{tmp}/cache.db", "DB_BACKEND": "sqlite",
                       "AGENT_MODE": "scripted", "GEMINI_API_KEY": "", "PVGIS_LIVE": "0", "PASSPORT_SIGNING_KEY": f"{tmp}/key.pem"})
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app())


def yrs(v) -> str:
    return "never" if v is None else f"{v:.1f}"


def main() -> int:
    import logging

    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url")
    args = ap.parse_args()
    client = make_client(args.base_url)
    for noisy in ("httpx", "httpx2", "httpcore", "sol.geo", "sol.agent"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    failures = 0
    rows = []
    for persona, name, script in SCENARIOS:
        cid = f"demo-{persona}-{uuid.uuid4().hex[:12]}"
        su = client.post("/api/auth/signup", json={"name": name, "email": f"{cid}@demo-run.test", "password": uuid.uuid4().hex, **HOUSEHOLDS[persona]})
        su.raise_for_status()
        headers = {"Authorization": f"Bearer {su.json()['token']}"}
        last = None
        try:
            for text in script:
                r = client.post("/api/agent/chat?stream=false", data={"conversation_id": cid, "message": text}, headers=headers)
                r.raise_for_status()
                last = r.json()
            card = next((c for c in last["reply"]["cards"] if c["type"] == "analysis"), None)
            if card is None:
                raise RuntimeError("no analysis card: " + last["reply"]["text"][:160])
            top = card["data"]["packages"][0]
            pb, pf = top["payback_years"], top["net_profit_10y_php"]
            rows.append((name, top["label"], top["kwp"], top["capex_php"], top["bill_reduction_pct_year1"],
                         f"{yrs(pb['best_case'])} / {yrs(pb['expected'])} / {yrs(pb['bad_year'])}",
                         f"{pf['bad_year']:,.0f} to {pf['best_case']:,.0f}", "approx" if card["data"]["weather_is_approximate"] else "PVGIS"))
        except Exception as exc:  # noqa: BLE001
            failures += 1
            rows.append((name, f"FAILED: {exc}", 0, 0, 0, "", "", ""))
    print(f"{'Household':<14}{'Top option':<16}{'kWp':>6}{'Capex PHP':>12}{'Bill cut':>9}  {'Payback best/exp/bad (yrs)':<28}{'10y profit PHP (bad to best)':<30}{'Sun data'}")
    for r in rows:
        print(f"{r[0]:<14}{str(r[1]):<16}{r[2]:>6.1f}{r[3]:>12,.0f}{r[4]:>8.0f}%  {r[5]:<28}{r[6]:<30}{r[7]}")
    print("\nAll scenarios passed." if not failures else f"\n{failures} scenario(s) failed.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
