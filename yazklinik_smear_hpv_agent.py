"""Smear / HPV / Gebelik Takip Ajani.

Hastanin smear + HPV + jinekolojik tarama takip listesi:
    - Son smear tarihi -> sonraki tarama tarihi (kilavuzlara gore)
    - HPV pozitif ise: kolposkopi / takip plani
    - Gebelik tedavi protokolu (4 hafta, 8 hafta vs)
    - Otomatik hatirlatma uretir
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-smear-hpv"


@dataclass
class SmearRecord:
    patient_id: str
    smear_date: str        # ISO date
    smear_result: str      # NILM | ASCUS | LSIL | HSIL | AGC | SCC | inadequate
    hpv_test: str = ""     # negative | positive | hr_positive | hr16 | hr18
    age: int = 30
    is_pregnant: bool = False
    immunosuppressed: bool = False


@dataclass
class FollowupPlan:
    patient_id: str
    plan: str              # routine_3y | hpv_1y | colpo | leep | annual
    next_action: str
    next_due_date: str
    rationale: str
    urgency: str = "routine"   # routine | high | urgent
    agent_version: str = AGENT_VERSION


def compute_followup(rec: SmearRecord) -> FollowupPlan:
    """ASCCP 2019 + TUBITAK rehberi (basitlestirilmis)."""
    try:
        last = datetime.fromisoformat(rec.smear_date).date()
    except Exception:
        last = date.today()

    p = FollowupPlan(patient_id=rec.patient_id, plan="", next_action="",
                      next_due_date="", rationale="", urgency="routine")

    result = (rec.smear_result or "").upper()
    hpv = (rec.hpv_test or "").lower()

    if result in ("HSIL", "AGC", "SCC"):
        p.plan = "colpo"
        p.next_action = "Kolposkopi + biyopsi (ASAP)"
        p.next_due_date = (last + timedelta(days=14)).isoformat()
        p.urgency = "urgent"
        p.rationale = "HSIL/AGC/SCC: derhal kolposkopi"
    elif result == "LSIL":
        if rec.age >= 25:
            p.plan = "colpo"
            p.next_action = "Kolposkopi"
            p.next_due_date = (last + timedelta(days=30)).isoformat()
            p.urgency = "high"
            p.rationale = "LSIL >25y -> kolposkopi"
        else:
            p.plan = "hpv_1y"
            p.next_action = "1 yil sonra smear + HPV"
            p.next_due_date = (last + timedelta(days=365)).isoformat()
            p.rationale = "LSIL <25y -> 1 yil takip"
    elif result == "ASCUS":
        if hpv == "negative":
            p.plan = "routine_3y"
            p.next_action = "3 yil sonra rutin tarama"
            p.next_due_date = (last + timedelta(days=3*365)).isoformat()
            p.rationale = "ASCUS HPV-neg: dusuk risk"
        elif hpv in ("positive", "hr_positive", "hr16", "hr18"):
            p.plan = "colpo"
            p.next_action = "Kolposkopi"
            p.next_due_date = (last + timedelta(days=30)).isoformat()
            p.urgency = "high"
            p.rationale = "ASCUS HPV+ -> kolposkopi"
        else:
            p.plan = "hpv_1y"
            p.next_action = "HPV testi yapilmali"
            p.next_due_date = (last + timedelta(days=30)).isoformat()
            p.rationale = "ASCUS -> reflex HPV"
    elif result == "NILM":
        if hpv in ("hr16", "hr18"):
            p.plan = "colpo"
            p.next_action = "Kolposkopi (HPV 16/18 pozitif)"
            p.next_due_date = (last + timedelta(days=30)).isoformat()
            p.urgency = "high"
            p.rationale = "NILM ama HPV 16/18 pozitif"
        elif hpv in ("positive", "hr_positive"):
            p.plan = "hpv_1y"
            p.next_action = "1 yil sonra HPV + smear"
            p.next_due_date = (last + timedelta(days=365)).isoformat()
            p.rationale = "NILM + HPV+ -> 1 yil takip"
        else:
            p.plan = "routine_3y"
            p.next_action = "3 yil sonra rutin tarama (HPV) veya 5 yil (co-test)"
            p.next_due_date = (last + timedelta(days=3*365)).isoformat()
            p.rationale = "NILM HPV-neg: dusuk risk"
    elif result == "INADEQUATE":
        p.plan = "repeat"
        p.next_action = "2-4 ay icinde tekrar smear"
        p.next_due_date = (last + timedelta(days=90)).isoformat()
        p.rationale = "Yetersiz numune -> tekrar"
    else:
        p.plan = "routine_3y"
        p.next_action = "Tanim disi sonuc - 1 yil sonra tekrar"
        p.next_due_date = (last + timedelta(days=365)).isoformat()
        p.rationale = f"Bilinmeyen sonuc: {result}"

    # Gebelik durumu
    if rec.is_pregnant and p.urgency == "urgent":
        p.next_action += " (Gebelik nedeniyle dogum sonrasi)"
        p.rationale += " | Gebelikte konizasyon ertelenir"

    # Immunsupresif
    if rec.immunosuppressed and p.plan == "routine_3y":
        p.plan = "annual"
        p.next_action = "Yillik tarama (immunsupresif)"
        p.next_due_date = (last + timedelta(days=365)).isoformat()

    return p


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION}


if __name__ == "__main__":
    r = SmearRecord(patient_id="P-001", smear_date="2025-11-10",
                     smear_result="ASCUS", hpv_test="positive", age=42)
    p = compute_followup(r)
    print(json.dumps(asdict(p), ensure_ascii=False, indent=2))
