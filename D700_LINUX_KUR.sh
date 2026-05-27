#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON_BIN="${PYTHON_BIN:-python3}"
VENV_DIR="${VENV_DIR:-$ROOT/.venv-linux}"

echo "[1/5] Python kontrol"
"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("Python 3.10+ gerekli")
print("python=" + sys.version.split()[0])
PY

echo "[2/5] Linux env dosyasi"
if [ ! -f "$ROOT/.env.linux" ]; then
  cp "$ROOT/infra/linux/d700.env.example" "$ROOT/.env.linux"
  echo "olustu: $ROOT/.env.linux"
  echo "NOT: NAS/DB/PostgreSQL yollarini bu dosyada kontrol et."
else
  echo "mevcut: $ROOT/.env.linux"
fi

echo "[3/5] Sanal ortam"
if [ ! -x "$VENV_DIR/bin/python" ]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel

echo "[4/5] Paketler"
"$VENV_DIR/bin/python" -m pip install -r "$ROOT/requirements-linux.txt"

echo "[5/5] Dizinler"
mkdir -p "$ROOT/runtime_state/perf" "$ROOT/logs"

cat <<EOF

OK: Linux hazirlik tamam.
Baslat:
  bash "$ROOT/D700_LINUX_BASLAT.sh"

Hiz testi:
  bash "$ROOT/D700_LINUX_HIZ_TESTI.sh"

Systemd/Nginx sablonlari:
  $ROOT/infra/linux/yazklinik-d700.service
  $ROOT/infra/linux/nginx-yazklinik-d700.conf
EOF
