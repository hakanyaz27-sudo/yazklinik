"""Sesli Randevu Evet Onayi Ajani.

Telefonla aranan hasta "evet" / "tamam" / "olur" derse randevu kesinlesir.
"Hayir" / "iptal" / "uygun degil" derse iptal kuyruguna alinir.
Belirsizse hic dokunmaz, sekretere isaretler.

Niye ayri bir ajan: Telesekreter (yeni cagri triyaji) ve confirm flow
farkli risk seviyesindedir. Confirm akisi randevu state'ini gercekten
kesinlestirir/iptal eder; o yuzden mantik izole.

Stdlib + dataclass. Web layer cagri yapar, sonuc onay kuyruguna duser.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.16-sesli-onay"
SOURCE_LABEL = "Sesli randevu onay yaniti"

# Sira: belirgin red > belirgin onay > tereddut > anlasilmadi
YES_TOKENS = (
    "evet", "tamam", "olur", "kabul", "geliyorum", "gelecegim",
    "okay", "ok", "iyi", "uygun", "tabii", "tabi", "katiliyorum",
)
NO_TOKENS = (
    "hayir", "iptal", "gelmiyorum", "gelemiyorum", "uygun degil",
    "vazgec", "vazgectim", "olmaz", "kabul etmiyorum",
)
RESCHEDULE_TOKENS = (
    "ertelemek", "erteler misin", "baska gun", "baska saat",
    "musait degilim", "degistirmek istiyorum",
)
UNSURE_TOKENS = (
    "bilmiyorum", "dusunmem lazim", "esime sorayim", "belki",
    "sonra ararim", "geri donerim",
)


@dataclass
class ConfirmationRequest:
    """Web layer'in hazirladigi onay isteme baglami."""
    appointment_id: str
    patient_phone: str
    patient_name: str
    appointment_at: str          # ISO 8601 string
    spoken_response: str         # STT cikti


@dataclass
class ConfirmationResult:
    appointment_id: str
    decision: str                # "confirmed" | "cancelled" | "reschedule" | "unclear" | "no_response"
    confidence: int              # 0-100
    spoken_response: str
    matched_tokens: List[str] = field(default_factory=list)
    requires_human_review: bool = False
    suggested_action: str = ""
    decided_at: str = ""
    agent_version: str = AGENT_VERSION


def _fold(value: Any) -> str:
    text = str(value or "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("ı", "i").replace("İ", "I")
    return text.casefold()


def _hits(folded: str, tokens) -> List[str]:
    out = []
    for t in tokens:
        # Kelime sinirina yakin eslestir, "evetler" gibi olur ama "hayirsiz" 'hayir' yakalanmasi istenmez
        if re.search(r"\b" + re.escape(t) + r"\b", folded):
            out.append(t)
    return out


def classify_response(spoken: str) -> Dict[str, Any]:
    """Sira kritik: red > erteleme > tereddut > onay > anlasilmadi."""
    folded = _fold(spoken)
    if not folded.strip():
        return {"decision": "no_response", "confidence": 100, "tokens": []}

    no_hits = _hits(folded, NO_TOKENS)
    yes_hits = _hits(folded, YES_TOKENS)
    res_hits = _hits(folded, RESCHEDULE_TOKENS)
    uns_hits = _hits(folded, UNSURE_TOKENS)

    # 1. Erteleme ozel: net niyet, ayri akis
    if res_hits and not no_hits:
        return {"decision": "reschedule", "confidence": 75, "tokens": res_hits}

    # 2. Net red
    if no_hits and not yes_hits:
        return {"decision": "cancelled", "confidence": 90, "tokens": no_hits}

    # 3. Net onay
    if yes_hits and not no_hits:
        # "evet ama" gibi tereddut karistirici
        if uns_hits:
            return {"decision": "unclear", "confidence": 40, "tokens": yes_hits + uns_hits}
        return {"decision": "confirmed", "confidence": 85, "tokens": yes_hits}

    # 4. Hem evet hem hayir (catismali)
    if yes_hits and no_hits:
        return {"decision": "unclear", "confidence": 30, "tokens": yes_hits + no_hits}

    # 5. Tereddut tek basina
    if uns_hits:
        return {"decision": "unclear", "confidence": 50, "tokens": uns_hits}

    # 6. Hicbir sinyal yok
    return {"decision": "unclear", "confidence": 20, "tokens": []}


def decide(request: ConfirmationRequest) -> ConfirmationResult:
    """Ana giris noktasi."""
    cls = classify_response(request.spoken_response)
    decision = cls["decision"]
    confidence = int(cls["confidence"])
    tokens = list(cls["tokens"])

    if decision == "confirmed":
        suggested = f"Randevu {request.appointment_at} kesinlestirilebilir; SMS onayi gonderilebilir."
        needs_human = confidence < 70
    elif decision == "cancelled":
        suggested = f"Randevu {request.appointment_at} iptal kuyruguna alinmali; ayni hasta icin yeni slot teklif edilebilir."
        needs_human = confidence < 80
    elif decision == "reschedule":
        suggested = "Hastayla yeni gun/saat icin geri arama planlanmali."
        needs_human = True
    elif decision == "no_response":
        suggested = "Cevap yok; ikinci arama 24 saat sonra otomatik planlanabilir."
        needs_human = False
    else:  # unclear
        suggested = "Sekretere yonlendirilmeli; ses kaydi insanca dinlenmeli."
        needs_human = True

    return ConfirmationResult(
        appointment_id=str(request.appointment_id),
        decision=decision,
        confidence=confidence,
        spoken_response=request.spoken_response,
        matched_tokens=tokens,
        requires_human_review=needs_human,
        suggested_action=suggested,
        decided_at=datetime.now().isoformat(timespec="seconds"),
    )


def can_auto_apply(result: ConfirmationResult, min_confidence: int = 80) -> bool:
    """Web layer bu fonksiyona sorar: ben bu kararı otomatik uygulayabilir miyim?

    Sadece 'confirmed' ya da 'cancelled' kararlari otomatik uygulanabilir
    ve guven esigin uzerinde olmalidir. Insan onayi gerekiyorsa False.
    """
    if result.requires_human_review:
        return False
    if result.decision not in ("confirmed", "cancelled"):
        return False
    return result.confidence >= min_confidence


def to_audit_payload(result: ConfirmationResult) -> Dict[str, Any]:
    payload = asdict(result)
    payload["action"] = f"sesli_onay:{result.decision}"
    return payload


if __name__ == "__main__":
    samples = [
        ConfirmationRequest("A001", "05551112233", "Ayse Y.", "2026-05-20T10:00:00", "Evet doktor bey gelecegim"),
        ConfirmationRequest("A002", "05552223344", "Fatma K.", "2026-05-20T11:30:00", "Hayir gelemiyorum iptal"),
        ConfirmationRequest("A003", "05553334455", "Zeynep B.", "2026-05-20T14:00:00", "Baska gun olabilir mi"),
        ConfirmationRequest("A004", "05554445566", "Esra D.", "2026-05-20T15:00:00", "Esime sorayim sonra ararim"),
        ConfirmationRequest("A005", "05555556677", "Selin A.", "2026-05-20T16:00:00", "Evet ama belki gelemem"),
        ConfirmationRequest("A006", "05556667788", "Test", "2026-05-20T17:00:00", ""),
    ]
    for s in samples:
        r = decide(s)
        auto = can_auto_apply(r)
        print(f"[{r.decision:11}] conf={r.confidence:3} auto={auto} | {r.suggested_action}")
