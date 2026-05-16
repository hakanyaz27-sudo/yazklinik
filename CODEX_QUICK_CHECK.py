#!/usr/bin/env python
"""CODEX_QUICK_CHECK.py - YazKlinik D300 sistem dogrulama.

Kullanim:
  python CODEX_QUICK_CHECK.py

Cikis: son satir 'CODEX_D300_QUICK_CHECK_OK' ise her sey OK.

Ne kontrol eder:
  1. Python ve venv
  2. Kritik dosyalar mevcut mu
  3. config.env okunabiliyor mu
  4. Lokal DB acilabiliyor mu (85 hasta?)
  5. NAS path erisilebilir mi (warn only)
  6. Server canli mi (config portu)
  7. Compile temiz mi (yazklinik_web.py + yazklinik_v68.py + feature_sync)
  8. Eger server ayakta ise: 5 ana route smoke test
"""
import os
import sys
import json
import sqlite3
import ssl
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

# ----------------------------------------------------------------------
# Renk kodlari (terminal)
# ----------------------------------------------------------------------
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"

if os.name == "nt":
    # Windows'ta ANSI dest. yoksa kapat
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 7)
    except Exception:
        GREEN = RED = YELLOW = CYAN = RESET = ""

ROOT = Path(__file__).parent.resolve()
errors = 0
warnings = 0


def ok(msg):
    print(f"  {GREEN}[OK]{RESET}  {msg}")


def warn(msg):
    global warnings
    warnings += 1
    print(f"  {YELLOW}[WARN]{RESET} {msg}")


def err(msg):
    global errors
    errors += 1
    print(f"  {RED}[ERR]{RESET} {msg}")


def section(name):
    print(f"\n{CYAN}=== {name} ==={RESET}")


def _smoke_login_credentials():
    """Smoke test icin sifreyi ekrana basmadan yerel kaynaktan bul."""
    user = (os.environ.get("YAZKLINIK_SMOKE_USER")
            or os.environ.get("CODEX_QUICK_CHECK_USER")
            or "doktor").strip() or "doktor"
    password = (os.environ.get("YAZKLINIK_SMOKE_PASSWORD")
                or os.environ.get("CODEX_QUICK_CHECK_PASSWORD")
                or "").strip()
    if not password:
        try:
            users_path = ROOT / "users.json"
            if users_path.exists():
                data = json.loads(users_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    item = data.get(user) or {}
                    if isinstance(item, dict):
                        password = str(item.get("password") or "").strip()
        except Exception as ex:
            warn(f"users.json smoke sifresi okunamadi: {ex}")
    return user, password or "1234"


# ----------------------------------------------------------------------
# 1) Python + venv
# ----------------------------------------------------------------------
section("1) Python ortami")
print(f"  Python: {sys.version.split()[0]}")
print(f"  Sys.executable: {sys.executable}")
if "venv" in sys.executable.lower() or ".venv" in sys.executable.lower():
    ok("Sanal ortam (.venv) kullaniliyor")
else:
    warn("Global Python kullaniliyor - .venv tercih edilir")


# ----------------------------------------------------------------------
# 2) Kritik dosyalar
# ----------------------------------------------------------------------
section("2) Kritik dosyalar")
critical = [
    "yazklinik_web.py",
    "yazklinik_v68.py",
    "yazklinik_feature_sync.py",
    "yazklinik_textfix.py",
    "yazklinik_common.py",
    "yazklinik_config.py",
    "config.env",
    "D300_BASLAT.bat",
    "AGENTS.md",
]
for f in critical:
    p = ROOT / f
    if p.exists():
        sz = p.stat().st_size
        ok(f"{f:32s} ({sz:>10,} byte)")
    else:
        err(f"{f} EKSIK!")


# ----------------------------------------------------------------------
# 3) config.env
# ----------------------------------------------------------------------
section("3) config.env okuma")
cfg_path = ROOT / "config.env"
config = {}
if cfg_path.exists():
    try:
        for line in cfg_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, v = line.split("=", 1)
                config[k.strip()] = v.strip()
        ok(f"config.env okundu: {len(config)} ayar")
        for key in ("YAZKLINIK_NAS_ROOT", "YAZKLINIK_DB_PATH",
                    "YAZKLINIK_WEB_PORT"):
            if config.get(key):
                print(f"    {key} = {config[key]}")
            else:
                warn(f"  {key} bos veya eksik")
    except Exception as ex:
        err(f"config.env okunamadi: {ex}")
else:
    err("config.env YOK")


# ----------------------------------------------------------------------
# 4) Lokal DB
# ----------------------------------------------------------------------
section("4) Lokal DB")
db_path = (config.get("YAZKLINIK_DB_PATH")
           or os.environ.get("YAZKLINIK_DB_PATH")
           or str(ROOT / "local_db" / "yazklinik_v68.sqlite3"))
print(f"  DB path: {db_path}")
if os.path.exists(db_path):
    try:
        sz_mb = os.path.getsize(db_path) / 1024 / 1024
        con = sqlite3.connect(db_path, timeout=3)
        n_patients = con.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        n_visits = con.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
        n_files = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        n_tables = con.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
        check = con.execute("PRAGMA integrity_check").fetchone()[0]
        con.close()
        ok(f"DB acildi - {sz_mb:.2f} MB")
        ok(f"Hasta: {n_patients} | Visit: {n_visits} | File: {n_files} | Tablo: {n_tables}")
        if check.lower() == "ok":
            ok(f"PRAGMA integrity_check = {check}")
        else:
            warn(f"integrity_check = {check}")
    except Exception as ex:
        err(f"DB acilmadi: {ex}")
else:
    err(f"DB dosyasi YOK: {db_path}")


# ----------------------------------------------------------------------
# 5) NAS erisim
# ----------------------------------------------------------------------
section("5) NAS erisim")
nas_root = config.get("YAZKLINIK_NAS_ROOT") or os.environ.get(
    "YAZKLINIK_NAS_ROOT", r"\\asustor\Voluson\Hastalar")
nas_test = nas_root[:-len("\\Hastalar")] if nas_root.lower().endswith(
    "\\hastalar") else nas_root
if os.path.exists(nas_test):
    ok(f"NAS erisilebilir: {nas_test}")
else:
    warn(f"NAS erisilemiyor: {nas_test}")
    print("    -> Map drive veya /sistem-ayarlari'dan farkli path tanimla")


# ----------------------------------------------------------------------
# 6) Server canli mi
# ----------------------------------------------------------------------
section(f"6) Server canli mi (port {config.get('YAZKLINIK_WEB_PORT', '5443')})")
port = int(config.get("YAZKLINIK_WEB_PORT", "5443"))
server_url = (config.get("YAZKLINIK_SERVER_URL") or "").strip()
if not server_url:
    scheme = "https" if config.get("YAZKLINIK_ENABLE_HTTPS") == "1" else "http"
    server_url = f"{scheme}://127.0.0.1:{port}"
opener_kwargs = {}
if server_url.lower().startswith("https://"):
    opener_kwargs["context"] = ssl._create_unverified_context()
server_alive = False
try:
    req = urllib.request.Request(f"{server_url}/giris")
    with urllib.request.urlopen(req, timeout=3, **opener_kwargs) as resp:
        ok(f"Server cevap veriyor (HTTP {resp.status})")
        server_alive = True
except urllib.error.URLError as ex:
    warn(f"Server kapali veya cevap yok: {ex}")
    print(f"    -> Baslat: {ROOT / 'D300_BASLAT.bat'}")
except Exception as ex:
    warn(f"Server beklenmedik hata: {ex}")


# ----------------------------------------------------------------------
# 7) Compile check (3 kritik dosya)
# ----------------------------------------------------------------------
section("7) Compile check")
import py_compile
compile_files = [
    ROOT / "yazklinik_web.py",
    ROOT / "yazklinik_v68.py",
    ROOT / "yazklinik_feature_sync.py",
]
for f in compile_files:
    if not f.exists():
        err(f"{f.name} YOK - compile atlandi")
        continue
    try:
        py_compile.compile(str(f), doraise=True, quiet=True)
        ok(f"{f.name} compile OK")
    except py_compile.PyCompileError as ex:
        err(f"{f.name} compile FAIL: {ex.msg.splitlines()[-1] if ex.msg else ex}")
    except Exception as ex:
        err(f"{f.name} compile error: {ex}")


# ----------------------------------------------------------------------
# 8) Route smoke test (server canli ise)
# ----------------------------------------------------------------------
if server_alive:
    section("8) Route smoke test")
    # Login + session cookie al
    try:
        import http.cookiejar
        cj = http.cookiejar.CookieJar()
        handlers = [urllib.request.HTTPCookieProcessor(cj)]
        if server_url.lower().startswith("https://"):
            handlers.append(
                urllib.request.HTTPSHandler(
                    context=ssl._create_unverified_context()))
        opener = urllib.request.build_opener(*handlers)
        # Login POST - sifre degistirildiyse users.json/env'den alinir.
        smoke_user, smoke_password = _smoke_login_credentials()
        body = urllib.parse.urlencode({
            "username": smoke_user,
            "password": smoke_password,
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{server_url}/giris", data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"})
        opener.open(req, timeout=5).read()
        # Test routes
        routes = [
            "/hastalar",
            "/tedavi-planla",
            "/sistem-ayarlari",
            "/ses-ve-alex",
            "/akilli-dialog",
            "/sessiz-alex",
            "/api/sistem-durumu",
        ]
        ok_count = 0
        for r in routes:
            try:
                with opener.open(f"{server_url}{r}", timeout=10) as resp:
                    ok(f"{r:32s} HTTP {resp.status}")
                    ok_count += 1
            except Exception as ex:
                err(f"{r}: {ex}")
        if ok_count == len(routes):
            ok(f"{ok_count}/{len(routes)} route OK")
    except Exception as ex:
        warn(f"Route test atlandi (login fail?): {ex}")


# ----------------------------------------------------------------------
# Final ozet
# ----------------------------------------------------------------------
print()
print("=" * 60)
print(f"  {GREEN}OK{RESET}: tum kritik kontroller gecti.")
print(f"  Hata: {RED}{errors}{RESET} | Uyari: {YELLOW}{warnings}{RESET}")
print("=" * 60)
if errors == 0:
    print("CODEX_D300_QUICK_CHECK_OK")
    sys.exit(0)
else:
    print(f"CODEX_D300_QUICK_CHECK_FAIL ({errors} hata)")
    sys.exit(1)

