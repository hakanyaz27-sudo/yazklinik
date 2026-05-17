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
                     share_config: Optional[Dict[str, Any]] = None,
                     db_path: Optional[str] = None) -> PortalLoginResult:
    """Hastaya magic-link uret + paylasim konfigurasyonu.

    share_config (opsiyonel JSON):
        {
            "visits": [visit_key1, visit_key2, ...],  # secilen ziyaretler
            "show_pdfs": True,                          # PDF arsiv goster
            "show_meds": True,                          # ilac listesi goster
            "show_labs": True,                          # lab sonuc goster
            "custom_message": "..."                     # doktor mesaji
        }
    Hicbiri verilmezse: TUM verileri goster (geriye uyumlu).
    """
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)

    token = secrets.token_urlsafe(24)
    now = datetime.now()
    expires = now + timedelta(hours=ttl_hours)
    sig = hmac.new(PORTAL_SECRET.encode(), f"{patient_id}|{token}".encode(),
                    hashlib.sha256).hexdigest()[:16]

    # scopes JSON (eski "read" string yerine yapilandirilmis config)
    if share_config and isinstance(share_config, dict):
        scopes_json = json.dumps(share_config, ensure_ascii=False)
    else:
        scopes_json = json.dumps({"all": True}, ensure_ascii=False)

    con = sqlite3.connect(db_path)
    try:
        con.execute(
            "INSERT INTO patient_portal_tokens "
            "(token, patient_id, phone, issued_at, expires_at, scopes) VALUES (?, ?, ?, ?, ?, ?)",
            (token, patient_id, phone, now.isoformat(timespec="seconds"),
             expires.isoformat(timespec="seconds"), scopes_json))
        con.commit()
    finally:
        con.close()

    link = f"{base_url}/hasta-portal/giris?token={token}&sig={sig}"
    return PortalLoginResult(ok=True, magic_link=link)


def get_token_scopes(token: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Token'in scopes JSON'unu cek. Yoksa {all: True} doner (default).

    Bu fonksiyon HER REQUEST'TE cagrilir - filter etmek icin.
    """
    db_path = db_path or DEFAULT_DB_PATH
    con = sqlite3.connect(db_path)
    try:
        r = con.execute(
            "SELECT scopes FROM patient_portal_tokens WHERE token = ?",
            (token,)).fetchone()
        if r and r[0]:
            try:
                d = json.loads(r[0])
                if isinstance(d, dict):
                    return d
            except Exception:
                pass
    finally:
        con.close()
    return {"all": True}


def verify_token(token: str, db_path: Optional[str] = None) -> PortalLoginResult:
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT * FROM patient_portal_tokens WHERE token = ?", (token,)).fetchone()
        if not row:
            return PortalLoginResult(ok=False, error="Token bulunamadı")
        if row["consumed_at"]:
            return PortalLoginResult(ok=False, error="Token zaten kullanıldı")
        try:
            exp = datetime.fromisoformat(row["expires_at"])
            if exp < datetime.now():
                return PortalLoginResult(ok=False, error="Token süresi geçti")
        except Exception:
            return PortalLoginResult(ok=False, error="Geçersiz tarih formatı")
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


def _sanitize_text_for_patient(t: str) -> str:
    """Doktorun ham notunu hastaya UYGUN hale getir.
    - BulutKlinik raw format ('Hasta: ... Sikayet/oyku:') KALDIR
    - Protokol no, kod kaldir
    - 200 char limit
    """
    if not t:
        return ""
    import re
    t = str(t)
    # 'BulutKlinik [tip] kaydi <hash> Hasta: <ad>' kaldir
    t = re.sub(r"^BulutKlinik\s+\w+\s+(kaydi|protokolu|protokol\s*#?\d+)\s+\w*\s*Hasta:\s*[^\n]+?\s*-\s*",
                "", t, flags=re.I)
    t = re.sub(r"BulutKlinik\s+(obstetri\s+takip|protokol)\s+\w+\s+Hasta:\s*[^\n]+?\s*",
                "", t, flags=re.I)
    t = re.sub(r"Protokol\s+tipi:\s*[^\s]+\s*", "", t, flags=re.I)
    t = re.sub(r"Brans:\s*[A-Z\s]+(?=Doktor|Medikal|$)", "", t, flags=re.I)
    t = re.sub(r"Doktor:\s*[A-Z\s]+(?=Medikal|Tani|$)", "", t, flags=re.I)
    t = re.sub(r"Tarih:\s*\d{4}-\d{2}-\d{2}\s*[\d:]*\s*", "", t)
    t = re.sub(r"Tani\s*kodlari:\s*\w+\s*", "", t, flags=re.I)
    t = re.sub(r"Medikal\s+bilgiler\s*-?\s*", "", t, flags=re.I)
    t = re.sub(r"Takip\s+no:\s*\d+", "", t, flags=re.I)
    # Cifte bosluklari temizle
    t = re.sub(r"\s+", " ", t).strip()
    return t[:240]


def list_my_visits(patient_id: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Hastanin ziyaret listesi - HASTAYA UYGUN format.

    D300 2026-05-17:
    - patient_folder_key
    - USG klasoru olanlari oncelikle goster (gercek ziyaret)
    - Ham BK metni temizle
    - LIMIT 5 (en son 5 - cok eski ziyaret hastayi yormaz)
    - Klasor yoksa (BK protokol-only) baska sectiona
    """
    db_path = db_path or DEFAULT_DB_PATH
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT visit_date, visit_type, examination, control_note, notes, "
            "  clinical_section, source, pdf_count, image_count, full_path "
            "FROM visits "
            "WHERE patient_folder_key = ? AND (archived_at IS NULL OR archived_at = '') "
            "  AND (image_count > 0 OR pdf_count > 0) "  # SADECE dosyali ziyaretler
            "ORDER BY visit_date DESC LIMIT 5",
            (patient_id,)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            # Hastaya gosterilen metin - sade
            ex = _sanitize_text_for_patient(d.get("examination") or "")
            cn = _sanitize_text_for_patient(d.get("control_note") or "")
            no = _sanitize_text_for_patient(d.get("notes") or "")
            d["examination_clean"] = ex
            d["control_note_clean"] = cn
            d["notes_clean"] = no
            out.append(d)
        return out
    except Exception:
        return []
    finally:
        con.close()


def list_visit_images(full_path: str, max_imgs: int = 12) -> List[Dict[str, Any]]:
    """Ziyaret klasorundeki USG resimleri (jpg/png) + PDF'ler."""
    out = {"images": [], "pdfs": []}
    if not full_path or not os.path.isdir(full_path):
        return out
    try:
        files = sorted(os.listdir(full_path))
        for f in files:
            full = os.path.join(full_path, f)
            if not os.path.isfile(full):
                continue
            low = f.lower()
            if low.endswith((".jpg", ".jpeg", ".png")) and len(out["images"]) < max_imgs:
                out["images"].append({"name": f, "abs_path": full})
            elif low.endswith(".pdf"):
                out["pdfs"].append({"name": f, "abs_path": full})
    except Exception:
        pass
    return out


def list_my_pdfs(patient_id: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Hastanin PDF raporlari (USG, lab vs)."""
    db_path = db_path or DEFAULT_DB_PATH
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT file_name, report_type, created_at, source, rel_path "
            "FROM patient_pdf_archive "
            "WHERE patient_key = ? AND deleted_at IS NULL "
            "ORDER BY created_at DESC LIMIT 20",
            (patient_id,)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        con.close()


def list_my_meds(patient_id: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Hastanin aktif ilac listesi."""
    db_path = db_path or DEFAULT_DB_PATH
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT drug_name, dose, frequency, indication, start_date "
            "FROM patient_medications "
            "WHERE patient_key = ? AND COALESCE(active, 1) = 1 "
            "ORDER BY start_date DESC LIMIT 20",
            (patient_id,)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        con.close()


def list_my_labs(patient_id: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Hastanin lab sonuclari.

    patient_id (folder_key) -> TC ile match veya patient_tc kolonu ile."""
    db_path = db_path or DEFAULT_DB_PATH
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    out = []
    try:
        # Ust olarak patient TC al
        tc = ""
        try:
            r = con.execute(
                "SELECT tc_no FROM patient_demographics WHERE patient_key = ?",
                (patient_id,)).fetchone()
            tc = (r[0] if r else "") or ""
        except Exception:
            pass
        # lab_results: patient_tc + patient_key her ikisinde de bak
        for col in ("patient_tc", "patient_id", "patient_key"):
            try:
                rows = con.execute(
                    f"SELECT test_code, test_name, value, unit, reference_range, "
                    f"  flag, sample_date, report_date, source "
                    f"FROM lab_results WHERE {col} IN (?, ?) "
                    f"ORDER BY COALESCE(report_date, sample_date) DESC LIMIT 50",
                    (patient_id, tc)).fetchall()
                if rows:
                    out = [dict(r) for r in rows]
                    break
            except Exception:
                continue
    finally:
        con.close()
    return out


def list_visit_summaries(patient_id: str, db_path: Optional[str] = None,
                          limit: int = 15) -> List[Dict[str, Any]]:
    """Doktor SELECTOR icin - tum ziyaretlerin kisa ozeti (checkbox).

    list_my_visits ile farkli: secim icin TUM ziyaretler (dosyali olsun olmasin),
    daha cok ziyaret (15) sade key + tarih + tip.
    """
    db_path = db_path or DEFAULT_DB_PATH
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT visit_key, visit_date, visit_type, full_path, "
            "  pdf_count, image_count, source "
            "FROM visits "
            "WHERE patient_folder_key = ? AND (archived_at IS NULL OR archived_at = '') "
            "ORDER BY visit_date DESC LIMIT ?",
            (patient_id, limit)).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        con.close()


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION}


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
