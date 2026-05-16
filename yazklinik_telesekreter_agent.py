"""YZ Telesekreter Ajani.

Doktor mesguliken / kapali iken gelen aramalari karsilar.
- Caller-ID + sesli mesaj transkriptini alir
- Niyet siniflandirir: yeni randevu / iptal / acil / bilgi / spam
- Aciliyet skoru ve uygun saat onerisi cikarir
- Doktor onayina aday olarak dusurur

Mimari:
    Asterisk/3CX/sip2sip ya da Twilio webhook -> POST /api/telesekreter/cagri
    Web layer bu modulun parse_call(...) fonksiyonunu cagirir.
    Sonuc yazklinik_web tarafindan onay kuyruguna yazilir.

Asla yapmaz:
    - Hastaya doktor onayi olmadan klinik bilgi vermez
    - Randevuyu otomatik kesinlestirmez (sesli_onay_agent o is icin)
    - Caller listesini disariya gondermez

Stdlib + dataclass; web/STT/TTS baglantilari web layer'da yapilir.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple


AGENT_VERSION = "2026.05.16-telesekreter"
SOURCE_LABEL = "Telesekreter cagri kaydi"

# Aciliyet anahtar kelimeleri (kucuk harf, ASCII katlanmis)
URGENT_KEYWORDS = (
    "acil", "kanama", "su geldi", "sancim", "sancilarim",
    "kasilma", "kasiliyor", "agriyor cok", "dusuk", "dusurdum",
    "bayildi", "bilincim", "112", "hastane git", "ates", "yuksek ates",
)
NEW_APPT_KEYWORDS = (
    "randevu", "muayene", "gelmek istiyorum", "gelebilir miyim",
    "uygun mu", "bos saat", "kontrol", "ilk muayene", "gebelik kontrol",
)
CANCEL_KEYWORDS = (
    "iptal", "gelemeyecegim", "gelemiyorum", "ertelemek", "erteleyebilir",
)
INFO_KEYWORDS = (
    "fiyat", "ucret", "adres", "nerede", "calisma saat", "acik mi",
    "anlasmali mi", "sigorta",
)
SPAM_HINTS = (
    "kampanya", "promosyon", "kredi", "fatura odeme", "size ozel teklif",
)


@dataclass
class CallRecord:
    caller_phone: str
    transcript: str
    received_at: str = ""
    duration_sec: int = 0
    caller_name: Optional[str] = None


@dataclass
class TriagedCall:
    caller_phone: str
    transcript: str
    received_at: str
    intent: str                       # "appointment_new" | "appointment_cancel" | "urgent" | "info" | "spam" | "other"
    urgency: int                      # 0-100
    suggested_slots: List[str] = field(default_factory=list)
    extracted_phone: Optional[str] = None
    extracted_name: Optional[str] = None
    matched_keywords: List[str] = field(default_factory=list)
    requires_doctor_action: bool = True
    notes: str = ""
    agent_version: str = AGENT_VERSION


def _fold(value: Any) -> str:
    text = str(value or "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("ı", "i").replace("İ", "I")
    return text.casefold()


def _digits_only(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _hit_keywords(folded: str, keywords: Tuple[str, ...]) -> List[str]:
    return sorted({k for k in keywords if k in folded})


def classify_intent(transcript: str) -> Tuple[str, List[str]]:
    """Niyet siniflandirma. Sira: urgent > cancel > new > info > spam > other."""
    folded = _fold(transcript)
    if not folded.strip():
        return "other", []

    urgent_hits = _hit_keywords(folded, URGENT_KEYWORDS)
    if urgent_hits:
        return "urgent", urgent_hits

    cancel_hits = _hit_keywords(folded, CANCEL_KEYWORDS)
    if cancel_hits:
        return "appointment_cancel", cancel_hits

    new_hits = _hit_keywords(folded, NEW_APPT_KEYWORDS)
    if new_hits:
        return "appointment_new", new_hits

    info_hits = _hit_keywords(folded, INFO_KEYWORDS)
    if info_hits:
        return "info", info_hits

    spam_hits = _hit_keywords(folded, SPAM_HINTS)
    if spam_hits:
        return "spam", spam_hits

    return "other", []


def urgency_score(intent: str, transcript: str) -> int:
    """0-100 arasi aciliyet skoru. Klinik karar degildir, sadece siralama icindir."""
    folded = _fold(transcript)
    score = 0
    if intent == "urgent":
        score = 80
        # Sinyal kelime tekrari skoru artirir
        for kw in URGENT_KEYWORDS:
            if kw in folded:
                score += 3
    elif intent == "appointment_cancel":
        score = 30
    elif intent == "appointment_new":
        score = 25
    elif intent == "info":
        score = 10
    elif intent == "spam":
        score = 0
    else:
        score = 5

    # Kanama / dusuk gibi mutlak risk artiricilar
    for hard in ("kanama", "su geldi", "bayildi", "112", "kasilma"):
        if hard in folded:
            score = min(100, score + 15)
    return max(0, min(100, score))


def extract_callback_phone(transcript: str, caller_phone: str) -> Optional[str]:
    """Konusmada gecen 10-11 haneli telefonu yakala; yoksa caller-ID."""
    digits = _digits_only(transcript)
    # Once tam 11 hane (Turkiye mobil)
    for match in re.finditer(r"\b\d{10,11}\b", transcript):
        raw = match.group(0)
        d = _digits_only(raw)
        if len(d) in (10, 11):
            return d[-10:]
    # Aramada gecen tum rakamlar 10+ ise son 10 hane
    if len(digits) >= 10:
        # 0-baslangici sayilmamak icin son 10
        return digits[-10:]
    return _digits_only(caller_phone)[-10:] or None


def extract_caller_name(transcript: str) -> Optional[str]:
    """"Ben ... / Adim ..." kaliplarini yakala."""
    folded = _fold(transcript)
    patterns = (
        r"ben\s+([a-z]+(?:\s+[a-z]+){0,2})",
        r"adim\s+([a-z]+(?:\s+[a-z]+){0,2})",
        r"ismim\s+([a-z]+(?:\s+[a-z]+){0,2})",
    )
    for pat in patterns:
        m = re.search(pat, folded)
        if m:
            name = m.group(1).strip()
            # Bariz stop kelimeleri at
            if name in ("ariyorum", "telefon", "size", "soyle", "demek"):
                continue
            return name.title()
    return None


def suggest_slots(received_at: str, intent: str, clinic_hours: Tuple[int, int] = (9, 17)) -> List[str]:
    """Onerilen ilk 3 acik saat. Klinik takvimine soruyu web layer yapar;
    burasi sadece "ilk uygun gun + saat" iskeleti dondurur.

    intent == 'urgent' ise ayni gun mumkun ise ayni gun, degilse ertesi sabah.
    """
    try:
        now = datetime.fromisoformat(received_at)
    except Exception:
        now = datetime.now()

    open_h, close_h = clinic_hours
    candidates: List[datetime] = []

    if intent == "urgent":
        # Ayni gun ilk uygun yarim saatlik
        start = now.replace(minute=0 if now.minute < 30 else 30, second=0, microsecond=0)
        if start <= now:
            start = start + timedelta(minutes=30)
        if open_h <= start.hour < close_h:
            candidates.append(start)
        # Ertesi sabah ilk slot
        tomorrow = (now + timedelta(days=1)).replace(hour=open_h, minute=0, second=0, microsecond=0)
        candidates.append(tomorrow)
    else:
        # Ertesi is gunu 10:00, 11:30, 14:30
        base = now + timedelta(days=1)
        for hh, mm in ((10, 0), (11, 30), (14, 30)):
            candidates.append(base.replace(hour=hh, minute=mm, second=0, microsecond=0))

    return [c.strftime("%Y-%m-%d %H:%M") for c in candidates[:3]]


def parse_call(call: CallRecord, clinic_hours: Tuple[int, int] = (9, 17)) -> TriagedCall:
    """Ana giris: ham cagri kaydini triyajli kayit dondur."""
    received_at = call.received_at or datetime.now().isoformat(timespec="seconds")
    intent, hits = classify_intent(call.transcript)
    urgency = urgency_score(intent, call.transcript)
    slots = suggest_slots(received_at, intent, clinic_hours) if intent in ("appointment_new", "urgent") else []
    phone = extract_callback_phone(call.transcript, call.caller_phone)
    name = call.caller_name or extract_caller_name(call.transcript)

    notes_parts = []
    if intent == "urgent":
        notes_parts.append("ACIL: Doktor/sekreter derhal bakmali")
    if intent == "spam":
        notes_parts.append("Muhtemel spam/pazarlama - reddedilebilir")
    if not call.transcript.strip():
        notes_parts.append("Bos transkript - sadece kacan arama")

    return TriagedCall(
        caller_phone=str(call.caller_phone or ""),
        transcript=call.transcript or "",
        received_at=received_at,
        intent=intent,
        urgency=urgency,
        suggested_slots=slots,
        extracted_phone=phone,
        extracted_name=name,
        matched_keywords=hits,
        requires_doctor_action=intent != "spam",
        notes=" | ".join(notes_parts),
    )


def to_audit_payload(triaged: TriagedCall) -> Dict[str, Any]:
    """web_audit_log icin serileme."""
    payload = asdict(triaged)
    payload["action"] = f"telesekreter:{triaged.intent}"
    return payload


if __name__ == "__main__":
    # Hizli sanity check (web baglantisiz)
    samples = [
        CallRecord(caller_phone="05551234567", transcript="Merhaba doktor bey, ben Ayse. Su geldi sancilarim var, ne yapayim?"),
        CallRecord(caller_phone="05559876543", transcript="Yarin saat 10 randevu istiyorum gebelik kontrol icin."),
        CallRecord(caller_phone="08503334455", transcript="Size ozel teklifimiz var, kredi karti faturanizla ilgili."),
        CallRecord(caller_phone="05551112233", transcript="Iptal etmek istiyorum, gelemiyorum yarinki randevuya."),
        CallRecord(caller_phone="05554445566", transcript=""),
    ]
    for s in samples:
        result = parse_call(s)
        print(f"[{result.intent:20}] urg={result.urgency:3} phone={s.caller_phone} -> {result.suggested_slots} | {result.notes}")
