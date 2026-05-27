"""Voice Command Dispatcher - eli serbest klinik kullanim.

Alex zaten sesli sohbet ediyor; bu modul, niyet tespit sonrasi
KOMUTU YAPMASINI saglar:
    "yeni hasta Ayse Yilmaz" -> hasta olustur ve yonlendir
    "reçete yaz parasetamol" -> recete agentina gec
    "BPD 85" -> aktif USG'ye olcum ekle
    "kaydet" -> mevcut formu submit et
    "ana sayfa" -> /
    "sonraki hasta" -> randevu siradaki
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


AGENT_VERSION = "2026.05.17-voice-cmd"


@dataclass
class VoiceCommand:
    intent: str           # "navigate" | "create" | "save" | "measure" | "search" | "unknown"
    target: str = ""      # url / form id / measurement key
    params: Dict[str, Any] = field(default_factory=dict)
    confidence: int = 0
    raw_text: str = ""
    suggested_action: str = ""
    requires_confirm: bool = False


def _fold(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return t.lower().replace("ı", "i")


COMMAND_PATTERNS = [
    # (regex, intent, target_template, params_extractor, confidence)
    (r"\byeni hasta\s+(\w+(?:\s+\w+)?)", "create", "/yeni-hasta",
     lambda m: {"name": m.group(1)}, 85),
    (r"\b(ana sayfa|hastalar)\b", "navigate", "/", lambda m: {}, 90),
    (r"\b(randevular|takvim|randevu listesi)\b", "navigate", "/randevular",
     lambda m: {}, 90),
    (r"\b(yeni randevu|randevu ekle)\b", "navigate", "/randevu/yeni",
     lambda m: {}, 88),
    (r"\b(dashboard|gosterge|panel)\b", "navigate", "/dashboard", lambda m: {}, 88),
    (r"\b(ajanlar|agents)\b", "navigate", "/ajanlar", lambda m: {}, 88),
    (r"\b(konsult|konsultasyon|tani)\b", "navigate", "/yz-konsultasyon",
     lambda m: {}, 85),
    (r"\b(rag|bilgi havuzu|alex bilgi)\b", "navigate", "/alex-rag-merkezi",
     lambda m: {}, 80),
    (r"\b(veridb|veri tabani|database)\b", "navigate", "/veridb-merkezi",
     lambda m: {}, 80),
    (r"\b(instagram|sosyal medya|post)\b", "navigate", "/instagram-hazirla",
     lambda m: {}, 80),
    (r"\b(ceviri|pubmed|makale)\b", "navigate", "/ceviri-merkezi", lambda m: {}, 85),
    (r"\bbpd\s+(\d+(?:[.,]\d+)?)", "measure", "bpd_mm",
     lambda m: {"value": float(m.group(1).replace(",", "."))}, 92),
    (r"\bhc\s+(\d+(?:[.,]\d+)?)", "measure", "hc_mm",
     lambda m: {"value": float(m.group(1).replace(",", "."))}, 92),
    (r"\bac\s+(\d+(?:[.,]\d+)?)", "measure", "ac_mm",
     lambda m: {"value": float(m.group(1).replace(",", "."))}, 92),
    (r"\bfl\s+(\d+(?:[.,]\d+)?)", "measure", "fl_mm",
     lambda m: {"value": float(m.group(1).replace(",", "."))}, 92),
    (r"\btansiyon\s+(\d{2,3})\s*[\/\\]\s*(\d{2,3})", "measure", "blood_pressure",
     lambda m: {"systolic": int(m.group(1)), "diastolic": int(m.group(2))}, 95),
    (r"\bkilo\s+(\d{2,3}(?:[.,]\d)?)", "measure", "weight_kg",
     lambda m: {"value": float(m.group(1).replace(",", "."))}, 90),
    (r"\b(kaydet|save|tamam|kayit et)\b", "save", "active_form",
     lambda m: {}, 80),
    (r"\b(iptal|vazgec|cancel)\b", "cancel", "active_form", lambda m: {}, 80),
    (r"\b(sonraki hasta|next|sira|sonraki)\b", "navigate", "/randevular?next=1",
     lambda m: {}, 75),
    (r"\barama?\s+(.+)", "search", "/api/search/full-text",
     lambda m: {"query": m.group(1).strip()}, 78),
]


def parse(spoken_text: str) -> VoiceCommand:
    """Sesli komutu yapilandirilmis aksiyona cevir."""
    if not spoken_text or not spoken_text.strip():
        return VoiceCommand(intent="unknown", raw_text=spoken_text or "")
    text_folded = _fold(spoken_text)
    for pattern, intent, target, params_fn, conf in COMMAND_PATTERNS:
        m = re.search(pattern, text_folded)
        if m:
            try:
                params = params_fn(m)
            except Exception:
                params = {}
            cmd = VoiceCommand(intent=intent, target=target,
                                 params=params, confidence=conf,
                                 raw_text=spoken_text)
            if intent == "create" or intent == "save":
                cmd.requires_confirm = True
            cmd.suggested_action = _describe(cmd)
            return cmd
    return VoiceCommand(intent="unknown", raw_text=spoken_text,
                         suggested_action="Anlamadım, tekrar dener misin?")


def _describe(cmd: VoiceCommand) -> str:
    if cmd.intent == "navigate":
        return f"-> {cmd.target}"
    if cmd.intent == "create":
        return f"Yeni hasta oluştur: {cmd.params.get('name', '?')}"
    if cmd.intent == "save":
        return "Aktif formu kaydet"
    if cmd.intent == "cancel":
        return "Aktif işlemi iptal et"
    if cmd.intent == "measure":
        return f"Ölçüm kaydet: {cmd.target} = {cmd.params}"
    if cmd.intent == "search":
        return f"Ara: {cmd.params.get('query', '')}"
    return "Bilinmiyor"


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "patterns": len(COMMAND_PATTERNS)}


if __name__ == "__main__":
    tests = ["yeni hasta Ayse Yilmaz", "BPD 85", "tansiyon 158/102",
             "randevular", "ana sayfa", "kaydet", "araba ne",
             "kilo 72.5", "konsultasyon", "ajanlar"]
    for t in tests:
        c = parse(t)
        print(f"  '{t}' -> {c.intent}({c.target}) conf={c.confidence} | {c.suggested_action}")
