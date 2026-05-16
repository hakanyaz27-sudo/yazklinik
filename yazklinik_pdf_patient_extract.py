"""PDF patient-data extraction helpers for YazKlinik.

This module is intentionally stdlib-only.  The web layer supplies PDF text
already extracted by PyMuPDF; this file turns that text into structured
patient-file data that can safely prefill the YazKlinik patient record.
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any, Iterable


def _fold(value: Any) -> str:
    text = str(value or "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.replace("ı", "i").replace("İ", "I")
    return text.casefold()


def _clean(value: Any, limit: int = 220) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    text = text.strip(" :;-|\t\r\n")
    return text[:limit].strip()


def _num(value: Any, low: float | None = None,
         high: float | None = None) -> float | None:
    raw = str(value or "").replace(",", ".")
    m = re.search(r"-?\d+(?:\.\d+)?", raw)
    if not m:
        return None
    try:
        val = float(m.group(0))
    except Exception:
        return None
    if low is not None and val < low:
        return None
    if high is not None and val > high:
        return None
    return round(val, 2)


def _int_num(value: Any, low: int | None = None,
             high: int | None = None) -> int | None:
    val = _num(value, low=low, high=high)
    if val is None:
        return None
    return int(round(val))


def _date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    m = re.search(
        r"(\d{1,2})[./-](\d{1,2})[./-](\d{4})|"
        r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})",
        raw)
    if not m:
        return ""
    try:
        if m.group(1):
            day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            year, month, day = int(m.group(4)), int(m.group(5)), int(m.group(6))
        dt = datetime(year, month, day)
        if 1900 <= dt.year <= 2100:
            return dt.strftime("%d.%m.%Y")
    except Exception:
        return ""
    return ""


def _iso_date(value: Any) -> str:
    ddmmyyyy = _date(value)
    if not ddmmyyyy:
        return ""
    try:
        return datetime.strptime(ddmmyyyy, "%d.%m.%Y").strftime("%Y-%m-%d")
    except Exception:
        return ""


def _age_from_birth(birth_date: str) -> int | None:
    try:
        born = datetime.strptime(birth_date, "%d.%m.%Y").date()
        today = datetime.now().date()
        age = today.year - born.year - (
            (today.month, today.day) < (born.month, born.day))
        return age if 1 < age <= 120 else None
    except Exception:
        return None


def _line_value(lines: list[str], labels: Iterable[str]) -> str:
    folded_labels = [_fold(label).strip() for label in labels]

    def label_index(fline: str, label: str) -> int:
        idx = fline.find(label)
        while idx >= 0:
            before = fline[idx - 1] if idx > 0 else " "
            end = idx + len(label)
            after = fline[end] if end < len(fline) else " "
            left_ok = (not before.isalnum()) or before in " \t\r\n:=-/("
            right_ok = (not after.isalnum()) or after in " \t\r\n:=-/)"
            if left_ok and right_ok:
                return idx
            idx = fline.find(label, idx + 1)
        return -1

    for line in lines:
        raw = _clean(line, limit=400)
        if not raw:
            continue
        fline = _fold(raw)
        for label in folded_labels:
            if not label:
                continue
            idx = label_index(fline, label)
            if idx < 0:
                continue
            if "\t" in raw:
                return _clean(raw.split("\t")[-1])
            suffix = raw[idx + len(label):]
            suffix = re.sub(r"^\s*[:=\-]?\s*", "", suffix)
            return _clean(suffix)
    return ""


def _flat_value(folded_text: str, patterns: Iterable[str]) -> str:
    for pattern in patterns:
        m = re.search(pattern, folded_text, re.IGNORECASE)
        if m:
            return _clean(m.group(1) if m.groups() else m.group(0))
    return ""


def _parse_blood(raw: str) -> tuple[str, str]:
    text = _fold(raw)
    m = re.search(
        r"\b(ab|a|b|0)\b(?:\s*rh)?\s*[\( ]*\s*"
        r"([+-]|pozitif|positive|negatif|negative)?",
        text)
    if not m:
        return "", ""
    blood = m.group(1).upper()
    rh_raw = m.group(2) or ""
    rh = ""
    if rh_raw in ("+", "pozitif", "positive"):
        rh = "positive"
    elif rh_raw in ("-", "negatif", "negative"):
        rh = "negative"
    return blood, rh


def _find_number_near(text: str, labels: Iterable[str],
                      low: float | None = None,
                      high: float | None = None) -> float | None:
    folded = _fold(text)
    for label in labels:
        label_fold = re.escape(_fold(label))
        patterns = (
            rf"{label_fold}\s*[:=]?\s*(\d{{1,5}}(?:[.,]\d+)?)",
            rf"{label_fold}\D{{0,24}}(\d{{1,5}}(?:[.,]\d+)?)",
        )
        for pattern in patterns:
            m = re.search(pattern, folded, re.IGNORECASE)
            if m:
                return _num(m.group(1), low=low, high=high)
    return None


def _line_has_any(line: str, words: Iterable[str]) -> bool:
    folded = _fold(line)
    return any(_fold(word) in folded for word in words)


def _number_after_label(line: str, labels: Iterable[str],
                        max_gap: int = 28) -> str:
    folded = _fold(line)
    for label in labels:
        label_fold = re.escape(_fold(label))
        patterns = (
            rf"(?:^|[^a-z0-9]){label_fold}\s*[:=\-]?\s*"
            rf"(\d{{1,4}}(?:[.,]\d+)?)(?!\s*[+]\s*\d)",
            rf"(?:^|[^a-z0-9]){label_fold}\D{{0,{max_gap}}}"
            rf"(\d{{1,4}}(?:[.,]\d+)?)(?!\s*[+]\s*\d)",
        )
        for pattern in patterns:
            m = re.search(pattern, folded, re.IGNORECASE)
            if m:
                return m.group(1)
    return ""


def _parse_patient_age(lines: list[str], folded_text: str) -> int | None:
    forbidden = (
        "gebelik", "gestasyon", "gestational", "ga", "aog", "usg",
        "ultrason", "fetal", "hafta", "hf", "week", "w+",
    )
    age_labels = (
        "hasta yasi", "hasta yas", "patient age", "age of patient",
        "yasi", "yas", "age",
    )
    for line in lines:
        if _line_has_any(line, forbidden):
            continue
        raw = _number_after_label(line, age_labels, max_gap=16)
        age = _int_num(raw, low=2, high=120)
        if age is not None:
            return age
    for pattern in (
        r"(?:hasta\s*yasi|patient\s*age|age\s*of\s*patient)\D{0,16}(\d{1,3})",
        r"(?:\byas\b|\bage\b)\D{0,10}(\d{1,3})(?!\s*[+]\s*\d)",
    ):
        m = re.search(pattern, folded_text, re.IGNORECASE)
        if not m:
            continue
        start = max(0, m.start() - 40)
        end = min(len(folded_text), m.end() + 40)
        if any(word in folded_text[start:end] for word in forbidden):
            continue
        age = _int_num(m.group(1), low=2, high=120)
        if age is not None:
            return age
    return None


def _height_cm(value: Any) -> float | None:
    raw = str(value or "").replace(",", ".")
    m = re.search(r"\d+(?:\.\d+)?", raw)
    if not m:
        return None
    try:
        val = float(m.group(0))
    except Exception:
        return None
    folded = _fold(raw)
    if 1.0 <= val <= 2.3 and ("m" in folded or val < 3):
        val *= 100.0
    if 90 <= val <= 230:
        return round(val, 1)
    return None


def _parse_metric_value(lines: list[str], labels: Iterable[str],
                        low: float, high: float,
                        forbidden: Iterable[str] = (),
                        height: bool = False) -> float | None:
    for line in lines:
        if forbidden and _line_has_any(line, forbidden):
            continue
        raw = _number_after_label(line, labels, max_gap=30)
        if not raw:
            continue
        parsed = _height_cm(raw) if height else _num(raw, low=low, high=high)
        if parsed is not None:
            return parsed
    return None


def _parse_gpal_values(lines: list[str], folded_text: str) -> dict[str, int]:
    out: dict[str, int] = {}

    def put(key: str, raw: Any):
        if key in out:
            return
        val = _int_num(raw, low=0, high=30)
        if val is not None:
            out[key] = val

    combo_patterns = (
        r"\bgpal\b\D{0,12}(\d{1,2})\D+(\d{1,2})\D+(\d{1,2})\D+(\d{1,2})",
        r"\bgpa\b\D{0,12}(\d{1,2})\D+(\d{1,2})\D+(\d{1,2})",
        r"\bg\s*[:=]?\s*(\d{1,2})\D{0,12}p\s*[:=]?\s*(\d{1,2})\D{0,12}a\s*[:=]?\s*(\d{1,2})(?:\D{0,12}l\s*[:=]?\s*(\d{1,2}))?",
        r"\bgravida\b\D{0,12}(\d{1,2})\D{0,20}\bpara\b\D{0,12}(\d{1,2})\D{0,20}\babort\w*\b\D{0,12}(\d{1,2})(?:\D{0,20}(?:living|yasayan|canli)\b\D{0,12}(\d{1,2}))?",
    )
    for pattern in combo_patterns:
        m = re.search(pattern, folded_text, re.IGNORECASE)
        if not m:
            continue
        keys = ("gravida", "para", "abortus", "living")
        for idx, key in enumerate(keys, start=1):
            if idx <= len(m.groups()) and m.group(idx) not in (None, ""):
                put(key, m.group(idx))
        if out:
            break

    specs = (
        ("gravida", ("gravida", "gravidite", "gebelik sayisi", "g")),
        ("para", ("para", "parite", "dogum sayisi", "p")),
        ("abortus", ("abortus", "abort", "dusuk", "kuretaj", "a")),
        ("living", ("living", "yasayan", "canli", "yasayan cocuk", "l")),
    )
    forbidden = ("hafta", "hf", "gebelik haftasi", "efw", "bpd", "hc", "ac", "fl")
    for line in lines:
        folded = _fold(line)
        if any(word in folded for word in forbidden):
            continue
        for key, labels in specs:
            if key in out:
                continue
            raw = _number_after_label(line, labels, max_gap=18)
            put(key, raw)
    return out


def _parse_ga(text: str) -> tuple[int | None, int | None]:
    folded = _fold(text)
    patterns = (
        r"(?:ga|aog|gebelik\s*hafta\w*|gebelik\s*yas\w*|gestasyonel\s*yas\w*|gestational\s*age)\s*[:=]?\s*(\d{1,2})\s*(?:w|hf|hafta)?\s*[+ ]\s*(\d{1,2})",
        r"\b(\d{1,2})\s*w\s*(\d{1,2})\s*d\b",
        r"\b(\d{1,2})\s*hafta\s*(\d{1,2})\s*gun\b",
    )
    for pattern in patterns:
        m = re.search(pattern, folded, re.IGNORECASE)
        if not m:
            continue
        try:
            w, d = int(m.group(1)), int(m.group(2))
            if 3 <= w <= 43 and 0 <= d <= 6:
                return w, d
        except Exception:
            pass
    return None, None


def _parse_measurements(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    specs = {
        "bpd": (("bpd",), 5, 120),
        "hc": (("hc", "head circumference"), 20, 450),
        "ac": (("ac", "abdominal circumference"), 20, 450),
        "fl": (("fl", "femur length"), 3, 100),
        "crl": (("crl",), 1, 150),
        "nt": (("nt", "nuchal translucency", "ense saydamligi"), 0.3, 15),
        "efw": (("efw", "estimated fetal weight", "tahmini fetal agirlik"), 40, 6500),
        "afi": (("afi", "amniotic fluid index", "amniyon sivi indeksi"), 1, 45),
        "fhr": (("fhr", "fetal heart rate", "kalp atimi", "fetal nabiz"), 40, 240),
        "cervix_mm": (("cervix", "serviks", "cervical length"), 5, 80),
        "ua_pi": (("ua pi", "umbilikal arter pi", "umbilical artery pi"), 0.1, 5),
        "mca_pi": (("mca pi", "middle cerebral artery pi"), 0.1, 5),
        "mca_psv": (("mca psv", "middle cerebral artery psv"), 5, 150),
    }
    for key, (labels, low, high) in specs.items():
        val = _find_number_near(text, labels, low=low, high=high)
        if val is None:
            continue
        out[key] = int(round(val)) if key == "efw" else val

    folded = _fold(text)
    placenta_map = (
        ("previa", ("plasenta previa", "placenta previa")),
        ("low-lying", ("low lying placenta", "low-lying placenta", "alcak plasenta")),
        ("anterior", ("plasenta anterior", "anterior placenta")),
        ("posterior", ("plasenta posterior", "posterior placenta")),
        ("fundal", ("plasenta fundal", "fundal placenta")),
    )
    for label, keys in placenta_map:
        if any(k in folded for k in keys):
            out["placenta"] = label
            break

    pos_map = (
        ("cephalic", ("sefalik", "cephalic", "vertex", "bas asagi")),
        ("breech", ("breech", "makat")),
        ("transverse", ("transverse", "transvers", "enine")),
        ("oblique", ("oblique", "oblik")),
    )
    for label, keys in pos_map:
        if any(k in folded for k in keys):
            out["fetal_position"] = label
            break

    ga_w, ga_d = _parse_ga(text)
    if ga_w is not None:
        out["ga_weeks"] = ga_w
        out["ga_days"] = ga_d or 0
    return out


def _parse_labs(lines: list[str], source: str, limit: int = 40) -> list[dict[str, Any]]:
    lab_keywords = {
        "hb", "hgb", "hemoglobin", "wbc", "plt", "tsh", "ft4", "glukoz",
        "glucose", "hba1c", "ast", "alt", "creatinine", "kreatinin",
        "ferritin", "vitamin d", "b12", "beta hcg", "afp", "estradiol",
        "progesteron", "idrar", "protein", "crp",
    }
    rows: list[dict[str, Any]] = []
    for raw in lines:
        line = _clean(raw, limit=260)
        if not line:
            continue
        folded = _fold(line)
        if not any(k in folded for k in lab_keywords):
            continue
        m = re.search(r"([A-Za-z0-9 ._/%+-]{2,40})\s*[:=]?\s*(-?\d+(?:[.,]\d+)?)\s*([A-Za-z/%]+)?", line)
        if not m:
            continue
        name = _clean(m.group(1), limit=48)
        value = _clean(m.group(2), limit=24)
        unit = _clean(m.group(3) or "", limit=24)
        if not name or not value:
            continue
        rows.append({"name": name, "value": value, "unit": unit, "source": source})
        if len(rows) >= limit:
            break
    return rows


def _parse_diagnoses(lines: list[str], source: str, limit: int = 16) -> list[dict[str, str]]:
    labels = (
        "tani", "tani/endikasyon", "diagnosis", "endikasyon", "icd",
        "sonuc", "impression", "conclusion",
    )
    out: list[dict[str, str]] = []
    for line in lines:
        fline = _fold(line)
        if not any(label in fline for label in labels):
            continue
        value = _line_value([line], labels) or _clean(line, limit=260)
        value = value.strip()
        if len(value) < 3:
            continue
        if not any(item["text"] == value for item in out):
            out.append({"text": value, "source": source})
        if len(out) >= limit:
            break
    return out


def extract_patient_pdf_payload(pdf_items: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Extract a merged patient-file payload from already-read PDF texts.

    Newer PDFs should be passed first.  The merged demographics keep the newest
    PDF value, while each PDF record also carries its own extracted values so
    the web layer can write fetal measurements into the matching visit.
    """
    demographics: dict[str, Any] = {}
    sources: dict[str, str] = {}
    fetal: dict[str, Any] = {}
    fetal_sources: dict[str, str] = {}
    labs: list[dict[str, Any]] = []
    diagnoses: list[dict[str, str]] = []
    notes: list[dict[str, str]] = []
    pdfs: list[dict[str, Any]] = []

    def set_first(target: dict[str, Any], target_sources: dict[str, str],
                  key: str, value: Any, source: str):
        if value in (None, "") or target.get(key) not in (None, ""):
            return
        target[key] = value
        target_sources[key] = source

    for item in pdf_items:
        source = _clean(item.get("name") or item.get("source") or "PDF", limit=120)
        text = str(item.get("text") or "")
        if not text.strip():
            continue
        pdf_demo: dict[str, Any] = {}
        pdf_sources: dict[str, str] = {}
        pdf_fetal: dict[str, Any] = {}
        pdf_fetal_sources: dict[str, str] = {}
        pdf_labs: list[dict[str, Any]] = []
        pdf_diagnoses: list[dict[str, str]] = []
        pdf_notes: list[dict[str, str]] = []
        report_date_norm = ""

        def set_demo(key: str, value: Any, item_source: str = source):
            set_first(pdf_demo, pdf_sources, key, value, item_source)
            set_first(demographics, sources, key, value, item_source)

        def set_fetal(key: str, value: Any, item_source: str = source):
            set_first(pdf_fetal, pdf_fetal_sources, key, value, item_source)
            set_first(fetal, fetal_sources, key, value, item_source)

        lines = [_clean(line, limit=500) for line in text.splitlines()]
        lines = [line for line in lines if line]
        folded = _fold("\n".join(lines))
        pdf_record = {
            "name": source,
            "chars": len(text),
            "mtime": item.get("mtime") or 0,
            "path": str(item.get("path") or ""),
            "visit_key": str(item.get("visit_key") or ""),
            "visit_date": str(item.get("visit_date") or ""),
        }

        name = _line_value(lines, (
            "hasta adi soyadi", "hasta adi", "adi soyadi", "ad soyad",
            "patient name", "name surname", "name",
        ))
        if name and not re.search(r"\d", name) and len(name) >= 3:
            set_demo("patient_name", name, source)

        tc = _line_value(lines, (
            "tc kimlik no", "kimlik no", "tckn", "t.c.", "patient id",
            "protokol", "protocol",
        ))
        tc_digits = re.sub(r"\D", "", tc or "")
        if 8 <= len(tc_digits) <= 12:
            set_demo("tc_no", tc_digits, source)

        birth = _line_value(lines, (
            "dogum tarihi", "birth date", "date of birth", "dob",
        ))
        birth_date = _date(birth) or _date(_flat_value(folded, (
            r"(?:dogum\s*tarihi|birth\s*date|date\s*of\s*birth|dob)\D{0,20}(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
            r"(?:dogum\s*tarihi|birth\s*date|date\s*of\s*birth|dob)\D{0,20}(\d{4}[./-]\d{1,2}[./-]\d{1,2})",
        )))
        if birth_date:
            set_demo("birth_date", birth_date, source)
            age = _age_from_birth(birth_date)
            if age:
                set_demo("age", age, source)

        age = _parse_patient_age(lines, folded)
        if age is not None:
            set_demo("age", age, source)

        phone = _line_value(lines, ("telefon", "phone", "gsm", "cep"))
        phone_digits = re.sub(r"\D", "", phone or "")
        if len(phone_digits) >= 10:
            set_demo("phone", phone_digits[-11:] if phone_digits.startswith("90") else phone_digits, source)

        blood_raw = _line_value(lines, ("kan grubu", "blood group"))
        blood, rh = _parse_blood(blood_raw)
        if blood:
            set_demo("blood_type", blood, source)
        if rh:
            set_demo("rh_factor", rh, source)

        for key, parsed in _parse_gpal_values(lines, folded).items():
            set_demo(key, parsed, source)

        weight = _parse_metric_value(
            lines,
            ("kilo", "vucut agirligi", "anne kilo", "maternal weight",
             "patient weight", "weight"),
            low=20, high=250,
            forbidden=("fetal", "efw", "tahmini fetal", "birth weight"))
        if weight is not None:
            set_demo("weight", weight, source)

        height_val = _parse_metric_value(
            lines,
            ("boy", "boyu", "height", "height cm", "stature"),
            low=90, high=230,
            forbidden=("femur", "fl", "crl", "boyut", "image size"),
            height=True)
        if height_val is not None:
            set_demo("height", height_val, source)

        pre_weight = _parse_metric_value(
            lines,
            ("gebelik oncesi kilo", "gebelik oncesi agirlik",
             "pre pregnancy weight", "prepregnancy weight",
             "pre-pregnancy weight"),
            low=20, high=250,
            forbidden=("fetal", "efw", "tahmini fetal"))
        if pre_weight is not None:
            set_demo("pre_pregnancy_weight", pre_weight, source)

        bmi = _parse_metric_value(
            lines,
            ("bmi", "vki", "bki", "beden kitle indeksi", "body mass index"),
            low=10, high=80,
            forbidden=("fetal",))
        if bmi is not None:
            set_demo("bmi", bmi, source)
        elif weight is not None and height_val is not None:
            try:
                h_m = float(height_val) / 100.0
                if h_m > 0:
                    set_demo("bmi", round(float(weight) / (h_m * h_m), 1), source)
            except Exception:
                pass

        for key, labels in (
            ("allergies", ("alerji", "allergy", "allergies")),
            ("medications", ("ilaclar", "kullandigi ilac", "medication", "medications")),
            ("chronic_conditions", ("kronik hastalik", "ozgecmis", "medical history", "chronic")),
        ):
            val = _line_value(lines, labels)
            if val:
                set_demo(key, val, source)

        lmp = _line_value(lines, ("sat", "son adet tarihi", "lmp", "last menstrual period"))
        lmp_date = _date(lmp) or _date(_flat_value(folded, (
            r"(?:\bsat\b|son\s*adet\s*tarihi|\blmp\b|last\s*menstrual\s*period)\D{0,30}(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
            r"(?:\bsat\b|son\s*adet\s*tarihi|\blmp\b|last\s*menstrual\s*period)\D{0,30}(\d{4}[./-]\d{1,2}[./-]\d{1,2})",
        )))
        if lmp_date:
            set_demo("lmp_override", lmp_date, source)

        edd = _line_value(lines, ("tahmini dogum", "edd", "expected date", "due date"))
        edd_date = _date(edd) or _date(_flat_value(folded, (
            r"(?:tahmini\s*dogum|edd|expected\s*date|due\s*date)\D{0,30}(\d{1,2}[./-]\d{1,2}[./-]\d{4})",
            r"(?:tahmini\s*dogum|edd|expected\s*date|due\s*date)\D{0,30}(\d{4}[./-]\d{1,2}[./-]\d{1,2})",
        )))
        if edd_date:
            set_demo("edd_from_pdf", edd_date, source)

        report_date = _line_value(lines, ("rapor tarihi", "muayene tarihi", "study date", "exam date", "date"))
        report_date_norm = _iso_date(report_date)
        if report_date_norm:
            set_fetal("usg_date", report_date_norm, source)

        measurements = _parse_measurements(text)
        for key, value in measurements.items():
            set_fetal(key, value, source)

        pdf_labs = _parse_labs(lines, source, limit=40)
        labs.extend(pdf_labs)
        for diag in _parse_diagnoses(lines, source, limit=12):
            if not any(d["text"] == diag["text"] for d in diagnoses):
                diagnoses.append(diag)
            if not any(d["text"] == diag["text"] for d in pdf_diagnoses):
                pdf_diagnoses.append(diag)

        for labels in (
            ("sonuc", "conclusion", "impression"),
            ("aciklama", "not", "note"),
        ):
            val = _line_value(lines, labels)
            if val and len(val) >= 5 and not any(n["text"] == val for n in notes):
                note_row = {"text": val, "source": source}
                notes.append(note_row)
                pdf_notes.append(note_row)

        if report_date_norm:
            pdf_record["report_date"] = report_date_norm
        pdf_record["demographics"] = pdf_demo
        pdf_record["sources"] = pdf_sources
        pdf_record["fetal"] = pdf_fetal
        pdf_record["fetal_sources"] = pdf_fetal_sources
        pdf_record["labs"] = pdf_labs[:40]
        pdf_record["diagnoses"] = pdf_diagnoses[:12]
        pdf_record["notes"] = pdf_notes[:12]
        pdfs.append(pdf_record)

    summary: list[str] = []
    if demographics:
        summary.append(f"{len(demographics)} hasta alani bulundu")
    if fetal:
        summary.append(f"{len(fetal)} USG/gebelik alani bulundu")
    if labs:
        summary.append(f"{len(labs)} laboratuvar satiri yakalandi")
    if diagnoses:
        summary.append(f"{len(diagnoses)} tani/sonuc satiri yakalandi")

    return {
        "ok": bool(demographics or fetal or labs or diagnoses or notes),
        "demographics": demographics,
        "sources": sources,
        "fetal": fetal,
        "fetal_sources": fetal_sources,
        "labs": labs[:80],
        "diagnoses": diagnoses[:40],
        "notes": notes[:40],
        "pdfs": pdfs,
        "summary_lines": summary,
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
    }
