#!/usr/bin/env python
"""PostgreSQL cutover readiness checks for YazKlinik D700.

This is Phase 2 after full mirror migration. It does not switch the live app.
It answers one question safely: "Is PostgreSQL ready enough to begin shadow
read / dual-write work, and what blocks primary cutover?"
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent
CONFIG_ENV = ROOT / "config.env"
RUNTIME_DIR = ROOT / "runtime_state" / "postgres_full_migration"
LAST_REPORT = RUNTIME_DIR / "last_report.json"
LAST_SCHEMA = RUNTIME_DIR / "last_schema.txt"
AGENT_VERSION = "2026.05.19-pg-cutover-readiness"

DEFAULT_KEY_TABLES = [
    "patients",
    "visits",
    "files",
    "settings",
    "usg_measurements",
    "patient_demographics",
    "patient_protocols",
    "prescriptions",
    "lab_results",
    "smart_result_uploads",
    "gama_lab_results",
]

SQLITE_CONNECT_CATEGORY_KEYS = (
    "core_runtime",
    "feature_runtime",
    "sqlite_maintenance",
    "unknown",
)


def _reexec_with_project_venv() -> None:
    if os.environ.get("YAZKLINIK_PG_CUTOVER_NO_REEXEC") == "1":
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
    os.environ["YAZKLINIK_PG_CUTOVER_NO_REEXEC"] = "1"
    os.execv(str(target), [str(target), str(Path(__file__).resolve()), *sys.argv[1:]])


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


def _env_bool(key: str, default: bool = False) -> bool:
    raw = str(os.environ.get(key, "1" if default else "0")).strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def _dsn() -> str:
    explicit = os.environ.get("YAZKLINIK_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if explicit:
        return explicit
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "15432")
    user = os.environ.get("POSTGRES_USER", "yazklinik")
    pwd = os.environ.get("POSTGRES_PASSWORD", "")
    db = os.environ.get("POSTGRES_DB", "yazklinik")
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


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


def _sqlite_path() -> Path:
    return Path(
        os.environ.get("YAZKLINIK_DB_PATH")
        or str(ROOT / "local_db" / "yazklinik_v68.sqlite3")
    )


def _connect_sqlite(path: Path) -> sqlite3.Connection:
    uri = path.resolve().as_uri() + "?mode=ro"
    con = sqlite3.connect(uri, uri=True, timeout=30)
    con.row_factory = sqlite3.Row
    return con


def _connect_pg():
    try:
        import psycopg
    except Exception as exc:
        raise RuntimeError(f"psycopg import failed: {exc}")
    return psycopg.connect(_dsn(), connect_timeout=8, autocommit=False)


def _safe_ident(value: str) -> str:
    text = str(value or "").strip()
    if not text or not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", text):
        raise ValueError(f"unsafe identifier: {value!r}")
    return text


def _q_sqlite_ident(value: str) -> str:
    return '"' + _safe_ident(value).replace('"', '""') + '"'


def _last_schema() -> str:
    if LAST_SCHEMA.exists():
        return LAST_SCHEMA.read_text(encoding="utf-8").strip()
    if LAST_REPORT.exists():
        try:
            data = json.loads(LAST_REPORT.read_text(encoding="utf-8"))
            return str(data.get("schema") or "").strip()
        except Exception:
            return ""
    return ""


def _read_last_report() -> Dict[str, Any]:
    if not LAST_REPORT.exists():
        return {"ok": False, "status": "missing", "report_path": str(LAST_REPORT)}
    try:
        data = json.loads(LAST_REPORT.read_text(encoding="utf-8"))
        data.setdefault("report_path", str(LAST_REPORT))
        return data
    except Exception as exc:
        return {"ok": False, "status": "unreadable", "error": str(exc)}


def _sqlite_tables(con: sqlite3.Connection) -> List[str]:
    rows = con.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def _sqlite_columns(con: sqlite3.Connection, table: str) -> List[str]:
    return [str(row["name"]) for row in con.execute(
        f"PRAGMA table_info({_q_sqlite_ident(table)})").fetchall()]


def _sqlite_column_types(con: sqlite3.Connection, table: str) -> Dict[str, str]:
    return {
        str(row["name"]): str(row["type"] or "")
        for row in con.execute(f"PRAGMA table_info({_q_sqlite_ident(table)})").fetchall()
    }


def _sqlite_numeric_columns(con: sqlite3.Connection, table: str) -> set[str]:
    types = _sqlite_column_types(con, table)
    out = set()
    for name, typ in types.items():
        t = str(typ or "").upper()
        if any(token in t for token in ("INT", "REAL", "FLOA", "DOUB", "NUM")):
            out.add(name)
    return out


def _sqlite_count(con: sqlite3.Connection, table: str) -> int:
    return int(con.execute(f"SELECT COUNT(*) FROM {_q_sqlite_ident(table)}").fetchone()[0])


def _pg_schema_exists(pg, schema: str) -> bool:
    with pg.cursor() as cur:
        cur.execute(
            "SELECT 1 FROM information_schema.schemata WHERE schema_name=%s",
            (schema,),
        )
        return bool(cur.fetchone())


def _pg_table_count(pg, schema: str, table: str) -> int:
    from psycopg import sql

    with pg.cursor() as cur:
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
            sql.Identifier(schema),
            sql.Identifier(table),
        ))
        return int(cur.fetchone()[0])


def _pg_columns(pg, schema: str, table: str) -> List[str]:
    with pg.cursor() as cur:
        cur.execute(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema=%s AND table_name=%s
            ORDER BY ordinal_position
            """,
            (schema, table),
        )
        return [str(row[0]) for row in cur.fetchall()]


def _canon_numeric(value: Any) -> str:
    try:
        dec = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return str(value)
    if not dec.is_finite():
        return str(value)
    normalized = dec.normalize()
    if normalized == 0:
        return "0"
    return format(normalized, "f").rstrip("0").rstrip(".") or "0"


def _canon_jsonish(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return {
            "json": json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        }
    if isinstance(value, str):
        text = value.strip()
        if text.startswith("{") or text.startswith("["):
            try:
                parsed = json.loads(text)
                if isinstance(parsed, (dict, list)):
                    return {
                        "json": json.dumps(
                            parsed,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    }
            except Exception:
                return value
    return value


def _canon_value(value: Any, numeric: bool = False) -> Any:
    if value is None:
        return None
    if isinstance(value, memoryview):
        value = value.tobytes()
    if isinstance(value, (bytes, bytearray)):
        raw = bytes(value)
        return {"blob_sha256": hashlib.sha256(raw).hexdigest(), "len": len(raw)}
    if numeric:
        return _canon_numeric(value)
    value = _canon_jsonish(value)
    if isinstance(value, (dict, list)):
        return value
    return str(value)


def _rows_digest_sqlite(con: sqlite3.Connection, table: str, columns: List[str],
                        numeric_columns: set[str]) -> Dict[str, Any]:
    sha = hashlib.sha256()
    total = 0
    rows = []
    col_sql = ", ".join(_q_sqlite_ident(c) for c in columns)
    for row in con.execute(f"SELECT {col_sql} FROM {_q_sqlite_ident(table)}").fetchall():
        rows.append(json.dumps([_canon_value(row[c], c in numeric_columns) for c in columns],
                               ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    for encoded in sorted(rows):
        sha.update(encoded.encode("utf-8"))
        sha.update(b"\n")
        total += 1
    return {"count": total, "sha256": sha.hexdigest()}


def _rows_digest_pg(pg, schema: str, table: str, columns: List[str],
                    numeric_columns: set[str]) -> Dict[str, Any]:
    from psycopg import sql

    sha = hashlib.sha256()
    rows = []
    total = 0
    query = sql.SQL("SELECT {} FROM {}.{}").format(
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        sql.Identifier(schema),
        sql.Identifier(table),
    )
    with pg.cursor() as cur:
        cur.execute(query)
        for row in cur.fetchall():
            rows.append(json.dumps([
                _canon_value(v, columns[idx] in numeric_columns)
                for idx, v in enumerate(row)
            ],
                                   ensure_ascii=False, sort_keys=True, separators=(",", ":")))
    for encoded in sorted(rows):
        sha.update(encoded.encode("utf-8"))
        sha.update(b"\n")
        total += 1
    return {"count": total, "sha256": sha.hexdigest()}


def _pg_transaction_probe(pg, schema: str) -> Dict[str, Any]:
    from psycopg import sql

    table = "_cutover_probe"
    try:
        with pg.cursor() as cur:
            cur.execute(sql.SQL("CREATE TABLE IF NOT EXISTS {}.{} (id BIGINT, note TEXT)").format(
                sql.Identifier(schema), sql.Identifier(table)))
        pg.commit()
        with pg.cursor() as cur:
            cur.execute(sql.SQL("INSERT INTO {}.{} (id, note) VALUES (1, %s)").format(
                sql.Identifier(schema), sql.Identifier(table)), ("rollback-probe",))
            cur.execute(sql.SQL("SELECT COUNT(*) FROM {}.{} WHERE note=%s").format(
                sql.Identifier(schema), sql.Identifier(table)), ("rollback-probe",))
            before_rollback = int(cur.fetchone()[0])
        pg.rollback()
        with pg.cursor() as cur:
            cur.execute(sql.SQL("SELECT COUNT(*) FROM {}.{} WHERE note=%s").format(
                sql.Identifier(schema), sql.Identifier(table)), ("rollback-probe",))
            after_rollback = int(cur.fetchone()[0])
        pg.commit()
        return {
            "ok": before_rollback >= 1 and after_rollback == 0,
            "before_rollback": before_rollback,
            "after_rollback": after_rollback,
        }
    except Exception as exc:
        try:
            pg.rollback()
        except Exception:
            pass
        return {"ok": False, "error": str(exc)}


def _source_scan() -> Dict[str, Any]:
    files = [
        ROOT / "yazklinik_web.py",
        ROOT / "yazklinik_v68.py",
        ROOT / "yazklinik_common.py",
        ROOT / "yazklinik_config.py",
    ]
    patterns = {
        "sqlite3_connect": r"\bsqlite3\.connect\s*\(",
        "sqlite_pragmas": r"\bPRAGMA\b",
        "sqlite_rowid": r"\browid\b",
        "sqlite_sequence": r"\bsqlite_sequence\b",
    }
    out = {
        "files": [],
        "totals": {key: 0 for key in patterns},
        "sqlite3_references": [],
        "summary": {
            "sqlite3_connect_total": 0,
            "core_runtime": 0,
            "feature_runtime": 0,
            "sqlite_maintenance": 0,
            "unknown": 0,
        },
    }
    for path in files:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        item = {"file": str(path.name), "matches": {}}
        for key, pattern in patterns.items():
            count = len(re.findall(pattern, text, flags=re.IGNORECASE))
            item["matches"][key] = count
            out["totals"][key] += count
        out["files"].append(item)
        for line_no, line in enumerate(text.splitlines(), start=1):
            if not re.search(patterns["sqlite3_connect"], line, flags=re.IGNORECASE):
                continue
            ref = _classify_sqlite_connect_ref(path.name, line_no, line)
            out["sqlite3_references"].append(ref)
            category = str(ref.get("category") or "unknown")
            if category not in SQLITE_CONNECT_CATEGORY_KEYS:
                category = "unknown"
            out["summary"][category] += 1
            out["summary"]["sqlite3_connect_total"] += 1
    return out


def _classify_sqlite_connect_ref(file_name: str, line_no: int,
                                 line_text: str) -> Dict[str, Any]:
    """Classify direct sqlite3.connect sites for PostgreSQL cutover planning."""
    category = "unknown"
    group = "unknown_sqlite_connect"
    action = "Incele ve PostgreSQL primary oncesi adapter/disable karari ver."

    if file_name == "yazklinik_v68.py":
        if 8740 <= line_no <= 8845:
            category = "core_runtime"
            group = "legacy_db_conn_runtime"
            action = "Ana db_conn/_raw_db_conn katmani PostgreSQL adapter olmadan primary cutover yapma."
        elif 8691 <= line_no <= 8713:
            category = "core_runtime"
            group = "startup_sqlite_ready_check"
            action = "Startup DB readiness kontrolunu DB dialect-aware hale getir."
        elif 8580 <= line_no <= 8625:
            category = "sqlite_maintenance"
            group = "sqlite_corruption_recovery_probe"
            action = "SQLite corruption recovery sadece SQLite primary/modunda calissin."
        elif 1490 <= line_no <= 1565:
            category = "sqlite_maintenance"
            group = "full_reset_sqlite_maintenance"
            action = "Tam sifirlama islemini PG icin ayri ve onayli akisla degistir."
        elif 1571 <= line_no <= 1610:
            category = "sqlite_maintenance"
            group = "sqlite_backup_snapshot"
            action = "Backup akisini PG dump + SQLite snapshot ayrimina al."
        elif 1612 <= line_no <= 1665:
            category = "sqlite_maintenance"
            group = "sqlite_restore_probe"
            action = "Restore akisini SQLite dosya restore yerine PG restore/import akisi ile ayir."
        elif 1670 <= line_no <= 1710:
            category = "sqlite_maintenance"
            group = "sqlite_diagnostics"
            action = "DB diagnostigini SQLite/PG dialect-aware hale getir."

    elif file_name == "yazklinik_web.py":
        if "sqlite3.connect" in line_text and "DB_PATH" in line_text:
            category = "sqlite_maintenance"
            group = "web_sqlite_maintenance"
            action = "Web tarafindaki SQLite'a ozel bakim/snapshot akisini PG uyumlu hale getir."
        elif "sqlite3.connect" in line_text and "target" in line_text:
            category = "sqlite_maintenance"
            group = "sqlite_snapshot_copy"
            action = "Snapshot hedefini PG dump/mirror export akisi ile degistir."
        if 108677 <= line_no <= 108730:
            category = "sqlite_maintenance"
            group = "selective_database_delete"
            action = "Secimli temizlik SQL'ini PG transaction ve sequence reset uyumlu hale getir."
        elif 165840 <= line_no <= 165890:
            category = "sqlite_maintenance"
            group = "sqlite_bloat_maintenance"
            action = "WAL checkpoint/VACUUM yerine PG VACUUM/ANALYZE veya no-op kullan."
        elif 167812 <= line_no <= 167833:
            category = "sqlite_maintenance"
            group = "sqlite_snapshot_copy"
            action = "Snapshot kopyasini PG dump/mirror export ile degistir."
        elif 174671 <= line_no <= 174690:
            category = "feature_runtime"
            group = "patient_portal_token_lookup"
            action = "Hasta portal token sorgusunu db_conn veya PG uyumlu repository katmanina tasi."

    return {
        "file": file_name,
        "line": line_no,
        "category": category,
        "group": group,
        "primary_cutover_blocker": True,
        "action": action,
        "text": str(line_text or "").strip()[:220],
    }


def readiness_check(deep: bool = False,
                    key_tables: Optional[List[str]] = None,
                    schema: str = "") -> Dict[str, Any]:
    _load_config_env()
    sqlite_path = _sqlite_path()
    schema = schema or _last_schema()
    report: Dict[str, Any] = {
        "ok": False,
        "shadow_ready": False,
        "primary_cutover_ready": False,
        "agent_version": AGENT_VERSION,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "sqlite_path": str(sqlite_path),
        "postgres_dsn": _masked_dsn(_dsn()),
        "schema": schema,
        "deep": bool(deep),
        "checks": [],
        "blockers": [],
    }

    if not sqlite_path.exists():
        report["blockers"].append(f"SQLite source missing: {sqlite_path}")
        return report
    if not schema:
        report["blockers"].append("No PostgreSQL full mirror schema found")
        return report

    last = _read_last_report()
    mirror_ok = bool(last.get("ok")) and int(last.get("sqlite_total_rows") or 0) == int(
        last.get("postgres_total_rows") or -1)
    report["checks"].append({
        "name": "last_full_mirror_report",
        "ok": mirror_ok,
        "schema": last.get("schema"),
        "sqlite_total_rows": last.get("sqlite_total_rows"),
        "postgres_total_rows": last.get("postgres_total_rows"),
        "report_path": last.get("report_path") or str(LAST_REPORT),
    })

    sq = None
    pg = None
    try:
        sq = _connect_sqlite(sqlite_path)
        pg = _connect_pg()
        schema_exists = _pg_schema_exists(pg, schema)
        report["checks"].append({"name": "pg_schema_exists", "ok": schema_exists})
        if not schema_exists:
            report["blockers"].append(f"PostgreSQL schema missing: {schema}")
            return report

        present_tables = set(_sqlite_tables(sq))
        wanted = key_tables or DEFAULT_KEY_TABLES
        checked_tables = [t for t in wanted if t in present_tables]
        table_checks = []
        for table in checked_tables:
            sqlite_count = _sqlite_count(sq, table)
            pg_count = _pg_table_count(pg, schema, table)
            sqlite_cols = _sqlite_columns(sq, table)
            pg_cols = _pg_columns(pg, schema, table)
            col_ok = sqlite_cols == pg_cols
            count_ok = sqlite_count == pg_count
            row: Dict[str, Any] = {
                "table": table,
                "ok": count_ok and col_ok,
                "sqlite_count": sqlite_count,
                "postgres_count": pg_count,
                "columns_match": col_ok,
            }
            if deep and count_ok and col_ok:
                numeric_cols = _sqlite_numeric_columns(sq, table)
                s_digest = _rows_digest_sqlite(sq, table, sqlite_cols, numeric_cols)
                p_digest = _rows_digest_pg(pg, schema, table, pg_cols, numeric_cols)
                row["digest_match"] = s_digest == p_digest
                row["sqlite_digest"] = s_digest
                row["postgres_digest"] = p_digest
                row["ok"] = bool(row["ok"] and row["digest_match"])
            table_checks.append(row)
        report["checks"].append({
            "name": "key_table_counts" + ("_and_digests" if deep else ""),
            "ok": all(t.get("ok") for t in table_checks),
            "checked": len(table_checks),
            "tables": table_checks,
        })

        tx_probe = _pg_transaction_probe(pg, schema)
        report["checks"].append({"name": "pg_transaction_rollback_probe", **tx_probe})

        source = _source_scan()
        report["source_scan"] = source
        direct_sqlite_refs = int(source.get("totals", {}).get("sqlite3_connect") or 0)
        if direct_sqlite_refs > 0:
            summary = source.get("summary") or {}
            report["blockers"].append(
                "Direct sqlite3.connect references remain: "
                f"total={direct_sqlite_refs}, "
                f"core_runtime={int(summary.get('core_runtime') or 0)}, "
                f"feature_runtime={int(summary.get('feature_runtime') or 0)}, "
                f"sqlite_maintenance={int(summary.get('sqlite_maintenance') or 0)}, "
                f"unknown={int(summary.get('unknown') or 0)}")

        runtime_adapter_ready = _env_bool("YAZKLINIK_POSTGRES_RUNTIME_ADAPTER_READY", False)
        sql_compat_ready = _env_bool("YAZKLINIK_POSTGRES_SQL_COMPAT_READY", False)
        report["runtime_cutover_flags"] = {
            "postgres_runtime_adapter_ready": runtime_adapter_ready,
            "postgres_sql_compat_ready": sql_compat_ready,
        }
        if not runtime_adapter_ready:
            report["blockers"].append(
                "PostgreSQL runtime adapter is not marked ready "
                "(YAZKLINIK_POSTGRES_RUNTIME_ADAPTER_READY=1 required)")
        if not sql_compat_ready:
            report["blockers"].append(
                "PostgreSQL SQL compatibility is not marked ready "
                "(YAZKLINIK_POSTGRES_SQL_COMPAT_READY=1 required)")

        report["shadow_ready"] = all(
            check.get("ok") for check in report["checks"]
            if check.get("name") in {
                "last_full_mirror_report",
                "pg_schema_exists",
                "key_table_counts",
                "key_table_counts_and_digests",
                "pg_transaction_rollback_probe",
            }
        )
        report["primary_cutover_ready"] = bool(report["shadow_ready"] and not report["blockers"])
        report["ok"] = bool(report["shadow_ready"])
    except Exception as exc:
        report["blockers"].append(f"{type(exc).__name__}: {exc}")
    finally:
        try:
            if sq is not None:
                sq.close()
        finally:
            if pg is not None:
                pg.close()

    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YazKlinik PostgreSQL cutover readiness")
    parser.add_argument("--deep", action="store_true", help="Kritik tablolar icin tam row digest karsilastir")
    parser.add_argument("--schema", default="", help="Mirror schema; bos ise son schema")
    parser.add_argument("--tables", nargs="*", default=None, help="Kontrol edilecek tablo listesi")
    parser.add_argument("--json", action="store_true", help="Tam JSON yazdir")
    return parser.parse_args()


def main() -> int:
    _reexec_with_project_venv()
    args = parse_args()
    report = readiness_check(deep=args.deep, key_tables=args.tables, schema=args.schema)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("POSTGRES_CUTOVER_READINESS_" + ("OK" if report.get("ok") else "FAIL"))
        print(
            f"shadow_ready={report.get('shadow_ready')} "
            f"primary_cutover_ready={report.get('primary_cutover_ready')} "
            f"schema={report.get('schema')}"
        )
        for check in report.get("checks") or []:
            print(f"  [{'OK' if check.get('ok') else 'ERR'}] {check.get('name')}")
        for blocker in report.get("blockers") or []:
            print(f"  [BLOCKER] {blocker}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

