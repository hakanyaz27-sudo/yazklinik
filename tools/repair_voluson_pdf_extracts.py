"""Repair cached patient data from Voluson/GE obstetric PDFs.

This is intentionally conservative:
- never deletes patient/visit/file rows;
- does not overwrite fields marked manual in data_json.manual_fields;
- only clears LMP/SAT when it was previously auto-filled from a PDF and the
  current parser no longer finds a real LMP in that patient's PDFs;
- upserts PDF-derived fetal measurements by source_instance_id.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import fitz

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from yazklinik_pdf_patient_extract import extract_patient_pdf_payload


DEFAULT_DB = ROOT / "local_db" / "yazklinik_v68.sqlite3"
PROFILE_VERSION = "2026-05-17-voluson-ga-metrics-v4"


DEMO_COLUMNS = {
    "age",
    "birth_date",
    "weight",
    "height",
    "bmi",
    "pre_pregnancy_weight",
    "lmp_override",
    "gravida",
    "para",
    "abortus",
    "living",
}

ALIASES = {
    "lmp": "lmp_override",
    "sat": "lmp_override",
    "last_menstrual_period": "lmp_override",
    "pre_weight": "pre_pregnancy_weight",
}

FETAL_KEYS_FLOAT = (
    "bpd", "hc", "ac", "fl", "crl", "nt", "afi", "fhr",
    "ua_pi", "ua_ri", "ua_sd", "mca_pi", "mca_ri", "mca_psv",
    "uta_pi", "uta_ri", "dv_pi", "cpr",
)


def _now() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _num(value: Any, low: float | None = None,
         high: float | None = None) -> float | None:
    raw = str(value or "").replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not m:
        return None
    try:
        val = float(m.group(0))
    except Exception:
        return None
    if low is not None and val < low:
        return None
    if high is not None and val > high:
        return None
    return round(val, 2)


def _int(value: Any, low: int | None = None,
         high: int | None = None) -> int | None:
    val = _num(value, low=low, high=high)
    if val is None:
        return None
    return int(round(val))


def _date_ddmmyyyy(value: Any) -> str:
    raw = str(value or "").strip()
    m = re.search(
        r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})|"
        r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})",
        raw,
    )
    if not m:
        return ""
    try:
        if m.group(1):
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            year, month, day = int(m.group(4)), int(m.group(5)), int(m.group(6))
        return datetime(year, month, day).strftime("%d.%m.%Y")
    except Exception:
        return ""


def _date_iso(value: Any) -> str:
    ddmmyyyy = _date_ddmmyyyy(value)
    if not ddmmyyyy:
        return ""
    try:
        return datetime.strptime(ddmmyyyy, "%d.%m.%Y").strftime("%Y-%m-%d")
    except Exception:
        return ""


def _normalize(field: str, value: Any) -> Any:
    field = ALIASES.get(field, field)
    if field == "birth_date":
        return _date_iso(value)
    if field == "lmp_override":
        return _date_ddmmyyyy(value)
    if field == "age":
        return _int(value, low=2, high=120)
    if field in ("gravida", "para", "abortus", "living"):
        return _int(value, low=0, high=30)
    if field == "weight":
        return _num(value, low=20, high=250)
    if field == "height":
        return _num(value, low=90, high=230)
    if field == "bmi":
        return _num(value, low=10, high=80)
    if field == "pre_pregnancy_weight":
        return _num(value, low=20, high=250)
    return _clean(value)


def _load_json(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})")}


def _pdf_text(path: str) -> str:
    doc = fitz.open(path)
    try:
        return "\n".join(page.get_text("text") or "" for page in doc)
    finally:
        doc.close()


def _collect_patient_pdfs(con: sqlite3.Connection, patient_key: str,
                          max_pdfs: int) -> tuple[list[dict[str, Any]], str]:
    rows = con.execute(
        """
        SELECT patient_folder_key, visit_key, file_name, full_path, mtime,
               size_bytes
        FROM files
        WHERE patient_folder_key=?
          AND lower(file_name) LIKE '%.pdf'
          AND archived_at IS NULL
        ORDER BY COALESCE(mtime, 0) DESC
        LIMIT ?
        """,
        (patient_key, max_pdfs),
    ).fetchall()
    items: list[dict[str, Any]] = []
    sig_bits: list[str] = []
    for row in rows:
        path = _clean(row["full_path"])
        if not path or not os.path.exists(path):
            continue
        try:
            stat = os.stat(path)
            mtime = float(stat.st_mtime)
            size = int(stat.st_size)
            text = _pdf_text(path)
        except Exception:
            continue
        visit_key = _clean(row["visit_key"])
        visit_date = ""
        if re.fullmatch(r"\d{8}_\d{6}", visit_key or ""):
            try:
                visit_date = datetime.strptime(
                    visit_key[:8], "%Y%m%d").strftime("%Y-%m-%d")
            except Exception:
                visit_date = ""
        items.append({
            "name": _clean(row["file_name"]) or os.path.basename(path),
            "path": path,
            "mtime": mtime,
            "text": text,
            "visit_key": visit_key,
            "visit_date": visit_date,
        })
        sig_bits.append(f"{path}|{int(mtime)}|{size}")
    return items, "\n".join(sig_bits)


def _source_for_field(pdf_payload: dict[str, Any],
                      field: str) -> dict[str, Any]:
    for entry in pdf_payload.get("pdfs") or []:
        demo = entry.get("demographics") or {}
        if field in demo or any(ALIASES.get(k, k) == field for k in demo):
            return {
                "source": entry.get("name") or "PDF",
                "path": entry.get("path") or "",
                "mtime": entry.get("mtime") or 0,
                "visit_key": entry.get("visit_key") or "",
                "visit_date": entry.get("visit_date") or "",
            }
    return {}


def _manual_fields(meta: dict[str, Any]) -> set[str]:
    raw = meta.get("manual_fields")
    if isinstance(raw, dict):
        return {ALIASES.get(str(k), str(k)) for k in raw}
    if isinstance(raw, list):
        return {ALIASES.get(str(k), str(k)) for k in raw}
    return set()


def _looks_pdf_auto_lmp(meta: dict[str, Any]) -> bool:
    sources = meta.get("pdf_auto_field_sources")
    if not isinstance(sources, dict):
        return False
    info = sources.get("lmp_override") or sources.get("lmp") or sources.get("sat")
    if not isinstance(info, dict):
        return False
    hay = " ".join(
        _clean(info.get(k)).lower()
        for k in ("source", "path", "visit_key")
    )
    return bool(hay) and (
        "rep_ob" in hay or "voluson" in hay or "img_" in hay
    )


def _best_usg_date(entry: dict[str, Any], fetal: dict[str, Any]) -> str:
    for value in (
        fetal.get("usg_date"),
        entry.get("report_date"),
        entry.get("visit_date"),
    ):
        iso = _date_iso(value)
        if iso:
            return iso
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", _clean(value)):
            return _clean(value)
    try:
        mtime = float(entry.get("mtime") or 0)
        if mtime > 0:
            return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except Exception:
        pass
    return datetime.now().strftime("%Y-%m-%d")


def _is_lab_pdf(entry: dict[str, Any]) -> bool:
    hay = " ".join(
        _clean(entry.get(k)).lower()
        for k in ("name", "path", "report_type")
    )
    return any(token in hay for token in (
        "enabiz", "e-nabiz", "tahlil", "tetkik", "lab", "laboratuvar",
    ))


def _upsert_usg(con: sqlite3.Connection, patient_key: str,
                payload: dict[str, Any], apply: bool) -> tuple[int, int]:
    inserted = 0
    updated = 0
    for entry in payload.get("pdfs") or []:
        if _is_lab_pdf(entry):
            continue
        fetal = dict(entry.get("fetal") or {})
        wanted = (
            "ga_weeks", "bpd", "hc", "ac", "fl", "crl", "nt", "efw", "afi",
            "fhr", "ua_pi", "ua_ri", "ua_sd", "mca_pi", "mca_ri", "mca_psv",
            "uta_pi", "uta_ri", "dv_pi", "cpr",
        )
        if not any(fetal.get(k) not in (None, "") for k in wanted):
            continue
        source_path = _clean(entry.get("path")) or _clean(entry.get("name"))
        instance_id = ("pdf:" + re.sub(
            r"\s+", " ", source_path.strip().lower()))[:480]
        values: dict[str, Any] = {
            "patient_key": patient_key,
            "usg_date": _best_usg_date(entry, fetal),
            "visit_key": _clean(entry.get("visit_key")),
            "source_type": "pdf",
            "source_study_id": source_path,
            "source_instance_id": instance_id,
            "source_accession_number": _clean(entry.get("name")) or "PDF",
        }
        ga_w = _int(fetal.get("ga_weeks"), low=3, high=43)
        if ga_w is not None:
            values["ga_weeks"] = ga_w
            values["ga_days"] = _int(fetal.get("ga_days"), low=0, high=6) or 0
        for key in FETAL_KEYS_FLOAT:
            val = _num(fetal.get(key))
            if val is not None:
                values[key] = val
        efw = _int(fetal.get("efw"), low=40, high=6500)
        if efw is not None:
            values["efw"] = efw
        for key in ("placenta", "fetal_position"):
            val = _clean(fetal.get(key))
            if val:
                values[key] = val[:120]
        bits = []
        if values.get("ga_weeks") is not None:
            bits.append(f"GA {values['ga_weeks']}+{values.get('ga_days', 0)}")
        for key, label in (("bpd", "BPD"), ("hc", "HC"), ("ac", "AC"),
                           ("fl", "FL"), ("efw", "EFW")):
            if values.get(key) not in (None, ""):
                bits.append(f"{label} {values[key]}")
        values["notes"] = (
            f"[PDF fetal] Kaynak: {values['source_accession_number']}"
            + (f" | {', '.join(bits)}" if bits else "")
        )
        existing = con.execute(
            "SELECT id FROM usg_measurements WHERE patient_key=? "
            "AND source_instance_id=? LIMIT 1",
            (patient_key, instance_id),
        ).fetchone()
        if existing:
            updated += 1
            if apply:
                update_values = dict(values)
                update_values.pop("patient_key", None)
                sets = ", ".join(f"{col}=?" for col in update_values)
                con.execute(
                    f"UPDATE usg_measurements SET {sets} WHERE id=?",
                    list(update_values.values()) + [existing["id"]],
                )
        else:
            inserted += 1
            if apply:
                values["created_by"] = "pdf_repair"
                values["created_at"] = _now()
                cols = list(values)
                con.execute(
                    "INSERT INTO usg_measurements("
                    + ", ".join(cols) + ") VALUES("
                    + ", ".join("?" for _ in cols) + ")",
                    [values[col] for col in cols],
                )
        visit_key = _clean(entry.get("visit_key"))
        if apply and visit_key and values.get("usg_date"):
            con.execute(
                "UPDATE visits SET visit_date=?, "
                "source=COALESCE(source, 'voluson:auto') "
                "WHERE patient_folder_key=? AND visit_key=?",
                (values["usg_date"], patient_key, visit_key),
            )
    return inserted, updated


def _repair_patient(con: sqlite3.Connection, patient_key: str,
                    max_pdfs: int, apply: bool) -> dict[str, Any]:
    items, signature = _collect_patient_pdfs(con, patient_key, max_pdfs=max_pdfs)
    if not items:
        return {"patient_key": patient_key, "status": "no_pdf"}
    payload = extract_patient_pdf_payload(items) or {}
    if not payload.get("ok"):
        return {"patient_key": patient_key, "status": "no_data"}

    now = _now()
    row = con.execute(
        "SELECT * FROM patient_demographics WHERE patient_key=?",
        (patient_key,),
    ).fetchone()
    current = dict(row) if row else {"patient_key": patient_key}
    meta = _load_json(current.get("data_json"))
    manual = _manual_fields(meta)
    pdf_sources = meta.get("pdf_auto_field_sources")
    if not isinstance(pdf_sources, dict):
        pdf_sources = {}

    applied: dict[str, Any] = {}
    skipped: dict[str, Any] = {}
    source_updates: dict[str, Any] = {}
    pdf_demo = dict(payload.get("demographics") or {})
    for raw_field, raw_value in pdf_demo.items():
        field = ALIASES.get(raw_field, raw_field)
        if field not in DEMO_COLUMNS:
            continue
        normalized = _normalize(field, raw_value)
        if normalized in (None, ""):
            continue
        current_norm = _normalize(field, current.get(field))
        was_pdf = field in pdf_sources
        if field in manual and current_norm not in (None, ""):
            skipped[field] = normalized
            continue
        if current_norm == normalized:
            continue
        if current_norm in (None, "") or was_pdf:
            applied[field] = normalized
            source_updates[field] = _source_for_field(payload, field)
        else:
            skipped[field] = normalized

    clear_lmp = False
    if (
        "lmp_override" not in pdf_demo
        and current.get("lmp_override")
        and "lmp_override" not in manual
        and _looks_pdf_auto_lmp(meta)
    ):
        clear_lmp = True
        applied["lmp_override"] = None

    compact = dict(payload)
    compact["pdfs"] = compact.get("pdfs", [])[:20]
    compact["labs"] = compact.get("labs", [])[:80]
    meta["pdf_patient_extract"] = compact
    meta["pdf_patient_extract_updated_at"] = now
    meta["pdf_patient_extract_applied"] = applied
    meta["pdf_patient_extract_auto_version"] = PROFILE_VERSION
    meta["pdf_patient_extract_auto_signature"] = signature
    meta["pdf_patient_extract_auto_checked_at"] = now
    meta["pdf_patient_extract_auto_applied"] = applied
    meta["pdf_patient_extract_auto_skipped"] = skipped
    for field, info in source_updates.items():
        if info:
            item = dict(info)
            item["updated_at"] = now
            pdf_sources[field] = item
    if clear_lmp:
        pdf_sources.pop("lmp_override", None)
    meta["pdf_auto_field_sources"] = pdf_sources

    columns = _table_columns(con, "patient_demographics")
    if apply:
        con.execute(
            "INSERT OR IGNORE INTO patient_demographics"
            "(patient_key, updated_at, data_json) VALUES(?,?,?)",
            (patient_key, now, "{}"),
        )
        sets = ["updated_at=?", "data_json=?"]
        values: list[Any] = [now, json.dumps(meta, ensure_ascii=False)]
        for field, value in applied.items():
            if field in columns:
                sets.append(f"{field}=?")
                values.append(value)
        values.append(patient_key)
        con.execute(
            "UPDATE patient_demographics SET " + ", ".join(sets)
            + " WHERE patient_key=?",
            values,
        )

    inserted, updated = _upsert_usg(con, patient_key, payload, apply=apply)
    return {
        "patient_key": patient_key,
        "status": "applied" if applied or inserted or updated else "read",
        "pdfs": len(items),
        "demo_applied": applied,
        "demo_skipped": skipped,
        "usg_inserted": inserted,
        "usg_updated": updated,
        "clear_lmp": clear_lmp,
    }


def run(db_path: str, apply: bool, max_pdfs: int,
        patient: str = "", limit: int = 0) -> dict[str, Any]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        if patient:
            patients = [patient]
        else:
            rows = con.execute(
                """
                SELECT patient_folder_key, MAX(COALESCE(mtime, 0)) AS mt
                FROM files
                WHERE lower(file_name) LIKE '%.pdf'
                  AND archived_at IS NULL
                GROUP BY patient_folder_key
                ORDER BY mt DESC
                """
            ).fetchall()
            patients = [_clean(row["patient_folder_key"]) for row in rows]
        if limit and limit > 0:
            patients = patients[:limit]
        results = []
        for patient_key in patients:
            results.append(_repair_patient(
                con, patient_key, max_pdfs=max_pdfs, apply=apply))
        if apply:
            con.commit()
        summary = {
            "apply": apply,
            "patients_seen": len(patients),
            "with_data": sum(1 for r in results if r["status"] != "no_pdf"),
            "demo_changed": sum(1 for r in results if r.get("demo_applied")),
            "lmp_cleared": sum(1 for r in results if r.get("clear_lmp")),
            "usg_inserted": sum(int(r.get("usg_inserted") or 0) for r in results),
            "usg_updated": sum(int(r.get("usg_updated") or 0) for r in results),
            "results": results,
        }
        return summary
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=os.environ.get(
        "YAZKLINIK_DB_PATH", str(DEFAULT_DB)))
    parser.add_argument("--apply", action="store_true",
                        help="Write repairs. Default is dry-run.")
    parser.add_argument("--max-pdfs", type=int, default=12)
    parser.add_argument("--patient", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    summary = run(
        db_path=args.db,
        apply=bool(args.apply),
        max_pdfs=max(1, int(args.max_pdfs or 12)),
        patient=args.patient,
        limit=max(0, int(args.limit or 0)),
    )
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    else:
        mode = "APPLY" if args.apply else "DRY-RUN"
        print(f"VOLUSON_PDF_REPAIR_{mode}")
        print(f"patients_seen={summary['patients_seen']}")
        print(f"with_data={summary['with_data']}")
        print(f"demo_changed={summary['demo_changed']}")
        print(f"lmp_cleared={summary['lmp_cleared']}")
        print(f"usg_inserted={summary['usg_inserted']}")
        print(f"usg_updated={summary['usg_updated']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
