"""Recete Hazirlayici Ajani.

Hastanin gecmis tedavisinden ve doktorun favori sablonlarindan recete
TASLAGI uretir. Asla otomatik recete yazmaz, asla e-Receteye gondermez.
Doktor secip duzenleyip imzalar.

Ne yapar:
    - Hastanin son N ziyaretinden ilac/doz desenini cikarir
    - Doktorun en sik yazdigi ilac kombinasyonlarini onerir
    - Etkilesim/alerjisi olan ilaclar icin DIKKAT isareti koyar (sadece uyari)
    - Recete formatini standartlastirir (ilac adi, doz, sure, kullanim sekli)

Asla yapmaz:
    - Tani veya doz onerisi yapmaz (sadece gecmis veriden cikarir)
    - Otomatik imzalamaz/gondermez
    - Hasta alerjilerine bakmadan onermez (alerji listesi yoksa REDDEDER)

Stdlib only.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Set, Tuple


AGENT_VERSION = "2026.05.16-recete-hazirlayici"
SOURCE_LABEL = "Recete taslak uretici"

# Yaygin etkilesim cifti ornekleri (genisletilebilir). Klinik karar degildir, sadece uyaridir.
INTERACTION_HINTS: Dict[Tuple[str, str], str] = {
    ("warfarin", "ibuprofen"): "Antikoagulan + NSAID kanama riski - doktor degerlendirsin.",
    ("metformin", "kontrast"): "Kontrast oncesi/sonrasi metformin durdurulmali.",
    ("amoksisilin", "metotreksat"): "Penisilin metotreksat seviyesini artirir.",
    ("kombine ohk", "varfar"): "OHK + varfarin kombinasyonu - doktor onayli.",
    ("ssri", "tramadol"): "Serotonin sendromu riski.",
}


@dataclass
class PastMedication:
    name: str
    dose: str = ""
    duration_days: int = 0
    prescribed_at: str = ""        # ISO date


@dataclass
class DraftRequest:
    patient_id: str
    patient_name: str
    patient_allergies: List[str] = field(default_factory=list)
    chronic_conditions: List[str] = field(default_factory=list)
    past_medications: List[PastMedication] = field(default_factory=list)
    visit_reason: str = ""
    doctor_preferred_combos: List[List[str]] = field(default_factory=list)
    max_suggestions: int = 5


@dataclass
class DraftItem:
    name: str
    dose: str
    duration_days: int
    usage: str
    confidence: int
    source: str               # "patient_history" | "doctor_preferred" | "free"
    interaction_warnings: List[str] = field(default_factory=list)


@dataclass
class RecipeDraft:
    patient_id: str
    patient_name: str
    items: List[DraftItem] = field(default_factory=list)
    skip_reason: Optional[str] = None
    requires_doctor_review: bool = True
    summary_note: str = ""
    agent_version: str = AGENT_VERSION


def _fold(value: Any) -> str:
    text = str(value or "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("ı", "i").replace("İ", "I")
    return text.casefold()


def _allergy_block(name: str, allergies: List[str]) -> Optional[str]:
    folded_name = _fold(name)
    for a in allergies:
        if not a:
            continue
        if _fold(a) in folded_name or folded_name in _fold(a):
            return f"Hastanin '{a}' alerjisi var - bu ilac engellendi."
    return None


def _interaction_warnings(name: str, others: List[str]) -> List[str]:
    folded = _fold(name)
    out: List[str] = []
    for (a, b), msg in INTERACTION_HINTS.items():
        af, bf = _fold(a), _fold(b)
        if af in folded:
            for other in others:
                if bf in _fold(other):
                    out.append(msg)
        if bf in folded:
            for other in others:
                if af in _fold(other):
                    out.append(msg)
    # tekrar etmesin
    return sorted(set(out))


def _history_top_meds(history: List[PastMedication], max_items: int) -> List[Tuple[PastMedication, int]]:
    """Son 90 gunde en sik gecen ilaclar (name birikim sayisina gore)."""
    cutoff = date.today() - timedelta(days=90)
    recent = []
    for m in history:
        try:
            d = date.fromisoformat(m.prescribed_at) if m.prescribed_at else None
        except Exception:
            d = None
        if d and d >= cutoff:
            recent.append(m)
    counts = Counter(_fold(m.name) for m in recent)
    seen: Set[str] = set()
    ordered: List[Tuple[PastMedication, int]] = []
    for name_folded, cnt in counts.most_common(max_items):
        for m in recent:
            if _fold(m.name) == name_folded and name_folded not in seen:
                ordered.append((m, cnt))
                seen.add(name_folded)
                break
    return ordered


def build_draft(req: DraftRequest) -> RecipeDraft:
    """Ana giris noktasi."""
    draft = RecipeDraft(patient_id=str(req.patient_id), patient_name=str(req.patient_name))

    # Sertifika gate: alerji listesi YOKSA hicbir oneri yapma
    if not req.patient_allergies and not req.chronic_conditions and not req.past_medications:
        draft.skip_reason = "Yetersiz hasta verisi (alerji/kronik/gecmis ilac listesi bos)."
        draft.summary_note = "Doktor el ile yazmalidir."
        return draft

    items: List[DraftItem] = []
    cart_names: List[str] = []

    # 1. Doktor onceligi
    for combo in req.doctor_preferred_combos[:2]:
        for name in combo:
            block = _allergy_block(name, req.patient_allergies)
            if block:
                continue
            items.append(DraftItem(
                name=name, dose="DOKTOR BELIRLEYIN", duration_days=0,
                usage="DOKTOR BELIRLEYIN", confidence=70, source="doctor_preferred",
                interaction_warnings=[],
            ))
            cart_names.append(name)

    # 2. Gecmis ilac deseni
    for med, cnt in _history_top_meds(req.past_medications, max_items=req.max_suggestions):
        if any(_fold(med.name) == _fold(i.name) for i in items):
            continue
        block = _allergy_block(med.name, req.patient_allergies)
        if block:
            continue
        items.append(DraftItem(
            name=med.name,
            dose=med.dose or "Onceki kullanima gore",
            duration_days=med.duration_days or 0,
            usage="Onceki recetedeki kullanim",
            confidence=min(60 + cnt * 10, 90),
            source="patient_history",
            interaction_warnings=[],
        ))
        cart_names.append(med.name)

    # 3. Etkilesim taramasi - liste son halinde, hepsi birbirine bakar
    for it in items:
        others = [n for n in cart_names if n != it.name]
        it.interaction_warnings = _interaction_warnings(it.name, others)

    # En fazla max_suggestions
    items = items[: max(1, req.max_suggestions)]

    draft.items = items
    if not items:
        draft.skip_reason = "Tum aday ilaclar alerji/etkilesim sebebiyle elendi."
        draft.summary_note = "Doktor manuel olarak alternatif belirlemelidir."
    else:
        draft.summary_note = (
            f"{len(items)} aday ilac listelendi. "
            "Tum dozaj/sure/kullanim bilgisi DOKTOR ONAYI bekliyor; "
            "e-Recete gonderimi yapilmadi."
        )

    return draft


def to_audit_payload(draft: RecipeDraft) -> Dict[str, Any]:
    payload = asdict(draft)
    payload["action"] = "recete:taslak" if draft.items else "recete:skip"
    return payload


if __name__ == "__main__":
    req = DraftRequest(
        patient_id="P001",
        patient_name="Ayse Y.",
        patient_allergies=["Penicillin"],
        chronic_conditions=["PCOS"],
        past_medications=[
            PastMedication("Metformin 500 mg", "1x1", 90, (date.today() - timedelta(days=20)).isoformat()),
            PastMedication("Folik asit 5 mg", "1x1", 30, (date.today() - timedelta(days=10)).isoformat()),
            PastMedication("Amoksisilin", "2x1", 7, (date.today() - timedelta(days=200)).isoformat()),
        ],
        doctor_preferred_combos=[["Folik asit 5 mg"], ["D vitamini 1000 IU"]],
        visit_reason="Kontrol",
    )
    d = build_draft(req)
    print(f"Items: {len(d.items)}  Skip: {d.skip_reason}")
    for it in d.items:
        warn = " | ".join(it.interaction_warnings) if it.interaction_warnings else "-"
        print(f"  - {it.name} ({it.source}, conf={it.confidence}) warn: {warn}")
    print("Note:", d.summary_note)
