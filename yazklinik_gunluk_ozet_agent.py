"""Gunluk Ozet Ajani.

Gun sonunda doktora gunun ozetini hazirlar:
    - Bugun goren / sonradan gelen / iptal olan hasta sayisi
    - Yarinki randevu tablosu
    - Bekleyen onay kuyruklari (e-Nabiz, BulutKlinik, USG taslak, telefon triyaj)
    - Mali ozet (gunluk gelir, SGK, ozel, anlasmali)
    - Onceki gunlere gore degisim yuzdesi

WhatsApp/e-posta icin sade metin uretir. Doktor kontrolune sunulur.

Asla:
    - Hasta verisini metnin icine koymaz (sadece sayilar ve adlar)
    - SGK fatura beyani yapmaz (sadece kayit gosterir)

Stdlib only.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.16-gunluk-ozet"
SOURCE_LABEL = "Gunluk klinik ozet"


@dataclass
class DailyStats:
    seen_count: int = 0                 # bugun muayene gorunen
    walkin_count: int = 0               # sonradan gelen
    cancelled_count: int = 0
    no_show_count: int = 0
    appointment_total: int = 0          # bugun planlanmis toplam


@dataclass
class FinanceSnapshot:
    cash_try: float = 0.0
    card_try: float = 0.0
    sgk_try: float = 0.0
    private_insurance_try: float = 0.0
    refunds_try: float = 0.0


@dataclass
class PendingQueues:
    enabiz_pending: int = 0
    bk_pending: int = 0
    usg_drafts_pending: int = 0
    voice_triage_pending: int = 0
    voice_confirm_pending: int = 0


@dataclass
class TomorrowSlot:
    time_str: str         # "09:00"
    patient_initials: str # "A.Y."
    appointment_type: str = ""
    notes: str = ""


@dataclass
class SummaryInput:
    for_date: str                       # ISO date
    today: DailyStats = field(default_factory=DailyStats)
    yesterday: Optional[DailyStats] = None
    today_finance: FinanceSnapshot = field(default_factory=FinanceSnapshot)
    queues: PendingQueues = field(default_factory=PendingQueues)
    tomorrow: List[TomorrowSlot] = field(default_factory=list)


@dataclass
class DailySummary:
    for_date: str
    text_plain: str
    text_short: str                     # < 320 karakter WhatsApp icin
    metrics: Dict[str, Any] = field(default_factory=dict)
    requires_doctor_review: bool = False
    agent_version: str = AGENT_VERSION


def _pct_change(now: int, prev: Optional[int]) -> str:
    if prev is None or prev == 0:
        return ""
    diff = now - prev
    pct = (diff / prev) * 100
    sign = "+" if diff >= 0 else ""
    return f" ({sign}{pct:.0f}% vs dun)"


def _total_finance(f: FinanceSnapshot) -> float:
    return round(f.cash_try + f.card_try + f.sgk_try + f.private_insurance_try - f.refunds_try, 2)


def build_summary(data: SummaryInput) -> DailySummary:
    """Ana giris noktasi."""
    total = _total_finance(data.today_finance)
    yest = data.yesterday

    lines: List[str] = []
    lines.append(f"YazKlinik gunluk ozet - {data.for_date}")
    lines.append("")
    lines.append("HASTA TRAFIGI:")
    lines.append(f"  - Planlanan: {data.today.appointment_total}")
    lines.append(f"  - Gorulen:   {data.today.seen_count}" + _pct_change(data.today.seen_count, yest.seen_count if yest else None))
    lines.append(f"  - Walk-in:   {data.today.walkin_count}")
    lines.append(f"  - Iptal:     {data.today.cancelled_count}")
    lines.append(f"  - Gelmedi:   {data.today.no_show_count}")

    lines.append("")
    lines.append("MALI:")
    lines.append(f"  - Nakit:     {data.today_finance.cash_try:>10.2f} TRY")
    lines.append(f"  - Kart:      {data.today_finance.card_try:>10.2f} TRY")
    lines.append(f"  - SGK:       {data.today_finance.sgk_try:>10.2f} TRY")
    lines.append(f"  - Anlasmali: {data.today_finance.private_insurance_try:>10.2f} TRY")
    if data.today_finance.refunds_try:
        lines.append(f"  - Iade:     -{data.today_finance.refunds_try:>9.2f} TRY")
    lines.append(f"  - TOPLAM:    {total:>10.2f} TRY")

    q = data.queues
    pending_total = (q.enabiz_pending + q.bk_pending + q.usg_drafts_pending
                     + q.voice_triage_pending + q.voice_confirm_pending)
    if pending_total:
        lines.append("")
        lines.append("BEKLEYEN ONAYLAR:")
        if q.enabiz_pending:
            lines.append(f"  - e-Nabiz PDF:        {q.enabiz_pending}")
        if q.bk_pending:
            lines.append(f"  - BulutKlinik:        {q.bk_pending}")
        if q.usg_drafts_pending:
            lines.append(f"  - USG taslak:         {q.usg_drafts_pending}")
        if q.voice_triage_pending:
            lines.append(f"  - Telesekreter:       {q.voice_triage_pending}")
        if q.voice_confirm_pending:
            lines.append(f"  - Sesli onay belirsiz:{q.voice_confirm_pending}")

    if data.tomorrow:
        lines.append("")
        lines.append("YARIN PROGRAMI:")
        for s in data.tomorrow:
            extra = f" - {s.appointment_type}" if s.appointment_type else ""
            note = f" ({s.notes})" if s.notes else ""
            lines.append(f"  {s.time_str:5}  {s.patient_initials:8}{extra}{note}")

    text_plain = "\n".join(lines)

    # Kisa surum (WhatsApp)
    short = (
        f"Bugun: gorulen {data.today.seen_count}/{data.today.appointment_total}, "
        f"ciro {total:.0f} TRY"
    )
    if pending_total:
        short += f", bekleyen onay {pending_total}"
    if data.tomorrow:
        short += f", yarin {len(data.tomorrow)} randevu"

    return DailySummary(
        for_date=str(data.for_date),
        text_plain=text_plain,
        text_short=short[:320],
        metrics={
            "total_finance_try": total,
            "appointments_total": data.today.appointment_total,
            "appointments_seen": data.today.seen_count,
            "pending_queues_total": pending_total,
            "tomorrow_slots": len(data.tomorrow),
        },
        requires_doctor_review=False,
    )


def to_audit_payload(summary: DailySummary) -> Dict[str, Any]:
    payload = asdict(summary)
    payload["action"] = "gunluk_ozet:hazir"
    return payload


if __name__ == "__main__":
    today = date.today().isoformat()
    sample = SummaryInput(
        for_date=today,
        today=DailyStats(seen_count=14, walkin_count=2, cancelled_count=1, no_show_count=1, appointment_total=18),
        yesterday=DailyStats(seen_count=11, appointment_total=14),
        today_finance=FinanceSnapshot(cash_try=2200, card_try=4500, sgk_try=1800, private_insurance_try=600),
        queues=PendingQueues(enabiz_pending=2, usg_drafts_pending=3, voice_triage_pending=1),
        tomorrow=[
            TomorrowSlot("09:00", "A.Y.", "kontrol"),
            TomorrowSlot("10:30", "F.K.", "ilk muayene"),
            TomorrowSlot("14:00", "Z.B.", "USG"),
        ],
    )
    s = build_summary(sample)
    print(s.text_plain)
    print("\n---KISA---")
    print(s.text_short)
