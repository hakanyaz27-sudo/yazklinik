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
                   or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")

PORTAL_SECRET = (os.environ.get("YAZKLINIK_PORTAL_SECRET")
                  or "yazklinik-default-portal-secret-CHANGE-ME")


def _portal_conn(db_path=None):
    # PG-primary aware: routes to PostgreSQL via the adapter when cutover is active,
    # otherwise raw sqlite3 to the main DB. Schema is created in PG on first use.
    import yazklinik_db_adapter as _adapter
    return _adapter.agent_connection("hasta_portal", sqlite_path=db_path or DEFAULT_DB_PATH)


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
    con = _portal_conn(db_path)
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS patient_portal_tokens (
            token TEXT PRIMARY KEY,
            patient_id TEXT NOT NULL,
            phone TEXT,
            issued_at TEXT,
            expires_at TEXT,
            consumed_at TEXT,
            scopes TEXT,
            tc_last4 TEXT,
            birth_year INTEGER,
            revoked_at TEXT,
            last_used_at TEXT,
            use_count INTEGER DEFAULT 0
        )""")
        # Eski sema icin migrate (kolon yoksa ekle)
        for col, type_def in [
            ("tc_last4", "TEXT"), ("birth_year", "INTEGER"),
            ("revoked_at", "TEXT"), ("last_used_at", "TEXT"),
            ("use_count", "INTEGER DEFAULT 0"),
        ]:
            try:
                con.execute(f"ALTER TABLE patient_portal_tokens ADD COLUMN {col} {type_def}")
            except Exception:
                pass  # zaten var
        con.commit()
    finally:
        con.close()


def issue_magic_link(patient_id: str, phone: str,
                     base_url: str = "https://127.0.0.1:5443",
                     ttl_hours: int = 24,
                     share_config: Optional[Dict[str, Any]] = None,
                     tc_last4: str = "",
                     birth_year: Optional[int] = None,
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

    # TC son 4 hane normalize
    tc_last4_clean = "".join(c for c in str(tc_last4 or "") if c.isdigit())[-4:]
    birth_year_int = None
    try:
        if birth_year:
            birth_year_int = int(birth_year)
    except Exception:
        pass

    con = _portal_conn(db_path)
    try:
        con.execute(
            "INSERT INTO patient_portal_tokens "
            "(token, patient_id, phone, issued_at, expires_at, scopes, "
            " tc_last4, birth_year, use_count) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0)",
            (token, patient_id, phone, now.isoformat(timespec="seconds"),
             expires.isoformat(timespec="seconds"), scopes_json,
             tc_last4_clean, birth_year_int))
        con.commit()
    finally:
        con.close()

    link = f"{base_url}/hasta-portal/giris?token={token}&sig={sig}"
    return PortalLoginResult(ok=True, magic_link=link)


def revoke_token(token: str, db_path: Optional[str] = None) -> bool:
    """Doktor token'i iptal eder. Hasta artik link ile giremez."""
    db_path = db_path or DEFAULT_DB_PATH
    con = _portal_conn(db_path)
    try:
        con.execute(
            "UPDATE patient_portal_tokens SET revoked_at = ? WHERE token = ?",
            (datetime.now().isoformat(timespec="seconds"), token))
        con.commit()
        return True
    except Exception:
        return False
    finally:
        con.close()


def delete_revoked_token(token: str, db_path: Optional[str] = None) -> bool:
    """Iptal edilmis tek token kaydini fiziksel olarak sil."""
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)
    con = _portal_conn(db_path)
    try:
        cur = con.execute(
            "DELETE FROM patient_portal_tokens "
            "WHERE token = ? AND COALESCE(revoked_at, '') <> ''",
            (token,))
        con.commit()
        return (cur.rowcount or 0) > 0
    except Exception:
        return False
    finally:
        con.close()


def cleanup_revoked_tokens(db_path: Optional[str] = None) -> int:
    """Iptal edilmis tum token kayitlarini temizle."""
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)
    con = _portal_conn(db_path)
    try:
        cur = con.execute(
            "DELETE FROM patient_portal_tokens "
            "WHERE COALESCE(revoked_at, '') <> ''")
        con.commit()
        return int(cur.rowcount or 0)
    except Exception:
        return 0
    finally:
        con.close()


def verify_tc_birth(token: str, tc_last4: str, birth_year: int,
                     db_path: Optional[str] = None) -> bool:
    """TC son 4 + dogum yili dogrula. Token DB'sindeki ile karsilastir."""
    db_path = db_path or DEFAULT_DB_PATH
    con = _portal_conn(db_path)
    con.row_factory = sqlite3.Row
    try:
        r = con.execute(
            "SELECT tc_last4, birth_year FROM patient_portal_tokens WHERE token = ?",
            (token,)).fetchone()
        if not r:
            return False
        expected_tc = r["tc_last4"] or ""
        expected_birth = r["birth_year"] or 0
        # Eger doktor TC ayarlamadiysa (bos), dogrulama atlanir
        if not expected_tc and not expected_birth:
            return True
        clean_tc = "".join(c for c in str(tc_last4 or "") if c.isdigit())[-4:]
        try:
            clean_birth = int(birth_year)
        except Exception:
            clean_birth = 0
        # Eger sadece TC veya sadece birth ayarlandiysa, sadece o dogrulanir
        if expected_tc and clean_tc != expected_tc:
            return False
        if expected_birth and clean_birth != expected_birth:
            return False
        return True
    finally:
        con.close()


def get_token_scopes(token: str, db_path: Optional[str] = None) -> Dict[str, Any]:
    """Token'in scopes JSON'unu cek. Yoksa {all: True} doner (default).

    Bu fonksiyon HER REQUEST'TE cagrilir - filter etmek icin.
    """
    db_path = db_path or DEFAULT_DB_PATH
    con = _portal_conn(db_path)
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


def verify_token(token: str, db_path: Optional[str] = None,
                  mark_used: bool = True) -> PortalLoginResult:
    """Token dogrula. mark_used=True ise use_count + last_used_at guncel."""
    db_path = db_path or DEFAULT_DB_PATH
    _ensure_table(db_path)
    con = _portal_conn(db_path)
    con.row_factory = sqlite3.Row
    try:
        row = con.execute(
            "SELECT * FROM patient_portal_tokens WHERE token = ?", (token,)).fetchone()
        if not row:
            return PortalLoginResult(ok=False, error="Token bulunamadÄ±")
        # Eski 'consumed_at' kolonu artik kullanilmiyor (tekrar acilabilir)
        # ama eski tokenlar gelirse 'revoked' olarak yorumla
        if row["revoked_at"]:
            return PortalLoginResult(ok=False, error="Bu link iptal edilmiÅŸ")
        try:
            exp = datetime.fromisoformat(row["expires_at"])
            if exp < datetime.now():
                return PortalLoginResult(ok=False, error="Link sÃ¼resi geÃ§ti")
        except Exception:
            return PortalLoginResult(ok=False, error="GeÃ§ersiz tarih")
        # TC dogrulama gerekiyor mu?
        needs_verify = bool(row["tc_last4"] or row["birth_year"])
        # Use count + last_used update
        if mark_used:
            try:
                con.execute(
                    "UPDATE patient_portal_tokens SET "
                    "  last_used_at = ?, use_count = COALESCE(use_count, 0) + 1 "
                    "WHERE token = ?",
                    (datetime.now().isoformat(timespec="seconds"), token))
                con.commit()
            except Exception:
                pass
        sess = PortalSession(
            patient_id=row["patient_id"], patient_name="",
            phone=row["phone"] or "", issued_at=row["issued_at"],
            expires_at=row["expires_at"], token=token,
            scopes=["read"])
        result = PortalLoginResult(ok=True, session=sess)
        # needs_verify bilgisini caller'a iletmek icin error field kullan
        # caller bunu kontrol edip TC formu gosterir
        if needs_verify:
            result.magic_link = "NEEDS_TC_VERIFY"  # signal
        return result
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


def list_my_visits(patient_id: str, db_path: Optional[str] = None,
                    limit: int = 50) -> List[Dict[str, Any]]:
    """Hastanin ziyaret listesi - HASTAYA UYGUN format.

    D700 2026-05-17:
    - KALICI LINK olarak calisir: hasta her giriste SON 50 ziyareti gorur
      (sonradan eklenen ziyaretler otomatik gozukur)
    - SADECE dosyali ziyaretler (image_count>0 OR pdf_count>0)
    - patient_folder_key kolon dogru
    - Ham BK metni temizle
    """
    db_path = db_path or DEFAULT_DB_PATH
    con = _portal_conn(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT visit_key, visit_date, visit_type, examination, control_note, notes, "
            "  clinical_section, source, pdf_count, image_count, full_path "
            "FROM visits "
            "WHERE patient_folder_key = ? AND (archived_at IS NULL OR archived_at = '') "
            "  AND (image_count > 0 OR pdf_count > 0) "
            "ORDER BY visit_date DESC LIMIT ?",
            (patient_id, limit)).fetchall()
        out = []
        for r in rows:
            d = dict(r)
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


def _pick_single_visit_pdf(candidates: List[Dict[str, Any]],
                           visit_date: str = "") -> List[Dict[str, Any]]:
    """Her ziyaret icin tek rapor PDF sec.

    Oncelik:
      1) Dosya adinda visit_date (YYYYMMDD) gecen,
      2) Rapor adina benzeyen (rep/rapor),
      3) Son degisim tarihi en yeni.
    """
    if not candidates:
        return []
    visit_tag = str(visit_date or "").strip().replace("-", "")

    def _score(item: Dict[str, Any]):
        name = str(item.get("name") or "").lower()
        mtime = int(item.get("mtime") or 0)
        digits = "".join(ch for ch in name if ch.isdigit())
        score = 0
        if visit_tag and visit_tag in digits:
            score += 400
        if "_rep_" in name or "rep_" in name or "rapor" in name:
            score += 60
        if name.endswith(".pdf"):
            score += 20
        return (score, mtime)

    best = max(candidates, key=_score)
    return [{
        "name": best.get("name") or "Rapor.pdf",
        "abs_path": best.get("abs_path") or "",
    }]


def list_visit_images(full_path: str, max_imgs: int = 12,
                      patient_id: str = "", visit_key: str = "",
                      visit_date: str = "",
                      db_path: Optional[str] = None) -> Dict[str, Any]:
    """Ziyaret gorselleri + tek rapor PDF.

    D700 2026-05-24:
      - Once DB/files tablosundan visit_key bazli okur (dogru ziyaret eslesmesi)
      - Klasor fallback'da bile PDF listesini TEK rapora indirger.
    """
    out = {"images": [], "videos": [], "pdfs": []}

    # 1) DB tabanli dogru eslesme (visit_key + patient_key)
    try:
        if patient_id and visit_key:
            open_db = db_path or DEFAULT_DB_PATH
            con = _portal_conn(open_db)
            con.row_factory = sqlite3.Row
            try:
                rows = con.execute(
                    "SELECT file_name, full_path, file_kind, mtime "
                    "FROM files "
                    "WHERE patient_folder_key = ? AND visit_key = ? "
                    "  AND (archived_at IS NULL OR archived_at = '') "
                    "ORDER BY COALESCE(mtime, 0) DESC, file_name ASC",
                    (patient_id, visit_key),
                ).fetchall()
            finally:
                con.close()
            pdf_candidates: List[Dict[str, Any]] = []
            for row in rows:
                name = str(row["file_name"] or "").strip()
                path = str(row["full_path"] or "").strip()
                kind = str(row["file_kind"] or "").strip().lower()
                if not name or not path:
                    continue
                low = name.lower()
                if low.endswith((".jpg", ".jpeg", ".png")):
                    if len(out["images"]) < max_imgs:
                        out["images"].append({"name": name, "abs_path": path})
                    continue
                if low.endswith((".mp4", ".mov", ".avi", ".webm", ".m4v")):
                    out["videos"].append({"name": name, "abs_path": path})
                    continue
                if low.endswith(".pdf"):
                    pdf_candidates.append({
                        "name": name,
                        "abs_path": path,
                        "mtime": int(row["mtime"] or 0),
                        "kind": kind,
                    })
            if pdf_candidates:
                out["pdfs"] = _pick_single_visit_pdf(
                    pdf_candidates, visit_date=visit_date)
            if out["images"] or out["videos"] or out["pdfs"]:
                return out
    except Exception:
        pass

    # 2) Klasor fallback (eski davranis) - yine de tek PDF goster
    if not full_path or not os.path.isdir(full_path):
        return out
    try:
        files = sorted(os.listdir(full_path))
        pdf_candidates: List[Dict[str, Any]] = []
        for f in files:
            full = os.path.join(full_path, f)
            if not os.path.isfile(full):
                continue
            low = f.lower()
            if low.endswith((".jpg", ".jpeg", ".png")) and len(out["images"]) < max_imgs:
                out["images"].append({"name": f, "abs_path": full})
            elif low.endswith((".mp4", ".mov", ".avi", ".webm", ".m4v")):
                out["videos"].append({"name": f, "abs_path": full})
            elif low.endswith(".pdf"):
                try:
                    mt = int(os.path.getmtime(full))
                except Exception:
                    mt = 0
                pdf_candidates.append({"name": f, "abs_path": full, "mtime": mt})
        if pdf_candidates:
            out["pdfs"] = _pick_single_visit_pdf(
                pdf_candidates, visit_date=visit_date)
    except Exception:
        pass
    return out


def list_visit_media_map(patient_id: str,
                         visits: List[Dict[str, Any]],
                         max_imgs: int = 12,
                         db_path: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """Ziyaret medya bilgilerini toplu getir (performans).

    Donus:
      {
        "<visit_key>": {"images":[...], "videos":[...], "pdfs":[...]},
        ...
      }
    """
    out: Dict[str, Dict[str, Any]] = {}
    if not patient_id or not visits:
        return out
    visit_keys: List[str] = []
    visit_date_map: Dict[str, str] = {}
    for v in visits:
        vk = str(v.get("visit_key") or "").strip()
        if not vk:
            continue
        if vk not in visit_keys:
            visit_keys.append(vk)
        visit_date_map[vk] = str(v.get("visit_date") or "")
        out[vk] = {"images": [], "videos": [], "pdfs": []}
    if not visit_keys:
        return out
    try:
        open_db = db_path or DEFAULT_DB_PATH
        con = _portal_conn(open_db)
        con.row_factory = sqlite3.Row
        try:
            ph = ",".join(["?"] * len(visit_keys))
            rows = con.execute(
                "SELECT visit_key, file_name, full_path, file_kind, mtime "
                "FROM files "
                f"WHERE patient_folder_key = ? AND visit_key IN ({ph}) "
                "  AND (archived_at IS NULL OR archived_at = '') "
                "ORDER BY COALESCE(mtime, 0) DESC, file_name ASC",
                tuple([patient_id] + visit_keys),
            ).fetchall()
        finally:
            con.close()
        pdf_candidates_map: Dict[str, List[Dict[str, Any]]] = {
            vk: [] for vk in visit_keys
        }
        for row in rows:
            vk = str(row["visit_key"] or "").strip()
            if not vk or vk not in out:
                continue
            name = str(row["file_name"] or "").strip()
            path = str(row["full_path"] or "").strip()
            kind = str(row["file_kind"] or "").strip().lower()
            if not name or not path:
                continue
            low = name.lower()
            bucket = out[vk]
            if low.endswith((".jpg", ".jpeg", ".png")):
                if len(bucket["images"]) < max_imgs:
                    bucket["images"].append({"name": name, "abs_path": path})
                continue
            if low.endswith((".mp4", ".mov", ".avi", ".webm", ".m4v")):
                if len(bucket["videos"]) < 48:
                    bucket["videos"].append({"name": name, "abs_path": path})
                continue
            if low.endswith(".pdf"):
                pdf_candidates_map[vk].append({
                    "name": name,
                    "abs_path": path,
                    "mtime": int(row["mtime"] or 0),
                    "kind": kind,
                })
        for vk in visit_keys:
            cands = pdf_candidates_map.get(vk) or []
            if cands:
                out[vk]["pdfs"] = _pick_single_visit_pdf(
                    cands, visit_date=visit_date_map.get(vk) or "")
    except Exception:
        # Sessiz fallback: caller tekil fonksiyona donebilir.
        pass
    return out


def list_my_pdfs(patient_id: str, db_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Hastanin PDF raporlari (USG, lab vs)."""
    db_path = db_path or DEFAULT_DB_PATH
    con = _portal_conn(db_path)
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
    con = _portal_conn(db_path)
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
    con = _portal_conn(db_path)
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
    con = _portal_conn(db_path)
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

