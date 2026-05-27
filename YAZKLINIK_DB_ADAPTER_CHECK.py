#!/usr/bin/env python
"""Smoke checks for the D700 database adapter scaffold."""
from __future__ import annotations

import json
import os
from typing import Any, Dict

import yazklinik_db_adapter as adapter


def adapter_check() -> Dict[str, Any]:
    status = adapter.adapter_status(deep=False)
    blocked_probe = {"ok": False}
    old_primary = os.environ.get("YAZKLINIK_DB_PRIMARY")
    old_mode = os.environ.get("YAZKLINIK_POSTGRES_MODE")
    try:
        os.environ["YAZKLINIK_DB_PRIMARY"] = "postgresql"
        os.environ["YAZKLINIK_POSTGRES_MODE"] = "primary"
        try:
            adapter.assert_sqlite_maintenance_allowed("forced-primary-probe")
            blocked_probe = {
                "ok": False,
                "error": "SQLite maintenance was not blocked under forced PG primary",
            }
        except RuntimeError as exc:
            blocked_probe = {"ok": True, "blocked": str(exc)}
    finally:
        if old_primary is None:
            os.environ.pop("YAZKLINIK_DB_PRIMARY", None)
        else:
            os.environ["YAZKLINIK_DB_PRIMARY"] = old_primary
        if old_mode is None:
            os.environ.pop("YAZKLINIK_POSTGRES_MODE", None)
        else:
            os.environ["YAZKLINIK_POSTGRES_MODE"] = old_mode

    return {
        "ok": bool(status.get("ok") and blocked_probe.get("ok")),
        "status": status,
        "forced_primary_sqlite_maintenance_block": blocked_probe,
    }


def main() -> int:
    report = adapter_check()
    print("YAZKLINIK_DB_ADAPTER_CHECK_" + ("OK" if report.get("ok") else "FAIL"))
    cfg = (report.get("status") or {}).get("config") or {}
    print(
        f"primary={cfg.get('primary')} mode={cfg.get('mode')} "
        f"wants_pg_primary={cfg.get('wants_pg_primary')}"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

