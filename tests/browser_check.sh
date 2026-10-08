#!/usr/bin/env bash
# Browser check: the real app in a real Chrome (on a private Xvfb display — headless Chrome stalls pdf.js workers),
# against a throwaway LabelDesk server. Covers what the unit tests can't: pdf.js opening a PDF, a label saved to
# Downloads opening by itself, the page's CSP, and no errors in the page.
# Needs: google-chrome, Xvfb, node 22+.   Usage: tests/browser_check.sh
set -euo pipefail
cd "$(dirname "$0")/.."
work=$(mktemp -d); mkdir -p "$work/dl" "$work/home"
pids=()
trap 'kill "${pids[@]}" 2>/dev/null || true; sleep 0.5; rm -rf "$work"' EXIT
port=$((20000 + RANDOM % 20000)); devtools=$((port + 1)); display=:$((50 + RANDOM % 40))
HOME="$work/home" LABELDESK_KEYS=file LABELDESK_DATA="$work/data" LABELDESK_DOWNLOADS="$work/dl" LABELDESK_PORT=$port \
  python3 server/app.py >"$work/server.log" 2>&1 & pids+=($!)
Xvfb "$display" -screen 0 1280x860x24 >/dev/null 2>&1 & pids+=($!)
sleep 1
chrome=$(command -v google-chrome || command -v chromium-browser || command -v chromium)
env -u WAYLAND_DISPLAY DISPLAY="$display" "$chrome" --ozone-platform=x11 --user-data-dir="$work/chrome" --no-first-run \
  --no-default-browser-check --remote-debugging-port=$devtools --app="http://127.0.0.1:$port/" >/dev/null 2>&1 & pids+=($!)
node tests/browser/check.mjs $devtools tests/samples/ups-sample.pdf "$work/dl" || { echo "--- server log"; tail -20 "$work/server.log"; exit 1; }
