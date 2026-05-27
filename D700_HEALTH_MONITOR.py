r"""YazKlinik D700 Health Monitor.

Her 30 saniyede bir servis sağlığını kontrol eder; düşen servisi otomatik restart eder.
Aktif kontrol edilen servisler:
  - Web 5443 (yazklinik_web.py)
  - Hasta Portal 5053 (yazklinik_patient_portal_public.py)
  - Whisper 9000 (yazklinik_whisper_service.py)
  - XTTS 9002 (yazklinik_xtts_service.py)
  - Piper 9001 (yazklinik_piper_service.py)
  - Alex SIP 9019 (yazklinik_sip_alex_client.py)

Calistirma:
  Set-Location D:\YazKlinik_Final_D700
  & "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" D700_HEALTH_MONITOR.py

Veya arka planda:
  Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "D700_HEALTH_MONITOR.py" -WindowStyle Hidden
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "Scripts", "python.exe")
VENV_PYW = os.path.join(HERE, ".venv", "Scripts", "pythonw.exe")
SERVICE_RUNNER = os.path.join(HERE, "D700_SERVICE_RUNNER.py")
CONFIG_ENV = os.path.join(HERE, "config.env")


def _prime_env_from_config() -> None:
    """Populate os.environ from config.env before module-level thresholds.

    Health monitor can be launched by external helpers that do not pre-load
    config.env. In that case fail/restart thresholds silently fall back to
    defaults and web restart latency increases.
    """
    if not os.path.exists(CONFIG_ENV):
        return
    try:
        with open(CONFIG_ENV, "r", encoding="utf-8-sig", errors="replace") as fh:
            for raw in fh:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if key:
                    val = value.strip()
                    # D700 2026-05-27: Health monitor threshold/env degerleri
                    # parent process'ten sizan stale env ile degismemeli.
                    # YAZKLINIK_HEALTH_* anahtarlarinda config.env her zaman
                    # birincil kaynak olsun; diger anahtarlarda mevcut davranis
                    # (setdefault) korunsun.
                    if key.upper().startswith("YAZKLINIK_HEALTH_"):
                        os.environ[key] = val
                    else:
                        os.environ.setdefault(key, val)
    except Exception:
        pass


_prime_env_from_config()

# Servis tanimlari: name -> (url, script, log, error_log, env_overrides)
SERVICES = [
    ("web", os.environ.get("YAZKLINIK_HEALTH_WEB_URL")
     or "http://127.0.0.1:5052/api/terminal/ping-fast",
     "yazklinik_web.py", "D700_server.log", "D700_server_HATA.log", {}),
    ("patient_portal", os.environ.get("YAZKLINIK_HEALTH_PATIENT_PORTAL_URL")
     or "http://127.0.0.1:5053/healthz",
     "yazklinik_patient_portal_public.py", "D700_patient_portal.log",
     "D700_patient_portal.err.log", {}),
    ("whisper", "http://127.0.0.1:9000/health",
     "yazklinik_whisper_service.py", "D700_whisper_service.log",
     "D700_whisper_service.err.log",
     {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}),
    ("xtts", "http://127.0.0.1:9002/health",
     "yazklinik_xtts_service.py", "D700_xtts_service.log",
     "D700_xtts_service.err.log",
     {"COQUI_TOS_AGREED": "1"}),
    ("piper", "http://127.0.0.1:9001/health",
     "yazklinik_piper_service.py", "D700_piper_service.log",
     "D700_piper_service.err.log", {}),
    ("comfyui", "http://127.0.0.1:8188/system_stats",
     "D700_COMFYUI_RUNNER.py", "D700_comfyui.log",
     "D700_comfyui.err.log", {}),
    ("sip_alex", "http://127.0.0.1:9019/status",
     "yazklinik_sip_alex_client.py", "D700_sip_alex.log",
     "D700_sip_alex.err.log", {}),
]


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "on", "evet", "aktif"}


def _active_services(base_env: dict[str, str]):
    """Honor optional-service switches from config.env/runtime env."""
    xtts_enabled = _env_bool("YAZKLINIK_XTTS_ENABLED", False)
    patient_portal_enabled = _env_bool("YAZKLINIK_PATIENT_PORTAL_ENABLED", True)
    if not base_env:
        base_env = {}
    # D700 2026-05-27: web health monitor asla kazara devre disi kalmamali.
    # Web'i kapatmak yalnizca explicit FORCE_OFF anahtari ile mumkundur.
    web_force_off = _env_bool("YAZKLINIK_HEALTH_WEB_ENABLED_FORCE_OFF", False)
    raw_web_force_off = str(
        base_env.get("YAZKLINIK_HEALTH_WEB_ENABLED_FORCE_OFF", "") or ""
    ).strip()
    if raw_web_force_off:
        web_force_off = raw_web_force_off.lower() in {"1", "true", "yes", "on", "evet", "aktif"}
    raw_cfg = str(base_env.get("YAZKLINIK_XTTS_ENABLED", "") or "").strip()
    if raw_cfg:
        xtts_enabled = raw_cfg.lower() in {"1", "true", "yes", "on", "evet", "aktif"}
    raw_portal_cfg = str(base_env.get("YAZKLINIK_PATIENT_PORTAL_ENABLED", "") or "").strip()
    if raw_portal_cfg:
        patient_portal_enabled = raw_portal_cfg.lower() in {"1", "true", "yes", "on", "evet", "aktif"}
    active = []
    for item in SERVICES:
        name = item[0]
        if name == "web" and web_force_off:
            continue
        if name == "xtts" and not xtts_enabled:
            continue
        if name == "patient_portal" and not patient_portal_enabled:
            continue
        active.append(item)
    return active

# D700 2026-05-19: Web kontrolu tek endpoint'e bagli kalmasin.
# HTTPS 5443 gecici takildiginda ama HTTP 5052 ayaktayken restart firtinasi
# olusuyordu. Her iki URL de saglik icin kabul edilir.
WEB_FALLBACK_URL = (
    os.environ.get("YAZKLINIK_HEALTH_WEB_FALLBACK_URL")
    or "https://127.0.0.1:5443/api/terminal/ping-fast"
)
# D700 2026-05-27: managed-owner kontrolu restart firtinasi yaratabiliyor.
# Kod seviyesinde kapali tutulur; port/HTTP saglik kontrolu tek otoritedir.
WEB_ENFORCE_MANAGED_OWNER = False


def _env_int(name: str, default: int) -> int:
    try:
        return int(str(os.environ.get(name, default)).strip())
    except Exception:
        return int(default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(str(os.environ.get(name, default)).strip())
    except Exception:
        return float(default)


# D700 2026-05-23: Startup firtinasi korumasi.
# Sahadaki gecici debug ayarlari (10s check, 20s grace, web fail=1) web'i
# ayaga kalkmadan oldurup restart dongusu uretiyordu. Bu nedenle minimum
# guvenli taban degerleri zorunlu.
CHECK_INTERVAL = max(20, _env_int("YAZKLINIK_HEALTH_CHECK_INTERVAL_SEC", 30))
RESTART_GRACE = max(25, _env_int("YAZKLINIK_HEALTH_RESTART_GRACE_SEC", 30))
INITIAL_GRACE = max(300, _env_int("YAZKLINIK_HEALTH_INITIAL_GRACE_SEC", 300))
MIN_RESTART_INTERVAL = max(120, _env_int("YAZKLINIK_HEALTH_MIN_RESTART_SEC", 180))
# D700 2026-05-18: Restart firtinasi tedavisi. Web yogun yukte /giris cevabi
# gecikebilir; tek check timeout'unda surec oldurmek 30-60sn downtime (SIP
# webhook 10061) yaratiyordu. N kez ust uste fail sart.
FAIL_THRESHOLD = max(3, _env_int("YAZKLINIK_HEALTH_FAIL_THRESHOLD", 3))
CHECK_TIMEOUT = _env_float("YAZKLINIK_HEALTH_CHECK_TIMEOUT_SEC", 20.0)
WEB_CHECK_TIMEOUT = _env_float("YAZKLINIK_HEALTH_WEB_CHECK_TIMEOUT_SEC", 6.0)
WEB_FAIL_THRESHOLD = int(
    os.environ.get(
        "YAZKLINIK_HEALTH_WEB_FAIL_THRESHOLD",
        str(max(FAIL_THRESHOLD, 6)),
    )
)
WEB_FAIL_THRESHOLD = max(6, WEB_FAIL_THRESHOLD)
# Web servis ayaga kalkma sureci (DB + SSL + preflight) uzun surebilir.
# Bu durumda web icin restart grace daha uzun tutulur.
WEB_RESTART_GRACE = max(
    300,
    RESTART_GRACE,
    _env_int("YAZKLINIK_HEALTH_WEB_RESTART_GRACE_SEC", 300),
)
SIP_ALEX_FAIL_THRESHOLD = int(
    os.environ.get(
        "YAZKLINIK_HEALTH_SIP_FAIL_THRESHOLD",
        str(max(FAIL_THRESHOLD, 6)),
    )
)
SIP_ALEX_FAIL_THRESHOLD = max(6, SIP_ALEX_FAIL_THRESHOLD)
TCP_SOFT_FAIL_THRESHOLD = max(
    8,
    _env_int("YAZKLINIK_HEALTH_TCP_SOFT_FAIL_THRESHOLD", 10),
)
WEB_ALLOW_TCP_DEGRADED = str(
    os.environ.get("YAZKLINIK_HEALTH_WEB_ALLOW_TCP_DEGRADED", "1")
).strip().lower() in {"1", "true", "yes", "on", "evet", "aktif"}
WEB_HARDDOWN_FAST_RESTART = str(
    os.environ.get("YAZKLINIK_HEALTH_WEB_HARDDOWN_FAST_RESTART", "0")
).strip().lower() in {"1", "true", "yes", "on", "evet", "aktif"} and str(
    os.environ.get("YAZKLINIK_HEALTH_WEB_HARDDOWN_FAST_RESTART_FORCE", "0")
).strip().lower() in {"1", "true", "yes", "on", "evet", "aktif"}
WEB_HARDDOWN_FAIL_THRESHOLD = max(
    6,
    _env_int("YAZKLINIK_HEALTH_WEB_HARDDOWN_FAIL_THRESHOLD", 6),
)
MONITOR_LOCK = Path(HERE) / "runtime_state" / "service_locks" / "D700_HEALTH_MONITOR.self.lock"
MONITOR_START_STAMP = Path(HERE) / "runtime_state" / "service_locks" / "D700_HEALTH_MONITOR.laststart"


def _hidden_subprocess_kwargs() -> dict:
    """Prevent short helper commands from flashing Windows Terminal windows."""
    if os.name != "nt":
        return {}
    kwargs = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return False
            code = ctypes.c_ulong()
            try:
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return False
                return code.value == 259
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except Exception:
        return False


def _acquire_monitor_lock() -> bool:
    MONITOR_LOCK.parent.mkdir(parents=True, exist_ok=True)
    while True:
        try:
            fd = os.open(str(MONITOR_LOCK), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w", encoding="ascii") as fh:
                fh.write(str(os.getpid()))
            return True
        except FileExistsError:
            lock_age_sec = 0.0
            try:
                lock_age_sec = max(0.0, time.time() - float(MONITOR_LOCK.stat().st_mtime))
            except Exception:
                lock_age_sec = 0.0
            try:
                old_pid = int(MONITOR_LOCK.read_text(encoding="ascii", errors="ignore").strip() or "0")
            except Exception:
                old_pid = 0
            # Race fix: if lock is brand new and PID not yet written, do not
            # remove it; wait for owner metadata to settle.
            if old_pid <= 0 and lock_age_sec < 5.0:
                time.sleep(0.2)
                continue
            if _pid_alive(old_pid):
                print(f"[{_ts()}] Baska health monitor aktif (PID {old_pid}); cikiliyor.", flush=True)
                return False
            try:
                MONITOR_LOCK.unlink()
            except Exception:
                return False


def _monitor_warm_restart_grace(grace_sec: int) -> int:
    """Reduce startup blind window when monitor respawns shortly after start."""
    try:
        now = time.time()
        prev_age = None
        if MONITOR_START_STAMP.exists():
            prev_age = max(0.0, now - float(MONITOR_START_STAMP.stat().st_mtime))
        MONITOR_START_STAMP.parent.mkdir(parents=True, exist_ok=True)
        MONITOR_START_STAMP.write_text(str(int(now)), encoding="ascii")
        if prev_age is None:
            return int(grace_sec)
        # D700 2026-05-27: full launcher can restart the monitor before the
        # web process finishes its slow import/listen phase. Short warm-grace
        # values caused false web restarts during normal boot, so keep a real
        # boot window even on rapid monitor respawns.
        if prev_age <= 900:
            return max(300, int(grace_sec))
    except Exception:
        pass
    return int(grace_sec)


def _interruptible_initial_grace(grace_sec: int, active_services: list[tuple]) -> None:
    """Wait startup grace, but do not stay blind if web process is absent.

    D700 field behavior: during failed boots, waiting the full grace window can
    delay web recovery for several minutes. If the web process is still missing
    after a short window, end grace early and let normal checks/restarts run.
    """
    total = max(0, int(grace_sec))
    if total <= 0:
        return
    has_web = any((one and one[0] == "web") for one in (active_services or []))
    started = time.time()
    while True:
        elapsed = int(max(0.0, time.time() - started))
        if elapsed >= total:
            return
        time.sleep(min(5, total - elapsed))
        elapsed = int(max(0.0, time.time() - started))
        if not has_web:
            continue
        if elapsed < 45:
            continue
        if not _project_web_process_active():
            print(
                f"[{_ts()}] Ilk acilis bekleme erken sonlandirildi: web process yok ({elapsed}s)",
                flush=True,
            )
            return


def _tcp_open(url: str, timeout: float = 1.5) -> bool:
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "127.0.0.1"
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


def _url_port(url: str) -> int:
    try:
        parsed = urlparse(url)
        return int(parsed.port or (443 if parsed.scheme == "https" else 80))
    except Exception:
        return 0


def _normalize_web_health_url(raw_url: str, default_url: str) -> str:
    """Force lightweight web health endpoint to avoid heavy /giris probes."""
    candidate = str(raw_url or "").strip() or str(default_url or "").strip()
    if not candidate:
        return "http://127.0.0.1:5052/api/terminal/ping-fast"
    try:
        p = urlparse(candidate)
        if not p.scheme or not p.netloc:
            raise ValueError("invalid")
        path = str(p.path or "").strip() or "/"
        folded = path.lower()
        if folded in {"/", "/giris", "/giris/"}:
            path = "/api/terminal/ping-fast"
        rebuilt = urlunparse((p.scheme, p.netloc, path, "", "", ""))
        return rebuilt
    except Exception:
        return str(default_url or "http://127.0.0.1:5052/api/terminal/ping-fast")


def _port_owner_pid(port: int) -> int:
    """Return LISTEN owner PID for a local TCP port on Windows."""
    if os.name != "nt" or not port:
        return 0
    try:
        cmd = (
            "Get-NetTCPConnection -LocalPort "
            f"{int(port)} -State Listen -ErrorAction SilentlyContinue | "
            "Select-Object -First 1 -ExpandProperty OwningProcess"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", cmd],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=4,
            **_hidden_subprocess_kwargs(),
        ).strip()
        return int(out.splitlines()[0].strip()) if out else 0
    except Exception:
        return 0


def _process_command_line(pid: int) -> str:
    if os.name != "nt" or pid <= 0:
        return ""
    try:
        cmd = (
            "$p=Get-CimInstance Win32_Process -Filter "
            f"'ProcessId={int(pid)}' -ErrorAction SilentlyContinue; "
            "if($p){$p.CommandLine}"
        )
        return subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", cmd],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=4,
            **_hidden_subprocess_kwargs(),
        ).strip()
    except Exception:
        return ""


def _process_parent_id(pid: int) -> int:
    if os.name != "nt" or pid <= 0:
        return 0
    try:
        cmd = (
            "$p=Get-CimInstance Win32_Process -Filter "
            f"'ProcessId={int(pid)}' -ErrorAction SilentlyContinue; "
            "if($p){$p.ParentProcessId}"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", cmd],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=4,
            **_hidden_subprocess_kwargs(),
        ).strip()
        return int(out.splitlines()[0].strip()) if out else 0
    except Exception:
        return 0


def _has_service_runner_ancestor(pid: int, max_depth: int = 8) -> bool:
    """Return True when a direct web child is supervised by D700 runner."""
    seen: set[int] = set()
    current = int(pid or 0)
    root_marker = str(Path(HERE).resolve()).lower()
    for _ in range(max(1, int(max_depth))):
        parent = _process_parent_id(current)
        if parent <= 0 or parent in seen:
            return False
        seen.add(parent)
        cmd = _process_command_line(parent).lower()
        if (
            "d700_service_runner.py" in cmd
            and (
                root_marker in cmd
                or "yazklinik_web.py" in cmd
                or "d700_server.log" in cmd
            )
        ):
            return True
        current = parent
    return False


def _project_web_process_active() -> bool:
    """Return True while YazKlinik web is booting, even before port 5052 opens."""
    if os.name != "nt":
        return False
    try:
        root = str(Path(HERE).resolve()).lower()
        ps_root = root.replace("'", "''")
        cmd = (
            "$root='" + ps_root + "'; "
            "Get-CimInstance Win32_Process | "
            "Where-Object { "
            "$c=[string]$_.CommandLine; "
            "$_.Name -match '^pythonw?\\.exe$' -and "
            "$c -and $c.ToLower().Contains($root) -and "
            "$c.ToLower().Contains('yazklinik_web.py') "
            "} | Select-Object -First 1 -ExpandProperty ProcessId"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", cmd],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=4,
            **_hidden_subprocess_kwargs(),
        ).strip()
        return bool(out)
    except Exception:
        return False


def _stop_process_tree(pid: int) -> bool:
    if os.name != "nt" or pid <= 0:
        return False
    try:
        result = subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=8,
            **_hidden_subprocess_kwargs(),
        )
        return result.returncode == 0
    except Exception:
        return False


def _service_lock_path(script: str) -> Path:
    safe_name = Path(script).stem.replace(" ", "_")
    return Path(HERE) / "runtime_state" / "service_locks" / f"{safe_name}.lock"


def _runner_pids_for_script(script: str) -> list[int]:
    """Collect runner PIDs that supervise a given service script."""
    if os.name != "nt":
        return []
    script_name = str(Path(script).name).lower()
    if not script_name:
        return []
    try:
        root = str(Path(HERE).resolve()).lower().replace("'", "''")
        svc = script_name.replace("'", "''")
        cmd = (
            "$root='" + root + "'; "
            "$svc='" + svc + "'; "
            "Get-CimInstance Win32_Process | "
            "Where-Object { "
            "$c=[string]$_.CommandLine; "
            "$_.Name -match '^pythonw?\\.exe$' -and $c -and "
            "$c.ToLower().Contains('d700_service_runner.py') -and "
            "$c.ToLower().Contains($svc) -and "
            "$c.ToLower().Contains($root) "
            "} | Select-Object -ExpandProperty ProcessId"
        )
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", cmd],
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=5,
            **_hidden_subprocess_kwargs(),
        )
        pids: list[int] = []
        for line in str(raw or "").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                one = int(line)
            except Exception:
                continue
            if one > 0:
                pids.append(one)
        return pids
    except Exception:
        return []


def _runner_root_pid(pid: int, script: str = "") -> int:
    """Find top-most D700_SERVICE_RUNNER ancestor for a service PID."""
    if os.name != "nt" or pid <= 0:
        return 0
    script_hint = str(Path(script).name).lower()
    seen: set[int] = set()
    current = int(pid)
    root_pid = 0
    for _ in range(10):
        if current <= 0 or current in seen:
            break
        seen.add(current)
        cmd = _process_command_line(current).lower()
        if "d700_service_runner.py" in cmd:
            if (not script_hint) or (script_hint in cmd):
                root_pid = current
        parent = _process_parent_id(current)
        if parent <= 0 or parent == current:
            break
        current = parent
    return int(root_pid or 0)


def _cleanup_web_instance_locks(base_env: dict | None = None) -> None:
    """Best-effort cleanup for stale temp web lock files before relaunch."""
    ports = {"5052"}
    try:
        if isinstance(base_env, dict):
            raw = str(base_env.get("YAZKLINIK_WEB_PORT", "") or "").strip()
            if raw.isdigit():
                ports.add(raw)
    except Exception:
        pass
    try:
        temp_root = Path(os.environ.get("TEMP", "")) / "YazKlinik" / "locks"
    except Exception:
        temp_root = Path(HERE) / "runtime_state" / "locks"
    for raw_port in ports:
        try:
            lock_path = temp_root / f"web_{int(raw_port)}.lock"
        except Exception:
            continue
        try:
            if lock_path.exists():
                lock_path.unlink()
        except Exception:
            pass


def _release_unhealthy_service_lock(script: str, base_env: dict | None = None) -> bool:
    """Drop stale runner lock safely before restart.

    Returns True only when lock ownership is cleared (or already absent).
    If lock owner cannot be terminated, restart is skipped to avoid spawning
    duplicate runner trees.
    """
    lock_path = _service_lock_path(script)
    if not lock_path.exists():
        return True
    try:
        lines = lock_path.read_text(encoding="ascii", errors="ignore").splitlines()
        old_pid = int((lines[0] if lines else "0").strip() or "0")
    except Exception:
        old_pid = 0
    # D700 2026-05-27: lock owner PID bazi makinelerde runner zincirinin
    # alt prosesi olabiliyor. Sadece alt PID kapaninca parent runner yeniden
    # dogurup cift web instance/lock loop uretebiliyor. Bu nedenle tum ilgili
    # runner PID'leri kill edilir.
    stop_targets: set[int] = set()
    if old_pid > 0:
        stop_targets.add(int(old_pid))
        root_pid = _runner_root_pid(old_pid, script)
        if root_pid > 0:
            stop_targets.add(int(root_pid))
    for one in _runner_pids_for_script(script):
        if one > 0:
            stop_targets.add(int(one))

    alive_targets = [pid for pid in sorted(stop_targets, reverse=True) if _pid_alive(pid)]
    if alive_targets:
        print(
            f"[{_ts()}] stale runner zinciri kapatiliyor ({script}): {', '.join(str(p) for p in alive_targets)}",
            flush=True,
        )
        for pid in alive_targets:
            _stop_process_tree(pid)
        time.sleep(1.2)
        still_alive = [pid for pid in alive_targets if _pid_alive(pid)]
        if still_alive:
            print(
                f"[{_ts()}] lock owner zinciri kapatilamadi; restart atlandi (PID: {', '.join(str(p) for p in still_alive)})",
                flush=True,
            )
            return False

    if str(Path(script).name).lower() == "yazklinik_web.py":
        _cleanup_web_instance_locks(base_env)

    for _ in range(3):
        try:
            lock_path.unlink()
            return True
        except FileNotFoundError:
            return True
        except PermissionError:
            time.sleep(0.2)
        except Exception:
            break
    return not lock_path.exists()


def _web_owner_is_unmanaged(url: str) -> tuple[bool, int, str]:
    """Detect Claude/nohup/direct web launches that steal a web port.

    The D700 launcher expects the web app to run through D700_SERVICE_RUNNER.
    A direct ``python yazklinik_web.py`` process can answer /giris but bypasses
    restart locks and can keep an old/half-tested Alex stack alive.
    """
    pid = _port_owner_pid(_url_port(url))
    if not pid:
        return False, 0, ""
    cmd = _process_command_line(pid)
    if not cmd:
        # Command-line bilgisi okunamiyorsa bu sureci "unmanaged" diye zorla
        # kapatma; aksi halde izin/yetki farkinda restart firtinasi olur.
        return False, pid, "<command-line-unavailable>"
    folded = cmd.lower()
    is_project_web = (
        "yazklinik_web.py" in folded
        and ("python.exe" in folded or "pythonw.exe" in folded)
    )
    is_runner = "d700_service_runner.py" in folded
    if is_project_web and not is_runner and _has_service_runner_ancestor(pid):
        return False, pid, cmd
    return bool(is_project_web and not is_runner), pid, cmd


def _open_restart_log(path: str):
    """Open a service log; if Windows has it locked, use a monitor-owned file."""
    try:
        return open(path, "ab")
    except PermissionError:
        fallback_dir = os.path.join(HERE, "runtime_state", "health_logs")
        os.makedirs(fallback_dir, exist_ok=True)
        base = os.path.basename(path)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        fallback = os.path.join(fallback_dir, f"{stamp}_{base}")
        return open(fallback, "ab")


def _ts():
    return datetime.now().strftime("%H:%M:%S")


def _load_config_env():
    """config.env'i env vars'a yukler (parent process icin)."""
    env = os.environ.copy()
    config_keys: set[str] = set()
    try:
        with open(CONFIG_ENV, "r", encoding="utf-8-sig", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                key = k.strip()
                env[key] = v.strip()
                config_keys.add(key)
    except Exception:
        pass
    try:
        from yazklinik_support_paths import apply_support_paths

        resolved = apply_support_paths()
        # D700 2026-05-27: config.env degerleri birincil kaynaktir.
        # apply_support_paths() sonrasinda os.environ'dan toplu update
        # yapildiginda parent process'teki stale env degerleri config'i
        # ezebiliyordu (ozellikle YAZKLINIK_HEALTH_*). Burada config'te
        # gelen anahtarlar korunur, kalan runtime env degerleri eklenir.
        for key, value in os.environ.items():
            if key in config_keys:
                continue
            env[key] = value
        for key, value in resolved.items():
            env[f"YAZKLINIK_SUPPORT_{key.upper()}"] = value
    except Exception:
        pass
    # D700 2026-05-27: takeover only explicit opt-in; default off.
    env.setdefault("YAZKLINIK_LOCK_TAKEOVER", "0")
    return env


def _cfg_bool(env_map: dict[str, str], key: str, default: bool) -> bool:
    raw = str(env_map.get(key, "1" if default else "0") or "").strip().lower()
    return raw in {"1", "true", "yes", "on", "evet", "aktif"}


def _cfg_int(env_map: dict[str, str], key: str, default: int) -> int:
    try:
        return int(str(env_map.get(key, default)).strip())
    except Exception:
        return int(default)


def _cfg_float(env_map: dict[str, str], key: str, default: float) -> float:
    try:
        return float(str(env_map.get(key, default)).strip())
    except Exception:
        return float(default)


def _check(url: str, timeout: float = None) -> tuple[bool, str]:
    """HTTP check - 200/302 OK. (healthy, reason) doner."""
    if timeout is None:
        timeout = CHECK_TIMEOUT
    try:
        import ssl
        import http.client

        parsed = urlparse(str(url or "").strip())
        scheme = (parsed.scheme or "http").lower()
        host = parsed.hostname or "127.0.0.1"
        port = int(parsed.port or (443 if scheme == "https" else 80))
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"

        conn = None
        if scheme == "https":
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            conn = http.client.HTTPSConnection(
                host,
                port=port,
                timeout=timeout,
                context=ctx,
            )
        else:
            conn = http.client.HTTPConnection(
                host,
                port=port,
                timeout=timeout,
            )

        conn.request(
            "GET",
            path,
            headers={
                "User-Agent": "D700-Health/1.0",
                "Connection": "close",
                "Cache-Control": "no-cache",
            },
        )
        resp = conn.getresponse()
        status = int(getattr(resp, "status", 0) or 0)
        try:
            resp.read(1)
        except Exception:
            pass
        try:
            conn.close()
        except Exception:
            pass
        if status in (200, 302):
            return True, "ok"
        return False, f"http_{status}"
    except Exception as exc:
        # Servis ayaga kalkmis ama HTTP health cevabi gecikiyor olabilir.
        # Port acik ama HTTP cevap yoksa healthy sayma; fail threshold zaten
        # tek gecici gecikmede restart firtinasini engelliyor.
        if _tcp_open(url):
            return False, f"tcp_ok_http_fail:{type(exc).__name__}"
        return False, f"down:{type(exc).__name__}"


def _check_many(urls: list[str], timeout: float = None) -> tuple[bool, str]:
    """Return healthy if any endpoint in the list is healthy."""
    if timeout is None:
        timeout = CHECK_TIMEOUT
    reasons = []
    seen = set()
    for raw in urls or []:
        url = str(raw or "").strip()
        if not url or url in seen:
            continue
        seen.add(url)
        ok, reason = _check(url, timeout=timeout)
        if ok:
            return True, f"{url} -> {reason}"
        reasons.append(f"{url} -> {reason}")
    if not reasons:
        return False, "no_check_url"
    return False, "; ".join(reasons)


def _fail_threshold_for(name: str, reason: str) -> int:
    """Service-specific fail threshold with TCP-soft-fail damping."""
    threshold = int(FAIL_THRESHOLD)
    if name == "web":
        threshold = max(threshold, int(WEB_FAIL_THRESHOLD))
    elif name == "sip_alex":
        threshold = max(threshold, int(SIP_ALEX_FAIL_THRESHOLD))
    if str(reason or "").startswith("tcp_ok_http_fail") and name in {"web", "sip_alex"}:
        threshold = max(threshold, int(TCP_SOFT_FAIL_THRESHOLD))
    return max(1, int(threshold))


def _service_min_restart_interval(name: str) -> int:
    """Allow per-service restart cooldown override from env."""
    safe = "".join(ch if ch.isalnum() else "_" for ch in str(name or "").upper())
    env_key = f"YAZKLINIK_HEALTH_{safe}_MIN_RESTART_SEC"
    raw = os.environ.get(env_key, "")
    try:
        value = int(str(raw or "").strip() or "0")
        if value > 0:
            if str(name or "").lower() == "web":
                # Keep web recovery bounded even if stale config injects
                # an overly conservative cooldown.
                return max(60, min(value, 180))
            return value
    except Exception:
        pass
    base = max(1, int(MIN_RESTART_INTERVAL))
    if str(name or "").lower() == "web":
        return max(60, min(base, 180))
    return base


def _restart(name: str, script: str, log: str, errlog: str,
             env_overrides: dict, base_env: dict) -> int:
    """Servisi yeniden baslat. PID doner."""
    print(f"[{_ts()}] RESTART {name}: {script}", flush=True)
    if not _release_unhealthy_service_lock(script, base_env):
        print(
            f"[{_ts()}] RESTART {name} atlandi: lock temizlenemedi ({script})",
            flush=True,
        )
        return 0
    env = base_env.copy()
    env.update(env_overrides)
    out_path = os.path.join(HERE, log)
    err_path = os.path.join(HERE, errlog)
    try:
        runner_py = VENV_PYW if os.path.exists(VENV_PYW) else VENV_PY
        flags = (
            subprocess.CREATE_NO_WINDOW
            | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "HIGH_PRIORITY_CLASS", 0x00000080)
        )
        proc = subprocess.Popen(
            [runner_py, SERVICE_RUNNER, os.path.join(HERE, script),
             out_path, err_path],
            cwd=HERE,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=flags,
            close_fds=True,
        )
        return proc.pid
    except Exception as exc:
        print(f"[{_ts()}] RESTART HATA {name}: {exc}", flush=True)
        return 0


def main():
    if not _acquire_monitor_lock():
        return
    base_env = _load_config_env()
    # D700 2026-05-27: Runtime ayarlari config.env'den tekrar hesaplanir.
    # Aksi halde parent process env'de kalan eski degerler (ornegin harddown=1)
    # monitoru yanlis threshold ile calistirabiliyor.
    global CHECK_INTERVAL, RESTART_GRACE, INITIAL_GRACE, MIN_RESTART_INTERVAL
    global FAIL_THRESHOLD, CHECK_TIMEOUT, WEB_CHECK_TIMEOUT, WEB_FAIL_THRESHOLD
    global WEB_RESTART_GRACE, SIP_ALEX_FAIL_THRESHOLD, TCP_SOFT_FAIL_THRESHOLD
    global WEB_ALLOW_TCP_DEGRADED, WEB_HARDDOWN_FAST_RESTART, WEB_HARDDOWN_FAIL_THRESHOLD
    CHECK_INTERVAL = max(20, _cfg_int(base_env, "YAZKLINIK_HEALTH_CHECK_INTERVAL_SEC", CHECK_INTERVAL))
    RESTART_GRACE = max(25, _cfg_int(base_env, "YAZKLINIK_HEALTH_RESTART_GRACE_SEC", RESTART_GRACE))
    initial_grace_raw = _cfg_int(
        base_env, "YAZKLINIK_HEALTH_INITIAL_GRACE_SEC", INITIAL_GRACE
    )
    # D700 2026-05-27: web import/preflight 2-5 dakika surebilir. Config
    # degeri alt sinirdir; warm restart sirasinda 30s gibi kisa grace'e dusme.
    INITIAL_GRACE = max(300, min(initial_grace_raw, 600))
    MIN_RESTART_INTERVAL = max(120, _cfg_int(base_env, "YAZKLINIK_HEALTH_MIN_RESTART_SEC", MIN_RESTART_INTERVAL))
    FAIL_THRESHOLD = max(3, _cfg_int(base_env, "YAZKLINIK_HEALTH_FAIL_THRESHOLD", FAIL_THRESHOLD))
    CHECK_TIMEOUT = _cfg_float(base_env, "YAZKLINIK_HEALTH_CHECK_TIMEOUT_SEC", CHECK_TIMEOUT)
    WEB_CHECK_TIMEOUT = _cfg_float(base_env, "YAZKLINIK_HEALTH_WEB_CHECK_TIMEOUT_SEC", WEB_CHECK_TIMEOUT)
    WEB_FAIL_THRESHOLD = max(6, _cfg_int(base_env, "YAZKLINIK_HEALTH_WEB_FAIL_THRESHOLD", WEB_FAIL_THRESHOLD))
    web_restart_raw = _cfg_int(
        base_env, "YAZKLINIK_HEALTH_WEB_RESTART_GRACE_SEC", WEB_RESTART_GRACE
    )
    WEB_RESTART_GRACE = max(300, RESTART_GRACE, min(web_restart_raw, 600))
    SIP_ALEX_FAIL_THRESHOLD = max(
        6,
        _cfg_int(base_env, "YAZKLINIK_HEALTH_SIP_FAIL_THRESHOLD", SIP_ALEX_FAIL_THRESHOLD),
    )
    TCP_SOFT_FAIL_THRESHOLD = max(
        8,
        _cfg_int(base_env, "YAZKLINIK_HEALTH_TCP_SOFT_FAIL_THRESHOLD", TCP_SOFT_FAIL_THRESHOLD),
    )
    WEB_ALLOW_TCP_DEGRADED = _cfg_bool(
        base_env, "YAZKLINIK_HEALTH_WEB_ALLOW_TCP_DEGRADED", WEB_ALLOW_TCP_DEGRADED
    )
    harddown_disabled = _cfg_bool(
        base_env,
        "YAZKLINIK_HEALTH_WEB_HARDDOWN_DISABLE",
        False,
    )
    fast_restart_raw = _cfg_bool(
        base_env,
        "YAZKLINIK_HEALTH_WEB_HARDDOWN_FAST_RESTART",
        WEB_HARDDOWN_FAST_RESTART,
    )
    fast_restart_force = _cfg_bool(
        base_env,
        "YAZKLINIK_HEALTH_WEB_HARDDOWN_FAST_RESTART_FORCE",
        False,
    )
    # D700 2026-05-27: Web import/preflight 2-5 dakika surebilir. Eski
    # config'ten kalan harddown=1 tek basina restart firtinasi baslatmasin;
    # hizli kill icin ayri FORCE anahtari gerekir.
    WEB_HARDDOWN_FAST_RESTART = bool(
        fast_restart_raw and fast_restart_force and not harddown_disabled
    )
    WEB_HARDDOWN_FAIL_THRESHOLD = max(
        6,
        _cfg_int(
            base_env,
            "YAZKLINIK_HEALTH_WEB_HARDDOWN_FAIL_THRESHOLD",
            WEB_HARDDOWN_FAIL_THRESHOLD,
        ),
    )
    active_services = _active_services(base_env)
    print(f"[{_ts()}] D700 Health Monitor basladi. "
          f"Check interval: {CHECK_INTERVAL}s, services: "
          f"{', '.join(s[0] for s in active_services)}",
          flush=True)
    web_primary_env = str(base_env.get("YAZKLINIK_HEALTH_WEB_URL", "") or "").strip()
    web_fallback_env = str(base_env.get("YAZKLINIK_HEALTH_WEB_FALLBACK_URL", "") or "").strip()
    managed_owner_raw = str(
        base_env.get(
            "YAZKLINIK_HEALTH_WEB_ENFORCE_MANAGED_OWNER",
            "1" if WEB_ENFORCE_MANAGED_OWNER else "0",
        )
        or ""
    ).strip().lower()
    managed_owner_force_raw = str(
        base_env.get("YAZKLINIK_HEALTH_WEB_ENFORCE_MANAGED_OWNER_FORCE", "")
        or ""
    ).strip().lower()
    web_enforce_managed_owner = False
    if managed_owner_force_raw in {"force-off-managed-owner", "managed-owner-force-off"}:
        web_enforce_managed_owner = False
    web_primary_log = _normalize_web_health_url(
        web_primary_env or "http://127.0.0.1:5052/api/terminal/ping-fast",
        "http://127.0.0.1:5052/api/terminal/ping-fast",
    )
    web_fallback_log = _normalize_web_health_url(
        web_fallback_env or "https://127.0.0.1:5443/api/terminal/ping-fast",
        "https://127.0.0.1:5443/api/terminal/ping-fast",
    )
    print(
        f"[{_ts()}] Web health hedefleri: primary={web_primary_log}, fallback={web_fallback_log}, managed-owner={'on' if web_enforce_managed_owner else 'off'}",
        flush=True,
    )
    print(
        f"[{_ts()}] Web fail ayari: threshold={WEB_FAIL_THRESHOLD}, harddown-fast={'on' if WEB_HARDDOWN_FAST_RESTART else 'off'} (fail={WEB_HARDDOWN_FAIL_THRESHOLD}), restart-grace={WEB_RESTART_GRACE}s",
        flush=True,
    )
    print(
        f"[{_ts()}] Config kaynak: {CONFIG_ENV} | managed_owner_raw={managed_owner_raw} | managed_owner_force_raw={managed_owner_force_raw} | harddown_fast_raw={str(base_env.get('YAZKLINIK_HEALTH_WEB_HARDDOWN_FAST_RESTART', '')).strip()} | harddown_disable_raw={str(base_env.get('YAZKLINIK_HEALTH_WEB_HARDDOWN_DISABLE', '')).strip()} | initial_grace_raw={initial_grace_raw}",
        flush=True,
    )
    runtime_initial_grace = _monitor_warm_restart_grace(INITIAL_GRACE)
    if runtime_initial_grace > 0:
        print(f"[{_ts()}] Ilk acilis bekleme: {runtime_initial_grace}s", flush=True)
        _interruptible_initial_grace(runtime_initial_grace, active_services)
    last_restart = {}  # name -> ts (anti-spam)
    fail_counts = {s[0]: 0 for s in active_services}
    next_check_at = {s[0]: 0.0 for s in active_services}
    cooldown_notice_at = {s[0]: 0.0 for s in active_services}

    while True:
        try:
            for name, url, script, log, errlog, ov in active_services:
                now = time.time()
                if now < float(next_check_at.get(name, 0.0) or 0.0):
                    continue
                if name == "web":
                    primary_default = "http://127.0.0.1:5052/api/terminal/ping-fast"
                    fallback_default = "https://127.0.0.1:5443/api/terminal/ping-fast"
                    primary_seed = web_primary_env or url
                    fallback_seed = web_fallback_env or WEB_FALLBACK_URL
                    web_urls = [_normalize_web_health_url(primary_seed, primary_default)]
                    if fallback_seed:
                        web_urls.append(_normalize_web_health_url(fallback_seed, fallback_default))
                    if web_enforce_managed_owner:
                        for one_url in web_urls:
                            unmanaged, owner_pid, owner_cmd = _web_owner_is_unmanaged(one_url)
                            if unmanaged:
                                print(
                                    f"[{_ts()}] web unmanaged PID {owner_pid} kapatiliyor: "
                                    f"{owner_cmd[:180]}",
                                    flush=True,
                                )
                                if not _stop_process_tree(owner_pid):
                                    print(
                                        f"[{_ts()}] web unmanaged PID {owner_pid} normal yetkiyle "
                                        "kapatilamadi; D700_ADMIN_WEB_RESTART.bat gerekli",
                                        flush=True,
                                    )
                                time.sleep(2)
                    healthy, reason = _check_many(web_urls, timeout=max(1.0, float(WEB_CHECK_TIMEOUT)))
                else:
                    healthy, reason = _check(url)
                web_hard_down = False
                if name == "web" and not healthy:
                    try:
                        # D700 2026-05-27: Hard-down kararinda fallback 5443
                        # (Caddy) owner'ini "web owner" sayma.
                        # Aksi halde 5052 kapaliyken bile Caddy acik oldugu icin
                        # fail threshold hep 6'da kaliyor ve restart gecikiyor.
                        primary_url = web_urls[0] if web_urls else ""
                        primary_port = _url_port(primary_url)
                        primary_owner_pid = (
                            _port_owner_pid(primary_port) if primary_port else 0
                        )
                        primary_owner_cmd = (
                            _process_command_line(primary_owner_pid).lower()
                            if primary_owner_pid else ""
                        )
                        primary_owner_is_web = (
                            bool(primary_owner_pid)
                            and "yazklinik_web.py" in primary_owner_cmd
                        )
                        booting_web_process = _project_web_process_active()
                        reason_text = str(reason or "")
                        hard_reason = (
                            ("down:" in reason_text)
                            or ("http_502" in reason_text)
                        )
                        # D700 boot can take several minutes before 5052 listens.
                        # A live web process in that window must not be treated as
                        # hard-down, otherwise the monitor restarts it forever.
                        web_hard_down = (
                            hard_reason
                            and (not primary_owner_is_web)
                            and (not booting_web_process)
                        )
                    except Exception:
                        web_hard_down = False
                if (
                    name == "web"
                    and not healthy
                    and WEB_ALLOW_TCP_DEGRADED
                    and "tcp_ok_http_fail" in str(reason or "")
                ):
                    print(
                        f"[{_ts()}] web degraded (tcp acik, http gecikiyor) restart atlandi: {reason}",
                        flush=True,
                    )
                    fail_counts[name] = 0
                    continue
                if healthy:
                    if fail_counts[name] > 0:
                        print(f"[{_ts()}] {name} recovered after {fail_counts[name]} fail(s) ({reason})", flush=True)
                    fail_counts[name] = 0
                    continue
                threshold = _fail_threshold_for(name, reason)
                if name == "web" and not _project_web_process_active():
                    # Web process tamamen yoksa 6 fail (~3dk) bekleme;
                    # daha hizli toparlama icin threshold'u dusur.
                    threshold = min(threshold, 2)
                if (
                    name == "web"
                    and not healthy
                    and "down:ConnectionRefusedError" in str(reason or "")
                    and "http_502" in str(reason or "")
                ):
                    # 5052 kapali + 5443 proxy 502 ise servis fiilen yoktur.
                    threshold = min(threshold, 2)
                if name == "web" and web_hard_down and WEB_HARDDOWN_FAST_RESTART:
                    # Opsiyonel hizli toparlama: normalde web için agir fail threshold
                    # korunur; sadece explicitly acildiginda hard-down hizli restart eder.
                    threshold = min(threshold, int(WEB_HARDDOWN_FAIL_THRESHOLD))
                fail_counts[name] += 1
                print(f"[{_ts()}] {name} check fail {fail_counts[name]}/{threshold} ({reason})", flush=True)
                # D700 2026-05-18: N consecutive fail sart, ariza zar gecisle gecsin.
                if fail_counts[name] < threshold:
                    continue
                # Anti-spam: ayni servis kisa araliklarla restart edilmesin.
                min_restart = _service_min_restart_interval(name)
                if name in last_restart and now - last_restart[name] < min_restart:
                    if now - float(cooldown_notice_at.get(name, 0.0) or 0.0) >= 60.0:
                        wait_left = int(max(1, min_restart - (now - last_restart[name])))
                        print(
                            f"[{_ts()}] {name} restart cooldown aktif, {wait_left}s kaldi",
                            flush=True,
                        )
                        cooldown_notice_at[name] = now
                    continue
                last_restart[name] = now
                cooldown_notice_at[name] = 0.0
                fail_counts[name] = 0
                pid = _restart(name, script, log, errlog, ov, base_env)
                if pid:
                    print(f"[{_ts()}] {name} restart OK (PID {pid})", flush=True)
                    grace = WEB_RESTART_GRACE if name == "web" else RESTART_GRACE
                    next_check_at[name] = time.time() + max(1, int(grace))
            time.sleep(CHECK_INTERVAL)
        except Exception as loop_ex:
            print(
                f"[{_ts()}] monitor loop exception: {type(loop_ex).__name__}: {loop_ex}",
                flush=True,
            )
            time.sleep(5)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"[{_ts()}] Monitor durduruldu (Ctrl+C)")
    finally:
        try:
            if MONITOR_LOCK.exists():
                owner_pid = int(
                    MONITOR_LOCK.read_text(encoding="ascii", errors="ignore").strip() or "0"
                )
                if owner_pid == os.getpid():
                    MONITOR_LOCK.unlink()
        except Exception:
            pass

