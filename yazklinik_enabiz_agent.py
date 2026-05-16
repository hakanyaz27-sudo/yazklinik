"""e-Nabiz Belge Aktarim Ajani.

Resmi e-Nabiz REST/OAuth API'si ucuncu parti yazilimlara acik degildir.
Tek doktor muayenehanesi icin pratik ve KVKK uyumlu yol:
    Hasta e-Nabiz mobil uygulamasindan PDF/rapor indirir.
    Doktor PDF'i bu sayfaya yukler.
    Yazilim Fitz + yazklinik_pdf_patient_extract ile yapilandirir.
    Doktor onayindan sonra ilgili hasta dosyasina yazilir.

Bu modul stdlib + 'fitz' (PyMuPDF) kullanir; web layer'a yardimci helper'lar saglar.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple


SOURCE_LABEL = "e-Nabiz PDF (hasta paylasimi)"
AGENT_VERSION = "2026.05.01-enabiz"


def _fold(value: Any) -> str:
    text = str(value or "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("ı", "i").replace("İ", "I")
    return text.casefold()


def _digits_only(value: Any) -> str:
    return re.sub(r"\D", "", str(value or ""))


def detect_enabiz_signature(text: str) -> Dict[str, Any]:
    """Heuristic: belge gercekten e-Nabiz/SBYS PDF'i mi?
    UI'a 'e-Nabiz tespit edildi' rozeti gostermek icin kullanilir.
    """
    if not text:
        return {"is_enabiz": False, "matches": []}
    folded = _fold(text)
    keywords = (
        "e-nabiz", "enabiz", "saglik bakanligi", "saglik.gov.tr",
        "saglik bilgi sistemi", "uss", "merkezi saglik",
        "ulusal saglik", "ckys", "medula", "sbys",
        "kisisel saglik kaydi", "rapor paylasim",
        "adi soyadi", "tahlil", "sonuc birimi", "referans degeri",
    )
    hits = sorted({k for k in keywords if k in folded})
    return {"is_enabiz": bool(hits), "matches": hits}


def score_patient_match(
    patient_row: Dict[str, Any],
    extracted: Dict[str, Any],
) -> Tuple[float, List[str]]:
    """0..1 arasi puan + neden listesi. Yuksek esik 0.85, orta 0.6."""
    if not isinstance(patient_row, dict) or not isinstance(extracted, dict):
        return 0.0, []
    score = 0.0
    reasons: List[str] = []

    # TC kimlik birebir
    pdf_tc = _digits_only(extracted.get("tc_no"))
    row_name_lower = _fold(patient_row.get("display_name") or "")
    row_folder = str(patient_row.get("folder_key") or "")
    if pdf_tc and len(pdf_tc) >= 10:
        if pdf_tc in row_folder or pdf_tc in row_name_lower:
            score += 0.7
            reasons.append("TC eslesti")

    # Telefon birebir
    pdf_phone = _digits_only(extracted.get("phone"))
    if pdf_phone and len(pdf_phone) >= 10:
        haystack = row_folder + " " + (patient_row.get("phone") or "")
        if pdf_phone[-10:] in haystack:
            score += 0.4
            reasons.append("Telefon eslesti")

    # Ad/soyad
    pdf_name = _fold(extracted.get("patient_name") or "")
    if pdf_name and row_name_lower:
        tokens_pdf = [t for t in re.split(r"[\s.]+", pdf_name) if len(t) >= 3]
        tokens_row = [t for t in re.split(r"[\s.]+", row_name_lower) if len(t) >= 3]
        if tokens_pdf and tokens_row:
            common = set(tokens_pdf) & set(tokens_row)
            if len(common) >= 2:
                score += 0.5
                reasons.append("Ad-soyad cogu eslesti")
            elif len(common) == 1:
                score += 0.25
                reasons.append("Ad veya soyad eslesti")

    # Dogum tarihi
    pdf_birth = str(extracted.get("birth_date") or "").strip()
    if pdf_birth and patient_row.get("birth_date"):
        if pdf_birth == str(patient_row.get("birth_date") or "").strip():
            score += 0.2
            reasons.append("Dogum tarihi eslesti")

    return min(1.0, score), reasons


def confidence_label(score: float) -> str:
    if score >= 0.85:
        return "yuksek"
    if score >= 0.6:
        return "orta"
    if score >= 0.35:
        return "dusuk"
    return "yok"


def build_candidate_payload(
    pdf_payload: Dict[str, Any],
    pdf_name: str,
    file_size: int,
    elapsed_ms: int,
    text_signature: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """yazklinik_pdf_patient_extract.extract_patient_pdf_payload sonucunu
    e-Nabiz UI'sinin bekledigi forma cevirir."""
    payload = pdf_payload or {}
    demo = dict(payload.get("demographics") or {})
    fetal = dict(payload.get("fetal") or {})
    labs = list(payload.get("labs") or [])
    diagnoses = list(payload.get("diagnoses") or [])
    notes = list(payload.get("notes") or [])
    pdfs = list(payload.get("pdfs") or [])
    summary = list(payload.get("summary_lines") or [])
    return {
        "ok": bool(payload.get("ok")),
        "agent_version": AGENT_VERSION,
        "source": SOURCE_LABEL,
        "file": {
            "name": pdf_name or "",
            "size_bytes": int(file_size or 0),
            "elapsed_ms": int(elapsed_ms or 0),
        },
        "signature": text_signature or {"is_enabiz": False, "matches": []},
        "demographics": demo,
        "fetal": fetal,
        "labs": labs[:120],
        "diagnoses": diagnoses[:60],
        "notes": notes[:60],
        "pdfs": pdfs,
        "summary_lines": summary,
        "extracted_at": datetime.now().isoformat(timespec="seconds"),
    }


def filter_demographics(
    candidate_demo: Dict[str, Any],
    selected_fields: Iterable[str],
) -> Dict[str, Any]:
    """Sadece doktorun isaretledigi alanlari dondur (snake_case key listesi)."""
    selected = {str(k or "").strip() for k in selected_fields if k}
    return {
        k: v for k, v in (candidate_demo or {}).items()
        if k in selected and v not in (None, "")
    }


# =====================================================================
# tahlil / ilac / tani / randevu cikaricilar
# e-Nabiz PDF iceriginin tipik bolumlerini siniflandirir.
# =====================================================================

import re as _re_e

_TAHLIL_KEYS = (
    "hb", "hgb", "hemoglobin", "hct", "wbc", "plt", "tsh", "ft4", "ft3",
    "glukoz", "glucose", "hba1c", "ast", "alt", "kreatinin", "creatinine",
    "ure", "urea", "ferritin", "vitamin d", "b12", "beta hcg", "afp",
    "estradiol", "lh", "fsh", "prolaktin", "kolesterol", "trigliserid",
    "ldl", "hdl", "albumin", "tsh-r", "crp", "sedim", "ggt", "alp",
    "bilirubin", "kreatin", "magnezyum", "kalsiyum", "fosfor", "demir",
    "transferrin", "psa",
)

_ILAC_KEYS = (
    "ilac", "ilaç", "rec", "reçete", "recete", "medication", "medications",
    "rx", "ilaç", "kullandigi ilac",
)

_RANDEVU_KEYS = (
    "randevu", "appointment", "kontrol", "follow up",
)


def _e_clean(value: Any, limit: int = 200) -> str:
    text = _re_e.sub(r"\s+", " ", str(value or "").strip())
    return text.strip(" :;-|\t\r\n")[:limit].strip()


def _e_parse_date(text: str) -> str:
    text = str(text or "")
    m = _re_e.search(r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})", text)
    if not m:
        m = _re_e.search(r"(\d{4}[./-]\d{1,2}[./-]\d{1,2})", text)
    return _e_clean(m.group(1)) if m else ""


_TAHLIL_BIRIM_PAT = (
    r"(?:mg/dL|mg/dl|g/dL|g/dl|mmol/L|mmol/l|mmol|"
    r"mIU/mL|mIU/L|uIU/mL|µIU/mL|IU/L|IU/mL|U/L|U/mL|"
    r"ng/mL|ng/dL|pg/mL|mEq/L|"
    r"%|mm/h|mm/hr|fL|pg|"
    r"10\^[36912]/uL|10\^[36912]/mL|/uL|/mm3|"
    r"mg|g|kg|ml|dl|l)"
)


def _parse_enabiz_vertical_tahlil_table(
    text: str,
    source: str = "",
    limit: int = 180,
) -> List[Dict[str, Any]]:
    """Parse e-Nabiz lab PDFs where table columns are emitted as lines.

    Typical text order is:
      date, test name, value, unit, reference, date, test name...
    Some child rows use '-' instead of repeating the date.
    """
    if not text:
        return []

    def clean_line(value: Any) -> str:
        raw = _re_e.sub(r"\s+", " ", str(value or "").strip())
        if raw == "-":
            return "-"
        return raw.strip(" :;|\t\r\n")[:220].strip()

    raw_lines = [clean_line(x) for x in str(text).splitlines()]
    lines = [x for x in raw_lines if x]
    headers = {
        "tarih", "tahlil", "sonuc", "sonuc birimi", "referans degeri",
        "referans değeri",
    }

    def is_header(line: str) -> bool:
        return _fold(line) in {_fold(x) for x in headers}

    def is_date(line: str) -> bool:
        return bool(_re_e.fullmatch(r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}", line))

    def is_marker(line: str) -> bool:
        return line == "-" or is_date(line)

    text_results = {
        "negatif", "pozitif", "normal", "numune reddedildi", "red",
        "eser", "yok", "var", "reaktif", "nonreaktif", "non reaktif",
        "neg", "poz",
    }

    def is_result(line: str) -> bool:
        folded = _fold(line).strip()
        if line == "-":
            return True
        if folded in text_results:
            return True
        return bool(_re_e.fullmatch(
            r"[<>]?\s*-?\d+(?:[.,]\d+)?(?:\s*[+-])?", line))

    def is_reference(line: str) -> bool:
        folded = _fold(line)
        if is_header(line) or is_marker(line):
            return False
        if any(k in folded for k in ("karar siniri", "risk", "gfh", "hasar")):
            return True
        return bool(_re_e.search(
            r"([<>]=?\s*)?\d+(?:[.,]\d+)?\s*[-–]\s*([<>]=?\s*)?\d+(?:[.,]\d+)?",
            line))

    def is_unit(line: str) -> bool:
        if is_header(line) or is_marker(line) or is_result(line):
            return False
        if is_reference(line):
            return False
        if len(line) > 32:
            return False
        if any(ch in line for ch in ("/", "%", "*", "^")):
            return True
        folded = _fold(line)
        unit_tokens = (
            "mg", "dl", "ul", "ml", "iu", "u/l", "g/l", "ng",
            "pg", "fl", "hpf", "mmol", "dk", "l",
        )
        return any(tok in folded for tok in unit_tokens)

    def next_starts_record(idx: int) -> bool:
        if idx >= len(lines):
            return True
        line = lines[idx]
        if is_header(line):
            return True
        if is_reference(line):
            return False
        if is_marker(line):
            return True
        if idx + 1 < len(lines) and lines[idx + 1] != "-" and is_result(lines[idx + 1]):
            return True
        if (idx + 2 < len(lines) and not is_result(line)
                and lines[idx + 2] != "-" and is_result(lines[idx + 2])):
            return True
        return False

    out: List[Dict[str, Any]] = []
    seen = set()
    i = 0
    current_date = ""
    while i < len(lines) and len(out) < limit:
        if is_header(lines[i]):
            i += 1
            continue
        entry_date = current_date
        if is_date(lines[i]):
            current_date = lines[i]
            entry_date = current_date
            i += 1
        elif lines[i] == "-":
            i += 1
        elif not current_date:
            i += 1
            continue

        while i < len(lines) and is_header(lines[i]):
            i += 1
        if i >= len(lines):
            break

        name_parts: List[str] = []
        result = ""
        start_i = i
        while i < len(lines):
            line = lines[i]
            if is_header(line):
                i += 1
                continue
            if is_marker(line) and not name_parts:
                break
            if name_parts and is_marker(line) and not is_result(line):
                break
            if name_parts and is_result(line):
                result = line
                i += 1
                break
            if is_result(line) and not name_parts:
                i += 1
                continue
            name_parts.append(line)
            i += 1
            if len(name_parts) >= 4:
                # If four lines did not lead to a value, this is likely a
                # wrapped reference/comment block, not a test name.
                if i >= len(lines) or not is_result(lines[i]):
                    i = start_i + 1
                    result = ""
                    break
        if not name_parts or not result:
            if i <= start_i:
                i = start_i + 1
            continue

        name = _e_clean(" ".join(name_parts), limit=120)
        folded_name = _fold(name)
        if not name or folded_name in headers:
            continue

        # Group headers such as "Tam Kan Sayimi (Hemogram) -" are not a real
        # parameter; child rows follow immediately.
        if result == "-" and (
            "hemogram" in folded_name
            or "tetkiki" in folded_name
            or "sayimi" in folded_name
        ):
            continue

        unit = ""
        if i < len(lines) and is_unit(lines[i]):
            unit = lines[i]
            i += 1

        ref_parts: List[str] = []
        while i < len(lines) and not next_starts_record(i):
            if not is_header(lines[i]):
                ref_parts.append(lines[i])
            i += 1
            if len(ref_parts) >= 8:
                break
        ref = _e_clean(" ".join(ref_parts), limit=260)

        sig = (_fold(name), _fold(result), _fold(unit), entry_date)
        if sig in seen:
            continue
        seen.add(sig)
        out.append({
            "ad": name,
            "deger": result,
            "birim": unit,
            "referans": ref,
            "tarih": entry_date,
            "source": source,
        })
    return out[:limit]


def parse_tahlil(text: str, source: str = "") -> List[Dict[str, Any]]:
    """e-Nabiz PDF'inden tahlil satirlari yakala.
    'TestAdi  12.5  g/dL  [12.05.2026]' formati.
    """
    if not text:
        return []
    table_rows = _parse_enabiz_vertical_tahlil_table(text, source=source)
    if table_rows:
        return table_rows
    out: List[Dict[str, Any]] = []
    seen = set()
    # Once tarihi yakala (varsa), sonra deger+birim, sonra ad
    line_pat = _re_e.compile(
        r"^\s*"
        r"(?P<ad>[A-Za-zÇçĞğİıŞşÜüÖöÂâÎî][A-Za-zÇçĞğİıŞşÜüÖö0-9 \-_/\.\(\)]{1,40}?)"
        r"\s*[:=]?\s*"
        r"(?P<deger>-?\d+(?:[.,]\d+)?)"
        r"\s+"
        r"(?P<birim>" + _TAHLIL_BIRIM_PAT + r")"
        r"\s*"
        r"(?P<tarih>\d{1,2}[./-]\d{1,2}[./-]\d{2,4})?"
        r"\s*$",
        _re_e.MULTILINE,
    )
    folded_keys = {_fold(k) for k in _TAHLIL_KEYS}
    for line in str(text).splitlines():
        raw = line.strip()
        if not raw or len(raw) > 200:
            continue
        m = line_pat.match(raw)
        if not m:
            continue
        ad = _e_clean(m.group("ad"))
        deger = _e_clean(m.group("deger"))
        birim = _e_clean(m.group("birim"))
        tarih = _e_parse_date(m.group("tarih") or "")
        if not ad or len(ad) < 2:
            continue
        ad_lower = _fold(ad)
        # ad ilac listesindeki kelimeyle baslamiyor ve sozlukle eslemiyorsa
        # birim varligi gerekli
        in_dict = any(key in ad_lower for key in folded_keys)
        if not in_dict and not birim:
            continue
        sig = (_fold(ad), deger, _fold(birim), tarih)
        if sig in seen:
            continue
        seen.add(sig)
        out.append({
            "ad": ad,
            "deger": deger,
            "birim": birim,
            "tarih": tarih,
            "source": source,
        })
        if len(out) >= 80:
            break
    return out


_FORM_KEYWORDS = (
    "tablet", "tab", "kapsul", "kapsül", "kaps",
    "surup", "şurup", "draje", "krem", "ampul",
    "merhem", "damla", "sprey", "supozituar", "fitil",
    "film", "flakon", "kuru toz", "ovul", "supp",
)


def parse_ilac(text: str, source: str = "") -> List[Dict[str, Any]]:
    """e-Recete/ilac satirlari yakala. Form kelimesi (TABLET, KAPSUL...) veya ATC zorunlu."""
    if not text:
        return []
    out: List[Dict[str, Any]] = []
    seen = set()
    drug_pat = _re_e.compile(
        r"^\s*(?P<ad>[A-ZÇĞİŞÜÖ][A-ZÇĞİŞÜÖa-zçğışüö\.\-\s]{2,55})"
        r"\s+(?P<doz>\d{1,4}(?:[.,]\d+)?\s?(?:mg|mcg|g|gr|gram|ml|iu|mg/ml|mg/g|µg))"
        r"\s+(?P<form>" + "|".join(_FORM_KEYWORDS) + r")\b"
        r"(?P<rest>[^\n]{0,100})",
        _re_e.MULTILINE | _re_e.IGNORECASE,
    )
    use_pat = _re_e.compile(
        r"(\d+\s*x\s*\d+|\bsabah\b|\baksam\b|akşam|gunde|günde|saatte|"
        r"gun\b|gün\b|aç karnına|tok karnına|"
        r"\d+\s*(?:doz|dose))",
        _re_e.IGNORECASE)
    atc_pat = _re_e.compile(r"\b([A-Z]\d{2}[A-Z]{2}\d{2})\b")
    for line in str(text).splitlines():
        raw = line.strip()
        if not raw or len(raw) > 220:
            continue
        m = drug_pat.match(raw)
        if not m:
            continue
        ad = _e_clean(m.group("ad"))
        if len(ad) < 4 or len(ad) > 60:
            continue
        # Whitelist: tum buyuk harf ile baslayan ve form keyword bulunan satirlar
        if ad.upper() == ad and len(ad) <= 5:
            continue
        doz_full = f"{_e_clean(m.group('doz'))} {_e_clean(m.group('form'))}".strip()
        rest = m.group("rest") or ""
        kullanim = ""
        u = use_pat.search(rest)
        if u:
            kullanim = _e_clean(u.group(0))
        atc_match = atc_pat.search(raw)
        atc = atc_match.group(1) if atc_match else ""
        sig = (_fold(ad), doz_full, kullanim)
        if sig in seen:
            continue
        seen.add(sig)
        out.append({
            "ad": ad,
            "doz": doz_full,
            "kullanim": kullanim,
            "atc": atc,
            "source": source,
        })
        if len(out) >= 50:
            break
    return out


def parse_tani(text: str, source: str = "") -> List[Dict[str, Any]]:
    """ICD-10 kodlu tani satirlari + tani anahtar kelimeli satirlar.
    ICD-10 patterni: harf + 2 rakam + nokta + 1-2 rakam (zorunlu nokta).
    Bu sayede 'B12 SURUP' gibi ilac adlari tanı olarak yakalanmaz.
    """
    if not text:
        return []
    out: List[Dict[str, Any]] = []
    seen = set()
    # Yalin ICD pattern: nokta ZORUNLU. 'A09.1', 'O24.4' kabul; 'B12' kabul DEGIL.
    icd_pat = _re_e.compile(
        r"\b([A-Z]\d{2}\.\d{1,3})\b\s*[-:]?\s*([^\n]{2,120})")
    # Form/ilac kelimesi varsa satir ilaca aittir, atla
    form_blacklist = tuple(_fold(k) for k in _FORM_KEYWORDS)
    diagnosis_keys = ("tani", "diagnosis", "icd", "tanı", "tıbbi durum")
    folded = _fold(text)
    for line in str(text).splitlines():
        raw = line.strip()
        if not raw or len(raw) > 220:
            continue
        line_fold = _fold(raw)
        if any(b in line_fold for b in form_blacklist):
            continue
        m = icd_pat.search(raw)
        if not m:
            continue
        kod = _e_clean(m.group(1))
        ad = _e_clean(m.group(2))
        if not ad or len(ad) > 130:
            continue
        sig = (kod, _fold(ad))
        if sig in seen:
            continue
        seen.add(sig)
        out.append({"kod": kod, "ad": ad, "source": source})
        if len(out) >= 30:
            break
    if not out and any(k in folded for k in (_fold(x) for x in diagnosis_keys)):
        for line in str(text).splitlines():
            raw = line.strip()
            if not raw or len(raw) > 200:
                continue
            l = _fold(raw)
            if any(b in l for b in form_blacklist):
                continue
            if any(k in l for k in (_fold(x) for x in diagnosis_keys)):
                ad = _e_clean(_re_e.sub(
                    r"^[^:\-]*[:\-]\s*", "", raw))
                if len(ad) >= 4:
                    sig = ("", _fold(ad))
                    if sig in seen:
                        continue
                    seen.add(sig)
                    out.append({"kod": "", "ad": ad, "source": source})
                    if len(out) >= 30:
                        break
    return out


def parse_randevu(text: str, source: str = "") -> List[Dict[str, Any]]:
    """Sadece 'Randevu/Kontrol/Appointment' anahtar kelimesini iceren satirlardan yakala."""
    if not text:
        return []
    out: List[Dict[str, Any]] = []
    seen = set()
    keys_folded = tuple(_fold(k) for k in _RANDEVU_KEYS)
    date_pat = _re_e.compile(
        r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})(?:\s+(\d{1,2}:\d{2}))?"
        r"\s*[-,|]?\s*([^\n]{0,150})")
    for line in str(text).splitlines():
        raw = line.strip()
        if not raw or len(raw) > 250:
            continue
        line_fold = _fold(raw)
        if not any(k in line_fold for k in keys_folded):
            continue
        # anahtar kelime sonrasi tarih ara
        tail_idx = max(line_fold.find(k) for k in keys_folded if k in line_fold)
        tail = raw[tail_idx:]
        m = date_pat.search(tail)
        if not m:
            continue
        tarih = _e_parse_date(m.group(1) or "")
        saat = _e_clean(m.group(2) or "")
        ctx = _e_clean(m.group(3) or "")
        if not tarih:
            continue
        kurum = ""
        bolum = ""
        ck = _fold(ctx)
        if any(t in ck for t in ("hastane", "klinik", "saglik", "tip merkezi", "asm", "ase")):
            parts = _re_e.split(r"[,/|]", ctx, maxsplit=1)
            kurum = _e_clean(parts[0])
            if len(parts) > 1:
                bolum = _e_clean(parts[1])
        else:
            kurum = ctx
        sig = (tarih, saat, _fold(kurum))
        if sig in seen:
            continue
        seen.add(sig)
        out.append({
            "tarih": tarih,
            "saat": saat,
            "kurum": kurum,
            "bolum": bolum,
            "source": source,
        })
        if len(out) >= 20:
            break
    return out


def extract_enabiz_records(text: str, source: str = "e-Nabiz PDF") -> Dict[str, List[Dict[str, Any]]]:
    """Tek seferde tahlil/ilac/tani/randevu cikar."""
    return {
        "tahlil": parse_tahlil(text, source=source),
        "ilac": parse_ilac(text, source=source),
        "tani": parse_tani(text, source=source),
        "randevu": parse_randevu(text, source=source),
    }


def filter_records_by_selection(
    aday: Dict[str, List[Dict[str, Any]]],
    selection: Dict[str, List[int]],
) -> Dict[str, List[Dict[str, Any]]]:
    """selection: {tip: [index, ...]} -> sadece secili kayitlari dondur."""
    out: Dict[str, List[Dict[str, Any]]] = {}
    for tip in ("tahlil", "ilac", "tani", "randevu"):
        kayitlar = list(aday.get(tip) or [])
        chosen = selection.get(tip)
        if chosen is None:
            out[tip] = kayitlar
            continue
        out[tip] = [
            kayitlar[i] for i in chosen
            if isinstance(i, int) and 0 <= i < len(kayitlar)
        ]
    return out


def kayit_ozet(tip: str, k: Dict[str, Any]) -> str:
    """Audit log + UI ozeti."""
    if not isinstance(k, dict):
        return str(k or "")
    if tip == "tahlil":
        return (
            f"{k.get('ad', '')}: {k.get('deger', '')} "
            f"{k.get('birim', '')}".strip()
            + (f" - {k.get('tarih')}" if k.get('tarih') else "")
        ).strip()
    if tip == "ilac":
        bits = [k.get("ad", ""), k.get("doz", "")]
        if k.get("kullanim"):
            bits.append(f"({k.get('kullanim')})")
        return " ".join(b for b in bits if b).strip()
    if tip == "tani":
        kod = k.get("kod", "")
        ad = k.get("ad", "")
        return f"[{kod}] {ad}".strip("[] ").strip() if kod else ad
    if tip == "randevu":
        bits = [k.get("tarih", ""), k.get("saat", "")]
        kurum = k.get("kurum", "") or ""
        bolum = k.get("bolum", "") or ""
        right = " / ".join(p for p in (kurum, bolum) if p)
        if right:
            bits.append("- " + right)
        return " ".join(b for b in bits if b).strip()
    return str(k)
