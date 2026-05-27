"""Central decision router for Alex.

Alex has many entry points: SIP phone, web dialog, silent Alex, doctor voice,
and patient-facing phone flows. The first decision must be deterministic:
who is speaking, through which channel, what is the intent, and what actions
are allowed. LLM text generation comes after this router, not before it.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass, field
from typing import Dict, Iterable, List, Optional


VERSION = "2026.05.21-central-alex-router"

_TR_TABLE = str.maketrans({
    "ı": "i", "İ": "I", "ğ": "g", "Ğ": "G", "ü": "u", "Ü": "U",
    "ş": "s", "Ş": "S", "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
})


def _env_bool(name: str, default: bool = True) -> bool:
    raw = str(os.environ.get(name, "1" if default else "0") or "").strip().lower()
    return raw in {"1", "true", "yes", "on", "evet", "aktif"}


def alex_router_enabled() -> bool:
    return _env_bool("YAZKLINIK_ALEX_CENTRAL_ROUTER", True)


def fold_text(value: object) -> str:
    text = str(value or "").translate(_TR_TABLE).lower()
    text = re.sub(r"[^a-z0-9+]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _has_any(folded: str, tokens: Iterable[str]) -> bool:
    return any(token and token in folded for token in tokens)


def _alpha_len(folded: str) -> int:
    return len(re.sub(r"[^a-z]+", "", folded or ""))


def _digits(value: object) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _looks_internal_extension(value: object) -> bool:
    digits = _digits(value)
    return bool(digits and len(digits) <= 4)


def _looks_mobile(value: object) -> bool:
    digits = _digits(value)
    return len(digits) >= 10 and digits[-10:].startswith("5")


def _history_text(history: Optional[list], limit: int = 8) -> str:
    parts = []
    for item in (history or [])[-limit:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower() or "user"
        content = str(item.get("content") or item.get("text") or "").strip()
        if content:
            parts.append(f"{role}: {content[:500]}")
    return "\n".join(parts)


@dataclass
class AlexRouteDecision:
    ok: bool = True
    enabled: bool = True
    version: str = VERSION
    channel: str = ""
    source: str = ""
    speaker_role: str = "unknown"
    intent: str = "unclear"
    confidence: float = 0.50
    risk: str = "normal"
    action_policy: str = "answer_only"
    allow_autonomous_action: bool = False
    forced_reply: str = ""
    status: str = "alex_router"
    prompt_hint: str = ""
    max_sentences: int = 3
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["confidence"] = round(float(self.confidence or 0.0), 2)
        return data


def _speaker_role(channel_f: str, source_f: str, caller_f: str, caller_raw: str) -> str:
    combined = f"{channel_f} {source_f} {caller_f}".strip()
    if _looks_internal_extension(caller_raw) and _has_any(combined, ("sip", "phone", "telefon")):
        return "doctor_internal"
    if caller_f in {"doktor", "doctor", "admin", "yazha", "hakan", "hakan yaz"}:
        return "doctor"
    if _has_any(combined, ("web test", "web_test", "akilli", "dialog", "smart", "sessiz")):
        return "doctor"
    if _has_any(combined, ("sip", "phone", "telefon", "telesekreter", "patient")):
        return "patient_phone"
    if _looks_mobile(caller_raw):
        return "patient_phone"
    return "staff_or_unknown"


def _classify_intent(folded: str, speaker_role: str) -> tuple[str, float, str, List[str]]:
    reasons: List[str] = []
    if not folded or _alpha_len(folded) < 4:
        return "unclear", 0.35, "normal", ["too_short"]

    if _has_any(folded, (
        "kanama", "kanamam", "siddetli agri", "cok agri", "bayil", "bayildim",
        "nefes alamiyorum", "suyum geldi", "su geldi", "bebek hareket etmiyor",
        "gogus agrisi", "nobet", "intihar", "acil",
    )):
        return "emergency", 0.96, "high", ["emergency_keyword"]

    if _has_any(folded, (
        "sekreter", "asistan", "insan", "canli", "operator",
        "doktorla gorus", "doktoru istiyorum", "geri arayin", "geri aranmak",
        "beni arayin",
    )):
        return "human_handoff", 0.88, "low", ["human_request"]

    if "alex" in folded or "aleks" in folded:
        if _has_any(folded, (
            "sacma", "aptal", "iq", "zeka", "zeki", "optimize", "duzelt",
            "ise yaramiyor", "islevsiz", "kalite", "daha iyi", "ne yapiyor",
        )):
            return "alex_quality_control", 0.90, "normal", ["alex_meta_quality"]

    if _has_any(folded, (
        "randevu", "muayene", "kontrol randevu", "gelmek istiyorum",
        "gelmek istiyordum", "randevu almak", "randevu istiyorum",
    )):
        return "appointment_request", 0.88, "medium", ["appointment_keyword"]

    if _has_any(folded, (
        "sonuc", "sonucum", "tahlil", "tetkik", "laboratuvar", "lab",
        "smear", "hpv", "nipt", "ikili test", "uclu test", "rapor",
    )):
        return "result_or_lab_request", 0.84, "medium", ["result_keyword"]

    if _has_any(folded, (
        "recete", "ilac", "doz", "rapor ilac", "recept", "ilac yaz",
    )):
        return "prescription_request", 0.82, "medium", ["prescription_keyword"]

    if _has_any(folded, (
        "hasta dosyasi", "dosyasina", "dosyaya", "kaydet", "yazdir",
        "pdf yazdir", "not olustur", "hasta ac", "hastayi ac",
    )):
        return "patient_file_action", 0.82, "medium", ["patient_file_keyword"]

    if _has_any(folded, (
        "hastalar", "liste", "sayfayi ac", "ekrani ac", "git", "goster",
        "sistem durumu", "ayarlar", "randevular", "takvim",
    )):
        return "navigation_command", 0.78, "low", ["navigation_keyword"]

    if _has_any(folded, (
        "gebelik", "hamile", "bulanti", "kusma", "hiperemezis", "usg",
        "fetus", "embriyo", "kan degeri", "beta hcg", "tsh", "amh",
        "ivf", "transfer", "folikul", "smear", "miyom", "kist",
    )):
        return "clinical_question", 0.76, "medium", ["clinical_keyword"]

    if _has_any(folded, (
        "adres", "konum", "nerede", "ucret", "fiyat", "calisma saati",
        "acik mi", "kapanis", "telefon",
    )):
        return "clinic_info", 0.74, "low", ["clinic_info_keyword"]

    if speaker_role in {"doctor", "doctor_internal"}:
        return "doctor_general", 0.68, "normal", ["doctor_default"]
    return "general_or_unclear", 0.58, "normal", ["default"]


def _phone_policy(decision: AlexRouteDecision, folded: str) -> None:
    decision.allow_autonomous_action = False
    decision.max_sentences = 2
    if decision.intent == "emergency":
        decision.action_policy = "urgent_handoff"
        decision.status = "alex_router_emergency"
        decision.forced_reply = (
            "Bu anlattiginiz acil olabilir. Lutfen beklemeden 112'yi arayin "
            "veya en yakin acil servise basvurun. Klinik ekibine acil not birakiyorum."
        )
        return
    if decision.intent == "appointment_request":
        # Booking is enabled on the phone: do not force a deflection. Let the
        # web appointment flow (_ai_phone_handle_appointment_flow) collect the
        # slot, confirm with the caller, and create the appointment.
        decision.action_policy = "book_appointment"
        decision.status = "alex_router_phone_appointment"
        decision.forced_reply = ""
        return
    if decision.intent in {"result_or_lab_request", "prescription_request"}:
        decision.action_policy = "identity_then_handoff"
        decision.status = "alex_router_phone_result_safe"
        decision.forced_reply = (
            "Bu talebi hasta dosyasina otomatik islem yapmadan klinik ekibine iletiyorum. "
            "Ad soyad ve telefon bilginizle ekip size geri donus yapacak."
        )
        return
    if decision.intent == "patient_file_action":
        decision.action_policy = "deny_autonomous_file_action"
        decision.status = "alex_router_phone_file_blocked"
        decision.forced_reply = (
            "Telefonda hasta dosyasina otomatik kayit yapamam. "
            "Mesajinizi klinik ekibine not olarak iletiyorum."
        )
        return
    if decision.intent == "human_handoff":
        decision.action_policy = "human_handoff"
        decision.status = "alex_router_phone_human"
        decision.forced_reply = (
            "Sizi yanlis yonlendirmemek icin mesajinizi klinik ekibine aktariyorum. "
            "Uygun olan ilk asistan geri donus yapacak."
        )
        return
    if decision.intent == "clinic_info":
        decision.action_policy = "clinic_info_handoff"
        decision.status = "alex_router_phone_clinic"
        decision.forced_reply = (
            "Bu bilgiyi yanlis aktarmamak icin klinik ekibine yonlendiriyorum. "
            "Sekreter kesin bilgiyi size iletecek."
        )
        return
    if decision.intent in {"unclear", "general_or_unclear"}:
        # No forced reply: a vague turn may be a name/phone/slot mid-booking.
        # The history-aware web flow handles it (or asks the caller to repeat),
        # so multi-turn appointment booking can progress.
        decision.action_policy = "passthrough"
        decision.status = "alex_router_phone_passthrough"
        decision.forced_reply = ""


def _doctor_policy(decision: AlexRouteDecision, folded: str) -> None:
    decision.max_sentences = 4
    decision.allow_autonomous_action = False
    if decision.intent == "alex_quality_control":
        decision.action_policy = "system_improvement"
        decision.status = "alex_router_doctor_quality"
        decision.forced_reply = (
            "Haklisiniz doktorum; Alex'i hasta telefonu, doktor sohbeti ve aksiyon "
            "komutlarini ayiran merkezi karar motoruna aliyorum. Artik once rol, niyet, "
            "guven skoru ve izinli aksiyon belirlenecek; emin olmadiginda islem yapmayacak."
        )
        return
    if decision.intent == "emergency":
        decision.action_policy = "clinical_urgent_answer"
        decision.status = "alex_router_doctor_emergency"
        decision.allow_autonomous_action = False
        return
    if decision.intent in {"navigation_command", "patient_file_action"}:
        decision.action_policy = "doctor_confirmed_action_only"
        decision.allow_autonomous_action = "ac" in folded or "yap" in folded or "kaydet" in folded
        decision.status = "alex_router_doctor_action"
        return
    if decision.intent == "clinical_question":
        decision.action_policy = "senior_clinical_copilot"
        decision.status = "alex_router_doctor_clinical"
        return
    decision.action_policy = "doctor_copilot_answer"
    decision.status = "alex_router_doctor"


def classify_alex_request(message: object, *, last_text: object = "",
                          full_transcript: object = "", caller: object = "",
                          channel: object = "", source: object = "",
                          triage: Optional[dict] = None,
                          history: Optional[list] = None) -> Dict[str, object]:
    if not alex_router_enabled():
        return AlexRouteDecision(
            ok=True, enabled=False, status="alex_router_disabled",
            prompt_hint="Central Alex Router disabled by environment.",
        ).to_dict()

    raw = str(message or "").strip()
    last = str(last_text or raw or "").strip()
    full = str(full_transcript or raw or "").strip()
    history_part = _history_text(history)
    folded = fold_text("\n".join(x for x in (full, last, history_part) if x))
    channel_f = fold_text(channel)
    source_f = fold_text(source)
    caller_raw = str(caller or "").strip()
    caller_f = fold_text(caller_raw)
    speaker = _speaker_role(channel_f, source_f, caller_f, caller_raw)

    intent, confidence, risk, reasons = _classify_intent(folded, speaker)
    decision = AlexRouteDecision(
        channel=str(channel or ""),
        source=str(source or ""),
        speaker_role=speaker,
        intent=intent,
        confidence=confidence,
        risk=risk,
        status=f"alex_router_{intent}",
        reasons=list(reasons),
    )
    if isinstance(triage, dict) and str(triage.get("intent") or "").strip():
        decision.reasons.append(f"triage={triage.get('intent')}")
        if str(triage.get("intent") or "").strip().lower() == "urgent":
            decision.intent = "emergency"
            decision.confidence = max(decision.confidence, 0.96)
            decision.risk = "high"

    if speaker in {"patient_phone", "staff_or_unknown"} and _has_any(
            f"{channel_f} {source_f}", ("sip", "phone", "telefon", "telesekreter")):
        _phone_policy(decision, folded)
    else:
        _doctor_policy(decision, folded)

    decision.prompt_hint = (
        f"AlexRouter v={VERSION}; speaker={decision.speaker_role}; "
        f"intent={decision.intent}; confidence={decision.confidence:.2f}; "
        f"risk={decision.risk}; policy={decision.action_policy}; "
        f"allow_auto_action={str(decision.allow_autonomous_action).lower()}. "
        "Doctor/staff channels must not use patient phone fallback. "
        "Patient phone channels must not create appointments, diagnoses, "
        "prescriptions, or patient-file writes without human confirmation."
    )
    return decision.to_dict()


def public_alex_router_status() -> Dict[str, object]:
    regression = run_alex_router_regression()
    return {
        "enabled": alex_router_enabled(),
        "version": VERSION,
        "default_phone_policy": "collect_and_handoff_no_autonomous_actions",
        "default_doctor_policy": "senior_copilot_with_explicit_action_gate",
        "regression_ok": bool(regression.get("ok")),
        "regression_passed": regression.get("passed"),
        "regression_total": regression.get("total"),
    }


def alex_router_regression_cases() -> List[Dict[str, object]]:
    return [
        {
            "name": "doctor_meta_quality",
            "text": "Alex sacma cevap veriyor, optimize et",
            "caller": "doktor",
            "channel": "web_test",
            "speaker_role": "doctor",
            "intent": "alex_quality_control",
            "policy": "system_improvement",
            "allow_autonomous_action": False,
        },
        {
            "name": "doctor_clinical_copilot",
            "text": "Hiperemezis hastasinda ilk yaklasim nasil olmali?",
            "caller": "doktor",
            "channel": "akilli-dialog",
            "speaker_role": "doctor",
            "intent": "clinical_question",
            "policy": "senior_clinical_copilot",
            "allow_autonomous_action": False,
        },
        {
            "name": "sip_internal_noise",
            "text": "Ne yapiyorsun?",
            "caller": "18",
            "channel": "sip_alex",
            "speaker_role": "doctor_internal",
            "allow_autonomous_action": False,
        },
        {
            "name": "patient_phone_appointment_booking",
            "text": "Randevu almak istiyorum",
            "caller": "05551112233",
            "channel": "sip_alex",
            "speaker_role": "patient_phone",
            "intent": "appointment_request",
            "policy": "book_appointment",
            "allow_autonomous_action": False,
        },
        {
            "name": "patient_phone_emergency",
            "text": "Kanamam var, suyum geldi",
            "caller": "05551112233",
            "channel": "sip_alex",
            "speaker_role": "patient_phone",
            "intent": "emergency",
            "policy": "urgent_handoff",
            "allow_autonomous_action": False,
        },
        {
            "name": "patient_file_action_blocked",
            "text": "Bunu hasta dosyasina kaydet",
            "caller": "05551112233",
            "channel": "sip_alex",
            "speaker_role": "patient_phone",
            "intent": "patient_file_action",
            "policy": "deny_autonomous_file_action",
            "allow_autonomous_action": False,
        },
        {
            "name": "doctor_navigation_explicit",
            "text": "Hastalar sayfasini ac",
            "caller": "doktor",
            "channel": "akilli-dialog",
            "speaker_role": "doctor",
            "intent": "navigation_command",
            "policy": "doctor_confirmed_action_only",
            "allow_autonomous_action": True,
        },
        {
            "name": "patient_phone_human_handoff",
            "text": "Sekreterle gorusmek istiyorum",
            "caller": "05551112233",
            "channel": "sip_alex",
            "speaker_role": "patient_phone",
            "intent": "human_handoff",
            "policy": "human_handoff",
            "allow_autonomous_action": False,
        },
        {
            "name": "patient_phone_clinic_info",
            "text": "Adresiniz nerede acik misiniz",
            "caller": "05551112233",
            "channel": "sip_alex",
            "speaker_role": "patient_phone",
            "intent": "clinic_info",
            "policy": "clinic_info_handoff",
            "allow_autonomous_action": False,
        },
    ]


def run_alex_router_regression() -> Dict[str, object]:
    results: List[Dict[str, object]] = []
    failures: List[Dict[str, object]] = []
    for case in alex_router_regression_cases():
        decision = classify_alex_request(
            case.get("text") or "",
            caller=case.get("caller") or "",
            channel=case.get("channel") or "",
            source=case.get("channel") or "",
            history=case.get("history") or [],
        )
        checks = {
            "speaker_role": decision.get("speaker_role") == case.get("speaker_role"),
            "allow_autonomous_action": (
                bool(decision.get("allow_autonomous_action"))
                == bool(case.get("allow_autonomous_action"))
            ),
        }
        if case.get("intent"):
            checks["intent"] = decision.get("intent") == case.get("intent")
        if case.get("policy"):
            checks["policy"] = decision.get("action_policy") == case.get("policy")
        ok = all(checks.values())
        row = {
            "name": case.get("name"),
            "ok": ok,
            "checks": checks,
            "decision": decision,
        }
        results.append(row)
        if not ok:
            failures.append(row)
    return {
        "ok": not failures,
        "version": VERSION,
        "total": len(results),
        "passed": len(results) - len(failures),
        "failed": failures,
        "results": results,
    }


def _self_test() -> int:
    regression = run_alex_router_regression()
    for row in regression.get("results") or []:
        decision = row.get("decision") or {}
        print(
            row.get("name"),
            "OK" if row.get("ok") else "FAIL",
            decision.get("speaker_role"),
            decision.get("intent"),
            decision.get("action_policy"),
            "auto=" + str(decision.get("allow_autonomous_action")),
        )
    print(json.dumps({
        "ok": regression.get("ok"),
        "version": regression.get("version"),
        "passed": regression.get("passed"),
        "total": regression.get("total"),
    }, ensure_ascii=False, sort_keys=True))
    return 0 if regression.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(_self_test())
