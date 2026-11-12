"""Chat with Sol from the terminal (no frontend needed).

Usage (from backend/, with the server running):  python scripts/agent_chat.py [--persona reyes] [--language auto]
Type a message, or a number to pick one of the suggested choices. /quit to exit.
"""
from __future__ import annotations

import argparse
import json
import sys
import uuid

import httpx


def stream_turn(client: httpx.Client, cid: str, text: str, persona: str, language: str) -> dict:
    reply: dict = {}
    with client.stream("POST", "/api/agent/chat", data={"conversation_id": cid, "message": text, "persona_id": persona, "language": language}) as r:
        if r.status_code != 200:
            r.read()
            print(f"  [error {r.status_code}] {r.json().get('detail', {}).get('message', r.text)}")
            return {}
        event = None
        for line in r.iter_lines():
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: ") and event:
                data = json.loads(line[6:])
                if event == "step":
                    mark = "..." if data["status"] == "running" else "ok"
                    print(f"  [{mark}] {data['label']}")
                elif event == "reply":
                    reply = data
    return reply


def main() -> int:
    # Windows consoles often use cp1252, which cannot print the peso sign: never crash on output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--persona", default="reyes", choices=["reyes", "maria", "wfh"])
    ap.add_argument("--language", default="auto", choices=["auto", "english", "taglish"])
    args = ap.parse_args()
    cid = f"cli-{uuid.uuid4().hex}"
    choices: list[dict] = []
    with httpx.Client(base_url=args.base_url, timeout=120) as client:
        print("Sol terminal chat. Type a message, a choice number, or /quit.\n")
        while True:
            try:
                text = input("you> ").strip()
            except (EOFError, KeyboardInterrupt):
                return 0
            if text == "/quit":
                return 0
            if text.isdigit() and 1 <= int(text) <= len(choices):
                text = choices[int(text) - 1]["text"]
                print(f"     ({text})")
            if not text:
                continue
            reply = stream_turn(client, cid, text, args.persona, args.language)
            if not reply:
                continue
            print(f"\nsol> {reply['text']}")
            if reply.get("hasMapArtifact"):
                print("     [map panel would open here]")
            choices = reply.get("next", [])
            for i, c in enumerate(choices, 1):
                print(f"     {i}. {c['label']}" + (f" - {c['hint']}" if c.get("hint") else ""))
            print()


if __name__ == "__main__":
    sys.exit(main())
