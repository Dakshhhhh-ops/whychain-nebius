#!/usr/bin/env bash
# Starts WhyChain on macOS or Linux, then warms it up. The same steps as start.cmd on Windows.
# Run from the project folder after the setup in the README:  ./start.sh   (Ctrl+C stops it)
#
# The default needs nothing but Python and NEBIUS_API_KEY in .env: every model call goes to NVIDIA Nemotron on
# Nebius Token Factory, data is queried in place with DuckDB, and memory lives in runs/. Optional extras start only
# when .env asks for them: the ERP database in Docker (USE_POSTGRES=true), the Zetaris platform (ZETARIS_DIR) and
# the Meterless engines bridge (METERLESS_BRIDGE_URL).
set -euo pipefail
cd "$(dirname "$0")"

PY=.venv/bin/python
[ -x "$PY" ] || { echo "No .venv found: run the Quick start in the README first."; exit 1; }

envval() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- | sed 's/[[:space:]]*#.*$//' || true; }

if [ "$(envval USE_POSTGRES)" = "true" ] || [ -n "$(envval ZETARIS_DIR)" ]; then
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    ZETARIS_DIR=$(envval ZETARIS_DIR)
    if [ -n "$ZETARIS_DIR" ] && [ -d "$ZETARIS_DIR" ]; then
      echo "Starting Zetaris from $ZETARIS_DIR ..."
      (cd "$ZETARIS_DIR" && docker compose up -d)
    fi
    if [ "$(envval USE_POSTGRES)" = "true" ]; then
      echo "Starting the ERP database..."
      docker compose up -d
    fi
  else
    echo "Docker is not running: the order system is read from its CSV copy."
  fi
fi

pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

if [ -n "$(envval METERLESS_BRIDGE_URL)" ] && [ -d meterless_bridge/node_modules ]; then
  echo "Starting the optional Meterless engines bridge..."
  (cd meterless_bridge && npm start >../meterless_bridge.log 2>&1) &
  pids+=($!)
fi

echo "Starting the web app..."
"$PY" -m whychain.api >whychain_api.log 2>&1 &
pids+=($!)

echo "Warming up..."
"$PY" scripts/warmup.py || true
echo "WhyChain is running at http://localhost:8000  (log: whychain_api.log; Ctrl+C to stop)"
wait
