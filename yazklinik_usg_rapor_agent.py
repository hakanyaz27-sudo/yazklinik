"""USG Rapor Ajani.

BK Voluson ya da elle girilen olcumlerden klinik standartta rapor taslagi uretir.
Sadece TASLAK uretir - doktor onayi olmadan hasta dosyasina yazmaz.

Ne yapar:
    - Olcum sozlugunu (BPD, HC, AC, FL, EFW vb.) alir
    - LMP/USG haftasi referansiyla gebelik haftasini hesaplar
    - Hadlock formuluyle EFW persantilini kestirir (rapor icin)
    - Standart 1. tri / 2. tri / 3. tri / morfolojik tarama sablonlarini doldurur
    - Anormal degerleri "dikkat" notu olarak isaretler

Asla yapmaz:
    - Klinik karar veya tani vermez ("normal/anormal" demez, sadece deger karsilastirir)
    - Otomatik hasta dosyasina yazmaz
    - NAS USG goruntusunu silmez/tasimaz

Stdlib only. yazklinik_voluson.py uretimi bu modulun input formati ile uyumludur.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple


AGENT_VERSION = "2026.05.16-usg-rapor"
SOURCE_LABEL = "USG olcum -> rapor taslagi"

REPORT_TYPES = ("first_trimester", "second_trimester", "third_trimester", "morphology", "free")

# Hadlock formulu icin tipik gebelik haftasi referans persantilleri (basit ortalama).
# Gercek normogram tablosu yerine "ortalama / +/- 2SD" yaklasimi - sadece taslakta is.
# Kaynak: Hadlock FP, Radiology 1984 - egitimlerde yaygin sablon.
REFERENCE_MEANS = {
    # GA(haftasi): {parametre: (mean_mm, sd_mm)}
    12: {"BPD": (20, 3), "HC": (74, 6), "AC": (60, 6), "FL": (8, 2)},
    16: {"BPD": (35, 3), "HC": (124, 7), "AC": (108, 8), "FL": (20, 3)},
    20: {"BPD": (47, 4), "HC": (175, 9), "AC": (152, 10), "FL": (32, 3)},
    24: {"BPD": (60, 4), "HC": (224, 11), "AC": (197, 13), "FL": (44, 4)},
    28: {"BPD": (71, 4), "HC": (266, 12), "AC": (240, 15), "FL": (54, 4)},
    32: {"BPD": (81, 5), "HC": (296, 13), "AC": (280, 18), "FL": (62, 4)},
    36: {"BPD": (88, 5), "HC": (322, 14), "AC": (319, 20), "FL": (68, 4)},
    40: {"BPD": (94, 6), "HC": (344, 14), "AC": (350, 22), "FL": (73, 4)},
}


@dataclass
class Measurement:
    name: str                # "BPD" | "HC" | "AC" | "FL" | "CRL" | ...
    value_mm: float
    notes: str = ""


@dataclass
class USGInput:
    patient_id: str
    patient_name: str
    exam_date: str           # ISO date
    lmp: Optional[str] = None  # last menstrual period ISO date
    measurements: List[Measurement] = field(default_factory=list)
    report_type: str = "second_trimester"
    operator: str = "Op. Dr. Hakan YAZ"
    device: str = "GE Voluson"


@dataclass
class USGReportDraft:
    patient_id: str
    patient_name: str
    exam_date: str
    report_type: str
    ga_text: str             # ornek: "20 hafta 3 gun"
    efw_grams: Optional[int] = None
    findings: List[str] = field(default_factory=list)
    measurement_table: List[Dict[str, Any]] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)   # dikkat notlari
    raw_body: str = ""
    requires_doctor_review: bool = True
    agent_version: str = AGENT_VERSION


def _fold(value: Any) -> str:
    text = str(value or "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return text.casefold()


def calc_ga_weeks_days(lmp: Optional[str], exam_date: str) -> Tuple[Optional[int], Optional[int]]:
    """LMP ve muayene tarihinden gebelik haftasi/gunu hesapla."""
    if not lmp:
        return None, None
    try:
        l = date.fromisoformat(lmp)
        e = date.fromisoformat(exam_date)
    except Exception:
        return None, None
    delta_days = (e - l).days
    if delta_days < 0 or delta_days > 320:
        return None, None
    return delta_days // 7, delta_days % 7


def hadlock_efw_grams(bpd_mm: float, hc_mm: float, ac_mm: float, fl_mm: float) -> Optional[int]:
    """Hadlock IV formulu (mm -> cm donusumu icin /10).

    log10(EFW) = 1.3596 + 0.0064*HC + 0.0424*AC + 0.174*FL +
                 0.00061*BPD*AC - 0.00386*AC*FL

    Sadece taslak; doktor klinik baglamla yorumlamali.
    """
    try:
        bpd = bpd_mm / 10.0
        hc = hc_mm / 10.0
        ac = ac_mm / 10.0
        fl = fl_mm / 10.0
        if min(bpd, hc, ac, fl) <= 0:
            return None
        log_efw = (
            1.3596
            + 0.0064 * hc
            + 0.0424 * ac
            + 0.174 * fl
            + 0.00061 * bpd * ac
            - 0.00386 * ac * fl
        )
        return int(round(10 ** log_efw))
    except Exception:
        return None


def reference_window(ga_weeks: int) -> Dict[str, Tuple[float, float]]:
    """En yakin haftaya gore (mean, sd) sozlugu."""
    if ga_weeks <= 0:
        return {}
    closest = min(REFERENCE_MEANS.keys(), key=lambda w: abs(w - ga_weeks))
    return REFERENCE_MEANS[closest]


def flag_measurements(measurements: List[Measurement], ga_weeks: Optional[int]) -> List[str]:
    """+/- 2SD disinda olanlari isaretle. Klinik karar degildir, sadece dikkat notudur."""
    flags: List[str] = []
    if not ga_weeks:
        return flags
    refs = reference_window(ga_weeks)
    for m in measurements:
        key = m.name.upper()
        if key not in refs:
            continue
        mean, sd = refs[key]
        diff = m.value_mm - mean
        if abs(diff) > 2 * sd:
            direction = "yuksek" if diff > 0 else "dusuk"
            flags.append(
                f"DIKKAT: {key} = {m.value_mm:.1f} mm "
                f"(beklenen ~{mean:.0f} +/- {2*sd:.0f}) - {direction} taraf disinda."
            )
    return flags


def _measurement_dict(measurements: List[Measurement]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for m in measurements:
        out[m.name.upper()] = float(m.value_mm)
    return out


def _build_body(report_type: str, patient_name: str, ga_text: str, efw_grams: Optional[int],
                measurements: List[Measurement], flags: List[str]) -> str:
    """Sablonlanmis duz metin rapor. Sablonlar genis tutuluyor; doktor uzerine yazar."""
    lines = []
    lines.append(f"Hasta: {patient_name}")
    lines.append(f"Rapor tipi: {report_type}")
    lines.append(f"Gebelik haftasi: {ga_text}")
    if efw_grams:
        lines.append(f"Tahmini fetal agirlik (EFW, Hadlock IV): {efw_grams} g")
    lines.append("")
    lines.append("Olcumler:")
    for m in measurements:
        notes = f" - {m.notes}" if m.notes else ""
        lines.append(f"  - {m.name}: {m.value_mm:.1f} mm{notes}")

    if report_type == "first_trimester":
        lines.extend([
            "",
            "Birinci trimester bulgular (taslak):",
            "  - Gestasyonel kese izlendi.",
            "  - Yolk sac dogal goruldu.",
            "  - Fetal kalp atimi izlendi / izlenmedi (DOKTOR BELIRLEYIN).",
            "  - NT olcumu icin uygun pozisyon (varsa girilmis olmali).",
        ])
    elif report_type == "second_trimester":
        lines.extend([
            "",
            "Ikinci trimester degerlendirme (taslak):",
            "  - Fetal biyometri yukarida ozetlenmistir.",
            "  - Plasenta lokalizasyonu / amnion mai (DOKTOR DOLDURUN).",
            "  - Major organ sistemleri morfolojik tarama (DOKTOR DOLDURUN).",
        ])
    elif report_type == "third_trimester":
        lines.extend([
            "",
            "Ucuncu trimester degerlendirme (taslak):",
            "  - Fetal pozisyon ve sunum (DOKTOR DOLDURUN).",
            "  - Plasenta - amnion mai - dopler (DOKTOR DOLDURUN).",
            "  - Tahmini dogum tarihine kalan sure (LMP ile).",
        ])
    elif report_type == "morphology":
        lines.extend([
            "",
            "Morfolojik tarama (18-22 hafta, taslak):",
            "  - Kafa ve beyin yapilari (DOKTOR DOLDURUN).",
            "  - Yuz / yumusak damak / dudak.",
            "  - Goguste kalp 4 odacik gorunumu.",
            "  - Abdomen, midye, bobrekler, mesane.",
            "  - Ekstremiteler (uzun kemikler).",
            "  - Genital bolge (aileye onayli paylasim).",
        ])

    if flags:
        lines.append("")
        lines.append("Dikkat notlari:")
        for f in flags:
            lines.append(f"  - {f}")

    lines.append("")
    lines.append("Bu rapor TASLAKTIR. Klinik karar ve son rapor doktora aittir.")
    return "\n".join(lines)


def build_draft(data: USGInput) -> USGReportDraft:
    """Ana giris noktasi."""
    if data.report_type not in REPORT_TYPES:
        report_type = "free"
    else:
        report_type = data.report_type

    weeks, days = calc_ga_weeks_days(data.lmp, data.exam_date)
    ga_text = f"{weeks} hafta {days} gun" if weeks is not None else "LMP girilmemis - GA hesaplanamadi"

    measurement_table: List[Dict[str, Any]] = [
        {"name": m.name, "value_mm": m.value_mm, "notes": m.notes} for m in data.measurements
    ]

    mdict = _measurement_dict(data.measurements)
    efw = None
    if all(k in mdict for k in ("BPD", "HC", "AC", "FL")):
        efw = hadlock_efw_grams(mdict["BPD"], mdict["HC"], mdict["AC"], mdict["FL"])

    flags = flag_measurements(data.measurements, weeks)

    body = _build_body(report_type, data.patient_name, ga_text, efw, data.measurements, flags)

    findings = []
    if efw:
        findings.append(f"Hadlock EFW: {efw} g")
    if not flags:
        findings.append("Standart biyometri referans araliginda goruldu (taslak yorum).")

    return USGReportDraft(
        patient_id=str(data.patient_id),
        patient_name=str(data.patient_name),
        exam_date=str(data.exam_date),
        report_type=report_type,
        ga_text=ga_text,
        efw_grams=efw,
        findings=findings,
        measurement_table=measurement_table,
        flags=flags,
        raw_body=body,
    )


def to_audit_payload(draft: USGReportDraft) -> Dict[str, Any]:
    payload = asdict(draft)
    payload["action"] = "usg_rapor:taslak"
    return payload


if __name__ == "__main__":
    sample = USGInput(
        patient_id="P0001",
        patient_name="Ayse Yilmaz",
        exam_date="2026-05-15",
        lmp="2025-12-22",
        report_type="second_trimester",
        measurements=[
            Measurement("BPD", 48.0),
            Measurement("HC", 178.0),
            Measurement("AC", 155.0),
            Measurement("FL", 33.0),
        ],
    )
    draft = build_draft(sample)
    print(f"GA: {draft.ga_text} | EFW: {draft.efw_grams} g | Flags: {len(draft.flags)}")
    print(draft.raw_body[:300])
