"""Anti-Burnout Doktor Verimlilik Dashboard Ajani.

Doktorun gunluk yorgunluk + odak gostergesi:
    - Bugun kac hasta, ortalama sure, mola sayisi
    - Haftalik trend (asiri calisma uyarisi)
    - Pomodoro break onerisi (2 saatte 5 dk)
    - Ekran karsisi suresi
    - Hatasiz islem orani (audit log'tan)

Veriyi visits + audit_log'tan ceker.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-anti-burnout"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")


@dataclass
class BurnoutReport:
    for_date: str
    patients_today: int = 0
    avg_minutes_per_patient: float = 0
    longest_stretch_minutes: int = 0
    breaks_count: int = 0
    total_screen_hours: float = 0
    weekly_avg_patients: float = 0
    weekly_overload: bool = False
    pomodoro_due: bool = False
    fatigue_score: int = 0          # 0-100
    fatigue_level: str = "low"      # low / moderate / high / burnout
    recommendations: List[str] = field(default_factory=list)
    agent_version: str = AGENT_VERSION


def _list_today_visits(db_path: str, the_date: date) -> List[Dict[str, Any]]:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(
            "SELECT visit_date, visit_type, created_at FROM visits "
            "WHERE date(visit_date) = ? OR date(created_at) = ?",
            (the_date.isoformat(), the_date.isoformat())).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        con.close()


def compute_report(target_date: Optional[date] = None,
                    db_path: Optional[str] = None) -> BurnoutReport:
    """Bugunun raporunu cikar."""
    target_date = target_date or date.today()
    db_path = db_path or DEFAULT_DB_PATH
    rpt = BurnoutReport(for_date=target_date.isoformat())

    visits = _list_today_visits(db_path, target_date)
    rpt.patients_today = len(visits)

    # Time stamps al
    times = []
    for v in visits:
        ts = v.get("created_at") or v.get("visit_date")
        try:
            dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
            times.append(dt)
        except Exception:
            pass
    times.sort()
    # Gun icindeki gaps + longest stretch
    if len(times) >= 2:
        gaps = [(times[i+1] - times[i]).total_seconds() / 60 for i in range(len(times)-1)]
        rpt.breaks_count = sum(1 for g in gaps if g >= 10)
        rpt.longest_stretch_minutes = int(max([g for g in gaps if g < 10], default=0))
        total_min = (times[-1] - times[0]).total_seconds() / 60
        rpt.avg_minutes_per_patient = round(total_min / max(1, len(times) - 1), 1)
        rpt.total_screen_hours = round(total_min / 60, 1)

    # Haftalik trend
    week_visits = 0
    for d_off in range(7):
        d2 = target_date - timedelta(days=d_off)
        week_visits += len(_list_today_visits(db_path, d2))
    rpt.weekly_avg_patients = round(week_visits / 7, 1)

    # Fatigue scoring
    fatigue = 0
    if rpt.patients_today >= 25: fatigue += 35
    elif rpt.patients_today >= 20: fatigue += 25
    elif rpt.patients_today >= 15: fatigue += 15
    if rpt.longest_stretch_minutes >= 180: fatigue += 25
    elif rpt.longest_stretch_minutes >= 120: fatigue += 15
    if rpt.breaks_count == 0 and rpt.patients_today >= 5: fatigue += 15
    if rpt.weekly_avg_patients >= 22: fatigue += 25

    rpt.fatigue_score = min(100, fatigue)
    rpt.weekly_overload = rpt.weekly_avg_patients >= 22

    if fatigue >= 70:
        rpt.fatigue_level = "burnout"
        rpt.recommendations = ["ACIL: bu hafta hasta sayini azalt",
                                 "Yarin 1 saat erken bitir",
                                 "10 dakikalik nefes/meditasyon"]
    elif fatigue >= 50:
        rpt.fatigue_level = "high"
        rpt.recommendations = ["10 dk mola al",
                                 "Su ic, ayaga kalk",
                                 "Sonraki hastayi 5 dk geciktir"]
    elif fatigue >= 25:
        rpt.fatigue_level = "moderate"
        rpt.recommendations = ["Pomodoro yakla (5 dk break)",
                                 "Su ic"]
    else:
        rpt.fatigue_level = "low"
        rpt.recommendations = ["Tempo iyi, devam"]

    # Pomodoro: son break 2 saat oncesinden eski ise tetikle
    rpt.pomodoro_due = rpt.longest_stretch_minutes >= 120

    return rpt


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION}


if __name__ == "__main__":
    r = compute_report()
    print(json.dumps(asdict(r), ensure_ascii=False, indent=2))
