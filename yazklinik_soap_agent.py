"""SOAP Notes Ajani - kısa not -> tam SOAP formatinda visit notu.

Doktor: "kanama 2 gun, ta 130/85, smear normal"
SOAP cikti:
    S (Subjective): Hasta 2 gundur vajinal kanama tarif ediyor...
    O (Objective): TA 130/85, smear normal...
    A (Assessment): Anormal uterin kanama suphesi (PALM-COEIN)...
    P (Plan): TIT, hormonal panel, USG, kontrol 1 hafta...

Kullanim:
    expand_to_soap("kanama 2 gun, ta 130/85") -> SOAPNote
    expand_to_soap_with_icd(...) -> SOAPNote + ICD-10 onerileri
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-soap"

SOAP_PROMPT = """Sen 25 yillik OB-GYN konsultanisin. Asagidaki KISA notu klinik
standart SOAP formatinda genislet. SADECE JSON dondur:

{
  "subjective": "Hasta ne sikayet ediyor (genisletilmis)",
  "objective": "Vital bulgular, muayene, lab",
  "assessment": "Klinik degerlendirme + DDx (kisa)",
  "plan": "Tetkik, tedavi, kontrol",
  "patient_education": "Hastaya soylenecek 1-2 cumle",
  "follow_up": "Ne zaman kontrol",
  "needs_more_info": [eksik kritik bilgi listesi]
}

Klinik karar yetkili doktora aittir; cikti ONERI niteliginde."""


@dataclass
class SOAPNote:
    subjective: str = ""
    objective: str = ""
    assessment: str = ""
    plan: str = ""
    patient_education: str = ""
    follow_up: str = ""
    needs_more_info: List[str] = field(default_factory=list)
    raw_input: str = ""
    method: str = ""
    error: Optional[str] = None
    requires_doctor_review: bool = True
    agent_version: str = AGENT_VERSION


def _rule_based_soap(short_note: str, method: str = "local_rule") -> SOAPNote:
    raw = str(short_note or "").strip()
    folded = raw.lower()
    out = SOAPNote(raw_input=raw, method=method)
    out.subjective = raw

    vitals: List[str] = []
    m_ta = re.search(r"\b(?:ta|tansiyon)\s*[:=]?\s*(\d{2,3})\s*/\s*(\d{2,3})", folded)
    if m_ta:
        vitals.append(f"TA {m_ta.group(1)}/{m_ta.group(2)} mmHg")

    if "sikayet yok" in folded:
        out.subjective = "Hasta belirgin sikayet tarif etmiyor. " + raw
    out.objective = ", ".join(vitals) if vitals else (
        "Objektif bulgular kisa notta sinirli; vital, muayene ve tetkik alanlari doktor tarafindan tamamlanmali."
    )

    assessments: List[str] = []
    if "gebelik" in folded or "gebe" in folded:
        assessments.append("Gebelik rutini/kontrol degerlendirmesi")
    if "hipertans" in folded or "tansiyon" in folded or " ta " in f" {folded} ":
        assessments.append("Gebelikte hipertansif hastaliklar acisindan izlem")
    if "kanama" in folded:
        assessments.append("Vajinal kanama/AUB ayirici tanisi")
    if "smear" in folded or "hpv" in folded:
        assessments.append("Servikal tarama sonucu degerlendirmesi")
    out.assessment = "; ".join(assessments) if assessments else (
        "Kisa nottan klinik on degerlendirme taslagi; hekim tarafindan tamamlanmali."
    )

    plans: List[str] = []
    if "gebelik" in folded or "gebe" in folded:
        plans.append("Gebelik haftasi, fetal kalp atimi, USG ve rutin takip bilgileri kontrol edilecek")
    if "tansiyon" in folded or " ta " in f" {folded} " or "hipertans" in folded:
        plans.append("Tansiyon tekrar olcumu, proteinuri ve preeklampsi alarm bulgulari sorgulanacak")
    if "kanama" in folded:
        plans.append("Kanama miktari, gebelik durumu, USG ve gerekli lab tetkikleri degerlendirilecek")
    plans.append("Doktor muayenesi ve klinik karar sonrasi plan kesinlestirilecek")
    out.plan = "; ".join(plans)
    out.patient_education = "Alarm bulgulari olursa klinik veya acil basvuru onerisi doktor tarafindan netlestirilir."
    out.follow_up = "Kontrol araligi klinik bulguya gore doktor tarafindan belirlenir."

    if not vitals:
        out.needs_more_info.append("Vital bulgular")
    if ("gebelik" in folded or "gebe" in folded) and not re.search(r"\b\d{1,2}\s*(?:hf|hafta)", folded):
        out.needs_more_info.append("Gebelik haftasi")
    out.needs_more_info.extend(["Muayene bulgusu", "Gerekli laboratuvar/USG sonucu"])
    return out


def expand_to_soap(short_note: str, prefer: str = "ollama") -> SOAPNote:
    out = SOAPNote(raw_input=short_note)
    if not short_note or not short_note.strip():
        out.error = "Bos not"
        return out
    if prefer == "skip":
        return _rule_based_soap(short_note)
    try:
        from yazklinik_konsult_agent import _llm_call
        prompt = f"{SOAP_PROMPT}\n\nKISA NOT:\n{short_note.strip()}\n\nSOAP JSON:"
        text, err, method = _llm_call(prompt, prefer=prefer, json_mode=True, step="treatment")
        out.method = method
        if err:
            out.error = err
        if text:
            m = re.search(r"\{[\s\S]*\}", text)
            if m:
                try:
                    data = json.loads(m.group(0))
                    out.subjective = str(data.get("subjective") or "")
                    out.objective = str(data.get("objective") or "")
                    out.assessment = str(data.get("assessment") or "")
                    out.plan = str(data.get("plan") or "")
                    out.patient_education = str(data.get("patient_education") or "")
                    out.follow_up = str(data.get("follow_up") or "")
                    out.needs_more_info = [str(x) for x in (data.get("needs_more_info") or [])]
                except Exception as e:
                    out.error = f"JSON parse: {e}"
    except Exception as e:
        out.error = f"{type(e).__name__}: {e}"
    fallback = _rule_based_soap(short_note, method=out.method or "local_rule_fallback")
    if not out.subjective:
        out.subjective = fallback.subjective
    if not out.objective:
        out.objective = fallback.objective
    if not out.assessment:
        out.assessment = fallback.assessment
    if not out.plan:
        out.plan = fallback.plan
    if not out.patient_education:
        out.patient_education = fallback.patient_education
    if not out.follow_up:
        out.follow_up = fallback.follow_up
    if not out.needs_more_info:
        out.needs_more_info = fallback.needs_more_info
    if not out.method:
        out.method = fallback.method
    return out


def format_as_markdown(s: SOAPNote) -> str:
    parts = ["## SOAP Notu (YZ-yardimli, doktor onayli)"]
    if s.subjective: parts.append(f"**S (Subjective):** {s.subjective}")
    if s.objective:  parts.append(f"**O (Objective):** {s.objective}")
    if s.assessment: parts.append(f"**A (Assessment):** {s.assessment}")
    if s.plan:       parts.append(f"**P (Plan):** {s.plan}")
    if s.patient_education:
        parts.append(f"\n*Hastaya:* {s.patient_education}")
    if s.follow_up:
        parts.append(f"*Takip:* {s.follow_up}")
    if s.needs_more_info:
        parts.append(f"\n**Eksik bilgi:**\n" + "\n".join(f"- {x}" for x in s.needs_more_info))
    return "\n\n".join(parts)


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION}


if __name__ == "__main__":
    s = expand_to_soap("kanama 2 gun, ta 130/85, smear normal")
    print(format_as_markdown(s))
