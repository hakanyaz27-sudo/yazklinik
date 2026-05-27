"""ICD-10 + SGK Kod Onerici Ajani.

Klinik notlardan ICD-10 kodlarini onerir (SGK fatura icin zorunlu).
- TR_ICD10 katalogu kullanir (static/tr_icd10_katalogu.txt)
- LLM ile semantic matching (meditron:70b)
- En olasi 3-5 kod + olasilik + kategori
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-icd10"

ICD10_CATALOG_PATH = Path(__file__).parent / "static" / "tr_icd10_katalogu.txt"


@dataclass
class ICD10Suggestion:
    code: str
    description: str
    confidence: int = 0       # 0-100
    category: str = ""
    primary: bool = False
    reason: str = ""


@dataclass
class CodingResult:
    note_input: str
    suggestions: List[ICD10Suggestion] = field(default_factory=list)
    primary_diagnosis_code: str = ""
    method: str = ""
    requires_doctor_review: bool = True
    error: Optional[str] = None
    agent_version: str = AGENT_VERSION


_CATALOG_CACHE = None


def _load_catalog() -> List[Dict[str, str]]:
    global _CATALOG_CACHE
    if _CATALOG_CACHE is not None:
        return _CATALOG_CACHE
    out = []
    if ICD10_CATALOG_PATH.exists():
        try:
            for line in ICD10_CATALOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                # Format: "O14.0   Preeklampsi" gibi
                m = re.match(r"([A-Z]\d+(?:\.\d+)?)\s+(.+)", line)
                if m:
                    out.append({"code": m.group(1), "description": m.group(2)})
        except Exception:
            pass
    _CATALOG_CACHE = out
    return out


def suggest_codes(note: str, top_k: int = 5, prefer: str = "ollama") -> CodingResult:
    """Klinik notunu ICD-10 koduyla esle.
    1. Hizli text match (catalogtan)
    2. LLM ile semantic genisletme (meditron)
    """
    out = CodingResult(note_input=note)
    if not note or not note.strip():
        out.error = "Bos not"
        return out

    # 1. Static catalog text match
    catalog = _load_catalog()
    note_lower = note.lower()
    matches = []
    for item in catalog:
        desc_lower = item["description"].lower()
        # Basit overlap
        score = 0
        for word in re.findall(r"\w{4,}", note_lower):
            if word in desc_lower:
                score += 1
        if score > 0:
            matches.append((score, item))
    matches.sort(key=lambda x: -x[0])
    for score, item in matches[:top_k]:
        out.suggestions.append(ICD10Suggestion(
            code=item["code"], description=item["description"],
            confidence=min(80, score * 15),
            category=item["code"][0],
            reason="static match"))

    # 2. LLM ile semantic
    if prefer != "skip":
        try:
            from yazklinik_konsult_agent import _llm_call
            prompt = (
                f"Asagidaki klinik notu ICD-10 TR koduyla esle. EN OLASILI 3 kodu "
                f"JSON listesi olarak ver:\n[{{\"code\": \"...\", \"description\": \"...\", "
                f"\"confidence\": 0-100, \"primary\": true/false, \"reason\": \"...\"}}]\n\n"
                f"NOT:\n{note}\n\nJSON:")
            text, err, method = _llm_call(prompt, prefer=prefer, json_mode=True, step="extract")
            out.method = method
            if text:
                m = re.search(r"\[[\s\S]*\]", text)
                if m:
                    try:
                        data = json.loads(m.group(0))
                        # LLM cikti onerilerini onlemeden ekle (duplikatlardan kacin)
                        existing_codes = {s.code for s in out.suggestions}
                        for d in data:
                            if not isinstance(d, dict):
                                continue
                            code = str(d.get("code") or "")
                            if not code or code in existing_codes:
                                continue
                            out.suggestions.append(ICD10Suggestion(
                                code=code,
                                description=str(d.get("description") or ""),
                                confidence=int(d.get("confidence") or 50),
                                category=code[0] if code else "",
                                primary=bool(d.get("primary")),
                                reason=str(d.get("reason") or "llm")))
                    except Exception as e:
                        out.error = f"LLM JSON parse: {e}"
        except Exception:
            pass

    # Sirala + primary sec
    out.suggestions.sort(key=lambda s: -s.confidence)
    out.suggestions = out.suggestions[:top_k]
    if out.suggestions:
        primary = next((s for s in out.suggestions if s.primary), out.suggestions[0])
        out.primary_diagnosis_code = primary.code

    return out


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "catalog_size": len(_load_catalog()),
            "catalog_path": str(ICD10_CATALOG_PATH)}


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
    r = suggest_codes("32 hafta gebe preeklampsi suphesi proteinuri", prefer="skip")
    for s in r.suggestions[:3]:
        print(f"  {s.code} - {s.description} ({s.confidence})")
