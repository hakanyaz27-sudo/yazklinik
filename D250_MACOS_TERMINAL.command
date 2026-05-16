#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if [ -x "$ROOT/.venv/bin/python" ]; then
  PY="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="$(command -v python3)"
else
  echo "python3 bulunamadi."
  exit 1
fi

PORT="${YAZKLINIK_WEB_PORT:-5052}"
SERVER_URL="http://127.0.0.1:${PORT}"

"$PY" "$ROOT/D250_TERMINAL_SYNC.py" --server-url "$SERVER_URL"
set -a
. "$ROOT/terminal_env.sh"
set +a

if ! "$PY" - <<PYCHECK >/dev/null 2>&1
import urllib.request
urllib.request.urlopen("${SERVER_URL}/giris", timeout=3).read(1)
PYCHECK
then
  echo "Web server baslatiliyor: ${SERVER_URL}"
  mkdir -p "$ROOT/local_db" "$ROOT/auto_backups"
  nohup "$PY" -u "$ROOT/yazklinik_web.py" > "$ROOT/D250_server.log" 2> "$ROOT/D250_server_HATA.log" &
  for i in $(seq 1 45); do
    if "$PY" - <<PYWAIT >/dev/null 2>&1
import urllib.request
urllib.request.urlopen("${SERVER_URL}/giris", timeout=2).read(1)
PYWAIT
    then
      break
    fi
    sleep 1
  done
fi

open "$SERVER_URL" >/dev/null 2>&1 || true

if [ -f "$ROOT/yazklinik_desktop_v1000.py" ]; then
  nohup "$PY" -u "$ROOT/yazklinik_desktop_v1000.py" > "$ROOT/D200_terminal_desktop.log" 2>&1 &
fi

echo "macOS terminal web surumle eslendi: ${SERVER_URL}"
