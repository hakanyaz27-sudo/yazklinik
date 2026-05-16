#!/usr/bin/env python3
"""Offline SQLite repair helper for YazKlinik.

This tool is intentionally independent from Flask startup. It can run when the
web app cannot open because the main SQLite database is locked.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path


DEFAULT_DB = r"\\Sam\usg\DATABASE\yazklinik_v68.sqlite3"
RUNTIME_TOKENS = (
    "yazklinik_web.py",
    "YazKlinik_FINAL3000_Baslat.bat",
    "YazKlinik_Server_Baslat.bat",
    "YazKlinik_Hibrit_Baslat.bat",
    "WebShell\\main.py",
    "WebShell/main.py",
    "/api/terminal/ping",
)


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def log(message: str) -> None:
    print(f"[DB-ONAR] {message}", flush=True)


def read_env_bat(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line.lower().startswith("set "):
            continue
        raw = line[4:].strip()
        if raw.startswith('"') and raw.endswith('"'):
            raw = raw[1:-1]
        if "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def resolve_db_path(root: Path, explicit: str = "") -> Path:
    if explicit:
        return Path(explicit)
    env_db = os.environ.get("YAZKLINIK_DB_PATH", "").strip()
    if env_db:
        return Path(env_db)
    cfg_path = root / "yazklinik_config.json"
    if cfg_path.exists():
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
            if cfg.get("db_path"):
                return Path(str(cfg["db_path"]))
        except Exception:
            pass
    env_file = read_env_bat(root / "yazklinik.env.bat")
    if env_file.get("YAZKLINIK_DB_PATH"):
        return Path(env_file["YAZKLINIK_DB_PATH"])
    return Path(DEFAULT_DB)


def stop_yazklinik_processes(root: Path) -> None:
    ps_tokens = "@(" + ",".join(repr(t) for t in RUNTIME_TOKENS) + ")"
    script = rf"""
$tokens = {ps_tokens}
$self = $PID
$root = '{str(root).replace("'", "''")}'
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | ForEach-Object {{
  $cmd = [string]$_.CommandLine
  if ([string]::IsNullOrWhiteSpace($cmd)) {{ return }}
  if ($_.ProcessId -eq $self) {{ return }}
  if ($cmd -like '*yazklinik_db_onar.py*' -or $cmd -like '*YazKlinik-DB-Onar*') {{ return }}
  $hit = $false
  foreach ($token in $tokens) {{
    if ($cmd.IndexOf($token, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {{
      $hit = $true
      break
    }}
  }}
  if (-not $hit -and $root) {{
    $inRoot = $cmd.IndexOf($root, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    $isRuntime = ($_.Name -like 'python*' -or $_.Name -like 'pythonw*')
    $hit = $inRoot -and $isRuntime
  }}
  if ($hit) {{
    try {{
      Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop
      Write-Output ('stopped ' + $_.Name + ' ' + $_.ProcessId)
    }} catch {{
      Write-Output ('could not stop ' + $_.Name + ' ' + $_.ProcessId + ': ' + $_.Exception.Message)
    }}
  }}
}}
"""
    log("YazKlinik server/kabuk surecleri kapatiliyor...")
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            text=True,
            capture_output=True,
            timeout=35,
        )
        for line in (out.stdout or "").splitlines():
            log(line)
        if out.stderr.strip():
            log(out.stderr.strip())
    except Exception as exc:
        log(f"Surec kapatma uyarisi: {exc}")
    time.sleep(2.0)


def sidecars(db_path: Path) -> list[Path]:
    return [db_path.with_name(db_path.name + suffix) for suffix in ("-wal", "-shm", "-journal")]


def backup_files(db_path: Path) -> Path:
    backup_dir = db_path.parent / "auto_backups" / ("db_onar_" + now_stamp())
    backup_dir.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        shutil.copy2(str(db_path), str(backup_dir / db_path.name))
    for item in sidecars(db_path):
        if item.exists():
            try:
                shutil.copy2(str(item), str(backup_dir / item.name))
            except Exception as exc:
                log(f"Sidecar yedek uyarisi {item.name}: {exc}")
    return backup_dir


def write_json_config_db_path(root: Path, db_path: Path) -> None:
    cfg_path = root / "yazklinik_config.json"
    if not cfg_path.exists():
        return
    try:
        cfg = json.loads(cfg_path.read_text(encoding="utf-8-sig"))
        cfg["db_path"] = str(db_path)
        cfg["db_root"] = str(db_path.parent)
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=4) + "\n", encoding="utf-8")
    except Exception as exc:
        log(f"Config DB yolu guncellenemedi ({cfg_path}): {exc}")


def update_env_bat_values(path: Path, updates: dict[str, str]) -> None:
    if not path.exists():
        return
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        seen: set[str] = set()
        new_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            replacement = None
            if stripped.lower().startswith("set "):
                raw = stripped[4:].strip()
                if raw.startswith('"') and raw.endswith('"'):
                    raw = raw[1:-1]
                if "=" in raw:
                    key = raw.split("=", 1)[0].strip()
                    if key in updates:
                        replacement = f'set "{key}={updates[key]}"'
                        seen.add(key)
            new_lines.append(replacement if replacement is not None else line)
        for key, value in updates.items():
            if key not in seen:
                new_lines.append(f'set "{key}={value}"')
        path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    except Exception as exc:
        log(f"ENV DB yolu guncellenemedi ({path}): {exc}")


def persist_db_path(root: Path, db_path: Path) -> None:
    os.environ["YAZKLINIK_DB_PATH"] = str(db_path)
    os.environ["YAZKLINIK_DB_ROOT"] = str(db_path.parent)
    write_json_config_db_path(root, db_path)
    update_env_bat_values(
        root / "yazklinik.env.bat",
        {
            "YAZKLINIK_DB_ROOT": str(db_path.parent),
            "YAZKLINIK_DB_PATH": str(db_path),
        },
    )


def clone_locked_database(db_path: Path) -> tuple[Path, dict[str, object]]:
    wal_path = db_path.with_name(db_path.name + "-wal")
    if wal_path.exists():
        wal_size = wal_path.stat().st_size
        if wal_size > 0:
            raise RuntimeError(
                f"{wal_path.name} dolu ({wal_size} bayt). Veri kaybi riski nedeniyle kopya DB'ye gecilmedi."
            )
    clone_path = db_path.with_name(f"{db_path.stem}_A113_ONARILMIS_{now_stamp()}{db_path.suffix}")
    shutil.copy2(str(db_path), str(clone_path))
    for item in sidecars(clone_path):
        if item.exists():
            try:
                item.unlink()
            except Exception:
                pass
    check = connect_and_check(clone_path, allow_sidecar_cleanup=True)
    if str(check.get("quick_check", "")).lower() != "ok":
        raise RuntimeError("A113 kopya SQLite quick_check OK degil: " + str(check.get("quick_check")))
    return clone_path, check


def connect_and_check(db_path: Path, allow_sidecar_cleanup: bool) -> dict[str, object]:
    result: dict[str, object] = {}
    try:
        con = sqlite3.connect(str(db_path), timeout=12)
        try:
            con.execute("PRAGMA busy_timeout=12000")
            try:
                result["journal_mode_before"] = (con.execute("PRAGMA journal_mode").fetchone() or ["?"])[0]
            except Exception:
                pass
            try:
                result["wal_checkpoint"] = con.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            except Exception as exc:
                result["wal_checkpoint_error"] = str(exc)
            result["quick_check"] = (con.execute("PRAGMA quick_check").fetchone() or ["?"])[0]
            try:
                result["integrity_check"] = (con.execute("PRAGMA integrity_check").fetchone() or ["?"])[0]
            except Exception as exc:
                result["integrity_check_error"] = str(exc)
            try:
                con.execute("PRAGMA optimize")
            except Exception:
                pass
            con.commit()
        finally:
            con.close()
        return result
    except sqlite3.OperationalError as exc:
        msg = str(exc).lower()
        result["first_error"] = str(exc)
        if "locked" not in msg or not allow_sidecar_cleanup:
            raise
        log("DB kilidi devam ediyor; eski WAL/SHM yan dosyalari temizleniyor.")
        for item in sidecars(db_path):
            if not item.exists():
                continue
            try:
                if item.name.endswith("-wal") and item.stat().st_size > 0:
                    log(f"{item.name} dolu oldugu icin silinmedi ({item.stat().st_size} bayt).")
                    continue
                item.unlink()
                log(f"Silindi: {item}")
            except Exception as cleanup_exc:
                log(f"Silinemedi {item}: {cleanup_exc}")
        retry = connect_and_check(db_path, allow_sidecar_cleanup=False)
        retry["first_error"] = result.get("first_error")
        retry["sidecars_cleaned"] = True
        return retry


def run_schema_repair(root: Path, db_path: Path) -> dict[str, object]:
    os.environ["YAZKLINIK_DB_PATH"] = str(db_path)
    os.environ.setdefault("YAZKLINIK_SMART_ASSISTANT_QUIET", "1")
    sys.path.insert(0, str(root))
    try:
        import yazklinik_v68 as core  # type: ignore
        core.DB_PATH = db_path
        core._DB_INITIALISED = False
        info = core.ensure_database_ready(recreate=True)
        health = core.database_health_check(fast=True)
        return {"schema": info, "health": health}
    except Exception as exc:
        return {"schema_error": str(exc)}


def wait_http(url: str, seconds: int = 90) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=4) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False


def restart_server(root: Path, port: str) -> bool:
    launcher = root / "YazKlinik_FINAL3000_Baslat.bat"
    if not launcher.exists():
        launcher = root / "YazKlinik_Server_Baslat.bat"
    if not launcher.exists():
        log("Server baslatici bulunamadi; elle baslatin.")
        return False
    log(f"Server yeniden baslatiliyor: {launcher}")
    subprocess.Popen(
        ["cmd", "/c", "start", "YazKlinik Final A113", str(launcher)],
        cwd=str(root),
        shell=False,
    )
    ok = wait_http(f"http://127.0.0.1:{port}/api/terminal/ping?deep=1", seconds=120)
    log("Server ping OK." if ok else "Server ping suresi doldu; baslatma penceresini kontrol edin.")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default="")
    parser.add_argument("--root", default="")
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--port", default="")
    parser.add_argument("--no-stop", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve() if args.root else Path(__file__).resolve().parent
    db_path = resolve_db_path(root, args.db)
    port = args.port or os.environ.get("YAZKLINIK_WEB_PORT", "5052")
    report_path = root / ("DB_ONAR_RAPORU_" + now_stamp() + ".txt")

    lines: list[str] = []

    def record(message: str) -> None:
        lines.append(message)
        log(message)

    try:
        record(f"Root: {root}")
        record(f"DB: {db_path}")
        if not args.no_stop:
            stop_yazklinik_processes(root)
        if not db_path.exists():
            raise FileNotFoundError(f"DB bulunamadi: {db_path}")
        backup_dir = backup_files(db_path)
        record(f"Yedek klasoru: {backup_dir}")
        try:
            check = connect_and_check(db_path, allow_sidecar_cleanup=True)
        except sqlite3.OperationalError as locked_exc:
            if "locked" not in str(locked_exc).lower():
                raise
            record("Ana DB kilidi acilamadi; sifir boyutlu WAL icin A113 temiz kopya yolu deneniyor.")
            clone_path, check = clone_locked_database(db_path)
            db_path = clone_path
            persist_db_path(root, db_path)
            record(f"A113 onarilmis DB kopyasi aktif edildi: {db_path}")
        record("SQLite quick_check: " + str(check.get("quick_check")))
        record("SQLite integrity_check: " + str(check.get("integrity_check", check.get("integrity_check_error", "?"))))
        schema = run_schema_repair(root, db_path)
        record("Schema/health: " + json.dumps(schema, ensure_ascii=False, default=str)[:4000])
        if str(check.get("quick_check", "")).lower() != "ok":
            raise RuntimeError("SQLite quick_check OK degil: " + str(check.get("quick_check")))
        if args.restart:
            restart_ok = restart_server(root, str(port or "5052"))
            record("Restart ping: " + ("OK" if restart_ok else "TIMEOUT"))
        record("DB_ONAR_OK")
        return 0
    except Exception as exc:
        record("DB_ONAR_HATA: " + str(exc))
        return 1
    finally:
        try:
            report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
            log(f"Rapor: {report_path}")
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())

