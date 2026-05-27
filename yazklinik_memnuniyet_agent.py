"""Memnuniyet Anketi + Dogum Gunu Tebrik Cron Ajani.

Iki gunluk gorev:
    1. Dun gelen hastalara WhatsApp anket gonder (5 yildiz + 1 cumle)
    2. Bugun dogum gunu olan hastalara tebrik gonder

Cron task ile gunluk calistirilir.
"""
from __future__ import annotations

import json
import os
import sqlite3
from yazklinik_db_adapter import agent_connection as _pgconn  # PG-primary aware (cutover)
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-memnuniyet"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")


SURVEY_TEMPLATE = (
    "Merhaba {name},\n"
    "Dünkü ziyaretiniz için teşekkürler. Hizmetimizden memnuniyet seviyenizi\n"
    "1-5 arası puanlayabilir misiniz?\n\n"
    "Cevap: 1 (kötü) 2 3 4 5 (çok iyi)\n"
    "Eklemek istediğiniz bir not varsa lütfen yazın.\n\n"
    "Saygılarımla,\n"
    "Op. Dr. Hakan Yaz"
)

BIRTHDAY_TEMPLATE = (
    "Sevgili {name},\n"
    "Doğum gününüz kutlu olsun! Sağlık, mutluluk ve güzelliklerle dolu\n"
    "bir yaş dilerim.\n\n"
    "- Op. Dr. Hakan Yaz"
)


@dataclass
class CronResult:
    job: str
    ran_at: str
    target_count: int = 0
    sent_count: int = 0
    errors: List[str] = field(default_factory=list)
    preview_messages: List[Dict[str, str]] = field(default_factory=list)
    dry_run: bool = False
    agent_version: str = AGENT_VERSION


def _send_whatsapp(phone: str, text: str) -> bool:
    try:
        from yazklinik_whatsapp_local_helper import send_whatsapp_message
        send_whatsapp_message(phone, text)
        return True
    except Exception:
        return False


def _table_columns(con: sqlite3.Connection, table: str) -> List[str]:
    try:
        return [str(r[1]) for r in con.execute(f"PRAGMA table_info({table})").fetchall()]
    except Exception:
        return []


def _patient_display_expr(alias: str = "p", demo_alias: str = "d") -> str:
    return (
        f"COALESCE(NULLIF({demo_alias}.canonical_name, ''), "
        f"NULLIF({alias}.display_name, ''), {alias}.folder_key)"
    )


def _first_name(name: str) -> str:
    clean = (name or "").strip()
    return clean.split()[0] if clean else "Hasta"


def _safe_phone(value: Any) -> str:
    return str(value or "").strip()


def _send_or_preview(rpt: CronResult, patient_id: str, name: str,
                     phone: str, text: str, dry_run: bool) -> None:
    if dry_run:
        rpt.preview_messages.append({
            "patient_id": str(patient_id or ""),
            "name": str(name or ""),
            "phone": phone,
            "text": text,
        })
        return
    if _send_whatsapp(phone, text):
        rpt.sent_count += 1
    else:
        rpt.errors.append(f"send_failed: {patient_id}")


def send_survey_for_yesterday(db_path: Optional[str] = None,
                              dry_run: bool = False) -> CronResult:
    """Dun gelen hastalara memnuniyet anketi."""
    db_path = db_path or DEFAULT_DB_PATH
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    rpt = CronResult(job="memnuniyet_survey",
                      ran_at=datetime.now().isoformat(timespec="seconds"),
                      dry_run=bool(dry_run))

    con = _pgconn(sqlite_path=db_path)
    con.row_factory = sqlite3.Row
    try:
        patient_cols = set(_table_columns(con, "patients"))
        visit_cols = set(_table_columns(con, "visits"))
        demo_cols = set(_table_columns(con, "patient_demographics"))

        if {"folder_key", "display_name"}.issubset(patient_cols) and "patient_folder_key" in visit_cols:
            phone_expr = "d.phone" if "phone" in demo_cols else "''"
            name_expr = _patient_display_expr("p", "d") if "canonical_name" in demo_cols else (
                "COALESCE(NULLIF(p.display_name, ''), p.folder_key)"
            )
            rows = con.execute(
                f"SELECT DISTINCT p.folder_key AS patient_id, {name_expr} AS name, "
                f"{phone_expr} AS phone "
                "FROM patients p "
                "JOIN visits v ON v.patient_folder_key = p.folder_key "
                "LEFT JOIN patient_demographics d ON d.patient_key = p.folder_key "
                "WHERE date(v.visit_date) = ? "
                "AND COALESCE(p.archived_at, '') = '' "
                "AND COALESCE(d.phone, '') != ''",
                (yesterday,),
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT DISTINCT p.id AS patient_id, p.name AS name, p.phone AS phone "
                "FROM patients p JOIN visits v ON v.patient_id = p.id "
                "WHERE date(v.visit_date) = ? AND p.phone IS NOT NULL "
                "AND p.phone != ''",
                (yesterday,),
            ).fetchall()
        rpt.target_count = len(rows)
        for r in rows:
            try:
                phone = _safe_phone(r["phone"])
                if not phone:
                    continue
                first = _first_name(r["name"])
                _send_or_preview(
                    rpt,
                    str(r["patient_id"]),
                    str(r["name"] or ""),
                    phone,
                    SURVEY_TEMPLATE.format(name=first),
                    dry_run=bool(dry_run),
                )
            except Exception as e:
                rpt.errors.append(f"{r['patient_id']}: {e}")
    except Exception as e:
        rpt.errors.append(f"db_error: {e}")
    finally:
        con.close()
    return rpt


def send_birthday_today(db_path: Optional[str] = None,
                        dry_run: bool = False) -> CronResult:
    """Bugun dogan hastalara tebrik."""
    db_path = db_path or DEFAULT_DB_PATH
    today_md = date.today().strftime("%m-%d")
    rpt = CronResult(job="birthday_wishes",
                      ran_at=datetime.now().isoformat(timespec="seconds"),
                      dry_run=bool(dry_run))

    con = _pgconn(sqlite_path=db_path)
    con.row_factory = sqlite3.Row
    try:
        patient_cols = set(_table_columns(con, "patients"))
        demo_cols = set(_table_columns(con, "patient_demographics"))

        if {"folder_key", "display_name"}.issubset(patient_cols) and "birth_date" in demo_cols:
            phone_expr = "d.phone" if "phone" in demo_cols else "''"
            name_expr = _patient_display_expr("p", "d") if "canonical_name" in demo_cols else (
                "COALESCE(NULLIF(p.display_name, ''), p.folder_key)"
            )
            rows = con.execute(
                f"SELECT p.folder_key AS patient_id, {name_expr} AS name, "
                f"{phone_expr} AS phone, d.birth_date AS birth_date "
                "FROM patients p "
                "JOIN patient_demographics d ON d.patient_key = p.folder_key "
                "WHERE d.birth_date IS NOT NULL "
                "AND COALESCE(p.archived_at, '') = '' "
                "AND COALESCE(d.phone, '') != ''"
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT id AS patient_id, name, phone, birth_date FROM patients "
                "WHERE birth_date IS NOT NULL AND phone IS NOT NULL AND phone != ''"
            ).fetchall()
        for r in rows:
            try:
                bd = r["birth_date"]
                if bd and bd[5:10] == today_md:
                    rpt.target_count += 1
                    phone = _safe_phone(r["phone"])
                    if not phone:
                        continue
                    first = _first_name(r["name"])
                    _send_or_preview(
                        rpt,
                        str(r["patient_id"]),
                        str(r["name"] or ""),
                        phone,
                        BIRTHDAY_TEMPLATE.format(name=first),
                        dry_run=bool(dry_run),
                    )
            except Exception as e:
                rpt.errors.append(f"{r['patient_id']}: {e}")
    except Exception as e:
        rpt.errors.append(f"db_error: {e}")
    finally:
        con.close()
    return rpt


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION}


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
