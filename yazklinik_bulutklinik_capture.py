"""BulutKlinik smart capture helpers.

BulutKlinik import rows should not fall into one mixed note. This module
classifies incoming BK data into YazKlinik clinical buckets and writes them to
matching tables with idempotent source markers.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


AGENT_VERSION = "2026.05.19-bk-smart-capture"

SECTION_LABELS = {
    "hikaye": "Hikaye",
    "sikayetler": "Sikayet",
    "muayene_bulgulari": "Muayene bulgulari",
    "notlar": "Notlar",
    "tanilar": "Tanilar",
    "tetkikler": "Tetkikler",
    "ilaclar": "Ilaclar",
    "oneriler": "Oneriler",
    "tedavi_planlari": "Tedavi planlari",
    "gebelik_haftalari": "Gebelik haftasi",
}


def _norm_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _long_text(value: Any) -> str:
    return str(value or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def _table_exists(con, table: str) -> bool:
    row = con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,),
    ).fetchone()
    return bool(row)


def _columns(con, table: str) -> set:
    try:
        return {str(r[1]) for r in con.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def _rows(con, sql: str, params: Iterable[Any] = ()) -> List[Dict[str, Any]]:
    cur = con.execute(sql, tuple(params))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _parse_date(value: Any) -> str:
    raw = _norm_text(value)
    if not raw:
        return ""
    raw = raw.split("T", 1)[0].split(" ", 1)[0]
    for fmt in (
        "%Y-%m-%d", "%d.%m.%Y", "%d/%m/%Y", "%d-%m-%Y",
        "%Y/%m/%d", "%d.%m.%y", "%d/%m/%y",
    ):
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except Exception:
            pass
    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", raw)
    if m:
        day, month, year = m.groups()
        year = ("20" + year) if len(year) == 2 else year
        try:
            return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
        except Exception:
            return ""
    return ""


def _date_or_now(value: Any) -> str:
    return _parse_date(value) or datetime.now().strftime("%Y-%m-%d")


def _parse_ga(value: Any) -> Tuple[Optional[int], Optional[int]]:
    text = _norm_text(value).lower()
    if not text:
        return None, None
    for pattern in (
        r"\b(\d{1,2})\s*\+\s*(\d)\b",
        r"\b(\d{1,2})\s*(?:hf|hafta|week|w)\s*(\d)?\b",
    ):
        m = re.search(pattern, text)
        if not m:
            continue
        weeks = int(m.group(1))
        days = int(m.group(2) or 0)
        if 3 <= weeks <= 45 and 0 <= days <= 6:
            return weeks, days
    return None, None


def _ga_from_lmp(lmp: str, at_date: str) -> Tuple[Optional[int], Optional[int]]:
    lmp_iso = _parse_date(lmp)
    at_iso = _parse_date(at_date) or datetime.now().strftime("%Y-%m-%d")
    if not lmp_iso:
        return None, None
    try:
        days = (
            datetime.strptime(at_iso, "%Y-%m-%d")
            - datetime.strptime(lmp_iso, "%Y-%m-%d")
        ).days
    except Exception:
        return None, None
    if days < 0 or days > 330:
        return None, None
    return days // 7, days % 7


def _split_lines(value: Any) -> List[str]:
    text = _long_text(value)
    if not text:
        return []
    parts = re.split(r"(?:\n+|;\s+|\s+\|\s+)", text)
    return [_norm_text(p) for p in parts if _norm_text(p)]


def _new_capture(bk_no: str) -> Dict[str, Any]:
    return {
        "ok": True,
        "agent_version": AGENT_VERSION,
        "bk_hasta_no": str(bk_no or "").strip(),
        "linked_patient_key": "",
        "demographics": {},
        "sections": {key: [] for key in SECTION_LABELS},
        "counts": {},
    }


def _add(
    capture: Dict[str, Any],
    section: str,
    text: Any,
    source_id: str,
    date: Any = "",
    title: str = "",
    meta: Optional[dict] = None,
) -> None:
    value = _long_text(text)
    if not value:
        return
    item = {
        "section": section,
        "label": SECTION_LABELS.get(section, section),
        "title": _norm_text(title),
        "text": value,
        "date": _date_or_now(date),
        "source_id": _norm_text(source_id)[:180],
        "meta": dict(meta or {}),
    }
    bucket = capture["sections"].setdefault(section, [])
    sig = (section, item["date"], item["source_id"], _norm_text(value).lower()[:240])
    for existing in bucket:
        old_sig = (
            section,
            existing.get("date"),
            existing.get("source_id"),
            _norm_text(existing.get("text")).lower()[:240],
        )
        if old_sig == sig:
            return
    bucket.append(item)


def _set_demo(capture: Dict[str, Any], key: str, value: Any) -> None:
    text = _norm_text(value)
    if text:
        capture["demographics"][key] = text


def build_capture_payload(con, bk_no: str) -> Dict[str, Any]:
    """Read BulutKlinik mirror tables and classify records by clinical purpose."""
    bk_no = str(bk_no or "").strip()
    capture = _new_capture(bk_no)
    if not bk_no:
        capture["ok"] = False
        capture["error"] = "bk_hasta_no gerekli"
        return capture

    if _table_exists(con, "bk_voluson_links"):
        rows = _rows(
            con,
            "SELECT folder_key FROM bk_voluson_links WHERE bk_hasta_no=? LIMIT 1",
            (bk_no,),
        )
        if rows:
            capture["linked_patient_key"] = _norm_text(rows[0].get("folder_key"))

    if _table_exists(con, "bk_patients"):
        rows = _rows(con, "SELECT * FROM bk_patients WHERE bk_hasta_no=? LIMIT 1", (bk_no,))
        if rows:
            p = rows[0]
            full_name = _norm_text((p.get("ad") or "") + " " + (p.get("soyad") or ""))
            _set_demo(capture, "canonical_name", full_name)
            _set_demo(capture, "tc_no", p.get("tc_kimlik"))
            _set_demo(capture, "phone", p.get("telefon"))
            _set_demo(capture, "birth_date", _parse_date(p.get("dogum_tarihi")))
            _set_demo(capture, "allergies", p.get("alerjiler"))
            _set_demo(capture, "chronic_conditions", p.get("ozgecmis"))
            _add(capture, "hikaye", p.get("ozgecmis"), f"bk_patient:{bk_no}:ozgecmis", p.get("gelis_tarihi"), "Ozgecmis")
            _add(capture, "hikaye", p.get("soygecmis"), f"bk_patient:{bk_no}:soygecmis", p.get("gelis_tarihi"), "Soygecmis")
            _add(capture, "sikayetler", p.get("gelis_nedeni"), f"bk_patient:{bk_no}:gelis_nedeni", p.get("gelis_tarihi"), "Gelis nedeni")
            _add(capture, "notlar", p.get("not_text"), f"bk_patient:{bk_no}:not", p.get("gelis_tarihi"), "Hasta notu")

    if _table_exists(con, "bk_medical_infos"):
        for r in _rows(con, "SELECT * FROM bk_medical_infos WHERE bk_hasta_no=? ORDER BY protokol_tarihi DESC", (bk_no,)):
            pno = _norm_text(r.get("protokol_no")) or "no-protocol"
            date = r.get("protokol_tarihi")
            _add(capture, "hikaye", r.get("hikayesi"), f"bk_medical:{pno}:hikaye", date, "Hikaye")
            _add(capture, "sikayetler", r.get("sikayeti"), f"bk_medical:{pno}:sikayet", date, "Sikayet")
            _add(capture, "hikaye", r.get("ozgecmis"), f"bk_medical:{pno}:ozgecmis", date, "Ozgecmis")
            _add(capture, "hikaye", r.get("soygecmis"), f"bk_medical:{pno}:soygecmis", date, "Soygecmis")
            _add(capture, "muayene_bulgulari", r.get("bulgular"), f"bk_medical:{pno}:bulgular", date, "Bulgular")
            _add(capture, "tedavi_planlari", r.get("uygulamalar"), f"bk_medical:{pno}:uygulamalar", date, "Uygulamalar")
            _add(capture, "oneriler", r.get("oneriler"), f"bk_medical:{pno}:oneriler", date, "Oneriler")
            _add(capture, "notlar", r.get("notlar"), f"bk_medical:{pno}:notlar", date, "Notlar")
            _add(capture, "tanilar", r.get("tani_kodlari"), f"bk_medical:{pno}:tani", date, "Tani kodlari")

    if _table_exists(con, "bk_protocols"):
        for r in _rows(con, "SELECT * FROM bk_protocols WHERE bk_hasta_no=? ORDER BY protokol_tarihi DESC", (bk_no,)):
            pno = _norm_text(r.get("protokol_no")) or "no-protocol"
            _add(capture, "sikayetler", r.get("gelis_nedeni"), f"bk_protocol:{pno}:gelis_nedeni", r.get("protokol_tarihi"), "Protokol gelis nedeni")

    if _table_exists(con, "bk_gynecology_resume"):
        for r in _rows(con, "SELECT * FROM bk_gynecology_resume WHERE bk_hasta_no=? ORDER BY tarih DESC", (bk_no,)):
            rid = _norm_text(r.get("row_hash") or r.get("resume_no") or r.get("protokol_no"))
            date = r.get("tarih")
            lmp = _parse_date(r.get("son_adet_tarihi"))
            if lmp:
                _set_demo(capture, "lmp_override", lmp)
                weeks, days = _ga_from_lmp(lmp, date)
                if weeks is not None:
                    _add(
                        capture,
                        "gebelik_haftalari",
                        f"{weeks}+{days} (SAT: {lmp})",
                        f"bk_gyn_resume:{rid}:ga",
                        date,
                        "Gebelik haftasi",
                        {"ga_weeks": weeks, "ga_days": days, "lmp": lmp},
                    )
            _add(capture, "hikaye", r.get("sikayet_oyku"), f"bk_gyn_resume:{rid}:oyku", date, "Sikayet/oyku")
            _add(capture, "muayene_bulgulari", r.get("bulgular"), f"bk_gyn_resume:{rid}:bulgular", date, "Jinekolojik bulgular")
            _add(capture, "notlar", r.get("notlar"), f"bk_gyn_resume:{rid}:notlar", date, "Jinekoloji notlari")
            _add(capture, "tanilar", r.get("tani"), f"bk_gyn_resume:{rid}:tani", date, "Jinekoloji tani")
            _add(capture, "tedavi_planlari", r.get("tedavi_plani"), f"bk_gyn_resume:{rid}:tedavi", date, "Tedavi plani")
            for med in _split_lines(r.get("recete")):
                _add(capture, "ilaclar", med, f"bk_gyn_resume:{rid}:recete:{med[:40]}", date, "Recete")
            _add(capture, "oneriler", r.get("sonuc"), f"bk_gyn_resume:{rid}:sonuc", date, "Sonuc/Oneri")

    if _table_exists(con, "bk_gynecology_tracking"):
        for r in _rows(con, "SELECT * FROM bk_gynecology_tracking WHERE bk_hasta_no=? ORDER BY tarih DESC", (bk_no,)):
            rid = _norm_text(r.get("row_hash") or r.get("takip_no"))
            date = r.get("tarih")
            weeks, days = _parse_ga(r.get("usg_age"))
            if weeks is not None:
                _add(capture, "gebelik_haftalari", f"{weeks}+{days}", f"bk_gyn_tracking:{rid}:ga", date, "USG gebelik haftasi", {"ga_weeks": weeks, "ga_days": days})
            usg_bits = []
            for key, label in (("efw", "EFW"), ("amnion", "Amnion"), ("plasenta", "Plasenta"), ("serviks", "Serviks")):
                if _norm_text(r.get(key)):
                    usg_bits.append(f"{label}: {_norm_text(r.get(key))}")
            if usg_bits:
                _add(capture, "muayene_bulgulari", "\n".join(usg_bits), f"bk_gyn_tracking:{rid}:usg", date, "USG bulgulari")
            lab_bits = []
            for key, label in (("hb", "Hb"), ("hct", "Hct"), ("mcv", "MCV"), ("plt", "PLT"), ("tit", "TIT"), ("diger", "Diger")):
                if _norm_text(r.get(key)):
                    lab_bits.append(f"{label}: {_norm_text(r.get(key))}")
            if lab_bits:
                _add(capture, "tetkikler", "\n".join(lab_bits), f"bk_gyn_tracking:{rid}:tetkik", date, "Takip tetkikleri")
            obs_bits = []
            for key, label in (("kilo", "Kilo"), ("ta", "TA"), ("sikayet", "Sikayet")):
                if _norm_text(r.get(key)):
                    obs_bits.append(f"{label}: {_norm_text(r.get(key))}")
            if obs_bits:
                _add(capture, "notlar", "\n".join(obs_bits), f"bk_gyn_tracking:{rid}:not", date, "Takip notu")

    if _table_exists(con, "bk_services"):
        for r in _rows(con, "SELECT * FROM bk_services WHERE bk_hasta_no=? ORDER BY islem_tarihi DESC", (bk_no,)):
            rid = _norm_text(r.get("row_hash") or r.get("hizmet_no"))
            name = _norm_text(r.get("hizmet_adi"))
            if not name:
                continue
            detail = name
            if _norm_text(r.get("grup_adi")):
                detail += f" ({_norm_text(r.get('grup_adi'))})"
            _add(capture, "tetkikler", detail, f"bk_service:{rid}", r.get("islem_tarihi"), "Hizmet/Tetkik")

    capture["counts"] = {k: len(v) for k, v in capture["sections"].items()}
    return capture


def _ensure_write_schema(con) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS lab_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_key TEXT,
            pdf_path TEXT,
            source TEXT,
            test_date TEXT,
            uploaded_at TEXT,
            extracted_json TEXT,
            raw_text TEXT,
            notes TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_key TEXT,
            medications TEXT,
            diagnosis TEXT,
            notes TEXT,
            created_by TEXT,
            created_at TEXT
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            patient_folder_key TEXT,
            visit_key TEXT,
            full_path TEXT,
            visit_date TEXT,
            first_seen_at TEXT,
            last_synced_at TEXT,
            visit_type TEXT,
            notes TEXT,
            examination TEXT,
            control_note TEXT,
            source TEXT,
            clinical_section TEXT,
            created_at TEXT
        )
    """)
    for column, ddl in (
        ("visit_key", "ALTER TABLE visits ADD COLUMN visit_key TEXT"),
        ("full_path", "ALTER TABLE visits ADD COLUMN full_path TEXT"),
        ("first_seen_at", "ALTER TABLE visits ADD COLUMN first_seen_at TEXT"),
        ("last_synced_at", "ALTER TABLE visits ADD COLUMN last_synced_at TEXT"),
        ("visit_type", "ALTER TABLE visits ADD COLUMN visit_type TEXT"),
        ("clinical_section", "ALTER TABLE visits ADD COLUMN clinical_section TEXT"),
        ("control_note", "ALTER TABLE visits ADD COLUMN control_note TEXT"),
    ):
        if column not in _columns(con, "visits"):
            try:
                con.execute(ddl)
            except Exception:
                pass
    con.execute("""
        CREATE TABLE IF NOT EXISTS usg_measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_key TEXT NOT NULL,
            usg_date TEXT NOT NULL,
            ga_weeks INTEGER,
            ga_days INTEGER,
            notes TEXT,
            created_by TEXT,
            created_at TEXT
        )
    """)
    for column, ddl in (
        ("source_type", "ALTER TABLE usg_measurements ADD COLUMN source_type TEXT"),
        ("source_study_id", "ALTER TABLE usg_measurements ADD COLUMN source_study_id TEXT"),
    ):
        if column not in _columns(con, "usg_measurements"):
            try:
                con.execute(ddl)
            except Exception:
                pass


def _source(item: Dict[str, Any], prefix: str = "bulutklinik_capture") -> str:
    return f"{prefix}:{_norm_text(item.get('section'))}:{_norm_text(item.get('source_id'))}"[:240]


def _insert_visit(con, patient_key: str, item: Dict[str, Any], dry_run: bool = False) -> bool:
    source = _source(item)
    row = con.execute(
        "SELECT 1 FROM visits WHERE patient_folder_key=? AND source=? LIMIT 1",
        (patient_key, source),
    ).fetchone()
    if row:
        return False
    section = item.get("section")
    text = _long_text(item.get("text"))
    title = _norm_text(item.get("title") or item.get("label"))
    notes = examination = control_note = ""
    if section in {"hikaye", "notlar"}:
        notes = f"{title}\n{text}".strip()
    elif section in {"sikayetler", "muayene_bulgulari"}:
        examination = f"{title}\n{text}".strip()
    elif section in {"oneriler", "tedavi_planlari"}:
        control_note = f"{title}\n{text}".strip()
    else:
        notes = f"{title}\n{text}".strip()
    if dry_run:
        return True
    visit_date = item.get("date") or datetime.now().strftime("%Y-%m-%d")
    created_at = datetime.now().isoformat(sep=" ", timespec="seconds")
    visit_cols = set(_columns(con, "visits") or [])
    required_visit_cols = {
        "patient_folder_key",
        "visit_key",
        "full_path",
        "visit_date",
        "first_seen_at",
        "last_synced_at",
        "visit_type",
        "notes",
        "examination",
        "control_note",
        "source",
        "clinical_section",
        "created_at",
    }
    if not visit_cols:
        visit_cols = set(required_visit_cols)
    else:
        # D700'de bu alanlar zorunlu; PRAGMA gecici/eksik donerse de INSERT
        # tarafinda NOT NULL hatasina dusmemek icin cekirdek kolonlari garanti et.
        visit_cols |= required_visit_cols
    values = {
        "patient_folder_key": patient_key,
        "visit_date": visit_date,
        "notes": notes,
        "examination": examination,
        "control_note": control_note,
        "source": source,
        "clinical_section": section,
        "created_at": created_at,
    }
    # Ana D700 schema'sinda visits.visit_key NOT NULL. Smart-capture insertleri
    # de uyumlu anahtar ureterek yazilsin.
    if "visit_key" in visit_cols:
        date_token = str(visit_date).replace("-", "")[:8] or datetime.now().strftime("%Y%m%d")
        src_seed = f"{patient_key}_{source}"[-96:]
        src_safe = "".join(ch if ch.isalnum() else "_" for ch in src_seed).strip("_")
        if not src_safe:
            src_safe = "bk"
        values["visit_key"] = f"BKCAP_{date_token}_{src_safe}"[:180]
    if "full_path" in visit_cols and "full_path" not in values:
        values["full_path"] = ""
    # D700 ana schema uyumu: visits.first_seen_at ve visits.last_synced_at
    # alanlari NOT NULL olabilir. Smart-capture insertleri bu alanlari da
    # doldurmazsa INSERT 500'e duser.
    if "first_seen_at" in visit_cols and not values.get("first_seen_at"):
        values["first_seen_at"] = created_at
    if "last_synced_at" in visit_cols and not values.get("last_synced_at"):
        values["last_synced_at"] = created_at
    if "visit_type" in visit_cols and not values.get("visit_type"):
        values["visit_type"] = "muayene"
    insert_cols = [c for c in (
        "patient_folder_key",
        "visit_key",
        "full_path",
        "visit_date",
        "first_seen_at",
        "last_synced_at",
        "visit_type",
        "notes",
        "examination",
        "control_note",
        "source",
        "clinical_section",
        "created_at",
    ) if c in visit_cols]
    if not insert_cols:
        insert_cols = [
            "patient_folder_key",
            "visit_key",
            "full_path",
            "visit_date",
            "first_seen_at",
            "last_synced_at",
            "visit_type",
            "notes",
            "examination",
            "control_note",
            "source",
            "clinical_section",
            "created_at",
        ]
    con.execute(
        f"INSERT INTO visits({', '.join(insert_cols)}) VALUES({', '.join('?' for _ in insert_cols)})",
        [values.get(c) for c in insert_cols],
    )
    return True


def _insert_prescription(con, patient_key: str, item: Dict[str, Any], kind: str, user: str, dry_run: bool = False) -> bool:
    marker = _source(item)
    row = con.execute(
        "SELECT 1 FROM prescriptions WHERE patient_key=? AND notes LIKE ? LIMIT 1",
        (patient_key, f"%{marker}%"),
    ).fetchone()
    if row:
        return False
    medications = item.get("text") if kind == "ilaclar" else ""
    diagnosis = item.get("text") if kind == "tanilar" else ""
    if dry_run:
        return True
    cols = _columns(con, "prescriptions")
    base = {
        "patient_key": patient_key,
        "medications": medications,
        "diagnosis": diagnosis,
        "notes": f"BulutKlinik smart capture\n{marker}",
        "created_by": user or "system",
        "created_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
    }
    if "template_name" in cols:
        base["template_name"] = "BulutKlinik smart capture"
    if "purpose" in cols:
        base["purpose"] = "BulutKlinik smart capture"
    insert_cols = [c for c in base if c in cols]
    con.execute(
        f"INSERT INTO prescriptions({', '.join(insert_cols)}) VALUES({', '.join('?' for _ in insert_cols)})",
        [base[c] for c in insert_cols],
    )
    return True


def _insert_lab(con, patient_key: str, item: Dict[str, Any], dry_run: bool = False) -> bool:
    marker = _source(item)
    row = con.execute(
        "SELECT 1 FROM lab_results WHERE patient_key=? AND source=? AND notes LIKE ? LIMIT 1",
        (patient_key, "BulutKlinik smart capture", f"%{marker}%"),
    ).fetchone()
    if row:
        return False
    if dry_run:
        return True
    values = {
        item.get("title") or "BulutKlinik tetkik": {
            "value": item.get("text"),
            "date": item.get("date"),
            "source": marker,
        }
    }
    con.execute(
        "INSERT INTO lab_results(patient_key, pdf_path, source, test_date, uploaded_at, extracted_json, raw_text, notes) "
        "VALUES(?,?,?,?,?,?,?,?)",
        (
            patient_key,
            "",
            "BulutKlinik smart capture",
            item.get("date") or datetime.now().strftime("%Y-%m-%d"),
            datetime.now().isoformat(sep=" ", timespec="seconds"),
            json.dumps(values, ensure_ascii=False),
            item.get("text") or "",
            f"BulutKlinik smart capture\n{marker}",
        ),
    )
    return True


def _insert_ga(con, patient_key: str, item: Dict[str, Any], user: str, dry_run: bool = False) -> bool:
    meta = dict(item.get("meta") or {})
    weeks = meta.get("ga_weeks")
    days = meta.get("ga_days")
    if weeks is None:
        weeks, days = _parse_ga(item.get("text"))
    if weeks is None:
        return False
    marker = _source(item)
    row = con.execute(
        "SELECT 1 FROM usg_measurements WHERE patient_key=? AND source_type=? AND source_study_id=? LIMIT 1",
        (patient_key, "bulutklinik_capture", marker),
    ).fetchone()
    if row:
        return False
    if dry_run:
        return True
    con.execute(
        "INSERT INTO usg_measurements(patient_key, usg_date, ga_weeks, ga_days, notes, created_by, created_at, source_type, source_study_id) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (
            patient_key,
            item.get("date") or datetime.now().strftime("%Y-%m-%d"),
            int(weeks),
            int(days or 0),
            f"BulutKlinik gebelik haftasi: {item.get('text')}\n{marker}",
            user or "system",
            datetime.now().isoformat(sep=" ", timespec="seconds"),
            "bulutklinik_capture",
            marker,
        ),
    )
    return True


def apply_capture_payload(con, patient_key: str, capture: Dict[str, Any], user: str = "system", dry_run: bool = False) -> Dict[str, Any]:
    """Write classified capture to matching tables. Idempotent by source marker."""
    patient_key = _norm_text(patient_key)
    if not patient_key:
        return {"ok": False, "error": "patient_key gerekli"}
    _ensure_write_schema(con)
    summary = {
        "ok": True,
        "dry_run": bool(dry_run),
        "patient_key": patient_key,
        "inserted": {key: 0 for key in SECTION_LABELS},
        "skipped_duplicates": 0,
    }
    sections = capture.get("sections") or {}
    for section in ("hikaye", "sikayetler", "muayene_bulgulari", "notlar", "oneriler", "tedavi_planlari"):
        for item in sections.get(section) or []:
            item = dict(item or {})
            item["section"] = section
            if _insert_visit(con, patient_key, item, dry_run=dry_run):
                summary["inserted"][section] += 1
            else:
                summary["skipped_duplicates"] += 1
    for section in ("tanilar", "ilaclar"):
        for item in sections.get(section) or []:
            item = dict(item or {})
            item["section"] = section
            if _insert_prescription(con, patient_key, item, section, user, dry_run=dry_run):
                summary["inserted"][section] += 1
            else:
                summary["skipped_duplicates"] += 1
    for item in sections.get("tetkikler") or []:
        item = dict(item or {})
        item["section"] = "tetkikler"
        if _insert_lab(con, patient_key, item, dry_run=dry_run):
            summary["inserted"]["tetkikler"] += 1
        else:
            summary["skipped_duplicates"] += 1
    for item in sections.get("gebelik_haftalari") or []:
        item = dict(item or {})
        item["section"] = "gebelik_haftalari"
        if _insert_ga(con, patient_key, item, user, dry_run=dry_run):
            summary["inserted"]["gebelik_haftalari"] += 1
        else:
            summary["skipped_duplicates"] += 1
    if not dry_run:
        con.commit()
    return summary

