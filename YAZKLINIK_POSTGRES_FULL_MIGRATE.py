#!/usr/bin/env python
"""Full SQLite -> PostgreSQL mirror migration for YazKlinik D700.

This tool does not switch the live application to PostgreSQL. It creates a
separate PostgreSQL schema and copies all normal SQLite tables into it for
verification. That makes the transition safe: no patient data is deleted, the
live SQLite file remains untouched, and PostgreSQL completeness can be checked
before application cutover work starts.

Examples:
  python YAZKLINIK_POSTGRES_FULL_MIGRATE.py --dry-run
  python YAZKLINIK_POSTGRES_FULL_MIGRATE.py --apply --yes
  python YAZKLINIK_POSTGRES_FULL_MIGRATE.py --compare --schema yk_sqlite_full_20260519_220000
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit


ROOT = Path(__file__).resolve().parent
CONFIG_ENV = ROOT / "config.env"
RUNTIME_DIR = ROOT / "runtime_state" / "postgres_full_migration"
LAST_REPORT = RUNTIME_DIR / "last_report.json"
LAST_SCHEMA = RUNTIME_DIR / "last_schema.txt"
AGENT_VERSION = "2026.05.19-full-pg-mirror"


def _reexec_with_project_venv() -> None:
    if os.environ.get("YAZKLINIK_PG_FULL_NO_REEXEC") == "1":
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
    os.environ["YAZKLINIK_PG_FULL_NO_REEXEC"] = "1"
    os.execv(str(target), [str(target), str(Path(__file__).resolve()), *sys.argv[1:]])


def _load_config_env(path: Path = CONFIG_ENV, override: bool = False) -> Dict[str, str]:
    data: Dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        data[key] = value
        if override or key not in os.environ:
            os.environ[key] = value
    return data


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


def _masked_dsn(dsn: str) -> str:
    try:
        parts = urlsplit(dsn)
        host = parts.hostname or ""
        if parts.port:
            host = f"{host}:{parts.port}"
        if parts.username:
            netloc = f"{parts.username}:***@{host}"
        else:
            netloc = host
        return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))
    except Exception:
        return "***"


def _safe_schema_name(value: str) -> str:
    name = str(value or "").strip().lower()
    name = re.sub(r"[^a-z0-9_]+", "_", name)
    name = re.sub(r"_+", "_", name).strip("_")
    if not name or not re.match(r"^[a-z_]", name):
        raise ValueError(f"unsafe schema name: {value!r}")
    return name[:58]


def _default_schema_name() -> str:
    return "yk_sqlite_full_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def _sqlite_path() -> Path:
    return Path(
        os.environ.get("YAZKLINIK_DB_PATH")
        or str(ROOT / "local_db" / "yazklinik_v68.sqlite3")
    )


def _connect_sqlite_readonly(path: Path) -> sqlite3.Connection:
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


def _sqlite_normal_tables(con: sqlite3.Connection,
                          only_tables: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    only = {str(t).strip() for t in (only_tables or []) if str(t).strip()}
    rows = con.execute(
        """
        SELECT name, sql
        FROM sqlite_master
        WHERE type='table'
          AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    out: List[Dict[str, Any]] = []
    for row in rows:
        name = str(row["name"] or "")
        if only and name not in only:
            continue
        create_sql = str(row["sql"] or "")
        if create_sql.upper().startswith("CREATE VIRTUAL TABLE"):
            out.append({
                "name": name,
                "skipped": True,
                "skip_reason": "virtual_table",
                "sqlite_sql": create_sql,
            })
            continue
        cols = con.execute(f'PRAGMA table_info("{name.replace(chr(34), chr(34) + chr(34))}")').fetchall()
        out.append({
            "name": name,
            "columns": [
                {
                    "name": str(c["name"]),
                    "type": str(c["type"] or ""),
                    "notnull": bool(c["notnull"]),
                    "pk": int(c["pk"] or 0),
                }
                for c in cols
            ],
            "sqlite_sql": create_sql,
        })
    return out


def _sqlite_count(con: sqlite3.Connection, table: str) -> int:
    safe = table.replace('"', '""')
    return int(con.execute(f'SELECT COUNT(*) FROM "{safe}"').fetchone()[0])


def _typed_schema_enabled() -> bool:
    return str(os.environ.get("YAZKLINIK_PG_TYPED_SCHEMA", "")).strip().lower() in (
        "1", "true", "yes", "on", "y")


def _sqlite_affinity(sqlite_type: str) -> str:
    """SQLite type-affinity rules (https://sqlite.org/datatype3.html)."""
    t = str(sqlite_type or "").upper()
    if "INT" in t or "BOOL" in t:
        return "INTEGER"
    if any(k in t for k in ("CHAR", "CLOB", "TEXT")):
        return "TEXT"
    if t == "" or "BLOB" in t:
        return "BLOB"
    if any(k in t for k in ("REAL", "FLOA", "DOUB")):
        return "REAL"
    return "NUMERIC"


def _pg_type(sqlite_type: str) -> str:
    t = str(sqlite_type or "").upper()
    if "BLOB" in t:
        return "BYTEA"
    if not _typed_schema_enabled():
        # Default full mirror is for completeness/safety, not production typing.
        # SQLite columns can hold mixed values regardless of declared affinity;
        # all-TEXT avoids lossy cast failures during the initial clinical copy.
        return "TEXT"
    # Typed production schema (YAZKLINIK_PG_TYPED_SCHEMA=1): integer/real
    # affinity -> numeric PG types so arithmetic/comparison works under PG
    # primary. Dates/decimals/strings stay TEXT (app treats them as text).
    aff = _sqlite_affinity(sqlite_type)
    if aff == "INTEGER":
        return "BIGINT"
    if aff == "REAL":
        return "DOUBLE PRECISION"
    if aff == "BLOB":
        return "BYTEA"
    return "TEXT"


def _coerce_for_pg(value: Any, pg_type: str) -> Any:
    """Coerce a SQLite value to the typed PG column type; bad values -> NULL.

    Only active for typed numeric columns; TEXT/BYTEA pass through unchanged
    (matching the proven all-TEXT mirror behaviour).
    """
    if value is None or pg_type in ("TEXT", "BYTEA"):
        return value
    if pg_type == "BIGINT":
        if isinstance(value, bool):
            return 1 if value else 0
        if isinstance(value, int):
            return value
        try:
            s = str(value).strip()
            if s == "":
                return None
            return int(s) if re.fullmatch(r"[+-]?\d+", s) else int(float(s))
        except Exception:
            return None
    if pg_type == "DOUBLE PRECISION":
        if isinstance(value, bool):
            return 1.0 if value else 0.0
        if isinstance(value, (int, float)):
            return float(value)
        try:
            s = str(value).strip()
            return float(s) if s else None
        except Exception:
            return None
    return value


def _create_schema_and_meta(pg, schema: str, replace: bool) -> None:
    from psycopg import sql

    with pg.cursor() as cur:
        if replace:
            cur.execute(sql.SQL("DROP SCHEMA IF EXISTS {} CASCADE").format(sql.Identifier(schema)))
        cur.execute(sql.SQL("CREATE SCHEMA IF NOT EXISTS {}").format(sql.Identifier(schema)))
        cur.execute(sql.SQL("""
            CREATE TABLE IF NOT EXISTS {}._migration_meta (
                key TEXT PRIMARY KEY,
                value TEXT,
                created_at TIMESTAMPTZ DEFAULT now()
            )
        """).format(sql.Identifier(schema)))
        cur.execute(sql.SQL("""
            INSERT INTO {}._migration_meta(key, value)
            VALUES ('agent_version', %s)
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, created_at=now()
        """).format(sql.Identifier(schema)), (AGENT_VERSION,))
        cur.execute(sql.SQL("""
            INSERT INTO {}._migration_meta(key, value)
            VALUES ('source_sqlite', %s)
            ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, created_at=now()
        """).format(sql.Identifier(schema)), (str(_sqlite_path()),))


def _create_pg_table(pg, schema: str, table: Dict[str, Any]) -> None:
    from psycopg import sql

    columns = table.get("columns") or []
    if not columns:
        return
    col_defs = []
    seen = set()
    for col in columns:
        col_name = str(col["name"])
        if col_name in seen:
            continue
        seen.add(col_name)
        col_defs.append(sql.SQL("{} {}").format(
            sql.Identifier(col_name),
            sql.SQL(_pg_type(str(col.get("type") or ""))),
        ))
    with pg.cursor() as cur:
        cur.execute(sql.SQL("DROP TABLE IF EXISTS {}.{}").format(
            sql.Identifier(schema), sql.Identifier(str(table["name"]))))
        cur.execute(sql.SQL("CREATE TABLE {}.{} ({})").format(
            sql.Identifier(schema),
            sql.Identifier(str(table["name"])),
            sql.SQL(", ").join(col_defs),
        ))


def _copy_table(sqlite_con: sqlite3.Connection, pg, schema: str, table: Dict[str, Any],
                batch_size: int) -> Dict[str, Any]:
    from psycopg import sql

    name = str(table["name"])
    columns = [str(c["name"]) for c in (table.get("columns") or [])]
    report: Dict[str, Any] = {
        "table": name,
        "columns": len(columns),
        "sqlite_count": 0,
        "postgres_count": 0,
        "copied": 0,
        "ok": False,
    }
    if table.get("skipped"):
        report.update({
            "skipped": True,
            "skip_reason": table.get("skip_reason") or "skipped",
            "ok": True,
        })
        return report
    if not columns:
        report.update({"skipped": True, "skip_reason": "no_columns", "ok": True})
        return report

    report["sqlite_count"] = _sqlite_count(sqlite_con, name)
    _create_pg_table(pg, schema, table)

    safe_name = name.replace('"', '""')
    select_sql = f'SELECT * FROM "{safe_name}"'
    sq_cur = sqlite_con.execute(select_sql)
    placeholders = sql.SQL(", ").join(sql.Placeholder() for _ in columns)
    insert_sql = sql.SQL("INSERT INTO {}.{} ({}) VALUES ({})").format(
        sql.Identifier(schema),
        sql.Identifier(name),
        sql.SQL(", ").join(sql.Identifier(c) for c in columns),
        placeholders,
    )
    col_types = {
        str(c["name"]): _pg_type(str(c.get("type") or ""))
        for c in (table.get("columns") or [])
    }
    copied = 0
    with pg.cursor() as cur:
        while True:
            rows = sq_cur.fetchmany(max(1, int(batch_size or 1000)))
            if not rows:
                break
            payload = [
                tuple(_coerce_for_pg(row[c], col_types.get(c, "TEXT")) for c in columns)
                for row in rows
            ]
            cur.executemany(insert_sql, payload)
            copied += len(payload)
    report["copied"] = copied
    with pg.cursor() as cur:
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
            sql.Identifier(schema), sql.Identifier(name)))
        report["postgres_count"] = int(cur.fetchone()[0])
    report["ok"] = report["sqlite_count"] == report["postgres_count"] == copied
    return report


def _add_keys_and_identity(pg, schema: str,
                           tables: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Typed-schema only: add PRIMARY KEY + (single integer PK) IDENTITY.

    Runs after the data copy so existing ids are preserved, then advances the
    identity sequence past MAX(id) so new INSERTs auto-generate non-colliding
    ids. Per-table graceful failure: a table whose mirrored data can't satisfy
    a PK (nulls/dupes) keeps its columns and is reported, not aborted.
    """
    from psycopg import sql

    out: List[Dict[str, Any]] = []
    for table in tables:
        if table.get("skipped") or not table.get("columns"):
            continue
        name = str(table["name"])
        cols = table.get("columns") or []
        pk_cols = [
            str(c["name"]) for c in sorted(
                (c for c in cols if int(c.get("pk") or 0) > 0),
                key=lambda c: int(c.get("pk") or 0))
        ]
        rec: Dict[str, Any] = {"table": name, "pk_cols": pk_cols,
                               "pk_ok": False, "identity": False}
        if not pk_cols:
            out.append(rec)
            continue
        try:
            with pg.cursor() as cur:
                cur.execute(sql.SQL("ALTER TABLE {}.{} ADD PRIMARY KEY ({})").format(
                    sql.Identifier(schema), sql.Identifier(name),
                    sql.SQL(", ").join(sql.Identifier(c) for c in pk_cols)))
            pg.commit()
            rec["pk_ok"] = True
        except Exception as exc:
            pg.rollback()
            rec["pk_error"] = str(exc)[:200]
            out.append(rec)
            continue
        if len(pk_cols) == 1:
            pkcol = pk_cols[0]
            pk_type = next((str(c.get("type") or "") for c in cols
                            if str(c["name"]) == pkcol), "")
            if _sqlite_affinity(pk_type) == "INTEGER":
                try:
                    with pg.cursor() as cur:
                        cur.execute(sql.SQL(
                            "ALTER TABLE {}.{} ALTER COLUMN {} "
                            "ADD GENERATED BY DEFAULT AS IDENTITY").format(
                            sql.Identifier(schema), sql.Identifier(name),
                            sql.Identifier(pkcol)))
                        cur.execute(sql.SQL(
                            "SELECT setval(pg_get_serial_sequence(%s, %s), "
                            "(SELECT COALESCE(MAX({c}), 0) + 1 FROM {s}.{t}), false)").format(
                            c=sql.Identifier(pkcol), s=sql.Identifier(schema),
                            t=sql.Identifier(name)),
                            (f"{schema}.{name}", pkcol))
                    pg.commit()
                    rec["identity"] = True
                except Exception as exc:
                    pg.rollback()
                    rec["identity_error"] = str(exc)[:200]
        out.append(rec)
    return out


def dry_run(sqlite_path: Path, only_tables: Optional[List[str]] = None) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "ok": False,
        "mode": "dry_run",
        "agent_version": AGENT_VERSION,
        "sqlite_path": str(sqlite_path),
        "dsn": _masked_dsn(_dsn()),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "tables": [],
    }
    with _connect_sqlite_readonly(sqlite_path) as sq:
        tables = _sqlite_normal_tables(sq, only_tables)
        for table in tables:
            if table.get("skipped"):
                count = None
            else:
                count = _sqlite_count(sq, str(table["name"]))
            report["tables"].append({
                "table": table["name"],
                "columns": len(table.get("columns") or []),
                "sqlite_count": count,
                "skipped": bool(table.get("skipped")),
                "skip_reason": table.get("skip_reason", ""),
            })
    try:
        with _connect_pg() as pg:
            with pg.cursor() as cur:
                cur.execute("SELECT current_database(), current_user")
                row = cur.fetchone()
                report["postgres"] = {"database": row[0], "user": row[1], "ok": True}
    except Exception as exc:
        report["postgres"] = {"ok": False, "error": str(exc)}
    report["normal_table_count"] = sum(1 for t in report["tables"] if not t["skipped"])
    report["skipped_table_count"] = sum(1 for t in report["tables"] if t["skipped"])
    report["sqlite_total_rows"] = sum(int(t["sqlite_count"] or 0) for t in report["tables"])
    report["ok"] = bool(report.get("postgres", {}).get("ok")) and report["normal_table_count"] > 0
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    return report


def apply_migration(sqlite_path: Path, schema: str, replace: bool = False,
                    only_tables: Optional[List[str]] = None,
                    batch_size: int = 1000) -> Dict[str, Any]:
    schema = _safe_schema_name(schema)
    report: Dict[str, Any] = {
        "ok": False,
        "mode": "apply",
        "agent_version": AGENT_VERSION,
        "schema": schema,
        "replace": bool(replace),
        "sqlite_path": str(sqlite_path),
        "dsn": _masked_dsn(_dsn()),
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "tables": [],
        "errors": [],
    }
    started = time.time()
    sq = _connect_sqlite_readonly(sqlite_path)
    pg = _connect_pg()
    try:
        tables = _sqlite_normal_tables(sq, only_tables)
        _create_schema_and_meta(pg, schema, replace=replace)
        pg.commit()
        for table in tables:
            try:
                row = _copy_table(sq, pg, schema, table, batch_size=batch_size)
                report["tables"].append(row)
                pg.commit()
            except Exception as exc:
                pg.rollback()
                report["errors"].append({"table": table.get("name"), "error": str(exc)})
                report["tables"].append({
                    "table": table.get("name"),
                    "ok": False,
                    "error": str(exc),
                })
        if _typed_schema_enabled():
            try:
                report["keys"] = _add_keys_and_identity(pg, schema, tables)
                report["pk_failures"] = [
                    k for k in report["keys"]
                    if k.get("pk_cols") and not k.get("pk_ok")]
                report["identity_count"] = sum(
                    1 for k in report["keys"] if k.get("identity"))
            except Exception as exc:
                pg.rollback()
                report["errors"].append({"keys_identity": str(exc)})
        report["normal_table_count"] = sum(
            1 for t in report["tables"] if not t.get("skipped"))
        report["skipped_table_count"] = sum(
            1 for t in report["tables"] if t.get("skipped"))
        report["sqlite_total_rows"] = sum(
            int(t.get("sqlite_count") or 0) for t in report["tables"])
        report["postgres_total_rows"] = sum(
            int(t.get("postgres_count") or 0) for t in report["tables"])
        bad = [t for t in report["tables"] if not t.get("ok")]
        report["ok"] = not report["errors"] and not bad
        report["duration_sec"] = round(time.time() - started, 2)
        report["finished_at"] = datetime.now().isoformat(timespec="seconds")
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        LAST_REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        LAST_SCHEMA.write_text(schema, encoding="utf-8")
    finally:
        try:
            sq.close()
        finally:
            pg.close()
    return report


def compare_schema(sqlite_path: Path, schema: str,
                   only_tables: Optional[List[str]] = None) -> Dict[str, Any]:
    from psycopg import sql

    schema = _safe_schema_name(schema)
    report: Dict[str, Any] = {
        "ok": False,
        "mode": "compare",
        "agent_version": AGENT_VERSION,
        "schema": schema,
        "sqlite_path": str(sqlite_path),
        "tables": [],
        "mismatches": [],
        "started_at": datetime.now().isoformat(timespec="seconds"),
    }
    with _connect_sqlite_readonly(sqlite_path) as sq, _connect_pg() as pg:
        tables = [t for t in _sqlite_normal_tables(sq, only_tables) if not t.get("skipped")]
        for table in tables:
            name = str(table["name"])
            sqlite_count = _sqlite_count(sq, name)
            try:
                with pg.cursor() as cur:
                    cur.execute(sql.SQL("SELECT COUNT(*) FROM {}.{}").format(
                        sql.Identifier(schema), sql.Identifier(name)))
                    pg_count = int(cur.fetchone()[0])
                ok = sqlite_count == pg_count
            except Exception as exc:
                # Keep compare resilient: one missing/broken table must not
                # poison all remaining checks with "transaction aborted".
                try:
                    pg.rollback()
                except Exception:
                    pass
                pg_count = None
                ok = False
                report["mismatches"].append({
                    "table": name,
                    "sqlite": sqlite_count,
                    "postgres": pg_count,
                    "error": str(exc),
                })
            row = {
                "table": name,
                "sqlite": sqlite_count,
                "postgres": pg_count,
                "matches": ok,
            }
            report["tables"].append(row)
            if not ok and not any(m.get("table") == name for m in report["mismatches"]):
                report["mismatches"].append(row)
    report["ok"] = not report["mismatches"]
    report["checked_tables"] = len(report["tables"])
    report["finished_at"] = datetime.now().isoformat(timespec="seconds")
    return report


def _summary(report: Dict[str, Any]) -> str:
    if report.get("mode") == "apply":
        return (
            f"ok={report.get('ok')} schema={report.get('schema')} "
            f"tables={report.get('normal_table_count')} skipped={report.get('skipped_table_count')} "
            f"rows={report.get('postgres_total_rows')}/{report.get('sqlite_total_rows')} "
            f"errors={len(report.get('errors') or [])}"
        )
    if report.get("mode") == "compare":
        return (
            f"ok={report.get('ok')} schema={report.get('schema')} "
            f"checked={report.get('checked_tables')} mismatches={len(report.get('mismatches') or [])}"
        )
    return (
        f"ok={report.get('ok')} tables={report.get('normal_table_count')} "
        f"skipped={report.get('skipped_table_count')} rows={report.get('sqlite_total_rows')}"
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YazKlinik full SQLite -> PostgreSQL mirror")
    parser.add_argument("--sqlite", default="", help="Kaynak SQLite yolu")
    parser.add_argument("--schema", default="", help="PostgreSQL hedef schema")
    parser.add_argument("--tables", nargs="*", default=None, help="Sadece belirli tablolar")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true", help="Sadece raporla")
    parser.add_argument("--apply", action="store_true", help="PostgreSQL'e mirror kopyala")
    parser.add_argument("--compare", action="store_true", help="SQLite ile PG schema sayilarini karsilastir")
    parser.add_argument("--replace", action="store_true", help="Hedef schema varsa drop cascade yap")
    parser.add_argument("--yes", action="store_true", help="--apply icin zorunlu onay")
    parser.add_argument("--json", action="store_true", help="Tam JSON yazdir")
    return parser.parse_args()


def main() -> int:
    _reexec_with_project_venv()
    _load_config_env()
    args = parse_args()
    sqlite_path = Path(args.sqlite) if args.sqlite else _sqlite_path()
    if not sqlite_path.exists():
        print(f"SQLite bulunamadi: {sqlite_path}", file=sys.stderr)
        return 2

    if args.apply and not args.yes:
        print("--apply icin --yes zorunlu. Canli SQLite'a dokunulmaz; sadece PG mirror yazilir.", file=sys.stderr)
        return 2
    if args.apply and args.compare:
        print("--apply ve --compare birlikte kullanilamaz.", file=sys.stderr)
        return 2

    schema = _safe_schema_name(args.schema) if args.schema else _default_schema_name()
    try:
        if args.compare:
            if not args.schema:
                if LAST_SCHEMA.exists():
                    schema = _safe_schema_name(LAST_SCHEMA.read_text(encoding="utf-8").strip())
                else:
                    print("--compare icin --schema gerekli (last_schema yok).", file=sys.stderr)
                    return 2
            report = compare_schema(sqlite_path, schema=schema, only_tables=args.tables)
        elif args.apply:
            report = apply_migration(
                sqlite_path,
                schema=schema,
                replace=args.replace,
                only_tables=args.tables,
                batch_size=args.batch_size,
            )
        else:
            report = dry_run(sqlite_path, only_tables=args.tables)
    except Exception as exc:
        report = {
            "ok": False,
            "agent_version": AGENT_VERSION,
            "error": f"{type(exc).__name__}: {exc}",
        }

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print("POSTGRES_FULL_MIGRATE_" + ("OK" if report.get("ok") else "FAIL"))
        print(_summary(report))
        if report.get("schema"):
            print(f"schema={report.get('schema')}")
        if report.get("mode") == "apply":
            print(f"report={LAST_REPORT}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())

