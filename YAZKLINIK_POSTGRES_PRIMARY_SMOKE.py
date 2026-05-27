#!/usr/bin/env python
"""Fast PostgreSQL primary runtime smoke test."""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict

import yazklinik_db_adapter as adapter

SMOKE_VERSION = "2026.05.20-pg-primary-smoke"


def primary_smoke() -> Dict[str, Any]:
    cfg = adapter.runtime_config()
    report: Dict[str, Any] = {
        "ok": False,
        "smoke_version": SMOKE_VERSION,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "config": cfg,
        "checks": [],
    }
    try:
        with adapter.runtime_connection("pg-primary-smoke") as con:
            patients = con.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
            con.execute("CREATE TEMP TABLE yk_primary_smoke(id INTEGER PRIMARY KEY AUTOINCREMENT, note TEXT)")
            cur = con.execute("INSERT INTO yk_primary_smoke(note) VALUES(?)", ("rollback",))
            inserted_id = cur.lastrowid
            before = con.execute("SELECT COUNT(*) FROM yk_primary_smoke").fetchone()[0]
            con.rollback()
            report["checks"].append({
                "name": "runtime_postgres_primary",
                "ok": bool(cfg.get("wants_pg_primary") and patients >= 0),
                "patients": int(patients),
            })
            report["checks"].append({
                "name": "ddl_insert_lastrowid_rollback",
                "ok": inserted_id == 1 and before == 1,
                "lastrowid": inserted_id,
                "before_rollback": int(before),
            })
    except Exception as exc:
        report["checks"].append({"name": "primary_smoke_exception", "ok": False, "error": str(exc)})
    report["ok"] = all(bool(c.get("ok")) for c in report["checks"])
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    return report


def main() -> int:
    report = primary_smoke()
    print("POSTGRES_PRIMARY_SMOKE_" + ("OK" if report.get("ok") else "FAIL"))
    for check in report.get("checks") or []:
        print(f"  [{'OK' if check.get('ok') else 'ERR'}] {check.get('name')}")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
