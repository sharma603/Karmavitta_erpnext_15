#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
  # shellcheck disable=SC1091
  source .venv/bin/activate
  pip install -r requirements.txt
else
  # shellcheck disable=SC1091
  source .venv/bin/activate
fi

if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "Created .env — set FACE_SERVICE_API_KEY before production use."
fi

export PYTHONPATH="$ROOT${PYTHONPATH:+:$PYTHONPATH}"
exec uvicorn app.main:app --host 127.0.0.1 --port "${PORT:-8090}" --reload
