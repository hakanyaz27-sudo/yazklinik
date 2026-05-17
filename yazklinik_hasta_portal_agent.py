"""Hasta Self-Service Portal Agent.

Hasta kendi telefon + dogum tarihi ile login olur:
    - Randevularini gorur
    - Recetelerini PDF indirir
    - Lab sonuclarini gorur
    - USG raporlarini gorur (sadece imzalanmis)
    - Yeni randevu talebi acar
    - Mesaj yazar (klinige)

Magic-link token: 24 saatlik tek kullanimlik link.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-hasta-portal"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")

PORTAL_SECRET = (os.environ.get("YAZKLINIK_PORTAL_SECRET")
                  or "yazklinik-default-portal-secret-CHANGE-ME")


@dataclass
class PortalSession:
    patient_id: str
    patient_name: str
    phone: str
    issued_at: str
    expires_at: str
    token: str
    scopes: List[str] = field(default_factory=lambda: ["read"])


@dataclass
class PortalLoginResult:
    ok: bool
    session: Optional[PortalSession] = None
    error: str = ""
    magic_link: str = ""
    agent_version: str = AGENT_VERSION


def _ensure_table(db_path: str) -> None:
    con = sqlite3.connect(db_path)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS patient_portal_tokens (
            token TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            phone TEXT,
            issued_at TEXT,
            expires_at TEXT,
            consumed_at TEXT,
            scopes TEXT
        )""")
        con.commit()
    finally:
        con.close()


def issue_magic_link(patient_id: str, phone: str,
                     base_url: str = "https://127.0.0.1:5443",
                     ttl_hours: int = 24,
                     db_path: Optional[str] = None) -> PortalLoginResult:
    """Hastaya 24s gecerli magic-link uret. Sonra WhatsApp ile yollanir."""
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)

    token = secrets.token_urlsafe(24)
    now = datetime.now()
    expires = now + timedelta(hours=ttl_hours)
    sig = hmac.new(PORTAL_SECRET.encode(), f"{patient_id}|{token}".encode(),
                    hashlib.sha256).hexdigest()[:16]

    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "INSERT INTO patient_portal_tokens "
            "(token, patient_id, phone, issued_at, expires_at, scopes) VALUES (?, ?, ?, ?, ?, ?)",
            (token, patient_id, phone, now.isoformat(timespec="seconds"),
             expires.isoformat(timespec="seconds"), "read"))
        con.commit()
    finally:
        con.close()

    link = f"{base_url}/hasta-portal/giris?token={token}&sig={sig}"
    return PortalLoginResult(ok=True, magic_link=link)


def verify_token(token: str, db_path: Optional[str] = None) -> PortalLoginResult:
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT * FROM patient_portal_tokens WHERE token = ?", (token,)).fetchone()
        if not row:
            return PortalLoginResult(ok=False, error="token bulunamadi")
        if row["consumed_at"]:
            return PortalLoginResult(ok=False, error="token kullanildi")
        try:
            exp = datetime.fromisoformat(row["expires_at"])
            if exp < datetime.now():
                return PortalLoginResult(ok=False, error="token suresi gecti")
        except Exception:
            return PortalLoginResult(ok=False, error="gecersiz expires_at")
        con.execute("UPDATE patient_portal_tokens SET consumed_at = ? WHERE token = ?",
                    (datetime.now().isoformat(timespec="seconds"), token))
        con.commit()
        sess = PortalSession(
            patient_id=row["patient_id"], patient_name="",
            phone=row["phone"] or "", issued_at=row["issued_at"],
            expires_at=row["expires_at"], token=token,
            scopes=(row["scopes"] or "read").split(","))
        return PortalLoginResult(ok=True, session=sess)
    finally:
        con.close()


def list_my_visits(patient_id: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    db_path = db_path or DEFAULT_DB_PATH
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT visit_date, visit_type, complaints, diagnosis "
            "FROM visits WHERE patient_id = ? ORDER BY visit_date DESC LIMIT 20",
            (patient_id,)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        con.close()


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION}


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
