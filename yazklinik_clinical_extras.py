# -*- coding: utf-8 -*-
"""
YazKlinik Clinical Extras - 7 yeni OB-GYN feature
==================================================
D700 v17 2026-05-17. Tek dosya, Flask Blueprint, hepsi self-contained.

Feature listesi:
1. /fetal-buyume       - Fetal Buyume Grafigi (Hadlock + Intergrowth percentile)
2. /servikal-uzunluk   - Servikal Uzunluk Takipcisi (preterm risk)
3. /postpartum-takvim  - Postpartum Otomatik Takvim (6w kontrol + PHQ-9)
4. /randevu-al         - Public Online Randevu Sayfasi (login YOK)
5. /partner-link       - Aile/Es Erisimi (magic-link partner kopya)
6. /kasa-dashboard     - Gunluk Kasa (gelir + tahsilat)
7. /triaj-bot          - AI Triaj Bot (paste WA mesaji -> aciliyet skoru)

Tum dosya read-only mevcut tablolari kullanir, sadece bir migration:
  - cervical_measurements (yeni tablo)
"""
from __future__ import annotations
import os
import json
import sqlite3
import secrets
import math
from datetime import datetime, timedelta, date
from typing import Optional, Dict, Any, List

from flask import (
    Blueprint, request, jsonify, render_template_string,
    redirect, url_for, session
)

clinical_bp = Blueprint("clinical_extras", __name__)


DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")


def _db():
    # PG-primary aware: routes to PostgreSQL via the adapter when cutover is active.
    import yazklinik_db_adapter as _adapter
    con = _adapter.agent_connection("clinical_extras")
    con.row_factory = sqlite3.Row
    return con


def _require_doctor():
    """Doktor login sart - aksi takdirde 302 /giris."""
    u = session.get("user") or session.get("username")
    if not u:
        return redirect(url_for("login_page") if False else "/giris")
    return None


def _safe_redirect_login():
    return redirect("/giris")


# ============================================================
# MIGRATION: cervical_measurements tablosu
# ============================================================
def _ensure_tables():
    con = _db()
    try:
        con.execute("""
            CREATE TABLE IF NOT EXISTS cervical_measurements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_key TEXT NOT NULL,
                measure_date TEXT NOT NULL,
                ga_weeks REAL,
                cl_mm REAL NOT NULL,
                method TEXT,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_cl_patient
            ON cervical_measurements(patient_key, measure_date DESC)
        """)
        # Postpartum auto-scheduling izleme
        con.execute("""
            CREATE TABLE IF NOT EXISTS postpartum_schedule_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_key TEXT NOT NULL,
                delivery_date TEXT NOT NULL,
                scheduled_at TEXT DEFAULT CURRENT_TIMESTAMP,
                appointments_created INTEGER DEFAULT 0,
                notes TEXT
            )
        """)
        # Public randevu istekleri (henuz dogrulanmamis)
        con.execute("""
            CREATE TABLE IF NOT EXISTS public_appointment_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tc TEXT,
                ad TEXT NOT NULL,
                soyad TEXT NOT NULL,
                phone TEXT NOT NULL,
                tercih_tarih TEXT,
                tercih_saat TEXT,
                sikayet TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                processed_at TEXT,
                status TEXT DEFAULT 'pending',
                appointment_id INTEGER,
                ip TEXT
            )
        """)
        # AI triaj sonuclari
        con.execute("""
            CREATE TABLE IF NOT EXISTS triaj_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                message TEXT NOT NULL,
                urgency INTEGER,
                category TEXT,
                ai_response TEXT,
                user_key TEXT
            )
        """)
        # D700 v17 round2: 7 yeni feature tablolari
        con.execute("""
            CREATE TABLE IF NOT EXISTS patient_tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_key TEXT NOT NULL,
                tag TEXT NOT NULL,
                color TEXT DEFAULT '#1769aa',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                UNIQUE(patient_key, tag)
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS patient_recalls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                patient_key TEXT NOT NULL,
                recall_date TEXT NOT NULL,
                purpose TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                created_by TEXT,
                completed_at TEXT,
                notes TEXT
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS visit_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                category TEXT,
                body TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                use_count INTEGER DEFAULT 0
            )
        """)
        # Pre-seed default templates
        default_templates = [
            ("Ilk Gebe Muayenesi", "obstetric",
             "TANSIYON: ___/___ mmHg\nKILO: ___ kg (boy ___ cm, BMI ___)\nLMP: ___\nGA: ___ hafta\nUSG: GS gozlendi, FH+, CRL ___ mm\nLAB ISTEK: TKS, AKS, TSH, kan grubu, idrar, HIV, HBsAg, VDRL, rubella IgG\nONERILER:\n- Folbiol 5mg 1x1\n- 4 hf sonra kontrol\n- Beslenme bilgilendirildi"),
            ("Rutin Gebelik Kontrolu", "obstetric",
             "TANSIYON: ___/___ mmHg\nKILO: ___ kg (artis ___ kg)\nGA: ___ hafta\nFETAL: hareket var, FHR ___\nUSG (varsa): BPD ___, HC ___, AC ___, FL ___, EFW ___\nLAB: ___\nONERILER: bir sonraki kontrol ___ hf sonra"),
            ("Postpartum 6. Hafta Kontrol", "postpartum",
             "DOGUM TARIHI: ___\nDOGUM TIPI: NSVD / C/S\nLAKTASYON: ___\nLOSHIA: bitti / devam\nDEPRESYON (PHQ-9): ___\nKONTRASEPSIYON: ___\nMUAYENE: serviks kapali, uterus involusyon iyi\nONERI: Pap smear randevusu, kontrasepsiyon plani"),
            ("Smear/HPV Sonuc Gorusmesi", "gynecology",
             "Smear sonucu: ___\nHPV: ___\nGorusme: hasta bilgilendirildi\nPLAN (ASCCP):\n- 12 ay sonra co-test / kolposkopi\nONERI: ___"),
            ("Menopoz Konsultasyonu", "gynecology",
             "Yas: ___\nSon adet: ___\nSEMPTOM: vazomotor, vajinal, uyku, kemik\nFRAX skoru: ___\nDXA: ___\nHRT degerlendirme: endikasyon var/yok\nONERI: kalsiyum+D, egzersiz, ___ ay sonra kontrol"),
            ("IVF Hazirlik Konsultasyonu", "fertility",
             "Yas: ___\nInfertilite suresi: ___ yil\nAMH: ___\nFSH/LH: ___\nUSG (AFC): ___ folicle\nERKEK FAKTOR: spermiogram ___\nPLAN:\n- ___ ay deneme\n- Folbiol, D vit\n- IVF programi: long/short/antagonist"),
            ("Tibbi Estetik Ilk Konsultasyon", "aesthetic",
             "TALEP: ___\nDERMATOLOJIK MUAYENE: ___\nMEDIKAL HASTALIK: yok\nALERJI: ___\nKULLANILAN ILAC: ___\nONERI: ___\nFIYAT: ___ TL\nRANDEVU: ___"),
            ("PCOS Degerlendirme", "gynecology",
             "Yas: ___\nADET: duzensiz / amenore (___ ay)\nHIRSUTISM: Ferriman-Gallwey ___\nUSG: bilateral polycystic over (___ folicle)\nLAB: LH/FSH ratio, AMH, total/free testosteron, DHEAS, OGTT, insulin\nROTTERDAM KRITER: ___/3\nTANI: PCOS evet/hayir\nTEDAVI: metformin / OCP / spironolactone / lifestyle"),
        ]
        for name, cat, body in default_templates:
            try:
                con.execute(
                    "INSERT OR IGNORE INTO visit_templates (name, category, body) VALUES (?, ?, ?)",
                    (name, cat, body))
            except Exception:
                pass
        con.commit()
    except Exception as e:
        print(f"[clinical_extras] migration err: {e}")
    finally:
        con.close()


# Module load anlik migration
_ensure_tables()


# ============================================================
# 1. FETAL BUYUME GRAFIGI (Hadlock + Intergrowth-21st)
# ============================================================

# Intergrowth-21st referans degerleri (haftalik, p3/p50/p97)
# Kaynak: WHO/Intergrowth-21st published standards, simplified
# Format: { gw: { metric: (p3, p50, p97) } }
# Sadece anlamli haftalik: 14-40 GW
INTERGROWTH = {
    # GW: BPD(mm) HC(mm) AC(mm) FL(mm) EFW(g)
    14: {"BPD": (25, 28, 32), "HC": (89, 99, 109), "AC": (75, 87, 100), "FL": (12, 15, 18), "EFW": (75, 93, 115)},
    16: {"BPD": (32, 36, 40), "HC": (118, 130, 142), "AC": (98, 113, 130), "FL": (18, 22, 26), "EFW": (122, 146, 175)},
    18: {"BPD": (39, 43, 48), "HC": (146, 159, 174), "AC": (123, 142, 162), "FL": (24, 28, 33), "EFW": (190, 222, 260)},
    20: {"BPD": (45, 50, 55), "HC": (170, 186, 203), "AC": (146, 168, 192), "FL": (29, 34, 39), "EFW": (278, 320, 370)},
    22: {"BPD": (51, 56, 61), "HC": (193, 211, 230), "AC": (167, 192, 220), "FL": (34, 39, 45), "EFW": (388, 444, 510)},
    24: {"BPD": (57, 62, 68), "HC": (216, 235, 256), "AC": (188, 216, 247), "FL": (39, 45, 51), "EFW": (520, 595, 681)},
    26: {"BPD": (62, 68, 74), "HC": (236, 256, 279), "AC": (208, 240, 274), "FL": (44, 50, 56), "EFW": (680, 778, 891)},
    28: {"BPD": (68, 74, 80), "HC": (252, 274, 297), "AC": (227, 262, 300), "FL": (49, 55, 61), "EFW": (881, 1006, 1153)},
    30: {"BPD": (72, 79, 85), "HC": (267, 289, 312), "AC": (245, 283, 324), "FL": (53, 59, 66), "EFW": (1133, 1294, 1481)},
    32: {"BPD": (77, 83, 90), "HC": (280, 302, 326), "AC": (262, 303, 348), "FL": (57, 63, 70), "EFW": (1437, 1639, 1878)},
    34: {"BPD": (81, 87, 94), "HC": (290, 313, 337), "AC": (278, 322, 369), "FL": (60, 66, 73), "EFW": (1791, 2042, 2336)},
    36: {"BPD": (84, 91, 98), "HC": (298, 321, 345), "AC": (294, 340, 391), "FL": (63, 69, 76), "EFW": (2192, 2500, 2860)},
    38: {"BPD": (87, 94, 101), "HC": (304, 327, 351), "AC": (308, 357, 410), "FL": (66, 72, 79), "EFW": (2628, 3000, 3433)},
    40: {"BPD": (89, 96, 103), "HC": (308, 331, 355), "AC": (321, 372, 428), "FL": (68, 74, 81), "EFW": (3084, 3522, 4029)},
}


def hadlock_efw(bpd_mm, hc_mm, ac_mm, fl_mm):
    """Hadlock 4-parameter formula. mm/g."""
    try:
        bpd = float(bpd_mm or 0) / 10.0  # mm -> cm
        hc = float(hc_mm or 0) / 10.0
        ac = float(ac_mm or 0) / 10.0
        fl = float(fl_mm or 0) / 10.0
        if not (bpd and hc and ac and fl):
            return None
        log_efw = (1.3596 + 0.00064 * hc + 0.00061 * bpd * ac
                   + 0.0424 * ac + 0.174 * fl - 0.00386 * ac * fl)
        return int(10 ** log_efw)
    except Exception:
        return None


def percentile_for(metric: str, ga_weeks: float, value: float) -> Optional[int]:
    """Yaklasik percentile (3/50/97 interpolation)."""
    if not ga_weeks or not value:
        return None
    gw_int = int(round(ga_weeks / 2.0)) * 2  # en yakin cift hafta
    gw_int = max(14, min(40, gw_int))
    if gw_int not in INTERGROWTH or metric not in INTERGROWTH[gw_int]:
        return None
    p3, p50, p97 = INTERGROWTH[gw_int][metric]
    if value <= p3:
        return 3
    if value <= p50:
        # 3-50 arasi linear
        return int(3 + (value - p3) / max(0.1, p50 - p3) * 47)
    if value <= p97:
        return int(50 + (value - p50) / max(0.1, p97 - p50) * 47)
    return 97


@clinical_bp.route("/fetal-buyume", methods=["GET"])
def fetal_buyume_page():
    auth = _require_doctor()
    if auth: return auth
    pid = (request.args.get("patient") or "").strip()
    measurements = []
    patient_name = ""
    if pid:
        con = _db()
        try:
            row = con.execute(
                "SELECT display_name FROM patients WHERE folder_key=?",
                (pid,)).fetchone()
            if row:
                patient_name = row[0] or pid
            rows = con.execute(
                "SELECT usg_date, ga_weeks, bpd, hc, ac, fl, efw, fhr "
                "FROM usg_measurements WHERE patient_key=? "
                "ORDER BY usg_date ASC LIMIT 50",
                (pid,)).fetchall()
            for r in rows:
                d = dict(r)
                # Eger EFW yoksa Hadlock ile hesapla
                if not d.get("efw") and d.get("bpd") and d.get("hc") and d.get("ac") and d.get("fl"):
                    d["efw"] = hadlock_efw(d["bpd"], d["hc"], d["ac"], d["fl"])
                # Percentile hesapla
                d["percentiles"] = {}
                ga = d.get("ga_weeks") or 0
                for m in ("BPD", "HC", "AC", "FL", "EFW"):
                    val = d.get(m.lower())
                    if val and ga:
                        d["percentiles"][m] = percentile_for(m, ga, val)
                measurements.append(d)
        finally:
            con.close()
    # Patient picker icin tum hastalar
    all_patients = []
    try:
        con = _db()
        rows = con.execute(
            "SELECT folder_key, display_name FROM patients "
            "WHERE archived_at IS NULL ORDER BY updated_at DESC LIMIT 2000"
        ).fetchall()
        all_patients = [{"k": r[0], "n": r[1] or r[0]} for r in rows]
        con.close()
    except Exception:
        pass
    return render_template_string(
        _FETAL_BUYUME_PAGE,
        pid=pid, patient_name=patient_name,
        measurements_json=json.dumps(measurements, ensure_ascii=False),
        intergrowth_json=json.dumps(INTERGROWTH, ensure_ascii=False),
        all_patients_json=json.dumps(all_patients, ensure_ascii=False).replace("</", "<\\/")
    )


_FETAL_BUYUME_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Fetal Buyume Grafigi</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:1100px;margin:0 auto;padding:18px;background:#f5f8fb;color:#122236}
h1{color:#0d4f8b;margin-bottom:6px}
.card{background:#fff;border:1px solid #cdd9e3;border-radius:12px;padding:16px;margin-bottom:14px;box-shadow:0 2px 6px rgba(0,0,0,0.04)}
.search{padding:12px;border:2px solid #1769aa;border-radius:8px;font-size:15px;width:100%}
.dd{display:none;position:relative;background:#fff;border:2px solid #1769aa;border-radius:8px;max-height:300px;overflow-y:auto;margin-top:4px;z-index:50}
.dd a{display:block;padding:10px 14px;border-bottom:1px solid #eef;text-decoration:none;color:#0d4f8b}
.dd a:hover{background:#eff5fb}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:14px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#eff5fb;padding:6px;text-align:left;border-bottom:2px solid #cdd9e3}
td{padding:6px;border-bottom:1px solid #eef}
.pctl{display:inline-block;padding:2px 7px;border-radius:10px;font-size:11px;font-weight:700}
.pctl-low{background:#fee2e2;color:#b3261e}
.pctl-mid{background:#dcfce7;color:#166534}
.pctl-high{background:#fef3c7;color:#92400e}
small{color:#5e7185}
</style></head><body>
<h1>Fetal Buyume Grafigi</h1>
<div style="color:#5e7185;margin-bottom:14px">Voluson USG olculerini Intergrowth-21st percentil egrisinde gosterir. IUGR/makrozomi erken tespit.</div>

<div class="card">
  <label style="font-weight:700;color:#0d4f8b">Hasta sec (2 harf yeter):</label>
  <input type="search" id="searchBox" class="search" placeholder="Hasta adi yaz..." autocomplete="off"
         value="{{patient_name}}">
  <div id="dropdown" class="dd"></div>
</div>

{% if pid and measurements_json != '[]' %}
<div class="card">
  <h3 style="margin-top:0;color:#0d4f8b">{{patient_name}} - Olcumler ({{measurements_json|length}} kayit)</h3>
  <table>
    <thead><tr><th>Tarih</th><th>GA (hf)</th><th>BPD</th><th>HC</th><th>AC</th><th>FL</th><th>EFW (g)</th><th>FHR</th></tr></thead>
    <tbody id="measureTable"></tbody>
  </table>
</div>

<div class="grid">
  <div class="card"><h3 style="margin-top:0;color:#1769aa">BPD (Biparietal Diameter)</h3><canvas id="chartBPD" height="180"></canvas></div>
  <div class="card"><h3 style="margin-top:0;color:#1769aa">HC (Head Circumference)</h3><canvas id="chartHC" height="180"></canvas></div>
  <div class="card"><h3 style="margin-top:0;color:#1769aa">AC (Abdominal Circumference)</h3><canvas id="chartAC" height="180"></canvas></div>
  <div class="card"><h3 style="margin-top:0;color:#1769aa">FL (Femur Length)</h3><canvas id="chartFL" height="180"></canvas></div>
  <div class="card"><h3 style="margin-top:0;color:#1769aa">EFW (Estimated Fetal Weight)</h3><canvas id="chartEFW" height="180"></canvas></div>
</div>
{% elif pid %}
<div class="card" style="text-align:center;color:#5e7185;padding:40px">Bu hasta icin USG olcumu yok.</div>
{% endif %}

<p style="margin-top:14px"><a href="/">&lt;- Ana sayfa</a></p>

<script>
const AC_PATIENTS = {{all_patients_json|safe}};
const MEASUREMENTS = {{measurements_json|safe}};
const INTERGROWTH = {{intergrowth_json|safe}};

// Autocomplete (Hasta Portal patern)
function fold(s){return String(s||'').toLowerCase().replace(/[Ä±Ä°iI]/g,'i').replace(/[ÅŸÅSs]/g,'s').replace(/[ÄŸÄGg]/g,'g').replace(/[Ã¼ÃœUu]/g,'u').replace(/[Ã¶Ã–Oo]/g,'o').replace(/[Ã§Ã‡Cc]/g,'c');}
const IDX = AC_PATIENTS.map(p => ({k:p.k, n:p.n, h:fold(p.n+' '+p.k)}));
const box = document.getElementById('searchBox');
const dd = document.getElementById('dropdown');
let acTimer = null;
function runAc(){
  const q = (box.value||'').trim();
  if (q.length < 2) { dd.style.display='none'; return; }
  const qf = fold(q);
  const words = qf.split(/\s+/).filter(Boolean);
  const out = [];
  for (const p of IDX) {
    let ok = true; for (const w of words) if (!p.h.includes(w)) { ok=false; break; }
    if (ok) out.push(p);
    if (out.length > 15) break;
  }
  if (!out.length) { dd.innerHTML = '<div style="padding:14px;color:#5e7185">Hasta yok</div>'; dd.style.display='block'; return; }
  dd.innerHTML = out.map(p => '<a href="/fetal-buyume?patient=' + encodeURIComponent(p.k) + '">' + p.n + '</a>').join('');
  dd.style.display = 'block';
}
box.addEventListener('input', () => { if (acTimer) clearTimeout(acTimer); acTimer = setTimeout(runAc, 80); });
document.addEventListener('click', ev => { if (ev.target !== box && !dd.contains(ev.target)) dd.style.display='none'; });

// Tablo render + chart
if (MEASUREMENTS.length) {
  const tbody = document.getElementById('measureTable');
  tbody.innerHTML = MEASUREMENTS.map(m => {
    const pct = m.percentiles || {};
    const pctLbl = (v) => {
      if (!v) return '-';
      const cls = v < 10 || v > 90 ? 'pctl-low' : (v >= 25 && v <= 75 ? 'pctl-mid' : 'pctl-high');
      return '<span class="pctl ' + cls + '">' + v + 'p</span>';
    };
    return '<tr><td>' + (m.usg_date||'') + '</td>' +
           '<td>' + (m.ga_weeks||'-') + '</td>' +
           '<td>' + (m.bpd||'-') + ' ' + pctLbl(pct.BPD) + '</td>' +
           '<td>' + (m.hc||'-') + ' ' + pctLbl(pct.HC) + '</td>' +
           '<td>' + (m.ac||'-') + ' ' + pctLbl(pct.AC) + '</td>' +
           '<td>' + (m.fl||'-') + ' ' + pctLbl(pct.FL) + '</td>' +
           '<td>' + (m.efw||'-') + ' ' + pctLbl(pct.EFW) + '</td>' +
           '<td>' + (m.fhr||'-') + '</td></tr>';
  }).join('');

  function buildChart(canvasId, metric, color) {
    const labels = []; const p3 = []; const p50 = []; const p97 = []; const userPoints = [];
    for (let gw = 14; gw <= 40; gw += 2) {
      labels.push(gw + 'w');
      const ref = INTERGROWTH[gw] && INTERGROWTH[gw][metric];
      p3.push(ref ? ref[0] : null);
      p50.push(ref ? ref[1] : null);
      p97.push(ref ? ref[2] : null);
    }
    const userVals = labels.map((_, idx) => {
      const gw = 14 + idx * 2;
      const hit = MEASUREMENTS.find(m => m.ga_weeks && Math.round(m.ga_weeks/2)*2 === gw);
      return hit ? hit[metric.toLowerCase()] : null;
    });
    new Chart(document.getElementById(canvasId), {
      type: 'line',
      data: { labels: labels, datasets: [
        {label: '3p', data: p3, borderColor: '#fbbf24', borderDash:[4,4], pointRadius:0, fill:false, tension:0.4},
        {label: '50p', data: p50, borderColor: '#10b981', borderWidth:2, pointRadius:0, fill:false, tension:0.4},
        {label: '97p', data: p97, borderColor: '#fbbf24', borderDash:[4,4], pointRadius:0, fill:false, tension:0.4},
        {label: 'Hasta', data: userVals, borderColor: '#dc2626', backgroundColor:'#dc2626', borderWidth:3, pointRadius:6, fill:false, spanGaps:true}
      ]},
      options: {responsive:true, plugins:{legend:{position:'bottom'}}, scales:{y:{title:{display:true,text:metric}}}}
    });
  }
  buildChart('chartBPD', 'BPD', '#1769aa');
  buildChart('chartHC', 'HC', '#1769aa');
  buildChart('chartAC', 'AC', '#1769aa');
  buildChart('chartFL', 'FL', '#1769aa');
  buildChart('chartEFW', 'EFW', '#1769aa');
}
</script></body></html>
"""


# ============================================================
# 2. SERVIKAL UZUNLUK TAKIPCISI
# ============================================================
@clinical_bp.route("/servikal-uzunluk", methods=["GET", "POST"])
def servikal_uzunluk_page():
    auth = _require_doctor()
    if auth: return auth
    pid = (request.args.get("patient") or request.form.get("patient") or "").strip()

    if request.method == "POST" and pid:
        cl_mm = request.form.get("cl_mm", "").strip()
        ga = request.form.get("ga_weeks", "").strip()
        notes = request.form.get("notes", "").strip()
        method = request.form.get("method", "transvaginal").strip()
        try:
            cl_f = float(cl_mm)
            ga_f = float(ga) if ga else None
            con = _db()
            try:
                con.execute(
                    "INSERT INTO cervical_measurements "
                    "(patient_key, measure_date, ga_weeks, cl_mm, method, notes) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (pid, datetime.now().strftime("%Y-%m-%d"), ga_f, cl_f, method, notes))
                con.commit()
            finally:
                con.close()
        except Exception:
            pass
        return redirect(f"/servikal-uzunluk?patient={pid}")

    rows = []
    patient_name = ""
    if pid:
        con = _db()
        try:
            r = con.execute("SELECT display_name FROM patients WHERE folder_key=?", (pid,)).fetchone()
            if r: patient_name = r[0] or pid
            rs = con.execute(
                "SELECT measure_date, ga_weeks, cl_mm, method, notes "
                "FROM cervical_measurements WHERE patient_key=? "
                "ORDER BY measure_date ASC", (pid,)).fetchall()
            rows = [dict(x) for x in rs]
        finally:
            con.close()

    all_patients = []
    try:
        con = _db()
        rs = con.execute(
            "SELECT folder_key, display_name FROM patients "
            "WHERE archived_at IS NULL ORDER BY updated_at DESC LIMIT 2000").fetchall()
        all_patients = [{"k": r[0], "n": r[1] or r[0]} for r in rs]
        con.close()
    except Exception:
        pass
    return render_template_string(
        _SERVIKAL_PAGE, pid=pid, patient_name=patient_name,
        measurements_json=json.dumps(rows, ensure_ascii=False),
        all_patients_json=json.dumps(all_patients, ensure_ascii=False).replace("</", "<\\/")
    )


_SERVIKAL_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Servikal Uzunluk</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:900px;margin:0 auto;padding:18px;background:#f5f8fb;color:#122236}
h1{color:#0d4f8b}
.card{background:#fff;border:1px solid #cdd9e3;border-radius:12px;padding:16px;margin-bottom:14px}
.search{padding:12px;border:2px solid #1769aa;border-radius:8px;font-size:15px;width:100%}
.dd{display:none;background:#fff;border:2px solid #1769aa;border-radius:8px;max-height:300px;overflow-y:auto;margin-top:4px;z-index:50}
.dd a{display:block;padding:10px;border-bottom:1px solid #eef;text-decoration:none;color:#0d4f8b}
.dd a:hover{background:#eff5fb}
input,select,textarea{padding:8px;border:1px solid #cdd9e3;border-radius:6px;font-size:14px;width:100%}
.btn{background:#1769aa;color:#fff;border:none;padding:10px 16px;border-radius:6px;font-weight:600;cursor:pointer}
.alarm-red{background:#fee2e2;color:#b3261e;padding:10px;border-radius:8px;font-weight:700;margin-bottom:10px}
.alarm-yellow{background:#fef3c7;color:#92400e;padding:10px;border-radius:8px;font-weight:700;margin-bottom:10px}
.alarm-green{background:#dcfce7;color:#166534;padding:10px;border-radius:8px;font-weight:700;margin-bottom:10px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#eff5fb;padding:6px;text-align:left}
td{padding:6px;border-bottom:1px solid #eef}
</style></head><body>
<h1>Servikal Uzunluk Takipcisi</h1>
<div style="color:#5e7185;margin-bottom:14px">Preterm risk: CL &lt;25mm uyarisi + cerclage/progesteron onerisi.</div>

<div class="card">
  <input type="search" id="searchBox" class="search" placeholder="Hasta ara (2 harf)..." value="{{patient_name}}">
  <div id="dropdown" class="dd"></div>
</div>

{% if pid %}
<div class="card">
  <h3 style="margin-top:0">{{patient_name}}</h3>
  {% if measurements_json != '[]' %}
    {% set last = (measurements_json|from_json)[-1] %}
    {% if last and last.cl_mm < 15 %}
    <div class="alarm-red">KRITIK: CL {{last.cl_mm}}mm &lt; 15mm - CERCLAGE acil degerlendirme</div>
    {% elif last and last.cl_mm < 25 %}
    <div class="alarm-yellow">RISKLI: CL {{last.cl_mm}}mm &lt; 25mm - vajinal progesteron + 2 hafta sonra kontrol</div>
    {% elif last %}
    <div class="alarm-green">NORMAL: CL {{last.cl_mm}}mm - rutin takip</div>
    {% endif %}
  {% endif %}

  <form method="POST" action="/servikal-uzunluk">
    <input type="hidden" name="patient" value="{{pid}}">
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <div style="flex:1;min-width:120px"><label>CL (mm)</label><input type="number" step="0.1" name="cl_mm" required></div>
      <div style="flex:1;min-width:100px"><label>GA (hf)</label><input type="number" step="0.1" name="ga_weeks"></div>
      <div style="flex:1;min-width:140px"><label>Yontem</label><select name="method"><option value="transvaginal">Transvajinal</option><option value="transabdominal">Transabdominal</option></select></div>
    </div>
    <div style="margin-top:8px"><label>Notlar</label><textarea name="notes" rows="2"></textarea></div>
    <button type="submit" class="btn" style="margin-top:10px">Olcumu Kaydet</button>
  </form>
</div>

{% if measurements_json != '[]' %}
<div class="card">
  <h3 style="margin-top:0">Olcum Gecmisi</h3>
  <canvas id="chart" height="120"></canvas>
  <table style="margin-top:14px">
    <thead><tr><th>Tarih</th><th>GA</th><th>CL (mm)</th><th>Yontem</th><th>Not</th></tr></thead>
    <tbody id="histBody"></tbody>
  </table>
</div>
{% endif %}
{% endif %}

<p><a href="/">&lt;- Ana sayfa</a></p>

<script>
const AC = {{all_patients_json|safe}};
const M = {{measurements_json|safe}};
function fold(s){return String(s||'').toLowerCase().replace(/[Ä±Ä°iI]/g,'i').replace(/[ÅŸÅSs]/g,'s').replace(/[ÄŸÄGg]/g,'g').replace(/[Ã¼ÃœUu]/g,'u').replace(/[Ã¶Ã–Oo]/g,'o').replace(/[Ã§Ã‡Cc]/g,'c');}
const IDX = AC.map(p => ({k:p.k, n:p.n, h:fold(p.n+' '+p.k)}));
const box = document.getElementById('searchBox'), dd = document.getElementById('dropdown');
let t = null;
function ac(){
  const q = (box.value||'').trim(); if (q.length < 2) { dd.style.display='none'; return; }
  const qf = fold(q); const ws = qf.split(/\s+/).filter(Boolean); const out = [];
  for (const p of IDX) { let ok=true; for (const w of ws) if (!p.h.includes(w)) {ok=false;break;}
    if (ok) out.push(p); if (out.length>15) break; }
  dd.innerHTML = out.map(p => '<a href="/servikal-uzunluk?patient=' + encodeURIComponent(p.k) + '">' + p.n + '</a>').join('') ||
    '<div style="padding:14px;color:#5e7185">Hasta yok</div>';
  dd.style.display = 'block';
}
box.addEventListener('input', () => { clearTimeout(t); t = setTimeout(ac, 80); });
document.addEventListener('click', ev => { if (ev.target !== box && !dd.contains(ev.target)) dd.style.display='none'; });

if (M.length && document.getElementById('chart')) {
  document.getElementById('histBody').innerHTML = M.map(m =>
    '<tr><td>' + m.measure_date + '</td><td>' + (m.ga_weeks||'-') + '</td>' +
    '<td><b>' + m.cl_mm + 'mm</b></td><td>' + (m.method||'-') + '</td>' +
    '<td>' + (m.notes||'') + '</td></tr>').join('');
  new Chart(document.getElementById('chart'), {
    type: 'line',
    data: {
      labels: M.map(m => m.ga_weeks ? m.ga_weeks + 'w' : m.measure_date),
      datasets: [
        {label:'CL (mm)', data:M.map(m=>m.cl_mm), borderColor:'#1769aa', borderWidth:3, pointRadius:6, fill:false, tension:0.3},
        {label:'25mm esik', data:M.map(()=>25), borderColor:'#fbbf24', borderDash:[6,6], pointRadius:0, fill:false},
        {label:'15mm KRITIK', data:M.map(()=>15), borderColor:'#dc2626', borderDash:[6,6], pointRadius:0, fill:false}
      ]
    },
    options: {responsive:true, plugins:{legend:{position:'bottom'}}, scales:{y:{beginAtZero:false, suggestedMin:0, suggestedMax:50}}}
  });
}
</script></body></html>
"""


# Jinja filter
@clinical_bp.app_template_filter("from_json")
def _from_json(s):
    try: return json.loads(s) if isinstance(s, str) else s
    except Exception: return []


# ============================================================
# 3. POSTPARTUM OTOMATIK TAKVIM
# ============================================================
def _auto_create_postpartum_appts(patient_key: str, delivery_date_str: str) -> int:
    """Dogum sonrasi 3 otomatik randevu olustur. Geri donus: olusturulan sayi."""
    try:
        d = datetime.strptime(delivery_date_str, "%Y-%m-%d")
    except Exception:
        return 0
    appts = [
        (d + timedelta(weeks=6), "10:00", "Postpartum 6. hafta kontrol"),
        (d + timedelta(weeks=6, days=1), "10:30", "PHQ-9 postnatal depresyon tarama"),
        (d + timedelta(weeks=6, days=2), "11:00", "Kontrasepsiyon gorusmesi"),
    ]
    n = 0
    con = _db()
    try:
        # Daha onceden olusturuldu mu kontrol et
        already = con.execute(
            "SELECT id FROM postpartum_schedule_log WHERE patient_key=? AND delivery_date=?",
            (patient_key, delivery_date_str)).fetchone()
        if already:
            return 0
        for ap_d, ap_t, purpose in appts:
            try:
                con.execute(
                    "INSERT INTO appointments (patient_key, appointment_date, appointment_time, "
                    "purpose, status, created_by) VALUES (?, ?, ?, ?, 'scheduled', 'postpartum_auto')",
                    (patient_key, ap_d.strftime("%Y-%m-%d"), ap_t, purpose))
                n += 1
            except Exception:
                pass
        con.execute(
            "INSERT INTO postpartum_schedule_log (patient_key, delivery_date, appointments_created) "
            "VALUES (?, ?, ?)", (patient_key, delivery_date_str, n))
        con.commit()
    finally:
        con.close()
    return n


@clinical_bp.route("/postpartum-takvim", methods=["GET", "POST"])
def postpartum_takvim_page():
    auth = _require_doctor()
    if auth: return auth
    msg = ""
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "schedule":
            pid = request.form.get("patient_key", "")
            dd = request.form.get("delivery_date", "")
            n = _auto_create_postpartum_appts(pid, dd)
            msg = f"{pid}: {n} randevu olusturuldu"
        elif action == "bulk":
            # Tum dogumlar icin (henuz zamanlanmamis)
            con = _db()
            total = 0
            try:
                rows = con.execute(
                    "SELECT d.patient_key, d.delivery_date FROM deliveries d "
                    "LEFT JOIN postpartum_schedule_log s "
                    "  ON s.patient_key=d.patient_key AND s.delivery_date=d.delivery_date "
                    "WHERE s.id IS NULL AND d.delivery_date >= date('now', '-12 months')"
                ).fetchall()
            finally:
                con.close()
            for r in rows:
                total += _auto_create_postpartum_appts(r[0], r[1])
            msg = f"Toplu islem: {len(rows)} dogum, {total} randevu olusturuldu"

    # Liste cek
    con = _db()
    try:
        rows = con.execute(
            "SELECT d.patient_key, d.delivery_date, d.delivery_type, "
            "       p.display_name, s.id as scheduled "
            "FROM deliveries d "
            "LEFT JOIN patients p ON p.folder_key=d.patient_key "
            "LEFT JOIN postpartum_schedule_log s "
            "  ON s.patient_key=d.patient_key AND s.delivery_date=d.delivery_date "
            "WHERE d.delivery_date >= date('now', '-12 months') "
            "ORDER BY d.delivery_date DESC LIMIT 100"
        ).fetchall()
        deliveries = [dict(r) for r in rows]
    finally:
        con.close()
    return render_template_string(_POSTPARTUM_PAGE, msg=msg, deliveries=deliveries)


_POSTPARTUM_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Postpartum Otomatik Takvim</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:1000px;margin:0 auto;padding:18px;background:#f5f8fb}
h1{color:#0d4f8b}
.card{background:#fff;border:1px solid #cdd9e3;border-radius:12px;padding:16px;margin-bottom:14px}
table{width:100%;border-collapse:collapse;font-size:14px}
th{background:#eff5fb;padding:8px;text-align:left}
td{padding:8px;border-bottom:1px solid #eef}
.btn{background:#1769aa;color:#fff;border:none;padding:8px 14px;border-radius:6px;font-weight:600;cursor:pointer}
.btn-big{background:#0a8a76;font-size:15px;padding:12px 20px}
.tag-done{background:#dcfce7;color:#166534;padding:3px 8px;border-radius:10px;font-size:11px;font-weight:700}
.tag-pending{background:#fef3c7;color:#92400e;padding:3px 8px;border-radius:10px;font-size:11px;font-weight:700}
.msg{background:#dcfce7;border-left:4px solid #16815f;padding:10px 14px;border-radius:0 8px 8px 0;margin-bottom:14px}
</style></head><body>
<h1>Postpartum Otomatik Takvim</h1>
<div style="color:#5e7185;margin-bottom:14px">Dogum +6 hafta otomatik 3 randevu: <b>kontrol, PHQ-9 depresyon, kontrasepsiyon</b>.</div>

{% if msg %}<div class="msg">{{msg}}</div>{% endif %}

<div class="card">
  <form method="POST" style="display:inline">
    <input type="hidden" name="action" value="bulk">
    <button type="submit" class="btn btn-big">TUM dogumlar icin TOPLU olustur (henuz zamanlanmamis)</button>
  </form>
</div>

<div class="card">
  <h3 style="margin-top:0">Son 12 ay dogumlari ({{deliveries|length}})</h3>
  <table>
    <thead><tr><th>Hasta</th><th>Dogum Tarihi</th><th>Tip</th><th>Durum</th><th>Aksiyon</th></tr></thead>
    <tbody>
    {% for d in deliveries %}
    <tr>
      <td><a href="/hasta/{{d.patient_key}}">{{d.display_name or d.patient_key}}</a></td>
      <td>{{d.delivery_date}}</td>
      <td>{{d.delivery_type or '-'}}</td>
      <td>{% if d.scheduled %}<span class="tag-done">Olusturuldu</span>{% else %}<span class="tag-pending">Bekliyor</span>{% endif %}</td>
      <td>
        {% if not d.scheduled %}
        <form method="POST" style="display:inline">
          <input type="hidden" name="action" value="schedule">
          <input type="hidden" name="patient_key" value="{{d.patient_key}}">
          <input type="hidden" name="delivery_date" value="{{d.delivery_date}}">
          <button type="submit" class="btn">+ 3 Randevu</button>
        </form>
        {% endif %}
      </td>
    </tr>
    {% else %}
    <tr><td colspan="5" style="text-align:center;padding:30px;color:#5e7185">Son 12 ay dogum yok</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>
<p><a href="/">&lt;- Ana sayfa</a> &middot; <a href="/randevular">Tum Randevular</a></p>
</body></html>
"""


# ============================================================
# 4. PUBLIC ONLINE RANDEVU SAYFASI (login YOK)
# ============================================================
@clinical_bp.route("/randevu-al", methods=["GET", "POST"])
def public_randevu_al():
    """Public sayfa - login GEREKMEZ. Sadece talep alir, doktor onaylar."""
    msg = ""
    err = ""
    if request.method == "POST":
        ad = (request.form.get("ad") or "").strip()
        soyad = (request.form.get("soyad") or "").strip()
        tc = (request.form.get("tc") or "").strip()
        phone = (request.form.get("phone") or "").strip()
        tarih = (request.form.get("tercih_tarih") or "").strip()
        saat = (request.form.get("tercih_saat") or "").strip()
        sikayet = (request.form.get("sikayet") or "").strip()[:400]
        if not (ad and soyad and phone):
            err = "Ad, soyad ve telefon zorunlu."
        elif len(phone) < 10:
            err = "Gecerli bir telefon girin (10+ rakam)."
        else:
            try:
                con = _db()
                con.execute(
                    "INSERT INTO public_appointment_requests "
                    "(tc, ad, soyad, phone, tercih_tarih, tercih_saat, sikayet, ip) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (tc, ad, soyad, phone, tarih, saat, sikayet,
                     request.headers.get("X-Forwarded-For", request.remote_addr)))
                con.commit()
                con.close()
                msg = "Randevu talebiniz alindi. Doktor onaylayinca size WhatsApp ile bilgi gelecek."
            except Exception as e:
                err = f"Sistem hatasi: {e}"
    return render_template_string(_RANDEVU_AL_PAGE, msg=msg, err=err)


_RANDEVU_AL_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Randevu Al - Op. Dr. Hakan Yaz</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:480px;margin:0 auto;padding:20px;background:linear-gradient(135deg,#0d4f8b 0%,#0a8a76 100%);min-height:100vh;color:#122236}
.card{background:#fff;border-radius:14px;padding:24px;box-shadow:0 8px 24px rgba(0,0,0,0.15)}
h1{color:#0d4f8b;font-size:22px;margin-bottom:6px}
.sub{color:#5e7185;font-size:14px;margin-bottom:20px}
label{display:block;font-size:13px;font-weight:600;color:#0d4f8b;margin-bottom:4px;margin-top:12px}
input,select,textarea{width:100%;padding:12px;font-size:16px;border:1px solid #cdd9e3;border-radius:8px;font-family:inherit}
.row{display:flex;gap:8px}
.row > *{flex:1}
.btn{width:100%;background:linear-gradient(135deg,#0d4f8b,#0a8a76);color:#fff;border:none;padding:14px;border-radius:10px;font-size:16px;font-weight:700;margin-top:18px;cursor:pointer}
.msg{background:#dcfce7;color:#166534;padding:14px;border-radius:8px;margin-bottom:14px;font-weight:600}
.err{background:#fee2e2;color:#b3261e;padding:14px;border-radius:8px;margin-bottom:14px;font-weight:600}
small{display:block;color:#5e7185;font-size:11px;margin-top:14px;text-align:center}
</style></head><body>
<div class="card">
<h1>Randevu Al</h1>
<div class="sub"><b>Op. Dr. Hakan Yaz</b> - Kadin Hastaliklari ve Dogum</div>

{% if msg %}<div class="msg">{{msg}}</div>{% endif %}
{% if err %}<div class="err">{{err}}</div>{% endif %}

<form method="POST">
  <div class="row">
    <div><label>Ad *</label><input name="ad" required></div>
    <div><label>Soyad *</label><input name="soyad" required></div>
  </div>
  <label>Telefon (5XX...) *</label>
  <input type="tel" name="phone" required inputmode="tel" placeholder="5XX XXX XX XX">
  <label>TC (opsiyonel)</label>
  <input type="tel" name="tc" maxlength="11" inputmode="numeric">
  <div class="row">
    <div><label>Tercih Tarih</label><input type="date" name="tercih_tarih"></div>
    <div><label>Saat</label><select name="tercih_saat"><option value="">Farketmez</option><option>09:00-12:00</option><option>13:00-17:00</option><option>17:00-19:00</option></select></div>
  </div>
  <label>Sikayet / Talep (opsiyonel)</label>
  <textarea name="sikayet" rows="3" maxlength="400" placeholder="Kontrol, gebe takip, agri vb..."></textarea>
  <button type="submit" class="btn">Randevu Talebi Gonder</button>
</form>
<small>Talebiniz doktor onayina dusecek. Onayla birlikte WhatsApp'tan size kesin tarih/saat iletilecek.</small>
</div>
</body></html>
"""


@clinical_bp.route("/public-randevu-istekleri", methods=["GET"])
def public_randevu_istekleri():
    """Doktor public taleplerini gorur + onaylar."""
    auth = _require_doctor()
    if auth: return auth
    con = _db()
    try:
        rows = con.execute(
            "SELECT * FROM public_appointment_requests "
            "ORDER BY created_at DESC LIMIT 100").fetchall()
        items = [dict(r) for r in rows]
    finally:
        con.close()
    return render_template_string(_PUBLIC_REQS_PAGE, items=items)


_PUBLIC_REQS_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Public Randevu Talepleri</title>
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:1000px;margin:0 auto;padding:18px;background:#f5f8fb}
h1{color:#0d4f8b}
table{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;overflow:hidden}
th{background:#eff5fb;padding:10px;text-align:left;border-bottom:2px solid #cdd9e3}
td{padding:8px;border-bottom:1px solid #eef;font-size:13px;vertical-align:top}
.tag-pending{background:#fef3c7;color:#92400e;padding:2px 8px;border-radius:10px;font-size:11px}
.tag-done{background:#dcfce7;color:#166534;padding:2px 8px;border-radius:10px;font-size:11px}
</style></head><body>
<h1>Public Randevu Talepleri ({{items|length}})</h1>
<table>
<thead><tr><th>Tarih</th><th>Hasta</th><th>Telefon</th><th>TC</th><th>Tercih</th><th>Sikayet</th><th>Durum</th></tr></thead>
<tbody>
{% for i in items %}
<tr>
<td>{{i.created_at[:16]}}</td>
<td><b>{{i.ad}} {{i.soyad}}</b></td>
<td><a href="https://wa.me/9{{i.phone}}" target="_blank">{{i.phone}}</a></td>
<td>{{i.tc or '-'}}</td>
<td>{{i.tercih_tarih or '-'}} {{i.tercih_saat or ''}}</td>
<td style="max-width:280px">{{i.sikayet or '-'}}</td>
<td>{% if i.status == 'processed' %}<span class="tag-done">Onaylandi</span>{% else %}<span class="tag-pending">Bekliyor</span>{% endif %}</td>
</tr>
{% else %}
<tr><td colspan="7" style="text-align:center;padding:30px;color:#5e7185">Henuz public talep yok</td></tr>
{% endfor %}
</tbody></table>
<p style="margin-top:14px"><b>Public link:</b> <a href="/randevu-al" target="_blank">/randevu-al</a> (login GEREKMEZ - hastalar acabilir)</p>
<p><a href="/">&lt;- Ana sayfa</a></p>
</body></html>
"""


# ============================================================
# 5. AILE/ES ERISIMI - Partner Magic-Link
# ============================================================
@clinical_bp.route("/api/clinical/partner-link", methods=["POST"])
def api_partner_link():
    """Mevcut hasta token'i icin partner kopyasi olustur (ayni scope)."""
    auth = _require_doctor()
    if auth: return auth
    p = request.get_json(silent=True) or {}
    original_token = (p.get("original_token") or "").strip()
    partner_name = (p.get("partner_name") or "Es").strip()
    if not original_token:
        return jsonify({"ok": False, "error": "original_token gerekli"}), 400
    con = _db()
    try:
        r = con.execute(
            "SELECT patient_id, phone, expires_at, scopes, tc_last4, birth_year "
            "FROM patient_portal_tokens WHERE token=?", (original_token,)).fetchone()
        if not r:
            return jsonify({"ok": False, "error": "Token bulunamadi"}), 404
        new_token = secrets.token_urlsafe(32)
        # Scope'a partner notu ekle
        try:
            scopes = json.loads(r["scopes"] or "{}")
        except Exception:
            scopes = {"all": True}
        scopes["partner_view"] = True
        scopes["partner_name"] = partner_name
        scopes["custom_message"] = (scopes.get("custom_message", "") +
            f"\n\n[Es/Aile linki: {partner_name}]").strip()
        con.execute(
            "INSERT INTO patient_portal_tokens "
            "(token, patient_id, phone, issued_at, expires_at, scopes, tc_last4, birth_year) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (new_token, r["patient_id"], r["phone"],
             datetime.now().isoformat(), r["expires_at"],
             json.dumps(scopes, ensure_ascii=False),
             r["tc_last4"], r["birth_year"]))
        con.commit()
    finally:
        con.close()
    base = request.host_url.rstrip("/")
    return jsonify({
        "ok": True, "partner_token": new_token,
        "partner_url": f"{base}/hasta-portal/giris?token={new_token}",
        "message": f"{partner_name} icin partner linki olusturuldu"
    })


# ============================================================
# 6. GUNLUK KASA DASHBOARD
# ============================================================
@clinical_bp.route("/kasa-dashboard", methods=["GET"])
def kasa_dashboard_page():
    auth = _require_doctor()
    if auth: return auth
    today = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    month_ago = (date.today() - timedelta(days=30)).isoformat()

    stats = {"today": 0, "week": 0, "month": 0,
             "today_n": 0, "week_n": 0, "month_n": 0,
             "by_status": {}, "pending": 0, "recent": [],
             "daily_chart": []}

    con = _db()
    try:
        # patient_billing_records var mi kontrol
        tables = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "patient_billing_records" in tables:
            # Toplam tahsilat
            def sum_received(since_date):
                r = con.execute(
                    "SELECT COALESCE(SUM(amount_received), 0) AS total, COUNT(*) AS n "
                    "FROM patient_billing_records "
                    "WHERE date(created_at) >= ?", (since_date,)).fetchone()
                return float(r[0] or 0), int(r[1] or 0)
            stats["today"], stats["today_n"] = sum_received(today)
            stats["week"], stats["week_n"] = sum_received(week_ago)
            stats["month"], stats["month_n"] = sum_received(month_ago)
            # Bekleyen
            r = con.execute(
                "SELECT COALESCE(SUM(amount_quoted - COALESCE(amount_received,0)),0) "
                "FROM patient_billing_records "
                "WHERE payment_status IN ('partial', 'pending', 'unpaid')").fetchone()
            stats["pending"] = float(r[0] or 0)
            # Son 10 odeme
            rs = con.execute(
                "SELECT b.created_at, b.procedure_name, b.amount_received, "
                "       b.payment_status, p.display_name "
                "FROM patient_billing_records b "
                "LEFT JOIN patients p ON p.folder_key=b.patient_key "
                "WHERE b.amount_received > 0 "
                "ORDER BY b.created_at DESC LIMIT 10").fetchall()
            stats["recent"] = [dict(r) for r in rs]
            # Son 30 gun gunluk
            rs = con.execute(
                "SELECT date(created_at) as d, SUM(COALESCE(amount_received,0)) as t "
                "FROM patient_billing_records "
                "WHERE date(created_at) >= ? "
                "GROUP BY date(created_at) ORDER BY d", (month_ago,)).fetchall()
            stats["daily_chart"] = [{"d": r[0], "t": float(r[1])} for r in rs]
    except Exception as e:
        print(f"[kasa] err: {e}")
    finally:
        con.close()
    return render_template_string(_KASA_PAGE, stats=stats,
        chart_json=json.dumps(stats["daily_chart"], ensure_ascii=False))


_KASA_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Kasa Dashboard</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:1100px;margin:0 auto;padding:18px;background:#f5f8fb}
h1{color:#0d4f8b}
.kpi{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:18px}
.kpi-box{background:#fff;border-radius:12px;padding:18px;text-align:center;box-shadow:0 2px 6px rgba(0,0,0,0.05);border-top:4px solid #1769aa}
.kpi-box.green{border-top-color:#0a8a76}
.kpi-box.orange{border-top-color:#f0a92b}
.kpi-box.red{border-top-color:#dc2626}
.kpi-n{font-size:30px;font-weight:800;color:#0d4f8b;margin:6px 0}
.kpi-l{font-size:12px;color:#5e7185;text-transform:uppercase;letter-spacing:0.5px}
.kpi-s{font-size:11px;color:#5e7185;margin-top:4px}
.card{background:#fff;border-radius:12px;padding:18px;margin-bottom:14px}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#eff5fb;padding:8px;text-align:left}
td{padding:8px;border-bottom:1px solid #eef}
.fmt{font-variant-numeric:tabular-nums;font-weight:700}
</style></head><body>
<h1>Kasa Dashboard</h1>
<div style="color:#5e7185;margin-bottom:14px">Gelir tahsilat takibi - bugun, hafta, ay + bekleyen alacaklar.</div>

<div class="kpi">
  <div class="kpi-box green"><div class="kpi-l">BUGUN</div><div class="kpi-n">{{"{:,.0f}".format(stats.today).replace(",", ".")}} TL</div><div class="kpi-s">{{stats.today_n}} islem</div></div>
  <div class="kpi-box"><div class="kpi-l">SON 7 GUN</div><div class="kpi-n">{{"{:,.0f}".format(stats.week).replace(",", ".")}} TL</div><div class="kpi-s">{{stats.week_n}} islem</div></div>
  <div class="kpi-box orange"><div class="kpi-l">SON 30 GUN</div><div class="kpi-n">{{"{:,.0f}".format(stats.month).replace(",", ".")}} TL</div><div class="kpi-s">{{stats.month_n}} islem</div></div>
  <div class="kpi-box red"><div class="kpi-l">BEKLEYEN ALACAK</div><div class="kpi-n">{{"{:,.0f}".format(stats.pending).replace(",", ".")}} TL</div><div class="kpi-s">Eksik tahsilat</div></div>
</div>

<div class="card">
  <h3 style="margin-top:0;color:#0d4f8b">Son 30 Gun Trend</h3>
  <canvas id="chart" height="100"></canvas>
</div>

<div class="card">
  <h3 style="margin-top:0;color:#0d4f8b">Son 10 Tahsilat</h3>
  <table>
    <thead><tr><th>Tarih</th><th>Hasta</th><th>Islem</th><th>Tutar</th><th>Durum</th></tr></thead>
    <tbody>
    {% for r in stats.recent %}
    <tr><td>{{r.created_at[:16] if r.created_at else '-'}}</td>
        <td>{{r.display_name or '-'}}</td>
        <td>{{r.procedure_name or '-'}}</td>
        <td class="fmt">{{"{:,.0f}".format(r.amount_received or 0).replace(",", ".")}} TL</td>
        <td>{{r.payment_status or '-'}}</td></tr>
    {% else %}
    <tr><td colspan="5" style="text-align:center;padding:30px;color:#5e7185">Tahsilat kaydi yok</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>

<p><a href="/">&lt;- Ana sayfa</a> &middot; <a href="/istatistikler">Tum Istatistikler</a></p>

<script>
const D = {{chart_json|safe}};
if (D.length) {
  new Chart(document.getElementById('chart'), {
    type:'bar',
    data:{labels:D.map(x=>x.d.substring(5)), datasets:[
      {label:'Gunluk Gelir (TL)', data:D.map(x=>x.t), backgroundColor:'#0a8a76'}]},
    options:{responsive:true, plugins:{legend:{display:false}}, scales:{y:{beginAtZero:true}}}
  });
}
</script></body></html>
"""


# ============================================================
# 7. AI TRIAJ BOT
# ============================================================
@clinical_bp.route("/triaj-bot", methods=["GET", "POST"])
def triaj_bot_page():
    auth = _require_doctor()
    if auth: return auth
    result = None
    if request.method == "POST":
        msg = (request.form.get("message") or "").strip()
        if msg:
            result = _ai_triaj_classify(msg)
            # Logla
            try:
                con = _db()
                con.execute(
                    "INSERT INTO triaj_history (message, urgency, category, ai_response, user_key) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (msg, result["urgency"], result["category"], result["response"],
                     session.get("user", "doktor")))
                con.commit()
                con.close()
            except Exception:
                pass
    # History
    con = _db()
    try:
        rows = con.execute(
            "SELECT created_at, message, urgency, category "
            "FROM triaj_history ORDER BY id DESC LIMIT 20").fetchall()
        history = [dict(r) for r in rows]
    finally:
        con.close()
    return render_template_string(_TRIAJ_PAGE, result=result, history=history)


def _ai_triaj_classify(msg: str) -> Dict[str, Any]:
    """MesajÄ± sÄ±nÄ±flandÄ±r. Anahtar kelime tabanlÄ± + isteÄŸe baÄŸlÄ± Ollama.

    Returns: {urgency: 1-5, category: str, response: str}
    """
    msg_lower = msg.lower()
    msg_fold = (msg_lower
        .replace("Ä±", "i").replace("ÅŸ", "s").replace("ÄŸ", "g")
        .replace("Ã¼", "u").replace("Ã¶", "o").replace("Ã§", "c"))

    # KÄ±rmÄ±zÄ± bayrak: ACIL (urgency 5)
    red_flags = [
        ("kanama", "bol kanama, kanama,kanama 20", 5, "obstetrik_acil"),
        ("agri", "siddetli karin agrisi, dayanilmaz agri, kasilma", 5, "agÂ­ri_acil"),
        ("su geldi", "amniyon, su geldi", 5, "membran_ruptur"),
        ("kasilma", "siddetli kasilma, dakikada", 5, "preterm"),
        ("baygin", "bayildim, fenalik, gozlerim karariyor", 5, "presenkop"),
        ("ates", "39 ates, yuksek ates, 40 ates", 4, "enfeksiyon"),
        ("bebek hareket", "bebek hareket etmiyor, hareket yok", 5, "obstetrik_acil"),
        ("dusuk", "dustum, dusuk", 4, "trauma"),
    ]
    for kw, _examples, urg, cat in red_flags:
        if kw in msg_fold:
            return {
                "urgency": urg, "category": cat,
                "response": f"ACIL: '{kw}' belirtisi. Hasta hemen aranmali / acil servise yonlendirilmeli."
            }

    # Orta (urgency 3)
    yellow = [
        ("akinti", "vajinal akinti", 3, "akinti"),
        ("yanma", "idrar yanmasi", 3, "iyi"),
        ("kasinti", "kasinti", 2, "kasinti"),
        ("bulanti", "kusma, bulanti", 3, "obstetrik"),
        ("hpv", "hpv pozitif", 3, "smear"),
        ("smear", "smear sonucu", 2, "smear"),
    ]
    for kw, _ex, urg, cat in yellow:
        if kw in msg_fold:
            return {
                "urgency": urg, "category": cat,
                "response": f"Orta: '{kw}' ilgili. 24-48 saat icinde randevu."
            }

    # Rutin (1-2)
    routine = ["randevu", "ne zaman", "kontrol", "smear istiyorum", "iglac yazar misiniz",
               "recete", "rapor"]
    for kw in routine:
        if kw in msg_fold:
            return {
                "urgency": 1, "category": "rutin",
                "response": "Rutin talep. Yarin/oburgun mesai saatinde donulebilir."
            }

    # Fallback
    return {
        "urgency": 2, "category": "belirsiz",
        "response": "Belirsiz mesaj. Manuel inceleme onerilir - mesaj tarz olarak rutin gibi gozukuyor."
    }


_TRIAJ_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>AI Triaj Bot</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:900px;margin:0 auto;padding:18px;background:#f5f8fb}
h1{color:#0d4f8b}
.card{background:#fff;border-radius:12px;padding:18px;margin-bottom:14px;box-shadow:0 2px 6px rgba(0,0,0,0.05)}
textarea{width:100%;min-height:100px;padding:12px;border:1px solid #cdd9e3;border-radius:8px;font-size:15px;font-family:inherit}
.btn{background:#1769aa;color:#fff;border:none;padding:12px 24px;border-radius:8px;font-size:15px;font-weight:700;cursor:pointer}
.urg-5{background:#dc2626;color:#fff;padding:14px;border-radius:8px;font-weight:800}
.urg-4{background:#ea580c;color:#fff;padding:14px;border-radius:8px;font-weight:800}
.urg-3{background:#fbbf24;color:#7c2d12;padding:14px;border-radius:8px;font-weight:700}
.urg-2{background:#dcfce7;color:#166534;padding:14px;border-radius:8px;font-weight:700}
.urg-1{background:#e0f2fe;color:#0c4a6e;padding:14px;border-radius:8px;font-weight:700}
table{width:100%;border-collapse:collapse;font-size:13px}
th{background:#eff5fb;padding:6px;text-align:left}
td{padding:6px;border-bottom:1px solid #eef}
</style></head><body>
<h1>AI Triaj Bot (WhatsApp Mesaji Aciliyet Skoru)</h1>
<div style="color:#5e7185;margin-bottom:14px">Hastadan gelen mesaji yapistirin -&gt; aciliyet skoru (1-5) + onerilen aksiyon.</div>

<div class="card">
  <form method="POST">
    <label style="font-weight:700;color:#0d4f8b">WhatsApp / SMS mesaji:</label>
    <textarea name="message" placeholder="Hocam akilim adetim 1 hafta gecikti, agrim var, ne yapayim?" required></textarea>
    <button type="submit" class="btn" style="margin-top:10px">Triaj Et</button>
  </form>
</div>

{% if result %}
<div class="card">
  <h3 style="margin-top:0">Sonuc</h3>
  <div class="urg-{{result.urgency}}">
    ACILIYET: {{result.urgency}}/5 - {{result.category|upper}}
  </div>
  <p style="margin-top:10px"><b>Oneri:</b> {{result.response}}</p>
</div>
{% endif %}

<div class="card">
  <h3 style="margin-top:0">Son Triaj'lar</h3>
  <table>
    <thead><tr><th>Zaman</th><th>Mesaj (ilk 60)</th><th>Aciliyet</th><th>Kategori</th></tr></thead>
    <tbody>
    {% for h in history %}
    <tr><td>{{h.created_at[:16]}}</td>
        <td>{{(h.message or '')[:60]}}{% if (h.message or '')|length > 60 %}...{% endif %}</td>
        <td><b style="color:{{'#dc2626' if h.urgency >= 4 else ('#fbbf24' if h.urgency == 3 else '#166534')}}">{{h.urgency}}/5</b></td>
        <td>{{h.category}}</td></tr>
    {% else %}
    <tr><td colspan="4" style="text-align:center;padding:20px;color:#5e7185">Henuz triaj yok</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>

<p><a href="/">&lt;- Ana sayfa</a></p>
</body></html>
"""


# ============================================================
# 8. SESLI VISIT NOTE (Browser SpeechRecognition - Turkce)
# ============================================================
@clinical_bp.route("/sesli-not", methods=["GET"])
def sesli_not_page():
    """Mikrofona konus -> Turkce metne cevir -> hastaya kaydet."""
    auth = _require_doctor()
    if auth: return auth
    pid = (request.args.get("patient") or "").strip()
    patient_name = ""
    if pid:
        con = _db()
        try:
            r = con.execute("SELECT display_name FROM patients WHERE folder_key=?", (pid,)).fetchone()
            if r: patient_name = r[0] or pid
        finally:
            con.close()
    all_patients = []
    try:
        con = _db()
        rs = con.execute(
            "SELECT folder_key, display_name FROM patients "
            "WHERE archived_at IS NULL ORDER BY updated_at DESC LIMIT 2000").fetchall()
        all_patients = [{"k": r[0], "n": r[1] or r[0]} for r in rs]
        con.close()
    except Exception:
        pass
    return render_template_string(
        _SESLI_NOT_PAGE, pid=pid, patient_name=patient_name,
        all_patients_json=json.dumps(all_patients, ensure_ascii=False).replace("</", "<\\/"))


@clinical_bp.route("/api/clinical/visit-note-save", methods=["POST"])
def api_save_visit_note():
    """Transkripte metni hastanin son ziyaretine veya yeni notuna ekle."""
    auth = _require_doctor()
    if auth: return auth
    p = request.get_json(silent=True) or {}
    pid = (p.get("patient_key") or "").strip()
    text = (p.get("text") or "").strip()
    mode = (p.get("mode") or "append").strip()  # append | new_visit
    if not pid or not text:
        return jsonify({"ok": False, "error": "patient_key + text gerekli"}), 400
    con = _db()
    try:
        if mode == "new_visit":
            con.execute(
                "INSERT INTO visits (patient_folder_key, visit_date, visit_type, "
                "examination, source, created_at) "
                "VALUES (?, ?, 'Muayene', ?, 'sesli_not', CURRENT_TIMESTAMP)",
                (pid, datetime.now().strftime("%Y-%m-%d"), text))
        else:
            # En son ziyarete append
            row = con.execute(
                "SELECT id, examination FROM visits "
                "WHERE patient_folder_key=? ORDER BY visit_date DESC LIMIT 1",
                (pid,)).fetchone()
            if row:
                old = row["examination"] or ""
                sep = "\n\n--- Sesli not ({}): ---\n".format(datetime.now().strftime("%Y-%m-%d %H:%M"))
                new = old + sep + text
                con.execute(
                    "UPDATE visits SET examination=? WHERE id=?",
                    (new, row["id"]))
            else:
                # Hic ziyaret yok, yeni olustur
                con.execute(
                    "INSERT INTO visits (patient_folder_key, visit_date, visit_type, "
                    "examination, source, created_at) "
                    "VALUES (?, ?, 'Muayene', ?, 'sesli_not', CURRENT_TIMESTAMP)",
                    (pid, datetime.now().strftime("%Y-%m-%d"), text))
        con.commit()
    finally:
        con.close()
    return jsonify({"ok": True, "message": "Kaydedildi"})


_SESLI_NOT_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Sesli Visit Note</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:800px;margin:0 auto;padding:18px;background:#f5f8fb}
h1{color:#0d4f8b}
.card{background:#fff;border-radius:12px;padding:18px;margin-bottom:14px;box-shadow:0 2px 6px rgba(0,0,0,0.05)}
.search{padding:12px;border:2px solid #1769aa;border-radius:8px;font-size:15px;width:100%}
.dd{display:none;background:#fff;border:2px solid #1769aa;border-radius:8px;max-height:300px;overflow-y:auto;margin-top:4px;z-index:50}
.dd a{display:block;padding:10px;border-bottom:1px solid #eef;text-decoration:none;color:#0d4f8b}
.dd a:hover{background:#eff5fb}
.mic{background:#dc2626;color:#fff;border:none;padding:20px 30px;font-size:18px;font-weight:700;border-radius:50%;width:100px;height:100px;cursor:pointer;box-shadow:0 6px 16px rgba(220,38,38,0.4)}
.mic.rec{animation:pulse 1.2s ease-in-out infinite}
@keyframes pulse{0%,100%{box-shadow:0 6px 16px rgba(220,38,38,0.4)}50%{box-shadow:0 6px 28px rgba(220,38,38,0.8)}}
.mic:hover{transform:scale(1.05)}
textarea{width:100%;min-height:180px;padding:14px;border:1px solid #cdd9e3;border-radius:8px;font-size:15px;font-family:inherit;line-height:1.5}
.btn{background:#1769aa;color:#fff;border:none;padding:12px 20px;border-radius:8px;font-weight:700;cursor:pointer;font-size:14px}
.btn.green{background:#0a8a76}
.status{padding:8px 12px;border-radius:6px;font-size:13px;display:inline-block;margin-left:10px}
.status.live{background:#dcfce7;color:#166534}
.status.idle{background:#eef;color:#5e7185}
</style></head><body>
<h1>Sesli Visit Note</h1>
<div style="color:#5e7185;margin-bottom:14px">Mikrofona konus, otomatik Turkce metne cevirilir. Hastaya kaydet.</div>

<div class="card">
  <label style="font-weight:700;color:#0d4f8b">Hasta sec:</label>
  <input type="search" id="searchBox" class="search" placeholder="Hasta ara (2 harf)..." autocomplete="off" value="{{patient_name}}">
  <div id="dropdown" class="dd"></div>
</div>

<div class="card" style="text-align:center;padding:30px">
  <button id="micBtn" class="mic">REC</button>
  <div id="status" class="status idle" style="margin-top:14px;display:block;width:fit-content;margin-left:auto;margin-right:auto">Hazir - mikrofona basin</div>
</div>

<div class="card">
  <label style="font-weight:700;color:#0d4f8b">Transkripsyon (duzenleyebilirsin):</label>
  <textarea id="noteText" placeholder="Burada metin gozukecek..."></textarea>
  <div style="margin-top:14px;display:flex;gap:8px;flex-wrap:wrap">
    <button class="btn" id="saveAppend">Son Ziyarete Ekle</button>
    <button class="btn green" id="saveNew">Yeni Ziyaret Notu Olustur</button>
    <button class="btn" style="background:#5e7185" id="clearBtn">Temizle</button>
  </div>
  <div id="saveMsg" style="margin-top:10px"></div>
</div>

<p><a href="/">&lt;- Ana sayfa</a></p>

<script>
const AC = {{all_patients_json|safe}};
function fold(s){return String(s||'').toLowerCase().replace(/[Ä±Ä°iI]/g,'i').replace(/[ÅŸÅSs]/g,'s').replace(/[ÄŸÄGg]/g,'g').replace(/[Ã¼ÃœUu]/g,'u').replace(/[Ã¶Ã–Oo]/g,'o').replace(/[Ã§Ã‡Cc]/g,'c');}
const IDX = AC.map(p => ({k:p.k, n:p.n, h:fold(p.n+' '+p.k)}));
const box = document.getElementById('searchBox'), dd = document.getElementById('dropdown');
let pid = "{{pid|e}}";
let acTimer = null;
function runAc() {
  const q = (box.value||'').trim(); if (q.length < 2) { dd.style.display='none'; return; }
  const qf = fold(q); const ws = qf.split(/\s+/).filter(Boolean); const out = [];
  for (const p of IDX) { let ok=true; for (const w of ws) if (!p.h.includes(w)) {ok=false;break;}
    if (ok) out.push(p); if (out.length>15) break; }
  dd.innerHTML = out.map(p => '<a href="#" data-key="' + p.k + '" data-name="' + p.n + '">' + p.n + '</a>').join('') ||
    '<div style="padding:14px;color:#5e7185">Hasta yok</div>';
  dd.style.display = 'block';
  dd.querySelectorAll('a').forEach(a => a.addEventListener('click', (ev) => {
    ev.preventDefault(); pid = a.dataset.key; box.value = a.dataset.name;
    history.replaceState(null, '', '/sesli-not?patient=' + encodeURIComponent(pid));
    dd.style.display = 'none';
  }));
}
box.addEventListener('input', () => { clearTimeout(acTimer); acTimer = setTimeout(runAc, 80); });
document.addEventListener('click', ev => { if (ev.target !== box && !dd.contains(ev.target)) dd.style.display='none'; });

// Browser SpeechRecognition
const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
const micBtn = document.getElementById('micBtn');
const status = document.getElementById('status');
const noteText = document.getElementById('noteText');
let recognition = null;
let recording = false;
if (!SR) {
  status.textContent = 'Tarayicin SpeechRecognition desteklemiyor (Chrome/Edge kullanin)';
  status.className = 'status idle';
  micBtn.disabled = true;
} else {
  recognition = new SR();
  recognition.lang = 'tr-TR';
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.onresult = (event) => {
    let final = '';
    let interim = '';
    for (let i = event.resultIndex; i < event.results.length; i++) {
      const t = event.results[i][0].transcript;
      if (event.results[i].isFinal) final += t + ' ';
      else interim += t;
    }
    if (final) noteText.value += final;
    status.textContent = 'Dinleniyor... ' + (interim ? '(' + interim.substring(0,40) + '...)' : '');
  };
  recognition.onerror = (e) => { status.textContent = 'Hata: ' + e.error; status.className='status idle'; recording=false; micBtn.classList.remove('rec'); };
  recognition.onend = () => {
    if (recording) { try { recognition.start(); } catch(e){} }  // auto-restart
  };
}
micBtn.addEventListener('click', () => {
  if (!recognition) return;
  if (recording) {
    recording = false;
    recognition.stop();
    status.textContent = 'Durduruldu'; status.className = 'status idle';
    micBtn.classList.remove('rec'); micBtn.textContent = 'REC';
  } else {
    if (!pid) { alert('Once hasta sec'); return; }
    recording = true;
    recognition.start();
    status.textContent = 'Dinleniyor...'; status.className = 'status live';
    micBtn.classList.add('rec'); micBtn.textContent = 'STOP';
  }
});

document.getElementById('clearBtn').addEventListener('click', () => { noteText.value = ''; });

async function saveNote(mode) {
  if (!pid) { alert('Once hasta sec'); return; }
  const text = noteText.value.trim();
  if (!text) { alert('Metin bos'); return; }
  const msg = document.getElementById('saveMsg');
  msg.innerHTML = 'Kaydediliyor...';
  try {
    const r = await fetch('/api/clinical/visit-note-save', {
      method:'POST', credentials:'same-origin',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({patient_key:pid, text:text, mode:mode})
    });
    const j = await r.json();
    if (j.ok) {
      msg.innerHTML = '<span style="color:#166534;font-weight:700">Kaydedildi.</span>';
    } else { msg.innerHTML = '<span style="color:#b3261e">Hata: ' + j.error + '</span>'; }
  } catch(e) { msg.innerHTML = '<span style="color:#b3261e">Hata: ' + e.message + '</span>'; }
}
document.getElementById('saveAppend').addEventListener('click', () => saveNote('append'));
document.getElementById('saveNew').addEventListener('click', () => saveNote('new_visit'));
</script></body></html>
"""


# ============================================================
# 9. ZIYARET SABLONLARI
# ============================================================
@clinical_bp.route("/ziyaret-sablonlari", methods=["GET", "POST"])
def visit_templates_page():
    auth = _require_doctor()
    if auth: return auth
    msg = ""
    if request.method == "POST":
        action = request.form.get("action", "")
        if action == "delete":
            tid = request.form.get("id")
            if tid:
                con = _db(); con.execute("DELETE FROM visit_templates WHERE id=?", (tid,)); con.commit(); con.close()
                msg = "Sablon silindi"
        elif action == "add":
            name = (request.form.get("name") or "").strip()
            cat = (request.form.get("category") or "").strip()
            body = (request.form.get("body") or "").strip()
            if name and body:
                try:
                    con = _db(); con.execute("INSERT INTO visit_templates (name, category, body) VALUES (?, ?, ?)", (name, cat, body)); con.commit(); con.close()
                    msg = "Sablon eklendi"
                except Exception as e:
                    msg = f"Hata: {e}"
    con = _db()
    try:
        rows = con.execute(
            "SELECT id, name, category, body, use_count FROM visit_templates "
            "ORDER BY use_count DESC, name").fetchall()
        templates = [dict(r) for r in rows]
    finally:
        con.close()
    return render_template_string(_VISIT_TEMPLATES_PAGE, templates=templates, msg=msg)


@clinical_bp.route("/api/clinical/template-apply", methods=["POST"])
def api_template_apply():
    """Sablon kullanim sayacini artir."""
    auth = _require_doctor()
    if auth: return auth
    p = request.get_json(silent=True) or {}
    tid = p.get("id")
    if not tid: return jsonify({"ok": False}), 400
    try:
        con = _db()
        con.execute("UPDATE visit_templates SET use_count = use_count + 1 WHERE id=?", (tid,))
        con.commit()
        con.close()
    except Exception: pass
    return jsonify({"ok": True})


_VISIT_TEMPLATES_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Ziyaret Sablonlari</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:1000px;margin:0 auto;padding:18px;background:#f5f8fb}
h1{color:#0d4f8b}
.card{background:#fff;border-radius:12px;padding:16px;margin-bottom:14px;box-shadow:0 2px 6px rgba(0,0,0,0.05)}
.t-card{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}
.t-body{flex:1}
.t-name{font-weight:700;color:#0d4f8b;font-size:15px}
.t-meta{font-size:12px;color:#5e7185;margin-top:2px}
.t-pre{background:#f8fafc;border:1px solid #eef;border-radius:6px;padding:10px;margin-top:8px;font-family:monospace;font-size:12px;white-space:pre-wrap;max-height:140px;overflow:auto;display:none}
.t-card.open .t-pre{display:block}
.btn{background:#1769aa;color:#fff;border:none;padding:6px 12px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer;text-decoration:none;display:inline-block}
.btn-red{background:#b3261e}
.btn-green{background:#0a8a76}
.tag{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700;background:#eff5fb;color:#1769aa}
textarea,input,select{width:100%;padding:10px;border:1px solid #cdd9e3;border-radius:6px;font-size:14px;font-family:inherit}
.msg{background:#dcfce7;color:#166534;padding:10px;border-radius:6px;margin-bottom:14px;font-weight:600}
.copy{background:#10b981;color:#fff;padding:4px 10px;border-radius:4px;font-size:11px;border:none;cursor:pointer}
</style></head><body>
<h1>Ziyaret Sablonlari</h1>
<div style="color:#5e7185;margin-bottom:14px">Hazir sablonlardan kopyala -> ziyaret notuna yapistir. ___ yerlerini doldur.</div>

{% if msg %}<div class="msg">{{msg}}</div>{% endif %}

<div class="card">
  <h3 style="margin-top:0">Yeni Sablon Ekle</h3>
  <form method="POST">
    <input type="hidden" name="action" value="add">
    <div style="display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px">
      <div style="flex:2;min-width:200px"><label>Isim</label><input name="name" required placeholder="Orn: Renkli Doppler Kontrol"></div>
      <div style="flex:1;min-width:150px"><label>Kategori</label>
        <select name="category">
          <option value="obstetric">Obstetrik</option>
          <option value="gynecology">Jinekoloji</option>
          <option value="fertility">Fertilite</option>
          <option value="postpartum">Postpartum</option>
          <option value="aesthetic">Estetik</option>
          <option value="other">Diger</option>
        </select>
      </div>
    </div>
    <label>Sablon Govdesi (___ ile bos alan birak)</label>
    <textarea name="body" rows="6" required placeholder="TANSIYON: ___/___ mmHg&#10;KILO: ___ kg&#10;ONERILER: ___"></textarea>
    <button type="submit" class="btn" style="margin-top:8px;padding:10px 20px">Sablonu Kaydet</button>
  </form>
</div>

<h3 style="color:#0d4f8b">Mevcut Sablonlar ({{templates|length}})</h3>
{% for t in templates %}
<div class="card t-card" id="t-{{t.id}}">
  <div class="t-body">
    <div class="t-name">{{t.name}}</div>
    <div class="t-meta">
      <span class="tag">{{t.category or 'genel'}}</span>
      Kullanim: {{t.use_count}}x
    </div>
    <div class="t-pre" id="body-{{t.id}}">{{t.body}}</div>
  </div>
  <div style="display:flex;flex-direction:column;gap:4px">
    <button class="btn btn-green" onclick="toggleBody({{t.id}})">Goster</button>
    <button class="copy" onclick="copyBody({{t.id}})">Kopyala</button>
    <form method="POST" onsubmit="return confirm('Sablon silinsin?')" style="margin:0">
      <input type="hidden" name="action" value="delete">
      <input type="hidden" name="id" value="{{t.id}}">
      <button type="submit" class="btn btn-red">Sil</button>
    </form>
  </div>
</div>
{% endfor %}

<p><a href="/">&lt;- Ana sayfa</a></p>

<script>
function toggleBody(id) {
  document.getElementById('t-' + id).classList.toggle('open');
}
async function copyBody(id) {
  const txt = document.getElementById('body-' + id).textContent;
  try {
    await navigator.clipboard.writeText(txt);
    alert('Sablon panoya kopyalandi! Hasta ziyaret notuna Ctrl+V ile yapistir.');
    await fetch('/api/clinical/template-apply', {
      method:'POST', credentials:'same-origin',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({id: id})
    });
  } catch(e) {
    alert('Kopyalanamadi. Manuel sec.');
  }
}
</script></body></html>
"""


# ============================================================
# 10. OB-WHEEL DIJITAL
# ============================================================
@clinical_bp.route("/ob-wheel", methods=["GET"])
def ob_wheel_page():
    auth = _require_doctor()
    if auth: return auth
    return render_template_string(_OB_WHEEL_PAGE)


_OB_WHEEL_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>OB-Wheel - Gebelik Milestone</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:900px;margin:0 auto;padding:18px;background:#f5f8fb}
h1{color:#0d4f8b}
.card{background:#fff;border-radius:12px;padding:18px;margin-bottom:14px;box-shadow:0 2px 6px rgba(0,0,0,0.05)}
label{font-weight:700;color:#0d4f8b;display:block;margin-bottom:6px}
input,select{padding:12px;border:2px solid #1769aa;border-radius:8px;font-size:16px;width:100%}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end}
.row > *{flex:1;min-width:160px}
.btn{background:#1769aa;color:#fff;border:none;padding:12px 22px;border-radius:8px;font-weight:700;cursor:pointer;font-size:15px}
.milestone{display:flex;align-items:center;gap:14px;padding:14px;border-bottom:1px solid #eef}
.milestone:last-child{border-bottom:none}
.ms-icon{width:50px;height:50px;border-radius:14px;background:linear-gradient(135deg,#0d4f8b,#0a8a76);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px;flex-shrink:0}
.ms-icon.past{background:linear-gradient(135deg,#94a3b8,#64748b)}
.ms-icon.now{background:linear-gradient(135deg,#dc2626,#f0a92b);animation:glow 2s ease-in-out infinite}
@keyframes glow{0%,100%{box-shadow:0 0 10px rgba(220,38,38,0.5)}50%{box-shadow:0 0 24px rgba(220,38,38,0.9)}}
.ms-body{flex:1}
.ms-name{font-weight:700;color:#0d4f8b}
.ms-date{font-size:13px;color:#5e7185;margin-top:2px}
.ms-days{font-size:12px;font-weight:700;padding:4px 10px;border-radius:10px;background:#eff5fb;color:#1769aa;white-space:nowrap}
.ms-days.past{background:#dcfce7;color:#166534}
.ms-days.now{background:#fee2e2;color:#b3261e}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:14px}
.s-box{background:#fff;border-radius:10px;padding:14px;text-align:center;border-top:4px solid #1769aa}
.s-num{font-size:24px;font-weight:800;color:#0d4f8b}
.s-lbl{font-size:12px;color:#5e7185;margin-top:4px}
</style></head><body>
<h1>OB-Wheel Dijital (Gebelik Milestone)</h1>
<div style="color:#5e7185;margin-bottom:14px">LMP gir -> tum onemli tarihler tek bakista.</div>

<div class="card">
  <div class="row">
    <div>
      <label>Son Adet Tarihi (LMP)</label>
      <input type="date" id="lmp" required>
    </div>
    <button class="btn" onclick="calculate()">Hesapla</button>
  </div>
</div>

<div id="result" style="display:none">
  <div class="summary">
    <div class="s-box"><div class="s-num" id="gaNow">-</div><div class="s-lbl">Su anki GA</div></div>
    <div class="s-box" style="border-top-color:#0a8a76"><div class="s-num" id="eddDate">-</div><div class="s-lbl">Tahmini Dogum</div></div>
    <div class="s-box" style="border-top-color:#f0a92b"><div class="s-num" id="daysLeft">-</div><div class="s-lbl">Kalan Gun</div></div>
    <div class="s-box" style="border-top-color:#dc2626"><div class="s-num" id="trimester">-</div><div class="s-lbl">Trimester</div></div>
  </div>

  <div class="card">
    <h3 style="margin-top:0;color:#0d4f8b">Tum Milestone'lar</h3>
    <div id="milestones"></div>
  </div>
</div>

<p><a href="/">&lt;- Ana sayfa</a></p>

<script>
const MILESTONES = [
  {name:'1. Trimester USG', wk:7, info:'Erken USG - gestasyon kesesi, FH+', icon:'1T'},
  {name:'NT Tarama (1.tri)', wk:11, info:'11-13+6 hf NT + PAPP-A + b-hCG', icon:'NT'},
  {name:'2. Trimester (cinsiyet)', wk:16, info:'Bebek cinsiyeti, AFP', icon:'2T'},
  {name:'Anomali Tarama (Morfo)', wk:20, info:'18-22 hf - tum organlar detay', icon:'MO'},
  {name:'3. Trimester baslangic', wk:28, info:'GBS hazirlik, hareket sayimi', icon:'3T'},
  {name:'GDM Tarama (OGTT)', wk:25, info:'24-28 hf 75g OGTT', icon:'GD'},
  {name:'Tdap Asisi', wk:28, info:'27-36 hf bogmaca koruyucu', icon:'AS'},
  {name:'GBS Tarama', wk:36, info:'35-37 hf vajinal/rektal kultur', icon:'GB'},
  {name:'Term Gebelik', wk:37, info:'>37 hf term', icon:'TR'},
  {name:'Tahmini Dogum (EDD)', wk:40, info:'40 hf Naegele', icon:'ED'},
  {name:'Post-term', wk:42, info:'>42 hf indukstion', icon:'PT'},
];
function calculate() {
  const lmpStr = document.getElementById('lmp').value;
  if (!lmpStr) { alert('LMP gir'); return; }
  const lmp = new Date(lmpStr);
  const today = new Date();
  const diff = Math.floor((today - lmp) / (1000*60*60*24));
  const gaWk = Math.floor(diff / 7);
  const gaDay = diff % 7;
  const edd = new Date(lmp.getTime() + 280*24*60*60*1000);
  const daysLeft = Math.floor((edd - today) / (1000*60*60*24));
  let tri = '1.';
  if (gaWk >= 28) tri = '3.';
  else if (gaWk >= 14) tri = '2.';

  document.getElementById('gaNow').textContent = gaWk + 'w' + gaDay + 'd';
  document.getElementById('eddDate').textContent = edd.toLocaleDateString('tr-TR');
  document.getElementById('daysLeft').textContent = daysLeft;
  document.getElementById('trimester').textContent = tri;

  const fmt = (d) => d.toLocaleDateString('tr-TR', {day:'2-digit', month:'2-digit', year:'numeric'});
  const msEl = document.getElementById('milestones');
  msEl.innerHTML = MILESTONES.map(m => {
    const mDate = new Date(lmp.getTime() + m.wk*7*24*60*60*1000);
    const dleft = Math.floor((mDate - today) / (1000*60*60*24));
    let cls = '';
    let lbl = '';
    if (dleft < -7) { cls = 'past'; lbl = Math.abs(dleft) + ' gun once'; }
    else if (Math.abs(dleft) <= 7) { cls = 'now'; lbl = dleft === 0 ? 'BUGUN!' : (dleft > 0 ? dleft + ' gun sonra' : Math.abs(dleft) + ' gun once'); }
    else { cls = ''; lbl = dleft + ' gun kaldi'; }
    return '<div class="milestone">' +
      '<div class="ms-icon ' + cls + '">' + m.icon + '</div>' +
      '<div class="ms-body">' +
        '<div class="ms-name">' + m.name + ' (' + m.wk + ' hf)</div>' +
        '<div class="ms-date">' + fmt(mDate) + ' - ' + m.info + '</div>' +
      '</div>' +
      '<div class="ms-days ' + cls + '">' + lbl + '</div>' +
    '</div>';
  }).join('');

  document.getElementById('result').style.display = 'block';
}
// Eger URL'de ?lmp=YYYY-MM-DD varsa otomatik calistir
const params = new URLSearchParams(location.search);
if (params.get('lmp')) {
  document.getElementById('lmp').value = params.get('lmp');
  calculate();
}
</script></body></html>
"""


# ============================================================
# 11. HIZLI ETIKET SISTEMI (Patient Tags)
# ============================================================
@clinical_bp.route("/api/clinical/tag-add", methods=["POST"])
def api_tag_add():
    auth = _require_doctor()
    if auth: return auth
    p = request.get_json(silent=True) or {}
    pid = (p.get("patient_key") or "").strip()
    tag = (p.get("tag") or "").strip()[:32]
    color = (p.get("color") or "#1769aa").strip()
    if not pid or not tag:
        return jsonify({"ok": False, "error": "patient_key + tag gerekli"}), 400
    try:
        con = _db()
        con.execute(
            "INSERT OR IGNORE INTO patient_tags (patient_key, tag, color, created_by) VALUES (?, ?, ?, ?)",
            (pid, tag, color, session.get("user", "doktor")))
        con.commit()
        con.close()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})


@clinical_bp.route("/api/clinical/tag-remove", methods=["POST"])
def api_tag_remove():
    auth = _require_doctor()
    if auth: return auth
    p = request.get_json(silent=True) or {}
    tid = p.get("id")
    if not tid: return jsonify({"ok": False}), 400
    try:
        con = _db()
        con.execute("DELETE FROM patient_tags WHERE id=?", (tid,))
        con.commit()
        con.close()
    except Exception: pass
    return jsonify({"ok": True})


@clinical_bp.route("/etiketler", methods=["GET"])
def tags_overview_page():
    """Tum etiketler + tag bazli hasta listesi."""
    auth = _require_doctor()
    if auth: return auth
    con = _db()
    try:
        # Tag istatistikleri
        rows = con.execute(
            "SELECT tag, color, COUNT(*) as n FROM patient_tags "
            "GROUP BY tag, color ORDER BY n DESC").fetchall()
        tag_stats = [dict(r) for r in rows]
        # Detayli liste
        filter_tag = request.args.get("tag", "").strip()
        patients = []
        if filter_tag:
            rs = con.execute(
                "SELECT t.tag, t.color, t.patient_key, p.display_name "
                "FROM patient_tags t LEFT JOIN patients p ON p.folder_key=t.patient_key "
                "WHERE t.tag=? ORDER BY p.display_name", (filter_tag,)).fetchall()
            patients = [dict(r) for r in rs]
    finally:
        con.close()
    return render_template_string(_TAGS_PAGE, tag_stats=tag_stats,
        filter_tag=filter_tag, patients=patients)


_TAGS_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Hasta Etiketleri</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:1000px;margin:0 auto;padding:18px;background:#f5f8fb}
h1{color:#0d4f8b}
.card{background:#fff;border-radius:12px;padding:16px;margin-bottom:14px;box-shadow:0 2px 6px rgba(0,0,0,0.05)}
.tag-grid{display:flex;flex-wrap:wrap;gap:8px}
.tag{display:inline-flex;align-items:center;gap:6px;padding:8px 14px;border-radius:14px;color:#fff;font-weight:700;font-size:13px;text-decoration:none}
.tag .n{background:rgba(0,0,0,0.2);padding:2px 8px;border-radius:10px;font-size:11px}
table{width:100%;border-collapse:collapse}
th{background:#eff5fb;padding:10px;text-align:left}
td{padding:8px;border-bottom:1px solid #eef}
.empty{text-align:center;color:#5e7185;padding:30px}
</style></head><body>
<h1>Hasta Etiketleri</h1>
<div style="color:#5e7185;margin-bottom:14px">VIP, Akraba, Sigortali vb etiketler. Tikla -> o etiketteki hastalar.</div>

<div class="card">
  <h3 style="margin-top:0">Tum Etiketler</h3>
  {% if tag_stats %}
  <div class="tag-grid">
  {% for t in tag_stats %}
    <a href="/etiketler?tag={{t.tag|urlencode}}" class="tag" style="background:{{t.color}}">
      {{t.tag}} <span class="n">{{t.n}}</span>
    </a>
  {% endfor %}
  </div>
  {% else %}
  <div class="empty">Henuz etiket yok. Hasta sayfasinda etiket ekleyin.</div>
  {% endif %}
</div>

{% if filter_tag %}
<div class="card">
  <h3 style="margin-top:0">"{{filter_tag}}" etiketli hastalar ({{patients|length}})</h3>
  <table>
    <thead><tr><th>Hasta</th><th>Dosya</th></tr></thead>
    <tbody>
    {% for p in patients %}
    <tr>
      <td><a href="/hasta/{{p.patient_key}}">{{p.display_name or p.patient_key}}</a></td>
      <td><small>{{p.patient_key}}</small></td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
</div>
{% endif %}

<p><a href="/">&lt;- Ana sayfa</a></p>
</body></html>
"""


# ============================================================
# 12. HATIRLAT BUTONU (Patient Recalls)
# ============================================================
@clinical_bp.route("/api/clinical/recall-add", methods=["POST"])
def api_recall_add():
    auth = _require_doctor()
    if auth: return auth
    p = request.get_json(silent=True) or {}
    pid = (p.get("patient_key") or "").strip()
    days_ahead = int(p.get("days_ahead") or 30)
    purpose = (p.get("purpose") or "Genel hatirlatma").strip()
    if not pid: return jsonify({"ok": False, "error": "patient_key gerekli"}), 400
    recall_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")
    try:
        con = _db()
        con.execute(
            "INSERT INTO patient_recalls (patient_key, recall_date, purpose, created_by) "
            "VALUES (?, ?, ?, ?)",
            (pid, recall_date, purpose, session.get("user", "doktor")))
        con.commit()
        con.close()
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True, "recall_date": recall_date})


@clinical_bp.route("/hatirlat-listesi", methods=["GET", "POST"])
def recall_list_page():
    auth = _require_doctor()
    if auth: return auth
    if request.method == "POST":
        rid = request.form.get("complete_id")
        if rid:
            con = _db()
            con.execute("UPDATE patient_recalls SET completed_at=CURRENT_TIMESTAMP WHERE id=?", (rid,))
            con.commit(); con.close()
    con = _db()
    try:
        # Bugun + gecmis (henuz tamamlanmamis)
        rs = con.execute(
            "SELECT r.id, r.patient_key, r.recall_date, r.purpose, r.created_at, "
            "       p.display_name, pd.phone "
            "FROM patient_recalls r "
            "LEFT JOIN patients p ON p.folder_key = r.patient_key "
            "LEFT JOIN patient_demographics pd ON pd.patient_key = r.patient_key "
            "WHERE r.completed_at IS NULL AND r.recall_date <= date('now', '+7 days') "
            "ORDER BY r.recall_date").fetchall()
        today_or_soon = [dict(x) for x in rs]
        # Gelecek
        rs = con.execute(
            "SELECT r.id, r.patient_key, r.recall_date, r.purpose, "
            "       p.display_name "
            "FROM patient_recalls r "
            "LEFT JOIN patients p ON p.folder_key = r.patient_key "
            "WHERE r.completed_at IS NULL AND r.recall_date > date('now', '+7 days') "
            "ORDER BY r.recall_date LIMIT 100").fetchall()
        future = [dict(x) for x in rs]
    finally:
        con.close()
    return render_template_string(_RECALL_PAGE, today_or_soon=today_or_soon, future=future)


_RECALL_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Hatirlatma Listesi</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:1000px;margin:0 auto;padding:18px;background:#f5f8fb}
h1{color:#0d4f8b}
.card{background:#fff;border-radius:12px;padding:16px;margin-bottom:14px;box-shadow:0 2px 6px rgba(0,0,0,0.05)}
table{width:100%;border-collapse:collapse;font-size:14px}
th{background:#eff5fb;padding:8px;text-align:left}
td{padding:8px;border-bottom:1px solid #eef}
.btn{background:#0a8a76;color:#fff;border:none;padding:6px 12px;border-radius:6px;font-size:12px;font-weight:600;cursor:pointer}
.btn-wa{background:#25D366;text-decoration:none;display:inline-block;padding:6px 12px;border-radius:6px;color:#fff;font-size:12px;font-weight:600;margin-right:4px}
.urgent{background:#fee2e2}
</style></head><body>
<h1>Hatirlatma Listesi</h1>
<div style="color:#5e7185;margin-bottom:14px">Bugun ve onumuzdeki 7 gun aranacak/hatirlatilacak hastalar.</div>

<div class="card">
  <h3 style="margin-top:0">Bugun / 7 gun ({{today_or_soon|length}})</h3>
  {% if today_or_soon %}
  <table>
  <thead><tr><th>Tarih</th><th>Hasta</th><th>Telefon</th><th>Sebep</th><th>Aksiyon</th></tr></thead>
  <tbody>
  {% for r in today_or_soon %}
  <tr {% if r.recall_date <= today_str %}class="urgent"{% endif %}>
    <td><b>{{r.recall_date}}</b></td>
    <td><a href="/hasta/{{r.patient_key}}">{{r.display_name or r.patient_key}}</a></td>
    <td>{{r.phone or '-'}}</td>
    <td>{{r.purpose}}</td>
    <td>
      {% if r.phone %}<a href="https://wa.me/9{{r.phone}}?text={{('Sayin ' ~ (r.display_name or '') ~ ', kontrol icin sizi aramamiz gerekiyordu. Uygun musunuz?')|urlencode}}" target="_blank" class="btn-wa">WA</a>{% endif %}
      <form method="POST" style="display:inline">
        <input type="hidden" name="complete_id" value="{{r.id}}">
        <button class="btn" type="submit">Tamamlandi</button>
      </form>
    </td>
  </tr>
  {% endfor %}
  </tbody>
  </table>
  {% else %}
  <div style="text-align:center;color:#5e7185;padding:30px">Bugun ve onumuzdeki 7 gun hatirlatma yok</div>
  {% endif %}
</div>

<div class="card">
  <h3 style="margin-top:0">Gelecek ({{future|length}})</h3>
  {% if future %}
  <table>
  <thead><tr><th>Tarih</th><th>Hasta</th><th>Sebep</th></tr></thead>
  <tbody>
  {% for r in future %}
  <tr>
    <td>{{r.recall_date}}</td>
    <td><a href="/hasta/{{r.patient_key}}">{{r.display_name or r.patient_key}}</a></td>
    <td>{{r.purpose}}</td>
  </tr>
  {% endfor %}
  </tbody>
  </table>
  {% else %}
  <div style="text-align:center;color:#5e7185;padding:20px">Gelecek hatirlatma yok</div>
  {% endif %}
</div>

<p><a href="/">&lt;- Ana sayfa</a></p>
</body></html>
"""


# ============================================================
# 13. QR KLINIK DUVARI
# ============================================================
@clinical_bp.route("/qr-klinik", methods=["GET"])
def qr_klinik_page():
    auth = _require_doctor()
    if auth: return auth
    base = request.host_url.rstrip("/")
    # D700 v17 round2 BONUS: default artik self-giris (TC+tel -> otomatik magic-link)
    target = (request.args.get("target") or f"{base}/hasta-portal/self-giris").strip()
    return render_template_string(_QR_KLINIK_PAGE, target=target, base=base)


@clinical_bp.route("/ui-demo", methods=["GET"])
def ui_demo_page():
    """Tum UI polish'i tek sayfada gor + test et."""
    auth = _require_doctor()
    if auth: return auth
    return render_template_string(_UI_DEMO_PAGE)


_UI_DEMO_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>UI Demo - Polish Test</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{max-width:900px;margin:0 auto;padding:18px;background:#f5f8fb}
h1{color:#0d4f8b;margin-bottom:6px}
.subtitle{color:#5e7185;margin-bottom:20px}
.section{background:#fff;border-radius:14px;padding:20px;margin-bottom:14px;box-shadow:0 4px 12px rgba(0,0,0,0.06)}
.section h2{color:#0d4f8b;margin-top:0;border-bottom:2px solid #eef;padding-bottom:8px}
.btn-row{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:14px}
.btn{background:#1769aa;color:#fff;border:none;padding:10px 18px;border-radius:8px;font-weight:700;cursor:pointer;font-size:14px}
.btn-success{background:#0a8a76}
.btn-danger{background:#dc2626}
.btn-warning{background:#f0a92b}
.btn-info{background:#0284c7}
.demo-card{background:linear-gradient(135deg,#fff,#f5f8fb);border:1px solid #cdd9e3;border-radius:12px;padding:14px;margin-bottom:10px;cursor:pointer}
.icon-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(120px,1fr));gap:8px}
.icon-cell{text-align:center;padding:14px;background:#f5f8fb;border-radius:8px;font-size:12px;color:#5e7185;cursor:pointer}
.icon-cell:hover{background:#eff5fb}
.icon-cell i{font-size:24px;color:#0d4f8b;display:block;margin-bottom:6px}
.font-sample{font-size:18px;line-height:1.6}
.weight-100{font-weight:100}
.weight-400{font-weight:400}
.weight-700{font-weight:700}
.weight-900{font-weight:900}
.tn{font-variant-numeric:tabular-nums;font-feature-settings:'tnum' 1}
.scroll-test{height:200px;overflow:auto;background:#f5f8fb;border-radius:8px;padding:10px;border:1px solid #cdd9e3}
</style></head><body>
<h1>UI Polish Demo</h1>
<div class="subtitle">Tum yeni gorsel ozellikler tek sayfada. Her sey calisiyorsa premium hissedersin.</div>

<!-- 1. Font Test -->
<div class="section" data-aos="fade-up">
  <h2>1. Inter Font (Modern Tipografi)</h2>
  <div class="font-sample weight-100">Asagidaki rakamlar tabular: <span class="tn">1,234,567.89 TL</span></div>
  <div class="font-sample weight-400">Bu metin Inter 400 weight - okumasi rahat olmali.</div>
  <div class="font-sample weight-700"><b>Bu metin Inter 700 weight (Bold) - belirgin baslik.</b></div>
  <div class="font-sample weight-900" style="color:#0d4f8b">BU METIN INTER 900 - SUPER BOLD HEADING.</div>
</div>

<!-- 2. Buttons + Toast -->
<div class="section" data-aos="fade-up">
  <h2>2. Toastify Bildirimler (alert() override)</h2>
  <p class="subtitle" style="margin-bottom:10px">Asagidaki butonlara bas - sag altta sik bildirim cikar:</p>
  <div class="btn-row">
    <button class="btn btn-success" onclick="ykToast.success('Hasta basarili kaydedildi!')">ğŸŸ¢ Success Toast</button>
    <button class="btn btn-danger" onclick="ykToast.error('Hata: dosya bulunamadi')">ğŸ”´ Error Toast</button>
    <button class="btn btn-warning" onclick="ykToast.warning('Dikkat: emin misin?')">ğŸŸ¡ Warning Toast</button>
    <button class="btn btn-info" onclick="ykToast.info('Bilgi: sistem aktif')">ğŸ”µ Info Toast</button>
  </div>
  <div class="btn-row">
    <button class="btn" onclick="alert('Bu eski alert() cagrisi - otomatik ykToast olarak gozukmeli!')">Eski alert() Testi</button>
    <button class="btn" onclick="alert('Hata: bir seyler yanlis gitti')">Eski alert() Hata Testi</button>
    <button class="btn" onclick="alert('Kayit basarili tamamlandi')">Eski alert() Basari Testi</button>
  </div>
</div>

<!-- 3. SweetAlert Confirm -->
<div class="section" data-aos="fade-up">
  <h2>3. SweetAlert2 Modal'lar</h2>
  <div class="btn-row">
    <button class="btn" onclick="testConfirm()">ykConfirm Modal</button>
    <button class="btn btn-success" onclick="testPrompt()">ykPrompt Input</button>
    <button class="btn btn-warning" onclick="ykAlert('Bu sweetalert2 bildirim.', {icon:'success', title:'Tamam!'})">ykAlert</button>
  </div>
</div>

<!-- 4. Tippy Tooltips -->
<div class="section" data-aos="fade-up">
  <h2>4. Tippy.js Tooltip'ler</h2>
  <p class="subtitle">Mouse'u butonlarin uzerine getir - sik tooltip cikar:</p>
  <div class="btn-row">
    <button class="btn" data-tooltip="Bu bir tooltip ornegi">Tooltip 1</button>
    <button class="btn btn-success" data-tooltip="Tooltip sag tarafa cikar" data-tooltip-placement="right">Tooltip Sag</button>
    <button class="btn btn-info" data-tooltip="Bu da uzun bir tooltip mesaji ornegi">Uzun Tooltip</button>
  </div>
</div>

<!-- 5. Tabler Icons -->
<div class="section" data-aos="fade-up">
  <h2>5. Tabler Icons (4500+ Modern SVG)</h2>
  <div class="icon-grid">
    <div class="icon-cell"><i class="ti ti-heart-rate-monitor"></i>heart-rate</div>
    <div class="icon-cell"><i class="ti ti-stethoscope"></i>stethoscope</div>
    <div class="icon-cell"><i class="ti ti-pill"></i>pill</div>
    <div class="icon-cell"><i class="ti ti-vaccine"></i>vaccine</div>
    <div class="icon-cell"><i class="ti ti-microscope"></i>microscope</div>
    <div class="icon-cell"><i class="ti ti-virus"></i>virus</div>
    <div class="icon-cell"><i class="ti ti-mood-happy"></i>mood-happy</div>
    <div class="icon-cell"><i class="ti ti-baby-carriage"></i>baby</div>
    <div class="icon-cell"><i class="ti ti-calendar-heart"></i>calendar-heart</div>
    <div class="icon-cell"><i class="ti ti-clipboard-heart"></i>clipboard</div>
    <div class="icon-cell"><i class="ti ti-report-medical"></i>report</div>
    <div class="icon-cell"><i class="ti ti-bookmark"></i>bookmark</div>
  </div>
</div>

<!-- 6. Card Hover -->
<div class="section" data-aos="fade-up">
  <h2>6. Kart Hover (mouse uzerine getir)</h2>
  <div class="demo-card"><b>Demo Kart 1</b> - mouse uzerine getirince yukari kaymali</div>
  <div class="demo-card"><b>Demo Kart 2</b> - smooth transform animasyonu</div>
  <div class="demo-card"><b>Demo Kart 3</b> - cubic-bezier easing</div>
</div>

<!-- 7. Scrollbar -->
<div class="section" data-aos="fade-up">
  <h2>7. Inceltilmis Scrollbar (mavi)</h2>
  <div class="scroll-test">
    <p>Bu kutucuga scroll edersen scrollbar mavi-ince olmali (klasik gri-kalin yerine).</p>
    <p>Lorem ipsum dolor sit amet, consectetur adipiscing elit.</p>
    <p>Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.</p>
    <p>Ut enim ad minim veniam, quis nostrud exercitation ullamco.</p>
    <p>Duis aute irure dolor in reprehenderit in voluptate velit esse.</p>
    <p>Cillum dolore eu fugiat nulla pariatur excepteur sint occaecat.</p>
    <p>Cupidatat non proident, sunt in culpa qui officia deserunt.</p>
    <p>Mollit anim id est laborum sed ut perspiciatis unde omnis.</p>
  </div>
</div>

<!-- 8. AOS Animation -->
<div class="section" data-aos="fade-up">
  <h2>8. AOS Scroll Animation</h2>
  <p>Yukari/asagi scroll yap - kartlar gorununce fade-in animasyonu yapmali.</p>
</div>

<p style="text-align:center;margin-top:30px"><a href="/" class="btn">&lt;- Ana sayfa</a></p>

<script>
async function testConfirm() {
  const ok = await ykConfirm('Bu hasta gercekten silinsin mi?', {dangerous: true});
  if (ok) ykToast.success('Onaylandi!');
  else ykToast.info('Iptal edildi');
}
async function testPrompt() {
  const name = await ykPrompt('Etiket ismi:', {placeholder: 'VIP, Akraba, vb'});
  if (name) ykToast.success('Eklendi: ' + name);
  else ykToast.info('Iptal edildi');
}
</script>
</body></html>
"""


@clinical_bp.route("/qr-image", methods=["GET"])
def qr_image_route():
    """Lokal QR kod uretici (qrcode pip paketi - internet GEREK YOK)."""
    auth = _require_doctor()
    if auth: return auth
    data = (request.args.get("data") or "").strip()
    if not data:
        return jsonify({"ok": False, "error": "data param gerekli"}), 400
    try:
        import qrcode
        import io
        from flask import send_file
        size = int(request.args.get("size", 400))
        size = max(100, min(size, 1200))
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=max(2, size // 50),
            border=2,
        )
        qr.add_data(data)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0d4f8b", back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        buf.seek(0)
        return send_file(buf, mimetype="image/png", as_attachment=False,
                         download_name="qr-yazklinik.png")
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# ============================================================
# BONUS: Hasta Self-Service Magic-Link (TC+tel -> otomatik portal)
# ============================================================
_SELF_LOGIN_RATELIMIT = {}  # ip -> [(timestamp, ...)]


def _ratelimit_ok(ip: str, max_per_window: int = 5, window_sec: int = 600) -> bool:
    """Rate limit: 10 dakikada 5 deneme/IP."""
    import time as _t
    now = _t.time()
    tries = _SELF_LOGIN_RATELIMIT.get(ip, [])
    tries = [t for t in tries if now - t < window_sec]
    if len(tries) >= max_per_window:
        _SELF_LOGIN_RATELIMIT[ip] = tries
        return False
    tries.append(now)
    _SELF_LOGIN_RATELIMIT[ip] = tries
    return True


@clinical_bp.route("/hasta-portal/self-giris", methods=["GET", "POST"])
def self_login_page():
    """Public sayfa - TC son 4 + telefon ile otomatik magic-link uretir.
    QR Klinik Duvari'ndan tarayan hasta direkt buraya gelir.

    Login GEREKMEZ - hasta hicbir doktor onayÄ± olmadan kendi dosyasÄ±nÄ± aÃ§ar.
    GÃ¼venlik: rate limit + TC son 4 + phone match.
    """
    err = ""
    ip = request.headers.get("X-Forwarded-For", request.remote_addr) or "?"

    if request.method == "POST":
        if not _ratelimit_ok(ip):
            err = "Cok fazla deneme. 10 dakika sonra tekrar deneyin."
        else:
            tc_last4 = "".join(c for c in (request.form.get("tc_last4") or "") if c.isdigit())[-4:]
            phone_raw = (request.form.get("phone") or "").strip()
            phone = "".join(c for c in phone_raw if c.isdigit())
            if phone.startswith("90") and len(phone) > 10:
                phone = phone[2:]  # 90 prefix kaldir
            if phone.startswith("0"):
                phone = phone[1:]
            birth_year = (request.form.get("birth_year") or "").strip()

            if len(tc_last4) != 4 or len(phone) < 10:
                err = "TC son 4 ve telefon (10+ rakam) zorunlu."
            else:
                # Hasta eÅŸleÅŸtir
                con = _db()
                try:
                    rows = con.execute(
                        "SELECT pd.patient_key, pd.phone, pd.tc_no, p.display_name "
                        "FROM patient_demographics pd "
                        "LEFT JOIN patients p ON p.folder_key = pd.patient_key "
                        "WHERE pd.tc_no LIKE ? AND pd.phone LIKE ? "
                        "LIMIT 5",
                        ("%" + tc_last4, "%" + phone[-10:])
                    ).fetchall()
                    matches = [dict(r) for r in rows]
                finally:
                    con.close()

                if not matches:
                    err = "Eslesme bulunamadi. TC son 4 hane ve telefonu kontrol edin."
                elif len(matches) > 1:
                    err = "Birden fazla eslesme - lutfen kliniÄŸi arayÄ±n."
                else:
                    m = matches[0]
                    # Magic-link uret (24 saat)
                    try:
                        import yazklinik_hasta_portal_agent as _hp
                        base = request.host_url.rstrip("/")
                        result = _hp.issue_magic_link(
                            patient_id=m["patient_key"],
                            phone=m["phone"] or phone,
                            base_url=base,
                            ttl_hours=24,
                            tc_last4=tc_last4,
                            birth_year=int(birth_year) if birth_year.isdigit() else None,
                            share_config={"all": True,
                                          "custom_message": "Self-service link (QR klinik duvarindan)"}
                        )
                        # PortalLoginResult dataclass - .url attribute
                        login_url = getattr(result, "url", None) or getattr(result, "magic_url", None) or ""
                        if login_url:
                            return redirect(login_url)
                        else:
                            err = "Link uretildi ama URL alinamadi. Lutfen tekrar deneyin."
                    except Exception as e:
                        err = f"Sistem hatasi: {e}"

    return render_template_string(_SELF_LOGIN_PAGE, err=err)


_SELF_LOGIN_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Hasta Portal - Self Giris</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:420px;margin:0 auto;padding:20px;
  background:linear-gradient(135deg,#0d4f8b 0%,#0a8a76 100%);min-height:100vh;color:#122236}
.card{background:#fff;border-radius:14px;padding:24px;box-shadow:0 8px 24px rgba(0,0,0,0.15)}
h1{color:#0d4f8b;font-size:22px;margin-bottom:6px}
.sub{color:#5e7185;font-size:14px;margin-bottom:18px}
.info{background:#e2eef7;border-left:4px solid #1769aa;padding:10px 14px;border-radius:0 8px 8px 0;
  margin-bottom:14px;font-size:13px;color:#0d4f8b}
label{display:block;font-size:13px;font-weight:600;color:#0d4f8b;margin-bottom:4px;margin-top:12px}
input{width:100%;padding:14px;font-size:18px;border:2px solid #cdd9e3;border-radius:8px;
  font-family:inherit;letter-spacing:2px;text-align:center}
input:focus{border-color:#1769aa;outline:none}
.btn{width:100%;background:linear-gradient(135deg,#0d4f8b,#0a8a76);color:#fff;border:none;
  padding:14px;border-radius:10px;font-size:16px;font-weight:700;margin-top:18px;cursor:pointer}
.err{background:#fee2e2;color:#b3261e;padding:12px;border-radius:8px;margin-bottom:12px;font-weight:600;font-size:13px}
small{display:block;color:#5e7185;font-size:11px;margin-top:14px;text-align:center;line-height:1.5}
</style></head><body>
<div class="card">
<h1>Hasta Portal Girisi</h1>
<div class="sub"><b>Op. Dr. Hakan Yaz</b> - Kadin Hastaliklari ve Dogum</div>

<div class="info">
  <b>Bilgilerinizi girin:</b><br>
  Dosyanizdaki bilgilerle eslesirse otomatik portala alirsiniz (24 saat gecerli).
</div>

{% if err %}<div class="err">{{err}}</div>{% endif %}

<form method="POST" autocomplete="off">
  <label>TC Kimlik Son 4 Hane</label>
  <input type="tel" name="tc_last4" maxlength="4" pattern="[0-9]{4}" required
         inputmode="numeric" placeholder="****" autofocus>

  <label>Telefon (5XX XXX XX XX)</label>
  <input type="tel" name="phone" required inputmode="tel" placeholder="5XX XXX XX XX">

  <label>Dogum Yili (opsiyonel - extra guvenlik)</label>
  <input type="tel" name="birth_year" maxlength="4" pattern="[0-9]{4}"
         inputmode="numeric" placeholder="YYYY">

  <button type="submit" class="btn">Dosyami Ac</button>
</form>

<small>
  Bilgileriniz dosyada kayitlilarla eslesmezse giris yapamazsiniz.<br>
  Sorun olursa kliniÄŸi arayÄ±n. Link 24 saat gecerlidir.
</small>
</div>
</body></html>
"""


_QR_KLINIK_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>QR Klinik Duvari</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:800px;margin:0 auto;padding:18px;background:#f5f8fb}
h1{color:#0d4f8b}
.card{background:#fff;border-radius:12px;padding:18px;margin-bottom:14px;box-shadow:0 2px 6px rgba(0,0,0,0.05)}
input{padding:12px;border:2px solid #1769aa;border-radius:8px;font-size:14px;width:100%;margin-bottom:10px}
.btn{background:#1769aa;color:#fff;border:none;padding:10px 16px;border-radius:8px;font-weight:600;cursor:pointer}
.qr-display{text-align:center;padding:30px;background:#fff;border-radius:12px;border:2px dashed #cdd9e3}
.qr-display img{max-width:400px;width:100%;height:auto;border-radius:8px}
.print-card{background:#fff;border:3px solid #0d4f8b;border-radius:20px;padding:40px;text-align:center;margin:20px auto;max-width:500px}
.print-card h2{color:#0d4f8b;margin:0 0 14px;font-size:28px}
.print-card .qr-big{margin:20px auto;background:#fff;padding:16px;border-radius:12px}
.print-card .qr-big img{max-width:300px;width:100%}
@media print {
  body{background:#fff;padding:0;max-width:none}
  .card,.btn,.no-print{display:none !important}
  .print-card{box-shadow:none;border:3px solid #000}
}
</style></head><body>
<h1 class="no-print">QR Klinik Duvari</h1>
<div style="color:#5e7185;margin-bottom:14px" class="no-print">A4 yazdir -&gt; kliniÄŸe yapistir. Hastalar telefonuyla tarar -&gt; randevu/portal sayfasi acilir.</div>

<div class="card no-print">
  <label style="font-weight:700;color:#0d4f8b;display:block;margin-bottom:6px">Hedef URL:</label>
  <input type="url" id="target" value="{{target}}" placeholder="https://...">
  <small style="color:#5e7185;display:block;margin-bottom:10px">Onerilen: <a href="?target={{base}}/randevu-al">Public Randevu</a> | <a href="?target={{base}}/hasta-portal">Hasta Portal</a></small>
  <button class="btn" onclick="updateQR()">Guncelle</button>
  <button class="btn" style="background:#0a8a76" onclick="window.print()">A4 Yazdir</button>
</div>

<div class="print-card">
  <h2>Op. Dr. Hakan YAZ</h2>
  <div style="color:#5e7185;font-size:16px;margin-bottom:4px">Kadin Hastaliklari ve Dogum</div>
  <div style="font-size:18px;color:#0a8a76;font-weight:700;margin:14px 0">Randevu icin telefonunuzla taratin</div>
  <div class="qr-big">
    <img id="qrImg" src="/qr-image?data={{target|urlencode}}&size=500" alt="QR">
  </div>
  <div style="font-size:14px;color:#5e7185;margin-top:10px;word-break:break-all">{{target}}</div>
</div>

<p class="no-print"><a href="/">&lt;- Ana sayfa</a></p>

<script>
function updateQR() {
  const t = document.getElementById('target').value.trim();
  if (!t) return;
  location.href = '/qr-klinik?target=' + encodeURIComponent(t);
}
</script></body></html>
"""

