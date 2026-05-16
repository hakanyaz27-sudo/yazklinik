"""Hasta Geri Cagirma Ajani.

Kontrol zamani yaklasan / muayene sonrasi takip gerektiren hastalari
WhatsApp veya SMS ile hatirlatma kuyruguna alir.

Kurallar (doktor onayli, KVKK guvenli):
    - Sadece kontrol / takip / asi hatirlatmasi gonderir
    - Klinik bilgi / sonuc / tani PAYLAÅMAZ
    - Ayda ayni hastaya en fazla 2 mesaj
    - Hasta "vazgec / abone degil" derse o numarayi blokliste alir
    - Tum mesajlar doktor sablonundan secilir, AI mesaj YAZMAZ

Web layer hangi hastalarin uygun oldugunu sorgular ve mesaj sablonlarini
secen ekrani sunar. Bu modul kim - ne zaman - hangi sablon karari verir.

Stdlib only.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


AGENT_VERSION = "2026.05.16-geri-cagirma"
SOURCE_LABEL = "Geri cagirma kuyrugu"

CHANNEL_OPTIONS = ("whatsapp", "sms")
MAX_REMINDERS_PER_MONTH = 2

# Standart sablonlar - degisken {ad}, {tarih}, {gun_sayisi}
TEMPLATES: Dict[str, str] = {
    "gebelik_kontrol": (
        "Sayin {ad}, planlanan gebelik kontrol randevunuza "
        "{gun_sayisi} gun kalmistir. Onaylamak icin lutfen donus yapin."
    ),
    "smear_yenileme": (
        "Sayin {ad}, smear takibiniz icin yenileme zamani yaklasti. "
        "Randevu icin lutfen klinikten donus alin."
    ),
    "asi_hatirlatma": (
        "Sayin {ad}, asi takvimine gore {tarih} tarihinde "
        "yapilmasi planlanan asiniz icin randevu olusturalim mi?"
    ),
    "postop_takip": (
        "Sayin {ad}, operasyon sonrasi 1. hafta kontrolunuz icin "
        "uygun saatte bekliyoruz. Lutfen donus yapin."
    ),
    "yillik_kontrol": (
        "Sayin {ad}, yillik jinekolojik kontrol zamaniniz yaklasti. "
        "Randevu icin donus yapabilirsiniz."
    ),
    "ilac_yenileme": (
        "Sayin {ad}, devam ilaclariniz icin recete yenileme "
        "randevusu olusturmamizi ister misiniz?"
    ),
}


@dataclass
class PatientCandidate:
    """Web layer'dan gelen aday hasta minimum verisi."""
    patient_id: str
    name: str
    phone: str
    last_visit: Optional[str] = None       # ISO date
    next_due: Optional[str] = None         # ISO date - hatirlatma takvimine gore
    reason: str = ""                       # 'gebelik_kontrol' gibi sablon anahtari
    consent_messaging: bool = False        # KVKK iletisim onayi
    sent_this_month: int = 0
    blocked: bool = False


@dataclass
class ReminderJob:
    patient_id: str
    name: str
    phone: str
    channel: str
    template_key: str
    rendered_text: str
    scheduled_for: str                     # ISO datetime
    reason: str
    requires_doctor_review: bool = False
    skip_reason: Optional[str] = None
    agent_version: str = AGENT_VERSION


def _normalize_phone(phone: str) -> str:
    digits = re.sub(r"\D", "", str(phone or ""))
    if not digits:
        return ""
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


def days_between(from_date: Optional[str], to_date: Optional[str]) -> Optional[int]:
    try:
        a = date.fromisoformat(from_date) if from_date else None
        b = date.fromisoformat(to_date) if to_date else None
    except Exception:
        return None
    if not a or not b:
        return None
    return (b - a).days


def render_template(template_key: str, name: str, target_date: Optional[str]) -> str:
    template = TEMPLATES.get(template_key, "")
    if not template:
        return ""
    gun_sayisi = days_between(date.today().isoformat(), target_date) if target_date else None
    return template.format(
        ad=name.strip().split()[0] if name else "Hasta",
        tarih=target_date or "",
        gun_sayisi=gun_sayisi if gun_sayisi is not None else "yaklasik 7",
    )


def should_skip(p: PatientCandidate) -> Optional[str]:
    """Bos string degil, sebep dondurur (varsa)."""
    if p.blocked:
        return "Hasta mesajlasma listesinden cikarilmis."
    if not p.consent_messaging:
        return "Iletisim icin KVKK acik rizasi yok."
    phone = _normalize_phone(p.phone)
    if len(phone) != 10:
        return f"Telefon dogrulanamadi ({p.phone})."
    if p.sent_this_month >= MAX_REMINDERS_PER_MONTH:
        return f"Bu ay {p.sent_this_month} mesaj zaten gonderilmis (limit {MAX_REMINDERS_PER_MONTH})."
    if not p.reason or p.reason not in TEMPLATES:
        return f"Gecersiz hatirlatma sebebi: {p.reason!r}"
    if not p.next_due:
        return "next_due tarihi belirsiz."
    diff = days_between(date.today().isoformat(), p.next_due)
    if diff is None:
        return "next_due tarihi okunamadi."
    if diff < -3:
        return f"Tarih {abs(diff)} gun gecmis - geri donus icin doktor karari gerek."
    if diff > 30:
        return f"Tarihe {diff} gun var - su an icin erken."
    return None


def schedule_reminder(p: PatientCandidate, channel: str = "whatsapp",
                      lead_time_days: int = 2) -> ReminderJob:
    """Tek hasta icin hatirlatma issi olustur (zamanlanmis veya skip)."""
    skip = should_skip(p)
    target_dt = ""
    rendered = ""

    if skip:
        return ReminderJob(
            patient_id=str(p.patient_id),
            name=p.name,
            phone=_normalize_phone(p.phone),
            channel=channel,
            template_key=p.reason or "",
            rendered_text="",
            scheduled_for="",
            reason=p.reason,
            requires_doctor_review=True,
            skip_reason=skip,
        )

    if channel not in CHANNEL_OPTIONS:
        channel = "whatsapp"

    # Hatirlatma gun zamanlamasi: next_due'dan lead_time_days once, 10:00
    try:
        due = date.fromisoformat(p.next_due or "")
        send_day = due - timedelta(days=lead_time_days)
        if send_day < date.today():
            send_day = date.today()
        target_dt = datetime.combine(send_day, datetime.min.time()).replace(hour=10).isoformat(timespec="seconds")
    except Exception:
        target_dt = (datetime.now() + timedelta(days=1)).replace(hour=10, minute=0, second=0).isoformat(timespec="seconds")

    rendered = render_template(p.reason, p.name, p.next_due)

    return ReminderJob(
        patient_id=str(p.patient_id),
        name=p.name,
        phone=_normalize_phone(p.phone),
        channel=channel,
        template_key=p.reason,
        rendered_text=rendered,
        scheduled_for=target_dt,
        reason=p.reason,
        requires_doctor_review=False,
        skip_reason=None,
    )


def bulk_schedule(candidates: List[PatientCandidate], channel: str = "whatsapp") -> Dict[str, List[ReminderJob]]:
    queued: List[ReminderJob] = []
    skipped: List[ReminderJob] = []
    for c in candidates:
        job = schedule_reminder(c, channel=channel)
        (skipped if job.skip_reason else queued).append(job)
    return {"queued": queued, "skipped": skipped}


def to_audit_payload(job: ReminderJob) -> Dict[str, Any]:
    payload = asdict(job)
    payload["action"] = "geri_cagirma:" + ("skip" if job.skip_reason else "schedule")
    return payload


if __name__ == "__main__":
    today = date.today()
    samples = [
        PatientCandidate("P1", "Ayse Yilmaz", "05551112233",
                         next_due=(today + timedelta(days=5)).isoformat(),
                         reason="gebelik_kontrol", consent_messaging=True),
        PatientCandidate("P2", "Fatma K.", "05552223344",
                         next_due=(today + timedelta(days=14)).isoformat(),
                         reason="smear_yenileme", consent_messaging=True, sent_this_month=2),
        PatientCandidate("P3", "Selin A.", "0555",
                         next_due=(today + timedelta(days=3)).isoformat(),
                         reason="postop_takip", consent_messaging=True),
        PatientCandidate("P4", "Esra D.", "05554445566",
                         next_due=(today - timedelta(days=10)).isoformat(),
                         reason="yillik_kontrol", consent_messaging=True),
        PatientCandidate("P5", "Demo", "05556667788",
                         next_due=(today + timedelta(days=7)).isoformat(),
                         reason="ilac_yenileme", consent_messaging=False),
    ]
    result = bulk_schedule(samples)
    print(f"Queued: {len(result['queued'])}  Skipped: {len(result['skipped'])}")
    for j in result["queued"]:
        print(f"  -> {j.scheduled_for} | {j.phone} | {j.rendered_text[:60]}...")
    for j in result["skipped"]:
        print(f"  SKIP {j.patient_id}: {j.skip_reason}")
