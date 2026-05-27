"""YZ Konsultasyon Ajani - Uctan uca klinik karar destek sistemi.

Doktor vaka tarifini girer; ajan 5 adimli akilli zincir calistirir:

    1. EXTRACT  - Serbest metni yapilandirir (yas, gebelik, sikayet, vitaller...)
                  Eksik kritik bilgi varsa SORAR.
    2. DDx      - Ayirici tani (red flag + olasilik siralamali, kanit ile)
    3. WORKUP   - Onerilen laboratuvar / goruntuleme / ek anamnez / muayene
    4. TREATMENT- Tedavi plani (1. basamak / 2. basamak, dozaj, kontrendikasyon)
    5. PLAN     - Takip, hasta egitimi, kirmizi alarm bildirimleri, ICD-10

Calisma:
    - LLM cagrisi yazklinik_ceviri_agent'taki Ollama + OpenAI sarmalini kullanir
    - Her adim AYRI prompt (chain-of-thought + JSON cikti dayatma)
    - Yerel Ollama (qwen2.5:32b) varsayilan - hasta verisi PC'den cikmaz
    - Her oneri "DOKTOR ONAYI BEKLER" etiketi tasir

Asla:
    - "Hasta sunu yap" diye direktif vermez
    - Otomatik recete yazmaz
    - Hasta dosyasina otomatik kayit acmaz (doktor "Hasta dosyasina ekle" der)

Bagimlilik: stdlib + opsiyonel ceviri ajan modulleri (LLM cagrisi icin).
"""

from __future__ import annotations

import json
import os
import re
import textwrap
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


AGENT_VERSION = "2026.05.17-konsult-v2"
SOURCE_LABEL = "Klinik konsultasyon zinciri (OB-GYN)"

# Adim bazli model tercih sirasi (Ollama list'inden mevcut olani sec)
# meditron: tibbi LLM (Stanford), klinik sorular icin SOTA
# qwen2.5:72b: genel akil yurutme, JSON cikti dayatma iyi
# qwen2.5:32b: hizli, dengeli (fallback)
PREFERRED_MODELS_BY_STEP = {
    "extract":   ["qwen2.5:32b", "qwen2.5:72b", "qwen3-coder:30b"],  # JSON cikti
    "ddx":       ["meditron:70b", "qwen2.5:72b", "qwen2.5:32b"],     # tibbi akil
    "workup":    ["meditron:70b", "qwen2.5:32b"],                     # tibbi karar
    "treatment": ["meditron:70b", "qwen2.5:72b", "qwen2.5:32b"],      # ilac+doz
    "followup":  ["qwen2.5:32b", "meditron:70b"],                     # plan
}


# --- LLM helpers (ceviri ajanindan tembel import) ---

_OLLAMA_AVAILABLE_MODELS_CACHE = None


def _list_ollama_models() -> List[str]:
    """Ollama'da hangi modeller yuklu (cache 5dk). Bos liste dondurursa hata."""
    global _OLLAMA_AVAILABLE_MODELS_CACHE
    if _OLLAMA_AVAILABLE_MODELS_CACHE is not None:
        return _OLLAMA_AVAILABLE_MODELS_CACHE
    try:
        import urllib.request
        from yazklinik_ceviri_agent import DEFAULT_OLLAMA_URL
        req = urllib.request.Request(
            DEFAULT_OLLAMA_URL.rstrip("/") + "/api/tags",
            headers={"User-Agent": "YazKlinik/D700"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        _OLLAMA_AVAILABLE_MODELS_CACHE = [
            m.get("name", "") for m in (data.get("models") or [])]
    except Exception:
        _OLLAMA_AVAILABLE_MODELS_CACHE = []
    return _OLLAMA_AVAILABLE_MODELS_CACHE


def _pick_model_for_step(step: Optional[str]) -> Optional[str]:
    """Adim icin tercih edilen ilk yuklu modeli sec."""
    if not step:
        return None
    prefs = PREFERRED_MODELS_BY_STEP.get(step, [])
    if not prefs:
        return None
    available = set(_list_ollama_models())
    for p in prefs:
        if p in available:
            return p
    # Hicbiri yoksa ilk tercihi don, Ollama varsa pull eder
    return prefs[0] if prefs else None


def _llm_call(prompt: str, prefer: str = "ollama",
               model: Optional[str] = None,
               json_mode: bool = False,
               step: Optional[str] = None) -> Tuple[Optional[str], Optional[str], str]:
    """(text, error, used_method). LLM erisilemiyorsa (None, err, '').

    step: 'extract' | 'ddx' | 'workup' | 'treatment' | 'followup'
        - Model adi None ise step'e gore otomatik secer
          (meditron tibbi adimlar icin, qwen JSON icin)
    """
    try:
        from yazklinik_ceviri_agent import _ollama_generate, _openai_chat, DEFAULT_OLLAMA_MODEL
    except Exception as e:  # noqa: BLE001
        return None, f"LLM helper yuklenemedi: {e}", ""

    # Step bazli model otomatik secimi
    if not model and step:
        model = _pick_model_for_step(step)

    # Opsiyonlar: JSON modu icin temperature dusur
    options = {"temperature": 0.10 if json_mode else 0.25,
               "top_p": 0.9, "num_ctx": 8192}

    def try_ollama():
        out, err = _ollama_generate(prompt, model=model, options=options)
        return out, err, ("ollama:" + (model or DEFAULT_OLLAMA_MODEL))

    def try_openai():
        out, err = _openai_chat(prompt, model=model or "gpt-4o-mini")
        return out, err, ("openai:" + (model or "gpt-4o-mini"))

    if prefer == "openai":
        out, err, m = try_openai()
        if out:
            return out, None, m
        out2, err2, m2 = try_ollama()
        if out2:
            return out2, None, m2
        return None, err or err2, ""
    out, err, m = try_ollama()
    if out:
        return out, None, m
    out2, err2, m2 = try_openai()
    if out2:
        return out2, None, m2
    return None, err or err2, ""


# --- JSON parsing (LLM bazen markdown code-block icine sarar) ---

def _extract_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    # ```json ... ``` blogu
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # Ilk { ile son } arasi
    s = text.find("{"); e = text.rfind("}")
    if 0 <= s < e:
        snippet = text[s:e + 1]
        try:
            return json.loads(snippet)
        except Exception:
            pass
    try:
        return json.loads(text)
    except Exception:
        return None


# --- Persona ve system promptlar ---

PERSONA = textwrap.dedent("""\
    Sen Op. Dr. Hakan Yaz'a yardim eden 25 yillik OB-GYN konsultan hekimsin.
    ACOG, RCOG, TJOD kilavuzlarina hakimsin. Turkiye'deki TITCK ilac
    katalogunu, SGK kurallarini bilirsin. Cevaplarin daima:
    - Turkce, kisa, klinik, yapilandirilmis
    - Oneri olarak ifade edilmis (klinik karar doktorundur)
    - KVKK uyumlu (hicbir hasta PII'si tekrar etmez)
    - Klinik kilavuz baglantili (mevcut ise)
    - Ilac dozajlari acik, kontrendikasyonlu, gebelik kategorisi belirtilmis
    Bilmedigin sey icin uydurma; "yetersiz veri" de.""")


# --- Veri modelleri ---

@dataclass
class CaseStructured:
    yas: Optional[int] = None
    gravide: Optional[int] = None
    parite: Optional[str] = None             # "G2P1A0Y1" gibi
    gebelik_haftasi: Optional[int] = None
    son_adet_tarihi: Optional[str] = None    # ISO date
    presenting_complaint: str = ""
    duration: str = ""
    associated_symptoms: List[str] = field(default_factory=list)
    past_history: List[str] = field(default_factory=list)
    current_medications: List[str] = field(default_factory=list)
    allergies: List[str] = field(default_factory=list)
    vitals: Dict[str, Any] = field(default_factory=dict)
    exam_findings: Dict[str, Any] = field(default_factory=dict)
    labs: Dict[str, Any] = field(default_factory=dict)
    imaging: Dict[str, Any] = field(default_factory=dict)
    risk_factors: List[str] = field(default_factory=list)
    missing_critical_info: List[str] = field(default_factory=list)


@dataclass
class Differential:
    diagnosis: str
    icd10: str = ""
    probability: str = "medium"             # high | medium | low
    supporting_findings: List[str] = field(default_factory=list)
    against_findings: List[str] = field(default_factory=list)
    next_step_to_confirm: str = ""
    severity: str = "non_urgent"            # urgent | non_urgent
    notes: str = ""


@dataclass
class WorkupItem:
    category: str            # lab | imaging | exam | history
    name: str
    rationale: str = ""
    priority: str = "routine"  # urgent | priority | routine
    expected_finding: str = ""


@dataclass
class TreatmentOption:
    line: str                # "1.basamak" | "2.basamak" | "alternatif"
    intervention_type: str   # ilac | mudahale | konservatif | sevk | dogum
    name: str
    dose: str = ""
    duration: str = ""
    contraindications: List[str] = field(default_factory=list)
    pregnancy_category: str = ""   # A/B/C/D/X veya bos
    notes: str = ""


@dataclass
class FollowUp:
    interval: str = ""              # "1 hafta", "3 ay"
    what_to_watch: List[str] = field(default_factory=list)
    red_flags_to_return: List[str] = field(default_factory=list)
    next_tests: List[str] = field(default_factory=list)
    patient_counseling: List[str] = field(default_factory=list)


@dataclass
class ConsultationResult:
    case: CaseStructured
    red_flags: List[str] = field(default_factory=list)
    differentials: List[Differential] = field(default_factory=list)
    most_likely: str = ""
    workup: List[WorkupItem] = field(default_factory=list)
    treatment: List[TreatmentOption] = field(default_factory=list)
    follow_up: FollowUp = field(default_factory=FollowUp)
    patient_summary_tr: str = ""    # doktorun hastaya soyleyecegi sade aciklama
    confidence: str = "medium"
    reasoning_trace: List[str] = field(default_factory=list)
    used_methods: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    requires_doctor_review: bool = True
    agent_version: str = AGENT_VERSION
    finalized_at: str = ""


# --- Adim 1: EXTRACT - Serbest metni yapilandir ---

def _build_extract_prompt(free_text: str) -> str:
    return textwrap.dedent(f"""\
        {PERSONA}

        Asagidaki vaka tarifini SADECE JSON olarak yapilandir. Bilinmeyen alan icin null koy.
        "missing_critical_info" alanina kritik eksik bilgileri yaz.

        SEMA:
        {{
          "yas": int|null,
          "gravide": int|null,
          "parite": "G_P_A_Y" formatinda|null,
          "gebelik_haftasi": int|null,
          "son_adet_tarihi": "YYYY-MM-DD"|null,
          "presenting_complaint": "kisa cumle",
          "duration": "ne kadar suredir",
          "associated_symptoms": [...],
          "past_history": [...],
          "current_medications": [...],
          "allergies": [...],
          "vitals": {{"tansiyon":"...","nabiz":int,"ates":float,"satr":float}},
          "exam_findings": {{}},
          "labs": {{}},
          "imaging": {{}},
          "risk_factors": [...],
          "missing_critical_info": [...]
        }}

        VAKA:
        {free_text.strip()}

        JSON CIKTI (sadece JSON, baska metin yok):
        """)


def extract_case(free_text: str, prefer: str = "ollama") -> Tuple[CaseStructured, Dict[str, Any]]:
    prompt = _build_extract_prompt(free_text)
    text, err, method = _llm_call(prompt, prefer=prefer, json_mode=True, step="extract")
    trace = {"step": "extract", "method": method, "error": err, "raw_preview": (text or "")[:300]}
    if not text:
        return CaseStructured(presenting_complaint=free_text[:200].strip()), trace
    data = _extract_json(text)
    if not data:
        trace["error"] = (err or "") + " | JSON parse fail"
        return CaseStructured(presenting_complaint=free_text[:200].strip()), trace
    # Guvenli alan tipleri
    cs = CaseStructured()
    cs.yas = data.get("yas") if isinstance(data.get("yas"), int) else None
    cs.gravide = data.get("gravide") if isinstance(data.get("gravide"), int) else None
    cs.parite = data.get("parite") if isinstance(data.get("parite"), str) else None
    cs.gebelik_haftasi = data.get("gebelik_haftasi") if isinstance(data.get("gebelik_haftasi"), int) else None
    cs.son_adet_tarihi = data.get("son_adet_tarihi") if isinstance(data.get("son_adet_tarihi"), str) else None
    cs.presenting_complaint = str(data.get("presenting_complaint") or "").strip()
    cs.duration = str(data.get("duration") or "").strip()
    cs.associated_symptoms = [str(x) for x in (data.get("associated_symptoms") or []) if x]
    cs.past_history = [str(x) for x in (data.get("past_history") or []) if x]
    cs.current_medications = [str(x) for x in (data.get("current_medications") or []) if x]
    cs.allergies = [str(x) for x in (data.get("allergies") or []) if x]
    cs.vitals = data.get("vitals") if isinstance(data.get("vitals"), dict) else {}
    cs.exam_findings = data.get("exam_findings") if isinstance(data.get("exam_findings"), dict) else {}
    cs.labs = data.get("labs") if isinstance(data.get("labs"), dict) else {}
    cs.imaging = data.get("imaging") if isinstance(data.get("imaging"), dict) else {}
    cs.risk_factors = [str(x) for x in (data.get("risk_factors") or []) if x]
    cs.missing_critical_info = [str(x) for x in (data.get("missing_critical_info") or []) if x]
    return cs, trace


# --- Adim 2: DDx - Ayirici tani ---

def _build_ddx_prompt(case: CaseStructured) -> str:
    case_json = json.dumps(asdict(case), ensure_ascii=False, indent=2)
    return textwrap.dedent(f"""\
        {PERSONA}

        Asagidaki yapilandirilmis vakaya gore SADECE JSON olarak ayirici tani uret.
        - "red_flags": Bu hastada DERHAL dislamak/yonetmek gereken hayati durumlar
        - 5-8 farkli tani, olasilik (high/medium/low), supporting/against bulgular,
          ICD-10 kodu (mumkunse), tani dogrulamak icin "next_step", "severity"
        - "most_likely": bir cumle, en muhtemel tani

        SEMA:
        {{
          "red_flags": [...],
          "differentials": [
            {{
              "diagnosis":"...", "icd10":"O14.0", "probability":"high|medium|low",
              "supporting_findings":[...], "against_findings":[...],
              "next_step_to_confirm":"...", "severity":"urgent|non_urgent",
              "notes":"..."
            }}
          ],
          "most_likely":"...",
          "reasoning_summary":"2-3 cumle akil yurutme"
        }}

        VAKA:
        {case_json}

        JSON:
        """)


def generate_differential(case: CaseStructured, prefer: str = "ollama") -> Tuple[Dict[str, Any], Dict[str, Any]]:
    prompt = _build_ddx_prompt(case)
    text, err, method = _llm_call(prompt, prefer=prefer, json_mode=True, step="ddx")
    trace = {"step": "ddx", "method": method, "error": err}
    if not text:
        return {"red_flags": [], "differentials": [], "most_likely": ""}, trace
    data = _extract_json(text) or {}
    return data, trace


# --- Adim 3: WORKUP ---

def _build_workup_prompt(case: CaseStructured, ddx: Dict[str, Any]) -> str:
    return textwrap.dedent(f"""\
        {PERSONA}

        Vakaya ve ayirici tanilara gore SADECE JSON olarak onerilen TETKIK ve EK ANAMNEZ listesi:
        - category: "lab" | "imaging" | "exam" | "history"
        - priority: "urgent" (bugun) | "priority" (24-48 saat) | "routine" (planli)
        - "expected_finding": pozitif ya da negatif sonucun klinik anlami

        SEMA:
        {{
          "workup": [
            {{
              "category":"lab",
              "name":"Tam idrar tahlili",
              "rationale":"proteinuri preeklampsi sorgu",
              "priority":"urgent",
              "expected_finding":"+++ proteinuri preeklampsi tanisini destekler"
            }}
          ]
        }}

        VAKA:
        {json.dumps(asdict(case), ensure_ascii=False)}

        AYIRICI TANILAR:
        {json.dumps(ddx, ensure_ascii=False)}

        JSON:
        """)


def recommend_workup(case: CaseStructured, ddx: Dict[str, Any],
                      prefer: str = "ollama") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    prompt = _build_workup_prompt(case, ddx)
    text, err, method = _llm_call(prompt, prefer=prefer, json_mode=True, step="workup")
    trace = {"step": "workup", "method": method, "error": err}
    if not text:
        return [], trace
    data = _extract_json(text) or {}
    return list(data.get("workup") or []), trace


# --- Adim 4: TREATMENT ---

def _build_treatment_prompt(case: CaseStructured, ddx: Dict[str, Any]) -> str:
    is_pregnant = bool(case.gebelik_haftasi) or "gebe" in (case.presenting_complaint or "").lower()
    preg_note = ""
    if is_pregnant:
        preg_note = ("\nUYARI: Hasta GEBE. Tum ilac onerilerinde gebelik kategorisi "
                     "(A/B/C/D/X) belirt; X kategorideki ilaclari onerme.")
    return textwrap.dedent(f"""\
        {PERSONA}{preg_note}

        Vaka + ayirici tanilara gore SADECE JSON olarak TEDAVI PLANI cikar.
        - line: "1.basamak" | "2.basamak" | "alternatif"
        - intervention_type: "ilac" | "mudahale" | "konservatif" | "sevk" | "dogum"
        - "dose" net Turkce: ornek "Asetilsalisilik asit 100 mg 1x1 PO"
        - "pregnancy_category" gebede zorunlu, gerekirse "kontrendike"
        - "contraindications" liste

        SEMA:
        {{
          "treatment": [
            {{
              "line":"1.basamak",
              "intervention_type":"ilac",
              "name":"Aspirin 100 mg",
              "dose":"1x1 PO, geceleri",
              "duration":"36. haftaya kadar",
              "contraindications":["aktif PUD","aspirin alerjisi"],
              "pregnancy_category":"C/D (3. trimesterda dikkat)",
              "notes":"Preeklampsi proflaksisinde 12-16. haftada baslanir"
            }}
          ],
          "alternative_pathway":"1.basamak basarisiz ya da kontrendike ise..."
        }}

        VAKA:
        {json.dumps(asdict(case), ensure_ascii=False)}

        AYIRICI TANILAR:
        {json.dumps(ddx, ensure_ascii=False)}

        JSON:
        """)


def recommend_treatment(case: CaseStructured, ddx: Dict[str, Any],
                         prefer: str = "ollama") -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    prompt = _build_treatment_prompt(case, ddx)
    text, err, method = _llm_call(prompt, prefer=prefer, json_mode=True, step="treatment")
    trace = {"step": "treatment", "method": method, "error": err}
    if not text:
        return [], trace
    data = _extract_json(text) or {}
    return list(data.get("treatment") or []), trace


# --- Adim 5: FOLLOW-UP + sentez ---

def _build_followup_prompt(case: CaseStructured, ddx: Dict[str, Any]) -> str:
    return textwrap.dedent(f"""\
        {PERSONA}

        Vaka + ayirici tanilar isiginda SADECE JSON olarak takip plani cikar.
        - "patient_counseling": HASTAYA dogru tonda 3-5 maddelik aciklama (sade Turkce)
        - "red_flags_to_return": Hangi belirtilerde hasta acilen donmeli

        SEMA:
        {{
          "interval":"1 hafta sonra kontrol",
          "what_to_watch":[...],
          "red_flags_to_return":[...],
          "next_tests":[...],
          "patient_counseling":[...],
          "patient_summary_tr":"Hastaya yakin tonla 3-4 cumlelik aciklama"
        }}

        VAKA: {json.dumps(asdict(case), ensure_ascii=False)}
        AYIRICI TANILAR: {json.dumps(ddx, ensure_ascii=False)}

        JSON:
        """)


def recommend_followup(case: CaseStructured, ddx: Dict[str, Any],
                        prefer: str = "ollama") -> Tuple[Dict[str, Any], Dict[str, Any]]:
    prompt = _build_followup_prompt(case, ddx)
    text, err, method = _llm_call(prompt, prefer=prefer, json_mode=True, step="followup")
    trace = {"step": "followup", "method": method, "error": err}
    if not text:
        return {}, trace
    data = _extract_json(text) or {}
    return data, trace


# --- TAM KONSULTASYON ---

def full_consultation(free_text: str, prefer: str = "ollama",
                       skip_steps: Optional[List[str]] = None) -> ConsultationResult:
    """Tum zinciri calistir. skip_steps ile asama atlanabilir."""
    skip = set(skip_steps or [])
    result = ConsultationResult(case=CaseStructured())
    trace_log: List[str] = []

    # 1. EXTRACT
    case, t1 = extract_case(free_text, prefer=prefer)
    result.case = case
    trace_log.append(f"extract: {t1.get('method')} err={t1.get('error')}")
    if t1.get("error"):
        result.errors.append("extract: " + str(t1["error"]))
    if t1.get("method"):
        result.used_methods.append(t1["method"])

    # Eksik kritik bilgi varsa kullaniciya geri don
    if case.missing_critical_info and "extract" not in skip:
        result.reasoning_trace = trace_log
        result.finalized_at = datetime.now().isoformat(timespec="seconds")
        return result  # caller bakacak missing_critical_info'ya

    # 2. DDx
    if "ddx" not in skip:
        ddx_data, t2 = generate_differential(case, prefer=prefer)
        trace_log.append(f"ddx: {t2.get('method')} err={t2.get('error')}")
        if t2.get("error"):
            result.errors.append("ddx: " + str(t2["error"]))
        if t2.get("method"):
            result.used_methods.append(t2["method"])
        result.red_flags = [str(x) for x in (ddx_data.get("red_flags") or [])]
        result.most_likely = str(ddx_data.get("most_likely") or "")
        if ddx_data.get("reasoning_summary"):
            trace_log.append("ddx_reasoning: " + str(ddx_data["reasoning_summary"]))
        for d in (ddx_data.get("differentials") or []):
            if not isinstance(d, dict):
                continue
            result.differentials.append(Differential(
                diagnosis=str(d.get("diagnosis") or ""),
                icd10=str(d.get("icd10") or ""),
                probability=str(d.get("probability") or "medium"),
                supporting_findings=[str(x) for x in (d.get("supporting_findings") or [])],
                against_findings=[str(x) for x in (d.get("against_findings") or [])],
                next_step_to_confirm=str(d.get("next_step_to_confirm") or ""),
                severity=str(d.get("severity") or "non_urgent"),
                notes=str(d.get("notes") or ""),
            ))
    else:
        ddx_data = {}

    # 3. WORKUP
    if "workup" not in skip:
        workup_raw, t3 = recommend_workup(case, ddx_data, prefer=prefer)
        trace_log.append(f"workup: {t3.get('method')} err={t3.get('error')}")
        if t3.get("method"):
            result.used_methods.append(t3["method"])
        for w in workup_raw:
            if not isinstance(w, dict):
                continue
            result.workup.append(WorkupItem(
                category=str(w.get("category") or "exam"),
                name=str(w.get("name") or ""),
                rationale=str(w.get("rationale") or ""),
                priority=str(w.get("priority") or "routine"),
                expected_finding=str(w.get("expected_finding") or ""),
            ))

    # 4. TREATMENT
    if "treatment" not in skip:
        tx_raw, t4 = recommend_treatment(case, ddx_data, prefer=prefer)
        trace_log.append(f"treatment: {t4.get('method')} err={t4.get('error')}")
        if t4.get("method"):
            result.used_methods.append(t4["method"])
        for tx in tx_raw:
            if not isinstance(tx, dict):
                continue
            result.treatment.append(TreatmentOption(
                line=str(tx.get("line") or ""),
                intervention_type=str(tx.get("intervention_type") or "ilac"),
                name=str(tx.get("name") or ""),
                dose=str(tx.get("dose") or ""),
                duration=str(tx.get("duration") or ""),
                contraindications=[str(x) for x in (tx.get("contraindications") or [])],
                pregnancy_category=str(tx.get("pregnancy_category") or ""),
                notes=str(tx.get("notes") or ""),
            ))

    # 5. FOLLOW-UP
    if "followup" not in skip:
        fu_data, t5 = recommend_followup(case, ddx_data, prefer=prefer)
        trace_log.append(f"followup: {t5.get('method')} err={t5.get('error')}")
        if t5.get("method"):
            result.used_methods.append(t5["method"])
        if fu_data:
            result.follow_up = FollowUp(
                interval=str(fu_data.get("interval") or ""),
                what_to_watch=[str(x) for x in (fu_data.get("what_to_watch") or [])],
                red_flags_to_return=[str(x) for x in (fu_data.get("red_flags_to_return") or [])],
                next_tests=[str(x) for x in (fu_data.get("next_tests") or [])],
                patient_counseling=[str(x) for x in (fu_data.get("patient_counseling") or [])],
            )
            result.patient_summary_tr = str(fu_data.get("patient_summary_tr") or "")

    # Confidence
    result.confidence = _estimate_confidence(result)
    result.reasoning_trace = trace_log
    result.used_methods = sorted(set(result.used_methods))
    result.finalized_at = datetime.now().isoformat(timespec="seconds")
    return result


def _estimate_confidence(r: ConsultationResult) -> str:
    """Hata yok + 3+ DDx + 2+ workup + 1+ treatment => high."""
    if r.errors:
        return "low"
    if len(r.differentials) >= 3 and len(r.workup) >= 2 and len(r.treatment) >= 1:
        return "high"
    if len(r.differentials) >= 1:
        return "medium"
    return "low"


# --- Markdown export ---

def format_as_markdown(r: ConsultationResult, *, include_trace: bool = False) -> str:
    L: List[str] = []
    L.append("# YZ Konsultasyon Raporu")
    L.append(f"_Olusturulma: {r.finalized_at} | Guven: **{r.confidence}** | Yontem: {', '.join(r.used_methods) or 'yok'}_")
    L.append("")
    L.append("> **UYARI:** Bu rapor YZ destekli klinik karar destek ciktisidir. "
             "Klinik karar yetkili hekime aittir.")
    L.append("")
    L.append("## Yapilandirilmis Vaka")
    c = r.case
    bullets = []
    if c.yas: bullets.append(f"Yas: {c.yas}")
    if c.gravide: bullets.append(f"Gravide: {c.gravide}")
    if c.parite: bullets.append(f"Parite: {c.parite}")
    if c.gebelik_haftasi: bullets.append(f"Gebelik haftasi: {c.gebelik_haftasi}")
    if c.son_adet_tarihi: bullets.append(f"SAT: {c.son_adet_tarihi}")
    for b in bullets:
        L.append(f"- {b}")
    if c.presenting_complaint:
        L.append(f"- **Sikayet:** {c.presenting_complaint}")
    if c.duration:
        L.append(f"- **Sure:** {c.duration}")
    if c.associated_symptoms:
        L.append(f"- **Eslik eden:** {', '.join(c.associated_symptoms)}")
    if c.vitals:
        L.append(f"- **Vitaller:** {json.dumps(c.vitals, ensure_ascii=False)}")
    if c.missing_critical_info:
        L.append("")
        L.append("### Eksik Kritik Bilgi")
        for m in c.missing_critical_info:
            L.append(f"- [ ] {m}")

    if r.red_flags:
        L.append("")
        L.append("## KIRMIZI ALARMLAR")
        for rf in r.red_flags:
            L.append(f"- **{rf}**")

    if r.differentials:
        L.append("")
        L.append("## Ayirici Tanilar")
        L.append(f"_En muhtemel:_ **{r.most_likely or '-'}**")
        for i, d in enumerate(r.differentials, 1):
            urg = " (ACIL)" if d.severity == "urgent" else ""
            L.append(f"\n### {i}. {d.diagnosis}  [{d.probability}]{urg}")
            if d.icd10:
                L.append(f"- ICD-10: `{d.icd10}`")
            if d.supporting_findings:
                L.append(f"- Lehine: {', '.join(d.supporting_findings)}")
            if d.against_findings:
                L.append(f"- Aleyhine: {', '.join(d.against_findings)}")
            if d.next_step_to_confirm:
                L.append(f"- Dogrulamak icin: {d.next_step_to_confirm}")
            if d.notes:
                L.append(f"- Not: {d.notes}")

    if r.workup:
        L.append("")
        L.append("## Onerilen Tetkik / Ek Anamnez")
        urgent_first = sorted(r.workup, key=lambda w: {"urgent":0,"priority":1,"routine":2}.get(w.priority, 9))
        for w in urgent_first:
            L.append(f"- **[{w.priority.upper()}] {w.category}:** {w.name}")
            if w.rationale:
                L.append(f"    - Sebep: {w.rationale}")
            if w.expected_finding:
                L.append(f"    - Beklenen: {w.expected_finding}")

    if r.treatment:
        L.append("")
        L.append("## Tedavi Plani")
        by_line: Dict[str, List[TreatmentOption]] = {}
        for tx in r.treatment:
            by_line.setdefault(tx.line or "diger", []).append(tx)
        for line in ("1.basamak", "2.basamak", "alternatif"):
            items = by_line.pop(line, [])
            if not items:
                continue
            L.append(f"\n### {line}")
            for tx in items:
                L.append(f"- **{tx.name}** ({tx.intervention_type})")
                if tx.dose:
                    L.append(f"    - Doz: {tx.dose}")
                if tx.duration:
                    L.append(f"    - Sure: {tx.duration}")
                if tx.pregnancy_category:
                    L.append(f"    - Gebelik kat.: {tx.pregnancy_category}")
                if tx.contraindications:
                    L.append(f"    - Kontrendike: {', '.join(tx.contraindications)}")
                if tx.notes:
                    L.append(f"    - Not: {tx.notes}")
        for other_line, items in by_line.items():
            L.append(f"\n### {other_line}")
            for tx in items:
                L.append(f"- {tx.name} - {tx.dose}")

    fu = r.follow_up
    if fu.interval or fu.what_to_watch or fu.patient_counseling:
        L.append("")
        L.append("## Takip Plani")
        if fu.interval:
            L.append(f"- **Aralik:** {fu.interval}")
        if fu.what_to_watch:
            L.append(f"- **Izlenecek:** {', '.join(fu.what_to_watch)}")
        if fu.next_tests:
            L.append(f"- **Sonraki tetkikler:** {', '.join(fu.next_tests)}")
        if fu.red_flags_to_return:
            L.append("")
            L.append("### Hasta acilen donmeli ise:")
            for rf in fu.red_flags_to_return:
                L.append(f"- {rf}")
        if fu.patient_counseling:
            L.append("")
            L.append("### Hasta egitimi (doktor agziyla)")
            for pc in fu.patient_counseling:
                L.append(f"- {pc}")

    if r.patient_summary_tr:
        L.append("")
        L.append("## Hastaya Soylenecek (kisa)")
        L.append(f"> {r.patient_summary_tr}")

    if r.errors:
        L.append("")
        L.append("## Hatalar")
        for e in r.errors:
            L.append(f"- {e}")

    if include_trace and r.reasoning_trace:
        L.append("")
        L.append("## Akil Yurutme Izi")
        for t in r.reasoning_trace:
            L.append(f"- {t}")

    return "\n".join(L).strip() + "\n"


# --- Saglik kontrolu ---

def health_check() -> Dict[str, Any]:
    out: Dict[str, Any] = {"ok": True, "agent_version": AGENT_VERSION}
    try:
        from yazklinik_ceviri_agent import health_check as ce_health
        out["llm"] = ce_health()
    except Exception as e:  # noqa: BLE001
        out["llm_error"] = str(e)
    return out


if __name__ == "__main__":
    print("HEALTH:", json.dumps(health_check(), ensure_ascii=False, indent=2))
    if len(__import__("sys").argv) > 1:
        text = " ".join(__import__("sys").argv[1:])
        print("\n--- KONSULTASYON ---")
        r = full_consultation(text)
        print(format_as_markdown(r, include_trace=True))
    else:
        # Mini smoke
        sample = ("32 yas, G2P1, 34 hafta gebe. Son 2 gundur basagrisi, "
                  "gorme bulaniklasti. TA 158/102, idrar testinde ++ proteinuri. "
                  "Onceki gebelikte gestasyonel diyabet vardi.")
        r = full_consultation(sample, prefer="ollama")
        print("Confidence:", r.confidence)
        print("Most likely:", r.most_likely)
        print("Red flags:", r.red_flags)
        print("DDx count:", len(r.differentials))
        print("Workup count:", len(r.workup))
        print("Treatment count:", len(r.treatment))
        print("Methods:", r.used_methods)
        print("Errors:", r.errors)

