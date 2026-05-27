#!/usr/bin/env python
"""Keep the PostgreSQL shadow mirror fresh without cutting over live writes.

This is intentionally conservative:
- SQLite remains the live primary database.
- PostgreSQL receives a full, replaceable shadow schema.
- A deep readiness check proves the copied data is usable for the next phase.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


ROOT = Path(__file__).resolve().parent
CONFIG_ENV = ROOT / "config.env"
REPORT_DIR = ROOT / "runtime_state" / "postgres_shadow_sync"
LAST_REPORT = REPORT_DIR / "last_report.json"
AGENT_VERSION = "2026.05.19-pg-shadow-sync"
DEFAULT_SCHEMA = "yk_sqlite_shadow_current"


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


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _run(args: List[str]) -> Dict[str, Any]:
    started = datetime.now()
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
    )
    finished = datetime.now()
    return {
        "command": [Path(sys.executable).name, *args],
        "ok": proc.returncode == 0,
        "returncode": proc.returncode,
        "started_at": started.isoformat(timespec="seconds"),
        "finished_at": finished.isoformat(timespec="seconds"),
        "duration_sec": round((finished - started).total_seconds(), 3),
        "stdout": proc.stdout or "",
        "stdout_tail": (proc.stdout or "")[-6000:],
        "stderr_tail": (proc.stderr or "")[-6000:],
    }


def _json_from_step(step: Dict[str, Any]) -> Dict[str, Any]:
    text = str(step.get("stdout") or step.get("stdout_tail") or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except Exception:
        return {}


def shadow_sync_status() -> Dict[str, Any]:
    _load_config_env()
    if not LAST_REPORT.exists():
        return {
            "ok": False,
            "status": "missing",
            "report_path": str(LAST_REPORT),
        }
    try:
        data = json.loads(LAST_REPORT.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "status": "unreadable",
            "error": str(exc),
            "report_path": str(LAST_REPORT),
        }
    finished_at = str(data.get("finished_at") or "")
    age_minutes = None
    stale = False
    try:
        if finished_at:
            age_minutes = round(
                (datetime.now() - datetime.fromisoformat(finished_at)).total_seconds() / 60,
                2,
            )
            max_age = int(_env("YAZKLINIK_POSTGRES_SHADOW_MAX_AGE_MINUTES", "60") or "60")
            stale = age_minutes > max_age
    except Exception:
        pass
    return {
        "ok": bool(data.get("ok")) and not stale,
        "status": "stale" if stale else ("ready" if data.get("ok") else "failed"),
        "schema": data.get("schema") or "",
        "shadow_ready": bool(data.get("shadow_ready")),
        "primary_cutover_ready": bool(data.get("primary_cutover_ready")),
        "finished_at": finished_at,
        "age_minutes": age_minutes,
        "stale": stale,
        "cutover_blockers": data.get("cutover_blockers") or [],
        "report_path": str(LAST_REPORT),
    }


def shadow_sync(schema: str = "", deep: bool = True) -> Dict[str, Any]:
    _load_config_env()
    schema = schema or _env("YAZKLINIK_POSTGRES_SHADOW_SCHEMA", DEFAULT_SCHEMA)
    primary = _env("YAZKLINIK_DB_PRIMARY", "sqlite").strip().lower()
    mode = _env("YAZKLINIK_POSTGRES_MODE", "shadow").strip().lower()

    report: Dict[str, Any] = {
        "ok": False,
        "agent_version": AGENT_VERSION,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "schema": schema,
        "primary": primary,
        "mode": mode,
        "deep": bool(deep),
        "steps": [],
        "blockers": [],
    }

    if primary not in {"sqlite", "local_sqlite"}:
        report["blockers"].append(
            f"Shadow sync refused because YAZKLINIK_DB_PRIMARY={primary!r}")
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        return report

    migrate_args = [
        "YAZKLINIK_POSTGRES_FULL_MIGRATE.py",
        "--apply",
        "--yes",
        "--schema",
        schema,
        "--replace",
    ]
    compare_args = [
        "YAZKLINIK_POSTGRES_FULL_MIGRATE.py",
        "--compare",
        "--schema",
        schema,
    ]
    readiness_args = [
        "YAZKLINIK_POSTGRES_CUTOVER_READINESS.py",
        "--schema",
        schema,
        "--json",
    ]
    if deep:
        readiness_args.append("--deep")

    for args in (migrate_args, compare_args, readiness_args):
        step = _run(args)
        report["steps"].append(step)
        if not step.get("ok"):
            report["blockers"].append(
                f"Step failed: {' '.join(args)}")
            break

    readiness = _json_from_step(report["steps"][-1]) if report["steps"] else {}
    for step in report.get("steps") or []:
        step.pop("stdout", None)
    report["readiness"] = readiness
    report["shadow_ready"] = bool(readiness.get("shadow_ready"))
    report["primary_cutover_ready"] = bool(readiness.get("primary_cutover_ready"))
    report["cutover_blockers"] = readiness.get("blockers") or []
    report["ok"] = bool(
        not report["blockers"]
        and report["steps"]
        and all(step.get("ok") for step in report["steps"])
        and report["shadow_ready"]
    )
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    LAST_REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh PostgreSQL shadow mirror safely")
    parser.add_argument("--schema", default="", help="Shadow schema name")
    parser.add_argument("--deep", action="store_true", default=True,
                        help="Run deep row-digest readiness check")
    parser.add_argument("--no-deep", action="store_false", dest="deep",
                        help="Skip deep row-digest check")
    parser.add_argument("--json", action="store_true", help="Print full JSON")
    parser.add_argument("--status", action="store_true", help="Print latest shadow sync status")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.status:
        status = shadow_sync_status()
        if args.json:
            print(json.dumps(status, ensure_ascii=False, indent=2))
        else:
            print("POSTGRES_SHADOW_SYNC_STATUS_" + ("OK" if status.get("ok") else "WARN"))
            print(
                f"status={status.get('status')} "
                f"schema={status.get('schema')} "
                f"age_min={status.get('age_minutes')} "
                f"shadow_ready={status.get('shadow_ready')}"
            )
            print(f"report={LAST_REPORT}")
        return 0 if status.get("ok") else 1
    report = shadow_sync(schema=args.schema, deep=args.deep)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("POSTGRES_SHADOW_SYNC_" + ("OK" if report.get("ok") else "FAIL"))
        print(
            f"schema={report.get('schema')} "
            f"shadow_ready={report.get('shadow_ready')} "
            f"primary_cutover_ready={report.get('primary_cutover_ready')}"
        )
        for step in report.get("steps") or []:
            cmd = " ".join(str(x) for x in step.get("command") or [])
            print(f"  [{'OK' if step.get('ok') else 'ERR'}] {cmd}")
        for blocker in report.get("blockers") or []:
            print(f"  [BLOCKER] {blocker}")
        for blocker in report.get("cutover_blockers") or []:
            print(f"  [CUTOVER-BLOCKER] {blocker}")
        print(f"report={LAST_REPORT}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
