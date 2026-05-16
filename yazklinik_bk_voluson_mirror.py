"""BulutKlinik patients -> YazKlinik/Voluson DB mirror.

This module guarantees that every row in bk_patients has a corresponding
YazKlinik patient row or an explicit bk_voluson_links mapping. It is DB-only:
no NAS/Voluson folders are created or deleted.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sqlite3
import time
import unicodedata
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_DB_PATH = ROOT / "local_db" / "yazklinik_v68.sqlite3"
DEFAULT_NAS_ROOT = r"\\asustor\Voluson"
MIRROR_KIND = "bk_mirror"


_TR_ASCII = str.maketrans({
    "\u00c7": "C", "\u00e7": "c",
    "\u011e": "G", "\u011f": "g",
    "\u0130": "I", "\u0131": "i",
    "\u00d6": "O", "\u00f6": "o",
    "\u015e": "S", "\u015f": "s",
    "\u00dc": "U", "\u00fc": "u",
})


def _config_value(key: str, default: str = "") -> str:
    env_value = os.environ.get(key)
    if env_value:
        return env_value
    cfg = ROOT / "config.env"
    if not cfg.exists():
        return default
    try:
        for raw in cfg.read_text(encoding="utf-8-sig",
                                 errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip() or default
    except Exception:
        return default
    return default


def resolve_db_path(db_path: str | None = None) -> str:
    return str(db_path or _config_value("YAZKLINIK_DB_PATH",
                                        str(DEFAULT_DB_PATH)))


def _now() -> str:
    return _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _connect(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(r[1]) for r in con.execute(
            f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def ensure_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS patients (
            folder_key TEXT PRIMARY KEY,
            full_path TEXT NOT NULL,
            display_name TEXT NOT NULL,
            folder_mtime REAL,
            first_seen_at TEXT NOT NULL,
            last_synced_at TEXT NOT NULL,
            archived_at TEXT,
            archived_by TEXT,
            archive_reason TEXT,
            created_at TEXT,
            updated_at TEXT
        )
    """)
    patient_cols = _columns(con, "patients")
    for col, ddl in (
        ("full_path", "ALTER TABLE patients ADD COLUMN full_path TEXT"),
        ("display_name", "ALTER TABLE patients ADD COLUMN display_name TEXT"),
        ("folder_mtime", "ALTER TABLE patients ADD COLUMN folder_mtime REAL"),
        ("first_seen_at", "ALTER TABLE patients ADD COLUMN first_seen_at TEXT"),
        ("last_synced_at", "ALTER TABLE patients ADD COLUMN last_synced_at TEXT"),
        ("archived_at", "ALTER TABLE patients ADD COLUMN archived_at TEXT"),
        ("archived_by", "ALTER TABLE patients ADD COLUMN archived_by TEXT"),
        ("archive_reason", "ALTER TABLE patients ADD COLUMN archive_reason TEXT"),
        ("created_at", "ALTER TABLE patients ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE patients ADD COLUMN updated_at TEXT"),
    ):
        if col not in patient_cols:
            try:
                con.execute(ddl)
                patient_cols.add(col)
            except Exception:
                pass

    con.execute("""
        CREATE TABLE IF NOT EXISTS patient_demographics (
            patient_key TEXT PRIMARY KEY,
            data_json TEXT,
            updated_at TEXT
        )
    """)
    demo_cols = _columns(con, "patient_demographics")
    for col, ddl in (
        ("tc_no", "ALTER TABLE patient_demographics ADD COLUMN tc_no TEXT"),
        ("phone", "ALTER TABLE patient_demographics ADD COLUMN phone TEXT"),
        ("birth_date", "ALTER TABLE patient_demographics ADD COLUMN birth_date TEXT"),
        ("blood_type", "ALTER TABLE patient_demographics ADD COLUMN blood_type TEXT"),
        ("allergies", "ALTER TABLE patient_demographics ADD COLUMN allergies TEXT"),
        ("chronic_conditions",
         "ALTER TABLE patient_demographics ADD COLUMN chronic_conditions TEXT"),
        ("canonical_name",
         "ALTER TABLE patient_demographics ADD COLUMN canonical_name TEXT"),
        ("dicom_patient_id",
         "ALTER TABLE patient_demographics ADD COLUMN dicom_patient_id TEXT"),
        ("dicom_patient_name",
         "ALTER TABLE patient_demographics ADD COLUMN dicom_patient_name TEXT"),
        ("data_json", "ALTER TABLE patient_demographics ADD COLUMN data_json TEXT"),
        ("updated_at", "ALTER TABLE patient_demographics ADD COLUMN updated_at TEXT"),
    ):
        if col not in demo_cols:
            try:
                con.execute(ddl)
                demo_cols.add(col)
            except Exception:
                pass

    con.execute("""
        CREATE TABLE IF NOT EXISTS patient_type (
            patient_key TEXT PRIMARY KEY,
            ptype TEXT NOT NULL,
            is_manual INTEGER NOT NULL DEFAULT 0,
            age INTEGER,
            phone TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    type_cols = _columns(con, "patient_type")
    for col, ddl in (
        ("ptype", "ALTER TABLE patient_type ADD COLUMN ptype TEXT"),
        ("is_manual", "ALTER TABLE patient_type ADD COLUMN is_manual INTEGER DEFAULT 0"),
        ("age", "ALTER TABLE patient_type ADD COLUMN age INTEGER"),
        ("phone", "ALTER TABLE patient_type ADD COLUMN phone TEXT"),
        ("notes", "ALTER TABLE patient_type ADD COLUMN notes TEXT"),
        ("created_at", "ALTER TABLE patient_type ADD COLUMN created_at TEXT"),
        ("updated_at", "ALTER TABLE patient_type ADD COLUMN updated_at TEXT"),
    ):
        if col not in type_cols:
            try:
                con.execute(ddl)
                type_cols.add(col)
            except Exception:
                pass

    con.execute("""
        CREATE TABLE IF NOT EXISTS bk_voluson_links (
            bk_hasta_no TEXT PRIMARY KEY,
            folder_key TEXT NOT NULL,
            match_kind TEXT NOT NULL,
            confidence REAL,
            matched_at TEXT NOT NULL,
            matched_by TEXT,
            note TEXT
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_bk_vol_folder "
                "ON bk_voluson_links(folder_key)")
    con.execute("""
        CREATE TABLE IF NOT EXISTS bk_obstetri_index (
            bk_hasta_no TEXT PRIMARY KEY,
            visit_count INTEGER DEFAULT 0,
            last_visit TEXT,
            first_visit TEXT,
            updated_at TEXT NOT NULL
        )
    """)
    con.commit()


def _ascii_text(value: str) -> str:
    text = str(value or "").translate(_TR_ASCII)
    text = unicodedata.normalize("NFKD", text)
    return text.encode("ascii", "ignore").decode("ascii")


def _slug(value: str, fallback: str = "HASTA") -> str:
    text = _ascii_text(value).upper()
    text = re.sub(r"[^A-Z0-9]+", "_", text).strip("_")
    return text or fallback


def _normalize_name(value: str) -> str:
    text = _ascii_text(value).lower()
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return " ".join(sorted(text.split()))


def _display_name(row: sqlite3.Row) -> str:
    ad = str(row["ad"] or "").strip()
    soyad = str(row["soyad"] or "").strip()
    display = " ".join(p for p in (ad, soyad) if p).strip()
    return display or f"BulutKlinik {row['bk_hasta_no']}"


def _folder_key(row: sqlite3.Row) -> str:
    hno = _slug(str(row["bk_hasta_no"] or ""), "NO")
    soyad = _slug(str(row["soyad"] or ""), "SOYAD")
    ad = _slug(str(row["ad"] or ""), "AD")
    key = f"BK_{hno}_{soyad}_{ad}"
    return key[:180].rstrip("_") or f"BK_{hno}"


def _mirror_root(virtual_root: str | None = None) -> str:
    if virtual_root:
        return virtual_root.rstrip("\\/")
    configured = _config_value("YAZKLINIK_BK_VOLUSON_MIRROR_ROOT", "")
    if configured:
        return configured.rstrip("\\/")
    nas_root = _config_value("YAZKLINIK_NAS_ROOT", DEFAULT_NAS_ROOT)
    return os.path.join(nas_root.rstrip("\\/"), "_BK_IMPORTED")


def _virtual_path(folder_key: str, virtual_root: str | None = None) -> str:
    return os.path.join(_mirror_root(virtual_root), folder_key)


def _json_load(value: str | None) -> dict:
    if not value:
        return {}
    try:
        obj = json.loads(value)
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}


def _bk_meta(row: sqlite3.Row, folder_key: str, full_path: str, now: str) -> dict:
    fields = {}
    for key in (
        "bk_hasta_no", "tc_kimlik", "ad", "soyad", "cinsiyet", "uyruk",
        "pasaport_no", "gelis_tarihi", "dogum_tarihi", "dogum_yeri",
        "telefon", "eposta", "kan_grubu", "baba_adi", "anne_adi",
        "medeni_hali", "anlasmali_kurum",
    ):
        val = row[key] if key in row.keys() else ""
        if val not in (None, ""):
            fields[key] = val
    return {
        "source": "bulutklinik",
        "bk_hasta_no": str(row["bk_hasta_no"] or ""),
        "mirrored_at": now,
        "db_only": True,
        "folder_key": folder_key,
        "virtual_full_path": full_path,
        "fields": fields,
    }


def _merge_demo_json(con: sqlite3.Connection, patient_key: str,
                     meta: dict) -> str:
    raw = None
    try:
        r = con.execute(
            "SELECT data_json FROM patient_demographics WHERE patient_key = ?",
            (patient_key,)).fetchone()
        raw = r["data_json"] if r else None
    except Exception:
        raw = None
    obj = _json_load(raw)
    obj["bulutklinik"] = meta
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def _patient_exists(con: sqlite3.Connection, folder_key: str) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM patients WHERE folder_key = ? AND archived_at IS NULL",
        (folder_key,)).fetchone())


def _active_patient_names(con: sqlite3.Connection) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in con.execute("""
        SELECT folder_key, display_name FROM patients
        WHERE archived_at IS NULL
    """).fetchall():
        norm = _normalize_name(r["display_name"] or r["folder_key"])
        if norm:
            out.setdefault(norm, []).append(r["folder_key"])
    return out


def _active_patient_tc(con: sqlite3.Connection) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    try:
        rows = con.execute("""
            SELECT d.patient_key, d.tc_no, d.dicom_patient_id
            FROM patient_demographics d
            JOIN patients p ON p.folder_key = d.patient_key
            WHERE p.archived_at IS NULL
        """).fetchall()
    except Exception:
        return out
    for r in rows:
        for tc in (r["tc_no"], r["dicom_patient_id"]):
            tc_s = re.sub(r"\D+", "", str(tc or ""))
            if len(tc_s) == 11:
                out.setdefault(tc_s, []).append(r["patient_key"])
    return out


def _choose_existing_target(row: sqlite3.Row, tc_index: dict[str, list[str]],
                            name_index: dict[str, list[str]]) -> tuple[str, str, float]:
    tc = re.sub(r"\D+", "", str(row["tc_kimlik"] or ""))
    if len(tc) == 11 and len(tc_index.get(tc, [])) == 1:
        return tc_index[tc][0], "auto_tc", 0.99
    norm = _normalize_name(_display_name(row))
    if norm and len(name_index.get(norm, [])) == 1:
        return name_index[norm][0], "auto_exact", 0.95
    return "", "", 0.0


def _upsert_patient(con: sqlite3.Connection, folder_key: str, display_name: str,
                    full_path: str, now: str) -> bool:
    existed = _patient_exists(con, folder_key)
    con.execute("""
        INSERT INTO patients (
            folder_key, full_path, display_name, folder_mtime,
            first_seen_at, last_synced_at, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?)
        ON CONFLICT(folder_key) DO UPDATE SET
            display_name = excluded.display_name,
            full_path = excluded.full_path,
            last_synced_at = excluded.last_synced_at,
            updated_at = excluded.updated_at
    """, (folder_key, full_path, display_name, float(time.time()),
          now, now, now, now))
    return not existed


def _upsert_demographics(con: sqlite3.Connection, row: sqlite3.Row,
                         folder_key: str, display_name: str,
                         full_path: str, now: str) -> None:
    meta = _bk_meta(row, folder_key, full_path, now)
    data_json = _merge_demo_json(con, folder_key, meta)
    values = {
        "patient_key": folder_key,
        "updated_at": now,
        "canonical_name": display_name,
        "tc_no": row["tc_kimlik"] or "",
        "phone": row["telefon"] or "",
        "birth_date": row["dogum_tarihi"] or "",
        "blood_type": row["kan_grubu"] or "",
        "allergies": row["alerjiler"] or "",
        "chronic_conditions": row["ozgecmis"] or "",
        "dicom_patient_id": row["tc_kimlik"] or "",
        "dicom_patient_name": display_name,
        "data_json": data_json,
    }
    con.execute("""
        INSERT INTO patient_demographics (
            patient_key, updated_at, canonical_name, tc_no, phone, birth_date,
            blood_type, allergies, chronic_conditions, dicom_patient_id,
            dicom_patient_name, data_json)
        VALUES (:patient_key, :updated_at, :canonical_name, :tc_no, :phone,
            :birth_date, :blood_type, :allergies, :chronic_conditions,
            :dicom_patient_id, :dicom_patient_name, :data_json)
        ON CONFLICT(patient_key) DO UPDATE SET
            updated_at = excluded.updated_at,
            canonical_name = CASE
                WHEN COALESCE(patient_demographics.canonical_name, '') = ''
                THEN excluded.canonical_name ELSE patient_demographics.canonical_name END,
            tc_no = CASE
                WHEN COALESCE(patient_demographics.tc_no, '') = ''
                THEN excluded.tc_no ELSE patient_demographics.tc_no END,
            phone = CASE
                WHEN COALESCE(patient_demographics.phone, '') = ''
                THEN excluded.phone ELSE patient_demographics.phone END,
            birth_date = CASE
                WHEN COALESCE(patient_demographics.birth_date, '') = ''
                THEN excluded.birth_date ELSE patient_demographics.birth_date END,
            blood_type = CASE
                WHEN COALESCE(patient_demographics.blood_type, '') = ''
                THEN excluded.blood_type ELSE patient_demographics.blood_type END,
            allergies = CASE
                WHEN COALESCE(patient_demographics.allergies, '') = ''
                THEN excluded.allergies ELSE patient_demographics.allergies END,
            chronic_conditions = CASE
                WHEN COALESCE(patient_demographics.chronic_conditions, '') = ''
                THEN excluded.chronic_conditions
                ELSE patient_demographics.chronic_conditions END,
            dicom_patient_id = CASE
                WHEN COALESCE(patient_demographics.dicom_patient_id, '') = ''
                THEN excluded.dicom_patient_id
                ELSE patient_demographics.dicom_patient_id END,
            dicom_patient_name = CASE
                WHEN COALESCE(patient_demographics.dicom_patient_name, '') = ''
                THEN excluded.dicom_patient_name
                ELSE patient_demographics.dicom_patient_name END,
            data_json = excluded.data_json
    """, values)


def _upsert_patient_type(con: sqlite3.Connection, row: sqlite3.Row,
                         folder_key: str, now: str,
                         is_obstetric: bool) -> None:
    ptype = "obstetric" if is_obstetric else "gynecologic"
    phone = row["telefon"] or ""
    note = (f"BulutKlinik DB mirror; bk_hasta_no={row['bk_hasta_no']}; "
            "NAS klasoru olusturulmadan Voluson/YazKlinik DB'ye eklendi.")
    con.execute("""
        INSERT INTO patient_type (
            patient_key, ptype, is_manual, phone, notes, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(patient_key) DO UPDATE SET
            ptype = CASE WHEN patient_type.is_manual = 1
                         THEN patient_type.ptype ELSE excluded.ptype END,
            phone = CASE WHEN COALESCE(patient_type.phone, '') = ''
                         THEN excluded.phone ELSE patient_type.phone END,
            notes = CASE WHEN COALESCE(patient_type.notes, '') = ''
                         THEN excluded.notes ELSE patient_type.notes END,
            updated_at = excluded.updated_at
    """, (folder_key, ptype, 0, phone, note, now, now))


def _upsert_link(con: sqlite3.Connection, bk_no: str, folder_key: str,
                 kind: str, confidence: float, now: str,
                 user: str, note: str) -> bool:
    existed = bool(con.execute(
        "SELECT 1 FROM bk_voluson_links WHERE bk_hasta_no = ?",
        (bk_no,)).fetchone())
    con.execute("""
        INSERT INTO bk_voluson_links (
            bk_hasta_no, folder_key, match_kind, confidence,
            matched_at, matched_by, note)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(bk_hasta_no) DO UPDATE SET
            folder_key = excluded.folder_key,
            match_kind = excluded.match_kind,
            confidence = excluded.confidence,
            matched_at = excluded.matched_at,
            matched_by = excluded.matched_by,
            note = excluded.note
    """, (bk_no, folder_key, kind, confidence, now, user, note))
    return not existed


def _table_exists(con: sqlite3.Connection, table: str) -> bool:
    return bool(con.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (table,)).fetchone())


def _ensure_clinical_schema(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS visits (
            patient_folder_key TEXT NOT NULL,
            visit_key TEXT NOT NULL,
            full_path TEXT NOT NULL,
            visit_date TEXT,
            folder_mtime REAL,
            file_count INTEGER DEFAULT 0,
            image_count INTEGER DEFAULT 0,
            video_count INTEGER DEFAULT 0,
            pdf_count INTEGER DEFAULT 0,
            latest_pdf_path TEXT,
            first_seen_at TEXT,
            last_synced_at TEXT,
            archived_at TEXT,
            archived_by TEXT,
            archive_reason TEXT,
            visit_type TEXT DEFAULT 'muayene',
            examination TEXT,
            control_note TEXT,
            source TEXT,
            notes TEXT,
            created_at TEXT,
            PRIMARY KEY(patient_folder_key, visit_key)
        )
    """)
    visit_cols = _columns(con, "visits")
    for col, ddl in (
        ("visit_key", "ALTER TABLE visits ADD COLUMN visit_key TEXT"),
        ("full_path", "ALTER TABLE visits ADD COLUMN full_path TEXT"),
        ("visit_date", "ALTER TABLE visits ADD COLUMN visit_date TEXT"),
        ("folder_mtime", "ALTER TABLE visits ADD COLUMN folder_mtime REAL"),
        ("file_count", "ALTER TABLE visits ADD COLUMN file_count INTEGER DEFAULT 0"),
        ("image_count", "ALTER TABLE visits ADD COLUMN image_count INTEGER DEFAULT 0"),
        ("video_count", "ALTER TABLE visits ADD COLUMN video_count INTEGER DEFAULT 0"),
        ("pdf_count", "ALTER TABLE visits ADD COLUMN pdf_count INTEGER DEFAULT 0"),
        ("latest_pdf_path", "ALTER TABLE visits ADD COLUMN latest_pdf_path TEXT"),
        ("first_seen_at", "ALTER TABLE visits ADD COLUMN first_seen_at TEXT"),
        ("last_synced_at", "ALTER TABLE visits ADD COLUMN last_synced_at TEXT"),
        ("archived_at", "ALTER TABLE visits ADD COLUMN archived_at TEXT"),
        ("archived_by", "ALTER TABLE visits ADD COLUMN archived_by TEXT"),
        ("archive_reason", "ALTER TABLE visits ADD COLUMN archive_reason TEXT"),
        ("visit_type", "ALTER TABLE visits ADD COLUMN visit_type TEXT DEFAULT 'muayene'"),
        ("examination", "ALTER TABLE visits ADD COLUMN examination TEXT"),
        ("control_note", "ALTER TABLE visits ADD COLUMN control_note TEXT"),
        ("source", "ALTER TABLE visits ADD COLUMN source TEXT"),
        ("notes", "ALTER TABLE visits ADD COLUMN notes TEXT"),
        ("created_at", "ALTER TABLE visits ADD COLUMN created_at TEXT"),
    ):
        if col not in visit_cols:
            try:
                con.execute(ddl)
                visit_cols.add(col)
            except Exception:
                pass

    con.execute("""
        CREATE TABLE IF NOT EXISTS visit_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_key TEXT NOT NULL,
            visit_key TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE(patient_key, visit_key)
        )
    """)
    con.execute("""
        CREATE TABLE IF NOT EXISTS prescriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            patient_key TEXT NOT NULL,
            medications TEXT,
            diagnosis TEXT,
            notes TEXT,
            created_by TEXT,
            created_at TEXT,
            template_id INTEGER,
            template_name TEXT,
            purpose TEXT,
            patient_name TEXT,
            protocol_no TEXT,
            visit_key TEXT,
            updated_at TEXT,
            deleted_at TEXT,
            deleted_by TEXT,
            deleted_reason TEXT
        )
    """)
    rx_cols = _columns(con, "prescriptions")
    for col, ddl in (
        ("template_name", "ALTER TABLE prescriptions ADD COLUMN template_name TEXT"),
        ("purpose", "ALTER TABLE prescriptions ADD COLUMN purpose TEXT"),
        ("patient_name", "ALTER TABLE prescriptions ADD COLUMN patient_name TEXT"),
        ("protocol_no", "ALTER TABLE prescriptions ADD COLUMN protocol_no TEXT"),
        ("visit_key", "ALTER TABLE prescriptions ADD COLUMN visit_key TEXT"),
        ("updated_at", "ALTER TABLE prescriptions ADD COLUMN updated_at TEXT"),
        ("deleted_at", "ALTER TABLE prescriptions ADD COLUMN deleted_at TEXT"),
        ("deleted_by", "ALTER TABLE prescriptions ADD COLUMN deleted_by TEXT"),
        ("deleted_reason", "ALTER TABLE prescriptions ADD COLUMN deleted_reason TEXT"),
    ):
        if col not in rx_cols:
            try:
                con.execute(ddl)
                rx_cols.add(col)
            except Exception:
                pass
    for ddl in (
        "CREATE INDEX IF NOT EXISTS idx_bk_mirror_visits "
        "ON visits(patient_folder_key, source, visit_date)",
        "CREATE INDEX IF NOT EXISTS idx_bk_mirror_rx "
        "ON prescriptions(patient_key, visit_key, protocol_no)",
    ):
        try:
            con.execute(ddl)
        except Exception:
            pass


def _row_dict(row) -> dict:
    if not row:
        return {}
    if isinstance(row, sqlite3.Row):
        return {k: row[k] for k in row.keys()}
    return dict(row)


def _text(value) -> str:
    return str(value or "").strip()


def _date_only(value: str) -> str:
    raw = _text(value)
    if not raw:
        return ""
    m = re.search(r"(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})", raw)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{4})", raw)
    if m:
        return f"{int(m.group(3)):04d}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return raw[:10]


def _safe_visit_key(prefix: str, value: str) -> str:
    raw = _slug(value, "KAYIT")
    return f"BK_{prefix}_{raw}"[:180].rstrip("_")


def _fetch_table_rows(con: sqlite3.Connection, table: str, where: str,
                      params: tuple = (), order: str = "") -> list[dict]:
    if not _table_exists(con, table):
        return []
    try:
        sql = f"SELECT * FROM {table} {where} {order}"
        return [_row_dict(r) for r in con.execute(sql, params).fetchall()]
    except Exception:
        return []


def _append_section(lines: list[str], title: str, items: list[str]) -> None:
    clean = [str(x).strip() for x in items if str(x or "").strip()]
    if not clean:
        return
    if lines:
        lines.append("")
    lines.append(title)
    lines.extend(f"- {x}" for x in clean)


def _medical_for_protocol(con, protocol_no: str) -> dict:
    rows = _fetch_table_rows(
        con, "bk_medical_infos", "WHERE protokol_no=?",
        (protocol_no,), "LIMIT 1")
    return rows[0] if rows else {}


def _gyn_for_protocol(con, protocol_no: str) -> list[dict]:
    if not protocol_no:
        return []
    return _fetch_table_rows(
        con, "bk_gynecology_resume", "WHERE protokol_no=?",
        (protocol_no,), "ORDER BY COALESCE(tarih,'') DESC")


def _services_for_protocol(con, protocol_no: str) -> list[dict]:
    return _fetch_table_rows(
        con, "bk_services", "WHERE protokol_no=?",
        (protocol_no,), "ORDER BY COALESCE(islem_tarihi,'')")


def _payments_for_protocol(con, protocol_no: str) -> list[dict]:
    return _fetch_table_rows(
        con, "bk_payments", "WHERE protokol_no=?",
        (protocol_no,), "ORDER BY COALESCE(tarih,'')")


def _obs_for_patient_date(con, bk_no: str, visit_date: str) -> list[dict]:
    if not bk_no or not visit_date:
        return []
    return _fetch_table_rows(
        con, "bk_obstetri_visits",
        "WHERE bk_hasta_no=? AND substr(COALESCE(tarih,''),1,10)=?",
        (bk_no, visit_date), "ORDER BY COALESCE(tarih,'')")


def _gyn_track_for_patient_date(con, bk_no: str, visit_date: str) -> list[dict]:
    if not bk_no or not visit_date:
        return []
    return _fetch_table_rows(
        con, "bk_gynecology_tracking",
        "WHERE bk_hasta_no=? AND substr(COALESCE(tarih,''),1,10)=?",
        (bk_no, visit_date), "ORDER BY COALESCE(tarih,'')")


def _build_protocol_note(con, protocol: dict, display_name: str) -> tuple[str, str, str]:
    pno = _text(protocol.get("protokol_no"))
    bk_no = _text(protocol.get("bk_hasta_no"))
    visit_date = _date_only(protocol.get("protokol_tarihi"))
    med = _medical_for_protocol(con, pno)
    services = _services_for_protocol(con, pno)
    payments = _payments_for_protocol(con, pno)
    gyn_rows = _gyn_for_protocol(con, pno)
    obs_rows = _obs_for_patient_date(con, bk_no, visit_date)
    gyn_track = _gyn_track_for_patient_date(con, bk_no, visit_date)

    lines = [
        f"BulutKlinik protokol #{pno}",
        f"Hasta: {display_name}",
    ]
    for label, value in (
        ("Tarih", protocol.get("protokol_tarihi")),
        ("Protokol tipi", protocol.get("protokol_tipi")),
        ("Brans", protocol.get("brans")),
        ("Doktor", protocol.get("doktor")),
        ("Gelis nedeni", protocol.get("gelis_nedeni")),
    ):
        if _text(value):
            lines.append(f"{label}: {_text(value)}")

    _append_section(lines, "Medikal bilgiler", [
        f"Hikaye: {_text(med.get('hikayesi'))}" if _text(med.get("hikayesi")) else "",
        f"Sikayet: {_text(med.get('sikayeti'))}" if _text(med.get("sikayeti")) else "",
        f"Bulgular: {_text(med.get('bulgular'))}" if _text(med.get("bulgular")) else "",
        f"Uygulamalar: {_text(med.get('uygulamalar'))}" if _text(med.get("uygulamalar")) else "",
        f"Oneriler: {_text(med.get('oneriler'))}" if _text(med.get("oneriler")) else "",
        f"Tani kodlari: {_text(med.get('tani_kodlari'))}" if _text(med.get("tani_kodlari")) else "",
        f"Notlar: {_text(med.get('notlar'))}" if _text(med.get("notlar")) else "",
    ])

    _append_section(lines, "Islenmis hizmetler", [
        " | ".join(x for x in (
            _text(s.get("islem_tarihi")),
            _text(s.get("hizmet_adi")),
            f"adet {_text(s.get('adet'))}" if _text(s.get("adet")) else "",
            f"tahsilat {_text(s.get('tahsilat_tutari'))}" if _text(s.get("tahsilat_tutari")) else "",
        ) if x)
        for s in services[:40]
    ])

    _append_section(lines, "Jinekoloji", [
        " | ".join(x for x in (
            _text(g.get("tarih")),
            f"Tani: {_text(g.get('tani'))}" if _text(g.get("tani")) else "",
            f"Tedavi: {_text(g.get('tedavi_plani'))}" if _text(g.get("tedavi_plani")) else "",
            f"Recete: {_text(g.get('recete'))}" if _text(g.get("recete")) else "",
            f"Not: {_text(g.get('notlar'))}" if _text(g.get("notlar")) else "",
        ) if x)
        for g in gyn_rows[:20]
    ])

    _append_section(lines, "Obstetri takip", [
        " | ".join(x for x in (
            _text(o.get("tarih")),
            f"USG {_text(o.get('usg_age'))}" if _text(o.get("usg_age")) else "",
            f"EFW {_text(o.get('efw'))}" if _text(o.get("efw")) else "",
            f"Amnion {_text(o.get('amnion'))}" if _text(o.get("amnion")) else "",
            f"Plasenta {_text(o.get('plasenta'))}" if _text(o.get("plasenta")) else "",
            f"Serviks {_text(o.get('serviks'))}" if _text(o.get("serviks")) else "",
            f"Sikayet {_text(o.get('sikayet'))}" if _text(o.get("sikayet")) else "",
        ) if x)
        for o in obs_rows[:20]
    ])

    _append_section(lines, "Jinekoloji takip", [
        " | ".join(x for x in (
            _text(o.get("tarih")),
            f"USG {_text(o.get('usg_age'))}" if _text(o.get("usg_age")) else "",
            f"EFW {_text(o.get('efw'))}" if _text(o.get("efw")) else "",
            f"Sikayet {_text(o.get('sikayet'))}" if _text(o.get("sikayet")) else "",
        ) if x)
        for o in gyn_track[:20]
    ])

    _append_section(lines, "Tahsilat", [
        " | ".join(x for x in (
            _text(p.get("tarih")),
            f"{_text(p.get('odenen'))} {_text(p.get('cinsi'))}".strip(),
        ) if x)
        for p in payments[:20]
    ])

    control_items = []
    if _text(med.get("oneriler")):
        control_items.append(_text(med.get("oneriler")))
    for g in gyn_rows:
        if _text(g.get("tedavi_plani")):
            control_items.append(_text(g.get("tedavi_plani")))
        if _text(g.get("sonuc")):
            control_items.append(_text(g.get("sonuc")))
    control_note = "\n\n".join(dict.fromkeys(control_items))
    diagnosis = _text(med.get("tani_kodlari")) or "; ".join(
        _text(g.get("tani")) for g in gyn_rows if _text(g.get("tani")))
    return "\n".join(lines), control_note, diagnosis


def _upsert_bk_visit(con: sqlite3.Connection, patient_key: str, visit_key: str,
                     full_path: str, visit_date: str, note: str,
                     control_note: str, now: str) -> bool:
    existed = bool(con.execute(
        "SELECT 1 FROM visits WHERE patient_folder_key=? AND visit_key=?",
        (patient_key, visit_key)).fetchone())
    con.execute("""
        INSERT INTO visits (
            patient_folder_key, visit_key, full_path, visit_date, folder_mtime,
            file_count, image_count, video_count, pdf_count, latest_pdf_path,
            first_seen_at, last_synced_at, visit_type, examination,
            control_note, source, notes, created_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(patient_folder_key, visit_key) DO UPDATE SET
            full_path=excluded.full_path,
            visit_date=excluded.visit_date,
            folder_mtime=excluded.folder_mtime,
            last_synced_at=excluded.last_synced_at,
            visit_type=excluded.visit_type,
            examination=excluded.examination,
            control_note=excluded.control_note,
            source=excluded.source,
            notes=excluded.notes
    """, (
        patient_key, visit_key, full_path, visit_date,
        time.time(), 0, 0, 0, 0, None, now, now, "muayene",
        note, control_note, "bulutklinik", note, now,
    ))
    con.execute("""
        INSERT INTO visit_notes(patient_key, visit_key, note, updated_at)
        VALUES (?,?,?,?)
        ON CONFLICT(patient_key, visit_key) DO UPDATE SET
            note=excluded.note, updated_at=excluded.updated_at
    """, (patient_key, visit_key, note, now))
    return not existed


def _upsert_bk_prescription(con: sqlite3.Connection, patient_key: str,
                            visit_key: str, protocol_no: str,
                            display_name: str, diagnosis: str,
                            medications: str, now: str) -> bool:
    medications = _text(medications)
    if not medications:
        return False
    template = "BulutKlinik Jinekoloji Recete"
    existing = con.execute("""
        SELECT id FROM prescriptions
        WHERE patient_key=? AND visit_key=? AND protocol_no=?
          AND COALESCE(template_name,'')=?
          AND COALESCE(deleted_at,'')=''
        LIMIT 1
    """, (patient_key, visit_key, protocol_no, template)).fetchone()
    if existing:
        con.execute("""
            UPDATE prescriptions
            SET medications=?, diagnosis=?, notes=?, patient_name=?,
                updated_at=?
            WHERE id=?
        """, (
            medications, diagnosis, "BulutKlinik recete alanindan aktarildi.",
            display_name, now, existing["id"],
        ))
        return False
    con.execute("""
        INSERT INTO prescriptions (
            patient_key, medications, diagnosis, notes, created_by,
            created_at, template_name, purpose, patient_name, protocol_no,
            visit_key, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """, (
        patient_key, medications, diagnosis,
        "BulutKlinik recete alanindan aktarildi.", "bulutklinik",
        now, template, "bk-clinical-mirror", display_name,
        protocol_no, visit_key, now,
    ))
    return True


def _sync_bk_clinical_timeline(con: sqlite3.Connection, bk_no: str,
                               patient_key: str, display_name: str,
                               full_path: str, now: str) -> dict:
    stats = {"visits": 0, "notes": 0, "prescriptions": 0}
    if not bk_no:
        return stats
    _ensure_clinical_schema(con)
    protocols = _fetch_table_rows(
        con, "bk_protocols", "WHERE bk_hasta_no=?",
        (bk_no,), "ORDER BY COALESCE(protokol_tarihi,'')")
    protocol_ids = set()
    for protocol in protocols:
        pno = _text(protocol.get("protokol_no"))
        if not pno:
            continue
        protocol_ids.add(pno)
        visit_key = _safe_visit_key("PROTOKOL", pno)
        visit_date = _date_only(protocol.get("protokol_tarihi")) or now[:10]
        visit_path = os.path.join(full_path or _virtual_path(patient_key), visit_key)
        note, control_note, diagnosis = _build_protocol_note(
            con, protocol, display_name)
        if _upsert_bk_visit(con, patient_key, visit_key, visit_path,
                            visit_date, note, control_note, now):
            stats["visits"] += 1
        stats["notes"] += 1
        for gyn in _gyn_for_protocol(con, pno):
            if _upsert_bk_prescription(
                    con, patient_key, visit_key, pno, display_name,
                    diagnosis or _text(gyn.get("tani")),
                    _text(gyn.get("recete")), now):
                stats["prescriptions"] += 1

    gyn_rows = _fetch_table_rows(
        con, "bk_gynecology_resume", "WHERE bk_hasta_no=?",
        (bk_no,), "ORDER BY COALESCE(tarih,''), COALESCE(resume_no,'')")
    for gyn in gyn_rows:
        pno = _text(gyn.get("protokol_no"))
        if pno and pno in protocol_ids:
            continue
        raw_key = _text(gyn.get("row_hash")) or _text(gyn.get("resume_no"))
        if not raw_key:
            continue
        visit_key = _safe_visit_key("GYN", raw_key[:16])
        visit_date = _date_only(gyn.get("tarih")) or now[:10]
        lines = [f"BulutKlinik jinekoloji kaydi {raw_key[:12]}",
                 f"Hasta: {display_name}"]
        _append_section(lines, "Jinekoloji", [
            f"Tarih: {_text(gyn.get('tarih'))}" if _text(gyn.get("tarih")) else "",
            f"SAT: {_text(gyn.get('son_adet_tarihi'))}" if _text(gyn.get("son_adet_tarihi")) else "",
            f"Sikayet/oyku: {_text(gyn.get('sikayet_oyku'))}" if _text(gyn.get("sikayet_oyku")) else "",
            f"Bulgular: {_text(gyn.get('bulgular'))}" if _text(gyn.get("bulgular")) else "",
            f"Tani: {_text(gyn.get('tani'))}" if _text(gyn.get("tani")) else "",
            f"Tedavi: {_text(gyn.get('tedavi_plani'))}" if _text(gyn.get("tedavi_plani")) else "",
            f"Recete: {_text(gyn.get('recete'))}" if _text(gyn.get("recete")) else "",
            f"Sonuc: {_text(gyn.get('sonuc'))}" if _text(gyn.get("sonuc")) else "",
            f"Not: {_text(gyn.get('notlar'))}" if _text(gyn.get("notlar")) else "",
        ])
        note = "\n".join(lines)
        control_note = "\n\n".join(x for x in (
            _text(gyn.get("tedavi_plani")), _text(gyn.get("sonuc"))
        ) if x)
        visit_path = os.path.join(full_path or _virtual_path(patient_key), visit_key)
        if _upsert_bk_visit(con, patient_key, visit_key, visit_path,
                            visit_date, note, control_note, now):
            stats["visits"] += 1
        stats["notes"] += 1
        if _upsert_bk_prescription(
                con, patient_key, visit_key, pno or raw_key[:16],
                display_name, _text(gyn.get("tani")),
                _text(gyn.get("recete")), now):
            stats["prescriptions"] += 1

    for table, prefix, title in (
        ("bk_obstetri_visits", "OBS", "BulutKlinik obstetri takip"),
        ("bk_gynecology_tracking", "GYN_TAKIP", "BulutKlinik jinekoloji takip"),
    ):
        rows = _fetch_table_rows(
            con, table, "WHERE bk_hasta_no=?",
            (bk_no,), "ORDER BY COALESCE(tarih,''), COALESCE(takip_no,'')")
        for item in rows:
            raw_key = _text(item.get("row_hash")) or _text(item.get("takip_no"))
            if not raw_key:
                continue
            visit_key = _safe_visit_key(prefix, raw_key[:16])
            visit_date = _date_only(item.get("tarih")) or now[:10]
            lines = [f"{title} {raw_key[:12]}", f"Hasta: {display_name}"]
            _append_section(lines, "Takip", [
                f"Tarih: {_text(item.get('tarih'))}" if _text(item.get("tarih")) else "",
                f"Takip no: {_text(item.get('takip_no'))}" if _text(item.get("takip_no")) else "",
                f"USG age: {_text(item.get('usg_age'))}" if _text(item.get("usg_age")) else "",
                f"EFW: {_text(item.get('efw'))}" if _text(item.get("efw")) else "",
                f"Amnion: {_text(item.get('amnion'))}" if _text(item.get("amnion")) else "",
                f"Plasenta: {_text(item.get('plasenta'))}" if _text(item.get("plasenta")) else "",
                f"Serviks: {_text(item.get('serviks'))}" if _text(item.get("serviks")) else "",
                f"Hb/Hct/Plt: {_text(item.get('hb'))} / {_text(item.get('hct'))} / {_text(item.get('plt'))}".strip(" /") if (_text(item.get("hb")) or _text(item.get("hct")) or _text(item.get("plt"))) else "",
                f"Kilo: {_text(item.get('kilo'))}" if _text(item.get("kilo")) else "",
                f"TA: {_text(item.get('ta'))}" if _text(item.get("ta")) else "",
                f"Sikayet: {_text(item.get('sikayet'))}" if _text(item.get("sikayet")) else "",
                f"Diger: {_text(item.get('diger'))}" if _text(item.get("diger")) else "",
            ])
            note = "\n".join(lines)
            visit_path = os.path.join(
                full_path or _virtual_path(patient_key), visit_key)
            if _upsert_bk_visit(con, patient_key, visit_key, visit_path,
                                visit_date, note, "", now):
                stats["visits"] += 1
            stats["notes"] += 1
    return stats


def mirror_bk_patients(db_path: str | None = None, dry_run: bool = False,
                       only_obstetric: bool = False,
                       limit: int | None = None,
                       user: str = "system",
                       virtual_root: str | None = None) -> dict:
    """Mirror missing bk_patients into the YazKlinik patient tables.

    Existing explicit links are respected. For unlinked BK rows, the function
    first tries a safe TC/exact-name link to an active Voluson patient; if no
    unambiguous target exists, it creates a synthetic DB-only patient row.
    """
    db = resolve_db_path(db_path)
    con = _connect(db)
    try:
        ensure_schema(con)
        where = ""
        if only_obstetric:
            where = ("WHERE p.bk_hasta_no IN "
                     "(SELECT bk_hasta_no FROM bk_obstetri_index)")
        sql = f"""
            SELECT p.*,
                   CASE WHEN oi.bk_hasta_no IS NULL THEN 0 ELSE 1 END AS is_obstetric
            FROM bk_patients p
            LEFT JOIN bk_obstetri_index oi ON oi.bk_hasta_no = p.bk_hasta_no
            {where}
            ORDER BY CAST(p.bk_hasta_no AS INTEGER), p.bk_hasta_no
        """
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = con.execute(sql).fetchall()
        links = {
            r["bk_hasta_no"]: r["folder_key"]
            for r in con.execute(
                "SELECT bk_hasta_no, folder_key FROM bk_voluson_links")
        }
        name_index = _active_patient_names(con)
        tc_index = _active_patient_tc(con)
        now = _now()
        stats = {
            "ok": True,
            "dry_run": bool(dry_run),
            "db_path": db,
            "bk_total": len(rows),
            "already_linked": 0,
            "auto_linked_existing": 0,
            "created_patients": 0,
            "created_links": 0,
            "repaired_links": 0,
            "updated_demographics": 0,
            "updated_patient_type": 0,
            "clinical_visits": 0,
            "clinical_notes": 0,
            "clinical_prescriptions": 0,
            "mirror_root": _mirror_root(virtual_root),
        }
        for row in rows:
            bk_no = str(row["bk_hasta_no"] or "").strip()
            if not bk_no:
                continue
            display = _display_name(row)
            is_obstetric = bool(row["is_obstetric"])
            linked_fk = links.get(bk_no)
            if linked_fk and _patient_exists(con, linked_fk):
                stats["already_linked"] += 1
                if not dry_run:
                    linked_path = con.execute(
                        "SELECT full_path FROM patients WHERE folder_key = ?",
                        (linked_fk,)).fetchone()
                    full_path = (linked_path["full_path"]
                                 if linked_path else _virtual_path(linked_fk))
                    _upsert_demographics(con, row, linked_fk, display,
                                         full_path, now)
                    _upsert_patient_type(con, row, linked_fk, now,
                                         is_obstetric)
                    stats["updated_demographics"] += 1
                    stats["updated_patient_type"] += 1
                    clinical = _sync_bk_clinical_timeline(
                        con, bk_no, linked_fk, display, full_path, now)
                    stats["clinical_visits"] += clinical["visits"]
                    stats["clinical_notes"] += clinical["notes"]
                    stats["clinical_prescriptions"] += clinical["prescriptions"]
                continue

            target_fk = ""
            kind = MIRROR_KIND
            confidence = 0.0
            if not linked_fk:
                target_fk, auto_kind, auto_conf = _choose_existing_target(
                    row, tc_index, name_index)
                if target_fk:
                    kind, confidence = auto_kind, auto_conf
                    stats["auto_linked_existing"] += 1

            if target_fk:
                full_path_row = con.execute(
                    "SELECT full_path FROM patients WHERE folder_key = ?",
                    (target_fk,)).fetchone()
                full_path = (full_path_row["full_path"]
                             if full_path_row else _virtual_path(target_fk))
                if not dry_run:
                    if _upsert_link(con, bk_no, target_fk, kind, confidence,
                                    now, user,
                                    "BulutKlinik -> Voluson DB auto link"):
                        stats["created_links"] += 1
                    _upsert_demographics(con, row, target_fk, display,
                                         full_path, now)
                    _upsert_patient_type(con, row, target_fk, now,
                                         is_obstetric)
                    stats["updated_demographics"] += 1
                    stats["updated_patient_type"] += 1
                    clinical = _sync_bk_clinical_timeline(
                        con, bk_no, target_fk, display, full_path, now)
                    stats["clinical_visits"] += clinical["visits"]
                    stats["clinical_notes"] += clinical["notes"]
                    stats["clinical_prescriptions"] += clinical["prescriptions"]
                else:
                    stats["created_links"] += 1
                continue

            folder_key = _folder_key(row)
            full_path = _virtual_path(folder_key, virtual_root)
            if not dry_run:
                if _upsert_patient(con, folder_key, display, full_path, now):
                    stats["created_patients"] += 1
                if _upsert_link(con, bk_no, folder_key, MIRROR_KIND, 0.0,
                                now, user,
                                "DB-only BulutKlinik mirror; NAS folder not created"):
                    stats["created_links"] += 1
                if linked_fk:
                    stats["repaired_links"] += 1
                _upsert_demographics(con, row, folder_key, display,
                                     full_path, now)
                _upsert_patient_type(con, row, folder_key, now,
                                     is_obstetric)
                stats["updated_demographics"] += 1
                stats["updated_patient_type"] += 1
                clinical = _sync_bk_clinical_timeline(
                    con, bk_no, folder_key, display, full_path, now)
                stats["clinical_visits"] += clinical["visits"]
                stats["clinical_notes"] += clinical["notes"]
                stats["clinical_prescriptions"] += clinical["prescriptions"]
            else:
                if not _patient_exists(con, folder_key):
                    stats["created_patients"] += 1
                if not linked_fk:
                    stats["created_links"] += 1
                else:
                    stats["repaired_links"] += 1

        if dry_run:
            con.rollback()
        else:
            con.commit()
        stats["patients_total"] = con.execute(
            "SELECT COUNT(*) FROM patients").fetchone()[0]
        stats["links_total"] = con.execute(
            "SELECT COUNT(*) FROM bk_voluson_links").fetchone()[0]
        stats["mirror_links_total"] = con.execute(
            "SELECT COUNT(*) FROM bk_voluson_links WHERE match_kind = ?",
            (MIRROR_KIND,)).fetchone()[0]
        return stats
    finally:
        con.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db-path", default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only-obstetric", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    stats = mirror_bk_patients(db_path=args.db_path, dry_run=args.dry_run,
                               only_obstetric=args.only_obstetric,
                               limit=args.limit, user="cli")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
