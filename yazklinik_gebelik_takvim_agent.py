"""Gebelik Haftasi Akilli Hatirlatma Ajani.

Hasta gebeligi yorulmadan: 11-14, 18-22, 24-28, 28, 35-37, 37 haftalar
otomatik agenda + hasta + doktor hatirlatma.

PROTOKOL (TJOD + ACOG):
    11-14 hf   : NT, ucl test
    16 hf      : Erken AFP (opsiyonel)
    18-22 hf   : Detayli ultrason (morfolojik)
    20 hf      : Quad/triple test (yapilmamissa)
    24-28 hf   : GDM tarama (OGTT 75g)
    28 hf      : RhD-neg ise anti-D
    28-32 hf   : Demir+folik kontrolu
    35-37 hf   : GBS surveyensi
    37 hf      : Dogum cantasi hatirlatma
    40 hf      : Term, post-term plan
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-gebelik-takvim"

GA_MILESTONES = [
    {"week": (11, 14), "task": "NT olcumu + ucl test",
     "priority": "high", "patient_msg": "11-14 hafta arasi ense kalinligi olcumu",
     "doctor_remind_days_before": 7},
    {"week": (18, 22), "task": "Detayli ultrasonografi (morfolojik tarama)",
     "priority": "critical", "patient_msg": "Bebeginizin organlarini detayli inceleyecegiz",
     "doctor_remind_days_before": 14},
    {"week": (24, 28), "task": "75g OGTT (GDM tarama)",
     "priority": "high", "patient_msg": "Seker yukleme testi yapacagiz",
     "doctor_remind_days_before": 7},
    {"week": (28, 28), "task": "RhD-neg ise anti-D",
     "priority": "high", "patient_msg": "Kan grubunuza gore koruyucu igne",
     "doctor_remind_days_before": 3, "conditional": "rh_neg"},
    {"week": (28, 32), "task": "Demir + folik kontrolu",
     "priority": "medium", "patient_msg": "Vitamin takibi",
     "doctor_remind_days_before": 5},
    {"week": (35, 37), "task": "GBS surveyensi (B grubu strep)",
     "priority": "high", "patient_msg": "Dogum oncesi son onemli tarama",
     "doctor_remind_days_before": 7},
    {"week": (37, 37), "task": "Dogum cantasi hazirlama",
     "priority": "medium", "patient_msg": "Cantaniz hazir mi? Dogum yaklasti",
     "doctor_remind_days_before": 3},
    {"week": (40, 41), "task": "Term + post-term plan",
     "priority": "critical", "patient_msg": "Dogum gunu yaklasti, sik kontrol",
     "doctor_remind_days_before": 1},
]


@dataclass
class GestationalReminder:
    week: int
    task: str
    priority: str
    patient_msg: str
    target_date: str
    days_until: int
    conditional: Optional[str] = None


@dataclass
class GestationalPlan:
    lmp: str                                      # ISO date
    current_ga_weeks: int
    current_ga_days: int
    edd: str                                       # estimated date of delivery
    upcoming_reminders: List[GestationalReminder] = field(default_factory=list)
    overdue_reminders: List[GestationalReminder] = field(default_factory=list)
    completed_milestones: List[str] = field(default_factory=list)
    agent_version: str = AGENT_VERSION


def compute_plan(lmp_iso: str, today: Optional[date] = None,
                  rh_negative: bool = False,
                  completed_tasks: Optional[List[str]] = None) -> GestationalPlan:
    """LMP + bugun -> aktif hatirlatma listesi."""
    today = today or date.today()
    try:
        lmp = date.fromisoformat(lmp_iso)
    except Exception:
        raise ValueError(f"Gecersiz LMP: {lmp_iso}")
    days_pregnant = (today - lmp).days
    weeks = days_pregnant // 7
    days = days_pregnant % 7
    edd = lmp + timedelta(days=280)
    completed = set(completed_tasks or [])

    upcoming = []
    overdue = []
    for m in GA_MILESTONES:
        if m.get("conditional") == "rh_neg" and not rh_negative:
            continue
        wk_start, wk_end = m["week"]
        target_week = wk_start  # use start as anchor
        target_date = lmp + timedelta(days=target_week * 7)
        days_until = (target_date - today).days
        # Olustur reminder
        reminder = GestationalReminder(
            week=target_week, task=m["task"], priority=m["priority"],
            patient_msg=m["patient_msg"], target_date=target_date.isoformat(),
            days_until=days_until, conditional=m.get("conditional"))
        if m["task"] in completed:
            continue
        if days_until < 0 and weeks > wk_end + 2:
            overdue.append(reminder)
        elif -7 <= days_until <= m.get("doctor_remind_days_before", 7) + 7:
            upcoming.append(reminder)
        elif days_until > 0:
            upcoming.append(reminder)

    upcoming.sort(key=lambda r: r.days_until)
    return GestationalPlan(
        lmp=lmp_iso, current_ga_weeks=weeks, current_ga_days=days,
        edd=edd.isoformat(),
        upcoming_reminders=upcoming[:8],
        overdue_reminders=overdue,
        completed_milestones=list(completed))


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "milestones": len(GA_MILESTONES)}


if __name__ == "__main__":
    # 24 hafta gebe ornegi
    test_lmp = (date.today() - timedelta(days=24*7)).isoformat()
    p = compute_plan(test_lmp, rh_negative=True)
    print(f"GA: {p.current_ga_weeks}h{p.current_ga_days}g")
    print(f"EDD: {p.edd}")
    print(f"Upcoming: {len(p.upcoming_reminders)}")
    for r in p.upcoming_reminders[:5]:
        print(f"  [{r.priority}] {r.task} ({r.days_until} gun, hf {r.week})")
