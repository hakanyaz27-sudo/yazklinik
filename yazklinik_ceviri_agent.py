"""Tibbi Ceviri Ajani.

Ingilizce kaynaklardan (PubMed, makale URL, dogrudan metin) Turkce
medikal ceviri yapar. Proje mevcut LLM stack'ini kullanir:

    1. Ollama lokal (qwen2.5:32b RTX 5090 profili) - varsayilan
    2. OpenAI (OPENAI_API_KEY env varsa) - fallback
    3. "Prompt cikti" modu - LLM erisilemiyorsa, doktor ChatGPT'ye yapistirir

PubMed:
    NCBI E-utilities ucretsiz, API key gerekmez. Hizli limit: 3 req/sec.
    esearch -> PMID listesi, efetch -> XML metadata + abstract.

Ozellikler:
    - search_pubmed(query, max_results)
    - fetch_pubmed_pmid(pmid) -> {title, abstract, authors, year, journal, doi}
    - translate_text(text, target_lang='tr') -> {translation, method, model}
    - translate_pubmed_article(pmid) -> tam paket
    - format_as_markdown(article) -> export
    - build_translation_prompt(text) -> ChatGPT yapistir-cikar

Asla:
    - Hasta verisi cevirmek icin disariya cikmaz (Ollama yerel zaten)
    - PubMed sorgusu icine hasta kimligi koymaz
    - Klinik karar yorumu vermez - sadece ceviri ve oz

Bagimlilik: stdlib (urllib, xml.etree) + opsiyonel requests.
"""

from __future__ import annotations

import json
import os
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


AGENT_VERSION = "2026.05.16-ceviri"
SOURCE_LABEL = "Ingilizce medikal kaynak -> Turkce"

# NCBI E-utilities
NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
NCBI_TIMEOUT = 15
USER_AGENT = "YazKlinik/D700 (+https://ucandoktor.com)"

# Ollama defaults (config.env ile uyumlu)
def _normalize_ollama_base_url(raw: str) -> str:
    """Accept either Ollama root or a full API endpoint from config.env."""
    url = (raw or "http://localhost:11434").strip().rstrip("/")
    for suffix in ("/api/generate", "/api/chat", "/api/tags"):
        if url.lower().endswith(suffix):
            return url[: -len(suffix)].rstrip("/")
    return url


DEFAULT_OLLAMA_URL = _normalize_ollama_base_url(
    os.environ.get("YAZKLINIK_OLLAMA_URL") or os.environ.get("OLLAMA_URL")
    or "http://localhost:11434")
DEFAULT_OLLAMA_MODEL = os.environ.get("YAZKLINIK_OLLAMA_MODEL") or "qwen2.5:32b"
DEFAULT_OLLAMA_KEEP_ALIVE = os.environ.get("YAZKLINIK_OLLAMA_KEEP_ALIVE") or "5m"
DEFAULT_OLLAMA_TIMEOUT = int(os.environ.get("YAZKLINIK_OLLAMA_TIMEOUT") or 180)


# --- Veri modelleri ---

@dataclass
class PubMedArticle:
    pmid: str
    title: str = ""
    abstract: str = ""
    authors: List[str] = field(default_factory=list)
    journal: str = ""
    year: str = ""
    doi: str = ""
    pubmed_url: str = ""
    raw_xml_snippet: str = ""


@dataclass
class TranslationResult:
    source_text: str
    translated_text: str
    method: str                    # "ollama" | "openai" | "prompt_only"
    model: str
    target_lang: str = "tr"
    source_lang: str = "en"
    fallback_chain: List[str] = field(default_factory=list)
    error: Optional[str] = None
    requires_doctor_review: bool = True
    agent_version: str = AGENT_VERSION


@dataclass
class PubMedSearchHit:
    pmid: str
    title: str = ""
    journal: str = ""
    year: str = ""


@dataclass
class FullArticleResult:
    article: PubMedArticle
    title_tr: str = ""
    abstract_tr: str = ""
    summary_tr: str = ""           # 3-5 satir ozet
    method: str = ""
    fallback_chain: List[str] = field(default_factory=list)
    error: Optional[str] = None
    agent_version: str = AGENT_VERSION


# --- Mini medikal sozluk (OB-GYN agirlikli) ---

MEDICAL_GLOSSARY: Dict[str, str] = {
    "pregnancy": "gebelik",
    "obstetric": "obstetrik",
    "gynecology": "jinekoloji",
    "gestational": "gestasyonel",
    "trimester": "trimester",
    "fetal": "fetal",
    "preeclampsia": "preeklampsi",
    "eclampsia": "eklampsi",
    "ectopic": "ektopik",
    "miscarriage": "dusuk",
    "abortion": "abortus",
    "hyperemesis": "hiperemezis",
    "ultrasound": "ultrason",
    "ultrasonography": "ultrasonografi",
    "biometry": "biyometri",
    "amniocentesis": "amniyosentez",
    "cesarean": "sezaryen",
    "delivery": "dogum",
    "labor": "dogum eylemi",
    "induction": "induksiyon",
    "postpartum": "postpartum",
    "intrauterine": "intrauterin",
    "fertility": "fertilite",
    "infertility": "infertilite",
    "menstruation": "menstruasyon",
    "menopause": "menopoz",
    "endometriosis": "endometriozis",
    "polycystic ovary syndrome": "polikistik over sendromu",
    "pcos": "PKOS",
    "hypothyroidism": "hipotiroidi",
    "gestational diabetes": "gestasyonel diabetes mellitus (GDM)",
    "smear": "smear",
    "cervical": "servikal",
    "uterine": "uterin",
    "ovarian": "overyan",
    "follicle": "folikul",
    "progesterone": "progesteron",
    "estrogen": "ostrojen",
    "human chorionic gonadotropin": "hCG",
    "fetus": "fetus",
    "newborn": "yenidogan",
    "neonatal": "neonatal",
    "low birth weight": "dusuk dogum agirligi",
    "preterm": "preterm",
    "stillbirth": "olu dogum",
    "vbac": "VBAC (sezaryen sonrasi vajinal dogum)",
    "iugr": "IUGR (intrauterin buyume kisitlanmasi)",
    "pprom": "PPROM (preterm erken membran ruptur)",
    "anemia": "anemi",
    "fibroid": "myom",
    "leiomyoma": "leiomyom",
    "hyperplasia": "hiperplazi",
    "cancer": "kanser",
    "cervix": "serviks",
    "ovary": "over",
    "endometrium": "endometriyum",
    "hysterectomy": "histerektomi",
    "biopsy": "biyopsi",
    "doppler": "Doppler",
    "amniotic": "amniyotik",
    "placental": "plasental",
    "placenta previa": "plasenta previa",
    "abruption": "ablasyo",
    "hemorrhage": "kanama",
    "postpartum hemorrhage": "postpartum kanama",
    "hellp syndrome": "HELLP sendromu",
    "antibiotic": "antibiyotik",
    "infection": "enfeksiyon",
    "antibiotic prophylaxis": "antibiyotik proflaksisi",
}


def get_glossary_hints(text: str, max_terms: int = 30) -> List[Tuple[str, str]]:
    """Metinde gecen sozluk terimlerini cikar (ceviri promptuna eklenecek)."""
    lower = text.lower()
    hits: List[Tuple[str, str]] = []
    for en, tr in MEDICAL_GLOSSARY.items():
        if en in lower:
            hits.append((en, tr))
            if len(hits) >= max_terms:
                break
    return hits


# --- PubMed E-utilities ---

def _http_get(url: str, timeout: int = NCBI_TIMEOUT) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read().decode("utf-8", errors="replace")


def search_pubmed(query: str, max_results: int = 20) -> Dict[str, Any]:
    """ESearch ile PMID listesi + ESummary ile basit metadata."""
    out: Dict[str, Any] = {
        "ok": False,
        "query": query,
        "hits": [],
        "agent_version": AGENT_VERSION,
    }
    if not query or not query.strip():
        out["error"] = "Bos sorgu"
        return out

    try:
        # 1) ESearch
        url = (
            f"{NCBI_BASE}/esearch.fcgi?db=pubmed&retmode=json"
            f"&retmax={max(1, min(int(max_results), 50))}"
            f"&term={urllib.parse.quote(query)}"
        )
        data = json.loads(_http_get(url))
        pmids = (data.get("esearchresult") or {}).get("idlist") or []
        if not pmids:
            out["ok"] = True
            return out

        # 2) ESummary
        url2 = (
            f"{NCBI_BASE}/esummary.fcgi?db=pubmed&retmode=json"
            f"&id={','.join(pmids)}"
        )
        meta = json.loads(_http_get(url2))
        result = (meta.get("result") or {})
        hits: List[Dict[str, Any]] = []
        for pmid in pmids:
            doc = result.get(pmid) or {}
            year = ""
            pubdate = doc.get("pubdate") or ""
            m = re.match(r"(\d{4})", pubdate)
            if m:
                year = m.group(1)
            hits.append(asdict(PubMedSearchHit(
                pmid=pmid,
                title=str(doc.get("title") or "").strip(),
                journal=str(doc.get("source") or ""),
                year=year,
            )))
        out["ok"] = True
        out["hits"] = hits
        return out
    except urllib.error.URLError as e:
        out["error"] = f"NCBI baglanti hatasi: {e}"
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
    return out


def fetch_pubmed_pmid(pmid: str) -> PubMedArticle:
    """EFetch XML ile tam abstract + metadata."""
    pmid_str = str(pmid).strip()
    if not re.fullmatch(r"\d{1,12}", pmid_str):
        raise ValueError(f"Gecersiz PMID: {pmid_str!r}")

    url = (
        f"{NCBI_BASE}/efetch.fcgi?db=pubmed&id={pmid_str}"
        f"&rettype=abstract&retmode=xml"
    )
    xml = _http_get(url)
    try:
        root = ET.fromstring(xml)
    except ET.ParseError as e:
        raise RuntimeError(f"PubMed XML parse hatasi: {e}") from e

    art = PubMedArticle(pmid=pmid_str, pubmed_url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid_str}/")

    # Title
    title_node = root.find(".//ArticleTitle")
    if title_node is not None and title_node.text:
        art.title = title_node.text.strip()

    # Abstract (birden fazla AbstractText olabilir; Label ile)
    abs_parts: List[str] = []
    for at in root.findall(".//Abstract/AbstractText"):
        label = at.attrib.get("Label", "")
        # Inner text dahil tum child'lar
        text = "".join(at.itertext()).strip()
        if not text:
            continue
        if label:
            abs_parts.append(f"{label.upper()}: {text}")
        else:
            abs_parts.append(text)
    art.abstract = "\n\n".join(abs_parts)

    # Authors
    authors: List[str] = []
    for au in root.findall(".//AuthorList/Author"):
        last = au.findtext("LastName") or ""
        initials = au.findtext("Initials") or ""
        if last:
            authors.append(f"{last} {initials}".strip())
    art.authors = authors[:20]

    # Journal + year
    jt = root.find(".//Journal/Title")
    if jt is not None and jt.text:
        art.journal = jt.text.strip()
    year_node = (root.find(".//Article/Journal/JournalIssue/PubDate/Year")
                 or root.find(".//Article/ArticleDate/Year"))
    if year_node is not None and year_node.text:
        art.year = year_node.text.strip()

    # DOI
    for aid in root.findall(".//ArticleIdList/ArticleId"):
        if aid.attrib.get("IdType") == "doi" and aid.text:
            art.doi = aid.text.strip()
            break

    # Snippet (debug)
    art.raw_xml_snippet = xml[:600]
    return art


# --- Ceviri promptlari ---

TR_TRANSLATION_SYSTEM = (
    "You are a careful Turkish medical translator. "
    "Translate clinical English into clear, faithful Turkish suitable for an obstetrician. "
    "Keep technical accuracy. Preserve drug names, units (mg, IU, mmHg), gestational weeks, "
    "and standard abbreviations (BPD, HC, AC, FL, EFW, ICD-10 codes). "
    "Use Turkish medical terminology where appropriate. Do not summarize unless asked. "
    "Do not invent data. Output ONLY the Turkish translation, no commentary, no markdown headers."
)

TR_SUMMARY_SYSTEM = (
    "You are a Turkish medical writer. Summarize the given English clinical article "
    "in 3-5 short Turkish bullet points for a practicing obstetrician. "
    "Focus on: study design, primary outcome, key result, clinical implication. "
    "Output Turkish bullets only, no preamble, no English."
)


def build_translation_prompt(text: str, target_lang: str = "tr",
                              include_glossary: bool = True) -> str:
    """LLM'e gonderilecek prompt (system+user birlestirilmis halde).
    UI 'ChatGPT'ye yapistir' butonu icin de ayni prompt kullanir.
    """
    if target_lang != "tr":
        sys_msg = (
            f"You are a careful medical translator. Translate the following English "
            f"clinical text into {target_lang} accurately. Keep units and abbreviations."
        )
    else:
        sys_msg = TR_TRANSLATION_SYSTEM

    glossary_block = ""
    if include_glossary and target_lang == "tr":
        hints = get_glossary_hints(text)
        if hints:
            lines = [f"- {en} -> {tr}" for en, tr in hints]
            glossary_block = (
                "\n\nGlossary hints (use these Turkish equivalents):\n"
                + "\n".join(lines) + "\n"
            )

    return f"{sys_msg}{glossary_block}\n\nSOURCE:\n{text.strip()}\n\nTRANSLATION:"


def build_summary_prompt(text: str) -> str:
    return f"{TR_SUMMARY_SYSTEM}\n\nARTICLE:\n{text.strip()}\n\nTURKISH SUMMARY:"


# --- Ollama / OpenAI cagrilari ---

def _ollama_generate(prompt: str, model: str = None,
                     base_url: str = None, options: Optional[Dict[str, Any]] = None,
                     timeout: int = None) -> Tuple[Optional[str], Optional[str]]:
    """Ollama /api/generate cagrisi. (text, error) dondurur."""
    url = (base_url or DEFAULT_OLLAMA_URL).rstrip("/") + "/api/generate"
    body = {
        "model": model or DEFAULT_OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": DEFAULT_OLLAMA_KEEP_ALIVE,
        "options": options or {"temperature": 0.2, "top_p": 0.9, "num_ctx": 8192},
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or DEFAULT_OLLAMA_TIMEOUT) as resp:
            j = json.loads(resp.read().decode("utf-8", errors="replace"))
        return (j.get("response") or "").strip(), None
    except urllib.error.URLError as e:
        return None, f"Ollama erisilemiyor: {e}"
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def _openai_chat(prompt: str, model: str = "gpt-4o-mini",
                  api_key: Optional[str] = None, timeout: int = 60) -> Tuple[Optional[str], Optional[str]]:
    """OpenAI Chat Completions. (text, error)."""
    key = api_key or os.environ.get("OPENAI_API_KEY")
    if not key:
        return None, "OPENAI_API_KEY tanimli degil"
    url = "https://api.openai.com/v1/chat/completions"
    body = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.2,
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
            "User-Agent": USER_AGENT,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            j = json.loads(resp.read().decode("utf-8", errors="replace"))
        text = j["choices"][0]["message"]["content"]
        return text.strip(), None
    except urllib.error.HTTPError as e:
        return None, f"OpenAI HTTP {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return None, f"OpenAI baglanti hatasi: {e}"
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def translate_smart(text: str, prefer: str = "ollama",
                     ollama_model: Optional[str] = None,
                     openai_model: str = "gpt-4o-mini") -> TranslationResult:
    """Otomatik en iyi metodu sec.

    prefer:
        'ollama'      -> once Ollama, sonra OpenAI, sonra prompt-only
        'openai'      -> once OpenAI, sonra Ollama, sonra prompt-only
        'prompt_only' -> hicbir cagri yapma, sadece prompt'u dondur
    """
    chain: List[str] = []
    prompt = build_translation_prompt(text, target_lang="tr")
    text_in = text or ""

    def _try_ollama():
        chain.append("ollama:" + (ollama_model or DEFAULT_OLLAMA_MODEL))
        out, err = _ollama_generate(prompt, model=ollama_model)
        if out:
            return TranslationResult(
                source_text=text_in, translated_text=out,
                method="ollama", model=ollama_model or DEFAULT_OLLAMA_MODEL,
                fallback_chain=list(chain),
            )
        return err or "ollama empty"

    def _try_openai():
        chain.append("openai:" + openai_model)
        out, err = _openai_chat(prompt, model=openai_model)
        if out:
            return TranslationResult(
                source_text=text_in, translated_text=out,
                method="openai", model=openai_model,
                fallback_chain=list(chain),
            )
        return err or "openai empty"

    def _prompt_only(last_err: Optional[str] = None):
        chain.append("prompt_only")
        return TranslationResult(
            source_text=text_in, translated_text="",
            method="prompt_only", model="-",
            fallback_chain=list(chain),
            error=last_err,
        )

    last_err: Optional[str] = None
    if prefer == "openai":
        res = _try_openai()
        if isinstance(res, TranslationResult):
            return res
        last_err = res
        res = _try_ollama()
        if isinstance(res, TranslationResult):
            return res
        last_err = res
    elif prefer == "prompt_only":
        return _prompt_only()
    else:  # ollama
        res = _try_ollama()
        if isinstance(res, TranslationResult):
            return res
        last_err = res
        res = _try_openai()
        if isinstance(res, TranslationResult):
            return res
        last_err = res

    return _prompt_only(last_err)


def summarize_smart(text: str, prefer: str = "ollama",
                     ollama_model: Optional[str] = None) -> TranslationResult:
    """Ozet (Turkce). Ayni fallback zinciri."""
    prompt = build_summary_prompt(text)
    chain: List[str] = []

    def _ollama():
        chain.append("ollama:" + (ollama_model or DEFAULT_OLLAMA_MODEL))
        out, err = _ollama_generate(prompt, model=ollama_model)
        if out:
            return TranslationResult(
                source_text=text, translated_text=out,
                method="ollama-summary", model=ollama_model or DEFAULT_OLLAMA_MODEL,
                fallback_chain=list(chain),
            )
        return err

    def _openai():
        chain.append("openai:gpt-4o-mini")
        out, err = _openai_chat(prompt, model="gpt-4o-mini")
        if out:
            return TranslationResult(
                source_text=text, translated_text=out,
                method="openai-summary", model="gpt-4o-mini",
                fallback_chain=list(chain),
            )
        return err

    if prefer == "openai":
        r = _openai();  r2 = _ollama() if not isinstance(r, TranslationResult) else None
    else:
        r = _ollama();  r2 = _openai() if not isinstance(r, TranslationResult) else None
    if isinstance(r, TranslationResult):
        return r
    if isinstance(r2, TranslationResult):
        return r2
    return TranslationResult(
        source_text=text, translated_text="", method="prompt_only",
        model="-", fallback_chain=list(chain), error=str(r),
    )


def _auto_index_to_rag(article: PubMedArticle, tr_summary: str = "") -> bool:
    """D700 2026-05-17: Cevirilen makaleyi otomatik RAG'a ekle.
    Sessiz sessiz; RAG yoksa False doner."""
    try:
        import yazklinik_rag as _rag
        title = article.title or f"PubMed {article.pmid}"
        text = f"[PubMed {article.pmid}] {title}\n\nAbstract: {article.abstract}"
        if tr_summary:
            text += f"\n\nTR ozet:\n{tr_summary}"
        meta = {
            "kind": "research",
            "source": "pubmed",
            "pmid": article.pmid,
            "year": article.year,
            "journal": article.journal,
            "doi": article.doi or "",
            "query": "(auto-indexed from ceviri)",
        }
        ok = _rag.index_document(f"pubmed_{article.pmid}", text, meta)
        if ok:
            try: print(f"[CEVIRI] PubMed {article.pmid} RAG'a indekslendi", flush=True)
            except Exception: pass
        return bool(ok)
    except Exception as exc:
        try: print(f"[CEVIRI] RAG auto-index skip: {exc}", flush=True)
        except Exception: pass
        return False


def translate_pubmed_article(pmid: str, prefer: str = "ollama",
                              include_summary: bool = True,
                              auto_index_rag: bool = True) -> FullArticleResult:
    """PubMed makale + baslik + abstract ceviri (+ opsiyonel ozet).
    auto_index_rag=True ise sonuc RAG'a yazilir (Alex sonraki sorgularda bulur).
    """
    article = fetch_pubmed_pmid(pmid)
    out = FullArticleResult(article=article)

    if article.title:
        t = translate_smart(article.title, prefer=prefer)
        out.title_tr = t.translated_text
        out.method = t.method
        out.fallback_chain += t.fallback_chain
        if t.error:
            out.error = t.error

    if article.abstract:
        a = translate_smart(article.abstract, prefer=prefer)
        out.abstract_tr = a.translated_text
        out.fallback_chain += a.fallback_chain
        if a.error and not out.error:
            out.error = a.error

        if include_summary and a.translated_text:
            s = summarize_smart(article.abstract, prefer=prefer)
            out.summary_tr = s.translated_text
            out.fallback_chain += s.fallback_chain

    # Auto-index to RAG (Alex sonraki sorgularda bulur)
    if auto_index_rag and article.abstract:
        _auto_index_to_rag(article, tr_summary=out.summary_tr)

    return out


# --- Export bicimleri ---

def format_as_markdown(full: FullArticleResult) -> str:
    a = full.article
    parts = []
    parts.append(f"# {a.title or '(baslik yok)'}")
    if full.title_tr:
        parts.append(f"## TR: {full.title_tr}")
    meta = []
    if a.authors:
        meta.append(", ".join(a.authors[:6]) + (" et al." if len(a.authors) > 6 else ""))
    if a.journal:
        meta.append(a.journal)
    if a.year:
        meta.append(a.year)
    if meta:
        parts.append("*" + " Â· ".join(meta) + "*")
    if a.doi:
        parts.append(f"DOI: [{a.doi}](https://doi.org/{a.doi})")
    if a.pubmed_url:
        parts.append(f"PubMed: <{a.pubmed_url}>")
    parts.append("\n## English Abstract\n")
    parts.append(a.abstract or "(abstract bos)")
    if full.abstract_tr:
        parts.append("\n## Turkce Ceviri\n")
        parts.append(full.abstract_tr)
    if full.summary_tr:
        parts.append("\n## Turkce Ozet (3-5 madde)\n")
        parts.append(full.summary_tr)
    return "\n".join(parts).strip() + "\n"


# --- Saglik kontrolu ---

def health_check() -> Dict[str, Any]:
    """Hangi metodlar erisilebilir hizlica kontrol et."""
    out: Dict[str, Any] = {
        "ok": True,
        "ollama_url": DEFAULT_OLLAMA_URL,
        "ollama_model": DEFAULT_OLLAMA_MODEL,
        "ollama_available": False,
        "openai_available": bool(os.environ.get("OPENAI_API_KEY")),
        "pubmed_reachable": False,
        "agent_version": AGENT_VERSION,
    }
    # Ollama tags endpoint - hizli prob
    try:
        req = urllib.request.Request(
            DEFAULT_OLLAMA_URL.rstrip("/") + "/api/tags",
            headers={"User-Agent": USER_AGENT},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            j = json.loads(resp.read().decode("utf-8", errors="replace"))
        out["ollama_available"] = True
        out["ollama_models"] = [m.get("name") for m in (j.get("models") or [])][:10]
    except Exception as e:  # noqa: BLE001
        out["ollama_error"] = str(e)

    # PubMed hizli prob
    try:
        _http_get(f"{NCBI_BASE}/einfo.fcgi?db=pubmed&retmode=json", timeout=4)
        out["pubmed_reachable"] = True
    except Exception as e:  # noqa: BLE001
        out["pubmed_error"] = str(e)

    return out


if __name__ == "__main__":
    import sys
    print("HEALTH:", json.dumps(health_check(), ensure_ascii=False, indent=2))
    if len(sys.argv) > 1:
        if sys.argv[1].isdigit():
            print("\nPubMed fetch test...")
            a = fetch_pubmed_pmid(sys.argv[1])
            print(f"  Title: {a.title[:80]}")
            print(f"  Year: {a.year} | Journal: {a.journal} | Authors: {len(a.authors)}")
            print(f"  Abstract: {len(a.abstract)} char")
        else:
            print(f"\nPubMed search test for: {sys.argv[1]}")
            r = search_pubmed(sys.argv[1], max_results=5)
            for h in r.get("hits", []):
                print(f"  {h['pmid']} {h['year']} | {h['title'][:60]}")
    else:
        print("\nUsage: python yazklinik_ceviri_agent.py <pmid|query>")

