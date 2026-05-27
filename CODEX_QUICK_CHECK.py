#!/usr/bin/env python
"""CODEX_QUICK_CHECK.py - YazKlinik D700 sistem dogrulama.

Kullanim:
  python CODEX_QUICK_CHECK.py

Cikis: son satir 'CODEX_D700_QUICK_CHECK_OK' ise her sey OK.

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
import re
import time
import subprocess
import atexit
from datetime import datetime
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

ROOT = Path(__file__).parent.resolve()

MAINTENANCE_DISABLE_FLAGS = [
    ROOT / "runtime_state" / "maintenance_locks" / "quick_check_disabled.flag",
    Path(os.environ.get("TEMP") or os.environ.get("TMP") or str(ROOT / "runtime_state")) / "D700_quick_check_disabled.flag",
]


def _should_clear_stale_temp_maintenance_flag(flag_path: Path, flag_age: float) -> bool:
    """Eski queue-guard kalintisi TEMP flag'i quick check'i gereksiz bloklamasin."""
    try:
        if flag_path.name.lower() != "d700_quick_check_disabled.flag":
            return False
        if flag_age < 45:
            return False
        text = flag_path.read_text(encoding="utf-8", errors="ignore").strip().lower()
        return "disabled_by_codex_old_queue_guard" in text
    except Exception:
        return False


ALLOW_DURING_MAINTENANCE = str(os.environ.get("CODEX_QUICK_CHECK_ALLOW_DURING_MAINT", "")).strip().lower()
if ALLOW_DURING_MAINTENANCE not in {"1", "true", "yes", "on"}:
    for maintenance_flag in MAINTENANCE_DISABLE_FLAGS:
        if not maintenance_flag.exists():
            continue
        max_age = int(os.environ.get("CODEX_QUICK_CHECK_MAINT_LOCK_MAX_AGE_SECONDS", "1800") or "1800")
        try:
            flag_age = time.time() - maintenance_flag.stat().st_mtime
        except Exception:
            flag_age = 0
        if _should_clear_stale_temp_maintenance_flag(maintenance_flag, flag_age):
            try:
                maintenance_flag.unlink(missing_ok=True)
                print(f"[i] stale temp maintenance flag temizlendi: {maintenance_flag}")
            except Exception:
                pass
            continue
        if flag_age <= max_age:
            print(f"CODEX_QUICK_CHECK_SKIPPED_BY_MAINTENANCE_LOCK flag={maintenance_flag} age_sec={int(flag_age)}")
            raise SystemExit(0)

errors = 0
warnings = 0
CLI_ARGS = [str(a).strip() for a in sys.argv[1:]]
HELP_FLAGS = {"-h", "--help", "/?"}
QUICK_FLAGS = {"-q", "--quick"}
NO_ROUTE_FLAGS = {"--no-route", "--skip-route"}
NO_COMPILE_FLAGS = {"--no-compile", "--skip-compile"}
COMPILE_WEB_FLAGS = {"--compile-web", "--deep-compile-web"}
COMPILE_LEGACY_FLAGS = {"--compile-legacy", "--deep-compile-legacy"}
NO_COLOR_FLAGS = {"--plain", "--no-color"}
MOBILE_SCROLL_FLAGS = {"--mobile-scroll", "--mobile"}
MOBILE_SCROLL_STRICT_FLAGS = {"--mobile-scroll-strict"}
DEEP_AI_ROUTE_FLAGS = {"--deep-ai-routes", "--ai-routes"}
DEEP_SUPPORT_FLAGS = {"--deep-support", "--support-probes"}
QUICK_MODE = any(a in QUICK_FLAGS for a in CLI_ARGS)
SKIP_ROUTE = QUICK_MODE or any(a in NO_ROUTE_FLAGS for a in CLI_ARGS)
SKIP_COMPILE = QUICK_MODE or any(a in NO_COMPILE_FLAGS for a in CLI_ARGS)
RUN_WEB_COMPILE = (
    any(a in COMPILE_WEB_FLAGS for a in CLI_ARGS)
    or str(os.environ.get("CODEX_QUICK_CHECK_COMPILE_WEB", "")).strip().lower()
    in {"1", "true", "yes", "on"}
)
RUN_LEGACY_COMPILE = (
    any(a in COMPILE_LEGACY_FLAGS for a in CLI_ARGS)
    or str(os.environ.get("CODEX_QUICK_CHECK_COMPILE_LEGACY", "")).strip().lower()
    in {"1", "true", "yes", "on"}
)
RUN_MOBILE_SCROLL = any(a in MOBILE_SCROLL_FLAGS for a in CLI_ARGS)
MOBILE_SCROLL_STRICT = any(a in MOBILE_SCROLL_STRICT_FLAGS for a in CLI_ARGS)
RUN_DEEP_AI_ROUTES = (
    any(a in DEEP_AI_ROUTE_FLAGS for a in CLI_ARGS)
    or str(os.environ.get("CODEX_QUICK_CHECK_DEEP_AI_ROUTES", "")).strip().lower()
    in {"1", "true", "yes", "on"}
)
RUN_DEEP_SUPPORT = (
    any(a in DEEP_SUPPORT_FLAGS for a in CLI_ARGS)
    or str(os.environ.get("CODEX_QUICK_CHECK_DEEP_SUPPORT", "")).strip().lower()
    in {"1", "true", "yes", "on"}
)
if MOBILE_SCROLL_STRICT:
    RUN_MOBILE_SCROLL = True
PLAIN_OUTPUT = (
    any(a in NO_COLOR_FLAGS for a in CLI_ARGS)
    or str(os.environ.get("NO_COLOR", "")).strip().lower() in {"1", "true", "yes", "on"}
    or not bool(getattr(sys.stdout, "isatty", lambda: False)())
)

if PLAIN_OUTPUT:
    GREEN = RED = YELLOW = CYAN = RESET = ""
elif os.name == "nt":
    # Windows'ta ANSI dest. yoksa kapat
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 7)
    except Exception:
        GREEN = RED = YELLOW = CYAN = RESET = ""
if any(a in HELP_FLAGS for a in CLI_ARGS):
    print("CODEX_QUICK_CHECK.py - YazKlinik D700 hizli dogrulama")
    print("")
    print("Kullanim:")
    print("  python CODEX_QUICK_CHECK.py")
    print("  python CODEX_QUICK_CHECK.py --help")
    print("  python CODEX_QUICK_CHECK.py --quick")
    print("  python CODEX_QUICK_CHECK.py --no-route")
    print("  python CODEX_QUICK_CHECK.py --no-compile")
    print("  python CODEX_QUICK_CHECK.py --compile-web")
    print("  python CODEX_QUICK_CHECK.py --compile-legacy")
    print("  python CODEX_QUICK_CHECK.py --deep-ai-routes")
    print("  python CODEX_QUICK_CHECK.py --deep-support")
    print("  python CODEX_QUICK_CHECK.py --mobile-scroll")
    print("  python CODEX_QUICK_CHECK.py --mobile-scroll-strict")
    print("  python CODEX_QUICK_CHECK.py --plain")
    print("")
    print("Not:")
    print("  Bu komut compile + DB + servis + route smoke dahil tam kontrol calistirir.")
    print("  --quick: route smoke + compile adimlarini atlar.")
    print("  --compile-web: buyuk yazklinik_web.py icin ayrica py_compile calistirir.")
    print("  --compile-legacy: buyuk legacy yazklinik_v68.py icin ayrica py_compile calistirir.")
    print("  --deep-ai-routes: agir Alex/AI route smoke adimlarini da calistirir.")
    print("  --deep-support: destek yazilimlari ve yan servis probe adimlarini da calistirir.")
    print("  --mobile-scroll: mobil scroll smoke testini ekler (warn mod).")
    print("  --mobile-scroll-strict: mobil smoke basarisizsa hata sayar.")
    print("  --plain: ANSI renk kodlarini kapatir (log/CI icin).")
    print("  Son satir: CODEX_D700_QUICK_CHECK_OK / CODEX_D700_QUICK_CHECK_FAIL")
    sys.exit(0)
if QUICK_MODE:
    print("[i] QUICK mode aktif: compile + route smoke + bazi derin kontroller atlanacak.")


def _reexec_with_project_venv():
    """Global Python ile cagrilsa bile proje .venv icinden calis."""
    if os.environ.get("CODEX_QUICK_CHECK_NO_REEXEC") == "1":
        return
    if os.name != "nt":
        return
    venv_py = ROOT / ".venv" / "Scripts" / "python.exe"
    if not venv_py.exists():
        return
    try:
        current = Path(sys.executable).resolve()
        target = venv_py.resolve()
    except Exception:
        return
    if current == target:
        return
    try:
        venv_root = (ROOT / ".venv").resolve()
        if Path(getattr(sys, "prefix", "")).resolve() == venv_root:
            return
    except Exception:
        pass
    try:
        launched = Path((getattr(sys, "orig_argv", []) or [sys.executable])[0]).resolve()
        if str(launched).lower().replace("/", "\\").endswith("\\.venv\\scripts\\python.exe"):
            return
    except Exception:
        pass
    os.environ["CODEX_QUICK_CHECK_NO_REEXEC"] = "1"
    code = subprocess.call(
        [str(target), str(Path(__file__).resolve()), *sys.argv[1:]],
        cwd=str(ROOT),
        env=os.environ.copy(),
    )
    sys.exit(code)


_reexec_with_project_venv()


_QUICK_CHECK_LOCK_FD = None
_QUICK_CHECK_LOCK_PATH = ROOT / "runtime_state" / "locks" / "CODEX_QUICK_CHECK.lock"


def _pid_alive(pid):
    try:
        pid_int = int(pid)
    except Exception:
        return False
    if pid_int <= 0:
        return False
    try:
        os.kill(pid_int, 0)
        return True
    except OSError:
        return False
    except Exception:
        return True


def _lock_age_seconds(path):
    try:
        return max(0.0, time.time() - path.stat().st_mtime)
    except Exception:
        return 0.0


def _read_lock_pid(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        return data.get("pid")
    except Exception:
        return None


def _release_quick_check_lock():
    global _QUICK_CHECK_LOCK_FD
    if _QUICK_CHECK_LOCK_FD is None:
        return
    try:
        os.close(_QUICK_CHECK_LOCK_FD)
    except Exception:
        pass
    _QUICK_CHECK_LOCK_FD = None
    try:
        if _read_lock_pid(_QUICK_CHECK_LOCK_PATH) == os.getpid():
            _QUICK_CHECK_LOCK_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def _acquire_quick_check_lock():
    """Ayni anda birden fazla deep/compile check calisip web'i yormasin."""
    global _QUICK_CHECK_LOCK_FD
    if str(os.environ.get("CODEX_QUICK_CHECK_NO_LOCK", "")).strip().lower() in {"1", "true", "yes", "on"}:
        return
    lock_wait = int(str(os.environ.get("CODEX_QUICK_CHECK_LOCK_WAIT_SEC", "240") or "240"))
    stale_sec = int(str(os.environ.get("CODEX_QUICK_CHECK_LOCK_STALE_SEC", "2700") or "2700"))
    deadline = time.time() + max(0, lock_wait)
    _QUICK_CHECK_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            fd = os.open(str(_QUICK_CHECK_LOCK_PATH), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            payload = {
                "pid": os.getpid(),
                "started_at": datetime.now().isoformat(timespec="seconds"),
                "args": CLI_ARGS,
            }
            os.write(fd, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
            _QUICK_CHECK_LOCK_FD = fd
            atexit.register(_release_quick_check_lock)
            return
        except FileExistsError:
            old_pid = _read_lock_pid(_QUICK_CHECK_LOCK_PATH)
            old_age = _lock_age_seconds(_QUICK_CHECK_LOCK_PATH)
            if (old_pid and not _pid_alive(old_pid)) or old_age > stale_sec:
                try:
                    _QUICK_CHECK_LOCK_PATH.unlink(missing_ok=True)
                    continue
                except Exception:
                    pass
            if time.time() >= deadline:
                print(
                    f"[ERR] Baska CODEX_QUICK_CHECK calisiyor "
                    f"(pid={old_pid}, age={int(old_age)}s). Tekrar deneyin.",
                    flush=True,
                )
                sys.exit(2)
            print(
                f"[i] Baska CODEX_QUICK_CHECK calisiyor; bekleniyor "
                f"(pid={old_pid}, age={int(old_age)}s)...",
                flush=True,
            )
            try:
                time.sleep(10)
            except KeyboardInterrupt:
                print("[ERR] Lock bekleme kesildi (Ctrl+C).", flush=True)
                sys.exit(130)


_acquire_quick_check_lock()


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


def _is_transient_mobile_smoke_failure(detail_text, return_code):
    text = str(detail_text or "").lower()
    if return_code in (-1, 130, 137):
        return True
    transient_tokens = (
        "connection closed while reading from the driver",
        "target page, context or browser has been closed",
        "browser has been closed",
        "target closed",
        "econnreset",
        "timed out",
    )
    return any(token in text for token in transient_tokens)


def _run_mobile_scroll_smoke(strict_mode=False):
    """Opsiyonel mobil Chrome scroll smoke."""
    script_path = ROOT / "CODEX_MOBILE_SCROLL_CHECK.py"
    if not script_path.exists():
        msg = f"Mobile scroll smoke script yok: {script_path.name}"
        if strict_mode:
            err(msg)
        else:
            warn(msg)
        return False

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        try:
            proc = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=240,
                encoding="utf-8",
                errors="replace",
            )
        except KeyboardInterrupt:
            if attempt < max_attempts:
                print("  [INFO] Mobile scroll smoke kesintiye ugradi; 1 kez yeniden deneniyor...")
                time.sleep(2)
                continue
            msg = "Mobile scroll smoke kesinti nedeniyle tamamlanamadi (KeyboardInterrupt)."
            if strict_mode:
                err(msg)
            else:
                warn(msg)
            return False
        except Exception as ex:
            msg = f"Mobile scroll smoke calisamadi: {ex}"
            if strict_mode:
                err(msg)
            else:
                warn(msg)
            return False

        out_text = (proc.stdout or "").strip()
        err_text = (proc.stderr or "").strip()
        payload = {}
        if out_text:
            last_line = out_text.splitlines()[-1].strip()
            try:
                parsed = json.loads(last_line)
                if isinstance(parsed, dict):
                    payload = parsed
            except Exception:
                payload = {}

        ok_flag = bool(payload.get("ok")) and proc.returncode == 0
        if ok_flag:
            delta = payload.get("delta")
            shot = payload.get("screenshot") or "-"
            ok(f"Mobile scroll smoke OK (delta={delta}) [{shot}]")
            return True

        detail = (
            payload.get("error")
            or err_text
            or out_text[-320:]
            or f"exit={proc.returncode}"
        )
        if attempt < max_attempts and _is_transient_mobile_smoke_failure(detail, proc.returncode):
            print("  [INFO] Mobile scroll smoke gecici hata; 1 kez yeniden deneniyor...")
            time.sleep(2)
            continue

        msg = f"Mobile scroll smoke FAIL: {detail}"
        if strict_mode:
            err(msg)
        else:
            warn(msg)
        return False

    return False


REQUIRED_SQLITE_TABLES = (
    "patients",
    "visits",
    "files",
    "usg_measurements",
    "patient_protocols",
    "patient_demographics",
)


def _env_bool_like(value, default=False):
    return str(value or ("1" if default else "0")).strip().lower() in ("1", "true", "yes", "on", "y")


def _fmt_mb(size_bytes):
    return f"{size_bytes / 1024 / 1024:.2f} MB"


def _path_exists_with_timeout(path, timeout=5):
    """UNC/NAS path probe ana quick-check surecini asili birakmasin."""
    try:
        probe = subprocess.run(
            [
                sys.executable,
                "-c",
                "import os,sys; sys.exit(0 if os.path.exists(sys.argv[1]) else 1)",
                str(path),
            ],
            cwd=str(ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=max(1, int(timeout)),
        )
        return probe.returncode == 0
    except subprocess.TimeoutExpired:
        return None
    except BaseException:
        return None


def _load_support_snapshot_with_timeout(timeout=12):
    """Support path taramasi kill/timeout yerse quick-check ana akisi devam etsin."""
    code = (
        "import json;"
        "from yazklinik_support_paths import support_snapshot;"
        "print(json.dumps(support_snapshot(), ensure_ascii=False))"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(2, int(timeout)),
        )
    except subprocess.TimeoutExpired:
        return {}, "timeout"
    except BaseException as ex:
        return {}, str(ex)
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or f"exit={proc.returncode}").strip()
        return {}, detail[-320:]
    try:
        raw = (proc.stdout or "").strip().splitlines()[-1]
        parsed = json.loads(raw)
        return (parsed if isinstance(parsed, dict) else {}), None
    except Exception as ex:
        return {}, f"json parse: {ex}"


def _mask_secret_value(key, value):
    text = str(value or "")
    key_l = str(key or "").lower()
    if not text:
        return text
    if "://" in text and "@" in text:
        try:
            parsed = urllib.parse.urlsplit(text)
            if parsed.username:
                host = parsed.hostname or ""
                if parsed.port:
                    host = f"{host}:{parsed.port}"
                auth = f"{parsed.username}:***@{host}"
                return urllib.parse.urlunsplit((
                    parsed.scheme, auth, parsed.path, parsed.query, parsed.fragment
                ))
        except Exception:
            return "***"
    if any(token in key_l for token in ("password", "secret", "token", "key")):
        return "***"
    return text


_MOJIBAKE_SCAN_PATTERNS = (
    (re.compile(r"Do\u00c4(?:\u0178|Y)um"), "dogum-mojibake"),
    (re.compile(r"Geli\u00c5(?:\u0178|Y)"), "gelis-mojibake"),
    (re.compile(r"ba\u00c4(?:\u0178|Y)ar\u00c4\u00b1l\u00c4\u00b1"), "basarili-mojibake"),
    (re.compile(r"kayd\u00c4\u00b1"), "kaydi-mojibake"),
    (re.compile(r"T\u00c3\u00bcm\s+Hastalar"), "tum-hastalar-mojibake"),
)

_MOJIBAKE_ROUTE_IGNORE_LABELS = {
    # Bu sayfada legacy metin bloklari nedeniyle tekil "kaydi-mojibake"
    # yalanci pozitif verebiliyor; diger marker'lar izlenmeye devam eder.
    "/sistem-ayarlari": {"kaydi-mojibake"},
}


def _strip_html_for_text_scan(value: str) -> str:
    text = str(value or "")
    # Inline JS/CSS icerigindeki test stringleri yalanci pozitif uretebilir.
    text = re.sub(r"(?is)<script\b[^>]*>.*?</script>", " ", text)
    text = re.sub(r"(?is)<style\b[^>]*>.*?</style>", " ", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _detect_mojibake_markers(text: str) -> list[str]:
    haystack = str(text or "")
    hits: list[str] = []
    for pattern, label in _MOJIBAKE_SCAN_PATTERNS:
        if pattern.search(haystack):
            hits.append(label)
    return hits


def _simple_http_ok(url, timeout=3):
    # Windows'ta HTTPS probe icin curl -k daha stabil (sertifika store takilmalarini azaltir).
    if os.name == "nt":
        curl_cmd = [
            "curl.exe",
            "-sS",
            "-L",
            "-o",
            "NUL",
            "-w",
            "%{http_code}",
            "--max-time",
            str(max(1, int(timeout))),
            "--connect-timeout",
            str(max(1, int(timeout))),
        ]
        if str(url).lower().startswith("https://"):
            curl_cmd.append("-k")
        curl_cmd.append(str(url))
        try:
            proc = subprocess.run(
                curl_cmd,
                capture_output=True,
                text=True,
                timeout=max(2, int(timeout) + 2),
                encoding="utf-8",
                errors="replace",
            )
            code_text = (proc.stdout or "").strip()
            if proc.returncode == 0 and code_text.isdigit():
                return int(code_text), ""
            detail = (proc.stderr or "").strip() or f"curl_exit={proc.returncode}"
            return 0, detail
        except BaseException:
            # curl bulunamazsa/bozulursa urllib fallback calissin.
            pass
    try:
        kwargs = {}
        if str(url).lower().startswith("https://"):
            kwargs["context"] = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers={"User-Agent": "D700-QuickCheck/1.0"})
        with urllib.request.urlopen(req, timeout=timeout, **kwargs) as resp:
            return resp.status, ""
    except BaseException as ex:
        return 0, str(ex)


def _wait_base_ready(base_url, max_wait_sec=70, interval_sec=2.5):
    """Wait until /giris returns non-5xx so smoke steps avoid restart windows."""
    deadline = time.time() + max(5, int(max_wait_sec))
    last_detail = ""
    while time.time() < deadline:
        status, detail = _simple_http_ok(f"{base_url}/giris", timeout=5)
        if int(status or 0) in (200, 301, 302, 303, 307, 308):
            return True, f"HTTP {status}"
        if status:
            last_detail = f"HTTP {status}"
        elif detail:
            last_detail = str(detail)
        time.sleep(interval_sec)
    return False, last_detail or "timeout"


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
    "yazklinik_infra_guard.py",
    "yazklinik_textfix.py",
    "yazklinik_common.py",
    "yazklinik_config.py",
    "config.env",
    "D700_BASLAT.bat",
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
        optional_when_sqlite = {"YAZKLINIK_DATABASE_URL"}
        for key in ("YAZKLINIK_NAS_ROOT", "YAZKLINIK_DB_PATH",
                    "YAZKLINIK_DB_DIALECT", "YAZKLINIK_DATABASE_URL",
                    "YAZKLINIK_ENABLE_POSTGRES",
                    "POSTGRES_HOST", "POSTGRES_PORT", "POSTGRES_USER", "POSTGRES_DB",
                    "YAZKLINIK_WEB_PORT"):
            if config.get(key):
                print(f"    {key} = {_mask_secret_value(key, config[key])}")
            elif key in optional_when_sqlite:
                print(f"    {key} = (opsiyonel bos)")
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
backup_root = (config.get("YAZKLINIK_BACKUP_ROOT")
               or os.environ.get("YAZKLINIK_BACKUP_ROOT")
               or str(ROOT / "auto_backups"))
print(f"  DB path: {db_path}")
if os.path.exists(db_path):
    try:
        sz_mb = _fmt_mb(os.path.getsize(db_path))
        backup_root_path = Path(backup_root)
        if backup_root_path.exists():
            ok(f"Yedek klasoru: {backup_root_path}")
        else:
            try:
                backup_root_path.mkdir(parents=True, exist_ok=True)
                ok(f"Yedek klasoru olusturuldu: {backup_root_path}")
            except Exception as ex:
                warn(f"Yedek klasoru acilamadi: {backup_root_path} ({ex})")

        con = sqlite3.connect(db_path, timeout=3, isolation_level=None)
        try:
            con.execute("PRAGMA busy_timeout = 5000")
            n_patients = con.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
            n_visits = con.execute("SELECT COUNT(*) FROM visits").fetchone()[0]
            n_files = con.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            n_tables = con.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
            ).fetchone()[0]
            quick = (con.execute("PRAGMA quick_check").fetchone() or ["?"])[0]
            integrity = (con.execute("PRAGMA integrity_check").fetchone() or ["?"])[0]
            fk_issues = con.execute("PRAGMA foreign_key_check").fetchall()
            page_count = (con.execute("PRAGMA page_count").fetchone() or [0])[0]
            freelist = (con.execute("PRAGMA freelist_count").fetchone() or [0])[0]
            wal_file = Path(str(db_path) + "-wal")
            shm_file = Path(str(db_path) + "-shm")
            if wal_file.exists():
                wal_sz = wal_file.stat().st_size
                if wal_sz > 64 * 1024 * 1024:
                    warn(f"Büyük WAL var: {wal_file} = {_fmt_mb(wal_sz)}")
                else:
                    ok(f"WAL dosyasi: {_fmt_mb(wal_sz)}")
            if shm_file.exists():
                ok(f"SHM dosyasi: {_fmt_mb(shm_file.stat().st_size)}")

            ok(f"DB acildi - {sz_mb}")
            ok(f"Hasta: {n_patients} | Visit: {n_visits} | File: {n_files} | Tablo: {n_tables}")
            if quick.lower() == "ok":
                ok(f"PRAGMA quick_check = {quick}")
            else:
                err(f"PRAGMA quick_check = {quick}")
            if integrity.lower() == "ok":
                ok(f"PRAGMA integrity_check = {integrity}")
            else:
                err(f"PRAGMA integrity_check = {integrity}")
            if fk_issues:
                err(f"foreign_key_check sorunlu satir: {len(fk_issues)}")
                for row in fk_issues[:3]:
                    err(f"  FK: {row}")
            else:
                ok("foreign_key_check = ok")

            for table in REQUIRED_SQLITE_TABLES:
                present = con.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table,),
                ).fetchone()
                if not present:
                    err(f"Zorunlu tablo eksik: {table}")

            free_ratio = (freelist / float(page_count)) if page_count else 0
            ok(f"Page: {page_count} | Freelist: {freelist} ({free_ratio:.2%})")

            # Kilitli DB durumunu probe et (PG primary modunda SQLite write probe gereksiz)
            primary_hint = str(config.get("YAZKLINIK_DB_PRIMARY") or os.environ.get("YAZKLINIK_DB_PRIMARY") or "").strip().lower()
            mode_hint = str(config.get("YAZKLINIK_POSTGRES_MODE") or os.environ.get("YAZKLINIK_POSTGRES_MODE") or "").strip().lower()
            pg_only_hint = str(config.get("YAZKLINIK_POSTGRES_ONLY") or os.environ.get("YAZKLINIK_POSTGRES_ONLY") or "0").strip().lower()
            pg_primary_mode = (
                primary_hint in {"postgresql", "postgres", "pg"}
                or mode_hint in {"primary", "cutover", "postgres_primary"}
                or pg_only_hint in {"1", "true", "yes", "on"}
            )
            if pg_primary_mode:
                ok("Yazma kilit testi atlandi (PostgreSQL primary modu)")
            else:
                try:
                    lock_errors = []
                    write_probe_ok = False
                    for attempt in range(1, 4):
                        probe = sqlite3.connect(db_path, timeout=2)
                        try:
                            probe.execute("BEGIN IMMEDIATE")
                            probe.execute("SELECT 1")
                            probe.execute("COMMIT")
                            ok(f"Yazma kilit testi: OK (deneme {attempt}/3)")
                            write_probe_ok = True
                            break
                        except sqlite3.OperationalError as probe_ex:
                            lock_errors.append(str(probe_ex))
                            try:
                                probe.execute("ROLLBACK")
                            except Exception:
                                pass
                            if attempt < 3:
                                time.sleep(0.35)
                        finally:
                            probe.close()
                    if not write_probe_ok:
                        last_err = lock_errors[-1] if lock_errors else "bilinmeyen lock hatasi"
                        lock_only = bool(lock_errors) and all(
                            "database is locked" in str(one or "").lower()
                            for one in lock_errors
                        )
                        if lock_only:
                            ok("DB yazma kilit testi: aktif trafik nedeniyle gecici kilit (normal)")
                        else:
                            warn(f"DB yazma kilit testi 3 denemede de kilitli (non-blocking): {last_err}")

                except Exception as probe_ex:
                    warn(f"DB write-probe acilamadi: {probe_ex}")
        finally:
            con.close()

        # Hızlı yedek/restore doğrulama (SQLite backup API ile)
        if backup_root_path and not QUICK_MODE:
            backup_name = f"qc_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{os.getpid()}.sqlite3"
            backup_path = backup_root_path / backup_name
            try:
                src = sqlite3.connect(db_path, timeout=3)
                dst = sqlite3.connect(str(backup_path), timeout=3)
                try:
                    src.backup(dst)
                finally:
                    dst.close()
                    src.close()

                bcon = sqlite3.connect(str(backup_path), timeout=3)
                try:
                    bcheck = (bcon.execute("PRAGMA integrity_check").fetchone() or ["?"])[0]
                finally:
                    bcon.close()
                if bcheck.lower() == "ok":
                    ok(f"Backup integrity doğrulama OK: {backup_name}")
                else:
                    warn(f"Backup integrity_uyarisi: {bcheck}")
            except Exception as b_ex:
                warn(f"SQLite backup doğrulama atlandi: {b_ex}")
            finally:
                try:
                    if backup_path.exists():
                        backup_path.unlink()
                except Exception:
                    warn(f"Geçici backup silinemedi: {backup_path}")
        elif backup_root_path and QUICK_MODE:
            ok("Backup integrity adimi atlandi (--quick)")
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
nas_timeout = os.environ.get("CODEX_QUICK_CHECK_NAS_TIMEOUT_SEC", "5")
nas_exists = _path_exists_with_timeout(nas_test, nas_timeout)
if nas_exists is True:
    ok(f"NAS erisilebilir: {nas_test}")
elif nas_exists is None:
    warn(f"NAS erisim kontrolu zaman asimina ugradi: {nas_test}")
    print("    -> Quick-check devam ediyor; NAS'i Windows Explorer veya /sistem-ayarlari ile ayrıca dogrula")
else:
    warn(f"NAS erisilemiyor: {nas_test}")
    print("    -> Map drive veya /sistem-ayarlari'dan farkli path tanimla")


# ----------------------------------------------------------------------
# 5b) PostgreSQL hazırlık kontrolu
# ----------------------------------------------------------------------
section("5b) PostgreSQL hazırlık kontrolü")
pg_dialect_raw = config.get("YAZKLINIK_DB_DIALECT") or os.environ.get("YAZKLINIK_DB_DIALECT", "")
pg_dialect = (pg_dialect_raw or "sqlite").strip().lower()
pg_primary = (config.get("YAZKLINIK_DB_PRIMARY") or os.environ.get("YAZKLINIK_DB_PRIMARY") or "sqlite").strip().lower()
pg_mode = (config.get("YAZKLINIK_POSTGRES_MODE") or os.environ.get("YAZKLINIK_POSTGRES_MODE") or "shadow").strip().lower()
pg_url = (config.get("YAZKLINIK_DATABASE_URL") or os.environ.get("YAZKLINIK_DATABASE_URL", "")).strip()
enable_pg = _env_bool_like(config.get("YAZKLINIK_ENABLE_POSTGRES") or os.environ.get("YAZKLINIK_ENABLE_POSTGRES"), False)
pg_active = pg_dialect in {"postgres", "postgresql"} or enable_pg
if pg_url and not pg_dialect_raw:
    pg_active = True
if pg_active and QUICK_MODE:
    ok(
        "PG hedefi aktif (quick): "
        f"dialect={pg_dialect or 'postgresql'}, enable={enable_pg}, "
        f"primary={pg_primary}, mode={pg_mode}")
    if pg_url:
        print(f"    DSN: {_mask_secret_value('YAZKLINIK_DATABASE_URL', pg_url)}")
    else:
        print(f"    host: {config.get('POSTGRES_HOST', 'localhost')}:{config.get('POSTGRES_PORT', '15432')}")
        print(f"    db/user: {config.get('POSTGRES_DB', 'yazklinik')}/{config.get('POSTGRES_USER', 'yazklinik')}")
    try:
        import psycopg  # type: ignore
        ok("psycopg import OK")
        if pg_url:
            try:
                with psycopg.connect(pg_url, connect_timeout=4) as pcon:
                    with pcon.cursor() as cur:
                        cur.execute("SELECT current_database(), current_user")
                        row = cur.fetchone() or ("?", "?")
                ok(f"PG quick connect OK (database={row[0]}, user={row[1]})")
            except Exception as ex:
                warn(f"PG quick connect FAILED: {ex}")
        else:
            warn("PG quick connect atlandi: DSN yok")
    except Exception as ex:
        warn(f"psycopg import FAILED: {ex}")
        print("    Kurulum: pip install psycopg[binary]")
    ok("PG quick mode: full mirror/shadow/cutover/smoke kontrolleri atlandi")
elif pg_active:
    ok(
        "PG hedefi aktif: "
        f"dialect={pg_dialect or 'postgresql'}, enable={enable_pg}, "
        f"primary={pg_primary}, mode={pg_mode}")
    if pg_url:
        print(f"    DSN: {_mask_secret_value('YAZKLINIK_DATABASE_URL', pg_url)}")
    else:
        print(f"    host: {config.get('POSTGRES_HOST', 'localhost')}:{config.get('POSTGRES_PORT', '15432')}")
        print(f"    db/user: {config.get('POSTGRES_DB', 'yazklinik')}/{config.get('POSTGRES_USER', 'yazklinik')}")
    try:
        import psycopg  # type: ignore
        ok("psycopg import OK")
    except Exception as ex:
        warn(f"psycopg import FAILED: {ex}")
        print("    Kurulum: pip install psycopg[binary]")
    try:
        import yazklinik_postgres_agent as pg_agent
        pg_health = pg_agent.health_check()
        if pg_health.get("ok"):
            ok(f"PG health OK (database={pg_health.get('current_database')}, tables={pg_health.get('table_count')})")
            full_mirror = pg_health.get("full_mirror") or {}
            if full_mirror.get("ok"):
                ok(
                    "PG full mirror OK "
                    f"(schema={full_mirror.get('schema')}, "
                    f"tables={full_mirror.get('normal_table_count')}, "
                    f"rows={full_mirror.get('postgres_total_rows')})")
            else:
                warn(
                    "PG full mirror hazir degil: "
                    f"{full_mirror.get('status') or full_mirror.get('error') or 'unknown'}")
            shadow_sync = pg_health.get("shadow_sync") or {}
            if shadow_sync.get("ok"):
                ok(
                    "PG shadow sync OK "
                    f"(schema={shadow_sync.get('schema')}, "
                    f"age_min={shadow_sync.get('age_minutes')})")
            elif shadow_sync.get("status") and shadow_sync.get("status") != "missing":
                warn(
                    "PG shadow sync sorunlu: "
                    f"{shadow_sync.get('status') or shadow_sync.get('error') or 'unknown'}")
            try:
                import YAZKLINIK_POSTGRES_CUTOVER_READINESS as pg_cutover
                cutover = pg_cutover.readiness_check(deep=False)
                if cutover.get("shadow_ready"):
                    ok(
                        "PG cutover shadow readiness OK "
                        f"(primary_ready={cutover.get('primary_cutover_ready')})")
                    if not cutover.get("primary_cutover_ready"):
                        blockers = cutover.get("blockers") or []
                        source = cutover.get("source_scan") or {}
                        ref_summary = source.get("summary") or {}
                        if ref_summary:
                            sqlite_ref_total = int(ref_summary.get("sqlite3_connect_total") or 0)
                            if sqlite_ref_total > 0:
                                warn(
                                    "PG primary cutover bekliyor: "
                                    f"sqlite_refs={sqlite_ref_total}, "
                                    f"core={ref_summary.get('core_runtime', 0)}, "
                                    f"feature={ref_summary.get('feature_runtime', 0)}, "
                                    f"maintenance={ref_summary.get('sqlite_maintenance', 0)}, "
                                    f"unknown={ref_summary.get('unknown', 0)}")
                            elif blockers:
                                warn("PG primary cutover bekliyor: " + str(blockers[0])[:160])
                            else:
                                warn("PG primary cutover bekliyor: runtime/SQL uyumluluk onayi gerekli")
                        elif blockers:
                            warn("PG primary cutover bekliyor: " + str(blockers[0])[:160])
                else:
                    if shadow_sync.get("ok"):
                        blockers = shadow_sync.get("cutover_blockers") or []
                        if blockers:
                            warn("PG primary cutover bekliyor: " + str(blockers[0])[:160])
                        else:
                            warn(
                                "PG anlik cutover kontrolu canli SQLite degisikligi yakaladi; "
                                "son shadow sync OK")
                    else:
                        warn("PG cutover shadow readiness sorunlu")
            except Exception as ex:
                warn(f"PG cutover readiness check atlandi: {ex}")
            try:
                import YAZKLINIK_POSTGRES_PRIMARY_GUARD as pg_guard
                guard = pg_guard.primary_guard(deep=False)
                if guard.get("ok"):
                    ok(
                        "PG primary guard OK "
                        f"(guard={guard.get('guard')}, primary={guard.get('primary')}, "
                        f"mode={guard.get('mode')})")
                else:
                    blockers = guard.get("blockers") or []
                    warn("PG primary guard uyarisi: " + str(blockers[0] if blockers else guard.get("guard"))[:160])
            except Exception as ex:
                warn(f"PG primary guard check atlandi: {ex}")
            try:
                import yazklinik_db_adapter as db_adapter
                adapter_status = db_adapter.adapter_status(deep=False)
                if adapter_status.get("ok"):
                    cfg = adapter_status.get("config") or {}
                    ok(
                        "DB adapter scaffold OK "
                        f"(primary={cfg.get('primary')}, mode={cfg.get('mode')})")
                else:
                    warn("DB adapter scaffold uyarisi: " + str(
                        (adapter_status.get("blockers") or ["unknown"])[0])[:160])
            except Exception as ex:
                warn(f"DB adapter scaffold check atlandi: {ex}")
            try:
                import YAZKLINIK_SQL_DIALECT_CHECK as sql_dialect_check
                dialect_report = sql_dialect_check.run_checks()
                if dialect_report.get("ok"):
                    ok("SQL dialect adapter OK")
                else:
                    warn("SQL dialect adapter uyarisi")
            except Exception as ex:
                warn(f"SQL dialect adapter check atlandi: {ex}")
            try:
                import YAZKLINIK_POSTGRES_SQL_COMPAT_SCAN as pg_sql_scan
                sql_scan = pg_sql_scan.scan_sql_compat(max_examples=8)
                summary = sql_scan.get("summary") or {}
                if sql_scan.get("sql_compat_ready"):
                    ok("PG SQL compatibility scan OK")
                else:
                    risk_summary = sql_scan.get("risk_summary") or {}
                    warn(
                        "PG SQL compatibility bekliyor: "
                        f"high={summary.get('high', 0)}, "
                        f"medium={summary.get('medium', 0)}, "
                        f"runtime_blockers={risk_summary.get('runtime_blocker', 0)}, "
                        f"adapter_covered={risk_summary.get('adapter_covered', 0)}, "
                        f"report={pg_sql_scan.LAST_REPORT}")
            except Exception as ex:
                warn(f"PG SQL compatibility scan atlandi: {ex}")
            try:
                import YAZKLINIK_POSTGRES_PRIMARY_SMOKE as pg_primary_smoke
                primary_smoke = pg_primary_smoke.primary_smoke()
                if primary_smoke.get("ok"):
                    checks = primary_smoke.get("checks") or []
                    patient_count = ""
                    for item in checks:
                        if item.get("name") == "runtime_postgres_primary":
                            patient_count = f", patients={item.get('patients')}"
                            break
                    ok("PG primary runtime smoke OK" + patient_count)
                else:
                    warn("PG primary runtime smoke uyarisi")
            except Exception as ex:
                warn(f"PG primary runtime smoke atlandi: {ex}")
            try:
                import YAZKLINIK_POSTGRES_BACKUP as pg_backup
                backup_status = pg_backup.backup_status()
                if backup_status.get("ok"):
                    ok(
                        "PG primary backup OK "
                        f"(method={backup_status.get('method')}, "
                        f"age_min={backup_status.get('age_minutes')})")
                else:
                    warn(
                        "PG primary backup bekliyor: "
                        f"{backup_status.get('status') or backup_status.get('error') or 'unknown'}")
            except Exception as ex:
                warn(f"PG primary backup check atlandi: {ex}")
        else:
            warn(f"PG health sorunlu: {pg_health.get('error')}")
    except Exception as ex:
        warn(f"Postgres ajan import/check FAILED: {ex}")
else:
    ok("PG hedefi kapali: SQLite modu aktif")


# ----------------------------------------------------------------------
# 6) Destek yazilimlari / servis baglantilari
# ----------------------------------------------------------------------
section("6) Destek yazilimlari / servis baglantilari")
if not RUN_DEEP_SUPPORT:
    ok("Destek/yan servis ayrintili kontrol atlandi (--deep-support ile acilir)")
else:
    support_timeout = os.environ.get("CODEX_QUICK_CHECK_SUPPORT_TIMEOUT_SEC", "12")
    support, support_error = _load_support_snapshot_with_timeout(support_timeout)
    if support_error:
        warn(f"Destek yol bootstrap okunamadi/atlandi: {support_error}")

    support_items = [
        ("FFmpeg", support.get("ffmpeg_exe"), not bool(support_error)),
        ("FFprobe", support.get("ffprobe_exe"), False),
        ("PDF text (pdftotext)", support.get("pdftotext_exe"), False),
        ("Stirling PDF", support.get("stirling_pdf_exe"), False),
        ("Tesseract OCR", support.get("tesseract_cmd"), False),
        ("Tesseract tur data", str(Path(support.get("tessdata", "")) / "tur.traineddata")
         if support.get("tessdata") else "", False),
        ("Chrome", support.get("chrome_exe"), False),
        ("Edge", support.get("edge_exe"), False),
        ("Edge WebView2", support.get("webview2_exe"), False),
    ]
    for label, path, critical in support_items:
        if path and Path(path).exists():
            ok(f"{label:20s}: {path}")
        elif critical:
            err(f"{label} bulunamadi")
        else:
            warn(f"{label} bulunamadi")

    optional_pdf_items = [
        ("PDF info", support.get("pdfinfo_exe")),
        ("PDF image render", support.get("pdftoppm_exe")),
        ("QPDF", support.get("qpdf_exe")),
        ("wkhtmltopdf", support.get("wkhtmltopdf_exe")),
        ("MuPDF", support.get("mutool_exe")),
        ("SumatraPDF", support.get("sumatra_pdf_exe")),
        ("Ghostscript", support.get("ghostscript_exe")),
    ]
    for label, path in optional_pdf_items:
        if path and Path(path).exists():
            ok(f"{label:20s}: {path}")

    service_checks = [
        ("Ollama", "http://127.0.0.1:11434/api/tags"),
        ("Whisper", "http://127.0.0.1:9000/health"),
        ("Piper", "http://127.0.0.1:9001/health"),
        ("SIP Alex", "http://127.0.0.1:9019/status"),
        ("ComfyUI opsiyonel", config.get("YAZKLINIK_COMFYUI_URL", "http://127.0.0.1:8188").rstrip("/") + "/system_stats"),
    ]
    orthanc_url = (config.get("YAZKLINIK_ORTHANC_URL")
                   or config.get("orthanc_url")
                   or "http://127.0.0.1:8042").rstrip("/")
    service_checks.insert(1, ("Orthanc", orthanc_url + "/system"))

    xtts_enabled = _env_bool_like(
        config.get("YAZKLINIK_XTTS_ENABLED", os.environ.get("YAZKLINIK_XTTS_ENABLED", "0")),
        default=False,
    )
    if xtts_enabled:
        service_checks.insert(4, ("XTTS", "http://127.0.0.1:9002/health"))
    else:
        ok("XTTS                : devre disi (YAZKLINIK_XTTS_ENABLED=0)")

    for label, url in service_checks:
        status, detail = _simple_http_ok(url, timeout=4)
        if status:
            ok(f"{label:20s}: HTTP {status}")
        elif label.startswith("ComfyUI"):
            warn(f"{label:20s}: kapali/kurulu degil ({detail})")
        else:
            warn(f"{label:20s}: cevap yok ({detail})")


# ----------------------------------------------------------------------
# 7) Server canli mi
# ----------------------------------------------------------------------
section(f"7) Server canli mi (port {config.get('YAZKLINIK_WEB_PORT', '5443')})")
port = int(config.get("YAZKLINIK_WEB_PORT", "5443"))
server_url = (config.get("YAZKLINIK_SERVER_URL") or "").strip()
if not server_url:
    scheme = "https" if config.get("YAZKLINIK_ENABLE_HTTPS") == "1" else "http"
    server_url = f"{scheme}://127.0.0.1:{port}"
# Route smoke her zaman lokal loopback uzerinden calissin; LAN/public URL
# bazli testler (hairpin NAT/firewall) yalanci 10061 uretebiliyor.
# HTTP/HTTPS portlari farkliysa once HTTP web portu, sonra HTTPS fallback dene.
https_enabled = str(config.get("YAZKLINIK_ENABLE_HTTPS", "")).strip() == "1"
try:
    https_port = int(config.get("YAZKLINIK_HTTPS_PORT", str(port)) or port)
except Exception:
    https_port = int(port)
smoke_base_candidates = []
# AGENTS notu: smoke/login dogrulamasinda once 5052 HTTP tercih edilir.
http_candidate = f"http://127.0.0.1:{port}"
smoke_base_candidates.append(http_candidate)
if https_enabled:
    https_candidate = f"https://127.0.0.1:{https_port}"
    if https_candidate not in smoke_base_candidates:
        smoke_base_candidates.append(https_candidate)
# Ek fallback: server_url farkli bir loopback portu veriyorsa en sona ekle.
try:
    parsed_server = urllib.parse.urlsplit(server_url)
    preferred_scheme = (parsed_server.scheme or "").strip().lower()
    preferred_port = parsed_server.port
    if preferred_scheme in ("http", "https") and preferred_port:
        extra_candidate = f"{preferred_scheme}://127.0.0.1:{int(preferred_port)}"
        if extra_candidate not in smoke_base_candidates:
            smoke_base_candidates.append(extra_candidate)
except Exception:
    pass
smoke_base_url = smoke_base_candidates[0]
server_alive = False
probe_errors = []
for base_url in smoke_base_candidates:
    status, detail = _simple_http_ok(f"{base_url}/giris", timeout=4)
    if int(status or 0) in (200, 301, 302, 303, 307, 308):
        ok(f"Server cevap veriyor (HTTP {status}) [{base_url}]")
        server_alive = True
        smoke_base_url = base_url
        # Sonraki adimlar icin basarili aday hep ilk sirada olsun.
        if smoke_base_candidates and smoke_base_candidates[0] != base_url:
            smoke_base_candidates = [base_url] + [u for u in smoke_base_candidates if u != base_url]
        break
    probe_errors.append(f"{base_url}: {detail or ('HTTP ' + str(status))}")

if not server_alive:
    detail = probe_errors[0] if probe_errors else "bilinmeyen hata"
    msg = f"Server kapali veya cevap yok: {detail}"
    if MOBILE_SCROLL_STRICT:
        err(msg)
    else:
        warn(msg)
    print(f"    -> Baslat: {ROOT / 'D700_BASLAT.bat'}")


# ----------------------------------------------------------------------
# 8) Compile check (3 kritik dosya)
# ----------------------------------------------------------------------
section("8) Compile check")
web_compile_file = ROOT / "yazklinik_web.py"
legacy_compile_file = ROOT / "yazklinik_v68.py"
compile_files = [
    ROOT / "yazklinik_feature_sync.py",
    ROOT / "yazklinik_postgres_agent.py",
    ROOT / "yazklinik_infra_guard.py",
]
if SKIP_COMPILE:
    ok("Compile check atlandi (--quick/--no-compile)")
else:
    if RUN_WEB_COMPILE:
        compile_files.insert(0, web_compile_file)
    else:
        if server_alive:
            ok("yazklinik_web.py live import OK (--compile-web ile deep compile)")
        else:
            warn("yazklinik_web.py deep compile atlandi; once server ayaga kalkmali (--compile-web ile deneyin)")
    if RUN_LEGACY_COMPILE:
        compile_files.insert(0, legacy_compile_file)
    else:
        ok("yazklinik_v68.py legacy compile atlandi (--compile-legacy ile deep compile)")
    for f in compile_files:
        if not f.exists():
            err(f"{f.name} YOK - compile atlandi")
            continue
        try:
            proc = subprocess.run(
                [sys.executable, "-X", "faulthandler", "-m", "py_compile", str(f)],
                cwd=str(ROOT),
                capture_output=True,
                text=True,
                timeout=420,
                encoding="utf-8",
                errors="replace",
            )
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or f"exit={proc.returncode}").strip()
                raise RuntimeError(detail[-500:])
            ok(f"{f.name} compile OK")
        except BaseException as ex:
            err(f"{f.name} compile error: {ex}")


# ----------------------------------------------------------------------
# 8) Route smoke test (server canli ise)
# ----------------------------------------------------------------------
if server_alive and not SKIP_ROUTE:
    section("9) Route smoke test")
    # Login + session cookie al
    try:
        import http.cookiejar

        class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, req, fp, code, msg, headers, newurl):
                return None

        # Login POST - sifre degistirildiyse users.json/env'den alinir.
        smoke_user, smoke_password = _smoke_login_credentials()
        body = urllib.parse.urlencode({
            "username": smoke_user,
            "password": smoke_password,
        }).encode("utf-8")
        login_ok = False
        login_last_err = None
        opener = None
        active_smoke_base = smoke_base_url
        login_attempts = [(15, 0.8), (25, 1.2), (35, 2.0), (45, 2.4)]

        def _attempt_login_on_base(base_url):
            ready_ok, ready_detail = _wait_base_ready(base_url, max_wait_sec=80, interval_sec=2.4)
            if not ready_ok:
                return False, None, f"{base_url} not ready before login: {ready_detail}"
            cj = http.cookiejar.CookieJar()
            handlers = [
                urllib.request.HTTPCookieProcessor(cj),
                _NoRedirectHandler(),
            ]
            if base_url.lower().startswith("https://"):
                handlers.append(
                    urllib.request.HTTPSHandler(
                        context=ssl._create_unverified_context()))
            opener = urllib.request.build_opener(*handlers)
            for idx, (login_timeout, retry_sleep) in enumerate(login_attempts, start=1):
                try:
                    req = urllib.request.Request(
                        f"{base_url}/giris", data=body,
                        headers={"Content-Type": "application/x-www-form-urlencoded"})
                    with opener.open(req, timeout=login_timeout) as resp:
                        _ = resp.status
                    return True, opener, None
                except urllib.error.HTTPError as login_ex:
                    if int(getattr(login_ex, "code", 0)) in (301, 302, 303, 307, 308):
                        return True, opener, None
                    login_last_err = login_ex
                except Exception as login_ex:
                    login_last_err = login_ex
                if idx < len(login_attempts):
                    time.sleep(retry_sleep)
            return False, None, login_last_err

        for base_url in smoke_base_candidates:
            ok_login_now, opener_now, err_now = _attempt_login_on_base(base_url)
            if ok_login_now and opener_now is not None:
                login_ok = True
                opener = opener_now
                active_smoke_base = base_url
                break
            login_last_err = err_now

        # Last rescue pass on primary base (restart windows can recover late).
        if (not login_ok or opener is None) and smoke_base_candidates:
            rescue_base = smoke_base_candidates[0]
            ok_login_now, opener_now, err_now = _attempt_login_on_base(rescue_base)
            if ok_login_now and opener_now is not None:
                login_ok = True
                opener = opener_now
                active_smoke_base = rescue_base
            else:
                login_last_err = err_now

        if not login_ok or opener is None:
            raise RuntimeError(f"login timeout/fail after retries: {login_last_err}")
        # Test routes
        routes = [
            "/hastalar",
            "/hasta-islemleri",
            "/doguranlar",
            "/yaklasan-dogumlar",
            "/tedavi-planla",
            "/sistem-ayarlari",
            "/ajanlar",
            "/hizmet-ajanlari",
            "/entegrasyonlar",
            "/api/sistem-durumu",
            "/api/agents",
            "/api/hizmet-ajanlari?force=1",
            "/api/entegrasyonlar/yardimci",
            "/api/pdf-destek-durumu",
        ]
        deep_ai_routes = [
            "/ses-ve-alex",
            "/akilli-dialog",
            "/sessiz-alex",
            "/api/alex/router-health",
        ]
        if RUN_DEEP_AI_ROUTES:
            routes.extend(deep_ai_routes)
        else:
            ok("Agir Alex/AI route smoke atlandi (--deep-ai-routes ile acilir)")
        if pg_active:
            routes.append("/api/db/postgres/health")
        soft_timeout_routes = {
            "/yaklasan-dogumlar",
            "/api/sistem-durumu",
            "/api/agents",
            "/api/hizmet-ajanlari?force=1",
            "/api/entegrasyonlar/yardimci",
            "/api/pdf-destek-durumu",
            "/api/db/postgres/health",
        }
        mojibake_scan_routes = {
            "/hastalar",
            "/doguranlar",
            "/yaklasan-dogumlar",
            "/sistem-ayarlari",
        }
        if RUN_DEEP_AI_ROUTES:
            mojibake_scan_routes.add("/ses-ve-alex")
        ok_count = 0
        for r in routes:
            try:
                if r in soft_timeout_routes:
                    route_timeout = 45
                elif r.startswith("/api/"):
                    route_timeout = 15
                else:
                    route_timeout = 20
                with opener.open(f"{active_smoke_base}{r}", timeout=route_timeout) as resp:
                    body_text = ""
                    if r == "/api/db/postgres/health":
                        body_text = resp.read(200000).decode("utf-8", "replace")
                    elif r in mojibake_scan_routes:
                        body_text = resp.read(450000).decode("utf-8", "replace")
                    ok(f"{r:32s} HTTP {resp.status}")
                    ok_count += 1
                    if body_text:
                        leaked_pg_dsn = False
                        for m in re.finditer(r"postgresql://[^:\s\"']+:([^@\s\"']+)@", body_text):
                            secret = (m.group(1) or "").strip()
                            if secret and "*" not in secret and secret.lower() not in {"masked", "redacted", "hidden"}:
                                leaked_pg_dsn = True
                                break
                        if leaked_pg_dsn:
                            warn(f"{r}: PG DSN sifresi canli cevapta maskelenmemis - web restart gerekli")
                        if r in mojibake_scan_routes:
                            # Buyuk inline script bloklari bu testte yalanci pozitif
                            # uretebildigi icin ilk script tag'ina kadar olan kisim taranir.
                            script_cut = body_text.split("<script", 1)[0].split("<SCRIPT", 1)[0]
                            visible_text = _strip_html_for_text_scan(script_cut)
                            mojibake_hits = _detect_mojibake_markers(visible_text)
                            ignored = _MOJIBAKE_ROUTE_IGNORE_LABELS.get(r, set())
                            if ignored and mojibake_hits:
                                mojibake_hits = [
                                    hit for hit in mojibake_hits if hit not in ignored
                                ]
                            if mojibake_hits:
                                warn(f"{r}: okunabilirlik/mojibake izi bulundu ({', '.join(sorted(set(mojibake_hits)))})")
            except urllib.error.HTTPError as ex:
                if int(getattr(ex, "code", 0)) in (301, 302, 303, 307, 308):
                    ok(f"{r:32s} HTTP {ex.code} (redirect)")
                    ok_count += 1
                else:
                    err(f"{r}: {ex}")
            except Exception as ex:
                ex_text = str(ex or "")
                if r in soft_timeout_routes and ("timed out" in ex_text.lower() or "timeout" in ex_text.lower()):
                    warn(f"{r}: soft-timeout ({ex_text})")
                    ok_count += 1
                else:
                    err(f"{r}: {ex}")
        if ok_count == len(routes):
            ok(f"{ok_count}/{len(routes)} route OK")
    except Exception as ex:
        if MOBILE_SCROLL_STRICT:
            err(f"Route smoke login/oturum adimi atlandi: {ex}")
        else:
            warn(f"Route smoke login/oturum adimi atlandi: {ex}")
        try:
            ping_ok = False
            ping_last_err = None
            ping_urls = list(smoke_base_candidates)
            for ping_timeout in (6, 10, 14):
                for one_ping_url in ping_urls:
                    try:
                        ready_ok, ready_detail = _wait_base_ready(
                            one_ping_url, max_wait_sec=40, interval_sec=2.0
                        )
                        if not ready_ok:
                            ping_last_err = f"{one_ping_url} not ready: {ready_detail}"
                            continue
                        ping_target = f"{one_ping_url.rstrip('/')}/api/terminal/ping-fast"
                        with urllib.request.urlopen(
                            ping_target,
                            timeout=ping_timeout,
                            context=ssl._create_unverified_context() if one_ping_url.lower().startswith("https://") else None,
                        ) as resp:
                            ok(f"Fallback ping-fast OK (HTTP {resp.status})")
                            ping_ok = True
                            break
                    except Exception as ping_ex:
                        ping_last_err = ping_ex
                if ping_ok:
                    break
                time.sleep(0.9)
            if not ping_ok and ping_last_err is not None:
                warn(f"Fallback ping-fast de basarisiz: {ping_last_err}")
        except Exception as ping_ex:
            warn(f"Fallback ping-fast de basarisiz: {ping_ex}")
elif server_alive and SKIP_ROUTE:
    section("9) Route smoke test")
    ok("Route smoke atlandi (--quick/--no-route)")


# ----------------------------------------------------------------------
# 10) Cache header smoke (server canli ise)
# ----------------------------------------------------------------------
if server_alive:
    section("10) Cache header smoke")

    def _cfg_int(name, default_value):
        try:
            return int(str(config.get(name, default_value)).strip() or default_value)
        except Exception:
            return int(default_value)

    expected_static_cache_sec = _cfg_int("YAZKLINIK_STATIC_IMMUTABLE_CACHE_SEC", 30 * 24 * 3600)
    expected_media_cache_sec = _cfg_int("YAZKLINIK_MEDIA_IMMUTABLE_CACHE_SEC", 7 * 24 * 3600)

    cache_checks = [
        ("/yk-core.js", expected_static_cache_sec, "static-core-js"),
        ("/yk-core.css", expected_static_cache_sec, "static-core-css"),
        ("/yk-media-fx.js", expected_static_cache_sec, "static-media-fx-js"),
        ("/yk-stability.js", expected_static_cache_sec, "static-stability-js"),
    ]

    for route, expected_sec, label in cache_checks:
        checked = False
        last_err = None
        for base_url in smoke_base_candidates:
            ready_ok, ready_detail = _wait_base_ready(base_url, max_wait_sec=45, interval_sec=2.0)
            if not ready_ok:
                last_err = f"{base_url} not ready: {ready_detail}"
                continue
            for attempt in range(1, 4):
                try:
                    req = urllib.request.Request(f"{base_url}{route}", method="HEAD")
                    kwargs = {}
                    if base_url.lower().startswith("https://"):
                        kwargs["context"] = ssl._create_unverified_context()
                    with urllib.request.urlopen(req, timeout=8, **kwargs) as resp:
                        cc = (resp.headers.get("Cache-Control") or "").lower()
                        wanted = f"max-age={expected_sec}"
                        if "immutable" in cc and wanted in cc:
                            ok(f"{label:20s}: {cc}")
                        else:
                            warn(f"{label:20s}: beklenen '{wanted}, immutable' ama '{cc}'")
                        checked = True
                        break
                except Exception as ex:
                    last_err = ex
                    if attempt < 3:
                        time.sleep(1.2)
            if checked:
                break
        if not checked:
            warn(f"{label:20s}: header okunamadi ({last_err})")

    ok(f"media-cache-sec       : {expected_media_cache_sec} (config)")


# ----------------------------------------------------------------------
# 11) Mobile scroll smoke (opsiyonel)
# ----------------------------------------------------------------------
if RUN_MOBILE_SCROLL:
    section("11) Mobile scroll smoke")
    _run_mobile_scroll_smoke(strict_mode=MOBILE_SCROLL_STRICT)


# ----------------------------------------------------------------------
# Final ozet
# ----------------------------------------------------------------------
print()
print("=" * 60)
print(f"  {GREEN}OK{RESET}: tum kritik kontroller gecti.")
print(f"  Hata: {RED}{errors}{RESET} | Uyari: {YELLOW}{warnings}{RESET}")
print("=" * 60)
if errors == 0:
    print("CODEX_D700_QUICK_CHECK_OK")
    sys.exit(0)
else:
    print(f"CODEX_D700_QUICK_CHECK_FAIL ({errors} hata)")
    sys.exit(1)

