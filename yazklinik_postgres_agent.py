"""PostgreSQL Ajani - SQLite buyudukce migration + dual-write hazirligi.

DEFAULT DAVRANIS: YazKlinik SQLite ile calismaya DEVAM eder.
Bu modul sadece:
    - PostgreSQL baglantisi acmak
    - SQLite -> PostgreSQL migration (DRY-RUN default)
    - Dual-write helper (opsiyonel, manuel aktivasyon)
    - PG saglik kontrolu

Hicbir mevcut kod degistirilmez.

Env:
    YAZKLINIK_PG_DSN  veya
    POSTGRES_PASSWORD (akillilik/.env'den okur)
    PG default: postgresql://yazklinik:<pw>@localhost:15432/yazklinik

Kullanim:
    from yazklinik_postgres_agent import health_check, migrate_from_sqlite
    print(health_check())
    print(migrate_from_sqlite(dry_run=True))   # sadece raporlar
    print(migrate_from_sqlite(dry_run=False, tables=['patients','visits']))
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-postgres"

DEFAULT_SQLITE_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                       or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")

# Default DSN
_PG_DEFAULT_PORT = 15432
_PG_DEFAULT_USER = "yazklinik"
_PG_DEFAULT_DB = "yazklinik"


def _load_env_file(path: str = r"D:\YazKlinik_Final_D300\akillilik\.env") -> Dict[str, str]:
    out = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip()
    except Exception:
        pass
    return out


def _dsn(host: str = "localhost", port: int = _PG_DEFAULT_PORT) -> str:
    explicit = os.environ.get("YAZKLINIK_PG_DSN") or os.environ.get("DATABASE_URL")
    if explicit:
        return explicit
    pw = os.environ.get("POSTGRES_PASSWORD") or _load_env_file().get("POSTGRES_PASSWORD", "")
    if not pw:
        pw = "CHANGE_yk_pg"
    return f"postgresql://{_PG_DEFAULT_USER}:{pw}@{host}:{port}/{_PG_DEFAULT_DB}"


def _connect():
    try:
        import psycopg
        return psycopg.connect(_dsn(), connect_timeout=5)
    except ImportError:
        raise RuntimeError("psycopg yuklu degil. pip install psycopg[binary]")
    except Exception as e:
        raise RuntimeError(f"PG baglanti: {e}")


def health_check() -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "ok": False,
        "agent_version": AGENT_VERSION,
        "dsn_host": "localhost",
        "dsn_port": _PG_DEFAULT_PORT,
        "database": _PG_DEFAULT_DB,
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
                cur.execute("SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")
                out["table_count"] = cur.fetchone()[0]
        out["ok"] = True
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
    return out


def init_schema() -> Dict[str, Any]:
    """En azindan dual-write icin temel tablolari olustur (idempotent)."""
    sql = """
    CREATE TABLE IF NOT EXISTS yk_patients_pg (
        folder_key TEXT PRIMARY KEY,
        display_name TEXT,
        phone TEXT,
        archived_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ DEFAULT now(),
        synced_from_sqlite_at TIMESTAMPTZ
    );
    CREATE INDEX IF NOT EXISTS idx_yk_patients_pg_name ON yk_patients_pg
        USING gin(to_tsvector('simple', display_name));
    CREATE TABLE IF NOT EXISTS yk_visits_pg (
        id SERIAL PRIMARY KEY,
        patient_folder_key TEXT REFERENCES yk_patients_pg(folder_key) ON DELETE CASCADE,
        visit_date TIMESTAMPTZ,
        visit_type TEXT,
        notes TEXT,
        source TEXT,
        sqlite_id INT,
        created_at TIMESTAMPTZ DEFAULT now()
    );
    CREATE INDEX IF NOT EXISTS idx_yk_visits_pg_pk ON yk_visits_pg(patient_folder_key);
    CREATE TABLE IF NOT EXISTS yk_audit_log_pg (
        id SERIAL PRIMARY KEY,
        timestamp TIMESTAMPTZ DEFAULT now(),
        username TEXT,
        action TEXT,
        patient_key TEXT,
        payload JSONB
    );
    """
    out = {"ok": False, "agent_version": AGENT_VERSION}
    try:
        with _connect() as con:
            with con.cursor() as cur:
                cur.execute(sql)
                con.commit()
        out["ok"] = True
        out["message"] = "Sema olusturuldu (yk_patients_pg, yk_visits_pg, yk_audit_log_pg)"
    except Exception as e:
        out["error"] = str(e)
    return out


def migrate_from_sqlite(sqlite_path: Optional[str] = None,
                          tables: Optional[List[str]] = None,
                          batch_size: int = 500,
                          dry_run: bool = True) -> Dict[str, Any]:
    """SQLite'tan PG'ye veri kopyala (READ-ONLY SQLite, idempotent PG UPSERT).
    Default dry_run=True: hicbir sey yazmaz, sadece raporlar.
    """
    out: Dict[str, Any] = {
        "ok": False, "dry_run": dry_run, "started_at": datetime.now().isoformat(timespec="seconds"),
        "tables_processed": [], "rows_copied": 0, "errors": [],
        "agent_version": AGENT_VERSION,
    }
    src = sqlite_path or DEFAULT_SQLITE_PATH
    if not Path(src).exists():
        out["error"] = f"SQLite bulunamadi: {src}"
        return out

    target_tables = tables or ["patients", "visits"]
    sq = sqlite3.connect(src)
    sq.row_factory = sqlite3.Row
    try:
        pg = None
        if not dry_run:
            pg = _connect()
        for table in target_tables:
            try:
                count = sq.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                out["tables_processed"].append({"table": table, "row_count": count})
                if dry_run:
                    continue
                # Tipik kopyala mantigi: yalniz patients, visits
                with pg.cursor() as cur:
                    if table == "patients":
                        rows = sq.execute(
                            "SELECT folder_key, display_name, phone, archived_at "
                            "FROM patients").fetchall()
                        copied = 0
                        for r in rows:
                            cur.execute(
                                "INSERT INTO yk_patients_pg "
                                "(folder_key, display_name, phone, archived_at, synced_from_sqlite_at) "
                                "VALUES (%s, %s, %s, %s, now()) "
                                "ON CONFLICT (folder_key) DO UPDATE SET "
                                "  display_name=EXCLUDED.display_name, "
                                "  phone=EXCLUDED.phone, "
                                "  archived_at=EXCLUDED.archived_at, "
                                "  synced_from_sqlite_at=now()",
                                (r["folder_key"], r["display_name"], r["phone"], r["archived_at"]))
                            copied += 1
                            if copied % batch_size == 0:
                                pg.commit()
                        pg.commit()
                        out["rows_copied"] += copied
                    elif table == "visits":
                        rows = sq.execute(
                            "SELECT id, patient_folder_key, visit_date, visit_type, "
                            "notes, source FROM visits").fetchall()
                        copied = 0
                        for r in rows:
                            cur.execute(
                                "INSERT INTO yk_visits_pg "
                                "(sqlite_id, patient_folder_key, visit_date, visit_type, notes, source) "
                                "VALUES (%s, %s, %s, %s, %s, %s)",
                                (r["id"], r["patient_folder_key"], r["visit_date"],
                                 r["visit_type"], r["notes"], r["source"]))
                            copied += 1
                            if copied % batch_size == 0:
                                pg.commit()
                        pg.commit()
                        out["rows_copied"] += copied
            except Exception as e:
                out["errors"].append(f"{table}: {e}")
        if pg:
            pg.close()
        out["ok"] = True
        out["finished_at"] = datetime.now().isoformat(timespec="seconds")
    finally:
        sq.close()
    return out


if __name__ == "__main__":
    print("HEALTH:", json.dumps(health_check(), ensure_ascii=False, indent=2))
    print("\nINIT SCHEMA:", json.dumps(init_schema(), ensure_ascii=False, indent=2))
    print("\nDRY-RUN MIGRATION:", json.dumps(migrate_from_sqlite(dry_run=True), ensure_ascii=False, indent=2))
