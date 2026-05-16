"""Voluson Obstetrics Report PDF parser + import.

Voluson E-series cihazlardan "Print to PDF" ile uretilen rapor PDF'lerini
ayristirip hasta DB'sine isler. Tum 2D olcumler + Doppler + percentile +
hasta bilgisi cikar.

Test edilen format: "Measure Report" / "Obstetrics Report" (Microsoft Print To
PDF cikisi). Page 1 = patient + ana olcumler, Page 2-3 = doppler/graphs.

Kullanim:
  python yazklinik_voluson.py <pdf_yolu>      # tek dosya parse + JSON yazdir
  python yazklinik_voluson.py scan <kok_dir>  # toplu tarama + import
  python yazklinik_voluson.py import <pdf>    # parse + DB'ye yaz
"""
from __future__ import annotations

import os
import re
import json
import time
import sqlite3
import datetime
from typing import Optional


# ============================================================================
# Field extraction
# ============================================================================

def _to_float(s, default=None):
    if s is None:
        return default
    try:
        # "85.95 mm" -> 85.95 | "2240g" -> 2240
        m = re.search(r"-?\d+(?:\.\d+)?", str(s))
        return float(m.group(0)) if m else default
    except Exception:
        return default


def _to_int(s, default=None):
    v = _to_float(s, None)
    return int(v) if v is not None else default


def _ga_to_days(ga_str):
    """'32w0d' -> 224 (gun)."""
    if not ga_str:
        return None
    m = re.match(r"(\d+)w(\d+)d", str(ga_str).strip())
    if not m:
        return None
    return int(m.group(1)) * 7 + int(m.group(2))


def _parse_date(s):
    """'08.05.2026' / '03.07.2026' -> ISO 'YYYY-MM-DD'."""
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except Exception:
            continue
    return None


def _date_to_ms(date_str, time_str=None):
    """ISO date + 'HH:MM:SS' -> unix ms."""
    if not date_str:
        return None
    try:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        if time_str:
            t = datetime.datetime.strptime(time_str.strip(), "%H:%M:%S").time()
            dt = dt.replace(hour=t.hour, minute=t.minute, second=t.second)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def _next_value(lines, i, known_labels=None, skip_empty=True):
    """lines[i] label oldugunu varsay; sonraki dolu satiri don.

    known_labels verildiyse, eger sonraki satir baska bir bilinen label ise
    bu alanin BOS oldugu kabul edilir ('' donulur). Boylece "Gravida\nPara\n"
    gibi durumlarda Gravida'nin degeri 'Para' olarak okunmaz.
    """
    j = i + 1
    while j < len(lines):
        v = lines[j].strip()
        if v or not skip_empty:
            if known_labels and v in known_labels:
                return "", i  # bos field
            return v, j
        j += 1
    return "", j


def parse_voluson_pdf(pdf_path):
    """Voluson OB report PDF'i ayristir.

    Returns: dict {patient_id, name, dob, age, sex, height_cm, weight_kg,
                   bmi, lmp, edd_lmp, edd_aua, ga_lmp, ga_aua, fetus,
                   efw_g, efw_percentile, bpd_mm, bpd_ga, bpd_percentile,
                   ac_mm, ac_ga, ac_percentile, fl_mm, fl_ga, fl_percentile,
                   hc_mm, hc_ga, hc_percentile,
                   fl_ac_ratio, fl_bpd_ratio,
                   umb_pi, umb_ri, umb_sd, umb_ps, umb_ed, umb_tamax, umb_md,
                   fetal_hr, exam_date, exam_time, raw_text}
    """
    import fitz
    doc = fitz.open(pdf_path)
    all_text_parts = []
    for page in doc:
        all_text_parts.append(page.get_text("text"))
    raw_text = "\n".join(all_text_parts)
    doc.close()

    # Tum text'i satir satir kes
    lines = [l for l in raw_text.split("\n")]
    # Trim ama indeksleri koru
    out = {"raw_text": raw_text, "pdf_path": pdf_path,
           "pdf_filename": os.path.basename(pdf_path)}

    # --- 1) Direkt label arama (multi-line label/value pattern) ---
    label_map = {
        "Patient ID": "patient_id",
        "Name": "name",
        "DOB,Age": "dob_age_raw",
        "Sex": "sex",
        "Height": "height_raw",
        "Weight": "weight_raw",
        "BMI": "bmi",
        "Systolic BP": "systolic_bp",
        "Diastolic BP": "diastolic_bp",
        "MAP": "map_bp",
        "Gravida": "gravida",
        "Para": "para",
        "AB": "ab_count",
        "Ectopic": "ectopic",
        "Fetus": "fetus",
        "LMP": "lmp_raw",
        "DOC": "doc_raw",
        "EDD(LMP)": "edd_lmp_raw",
        "GA(LMP)": "ga_lmp",
        "GA(AUA)": "ga_aua",
        "EDD(AUA)": "edd_aua_raw",
        "Date of Exam:": "exam_date_raw",
        "Perf. Phys.": "perf_phys",
        "Ref. Phys.": "ref_phys",
        "Sonographer": "sonographer",
        "Comment": "comment",
        "Indication": "indication",
    }
    known_labels = set(label_map.keys())
    for i, line in enumerate(lines):
        l = line.strip()
        if l in label_map:
            v, _ = _next_value(lines, i, known_labels=known_labels)
            key = label_map[l]
            if key not in out:  # ilk gorulen kazanir
                out[key] = v

    # --- 2) Donusumler ---
    # DOB, Age "02.03.2002,24"
    if "dob_age_raw" in out:
        m = re.match(r"(\d{2}\.\d{2}\.\d{4})\s*,\s*(\d+)", out["dob_age_raw"])
        if m:
            out["dob"] = _parse_date(m.group(1))
            out["age"] = int(m.group(2))
    # Height "165.0 cm"
    out["height_cm"] = _to_float(out.get("height_raw"))
    out["weight_kg"] = _to_float(out.get("weight_raw"))
    out["bmi"] = _to_float(out.get("bmi"))
    out["systolic_bp"] = _to_int(out.get("systolic_bp"))
    out["diastolic_bp"] = _to_int(out.get("diastolic_bp"))
    out["fetus"] = _to_int(out.get("fetus"))
    # Dates
    out["lmp"] = _parse_date(out.get("lmp_raw"))
    out["edd_lmp"] = _parse_date(out.get("edd_lmp_raw"))
    out["edd_aua"] = _parse_date(out.get("edd_aua_raw"))
    out["exam_date"] = _parse_date(out.get("exam_date_raw"))
    # GA days
    out["ga_lmp_days"] = _ga_to_days(out.get("ga_lmp"))
    out["ga_aua_days"] = _ga_to_days(out.get("ga_aua"))

    # --- 3) EFW (Hadlock) - "2240g ± 327g  33w3d  86.6%" gibi satir ---
    # PDF text'inde: label "EFW (Hadlock)" sonra "Value\nRange\nAge\nRange\nGP (Hadlock)\nAC/BPD/FL"
    # sonra deger satiri olarak "2240g\n± 327g\n33w3d\n86.6%"
    efw_m = re.search(
        r"EFW\s*\(Hadlock\).*?\n(\d+)\s*g\s*\n[±+]?\s*(\d+)\s*g\s*\n"
        r"(\d+w\d+d)\s*\n([\d.]+)\s*%",
        raw_text, re.IGNORECASE | re.DOTALL)
    if efw_m:
        out["efw_g"] = int(efw_m.group(1))
        out["efw_range_g"] = int(efw_m.group(2))
        out["efw_ga"] = efw_m.group(3)
        out["efw_percentile"] = float(efw_m.group(4))

    # --- 4) BPD / AC / FL / HC blok pattern ---
    # "BPD (Hadlock)\n85.95 mm\n85.95\nlast\n96.8% 34w5d"
    # ya da "%96.8 34w5d"
    biometry_keys = [
        ("BPD", "bpd"),
        ("HC", "hc"),
        ("AC", "ac"),
        ("FL", "fl"),
        ("OFD", "ofd"),
        ("TCD", "tcd"),
        ("Cisterna Magna", "cm"),
        ("NF", "nf"),
        ("NT", "nt"),
        ("CRL", "crl"),
        ("BD", "bd"),
        ("APD", "apd"),
        ("FD", "fd"),
    ]
    for label, key in biometry_keys:
        # Pattern: "BPD (Hadlock)" sonra mm degeri (satir sonu veya bosluk)
        # sonra GP yuzdesi + GA (ayni satirda olabilir)
        # AC ornegi: "AC (Hadlock)\n281.27 mm 281.27\nlast\n53.8% 32w1d"
        # BPD ornegi: "BPD (Hadlock)\n85.95 mm\n85.95\nlast\n96.8% 34w5d"
        pat = re.compile(
            rf"\b{re.escape(label)}\b(?:\s*\([^)]+\))?\s*\n\s*"
            rf"([\d.]+)\s*mm[\s\S]{{0,80}}?([\d.]+)\s*%\s+(\d+w\d+d)",
            re.IGNORECASE)
        m = pat.search(raw_text)
        if m:
            out[f"{key}_mm"] = float(m.group(1))
            out[f"{key}_percentile"] = float(m.group(2))
            out[f"{key}_ga"] = m.group(3)

    # --- 5) FL/AC, FL/BPD oranlari ---
    for ratio_label, ratio_key in [("FL/AC", "fl_ac_ratio"),
                                   ("FL/BPD", "fl_bpd_ratio"),
                                   ("HC/AC", "hc_ac_ratio"),
                                   ("BPD/OFD", "bpd_ofd_ratio")]:
        m = re.search(rf"{re.escape(ratio_label)}\s*\n\s*([\d.]+)\s*%",
                      raw_text, re.IGNORECASE)
        if m:
            out[ratio_key] = float(m.group(1))

    # --- 6) Doppler ---
    # "Umbilical Art." sonra PS, ED, TAmax, MD, RI, PI, S/D, HR
    doppler_keys = [
        ("PS", "umb_ps", "cm/s"),
        ("ED", "umb_ed", "cm/s"),
        ("TAmax", "umb_tamax", "cm/s"),
        ("MD", "umb_md", "cm/s"),
        ("RI", "umb_ri", None),
        ("PI", "umb_pi", None),
        ("S/D", "umb_sd", None),
        ("HR", "fetal_hr", "bpm"),
    ]
    # Doppler bolumu yaklasik "Doppler Measurements" sonrasi
    dop_section = ""
    dm = re.search(r"Doppler\s+Measurements(.*?)(?:Doppler\s+Calculations|\Z)",
                   raw_text, re.IGNORECASE | re.DOTALL)
    if dm:
        dop_section = dm.group(1)
    for label, key, unit in doppler_keys:
        # "RI\n0.60 \n0.60\navg." pattern
        if label == "S/D":
            pat = re.compile(r"S/D\s*\n\s*([\d.]+)", re.IGNORECASE)
        else:
            pat = re.compile(
                rf"^\s*{re.escape(label)}\s*\n\s*([\d.]+)",
                re.IGNORECASE | re.MULTILINE)
        m = pat.search(dop_section) if dop_section else pat.search(raw_text)
        if m:
            val = float(m.group(1))
            if label == "HR":
                out[key] = int(val)
            else:
                out[key] = val

    # --- 7) Exam time (header'da "08.05.2026   13:20:52") ---
    tm = re.search(r"(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2}:\d{2})", raw_text)
    if tm:
        out["exam_time"] = tm.group(2)
        if not out.get("exam_date"):
            out["exam_date"] = _parse_date(tm.group(1))

    # --- 8) Computed: exam_ts ---
    out["exam_ts"] = _date_to_ms(out.get("exam_date"), out.get("exam_time"))
    out["imported_ts"] = int(time.time() * 1000)

    # --- 9) Klinik flag'ler (basit risk yorumu) ---
    flags = []
    if out.get("efw_percentile") is not None:
        if out["efw_percentile"] < 10:
            flags.append("EFW < 10p (SGA/IUGR riski)")
        elif out["efw_percentile"] > 90:
            flags.append("EFW > 90p (LGA/Makrozomi riski)")
    if out.get("umb_pi") is not None and out["umb_pi"] > 1.40:
        flags.append("Umb PI yuksek (placental disfonksiyon?)")
    if out.get("fetal_hr") is not None:
        hr = out["fetal_hr"]
        if hr < 110 or hr > 160:
            flags.append(f"Fetal HR anormal ({hr} bpm)")
    if out.get("bmi") is not None and out["bmi"] >= 30:
        flags.append(f"Maternal obezite (BMI {out['bmi']})")
    out["clinical_flags"] = flags

    return out


# ============================================================================
# DB schema + import
# ============================================================================

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")


def _db_conn(db_path=None):
    con = sqlite3.connect(db_path or DEFAULT_DB_PATH, timeout=10)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA synchronous=NORMAL")
    return con


def _now_iso():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _table_columns(con, table_name):
    try:
        return [r[1] for r in con.execute(
            f"PRAGMA table_info({table_name})").fetchall()]
    except Exception:
        return []


def _table_exists(con, name):
    try:
        r = con.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type='table' AND name=?", (name,)).fetchone()
        return bool(r)
    except Exception:
        return False


def _build_voluson_examination_summary(data):
    """Visit ekrani icin kisa, okunur ozet metni uret (Gelisler sayfasinda gosterilir)."""
    bits = []
    ga = data.get("ga_aua") or data.get("ga_lmp")
    if ga:
        bits.append(f"GA: {ga}")
    if data.get("efw_g"):
        suffix = ""
        if data.get("efw_percentile") is not None:
            suffix = f" (%{data['efw_percentile']:.0f}p)"
        bits.append(f"EFW: {data['efw_g']}g{suffix}")
    for key, label in (("bpd_mm","BPD"), ("hc_mm","HC"),
                       ("ac_mm","AC"), ("fl_mm","FL")):
        v = data.get(key)
        if v is not None:
            bits.append(f"{label}: {v:.1f}mm")
    if data.get("fetal_hr"):
        bits.append(f"FHR: {data['fetal_hr']}/dk")
    flags = data.get("clinical_flags") or []
    if flags:
        bits.append("FLAG: " + ", ".join(flags))
    return "USG (Voluson) - " + " | ".join(bits) if bits else "USG (Voluson) raporu"


def _build_voluson_visit_notes(data):
    """Notlar alani icin tum demografik+vital+olcum dokumu (uzun, hasta kartinda goruntulenir)."""
    lines = []
    lines.append("Voluson USG raporu (otomatik import)")
    pdf_fn = data.get("pdf_filename") or ""
    if pdf_fn:
        lines.append(f"Kaynak PDF: {pdf_fn}")
    # Demografik / vital
    dem = []
    if data.get("age"):       dem.append(f"Yas: {data['age']}")
    if data.get("dob"):       dem.append(f"DOB: {data['dob']}")
    if data.get("height_cm"): dem.append(f"Boy: {data['height_cm']} cm")
    if data.get("weight_kg"): dem.append(f"Kilo: {data['weight_kg']} kg")
    if data.get("bmi"):       dem.append(f"BMI: {data['bmi']}")
    if data.get("systolic_bp") and data.get("diastolic_bp"):
        dem.append(f"TA: {data['systolic_bp']}/{data['diastolic_bp']} mmHg")
    if dem:
        lines.append("Demografik / vital: " + " | ".join(dem))
    # Gebelik
    g = []
    if data.get("gravida"):   g.append(f"G: {data['gravida']}")
    if data.get("para"):      g.append(f"P: {data['para']}")
    if data.get("lmp"):       g.append(f"LMP: {data['lmp']}")
    if data.get("ga_lmp"):    g.append(f"GA(LMP): {data['ga_lmp']}")
    if data.get("ga_aua"):    g.append(f"GA(AUA): {data['ga_aua']}")
    if data.get("edd_lmp"):   g.append(f"EDD(LMP): {data['edd_lmp']}")
    if g:
        lines.append("Gebelik: " + " | ".join(g))
    # Biyometri tek satir
    bio = []
    for key, label in (("bpd_mm","BPD"), ("hc_mm","HC"),
                       ("ac_mm","AC"), ("fl_mm","FL"),
                       ("ofd_mm","OFD"), ("tcd_mm","TCD"),
                       ("nt_mm","NT"), ("crl_mm","CRL")):
        v = data.get(key)
        if v is not None:
            pct = data.get(key.replace("_mm","_percentile"))
            bio.append(f"{label} {v:.1f}mm" + (f" (%{pct:.0f}p)" if pct else ""))
    if bio:
        lines.append("Biyometri: " + " | ".join(bio))
    if data.get("efw_g"):
        s = f"EFW: {data['efw_g']}g"
        if data.get("efw_percentile") is not None:
            s += f" (%{data['efw_percentile']:.1f}p)"
        lines.append(s)
    # Doppler
    dop = []
    for key, label in (("umb_pi","Umb PI"), ("umb_ri","Umb RI"),
                       ("umb_sd","Umb S/D"), ("fetal_hr","FHR")):
        v = data.get(key)
        if v is not None:
            dop.append(f"{label}: {v}")
    if dop:
        lines.append("Doppler: " + " | ".join(dop))
    flags = data.get("clinical_flags") or []
    if flags:
        lines.append("Klinik flag'ler: " + "; ".join(flags))
    return "\n".join(lines)


def _sync_to_patient_records(con, data, patient_key, pdf_path):
    """Voluson PDF verisini visits + patient_demographics tablolarina kopru.

    Sadece patient_key eslesmis ise calisir; tablolarin var olup olmadigini
    defansif olarak kontrol eder. Tum is tek transaction icinde.

    Returns: {"visit_written": bool, "demographics_updated": bool, "reason": str}
    """
    out = {"visit_written": False, "demographics_updated": False, "reason": ""}
    if not patient_key:
        out["reason"] = "patient_key bos (hasta eslesmemis)"
        return out

    # --- 1) VISITS tablosu - ayni PDF'ten ikinci visit acmamak icin idempotent ---
    if _table_exists(con, "visits"):
        try:
            import hashlib as _hash
            visit_key = "voluson-" + _hash.md5(
                (pdf_path or "").encode("utf-8", "replace")).hexdigest()[:14]

            vcols = _table_columns(con, "visits")
            has_visit_key = "visit_key" in vcols
            has_source    = "source" in vcols
            has_visit_type = "visit_type" in vcols
            has_examination = "examination" in vcols

            # Daha once import edilmis mi?
            already = None
            if has_visit_key:
                r = con.execute(
                    "SELECT id FROM visits WHERE visit_key = ?",
                    (visit_key,)).fetchone()
                if r:
                    already = r[0]

            if not already:
                examination = _build_voluson_examination_summary(data)
                notes = _build_voluson_visit_notes(data)
                # exam_date varsa onu kullan, yoksa simdi
                visit_date = data.get("exam_date") or _now_iso()
                # Kolonlari dinamik kur
                col_names = ["patient_folder_key", "visit_date", "notes", "created_at"]
                values    = [patient_key, visit_date, notes, _now_iso()]
                if has_visit_type:
                    col_names.append("visit_type"); values.append("usg")
                if has_examination:
                    col_names.append("examination"); values.append(examination)
                if has_source:
                    col_names.append("source"); values.append("voluson:auto")
                if has_visit_key:
                    col_names.append("visit_key"); values.append(visit_key)
                placeholders = ",".join("?" * len(values))
                con.execute(
                    f"INSERT INTO visits ({','.join(col_names)}) "
                    f"VALUES ({placeholders})", values)
                out["visit_written"] = True
        except Exception as exc:
            out["reason"] = f"visits hata: {exc}"

    # --- 2) PATIENT_DEMOGRAPHICS - JSON merge, mevcudu ezme ---
    if _table_exists(con, "patient_demographics"):
        try:
            dcols = _table_columns(con, "patient_demographics")
            existing = {}
            if "data_json" in dcols:
                r = con.execute(
                    "SELECT data_json FROM patient_demographics "
                    "WHERE patient_key = ?", (patient_key,)).fetchone()
                if r and r[0]:
                    try:
                        existing = json.loads(r[0])
                        if not isinstance(existing, dict):
                            existing = {}
                    except Exception:
                        existing = {}

            def _set_if_empty(target, key, value):
                if value is None or value == "":
                    return
                # Mevcut bossa veya gercek bir deger degilse, yenisini koy
                cur = target.get(key)
                if cur in (None, "", 0):
                    target[key] = value

            _set_if_empty(existing, "age", data.get("age"))
            _set_if_empty(existing, "birth_date", data.get("dob"))
            _set_if_empty(existing, "height", data.get("height_cm"))
            _set_if_empty(existing, "height_cm", data.get("height_cm"))
            _set_if_empty(existing, "weight", data.get("weight_kg"))
            _set_if_empty(existing, "weight_kg", data.get("weight_kg"))
            _set_if_empty(existing, "bmi", data.get("bmi"))

            # Kan basinci nested olarak da, duz olarak da yazilsin (farkli sayfalar farkli okuyor)
            if data.get("systolic_bp"):
                _set_if_empty(existing, "systolic_bp", data["systolic_bp"])
                _set_if_empty(existing, "systolic", data["systolic_bp"])
            if data.get("diastolic_bp"):
                _set_if_empty(existing, "diastolic_bp", data["diastolic_bp"])
                _set_if_empty(existing, "diastolic", data["diastolic_bp"])
            if data.get("systolic_bp") and data.get("diastolic_bp"):
                bp = existing.get("blood_pressure")
                if not isinstance(bp, dict):
                    bp = {}
                bp.setdefault("systolic", data["systolic_bp"])
                bp.setdefault("diastolic", data["diastolic_bp"])
                bp.setdefault("recorded_at", data.get("exam_date") or _now_iso())
                bp.setdefault("source", "voluson")
                existing["blood_pressure"] = bp
                # Duz string fallback (eski sayfa)
                _set_if_empty(existing, "ta",
                              f"{data['systolic_bp']}/{data['diastolic_bp']}")

            # Gebelik bilgileri
            if data.get("lmp"):
                _set_if_empty(existing, "last_menstrual_period", data["lmp"])
                _set_if_empty(existing, "lmp", data["lmp"])
            if data.get("gravida"):
                _set_if_empty(existing, "gravida", data["gravida"])
            if data.get("para"):
                _set_if_empty(existing, "para", data["para"])

            existing["_last_voluson_sync"] = _now_iso()

            data_json = json.dumps(existing, ensure_ascii=False, default=str)
            if "data_json" in dcols and "updated_at" in dcols:
                con.execute(
                    "INSERT INTO patient_demographics (patient_key, data_json, updated_at) "
                    "VALUES (?, ?, ?) "
                    "ON CONFLICT(patient_key) DO UPDATE SET "
                    "  data_json = excluded.data_json, "
                    "  updated_at = excluded.updated_at",
                    (patient_key, data_json, _now_iso()))
                out["demographics_updated"] = True
            elif "data_json" in dcols:
                con.execute(
                    "INSERT INTO patient_demographics (patient_key, data_json) "
                    "VALUES (?, ?) "
                    "ON CONFLICT(patient_key) DO UPDATE SET "
                    "  data_json = excluded.data_json",
                    (patient_key, data_json))
                out["demographics_updated"] = True
        except Exception as exc:
            if out["reason"]:
                out["reason"] += " | "
            out["reason"] += f"demographics hata: {exc}"

    return out


def init_db(db_path=None):
    """voluson_reports tablosunu olustur (idempotent)."""
    con = _db_conn(db_path)
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS voluson_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_key TEXT,
                voluson_patient_id TEXT,
                patient_name TEXT,
                exam_date TEXT,
                exam_ts INTEGER,
                ga_lmp TEXT,
                ga_lmp_days INTEGER,
                ga_aua TEXT,
                ga_aua_days INTEGER,
                lmp TEXT,
                edd_lmp TEXT,
                edd_aua TEXT,
                fetus INTEGER,
                height_cm REAL,
                weight_kg REAL,
                bmi REAL,
                systolic_bp INTEGER,
                diastolic_bp INTEGER,
                efw_g INTEGER,
                efw_percentile REAL,
                efw_range_g INTEGER,
                bpd_mm REAL, bpd_ga TEXT, bpd_percentile REAL,
                ac_mm REAL, ac_ga TEXT, ac_percentile REAL,
                fl_mm REAL, fl_ga TEXT, fl_percentile REAL,
                hc_mm REAL, hc_ga TEXT, hc_percentile REAL,
                fl_ac_ratio REAL,
                fl_bpd_ratio REAL,
                umb_pi REAL, umb_ri REAL, umb_sd REAL,
                umb_ps REAL, umb_ed REAL, umb_tamax REAL, umb_md REAL,
                fetal_hr INTEGER,
                clinical_flags TEXT,
                pdf_path TEXT UNIQUE,
                pdf_filename TEXT,
                raw_json TEXT,
                imported_ts INTEGER NOT NULL
            )
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_voluson_hasta
            ON voluson_reports(patient_key, exam_ts DESC)
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_voluson_pid
            ON voluson_reports(voluson_patient_id, exam_ts DESC)
        """)
        con.commit()
    finally:
        con.close()


def match_patient(data, db_path=None):
    """patients tablosunda eslesen kaydi bul (folder_key TEXT PK).

    patients formatı: folder_key = "F137230-26-03-09-1_Kilic_Seval",
                      display_name = "Kilic Seval" (TR sirali)
    PDF formati:       patient_id = "F137230-26-03-09-1",
                       name = "Kilic, Seval"

    Strateji (oncelik sirasi):
      1) PDF dosya yolundaki klasor adi == folder_key (en guvenli)
      2) folder_key prefix == patient_id (orn "F137230-..." baslangic)
      3) display_name normalize == PDF name normalize (her iki sira denenir)

    Returns: folder_key (str) veya None.
    """
    con = _db_conn(db_path)
    try:
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name = 'patients'").fetchall()]
        if not tables:
            return None
        # 1) PDF yolu klasor adindan folder_key cikar
        pdf_path = data.get("pdf_path", "")
        if pdf_path:
            # E:\USG\Hastalar\<folder_key>\<date>\IMG_...pdf
            parts = pdf_path.replace("\\", "/").split("/")
            for p in reversed(parts):
                if p and "_" in p and p.startswith("F"):
                    candidate = p
                    r = con.execute(
                        "SELECT folder_key FROM patients WHERE folder_key = ?",
                        (candidate,)).fetchone()
                    if r:
                        return r[0]
                    break
        # 2) PDF patient_id ile folder_key prefix match
        vp_id = data.get("patient_id")
        if vp_id:
            r = con.execute(
                "SELECT folder_key FROM patients WHERE folder_key LIKE ? "
                "AND archived_at IS NULL LIMIT 1",
                (vp_id + "_%",)).fetchone()
            if r:
                return r[0]
        # 3) Ad eslesme (case-insensitive)
        name_raw = data.get("name", "") or ""
        if "," in name_raw:
            ln, fn = [p.strip() for p in name_raw.split(",", 1)]
            for variant in (f"{ln} {fn}", f"{fn} {ln}"):
                r = con.execute(
                    "SELECT folder_key FROM patients "
                    "WHERE LOWER(display_name) = LOWER(?) "
                    "AND archived_at IS NULL LIMIT 1",
                    (variant,)).fetchone()
                if r:
                    return r[0]
        return None
    except Exception as exc:
        print(f"[VOLUSON] match_patient HATA: {exc}")
        return None
    finally:
        con.close()


def import_pdf(pdf_path, db_path=None, force=False):
    """Tek PDF: parse + DB'ye yaz. Daha once import edildiyse skip (force=False).

    Returns: dict {imported: bool, id, matched_patient_key, data, reason}
    """
    init_db(db_path)
    con = _db_conn(db_path)
    try:
        # Skip mevcut?
        if not force:
            r = con.execute("SELECT id FROM voluson_reports WHERE pdf_path = ?",
                            (pdf_path,)).fetchone()
            if r:
                return {"imported": False, "id": r[0],
                        "reason": "daha once import edildi"}
        # Parse
        try:
            data = parse_voluson_pdf(pdf_path)
        except Exception as exc:
            return {"imported": False, "reason": f"parse HATA: {exc}"}
        # FILTRE: Voluson sistem/probe dosyalari (gercek hasta degil)
        spurious_names = {"Lyric Architecture", "fetalHQ", "Vscan Air",
                          "RIC10 / RIC5-9", "IC9-RS", "Curve", "Linear",
                          "Volume", "BT9-RS", "C1-6", "RIC6-12-D"}
        pn = (data.get("name") or "").strip()
        pid = (data.get("patient_id") or "").strip()
        if pn in spurious_names or not pn or not pid:
            return {"imported": False, "reason": f"spurious/empty: name={pn!r} pid={pid!r}"}
        # patient_id Voluson formati F<machine>-<date>-<seq> degilse skip
        if not pid.startswith("F") or len(pid) < 8:
            return {"imported": False, "reason": f"invalid patient_id: {pid!r}"}
        # Hasta eslestir
        patient_key = match_patient(data, db_path)
        data["patient_key"] = patient_key
        # Insert
        cols_vals = {
            "patient_key": patient_key,
            "voluson_patient_id": data.get("patient_id"),
            "patient_name": data.get("name"),
            "exam_date": data.get("exam_date"),
            "exam_ts": data.get("exam_ts"),
            "ga_lmp": data.get("ga_lmp"),
            "ga_lmp_days": data.get("ga_lmp_days"),
            "ga_aua": data.get("ga_aua"),
            "ga_aua_days": data.get("ga_aua_days"),
            "lmp": data.get("lmp"),
            "edd_lmp": data.get("edd_lmp"),
            "edd_aua": data.get("edd_aua"),
            "fetus": data.get("fetus"),
            "height_cm": data.get("height_cm"),
            "weight_kg": data.get("weight_kg"),
            "bmi": data.get("bmi"),
            "systolic_bp": data.get("systolic_bp"),
            "diastolic_bp": data.get("diastolic_bp"),
            "efw_g": data.get("efw_g"),
            "efw_percentile": data.get("efw_percentile"),
            "efw_range_g": data.get("efw_range_g"),
            "bpd_mm": data.get("bpd_mm"),
            "bpd_ga": data.get("bpd_ga"),
            "bpd_percentile": data.get("bpd_percentile"),
            "ac_mm": data.get("ac_mm"),
            "ac_ga": data.get("ac_ga"),
            "ac_percentile": data.get("ac_percentile"),
            "fl_mm": data.get("fl_mm"),
            "fl_ga": data.get("fl_ga"),
            "fl_percentile": data.get("fl_percentile"),
            "hc_mm": data.get("hc_mm"),
            "hc_ga": data.get("hc_ga"),
            "hc_percentile": data.get("hc_percentile"),
            "fl_ac_ratio": data.get("fl_ac_ratio"),
            "fl_bpd_ratio": data.get("fl_bpd_ratio"),
            "umb_pi": data.get("umb_pi"),
            "umb_ri": data.get("umb_ri"),
            "umb_sd": data.get("umb_sd"),
            "umb_ps": data.get("umb_ps"),
            "umb_ed": data.get("umb_ed"),
            "umb_tamax": data.get("umb_tamax"),
            "umb_md": data.get("umb_md"),
            "fetal_hr": data.get("fetal_hr"),
            "clinical_flags": json.dumps(data.get("clinical_flags") or [],
                                         ensure_ascii=False),
            "pdf_path": pdf_path,
            "pdf_filename": data.get("pdf_filename"),
            "raw_json": json.dumps(
                {k: v for k, v in data.items() if k != "raw_text"},
                ensure_ascii=False, default=str),
            "imported_ts": data.get("imported_ts"),
        }
        cols = ", ".join(cols_vals.keys())
        placeholders = ", ".join("?" * len(cols_vals))
        cur = con.execute(
            f"INSERT INTO voluson_reports ({cols}) VALUES ({placeholders})",
            list(cols_vals.values()))

        # === D300 2026-05-16: Hasta dosyasi kopru ===
        # voluson_reports'a yaziyoruz; ayni transactionda visits ve
        # patient_demographics'a da yaz ki "Gelisler" sayfasinda ve
        # hasta demografiklerinde yas/kilo/boy/TA gozuksun.
        sync_info = {}
        try:
            sync_info = _sync_to_patient_records(
                con, data, patient_key, pdf_path)
        except Exception as exc:
            sync_info = {"reason": f"sync hata: {exc}"}

        con.commit()
        return {"imported": True, "id": cur.lastrowid,
                "matched_patient_key": patient_key,
                "patient_name": data.get("name"),
                "ga_aua": data.get("ga_aua"),
                "efw_g": data.get("efw_g"),
                "flags": data.get("clinical_flags"),
                "visit_written": sync_info.get("visit_written"),
                "demographics_updated": sync_info.get("demographics_updated"),
                "sync_reason": sync_info.get("reason") or ""}
    finally:
        con.close()


def scan_and_import(root_dir, db_path=None, force=False):
    """Root klasor altindaki tum *_Rep_OB.pdf (veya *.pdf) dosyalarini tara.

    Voluson NAS yapisi tipik: ROOT/Hastalar/F<id>_<Ad>_<Soyad>/<YYYYMMDD>/IMG_*.pdf
    """
    init_db(db_path)
    stats = {"scanned": 0, "imported": 0, "skipped": 0,
             "errors": [], "items": []}
    if not os.path.isdir(root_dir):
        stats["errors"].append(f"klasor yok: {root_dir}")
        return stats
    for cur_root, dirs, files in os.walk(root_dir):
        for f in files:
            if not f.lower().endswith(".pdf"):
                continue
            stats["scanned"] += 1
            p = os.path.join(cur_root, f)
            try:
                r = import_pdf(p, db_path=db_path, force=force)
                if r.get("imported"):
                    stats["imported"] += 1
                    stats["items"].append({
                        "pdf": p, "id": r["id"],
                        "name": r.get("patient_name"),
                        "matched": r.get("matched_patient_key"),
                        "ga": r.get("ga_aua"),
                        "efw_g": r.get("efw_g"),
                    })
                else:
                    stats["skipped"] += 1
            except Exception as exc:
                stats["errors"].append(f"{p}: {exc}")
    return stats


def patient_recent_usg(patient_key, limit=3, db_path=None):
    """Hastanin (patient_key = folder_key) son USG olcumlerini don."""
    init_db(db_path)
    con = _db_conn(db_path)
    try:
        cur = con.execute(
            "SELECT id, exam_date, ga_aua, ga_lmp, efw_g, efw_percentile, "
            "bpd_mm, bpd_percentile, ac_mm, ac_percentile, "
            "fl_mm, fl_percentile, fetal_hr, umb_pi, umb_ri, "
            "clinical_flags, pdf_path "
            "FROM voluson_reports WHERE patient_key = ? "
            "ORDER BY exam_ts DESC LIMIT ?",
            (str(patient_key), int(limit)))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()


def patient_recent_usg_by_voluson_id(voluson_id, limit=3, db_path=None):
    """Voluson patient_id ile (henuz hasta DB'sine baglanmamis USG'leri de bulur)."""
    init_db(db_path)
    con = _db_conn(db_path)
    try:
        cur = con.execute(
            "SELECT id, exam_date, ga_aua, ga_lmp, efw_g, efw_percentile, "
            "bpd_mm, bpd_percentile, ac_mm, ac_percentile, "
            "fl_mm, fl_percentile, fetal_hr, umb_pi, umb_ri, "
            "clinical_flags, pdf_path, patient_name "
            "FROM voluson_reports WHERE voluson_patient_id = ? "
            "ORDER BY exam_ts DESC LIMIT ?",
            (str(voluson_id), int(limit)))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        con.close()


def format_usg_for_prompt(usg_list):
    """USG dict listesini Alex prompt'una uygun ozet stringi."""
    if not usg_list:
        return ""
    lines = []
    for u in usg_list:
        parts = [f"[{u.get('exam_date','?')} USG]"]
        if u.get("ga_aua"):
            parts.append(f"GA {u['ga_aua']}")
        if u.get("efw_g"):
            ep = f" ({u['efw_percentile']:.1f}p)" if u.get("efw_percentile") else ""
            parts.append(f"EFW {u['efw_g']}g{ep}")
        if u.get("bpd_mm"):
            parts.append(f"BPD {u['bpd_mm']:.1f}mm")
        if u.get("ac_mm"):
            parts.append(f"AC {u['ac_mm']:.1f}mm")
        if u.get("fl_mm"):
            parts.append(f"FL {u['fl_mm']:.1f}mm")
        if u.get("fetal_hr"):
            parts.append(f"FHR {u['fetal_hr']}bpm")
        if u.get("umb_pi"):
            parts.append(f"UmbPI {u['umb_pi']:.2f}")
        try:
            flags = json.loads(u.get("clinical_flags") or "[]")
            if flags:
                parts.append("flags: " + "; ".join(flags))
        except Exception:
            pass
        lines.append(" ".join(parts))
    return "\n".join(lines)


# ============================================================================
# CLI
# ============================================================================

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == "scan":
        root = sys.argv[2] if len(sys.argv) > 2 else r"E:\USG\Hastalar"
        print(f"Scan baslatildi: {root}")
        stats = scan_and_import(root)
        print(f"Tarandi: {stats['scanned']}, Import: {stats['imported']}, "
              f"Atlandi: {stats['skipped']}, Hata: {len(stats['errors'])}")
        for it in stats["items"][:20]:
            print(f"  + {it.get('name')} (GA {it.get('ga')}, "
                  f"EFW {it.get('efw_g')}g) patient_key={it.get('matched')}")
        for e in stats["errors"][:5]:
            print(f"  ! {e}")
    elif cmd == "import":
        pdf = sys.argv[2]
        r = import_pdf(pdf, force=("--force" in sys.argv))
        print(json.dumps(r, ensure_ascii=False, indent=2, default=str))
    else:
        # tek dosya parse
        pdf = cmd
        data = parse_voluson_pdf(pdf)
        # raw_text'i ozet basla
        data["raw_text"] = (data.get("raw_text") or "")[:200] + "..."
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
