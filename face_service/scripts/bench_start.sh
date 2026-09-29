#!/usr/bin/env bash
# Started by `bench start` via Procfile — keep ML deps in local .venv (not Frappe env).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/../../logs" 2>/dev/null || true
LOG_DIR="$(cd "$ROOT/../../.." && pwd)/logs"
mkdir -p "$LOG_DIR"

if [[ ! -x "$ROOT/.venv/bin/uvicorn" ]]; then
  echo "[karmavitta-face-service] Creating venv and installing requirements (first run)..."
  python3 -m venv "$ROOT/.venv"
  "$ROOT/.venv/bin/pip" install --upgrade pip
  "$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt"
fi

if [[ ! -f "$ROOT/.env" ]]; then
  echo "[karmavitta-face-service] Missing .env. Run bench migrate to let Karmavitta configure it automatically." >&2
  exit 1
fi

# Load env for pydantic-settings / process
set -a
# shellcheck disable=SC1091
source "$ROOT/.env"
set +a

APP_ROOT="$(dirname "$ROOT")"
export PYTHONPATH="$APP_ROOT${PYTHONPATH:+:$PYTHONPATH}"
PORT="${FACE_SERVICE_PORT:-8090}"
if ! (echo >/dev/tcp/127.0.0.1/"$PORT") >/dev/null 2>&1; then
  :
else
  echo "[karmavitta-face-service] Port ${PORT} is busy. Run bench migrate to select a new port and synchronize ERPNext settings." >&2
  exit 1
fi

echo "[karmavitta-face-service] Starting on 127.0.0.1:${PORT}"
exec "$ROOT/.venv/bin/uvicorn" face_service.app.main:app \
  --host 127.0.0.1 \
  --port "$PORT" \
  --log-level info
