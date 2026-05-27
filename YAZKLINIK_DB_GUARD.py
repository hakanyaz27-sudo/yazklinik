#!/usr/bin/env python
"""YazKlinik database guard.

Tek komutla:
- SQLite butunluk ve yedek dogrulama
- PostgreSQL container/health kontrolu
- SQLite -> PostgreSQL sayi karsilastirmasi
- Gerekiyorsa PG container baslatma ve mirror tablolarini yeniden senkronlama

Kullanim:
  python YAZKLINIK_DB_GUARD.py
  python YAZKLINIK_DB_GUARD.py --repair
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent
CONFIG_ENV = ROOT / "config.env"
AKILLILIK_ENV = ROOT / "akillilik" / ".env"
AKILLILIK_COMPOSE = ROOT / "akillilik" / "docker-compose.yml"
RUNTIME_DIR = ROOT / "runtime_state" / "db_guard"
REPORT_JSON = RUNTIME_DIR / "last_report.json"
REPORT_TXT = RUNTIME_DIR / "last_report.txt"
DEFAULT_TABLES = ["patients", "visits"]


def _reexec_with_project_venv() -> None:
    """Global Python ile cagrilsa bile D700 .venv icinden calis."""
    if os.environ.get("YAZKLINIK_DB_GUARD_NO_REEXEC") == "1":
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
    os.environ["YAZKLINIK_DB_GUARD_NO_REEXEC"] = "1"
    os.execv(str(target), [str(target), str(Path(__file__).resolve()), *sys.argv[1:]])


def _load_env_file(path: Path, override: bool = False) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        data[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    return data


def _env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key, "1" if default else "0").strip().lower()
    return raw in ("1", "true", "yes", "y", "on")


def _redact_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        if not parts.password:
            return url
        host = parts.hostname or ""
        netloc = host
        if parts.username:
            netloc = f"{parts.username}:***@{host}"
        if parts.port:
            netloc += f":{parts.port}"
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        return "***"


def _check(name: str, status: str, detail: str = "", **extra: Any) -> Dict[str, Any]:
    row = {"name": name, "status": status, "detail": detail}
    row.update(extra)
    return row


def _sqlite_counts(con: sqlite3.Connection, tables: List[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for table in tables:
        try:
            out[table] = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        except Exception as exc:
            out[table] = f"ERROR: {exc}"
    return out


def _verify_sqlite_backup(path: Path) -> str:
    con = sqlite3.connect(str(path), timeout=5)
    try:
        return (con.execute("PRAGMA integrity_check").fetchone() or ["?"])[0]
    finally:
        con.close()


def _prune_guard_backups(backup_dir: Path, keep: int) -> None:
    if keep <= 0 or not backup_dir.exists():
        return
    files = sorted(
        backup_dir.glob("db_guard_*.sqlite3"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for stale in files[keep:]:
        try:
            stale.unlink()
        except Exception:
            pass


def sqlite_guard(db_path: Path, backup_root: Path, keep_backups: int, make_backup: bool) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    if not db_path.exists():
        return [_check("sqlite_db", "fail", f"DB yok: {db_path}")]

    try:
        con = sqlite3.connect(str(db_path), timeout=5, isolation_level=None)
        try:
            con.execute("PRAGMA busy_timeout = 5000")
            quick = (con.execute("PRAGMA quick_check").fetchone() or ["?"])[0]
            integrity = (con.execute("PRAGMA integrity_check").fetchone() or ["?"])[0]
            fk_rows = con.execute("PRAGMA foreign_key_check").fetchall()
            counts = _sqlite_counts(con, DEFAULT_TABLES)

            checks.append(_check("sqlite_open", "ok", str(db_path)))
            checks.append(_check("sqlite_counts", "ok", json.dumps(counts, ensure_ascii=False)))
            checks.append(_check("sqlite_quick_check", "ok" if str(quick).lower() == "ok" else "fail", str(quick)))
            checks.append(_check("sqlite_integrity", "ok" if str(integrity).lower() == "ok" else "fail", str(integrity)))
            checks.append(_check(
                "sqlite_foreign_keys",
                "ok" if not fk_rows else "fail",
                "ok" if not fk_rows else f"{len(fk_rows)} sorun",
            ))
        finally:
            con.close()
    except Exception as exc:
        checks.append(_check("sqlite_integrity", "fail", f"{type(exc).__name__}: {exc}"))
        return checks

    if not make_backup:
        checks.append(_check("sqlite_backup", "warn", "yedek atlandi (--no-backup)"))
        return checks

    backup_dir = backup_root / "db_guard"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"db_guard_{stamp}.sqlite3"
    try:
        src = sqlite3.connect(str(db_path), timeout=5)
        dst = sqlite3.connect(str(backup_path), timeout=5)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        backup_check = _verify_sqlite_backup(backup_path)
        status = "ok" if backup_check.lower() == "ok" else "fail"
        checks.append(_check("sqlite_backup", status, str(backup_path), integrity=backup_check))
        _prune_guard_backups(backup_dir, keep_backups)
    except Exception as exc:
        checks.append(_check("sqlite_backup", "fail", f"{type(exc).__name__}: {exc}"))
    return checks


def _run_compose_postgres() -> Dict[str, Any]:
    if not AKILLILIK_COMPOSE.exists():
        return {"ok": False, "error": f"docker-compose yok: {AKILLILIK_COMPOSE}"}
    try:
        cmd = ["docker", "compose", "up", "-d", "postgres"]
        proc = subprocess.run(
            cmd,
            cwd=str(AKILLILIK_COMPOSE.parent),
            capture_output=True,
            text=True,
            timeout=90,
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-1000:],
            "stderr": (proc.stderr or "")[-1000:],
        }
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


def postgres_guard(repair: bool) -> List[Dict[str, Any]]:
    checks: List[Dict[str, Any]] = []
    enabled = _env_bool("YAZKLINIK_ENABLE_POSTGRES", False)
    dialect = os.environ.get("YAZKLINIK_DB_DIALECT", "").strip().lower()
    if not enabled and dialect != "postgresql":
        checks.append(_check("postgres_enabled", "warn", "PostgreSQL aktif degil"))
        return checks

    try:
        import yazklinik_postgres_agent as pg
    except Exception as exc:
        checks.append(_check("postgres_agent", "fail", f"{type(exc).__name__}: {exc}"))
        return checks

    health = pg.health_check()
    if not health.get("ok") and repair:
        start = _run_compose_postgres()
        checks.append(_check(
            "postgres_container_start",
            "ok" if start.get("ok") else "fail",
            json.dumps(start, ensure_ascii=False),
        ))
        for _ in range(20):
            time.sleep(1.5)
            health = pg.health_check()
            if health.get("ok"):
                break

    health_detail = dict(health)
    if "dsn" in health_detail:
        health_detail["dsn"] = _redact_url(str(health_detail["dsn"]))
    checks.append(_check(
        "postgres_health",
        "ok" if health.get("ok") else "fail",
        json.dumps(health_detail, ensure_ascii=False),
    ))
    if not health.get("ok"):
        return checks

    compare = pg.compare_counts(tables=DEFAULT_TABLES)
    if not compare.get("ok") and repair:
        migrate = pg.migrate_from_sqlite(
            tables=DEFAULT_TABLES,
            dry_run=False,
            init_schema_if_missing=True,
        )
        checks.append(_check(
            "postgres_resync",
            "ok" if migrate.get("ok") else "fail",
            json.dumps(migrate, ensure_ascii=False),
        ))
        compare = pg.compare_counts(tables=DEFAULT_TABLES)

    checks.append(_check(
        "postgres_compare",
        "ok" if compare.get("ok") else "fail",
        json.dumps(compare, ensure_ascii=False),
    ))
    return checks


def write_reports(report: Dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        f"YazKlinik DB Guard - {report['generated_at']}",
        f"Overall: {report['overall_status'].upper()}",
        "",
    ]
    for row in report["checks"]:
        lines.append(f"[{row['status'].upper()}] {row['name']}: {row.get('detail', '')}")
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    _reexec_with_project_venv()

    parser = argparse.ArgumentParser(description="YazKlinik DB Guard")
    parser.add_argument("--repair", action="store_true", help="PG container baslat ve gerekirse mirror senkronla")
    parser.add_argument("--no-backup", action="store_true", help="SQLite backup uretme")
    parser.add_argument("--keep-backups", type=int, default=21, help="Saklanacak guard backup sayisi")
    parser.add_argument("--json", action="store_true", help="Raporu JSON olarak yazdir")
    args = parser.parse_args()

    _load_env_file(CONFIG_ENV, override=False)
    _load_env_file(AKILLILIK_ENV, override=False)

    db_path = Path(os.environ.get("YAZKLINIK_DB_PATH") or ROOT / "local_db" / "yazklinik_v68.sqlite3")
    backup_root = Path(os.environ.get("YAZKLINIK_BACKUP_ROOT") or ROOT / "auto_backups")

    checks: List[Dict[str, Any]] = []
    checks.extend(sqlite_guard(db_path, backup_root, args.keep_backups, not args.no_backup))
    checks.extend(postgres_guard(args.repair))

    fail_count = sum(1 for row in checks if row["status"] == "fail")
    warn_count = sum(1 for row in checks if row["status"] == "warn")
    overall = "fail" if fail_count else "warn" if warn_count else "ok"
    report = {
        "ok": overall != "fail",
        "overall_status": overall,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "fail_count": fail_count,
        "warn_count": warn_count,
        "checks": checks,
    }
    write_reports(report)

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"DB_GUARD_STATUS={overall.upper()}")
        for row in checks:
            print(f"  [{row['status'].upper():4s}] {row['name']} - {row.get('detail', '')[:220]}")
        print(f"REPORT_JSON={REPORT_JSON}")
        print(f"REPORT_TXT={REPORT_TXT}")
        if report["ok"]:
            print("DATABASE_GUARD_OK")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

