"""PostgreSQL agent for YazKlinik: health check + dry-run migrate + counts.

Amaç:
- SQLite ile calismaya devam eden sistemde, PostgreSQL migration'yi
  once raporla, sonra güvenli geçişe hazırla.
- Uygulama davranısı bozulmadan, opsiyonel olarak sadece read-only
  doğrulama yapar.

Varsayilan:
- Postgres sadece "dry-run" ve "health" kontrolu icin acik olur.
- Calisma icin dependency olarak psycopg gereklidir.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlsplit, urlunsplit


AGENT_VERSION = "2026.05.19-postgres"
ROOT = Path(__file__).resolve().parent
CONFIG_ENV = ROOT / "config.env"
FULL_MIRROR_REPORT = ROOT / "runtime_state" / "postgres_full_migration" / "last_report.json"
SHADOW_SYNC_REPORT = ROOT / "runtime_state" / "postgres_shadow_sync" / "last_report.json"

DEFAULT_SQLITE_PATH = (
    os.environ.get("YAZKLINIK_DB_PATH")
    or str(ROOT / "local_db" / "yazklinik_v68.sqlite3")
)

_PG_DEFAULT_PORT = 15432
_PG_DEFAULT_USER = "yazklinik"
_PG_DEFAULT_DB = "yazklinik"

CRITICAL_SQLITE_TABLES = (
    "patients",
    "visits",
    "files",
    "usg_measurements",
    "patient_demographics",
    "patient_protocols",
    "prescriptions",
)

DEFAULT_MIGRATE_TABLES = ("patients", "visits")


def _runtime_schema() -> str:
    return (
        os.environ.get("YAZKLINIK_POSTGRES_RUNTIME_SCHEMA")
        or os.environ.get("YAZKLINIK_POSTGRES_SHADOW_SCHEMA")
        or "yk_sqlite_shadow_current"
    ).strip()


def _pg_primary_mode() -> bool:
    _load_config_env()
    primary = str(os.environ.get("YAZKLINIK_DB_PRIMARY") or "").strip().lower()
    mode = str(os.environ.get("YAZKLINIK_POSTGRES_MODE") or "").strip().lower()
    return primary in {"postgresql", "postgres", "pg"} and mode == "primary"


def _load_config_env(path: Path = CONFIG_ENV) -> None:
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        if key not in os.environ or str(os.environ.get(key) or "").strip() == "":
            os.environ[key] = value.strip()


def _load_env_file(path: str = str(ROOT / "akillilik" / ".env")) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, val = line.split("=", 1)
                out[key.strip()] = val.strip()
    except Exception:
        pass
    return out


def _env(key: str, default: str = "") -> str:
    _load_config_env()
    return os.environ.get(key, _load_env_file().get(key, default))


def _env_bool(key: str, default: bool = False) -> bool:
    raw = _env(key, "1" if default else "0").strip().lower()
    return raw in ("1", "true", "yes", "y", "on")


def _dsn() -> str:
    explicit = _env("YAZKLINIK_DATABASE_URL")
    if explicit:
        return explicit
    explicit = _env("YAZKLINIK_PG_DSN")
    if explicit:
        return explicit
    explicit = _env("DATABASE_URL")
    if explicit:
        return explicit

    host = _env("POSTGRES_HOST", "localhost")
    port = int(_env("POSTGRES_PORT", str(_PG_DEFAULT_PORT)))
    user = _env("POSTGRES_USER", _PG_DEFAULT_USER)
    pwd = _env("POSTGRES_PASSWORD", "CHANGE_yk_pg")
    db = _env("POSTGRES_DB", _PG_DEFAULT_DB)
    return f"postgresql://{user}:{pwd}@{host}:{port}/{db}"


def _masked_dsn(dsn: str) -> str:
    if not dsn:
        return ""
    try:
        parsed = urlsplit(dsn)
        if not parsed.username:
            return dsn
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        auth = f"{parsed.username}:***@{host}"
        return urlunsplit((parsed.scheme, auth, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        return "***"


def _connect():
    try:
        import psycopg
    except Exception as e:
        raise RuntimeError(f"psycopg yüklenemedi: {e}")

    try:
        return psycopg.connect(_dsn(), connect_timeout=5, autocommit=False)
    except Exception as e:
        raise RuntimeError(f"PG bağlantı hatası: {e}")


def _sqlite_counts(sqlite_path: str, tables: Iterable[str]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    con = sqlite3.connect(sqlite_path)
    try:
        con.row_factory = sqlite3.Row
        for t in tables:
            try:
                out[t] = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            except Exception:
                out[t] = None
        return out
    finally:
        con.close()


def health_check() -> Dict[str, Any]:
    schema = _runtime_schema()
    out: Dict[str, Any] = {
        "ok": False,
        "agent_version": AGENT_VERSION,
        "dsn": _masked_dsn(_dsn()),
        "runtime_schema": schema,
        "primary_mode": _pg_primary_mode(),
        "critical_tables": list(CRITICAL_SQLITE_TABLES),
        "timestamp": datetime.now().isoformat(timespec="seconds"),
    }
    try:
        with _connect() as con:
            with con.cursor() as cur:
                cur.execute("SELECT version();")
                out["version"] = cur.fetchone()[0]
                cur.execute("SELECT current_database(), current_user;")
                db, user = cur.fetchone()
                out["current_database"] = db
                out["current_user"] = user
                cur.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema=%s;",
                    (schema,),
                )
                out["table_count"] = cur.fetchone()[0]
                cur.execute("""
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = %s
                    ORDER BY table_name
                """, (schema,))
                out["tables"] = [r[0] for r in cur.fetchall()]
        out["full_mirror"] = full_mirror_status()
        out["cutover"] = cutover_status(deep=False)
        out["shadow_sync"] = shadow_sync_status()
        out["ok"] = True
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
    return out


def full_mirror_status() -> Dict[str, Any]:
    """Read latest full SQLite->PostgreSQL mirror report, if present."""
    if not FULL_MIRROR_REPORT.exists():
        return {
            "ok": False,
            "status": "missing",
            "report_path": str(FULL_MIRROR_REPORT),
        }
    try:
        data = json.loads(FULL_MIRROR_REPORT.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "status": "unreadable",
            "error": str(exc),
            "report_path": str(FULL_MIRROR_REPORT),
        }
    sqlite_rows = int(data.get("sqlite_total_rows") or 0)
    pg_rows = int(data.get("postgres_total_rows") or 0)
    ok = bool(data.get("ok")) and sqlite_rows == pg_rows and pg_rows > 0
    return {
        "ok": ok,
        "status": "ready" if ok else "mismatch",
        "schema": data.get("schema") or "",
        "normal_table_count": data.get("normal_table_count") or 0,
        "skipped_table_count": data.get("skipped_table_count") or 0,
        "sqlite_total_rows": sqlite_rows,
        "postgres_total_rows": pg_rows,
        "finished_at": data.get("finished_at") or "",
        "duration_sec": data.get("duration_sec"),
        "agent_version": data.get("agent_version") or "",
        "report_path": str(FULL_MIRROR_REPORT),
    }


def cutover_status(deep: bool = False) -> Dict[str, Any]:
    """Expose PostgreSQL cutover readiness through the PG health endpoint."""
    try:
        import YAZKLINIK_POSTGRES_CUTOVER_READINESS as readiness
        data = readiness.readiness_check(deep=deep)
    except Exception as exc:
        return {
            "ok": False,
            "status": "unavailable",
            "error": str(exc),
        }
    source = data.get("source_scan") or {}
    summary = source.get("summary") or {}
    return {
        "ok": bool(data.get("ok")),
        "shadow_ready": bool(data.get("shadow_ready")),
        "primary_cutover_ready": bool(data.get("primary_cutover_ready")),
        "schema": data.get("schema") or "",
        "blockers": data.get("blockers") or [],
        "sqlite_reference_summary": summary,
        "agent_version": data.get("agent_version") or "",
        "finished_at": data.get("finished_at") or "",
    }


def shadow_sync_status() -> Dict[str, Any]:
    """Read latest safe PostgreSQL shadow-sync run."""
    if _pg_primary_mode():
        return {
            "ok": True,
            "status": "disabled-primary-mode",
            "schema": _runtime_schema(),
            "shadow_ready": True,
            "primary_cutover_ready": True,
            "finished_at": "",
            "age_minutes": None,
            "stale": False,
            "cutover_blockers": [],
            "report_path": str(SHADOW_SYNC_REPORT),
        }
    if not SHADOW_SYNC_REPORT.exists():
        return {
            "ok": False,
            "status": "missing",
            "report_path": str(SHADOW_SYNC_REPORT),
        }
    try:
        data = json.loads(SHADOW_SYNC_REPORT.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "ok": False,
            "status": "unreadable",
            "error": str(exc),
            "report_path": str(SHADOW_SYNC_REPORT),
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
        "report_path": str(SHADOW_SYNC_REPORT),
    }


def init_schema() -> Dict[str, Any]:
    def _mismatch(cur, table_name: str, column_name: str, expect_type: str) -> bool:
        cur.execute(
            """
            SELECT data_type
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = %s
            """,
            (table_name, column_name),
        )
        row = cur.fetchone()
        if not row:
            return True
        return (row[0] or "").lower() != expect_type.lower()

    def _table_exists(cur, table_name: str) -> bool:
        cur.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema='public' AND table_name=%s
            """,
            (table_name,),
        )
        return bool(cur.fetchone())

    sql = """
    CREATE TABLE IF NOT EXISTS yk_patients_pg (
        folder_key TEXT PRIMARY KEY,
        display_name TEXT,
        phone TEXT,
        archived_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT now(),
        synced_from_sqlite_at TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_yk_patients_pg_name
        ON yk_patients_pg USING gin(to_tsvector('simple', COALESCE(display_name, '')));

    CREATE TABLE IF NOT EXISTS yk_visits_pg (
        id BIGSERIAL PRIMARY KEY,
        sqlite_id INTEGER UNIQUE,
        patient_folder_key TEXT NOT NULL,
        visit_date TIMESTAMPTZ,
        visit_type TEXT,
        notes TEXT,
        source TEXT,
        created_at TIMESTAMPTZ DEFAULT now(),
        CONSTRAINT fk_yk_visits_pg_patient
            FOREIGN KEY(patient_folder_key) REFERENCES yk_patients_pg(folder_key)
        ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_yk_visits_pg_pk ON yk_visits_pg(patient_folder_key);
    CREATE UNIQUE INDEX IF NOT EXISTS idx_yk_visits_pg_sqlite_id ON yk_visits_pg(sqlite_id);
    """
    out = {"ok": False, "agent_version": AGENT_VERSION, "timestamp": datetime.now().isoformat(timespec="seconds")}
    try:
        with _connect() as con:
            with con.cursor() as cur:
                if _mismatch(cur, "yk_patients_pg", "phone", "text"):
                    cur.execute("DROP TABLE IF EXISTS yk_patients_pg CASCADE;")
                if _mismatch(cur, "yk_visits_pg", "sqlite_id", "integer"):
                    cur.execute("DROP TABLE IF EXISTS yk_visits_pg CASCADE;")
                cur.execute(sql)
                if _table_exists(cur, "yk_patients_pg") and _table_exists(cur, "yk_visits_pg"):
                    cur.execute("TRUNCATE TABLE yk_visits_pg, yk_patients_pg RESTART IDENTITY CASCADE;")
                con.commit()
        out["ok"] = True
        out["message"] = "Sema hazır: yk_patients_pg, yk_visits_pg"
    except Exception as e:
        out["error"] = str(e)
    return out


def _copy_patients_from_sqlite(sqlite_con: sqlite3.Connection, pg_con) -> int:
    rows = sqlite_con.execute(
        "SELECT folder_key, display_name, archived_at FROM patients"
    ).fetchall()
    copied = 0
    with pg_con.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO yk_patients_pg
                    (folder_key, display_name, phone, archived_at, synced_from_sqlite_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (folder_key) DO UPDATE SET
                    display_name=EXCLUDED.display_name,
                    phone=EXCLUDED.phone,
                    archived_at=EXCLUDED.archived_at,
                    synced_from_sqlite_at=now()
                """,
                (row[0], row[1], None, row[2]),
            )
            copied += 1
    return copied


def _copy_visits_from_sqlite(sqlite_con: sqlite3.Connection, pg_con) -> int:
    rows = sqlite_con.execute(
        "SELECT rowid, patient_folder_key, visit_date, visit_type, notes, source FROM visits"
    ).fetchall()
    copied = 0
    with pg_con.cursor() as cur:
        for row in rows:
            cur.execute(
                """
                INSERT INTO yk_visits_pg
                    (sqlite_id, patient_folder_key, visit_date, visit_type, notes, source)
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (sqlite_id) DO UPDATE SET
                    patient_folder_key=EXCLUDED.patient_folder_key,
                    visit_date=EXCLUDED.visit_date,
                    visit_type=EXCLUDED.visit_type,
                    notes=EXCLUDED.notes,
                    source=EXCLUDED.source
                """,
                (row[0], row[1], row[2], row[3], row[4], row[5]),
            )
            copied += 1
    return copied


def migrate_from_sqlite(
    sqlite_path: Optional[str] = None,
    tables: Optional[List[str]] = None,
    batch_size: int = 500,
    dry_run: bool = True,
    init_schema_if_missing: bool = False,
) -> Dict[str, Any]:
    """SQLite'tan PostgreSQL'ye veri kopyasi (DRY-RUN default).

    Not: Guvenlik icin once sadece patients+visits kopyalanir.
    """
    out: Dict[str, Any] = {
        "ok": False,
        "agent_version": AGENT_VERSION,
        "dry_run": dry_run,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "tables": [],
        "rows_copied": 0,
        "errors": [],
    }

    src = sqlite_path or DEFAULT_SQLITE_PATH
    if not Path(src).exists():
        out["error"] = f"SQLite bulunamadi: {src}"
        return out

    target_tables = tuple(tables or DEFAULT_MIGRATE_TABLES)
    sq = sqlite3.connect(src)
    sq.row_factory = sqlite3.Row

    # oncece hangi tablolarin sayisini al
    counts = _sqlite_counts(src, target_tables if target_tables else CRITICAL_SQLITE_TABLES)
    for t in target_tables:
        out["tables"].append({"table": t, "sqlite_row_count": counts.get(t, None)})

    pg = None
    if dry_run:
        out["ok"] = True
        out["finished_at"] = datetime.now().isoformat(timespec="seconds")
        sq.close()
        return out

    try:
        if init_schema_if_missing:
            init_result = init_schema()
            out["init_schema"] = init_result
            if not init_result.get("ok"):
                out["errors"].append(f"init_schema failed: {init_result.get('error')}")
                out["error"] = "init_schema failed"
                return out

        pg = _connect()
        for table in target_tables:
            try:
                if table == "patients":
                    copied = _copy_patients_from_sqlite(sq, pg)
                elif table == "visits":
                    copied = _copy_visits_from_sqlite(sq, pg)
                else:
                    out["errors"].append(f"{table}: desteklenmiyor (yalniz patients+visits)")
                    continue
                out["rows_copied"] += copied
                out["tables"][ [x["table"] for x in out["tables"]].index(table) ]["copied"] = copied
                if batch_size and copied and copied % batch_size == 0:
                    pg.commit()
            except Exception as e:
                out["errors"].append(f"{table}: {e}")

        pg.commit()
        out["ok"] = len(out["errors"]) == 0
    except Exception as e:  # noqa: BLE001
        out["errors"].append(str(e))
    finally:
        try:
            if pg is not None:
                pg.close()
        finally:
            sq.close()

    out["finished_at"] = datetime.now().isoformat(timespec="seconds")
    if not out["ok"]:
        out["error"] = "Some tables not migrated successfully"
    return out


def compare_counts(sqlite_path: Optional[str] = None, tables: Optional[List[str]] = None) -> Dict[str, Any]:
    tables = tables or [*DEFAULT_MIGRATE_TABLES]
    src = sqlite_path or DEFAULT_SQLITE_PATH
    if not Path(src).exists():
        return {"ok": False, "error": f"SQLite bulunamadi: {src}"}

    out = {
        "ok": False,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "sqlite": {},
        "postgres": {},
        "tables": [],
        "mismatches": [],
        "agent_version": AGENT_VERSION,
    }
    out["sqlite"] = _sqlite_counts(src, tables)
    try:
        with _connect() as con:
            with con.cursor() as cur:
                out["postgres"]["yk_patients_pg"] = (
                    cur.execute("SELECT COUNT(*) FROM yk_patients_pg").fetchone()[0]
                )
                out["postgres"]["yk_visits_pg"] = (
                    cur.execute("SELECT COUNT(*) FROM yk_visits_pg").fetchone()[0]
                )
        for t in tables:
            pg_count = out["postgres"].get(
                "yk_patients_pg" if t == "patients" else "yk_visits_pg"
            )
            sqlite_count = out["sqlite"].get(t)
            matches = sqlite_count == pg_count
            out["tables"].append({
                "table": t,
                "sqlite": sqlite_count,
                "postgres": pg_count,
                "matches": matches,
            })
            if not matches:
                out["mismatches"].append({
                    "table": t,
                    "sqlite": sqlite_count,
                    "postgres": pg_count,
                })
        out["ok"] = not out["mismatches"]
    except Exception as e:
        out["error"] = str(e)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="YazKlinik PostgreSQL phase2 tool")
    p.add_argument("--sqlite", default=DEFAULT_SQLITE_PATH, help="SQLite db path")
    p.add_argument("--tables", nargs="*", default=list(DEFAULT_MIGRATE_TABLES))
    p.add_argument("--dry-run", action="store_true", default=True,
                   help="Default: only report, no write")
    p.add_argument("--apply", action="store_true", help="Gerçek migrate islemi yap")
    p.add_argument("--init-schema", action="store_true", help="Eksik PG tablolari olustur")
    p.add_argument("--compare", action="store_true", help="Row count karşılastirma")
    p.add_argument("--health", action="store_true", help="Sadece PG health raporu")
    args = p.parse_args()

    if args.health:
        print(json.dumps(health_check(), ensure_ascii=False, indent=2))
        return

    if args.compare:
        print(json.dumps(compare_counts(args.sqlite, args.tables), ensure_ascii=False, indent=2))
        return

    dry_run = not args.apply
    if dry_run:
        print("DRY RUN: only report")
    result = migrate_from_sqlite(
        sqlite_path=args.sqlite,
        tables=args.tables,
        dry_run=dry_run,
        init_schema_if_missing=args.init_schema,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
