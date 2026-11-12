#!/bin/sh
# Runs a hyperframes command against the outro by temporarily swapping it in as index.html
# (the CLI's check and snapshot read index.html). Asset paths are rewritten for the swap and the intro is always restored.
cd "$(dirname "$0")/sol-reel" || exit 1
mkdir -p .swap && cp index.html .swap/intro.html && sed 's#\.\./assets/#assets/#g' compositions/outro.html > index.html
trap 'cp .swap/intro.html index.html; rm -rf .swap' EXIT INT TERM
"$@"
