#!/usr/bin/env python
"""PostgreSQL resilience check for YazKlinik D700.

Checks:
- direct PostgreSQL connectivity (host:POSTGRES_PORT)
- runtime DSN connectivity (YAZKLINIK_DATABASE_URL, typically PgBouncer)
- PITR settings (archive_mode/wal_level/archive_command)
- WAL archive freshness
- base backup freshness
- optional PgBouncer admin visibility (SHOW VERSION / SHOW POOLS)
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, unquote, urlsplit

ROOT = Path(__file__).resolve().parent
CONFIG_ENV = ROOT / "config.env"
REPORT_DIR = ROOT / "runtime_state" / "postgres_resilience"
LAST_REPORT = REPORT_DIR / "last_report.json"
AGENT_VERSION = "2026.05.23-pg-resilience-check"


def _load_config_env(path: Path = CONFIG_ENV) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if key:
            val = value.strip()
            if val:
                os.environ[key] = val
            elif key not in os.environ:
                os.environ[key] = val


def _dsn_from_env(force_port: Optional[int] = None) -> str:
    explicit = (os.environ.get("YAZKLINIK_DATABASE_URL") or "").strip() or (os.environ.get("DATABASE_URL") or "").strip()
    if explicit and force_port is None:
        return explicit
    host = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    port = str(force_port or os.environ.get("POSTGRES_PORT", "15432"))
    user = os.environ.get("POSTGRES_USER", "yazklinik")
    pwd = os.environ.get("POSTGRES_PASSWORD", "")
    db = os.environ.get("POSTGRES_DB", "yazklinik")
    return f"postgresql://{quote(user)}:{quote(pwd)}@{host}:{port}/{quote(db)}"


def _masked_dsn(dsn: str) -> str:
    try:
        parts = urlsplit(dsn)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        user = parts.username or ""
        netloc = f"{user}:***@{host}" if user else host
        return f"{parts.scheme}://{netloc}{parts.path or ''}"
    except Exception:
        return "***"


@dataclass
class CheckItem:
    name: str
    ok: bool
    severity: str
    detail: str
    extra: Dict[str, Any]

    def as_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "name": self.name,
            "ok": self.ok,
            "severity": self.severity,
            "detail": self.detail,
        }
        if self.extra:
            payload["extra"] = self.extra
        return payload


def _connect_probe(dsn: str, label: str) -> CheckItem:
    try:
        import psycopg

        with psycopg.connect(dsn, connect_timeout=6, autocommit=True) as con:
            with con.cursor() as cur:
                cur.execute("select current_database(), current_user")
                db, user = cur.fetchone()
                cur.execute("show server_version")
                server_version = cur.fetchone()[0]
        return CheckItem(
            name=label,
            ok=True,
            severity="critical",
            detail=f"ok db={db} user={user}",
            extra={"server_version": str(server_version)},
        )
    except Exception as exc:
        return CheckItem(
            name=label,
            ok=False,
            severity="critical",
            detail=f"connect failed: {type(exc).__name__}: {exc}",
            extra={},
        )


def _query_pitr_settings(direct_dsn: str) -> CheckItem:
    keys = [
        "archive_mode",
        "wal_level",
        "archive_timeout",
        "archive_command",
        "max_wal_senders",
    ]
    out: Dict[str, str] = {}
    try:
        import psycopg

        with psycopg.connect(direct_dsn, connect_timeout=6, autocommit=True) as con:
            with con.cursor() as cur:
                for key in keys:
                    cur.execute(f"show {key}")
                    out[key] = str(cur.fetchone()[0])
    except Exception as exc:
        return CheckItem(
            name="pitr_settings",
            ok=False,
            severity="critical",
            detail=f"query failed: {type(exc).__name__}: {exc}",
            extra={},
        )
    archive_mode_ok = out.get("archive_mode", "").strip().lower() == "on"
    wal_level_ok = out.get("wal_level", "").strip().lower() in {"replica", "logical"}
    archive_cmd_ok = "archive_command" in out and "%p" in out["archive_command"] and "%f" in out["archive_command"]
    ok = archive_mode_ok and wal_level_ok and archive_cmd_ok
    detail = (
        f"archive_mode={out.get('archive_mode')} wal_level={out.get('wal_level')} "
        f"archive_timeout={out.get('archive_timeout')}"
    )
    return CheckItem(
        name="pitr_settings",
        ok=ok,
        severity="critical",
        detail=detail,
        extra=out,
    )


def _resolve_archive_host_path(archive_command: str) -> Optional[Path]:
    if not archive_command:
        return None
    m = re.search(r'"([^"]+)[/\\]%f"', archive_command)
    if not m:
        return None
    raw = m.group(1)
    if raw.startswith("/var/lib/postgresql/data/"):
        suffix = raw.replace("/var/lib/postgresql/data/", "", 1).strip("/")
        return ROOT / "akillilik" / "data" / "postgres" / Path(suffix)
    if re.match(r"^[A-Za-z]:[/\\]", raw):
        return Path(raw)
    if raw.startswith("//") or raw.startswith("\\\\"):
        return Path(raw)
    return (ROOT / raw.replace("/", os.sep)).resolve()


def _wal_archive_freshness(path: Optional[Path], max_age_min: int) -> CheckItem:
    if path is None:
        return CheckItem(
            name="wal_archive_freshness",
            ok=False,
            severity="critical",
            detail="archive path parse edilemedi",
            extra={},
        )
    if not path.exists():
        return CheckItem(
            name="wal_archive_freshness",
            ok=False,
            severity="critical",
            detail=f"archive path yok: {path}",
            extra={"path": str(path)},
        )
    files = [p for p in path.iterdir() if p.is_file()]
    if not files:
        return CheckItem(
            name="wal_archive_freshness",
            ok=False,
            severity="critical",
            detail=f"archive bos: {path}",
            extra={"path": str(path), "count": 0},
        )
    latest = max(files, key=lambda p: p.stat().st_mtime)
    age_min = round((datetime.now().timestamp() - latest.stat().st_mtime) / 60.0, 2)
    ok = age_min <= max_age_min
    return CheckItem(
        name="wal_archive_freshness",
        ok=ok,
        severity="critical",
        detail=f"count={len(files)} latest={latest.name} age_min={age_min}",
        extra={"path": str(path), "count": len(files), "latest": latest.name, "age_minutes": age_min},
    )


def _base_backup_freshness(max_age_hours: int) -> CheckItem:
    base_dir = ROOT / "auto_backups" / "postgres_base"
    if not base_dir.exists():
        return CheckItem(
            name="base_backup_freshness",
            ok=False,
            severity="critical",
            detail=f"klasor yok: {base_dir}",
            extra={"path": str(base_dir)},
        )
    candidates = [p for p in base_dir.iterdir() if p.is_file() or p.is_dir()]
    if not candidates:
        return CheckItem(
            name="base_backup_freshness",
            ok=False,
            severity="critical",
            detail="base backup adayi yok",
            extra={"path": str(base_dir)},
        )
    latest = max(candidates, key=lambda p: p.stat().st_mtime)
    age_hours = round((datetime.now().timestamp() - latest.stat().st_mtime) / 3600.0, 2)
    ok = age_hours <= max_age_hours
    return CheckItem(
        name="base_backup_freshness",
        ok=ok,
        severity="critical",
        detail=f"latest={latest.name} age_hours={age_hours}",
        extra={"path": str(base_dir), "latest": latest.name, "age_hours": age_hours},
    )


def _pgbouncer_admin_probe(runtime_dsn: str) -> CheckItem:
    try:
        import psycopg

        parts = urlsplit(runtime_dsn)
        user = os.environ.get("PGBOUNCER_ADMIN_USER") or (parts.username or "")
        password = os.environ.get("PGBOUNCER_ADMIN_PASSWORD") or unquote(parts.password or "")
        host = parts.hostname or "127.0.0.1"
        port = parts.port or 16432
        with psycopg.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            dbname="pgbouncer",
            connect_timeout=5,
            autocommit=True,
        ) as con:
            with con.cursor() as cur:
                cur.execute("SHOW VERSION")
                version = cur.fetchone()[0]
                cur.execute("SHOW POOLS")
                pools = cur.fetchall()
        return CheckItem(
            name="pgbouncer_admin_probe",
            ok=True,
            severity="warning",
            detail=f"ok version={version} pools={len(pools)}",
            extra={"version": str(version), "pools": len(pools), "user": user},
        )
    except Exception as exc:
        return CheckItem(
            name="pgbouncer_admin_probe",
            ok=False,
            severity="warning",
            detail=f"admin probe fail: {type(exc).__name__}: {exc}",
            extra={},
        )


def _backup_agent_status() -> CheckItem:
    try:
        import YAZKLINIK_POSTGRES_BACKUP as backup_agent

        st = backup_agent.backup_status()
        ok = bool(st.get("ok"))
        return CheckItem(
            name="primary_backup_status",
            ok=ok,
            severity="warning",
            detail=f"status={st.get('status')} method={st.get('method')} age_min={st.get('age_minutes')}",
            extra=st,
        )
    except Exception as exc:
        return CheckItem(
            name="primary_backup_status",
            ok=False,
            severity="warning",
            detail=f"status read fail: {type(exc).__name__}: {exc}",
            extra={},
        )


def run_check(with_admin: bool, max_wal_age_min: int, max_base_age_hours: int) -> Dict[str, Any]:
    _load_config_env()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    runtime_dsn = _dsn_from_env(force_port=None)
    direct_dsn = _dsn_from_env(force_port=int(os.environ.get("POSTGRES_PORT", "15432") or "15432"))

    checks: List[CheckItem] = []
    checks.append(_connect_probe(direct_dsn, "postgres_direct_connect"))
    checks.append(_connect_probe(runtime_dsn, "runtime_dsn_connect"))
    pitr = _query_pitr_settings(direct_dsn)
    checks.append(pitr)

    archive_cmd = ""
    if pitr.extra:
        archive_cmd = str(pitr.extra.get("archive_command") or "")
    archive_path = _resolve_archive_host_path(archive_cmd)
    checks.append(_wal_archive_freshness(archive_path, max_age_min=max_wal_age_min))
    checks.append(_base_backup_freshness(max_age_hours=max_base_age_hours))
    checks.append(_backup_agent_status())
    if with_admin:
        checks.append(_pgbouncer_admin_probe(runtime_dsn))

    critical_fail = any((not c.ok) and c.severity == "critical" for c in checks)
    warning_fail = [c for c in checks if (not c.ok) and c.severity == "warning"]
    report: Dict[str, Any] = {
        "ok": not critical_fail,
        "agent_version": AGENT_VERSION,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "runtime_dsn": _masked_dsn(runtime_dsn),
        "direct_dsn": _masked_dsn(direct_dsn),
        "with_admin_probe": with_admin,
        "max_wal_age_minutes": max_wal_age_min,
        "max_base_age_hours": max_base_age_hours,
        "critical_fail_count": sum(1 for c in checks if (not c.ok) and c.severity == "critical"),
        "warning_fail_count": len(warning_fail),
        "checks": [c.as_dict() for c in checks],
    }
    LAST_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YazKlinik PostgreSQL resilience check")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    parser.add_argument("--with-admin", action="store_true", help="Include PgBouncer admin probe")
    parser.add_argument("--max-wal-age-min", type=int, default=int(os.environ.get("YAZKLINIK_PITR_WAL_MAX_AGE_MINUTES", "45") or "45"))
    parser.add_argument("--max-base-age-hours", type=int, default=int(os.environ.get("YAZKLINIK_PITR_BASEBACKUP_MAX_AGE_HOURS", "48") or "48"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = run_check(
        with_admin=bool(args.with_admin),
        max_wal_age_min=max(1, int(args.max_wal_age_min)),
        max_base_age_hours=max(1, int(args.max_base_age_hours)),
    )
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("POSTGRES_RESILIENCE_" + ("OK" if report.get("ok") else "FAIL"))
        print(
            f"critical_fail={report.get('critical_fail_count')} "
            f"warning_fail={report.get('warning_fail_count')}"
        )
        for item in report.get("checks") or []:
            status = "OK" if item.get("ok") else "FAIL"
            print(f"  [{status}] {item.get('name')}: {item.get('detail')}")
        print(f"report={LAST_REPORT}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

