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

export PYTHONUTF8="${PYTHONUTF8:-1}"
export YAZKLINIK_WEB_PORT="${YAZKLINIK_WEB_PORT:-5052}"
export YAZKLINIK_ENABLE_HTTPS="${YAZKLINIK_ENABLE_HTTPS:-0}"
export YAZKLINIK_SERVER_ENGINE="${YAZKLINIK_SERVER_ENGINE:-gunicorn}"
export YAZKLINIK_DB_PATH="${YAZKLINIK_DB_PATH:-$ROOT/local_db/yazklinik_v68.sqlite3}"
export YAZKLINIK_BACKUP_ROOT="${YAZKLINIK_BACKUP_ROOT:-$ROOT/auto_backups}"

VENV_DIR="${VENV_DIR:-$ROOT/.venv-linux}"
GUNICORN_BIN="${GUNICORN_BIN:-$VENV_DIR/bin/gunicorn}"
WORKERS="${YAZKLINIK_GUNICORN_WORKERS:-1}"
THREADS="${YAZKLINIK_GUNICORN_THREADS:-24}"
TIMEOUT="${YAZKLINIK_GUNICORN_TIMEOUT:-300}"

if [ ! -x "$GUNICORN_BIN" ]; then
  echo "Gunicorn bulunamadi. Once calistir: bash D700_LINUX_KUR.sh" >&2
  exit 2
fi

if [ ! -f "$YAZKLINIK_DB_PATH" ]; then
  echo "DB bulunamadi: $YAZKLINIK_DB_PATH" >&2
  echo ".env.linux icindeki YAZKLINIK_DB_PATH degerini kontrol et." >&2
  exit 3
fi

mkdir -p "$ROOT/runtime_state/perf" "$ROOT/logs" "$YAZKLINIK_BACKUP_ROOT"

echo "YazKlinik D700 Linux/Gunicorn basliyor"
echo "port=$YAZKLINIK_WEB_PORT workers=$WORKERS threads=$THREADS db=$YAZKLINIK_DB_PATH"

exec "$GUNICORN_BIN" \
  --chdir "$ROOT" \
  --bind "0.0.0.0:$YAZKLINIK_WEB_PORT" \
  --workers "$WORKERS" \
  --threads "$THREADS" \
  --worker-class gthread \
  --timeout "$TIMEOUT" \
  --graceful-timeout 60 \
  --keep-alive 5 \
  --access-logfile "-" \
  --error-logfile "-" \
  yazklinik_wsgi:application
