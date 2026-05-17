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
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-memnuniyet"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")


SURVEY_TEMPLATE = (
    "Merhaba {name},\n"
    "Dunku ziyaretiniz icin tesekkurler. Hizmetimizden memnuniyet seviyenizi\n"
    "1-5 arasi puanlayabilir misiniz?\n\n"
    "Cevap: 1 (kotu) 2 3 4 5 (cok iyi)\n"
    "Eklemek istediginiz bir not varsa lutfen yazin.\n\n"
    "Saygilarimla,\n"
    "Op. Dr. Hakan Yaz"
)

BIRTHDAY_TEMPLATE = (
    "Sevgili {name},\n"
    "Dogum gununuz kutlu olsun! Saglik, mutluluk ve guzelliklerle dolu\n"
    "bir yas dilerim.\n\n"
    "- Op. Dr. Hakan Yaz"
)


@dataclass
class CronResult:
    job: str
    ran_at: str
    target_count: int = 0
    sent_count: int = 0
    errors: List[str] = field(default_factory=list)
    agent_version: str = AGENT_VERSION


def _send_whatsapp(phone: str, text: str) -> bool:
    try:
        from yazklinik_whatsapp_local_helper import send_whatsapp_message
        send_whatsapp_message(phone, text)
        return True
    except Exception:
        return False


def send_survey_for_yesterday(db_path: Optional[str] = None) -> CronResult:
    """Dun gelen hastalara memnuniyet anketi."""
    db_path = db_path or DEFAULT_DB_PATH
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    rpt = CronResult(job="memnuniyet_survey",
                      ran_at=datetime.now().isoformat(timespec="seconds"))

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT DISTINCT p.id, p.name, p.phone FROM patients p "
            "JOIN visits v ON v.patient_id = p.id "
            "WHERE date(v.visit_date) = ? AND p.phone IS NOT NULL "
            "AND p.phone != ''", (yesterday,)).fetchall()
        rpt.target_count = len(rows)
        for r in rows:
            try:
                first = (r["name"] or "").split()[0] if r["name"] else "Hasta"
                if _send_whatsapp(r["phone"], SURVEY_TEMPLATE.format(name=first)):
                    rpt.sent_count += 1
                else:
                    rpt.errors.append(f"send_failed: {r['id']}")
            except Exception as e:
                rpt.errors.append(f"{r['id']}: {e}")
    except Exception as e:
        rpt.errors.append(f"db_error: {e}")
    finally:
        con.close()
    return rpt


def send_birthday_today(db_path: Optional[str] = None) -> CronResult:
    """Bugun dogan hastalara tebrik."""
    db_path = db_path or DEFAULT_DB_PATH
    today_md = date.today().strftime("%m-%d")
    rpt = CronResult(job="birthday_wishes",
                      ran_at=datetime.now().isoformat(timespec="seconds"))

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT id, name, phone, birth_date FROM patients "
            "WHERE birth_date IS NOT NULL AND phone IS NOT NULL AND phone != ''"
        ).fetchall()
        for r in rows:
            try:
                bd = r["birth_date"]
                if bd and bd[5:10] == today_md:
                    rpt.target_count += 1
                    first = (r["name"] or "").split()[0] if r["name"] else "Hasta"
                    if _send_whatsapp(r["phone"], BIRTHDAY_TEMPLATE.format(name=first)):
                        rpt.sent_count += 1
                    else:
                        rpt.errors.append(f"send_failed: {r['id']}")
            except Exception as e:
                rpt.errors.append(f"{r['id']}: {e}")
    except Exception as e:
        rpt.errors.append(f"db_error: {e}")
    finally:
        con.close()
    return rpt


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION}


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
