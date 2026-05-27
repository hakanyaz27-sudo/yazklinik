#!/usr/bin/env python
"""Guard rails for switching YazKlinik D700 from SQLite to PostgreSQL primary.

The app is currently allowed to run PostgreSQL in shadow mode. This guard makes
that explicit and refuses a primary cutover if the readiness report still has
SQLite-only runtime or maintenance blockers.
"""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


ROOT = Path(__file__).resolve().parent
CONFIG_ENV = ROOT / "config.env"
AGENT_VERSION = "2026.05.19-pg-primary-guard"


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


def _norm(value: str) -> str:
    return str(value or "").strip().lower().replace("-", "_")


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _norm(os.environ.get(key, "1" if default else "0"))
    return raw in {"1", "true", "yes", "y", "on"}


def primary_guard(deep: bool = False) -> Dict[str, Any]:
    _load_config_env()
    primary = _norm(os.environ.get("YAZKLINIK_DB_PRIMARY", "sqlite"))
    mode = _norm(os.environ.get("YAZKLINIK_POSTGRES_MODE", "shadow"))
    dialect = _norm(os.environ.get("YAZKLINIK_DB_DIALECT", "sqlite"))
    enable_pg = _norm(os.environ.get("YAZKLINIK_ENABLE_POSTGRES", "0")) in {
        "1", "true", "yes", "on"
    }
    wants_pg_primary = primary in {"postgres", "postgresql", "pg"} or mode in {
        "primary", "cutover", "postgres_primary"
    }

    report: Dict[str, Any] = {
        "ok": False,
        "agent_version": AGENT_VERSION,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "primary": primary,
        "mode": mode,
        "dialect": dialect,
        "enable_postgres": enable_pg,
        "wants_pg_primary": wants_pg_primary,
        "guard": "unknown",
        "blockers": [],
        "runtime_adapter_ready": _env_bool("YAZKLINIK_POSTGRES_RUNTIME_ADAPTER_READY", False),
        "sql_compat_ready": _env_bool("YAZKLINIK_POSTGRES_SQL_COMPAT_READY", False),
    }

    try:
        import YAZKLINIK_POSTGRES_CUTOVER_READINESS as readiness
        cutover = readiness.readiness_check(deep=deep)
    except Exception as exc:
        report["guard"] = "readiness-unavailable"
        report["blockers"].append(f"readiness check failed: {exc}")
        return report

    report["cutover"] = {
        "ok": bool(cutover.get("ok")),
        "shadow_ready": bool(cutover.get("shadow_ready")),
        "primary_cutover_ready": bool(cutover.get("primary_cutover_ready")),
        "schema": cutover.get("schema") or "",
        "blockers": cutover.get("blockers") or [],
        "source_summary": (cutover.get("source_scan") or {}).get("summary") or {},
    }

    if wants_pg_primary:
        if not report["runtime_adapter_ready"]:
            report["blockers"].append(
                "PostgreSQL runtime adapter is not marked ready")
        if not report["sql_compat_ready"]:
            report["blockers"].append(
                "PostgreSQL SQL compatibility is not marked ready")
        if not cutover.get("primary_cutover_ready"):
            report["blockers"].extend(cutover.get("blockers") or [
                "PostgreSQL primary requested but cutover readiness is false"
            ])
        if report["blockers"]:
            report["guard"] = "blocked-primary-cutover"
            return report
        report["guard"] = "primary-cutover-allowed"
        report["ok"] = True
        return report

    if mode not in {"shadow", "mirror", "readonly", "read_only", ""}:
        report["guard"] = "unexpected-postgres-mode"
        report["blockers"].append(
            f"Unexpected YAZKLINIK_POSTGRES_MODE={mode!r}; expected shadow until cutover")
        return report

    report["guard"] = "shadow-safe"
    report["ok"] = bool(cutover.get("shadow_ready"))
    if not report["ok"]:
        report["blockers"].extend(cutover.get("blockers") or [
            "PostgreSQL shadow readiness is false"
        ])
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YazKlinik PostgreSQL primary guard")
    parser.add_argument("--deep", action="store_true", help="Run deep readiness check")
    parser.add_argument("--json", action="store_true", help="Print full JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = primary_guard(deep=args.deep)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("POSTGRES_PRIMARY_GUARD_" + ("OK" if report.get("ok") else "FAIL"))
        print(
            f"guard={report.get('guard')} "
            f"primary={report.get('primary')} "
            f"mode={report.get('mode')} "
            f"wants_pg_primary={report.get('wants_pg_primary')}"
        )
        cutover = report.get("cutover") or {}
        if cutover:
            print(
                f"shadow_ready={cutover.get('shadow_ready')} "
                f"primary_cutover_ready={cutover.get('primary_cutover_ready')} "
                f"schema={cutover.get('schema')}"
            )
        for blocker in report.get("blockers") or []:
            print(f"  [BLOCKER] {blocker}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

