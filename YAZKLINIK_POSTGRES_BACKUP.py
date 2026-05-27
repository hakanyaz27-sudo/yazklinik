#!/usr/bin/env python
"""PostgreSQL primary backup helper for YazKlinik D700."""
from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import quote, unquote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent
CONFIG_ENV = ROOT / "config.env"
BACKUP_DIR = ROOT / "auto_backups" / "postgres_primary"
REPORT_DIR = ROOT / "runtime_state" / "postgres_primary_backup"
LAST_REPORT = REPORT_DIR / "last_report.json"
BACKUP_VERSION = "2026.05.20-pg-primary-backup"


def _load_config_env(path: Path = CONFIG_ENV) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip()


def _dsn() -> str:
    explicit = os.environ.get("YAZKLINIK_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if explicit:
        return explicit
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "15432")
    user = os.environ.get("POSTGRES_USER", "yazklinik")
    pwd = os.environ.get("POSTGRES_PASSWORD", "")
    db = os.environ.get("POSTGRES_DB", "yazklinik")
    return f"postgresql://{user}:{quote(pwd)}@{host}:{port}/{db}"


def _masked_dsn(value: str) -> str:
    try:
        parts = urlsplit(value)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        netloc = f"{parts.username}:***@{host}" if parts.username else host
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        return "***"


def _safe_schema() -> str:
    schema = (
        os.environ.get("YAZKLINIK_POSTGRES_RUNTIME_SCHEMA")
        or os.environ.get("YAZKLINIK_POSTGRES_SHADOW_SCHEMA")
        or "yk_sqlite_shadow_current"
    ).strip()
    if not schema.replace("_", "a").isalnum() or not schema[:1].isalpha() and schema[:1] != "_":
        raise RuntimeError(f"Unsafe PostgreSQL schema name: {schema!r}")
    return schema


def _find_pg_dump() -> str:
    found = shutil.which("pg_dump")
    if found:
        return found
    candidates: List[Path] = []
    for root in (Path("C:/Program Files/PostgreSQL"), Path("C:/Program Files")):
        if root.exists():
            candidates.extend(root.glob("**/pg_dump.exe"))
    for item in sorted(candidates, reverse=True):
        if item.is_file():
            return str(item)
    return ""


def _dsn_without_password(dsn: str) -> tuple[str, str]:
    parts = urlsplit(dsn)
    password = unquote(parts.password or "")
    username = parts.username or ""
    host = parts.hostname or "localhost"
    netloc = quote(username) + "@" + host if username else host
    if parts.port:
        netloc += f":{parts.port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment)), password


def _run_pg_dump(pg_dump: str, dsn: str, schema: str, out_file: Path) -> Dict[str, Any]:
    dsn_safe, password = _dsn_without_password(dsn)
    env = dict(os.environ)
    if password:
        env["PGPASSWORD"] = password
    cmd = [
        pg_dump,
        f"--dbname={dsn_safe}",
        f"--schema={schema}",
        "--format=custom",
        "--blobs",
        "--no-owner",
        "--file",
        str(out_file),
    ]
    proc = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, env=env)
    return {
        "method": "pg_dump_custom",
        "ok": proc.returncode == 0 and out_file.exists() and out_file.stat().st_size > 0,
        "returncode": proc.returncode,
        "file": str(out_file),
        "size_bytes": out_file.stat().st_size if out_file.exists() else 0,
        "stderr_tail": (proc.stderr or "")[-4000:],
    }


def _json_snapshot(dsn: str, schema: str, out_file: Path) -> Dict[str, Any]:
    import psycopg
    from psycopg.rows import dict_row

    tables: List[str] = []
    row_count = 0
    with psycopg.connect(dsn, connect_timeout=8, row_factory=dict_row) as con:
        with con.cursor() as cur:
            cur.execute("SET search_path TO " + '"' + schema.replace('"', '""') + '"' + ", public")
            cur.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema=%s AND table_type='BASE TABLE' ORDER BY table_name",
                (schema,),
            )
            tables = [str(r["table_name"]) for r in cur.fetchall()]
            with gzip.open(out_file, "wt", encoding="utf-8") as fh:
                for table in tables:
                    cur.execute('SELECT * FROM "' + table.replace('"', '""') + '"')
                    for row in cur.fetchall():
                        fh.write(json.dumps({"table": table, "row": dict(row)}, ensure_ascii=False, default=str))
                        fh.write("\n")
                        row_count += 1
    return {
        "method": "jsonl_gzip_fallback",
        "ok": out_file.exists() and out_file.stat().st_size > 0,
        "file": str(out_file),
        "size_bytes": out_file.stat().st_size if out_file.exists() else 0,
        "tables": len(tables),
        "rows": row_count,
    }


def run_backup() -> Dict[str, Any]:
    _load_config_env()
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    schema = _safe_schema()
    dsn = _dsn()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report: Dict[str, Any] = {
        "ok": False,
        "backup_version": BACKUP_VERSION,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "schema": schema,
        "dsn": _masked_dsn(dsn),
        "backup_dir": str(BACKUP_DIR),
    }
    pg_dump = _find_pg_dump()
    try:
        if pg_dump:
            report["pg_dump"] = pg_dump
            result = _run_pg_dump(pg_dump, dsn, schema, BACKUP_DIR / f"yazklinik_pg_primary_{stamp}.dump")
        else:
            result = _json_snapshot(dsn, schema, BACKUP_DIR / f"yazklinik_pg_primary_{stamp}.jsonl.gz")
        report["result"] = result
        report["ok"] = bool(result.get("ok"))
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    LAST_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def backup_status() -> Dict[str, Any]:
    _load_config_env()
    if not LAST_REPORT.exists():
        return {"ok": False, "status": "missing", "report_path": str(LAST_REPORT)}
    try:
        data = json.loads(LAST_REPORT.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"ok": False, "status": "unreadable", "error": str(exc), "report_path": str(LAST_REPORT)}
    finished = str(data.get("finished_at") or "")
    age_min = None
    stale = False
    try:
        age_min = round((datetime.now() - datetime.fromisoformat(finished)).total_seconds() / 60, 2)
        stale = age_min > int(os.environ.get("YAZKLINIK_POSTGRES_BACKUP_MAX_AGE_MINUTES", "1440") or "1440")
    except Exception:
        pass
    result = data.get("result") or {}
    return {
        "ok": bool(data.get("ok")) and not stale,
        "status": "stale" if stale else ("ready" if data.get("ok") else "failed"),
        "schema": data.get("schema"),
        "method": result.get("method"),
        "file": result.get("file"),
        "size_bytes": result.get("size_bytes"),
        "finished_at": finished,
        "age_minutes": age_min,
        "report_path": str(LAST_REPORT),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="YazKlinik PostgreSQL primary backup")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = backup_status() if args.status else run_backup()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("POSTGRES_PRIMARY_BACKUP_" + ("OK" if report.get("ok") else "WARN"))
        if args.status:
            print(f"status={report.get('status')} method={report.get('method')} age_min={report.get('age_minutes')}")
        else:
            result = report.get("result") or {}
            print(f"method={result.get('method')} file={result.get('file')} size={result.get('size_bytes')}")
        print(f"report={LAST_REPORT}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

