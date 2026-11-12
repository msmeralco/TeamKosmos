#!/bin/bash
# Double-click to present (macOS). Serves this folder on localhost only, then opens the browser.
cd "$(dirname "$0")"
PORT=8000
while lsof -i :$PORT >/dev/null 2>&1; do PORT=$((PORT+1)); done
(sleep 1; open "http://localhost:$PORT/index.html") &
echo "Sol deck at http://localhost:$PORT  (Ctrl+C to stop)"
python3 -m http.server $PORT --bind 127.0.0.1
