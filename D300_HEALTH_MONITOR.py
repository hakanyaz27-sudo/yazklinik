r"""YazKlinik D300 Health Monitor.

Her 30 saniyede bir servis sağlığını kontrol eder; düşen servisi otomatik restart eder.
Aktif kontrol edilen servisler:
  - Web 5443 (yazklinik_web.py)
  - Whisper 9000 (yazklinik_whisper_service.py)
  - XTTS 9002 (yazklinik_xtts_service.py)
  - Piper 9001 (yazklinik_piper_service.py)

Calistirma:
  Set-Location D:\YazKlinik_Final_D300
  & "D:\YazKlinik_Final_D300\.venv\Scripts\python.exe" D300_HEALTH_MONITOR.py

Veya arka planda:
  Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "D300_HEALTH_MONITOR.py" -WindowStyle Hidden
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
VENV_PY = os.path.join(HERE, ".venv", "Scripts", "python.exe")
CONFIG_ENV = os.path.join(HERE, "config.env")

# Servis tanimlari: name -> (url, script, log, error_log, env_overrides)
SERVICES = [
    ("web", "https://127.0.0.1:5443/giris",
     "yazklinik_web.py", "D300_server.log", "D300_server_HATA.log", {}),
    ("whisper", "http://127.0.0.1:9000/health",
     "yazklinik_whisper_service.py", "D300_whisper_service.log",
     "D300_whisper_service_err.log",
     {"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}),
    ("xtts", "http://127.0.0.1:9002/health",
     "yazklinik_xtts_service.py", "D300_xtts_service.log",
     "D300_xtts_service_err.log",
     {"COQUI_TOS_AGREED": "1"}),
    ("piper", "http://127.0.0.1:9001/health",
     "yazklinik_piper_service.py", "D300_piper_service.log",
     "D300_piper_service_err.log", {}),
]

CHECK_INTERVAL = 30  # saniye
RESTART_GRACE = 15  # restart sonrasi tekrar check etmeden bekleme
INITIAL_GRACE = int(os.environ.get("YAZKLINIK_HEALTH_INITIAL_GRACE_SEC", "120"))


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
    try:
        with open(CONFIG_ENV, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    except Exception:
        pass
    return env


def _check(url: str, timeout: float = 3.0) -> bool:
    """HTTP check - 200/302 OK."""
    try:
        import ssl
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "D300-Health/1.0"})
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status in (200, 302)
    except Exception:
        return False


def _restart(name: str, script: str, log: str, errlog: str,
             env_overrides: dict, base_env: dict) -> int:
    """Servisi yeniden baslat. PID doner."""
    print(f"[{_ts()}] RESTART {name}: {script}", flush=True)
    env = base_env.copy()
    env.update(env_overrides)
    out_path = os.path.join(HERE, log)
    err_path = os.path.join(HERE, errlog)
    try:
        stdout = _open_restart_log(out_path)
        stderr = _open_restart_log(err_path)
        flags = (
            subprocess.CREATE_NO_WINDOW
            | getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
            | getattr(subprocess, "HIGH_PRIORITY_CLASS", 0x00000080)
        )
        proc = subprocess.Popen(
            [VENV_PY, "-u", script],
            cwd=HERE,
            env=env,
            stdout=stdout,
            stderr=stderr,
            creationflags=flags,
            close_fds=True,
        )
        return proc.pid
    except Exception as exc:
        print(f"[{_ts()}] RESTART HATA {name}: {exc}", flush=True)
        return 0


def main():
    print(f"[{_ts()}] D300 Health Monitor basladi. "
          f"Check interval: {CHECK_INTERVAL}s, services: "
          f"{', '.join(s[0] for s in SERVICES)}",
          flush=True)
    base_env = _load_config_env()
    if INITIAL_GRACE > 0:
        print(f"[{_ts()}] Ilk acilis bekleme: {INITIAL_GRACE}s", flush=True)
        time.sleep(INITIAL_GRACE)
    last_restart = {}  # name -> ts (anti-spam)

    while True:
        for name, url, script, log, errlog, ov in SERVICES:
            healthy = _check(url, timeout=3.0)
            if healthy:
                continue
            # Anti-spam: ayni servis 60sn icinde 2 kez restart edilmesin
            now = time.time()
            if name in last_restart and now - last_restart[name] < 60:
                continue
            last_restart[name] = now
            pid = _restart(name, script, log, errlog, ov, base_env)
            if pid:
                print(f"[{_ts()}] {name} restart OK (PID {pid})", flush=True)
                time.sleep(RESTART_GRACE)  # model load suresi
        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"[{_ts()}] Monitor durduruldu (Ctrl+C)")
