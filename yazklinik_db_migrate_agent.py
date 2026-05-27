"""DB Migration Ajani - boot-time idempotent tablo olusturma.

yazklinik_web.py basinda calistirilir; eksik tum Session 6+7 tablolarini
otomatik olusturur (audit_log, patient_consents, user_2fa, portal_tokens,
stock_items, stock_movements, patient_portal_tokens, payments, vs).

Tum CREATE'ler IF NOT EXISTS - mevcut DB zarar gormez.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-db-migrate"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")


# Session 6 + 7 tum yeni tablolar
# ONEMLI: schema_migrations EN BASTA olmali ki sonraki migration'lar kendilerini kaydedebilsin
MIGRATIONS: List[Dict[str, Any]] = [
    {
        "name": "000_schema_migrations",
        "sql": """CREATE TABLE IF NOT EXISTS schema_migrations (
            name TEXT PRIMARY KEY,
            applied_at TEXT,
            agent_version TEXT
        )""",
        "indexes": [],
    },
    {
        "name": "001_audit_log",
        "sql": """CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ts TEXT NOT NULL,
            user TEXT,
            action TEXT,
            payload_json TEXT,
            ip TEXT,
            user_agent TEXT
        )""",
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts)",
            "CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action)",
            "CREATE INDEX IF NOT EXISTS idx_audit_user ON audit_log(user)",
        ],
    },
    {
        "name": "002_patient_consents",
        "sql": """CREATE TABLE IF NOT EXISTS patient_consents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_id TEXT NOT NULL,
            consent_type TEXT NOT NULL,
            consent_given INTEGER DEFAULT 0,
            consent_text TEXT,
            given_at TEXT,
            withdrawn_at TEXT,
            signed_by TEXT,
            method TEXT
        )""",
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_consent_patient ON patient_consents(patient_id)",
            "CREATE INDEX IF NOT EXISTS idx_consent_type ON patient_consents(consent_type)",
        ],
    },
    {
        "name": "003_user_2fa",
        "sql": """CREATE TABLE IF NOT EXISTS user_2fa (
            user TEXT PRIMARY KEY,
            secret_b32 TEXT,
            enabled INTEGER DEFAULT 0,
            backup_codes_hash TEXT,
            created_at TEXT,
            last_verified TEXT
        )""",
        "indexes": [],
    },
    {
        "name": "004_patient_portal_tokens",
        "sql": """CREATE TABLE IF NOT EXISTS patient_portal_tokens (
            token TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            phone TEXT,
            issued_at TEXT,
            expires_at TEXT,
            consumed_at TEXT,
            scopes TEXT
        )""",
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_portal_patient ON patient_portal_tokens(patient_id)",
            "CREATE INDEX IF NOT EXISTS idx_portal_expires ON patient_portal_tokens(expires_at)",
        ],
    },
    {
        "name": "005_stock_items",
        "sql": """CREATE TABLE IF NOT EXISTS stock_items (
            code TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            quantity_on_hand INTEGER DEFAULT 0,
            reorder_threshold INTEGER DEFAULT 5,
            expiry_date TEXT,
            supplier TEXT,
            last_used TEXT,
            cost_per_unit REAL DEFAULT 0,
            updated_at TEXT
        )""",
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_stock_expiry ON stock_items(expiry_date)",
        ],
    },
    {
        "name": "006_stock_movements",
        "sql": """CREATE TABLE IF NOT EXISTS stock_movements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_code TEXT,
            direction TEXT,
            quantity INTEGER,
            note TEXT,
            ts TEXT
        )""",
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_stock_mov_code ON stock_movements(item_code)",
            "CREATE INDEX IF NOT EXISTS idx_stock_mov_ts ON stock_movements(ts)",
        ],
    },
    {
        "name": "007_payments",
        "sql": """CREATE TABLE IF NOT EXISTS payments (
            order_id TEXT PRIMARY KEY,
            patient_id TEXT,
            amount_try REAL,
            description TEXT,
            invoice_number TEXT,
            provider TEXT,
            installments INTEGER DEFAULT 1,
            status TEXT,
            provider_ref TEXT,
            created_at TEXT,
            paid_at TEXT,
            refunded_at TEXT,
            raw_response TEXT
        )""",
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_payment_patient ON payments(patient_id)",
            "CREATE INDEX IF NOT EXISTS idx_payment_status ON payments(status)",
        ],
    },
    {
        "name": "008_lab_results",
        "sql": """CREATE TABLE IF NOT EXISTS lab_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_tc TEXT,
            test_code TEXT,
            test_name TEXT,
            value TEXT,
            unit TEXT,
            reference_range TEXT,
            flag TEXT,
            sample_date TEXT,
            report_date TEXT,
            source TEXT,
            ingested_at TEXT
        )""",
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_lab_tc ON lab_results(patient_tc)",
            "CREATE INDEX IF NOT EXISTS idx_lab_code ON lab_results(test_code)",
        ],
    },
    {
        "name": "009_iot_readings",
        "sql": """CREATE TABLE IF NOT EXISTS iot_readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_type TEXT,
            device_model TEXT,
            patient_id TEXT,
            measured_at TEXT,
            values_json TEXT,
            raw_packet TEXT,
            ingested_at TEXT
        )""",
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_iot_patient ON iot_readings(patient_id)",
            "CREATE INDEX IF NOT EXISTS idx_iot_device ON iot_readings(device_type)",
        ],
    },
    {
        "name": "010_pubmed_seen",
        "sql": """CREATE TABLE IF NOT EXISTS pubmed_seen_pmids (
            pmid TEXT PRIMARY KEY,
            query TEXT,
            seen_at TEXT,
            indexed INTEGER DEFAULT 0
        )""",
        "indexes": [],
    },
    {
        "name": "011_usg_measurements_archive_columns",
        "columns": [
            {
                "table": "usg_measurements",
                "name": "archived_at",
                "definition": "TEXT",
            },
            {
                "table": "usg_measurements",
                "name": "archived_by",
                "definition": "TEXT",
            },
            {
                "table": "usg_measurements",
                "name": "archive_reason",
                "definition": "TEXT",
            },
        ],
        "indexes": [
            "CREATE INDEX IF NOT EXISTS idx_usg_measurements_patient_archive "
            "ON usg_measurements(patient_key, archived_at)",
        ],
    },
]


@dataclass
class MigrationResult:
    name: str
    status: str            # applied | skipped | failed
    detail: str = ""


@dataclass
class MigrateReport:
    db_path: str
    ran_at: str
    total: int = 0
    applied: int = 0
    skipped: int = 0
    failed: int = 0
    results: List[MigrationResult] = field(default_factory=list)
    agent_version: str = AGENT_VERSION


def _already_applied(con: sqlite3.Connection, name: str) -> bool:
    try:
        row = con.execute(
            "SELECT 1 FROM schema_migrations WHERE name = ?", (name,)).fetchone()
        return bool(row)
    except Exception:
        return False  # tablo henuz yok


def _quote_ident(name: str) -> str:
    """Quote a hardcoded SQLite identifier."""
    text = str(name or "").strip()
    if not text or not text.replace("_", "").isalnum():
        raise ValueError(f"unsafe identifier: {name!r}")
    return f'"{text}"'


def _has_column(con: sqlite3.Connection, table: str, column: str) -> bool:
    rows = con.execute(f"PRAGMA table_info({_quote_ident(table)})").fetchall()
    return any(str(row[1]).lower() == str(column).lower() for row in rows)


def _apply_column_migrations(con: sqlite3.Connection, mig: Dict[str, Any]) -> None:
    """Apply additive columns only when they are missing."""
    for col in mig.get("columns", []) or []:
        table = str(col["table"])
        name = str(col["name"])
        definition = str(col.get("definition") or "TEXT").strip()
        if _has_column(con, table, name):
            continue
        con.execute(
            f"ALTER TABLE {_quote_ident(table)} "
            f"ADD COLUMN {_quote_ident(name)} {definition}"
        )


def migrate_all(db_path: Optional[str] = None,
                 force: bool = False) -> MigrateReport:
    """Tum migration'lari sirayla uygula. Idempotent."""
    db_path = db_path or DEFAULT_DB_PATH
    rpt = MigrateReport(
        db_path=db_path, ran_at=datetime.now().isoformat(timespec="seconds"),
        total=len(MIGRATIONS))

    if not os.path.exists(db_path):
        # DB yoksa olustur
        try:
            os.makedirs(os.path.dirname(db_path), exist_ok=True)
            sqlite3.connect(db_path).close()
        except Exception as e:
            rpt.failed = rpt.total
            rpt.results.append(MigrationResult(
                name="DB_CREATE", status="failed", detail=str(e)))
            return rpt

    con = sqlite3.connect(db_path)
    try:
        for mig in MIGRATIONS:
            name = mig["name"]
            try:
                # schema_migrations once gelir; sonraki migration'lar onu kontrol eder
                if not force and name != "000_schema_migrations" and _already_applied(con, name):
                    rpt.results.append(MigrationResult(
                        name=name, status="skipped", detail="zaten uygulanmis"))
                    rpt.skipped += 1
                    continue

                if mig.get("sql"):
                    con.execute(mig["sql"])
                _apply_column_migrations(con, mig)
                # Index'leri tek tek dene; var olan tabloda kolon yoksa atla
                for idx in mig.get("indexes", []):
                    try:
                        con.execute(idx)
                    except sqlite3.OperationalError as ie:
                        # "no such column" - mevcut farkli sema, indeks atla
                        if "no such column" not in str(ie):
                            raise

                # Schema migrations'a kayda gec (000 olustuktan sonra herkes yapabilir)
                try:
                    con.execute(
                        "INSERT OR REPLACE INTO schema_migrations "
                        "(name, applied_at, agent_version) VALUES (?, ?, ?)",
                        (name, datetime.now().isoformat(timespec="seconds"),
                         AGENT_VERSION))
                except Exception:
                    pass

                con.commit()
                rpt.results.append(MigrationResult(name=name, status="applied"))
                rpt.applied += 1
            except Exception as e:
                rpt.results.append(MigrationResult(
                    name=name, status="failed", detail=str(e)[:200]))
                rpt.failed += 1
    finally:
        con.close()
    return rpt


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "migrations_defined": len(MIGRATIONS)}


def boot_migrate(db_path: Optional[str] = None) -> bool:
    """yazklinik_web.py basinda cagrilir."""
    try:
        r = migrate_all(db_path=db_path)
        return r.failed == 0
    except Exception:
        return False


if __name__ == "__main__":
    r = migrate_all()
    print(f"DB: {r.db_path}")
    print(f"Toplam: {r.total} | Applied: {r.applied} | Skipped: {r.skipped} | Failed: {r.failed}")
    for res in r.results:
        sym = {"applied": "[+]", "skipped": "[=]", "failed": "[X]"}.get(res.status, "[?]")
        print(f"  {sym} {res.name} {res.detail[:60]}")
