#!/usr/bin/env bash
# Runs the backend (uvicorn, port 8000) and the frontend (npm run dev) together.
# Usage: ./scripts/dev.sh     Stop both with Ctrl+C.
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
frontend="$root/frontend"
[ -d "$frontend" ] || frontend="$root/frontendv2"

# Ctrl+C or either process exiting stops both (kill 0 = this script's process group).
trap 'trap - INT TERM EXIT; kill 0' INT TERM EXIT

(cd "$root/backend" && exec "$root/.venv/bin/python" -m uvicorn app.main:app --reload --port 8000) &
back=$!
(cd "$frontend" && exec npm run dev) &
front=$!

# bash 3.2 (macOS) has no `wait -n`, so poll until either process exits.
while kill -0 "$back" 2>/dev/null && kill -0 "$front" 2>/dev/null; do sleep 0.5; done
