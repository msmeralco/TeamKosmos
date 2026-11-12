"""Run one full conversation against a running server and print what Sol said. Uses whatever LLM/DB the server has.

Usage (from backend/):  python scripts/live_check.py [--base-url http://127.0.0.1:8000] [--persona reyes]
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid

import httpx

SCRIPT = ["I want to install solar", "reyes demo", "Yes, use 450 kWh per month", "My budget is ₱300,000 to ₱500,000",
          "I want to cut my electricity bill", "Cut my bill by 50%", "Yes, run the numbers"]


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--persona", default="reyes")
    args = ap.parse_args()
    cid = f"live-check-{uuid.uuid4().hex}"
    with httpx.Client(base_url=args.base_url, timeout=150) as c:
        h = c.get("/api/health").json()
        print(f"server: db={h['db']['active']} llm={h['llm']['mode']} model={h['llm']['model']}\n")
        expected = ["roof_method", "load", "budget", "goal", "goal_param", "confirm", "done"]
        ok = True
        for i, text in enumerate(SCRIPT):
            t = time.time()
            r = c.post("/api/agent/chat?stream=false", data={"conversation_id": cid, "message": text, "persona_id": args.persona})
            r.raise_for_status()
            m = r.json()
            quick = any(s["label"] == "Switching to quick mode" for s in m["steps"])
            slot = m["reply"]["slot"]
            flag = "" if slot == expected[i] else f"   <-- expected slot {expected[i]}"
            ok = ok and slot == expected[i]
            print(f"{i + 1}. you: {text}\n   sol ({'quick mode' if quick else 'LLM'}, {time.time() - t:.1f}s, slot={slot}){flag}:\n   {m['reply']['text']}\n")
        s = c.get(f"/api/agent/sessions/{cid}").json()
        print(f"stored: turns={s['turnCount']} guardEvents={len(s['guardEvents'])} nextSlot={s['nextSlot']}")
        c.delete(f"/api/agent/sessions/{cid}")
    print("RESULT:", "every step happened in order" if ok else "steps were skipped or out of order")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
