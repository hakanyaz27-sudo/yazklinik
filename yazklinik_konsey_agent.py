"""Konsey Vaka Sunumu Ajani.

Multidisipliner konsey (tumor board / yuksek riskli gebelik) icin
otomatik vaka sunumu hazirla:
    - Anamnez ozeti
    - Lab + goruntuleme bulgulari
    - Mevcut tedavi
    - Sorulan sorular
    - Literatur referansi (RAG'dan)
    - PowerPoint slide taslagi (markdown)
"""
from __future__ import annotations

import json
import sqlite3
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-konsey"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")


@dataclass
class ConseyVakaInput:
    patient_id: str
    patient_initials: str   # anonim
    age: int = 0
    diagnosis: str = ""
    clinical_summary: str = ""
    relevant_labs: str = ""
    imaging: str = ""
    current_treatment: str = ""
    questions: List[str] = field(default_factory=list)


@dataclass
class ConseyVakaSlide:
    slide_number: int
    title: str
    bullets: List[str] = field(default_factory=list)
    notes: str = ""


@dataclass
class ConseyVakaSunum:
    case: ConseyVakaInput
    presented_at: str
    slides: List[ConseyVakaSlide] = field(default_factory=list)
    markdown_export: str = ""
    rag_citations: List[str] = field(default_factory=list)
    agent_version: str = AGENT_VERSION


def build_presentation(case: ConseyVakaInput,
                        use_rag: bool = True) -> ConseyVakaSunum:
    """Yapilandirilmis vaka -> slayt seti + markdown."""
    sunum = ConseyVakaSunum(
        case=case, presented_at=datetime.now().isoformat(timespec="seconds"))

    # Slide 1: Vaka tanitimi
    sunum.slides.append(ConseyVakaSlide(
        slide_number=1, title="Vaka Tanıtımı",
        bullets=[
            f"Hasta: {case.patient_initials} ({case.age} y)",
            f"Tanı: {case.diagnosis}",
            f"Sunum tarihi: {sunum.presented_at[:10]}",
        ]))

    # Slide 2: Klinik ozet
    sunum.slides.append(ConseyVakaSlide(
        slide_number=2, title="Klinik Özet",
        bullets=[s.strip() for s in case.clinical_summary.split(".") if s.strip()][:5],
        notes=case.clinical_summary))

    # Slide 3: Lab
    if case.relevant_labs:
        sunum.slides.append(ConseyVakaSlide(
            slide_number=3, title="Laboratuvar Bulguları",
            bullets=[s.strip() for s in case.relevant_labs.split(",") if s.strip()][:6]))

    # Slide 4: Goruntuleme
    if case.imaging:
        sunum.slides.append(ConseyVakaSlide(
            slide_number=4, title="Görüntüleme",
            bullets=[s.strip() for s in case.imaging.split(".") if s.strip()][:4]))

    # Slide 5: Mevcut tedavi
    if case.current_treatment:
        sunum.slides.append(ConseyVakaSlide(
            slide_number=5, title="Mevcut Tedavi",
            bullets=[case.current_treatment]))

    # Slide 6: Konseye sorular
    if case.questions:
        sunum.slides.append(ConseyVakaSlide(
            slide_number=6, title="Konseye Sorular",
            bullets=case.questions))

    # Slide 7: Literatur (RAG)
    if use_rag:
        try:
            from yazklinik_rag import semantic_search
            query = f"{case.diagnosis} tedavi guncel"
            results = semantic_search(query, top_k=3) or []
            cites = []
            for r in results[:3]:
                if isinstance(r, dict):
                    cites.append(r.get("source") or r.get("title") or str(r)[:80])
                else:
                    cites.append(str(r)[:80])
            sunum.rag_citations = cites
            sunum.slides.append(ConseyVakaSlide(
                slide_number=len(sunum.slides) + 1, title="Güncel Literatür",
                bullets=cites or ["RAG sonucu yok"]))
        except Exception:
            pass

    # Markdown export
    lines = [f"# Konsey Vakası - {case.patient_initials}", ""]
    for sl in sunum.slides:
        lines.append(f"## {sl.title}")
        for b in sl.bullets:
            lines.append(f"- {b}")
        lines.append("")
    sunum.markdown_export = "\n".join(lines)
    return sunum


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION}


if __name__ == "__main__":
    c = ConseyVakaInput(
        patient_id="P-2026-0042", patient_initials="A.Y.", age=34,
        diagnosis="Endometrium kanseri evre IB",
        clinical_summary="Postmenopozal kanama 3 ay. Endometrium 18 mm. Biyopsi: grade 2 endometrioid CA.",
        relevant_labs="CA-125: 28 U/ml, Hb: 11.2",
        imaging="MR pelvis: myometrial invazyon <50%, lenf nodu negatif",
        current_treatment="Cerrahi planlandi (TAH + BSO + lenf nodu sampling)",
        questions=["Adjuvan RT gerek var mi?", "Lenf nodu diseksiyonu kapsami?"])
    s = build_presentation(c, use_rag=False)
    print(s.markdown_export[:500])
    print(f"\n{len(s.slides)} slayt uretildi")
