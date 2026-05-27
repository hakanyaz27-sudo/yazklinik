#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

if [ -f "$ROOT/.env.linux" ]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env.linux"
  set +a
fi

VENV_DIR="${VENV_DIR:-$ROOT/.venv-linux}"
PYTHON_BIN="${PYTHON_BIN:-$VENV_DIR/bin/python}"
PORT="${YAZKLINIK_WEB_PORT:-5052}"
REPEAT="${1:-3}"
BASE_URL="${D700_PERF_BASE_URL:-http://127.0.0.1:$PORT}"

if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="${PYTHON_BIN_FALLBACK:-python3}"
fi

"$PYTHON_BIN" "$ROOT/D700_PERF_AUDIT.py" --base "$BASE_URL" --repeat "$REPEAT" --timeout 10
