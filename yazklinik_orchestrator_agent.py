"""Multi-Agent Orchestrator - ajanlari zincirleme calistir.

Senaryolar:
    full_visit(case_text):
        konsult → ddx → workup → treatment → followup
        → ICD-10 öner
        → DDI kontrol (treatment.meds varsa)
        → SOAP genislet
        → Sonuc tek paket

    pubmed_research_pack(query):
        ceviri.search_pubmed → top 3 → her birine translate_pubmed_article
        → auto-index RAG
        → ozet markdown

    usg_full_pipeline(image_path, patient_key, lmp):
        vision_usg analyze → biyometri tahmin
        → usg_rapor build_draft (LLM yorum + Hadlock)
        → konsult.save_to_visit (hasta dosyasi)
        → instagram aday + hatira hazirlik (consent gerek)
        → RAG auto-index

LangGraph yerine basit Python (bagimliliksiz).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-orchestrator"


@dataclass
class StepResult:
    step: str
    ok: bool
    summary: str
    payload: Any = None
    duration_ms: int = 0
    error: Optional[str] = None


@dataclass
class OrchestrationResult:
    flow_name: str
    started_at: str
    finished_at: str = ""
    duration_sec: float = 0
    steps: List[StepResult] = field(default_factory=list)
    overall_ok: bool = True
    summary: str = ""
    agent_version: str = AGENT_VERSION


def _time_step(step_name: str, fn, *args, **kwargs) -> StepResult:
    """Bir adimi zamanla + hata yakala."""
    t0 = datetime.now()
    sr = StepResult(step=step_name, ok=False, summary="")
    try:
        result = fn(*args, **kwargs)
        sr.ok = True
        sr.payload = result
        if hasattr(result, "__dict__"):
            sr.summary = str(getattr(result, "summary", ""))[:120] or str(type(result).__name__)
        else:
            sr.summary = str(result)[:120]
    except Exception as e:
        sr.error = f"{type(e).__name__}: {e}"
        sr.summary = sr.error
    sr.duration_ms = int((datetime.now() - t0).total_seconds() * 1000)
    return sr


def full_visit(case_text: str, prefer: str = "ollama") -> OrchestrationResult:
    """5-step konsult + ICD10 + DDI + SOAP zinciri."""
    out = OrchestrationResult(
        flow_name="full_visit",
        started_at=datetime.now().isoformat(timespec="seconds"))

    # 1. Konsultasyon
    try:
        from yazklinik_konsult_agent import full_consultation
        s = _time_step("konsult", full_consultation, case_text, prefer=prefer)
        out.steps.append(s)
        if not s.ok:
            out.overall_ok = False
        kons = s.payload
    except Exception as e:
        out.steps.append(StepResult(step="konsult", ok=False,
                                       summary=f"import err: {e}", error=str(e)))
        out.overall_ok = False
        kons = None

    # 2. ICD-10
    if kons:
        try:
            from yazklinik_icd10_agent import suggest_codes
            note_text = (kons.case.presenting_complaint or "") + " " + (kons.most_likely or "")
            s = _time_step("icd10", suggest_codes, note_text, top_k=5, prefer=prefer)
            out.steps.append(s)
        except Exception as e:
            out.steps.append(StepResult(step="icd10", ok=False, error=str(e)))

    # 3. DDI (treatment'taki ilaclar)
    if kons and kons.treatment:
        try:
            from yazklinik_ddi_agent import check_interactions
            drugs = [t.name for t in kons.treatment if t.name]
            is_pregnant = bool(kons.case.gebelik_haftasi)
            s = _time_step("ddi", check_interactions, drugs, is_pregnant=is_pregnant)
            out.steps.append(s)
        except Exception as e:
            out.steps.append(StepResult(step="ddi", ok=False, error=str(e)))

    # 4. SOAP (eger case kisaysa, genislet)
    if kons and len(case_text) < 300:
        try:
            from yazklinik_soap_agent import expand_to_soap
            s = _time_step("soap", expand_to_soap, case_text, prefer=prefer)
            out.steps.append(s)
        except Exception as e:
            out.steps.append(StepResult(step="soap", ok=False, error=str(e)))

    out.finished_at = datetime.now().isoformat(timespec="seconds")
    try:
        out.duration_sec = (datetime.fromisoformat(out.finished_at) -
                              datetime.fromisoformat(out.started_at)).total_seconds()
    except Exception:
        pass
    out.summary = (f"{len([s for s in out.steps if s.ok])}/{len(out.steps)} step OK, "
                    f"{out.duration_sec:.1f} sec")
    return out


def pubmed_research_pack(query: str, max_articles: int = 3) -> OrchestrationResult:
    """PubMed top N makaleyi cek, ceviri, RAG'a indeksle."""
    out = OrchestrationResult(
        flow_name="pubmed_research_pack",
        started_at=datetime.now().isoformat(timespec="seconds"))

    try:
        from yazklinik_ceviri_agent import search_pubmed, translate_pubmed_article
        s = _time_step("pubmed_search", search_pubmed, query, max_results=max_articles)
        out.steps.append(s)
        if s.ok and s.payload:
            hits = s.payload.get("hits", [])
            for hit in hits[:max_articles]:
                pmid = hit.get("pmid")
                if pmid:
                    s2 = _time_step(f"translate_{pmid}", translate_pubmed_article,
                                       pmid, auto_index_rag=True)
                    out.steps.append(s2)
    except Exception as e:
        out.steps.append(StepResult(step="pubmed_pack", ok=False, error=str(e)))
        out.overall_ok = False

    out.finished_at = datetime.now().isoformat(timespec="seconds")
    out.summary = f"{len(out.steps)} step"
    return out


def usg_full_pipeline(image_path: str, patient_key: str = "",
                       lmp: Optional[str] = None) -> OrchestrationResult:
    """Vision + biyometri + rapor + RAG zinciri."""
    out = OrchestrationResult(
        flow_name="usg_full_pipeline",
        started_at=datetime.now().isoformat(timespec="seconds"))

    # 1. Vision analiz
    try:
        from yazklinik_vision_usg_agent import analyze_image
        s = _time_step("vision_analyze", analyze_image, image_path)
        out.steps.append(s)
        vision = s.payload
    except Exception as e:
        out.steps.append(StepResult(step="vision_analyze", ok=False, error=str(e)))
        vision = None

    # 2. USG rapor taslagi (vision'dan parse edilen olculer ile)
    if vision and patient_key:
        try:
            from yazklinik_usg_rapor_agent import USGInput, Measurement, build_draft
            measurements = []
            for vm in (vision.visible_measurements or []):
                # "BPD: 85 mm" -> Measurement
                import re
                m = re.match(r"(\w+)[:\s]+(\d+\.?\d*)", vm)
                if m:
                    measurements.append(Measurement(
                        name=m.group(1).upper(), value_mm=float(m.group(2))))
            inp = USGInput(
                patient_id=patient_key, patient_name=patient_key,
                exam_date=datetime.now().date().isoformat(),
                lmp=lmp, measurements=measurements,
                report_type="second_trimester")
            s2 = _time_step("usg_rapor_build", build_draft, inp)
            out.steps.append(s2)
        except Exception as e:
            out.steps.append(StepResult(step="usg_rapor_build", ok=False, error=str(e)))

    out.finished_at = datetime.now().isoformat(timespec="seconds")
    out.summary = f"{len(out.steps)} step"
    return out


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "flows": ["full_visit", "pubmed_research_pack", "usg_full_pipeline"]}


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
