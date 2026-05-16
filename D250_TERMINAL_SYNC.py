#!/usr/bin/env python3
"""Sync YazKlinik D250 web settings to Windows/macOS terminal launchers."""

from __future__ import annotations

import argparse
import json
import os
import re
import ssl
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TOKEN = os.environ.get("YAZKLINIK_TERMINAL_TOKEN", "")


def read_config() -> dict[str, str]:
    cfg: dict[str, str] = {}
    path = ROOT / "config.env"
    if not path.exists():
        return cfg
    for raw in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        cfg[key.strip()] = value.strip()
    return cfg


def normalize_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return ""
    if not value.startswith(("http://", "https://")):
        value = "http://" + value
    return value


def looks_windows_path(value: str) -> bool:
    return bool(re.match(r"^[A-Za-z]:\\", value or "")) or str(value or "").startswith("\\\\")


def value_for_path(cfg: dict[str, str], key: str, relative_default: str) -> str:
    value = os.environ.get(key) or cfg.get(key) or ""
    if sys.platform != "win32" and looks_windows_path(value):
        value = ""
    return value or str(ROOT / relative_default)


def state_root(cfg: dict[str, str] | None = None) -> Path:
    cfg = cfg or {}
    value = os.environ.get("YAZKLINIK_STATE_ROOT") or cfg.get("YAZKLINIK_STATE_ROOT") or ""
    if sys.platform != "win32" and looks_windows_path(value):
        value = ""
    return Path(value).expanduser() if value else ROOT / "runtime_state"


def shell_quote(value: str) -> str:
    return "'" + str(value).replace("'", "'\"'\"'") + "'"


def ps_quote(value: str) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def build_env(cfg: dict[str, str], server_url: str, port: str) -> dict[str, str]:
    def cfg_env(key: str, default: str) -> str:
        return cfg.get(key) or os.environ.get(key) or default

    desktop_mode = (
        cfg.get("YAZKLINIK_DESKTOP_MODE")
        or os.environ.get("YAZKLINIK_DESKTOP_MODE")
        or "hybrid"
    ).strip().lower()
    if desktop_mode not in {"shell", "mirror", "hybrid"}:
        desktop_mode = "shell"
    web_mirror = "1" if desktop_mode == "mirror" else "0"
    env = {
        "YAZKLINIK_WEB_PORT": port,
        "YAZKLINIK_SERVER_URL": server_url,
        "YAZKLINIK_WEB_URL": server_url,
        "YAZKLINIK_AI_SERVER_URL": server_url,
        "YAZKLINIK_DEFAULT_SERVER_URL": server_url,
        "YAZKLINIK_ALLOW_LOCAL_TERMINAL_SERVER": "1",
        "YAZKLINIK_DESKTOP_MODE": desktop_mode,
        "YAZKLINIK_DESKTOP_MODE_FORCE": "1",
        "YAZKLINIK_DESKTOP_WEB_SHELL": "1",
        "YAZKLINIK_DESKTOP_ENABLE_WEBENGINE": "1",
        "YAZKLINIK_DESKTOP_DISABLE_WEBENGINE": "0",
        "YAZKLINIK_DESKTOP_WEB_MIRROR": web_mirror,
        "YAZKLINIK_DESKTOP_WEB_CENTER_FIRST": "1",
        "YAZKLINIK_DESKTOP_LEAN_SHELL": os.environ.get("YAZKLINIK_DESKTOP_LEAN_SHELL")
        or cfg.get("YAZKLINIK_DESKTOP_LEAN_SHELL")
        or "1",
        "YAZKLINIK_TERMINAL_TOKEN": os.environ.get("YAZKLINIK_TERMINAL_TOKEN")
        or cfg.get("YAZKLINIK_TERMINAL_TOKEN")
        or TOKEN,
        "YAZKLINIK_NAS_ROOT": os.environ.get("YAZKLINIK_NAS_ROOT")
        or cfg.get("YAZKLINIK_NAS_ROOT")
        or ("\\\\asustor\\Voluson" if sys.platform == "win32" else str(ROOT / "Hastalar")),
        "YAZKLINIK_DATA_ROOT": value_for_path(cfg, "YAZKLINIK_DATA_ROOT", "data"),
        "YAZKLINIK_DB_PATH": value_for_path(cfg, "YAZKLINIK_DB_PATH", "local_db/yazklinik_v68.sqlite3"),
        "YAZKLINIK_MULTIMEDIA_ROOT": value_for_path(cfg, "YAZKLINIK_MULTIMEDIA_ROOT", "local_multimedia"),
        "YAZKLINIK_TEMP_DIR": value_for_path(cfg, "YAZKLINIK_TEMP_DIR", "temp"),
        "YAZKLINIK_EXPORT_ROOT": value_for_path(cfg, "YAZKLINIK_EXPORT_ROOT", "exports"),
        "YAZKLINIK_VOICE_RECORDS_DIR": value_for_path(cfg, "YAZKLINIK_VOICE_RECORDS_DIR", "voice_records"),
        "YAZKLINIK_DICOM_CACHE_DIR": value_for_path(cfg, "YAZKLINIK_DICOM_CACHE_DIR", "dicom_cache"),
        "YAZKLINIK_BACKUP_ROOT": value_for_path(cfg, "YAZKLINIK_BACKUP_ROOT", "auto_backups"),
        "YAZKLINIK_STATE_ROOT": str(state_root(cfg)),
        "YAZKLINIK_WRITE_LOCALAPPDATA_STATE": cfg_env("YAZKLINIK_WRITE_LOCALAPPDATA_STATE", "0"),
        "YAZKLINIK_WEBSHELL_ENGINE": cfg_env("YAZKLINIK_WEBSHELL_ENGINE", "browser"),
        "YAZKLINIK_WEBSHELL_CACHE_MB": cfg_env("YAZKLINIK_WEBSHELL_CACHE_MB", "512"),
        "YAZKLINIK_WEBSHELL_WINDOWS_ACCELERATOR": cfg_env("YAZKLINIK_WEBSHELL_WINDOWS_ACCELERATOR", "1"),
        "YAZKLINIK_WEBSHELL_PRIORITY": cfg_env("YAZKLINIK_WEBSHELL_PRIORITY", "above"),
        "YAZKLINIK_WEBSHELL_KEEP_BACKGROUND_ACTIVE": cfg_env("YAZKLINIK_WEBSHELL_KEEP_BACKGROUND_ACTIVE", "1"),
        "YAZKLINIK_WEBSHELL_GPU_TURBO": cfg_env("YAZKLINIK_WEBSHELL_GPU_TURBO", "1"),
        "YAZKLINIK_WEBSHELL_SAFE_MODE": cfg_env("YAZKLINIK_WEBSHELL_SAFE_MODE", "0"),
        "YAZKLINIK_WEBSHELL_ROUTE_PREWARM": cfg_env("YAZKLINIK_WEBSHELL_ROUTE_PREWARM", "0"),
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUNBUFFERED": "1",
    }
    return env


def write_sync_files(env: dict[str, str], server_url: str) -> list[str]:
    written: list[str] = []
    for path in [ROOT / "terminal_server_url.txt", ROOT / "server_actual_url.txt"]:
        write_text(path, server_url + "\n")
        written.append(str(path))

    home_base = state_root(env)
    for path in [home_base / "terminal_server_url.txt", home_base / "server_actual_url.txt"]:
        write_text(path, server_url + "\n")
        written.append(str(path))

    desktop_mode = (env.get("YAZKLINIK_DESKTOP_MODE") or "shell").strip().lower() or "shell"
    for path in [ROOT / "desktop_mode.txt", home_base / "desktop_mode.txt"]:
        write_text(path, desktop_mode + "\n")
        written.append(str(path))

    local_app = os.environ.get("LOCALAPPDATA")
    if local_app and env.get("YAZKLINIK_WRITE_LOCALAPPDATA_STATE") == "1":
        base = Path(local_app) / "YazKlinik"
        for path in [
            base / "terminal_server_url.txt",
            base / "server_actual_url.txt",
            base / "Server" / "terminal_server_url.txt",
        ]:
            write_text(path, server_url + "\n")
            written.append(str(path))
        for path in [base / "desktop_mode.txt", base / "Server" / "desktop_mode.txt"]:
            write_text(path, desktop_mode + "\n")
            written.append(str(path))

    ps_lines = [f"$env:{key} = {ps_quote(value)}" for key, value in sorted(env.items())]
    write_text(ROOT / "terminal_env.ps1", "\n".join(ps_lines) + "\n")
    written.append(str(ROOT / "terminal_env.ps1"))

    sh_lines = [f"export {key}={shell_quote(value)}" for key, value in sorted(env.items())]
    sh = "\n".join(sh_lines) + "\n"
    write_text(ROOT / "terminal_env.sh", sh)
    write_text(home_base / "full_server.env", sh)
    written.extend([str(ROOT / "terminal_env.sh"), str(home_base / "full_server.env")])

    status = {
        "ok": True,
        "server_url": server_url,
        "root": str(ROOT),
        "platform": sys.platform,
        "env": env,
    }
    write_text(ROOT / "terminal_sync_status.json", json.dumps(status, ensure_ascii=False, indent=2) + "\n")
    written.append(str(ROOT / "terminal_sync_status.json"))
    return written


def ping(server_url: str, token: str) -> tuple[bool, str]:
    try:
        req = urllib.request.Request(
            server_url.rstrip("/") + "/api/terminal/ping",
            headers={"X-Terminal-Token": token, "Accept": "application/json"},
        )
        kwargs = {}
        if server_url.lower().startswith("https://"):
            kwargs["context"] = ssl._create_unverified_context()
        with urllib.request.urlopen(req, timeout=4, **kwargs) as resp:
            return 200 <= resp.status < 300, f"HTTP {resp.status}"
    except Exception as ex:
        return False, str(ex)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-url", default="")
    parser.add_argument("--port", default="")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    cfg = read_config()
    port = str(args.port or os.environ.get("YAZKLINIK_WEB_PORT") or cfg.get("YAZKLINIK_WEB_PORT") or "5443").strip()
    server_url = normalize_url(args.server_url) or f"http://127.0.0.1:{port}"
    env = build_env(cfg, server_url, port)
    written = write_sync_files(env, server_url)

    print(f"TERMINAL_SYNC_OK {server_url}")
    for path in written:
        print(path)
    if args.check:
        ok, detail = ping(server_url, env["YAZKLINIK_TERMINAL_TOKEN"])
        print(f"TERMINAL_PING_{'OK' if ok else 'FAIL'} {detail}")
        return 0 if ok else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
