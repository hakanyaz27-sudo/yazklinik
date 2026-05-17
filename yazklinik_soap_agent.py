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


def expand_to_soap(short_note: str, prefer: str = "ollama") -> SOAPNote:
    out = SOAPNote(raw_input=short_note)
    if not short_note or not short_note.strip():
        out.error = "Bos not"
        return out
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
