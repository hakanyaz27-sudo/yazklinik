"""Duzen Laboratuvari Entegrasyon Stub.

Duzen Lab (ve benzeri ozel laboratuvarlar) icin sonuc cekme + tarama.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-lab-duzen"

DUZEN_API_KEY = os.environ.get("DUZEN_API_KEY", "")
DUZEN_ENDPOINT = os.environ.get("DUZEN_ENDPOINT", "https://api.duzen.com.tr")

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")


@dataclass
class LabResult:
    patient_tc: str
    test_code: str         # TSH, beta-HCG, vs
    test_name: str
    value: str
    unit: str = ""
    reference_range: str = ""
    flag: str = ""         # H | L | N | critical
    sample_date: str = ""
    report_date: str = ""


@dataclass
class LabFetchResult:
    patient_tc: str
    results: List[LabResult] = field(default_factory=list)
    fetched_at: str = ""
    api_status: str = "unknown"
    agent_version: str = AGENT_VERSION


def _ensure_table(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS lab_results (
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
        )""")
        con.commit()
    finally:
        con.close()


def is_configured() -> bool:
    return bool(DUZEN_API_KEY)


def fetch_results(patient_tc: str, db_path: Optional[str] = None) -> LabFetchResult:
    """Hastanin son lab sonuclarini cek (stub)."""
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)
    res = LabFetchResult(patient_tc=patient_tc,
                          fetched_at=datetime.now().isoformat(timespec="seconds"))
    if not is_configured():
        res.api_status = "stub - DUZEN_API_KEY yok"
        return res

    # Production: requests.get(DUZEN_ENDPOINT + f"/patients/{tc}/results")
    res.api_status = "production call placeholder"
    return res


def upsert_manual(result: LabResult, db_path: Optional[str] = None) -> bool:
    """Manuel girilen lab sonucunu kaydet."""
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)
    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "INSERT INTO lab_results (patient_tc, test_code, test_name, value, unit, "
            "reference_range, flag, sample_date, report_date, source, ingested_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'manual', datetime('now'))",
            (result.patient_tc, result.test_code, result.test_name, result.value,
             result.unit, result.reference_range, result.flag,
             result.sample_date, result.report_date))
        con.commit()
        return True
    finally:
        con.close()


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "configured": is_configured()}


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
