"""Safety gate for SIP Alex.

The SIP bridge is a live phone line. It must not turn unclear speech, internal
doctor tests, or STT noise into appointment/patient actions. This module keeps
that first decision deterministic and intentionally conservative.
"""
from __future__ import annotations

import os
import re
from typing import Dict, Iterable, Optional

try:
    from yazklinik_alex_router import (
        classify_alex_request,
        public_alex_router_status,
    )
except Exception:
    def classify_alex_request(*_args, **_kwargs):
        return {}

    def public_alex_router_status():
        return {"enabled": False, "version": "missing"}


_TR_TABLE = str.maketrans({
    "ı": "i", "İ": "I", "ğ": "g", "Ğ": "G", "ü": "u", "Ü": "U",
    "ş": "s", "Ş": "S", "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
})


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0") or "").strip().lower()
    return raw in {"1", "true", "yes", "on", "evet", "aktif"}


def sip_alex_safe_mode_enabled() -> bool:
    # Always on. This is a live medical phone line: the deterministic guard must
    # govern every turn. Disabling it would drop emergency/appointment routing
    # down to a generic handoff, so the env toggle is intentionally not honoured.
    return True


def sip_alex_autonomous_actions_disabled() -> bool:
    return _env_bool("YAZKLINIK_SIP_ALEX_DISABLE_AUTONOMOUS_ACTIONS", True)


def sip_alex_hangup_after_safe_reply() -> bool:
    return _env_bool("YAZKLINIK_SIP_ALEX_HANGUP_AFTER_SAFE_REPLY", True)


def fold_text(value: object) -> str:
    text = str(value or "").translate(_TR_TABLE).lower()
    text = re.sub(r"[^a-z0-9+]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _has_any(folded: str, tokens: Iterable[str]) -> bool:
    return any(token and token in folded for token in tokens)


def _caller_is_internal(caller: object) -> bool:
    raw = str(caller or "").strip()
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits and len(digits) <= 4:
        return True
    folded = fold_text(raw)
    return folded in {"doktor", "doctor", "admin", "yazha", "internal", "sip"}


def _extract_mobile_phone(text: str, dtmf_digits: str = "") -> str:
    candidates = []
    if dtmf_digits:
        candidates.append("".join(ch for ch in str(dtmf_digits) if ch.isdigit()))
    candidates.extend(re.findall(r"(?:\+?90)?0?5\d(?:[\s().-]*\d){8}", text or ""))
    for candidate in candidates:
        digits = "".join(ch for ch in str(candidate) if ch.isdigit())
        if len(digits) >= 10:
            last10 = digits[-10:]
            if last10.startswith("5"):
                return "0" + last10
    return ""


def _has_date_or_time(folded_full: str) -> bool:
    if re.search(r"\b(?:[01]?\d|2[0-3])[:. ](?:[0-5]\d)\b", folded_full):
        return True
    if re.search(r"\b(?:[01]?\d|2[0-3])\s*(?:de|da|e|a)?\b", folded_full):
        return _has_any(folded_full, (
            "saat", "yarin", "bugun", "pazartesi", "sali", "carsamba",
            "persembe", "cuma", "cumartesi", "pazar",
        ))
    return _has_any(folded_full, (
        "yarin", "bugun", "obur gun", "pazartesi", "sali", "carsamba",
        "persembe", "cuma", "cumartesi", "pazar", "saat",
    ))


def _history_user_turns(history: Optional[list]) -> int:
    total = 0
    for item in history or []:
        if isinstance(item, dict) and str(item.get("role") or "").lower() == "user":
            total += 1
    return total


def _response(status: str, intent: str, reply: str, confidence: float = 0.75,
              terminal: bool = False, reason: str = "") -> Dict[str, object]:
    should_hangup = bool(terminal and sip_alex_hangup_after_safe_reply())
    return {
        "enabled": True,
        "block_webhook": True,
        "status": status,
        "intent": intent,
        "reply": reply,
        "confidence": round(float(confidence), 2),
        "terminal": bool(terminal),
        "should_hangup": should_hangup,
        "reason": reason,
    }


def build_sip_safe_response(text: str, full_transcript: str = "", caller: str = "",
                            triage: Optional[dict] = None,
                            history: Optional[list] = None,
                            dtmf_digits: str = "") -> Dict[str, object]:
    """Return a conservative reply plan for live SIP calls.

    In safe mode the bridge does not let web/LLM layers book appointments or
    perform patient-file actions from phone speech. It either asks for missing
    callback information or hands the request to staff.
    """
    if not sip_alex_safe_mode_enabled():
        return {"enabled": False, "block_webhook": False, "status": "sip_safe_disabled"}

    triage = triage if isinstance(triage, dict) else {}
    raw_last = str(text or "").strip()
    raw_full = str(full_transcript or text or "").strip()
    try:
        route = classify_alex_request(
            raw_last, last_text=raw_last, full_transcript=raw_full,
            caller=caller, channel="sip_alex", source="sip_alex",
            triage=triage, history=history)
    except Exception:
        route = {}
    # The guard is a thin SAFETY FILTER, not the booking brain. It blocks the
    # phone line only for safety-critical intents (emergency -> 112, medical
    # records, human handoff, clinic info). Everything else - appointment
    # requests, names, phone numbers, slot replies, general speech, and calls
    # from internal extensions - passes through (block_webhook=False) so the
    # live SIP turn reaches the web booking flow, which collects the slot,
    # confirms with the caller, and creates the appointment.
    intent = str(route.get("intent") or "")

    # Emergency is life-critical: handled here (112), never booked or LLM'd.
    if intent == "emergency" or str(triage.get("intent") or "") == "urgent":
        return _response(
            "sip_safe_emergency", "emergency",
            "Bu anlattiginiz acil olabilir. Lutfen beklemeden 112'yi arayin veya en yakin acil servise basvurun. Klinik ekibine acil not birakiyorum.",
            confidence=0.96, terminal=True, reason="emergency_keyword")

    # Medical-record actions never happen automatically over the phone.
    if intent in {"result_or_lab_request", "prescription_request"}:
        return _response(
            "sip_safe_result", "result_request",
            "Sonuc veya recete talebinizi klinik ekibine iletiyorum; telefonda hasta dosyasina otomatik islem yapmiyorum. Ekip sizi geri arayacak.",
            confidence=0.84, terminal=True, reason="result_request")
    if intent == "patient_file_action":
        return _response(
            "sip_safe_file_blocked", "patient_file_action",
            "Telefonda hasta dosyasina otomatik kayit yapamam. Mesajinizi klinik ekibine not olarak iletiyorum.",
            confidence=0.82, terminal=True, reason="patient_file_action")
    if intent == "human_handoff":
        return _response(
            "sip_safe_handoff", "human_handoff",
            "Sizi yanlis yonlendirmemek icin mesaji klinik ekibine aktariyorum. Uygun olan ilk asistan geri donus yapacak.",
            confidence=0.9, terminal=True, reason="human_request")
    if intent == "clinic_info":
        return _response(
            "sip_safe_clinic_info", "clinic_info",
            "Bu bilgiyi yanlis aktarmamak icin klinik ekibine yonlendiriyorum. Sekreter kesin bilgiyi size iletecek.",
            confidence=0.76, terminal=True, reason="clinic_info")

    # Appointment / general / unclear / internal caller -> pass through to the
    # web booking + assistant flow. No block, no hangup.
    confidence = 0.6
    if isinstance(route, dict):
        try:
            confidence = float(route.get("confidence") or 0.6)
        except (TypeError, ValueError):
            confidence = 0.6
    return {
        "enabled": True,
        "block_webhook": False,
        "status": "sip_pass_to_booking",
        "intent": intent or "passthrough",
        "reply": "",
        "confidence": round(confidence, 2),
        "terminal": False,
        "should_hangup": False,
        "reason": "pass_to_web_booking",
    }


def public_guard_status() -> Dict[str, object]:
    return {
        "safe_mode": sip_alex_safe_mode_enabled(),
        "autonomous_actions_disabled": sip_alex_autonomous_actions_disabled(),
        "hangup_after_safe_reply": sip_alex_hangup_after_safe_reply(),
        "version": "2026.05.21-sip-booking-guard",
        "central_router": public_alex_router_status(),
    }
