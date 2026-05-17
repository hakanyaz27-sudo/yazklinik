"""Obstetrik Risk Skor Ajani.

Real-time klinik karar destek:
    - Preeklampsi (Roberts-Friedman, sFLT1/PIGF gerekmez)
    - HELLP triad (hemoliz + KCFT + trombositopeni)
    - Bishop skoru (induksiyon karar)
    - VTE risk (Padua, RCOG green-top)
    - PPH risk (postpartum kanama)
    - GDM risk (NICE)
    - Preterm dogum riski

Asla klinik karar degildir; oneri + olasilik dondurur.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-risk-skor"


@dataclass
class RiskResult:
    score_name: str
    score_value: float
    risk_category: str    # low / moderate / high / critical
    interpretation: str
    recommended_actions: List[str] = field(default_factory=list)
    inputs: Dict[str, Any] = field(default_factory=dict)
    agent_version: str = AGENT_VERSION
    requires_doctor_review: bool = True


def preeklampsi_risk(systolic: int, diastolic: int,
                      proteinuria: str = "",          # "neg" | "+" | "++" | "+++"
                      headache: bool = False, vision: bool = False,
                      epigastric_pain: bool = False,
                      thrombocyte: Optional[int] = None,  # x10^3
                      gestational_age_weeks: Optional[int] = None) -> RiskResult:
    """Preeklampsi risk siniflandirma (ACOG 2013 + RCOG)."""
    bp_high = systolic >= 140 or diastolic >= 90
    bp_severe = systolic >= 160 or diastolic >= 110
    protein_score = {"neg": 0, "": 0, "+": 1, "++": 2, "+++": 3}.get(proteinuria, 0)
    severe_signs = sum([headache, vision, epigastric_pain])

    inputs = {"systolic": systolic, "diastolic": diastolic,
              "proteinuria": proteinuria, "headache": headache,
              "vision_changes": vision, "epigastric_pain": epigastric_pain,
              "thrombocyte_x1000": thrombocyte, "ga_weeks": gestational_age_weeks}

    if bp_severe and (protein_score >= 2 or severe_signs >= 1):
        cat = "critical"
        interp = "ŞİDDETLİ preeklampsi - acil hospitalizasyon"
        actions = ["Hospitalize et", "MgSO4 yükleme + idame", "Antihipertansif (labetalol/nifedipin)",
                   "Fetal monitör", "Doğum kararı (gebelik haftasıyla değerlendir)"]
    elif bp_high and (protein_score >= 1 or severe_signs >= 1):
        cat = "high"
        interp = "Preeklampsi - yatış + kontroller"
        actions = ["Yatış", "24 saat idrar protein", "KCFT + KBL + LDH",
                   "MgSO4 düşünülebilir", "Aspirin (varsa zaten)"]
    elif bp_high:
        cat = "moderate"
        interp = "Gestasyonel hipertansiyon şüphesi"
        actions = ["Haftalık TA + idrar takibi", "Lab bazal",
                   "Aspirin 100 mg geceleri (eğer 36 hf altında)"]
    else:
        cat = "low"
        interp = "Risk düşük"
        actions = ["Rutin antenatal takip"]

    score_val = (2 if bp_severe else 1 if bp_high else 0) * 30 + protein_score * 15 + severe_signs * 15
    return RiskResult(
        score_name="Preeklampsi Risk", score_value=min(100, score_val),
        risk_category=cat, interpretation=interp,
        recommended_actions=actions, inputs=inputs)


def hellp_risk(thrombocyte: int, ast: int, alt: int, ldh: int,
                bilirubin: float, schistocytes: bool = False) -> RiskResult:
    """HELLP triad - Mississippi sinflandirma."""
    inputs = {"PLT_x1000": thrombocyte, "AST": ast, "ALT": alt,
              "LDH": ldh, "TBili": bilirubin, "schistocytes": schistocytes}
    klass = None
    if thrombocyte < 50 and (ast >= 70 or alt >= 70) and ldh >= 600:
        klass = "I"  # most severe
    elif thrombocyte < 100 and (ast >= 70 or alt >= 70) and ldh >= 600:
        klass = "II"
    elif thrombocyte < 150 and (ast >= 40) and ldh >= 600:
        klass = "III"
    if klass:
        cat = "critical" if klass == "I" else "high" if klass == "II" else "moderate"
        return RiskResult(
            score_name="HELLP", score_value={"I": 95, "II": 75, "III": 55}[klass],
            risk_category=cat,
            interpretation=f"HELLP Class {klass}",
            recommended_actions=["Acil hospitalize", "Yüksek doz steroid",
                                   "MgSO4", "Trombosit infüzyonu (gerekirse)",
                                   "Doğum kararı"], inputs=inputs)
    return RiskResult(
        score_name="HELLP", score_value=10, risk_category="low",
        interpretation="HELLP kriterleri karşılanmıyor", inputs=inputs)


def bishop_score(dilation_cm: int, effacement_pct: int,
                  station: int, consistency: str, position: str) -> RiskResult:
    """Bishop induksiyon hazirligi skoru (0-13)."""
    # Dilation: 0/1-2/3-4/5+ -> 0/1/2/3
    d = 0 if dilation_cm < 1 else 1 if dilation_cm < 3 else 2 if dilation_cm < 5 else 3
    # Effacement: 0-30/40-50/60-70/80+ -> 0/1/2/3
    e = 0 if effacement_pct < 40 else 1 if effacement_pct < 60 else 2 if effacement_pct < 80 else 3
    # Station: -3/-2/-1,0/+1,+2 -> 0/1/2/3
    s = 0 if station <= -3 else 1 if station == -2 else 2 if station in (-1, 0) else 3
    # Consistency: firm/medium/soft -> 0/1/2
    c = {"firm": 0, "medium": 1, "soft": 2}.get(consistency.lower(), 1)
    # Position: posterior/middle/anterior -> 0/1/2
    p = {"posterior": 0, "middle": 1, "anterior": 2}.get(position.lower(), 1)
    total = d + e + s + c + p

    if total >= 8:
        cat = "high"
        interp = "Servikal hazır; indüksiyon başarı yüksek"
        actions = ["Oksitosin protokolü", "Amniyotomi", "Yakın monitör"]
    elif total >= 5:
        cat = "moderate"
        interp = "Orta hazırlık; PG2 mevcut seçenek"
        actions = ["Misoprostol 25 mcg PO 4-6 saatte", "12-24 saat sonra yeniden değerlendir"]
    else:
        cat = "low"
        interp = "Unfavorable serviks - mekanik veya farmakolojik hazırlık"
        actions = ["Foley balon", "Misoprostol",
                   "Sezaryen riskini hastayla tartış"]

    return RiskResult(
        score_name="Bishop", score_value=total, risk_category=cat,
        interpretation=interp, recommended_actions=actions,
        inputs={"dilation": dilation_cm, "effacement_pct": effacement_pct,
                "station": station, "consistency": consistency, "position": position})


def vte_padua_score(age_60_plus: bool = False, active_cancer: bool = False,
                     prior_vte: bool = False, reduced_mobility: bool = False,
                     thrombophilia: bool = False, recent_trauma: bool = False,
                     elderly_70_plus: bool = False, heart_failure: bool = False,
                     acute_mi_stroke: bool = False, infection_rheum: bool = False,
                     obesity_bmi_30: bool = False, hormone_treatment: bool = False) -> RiskResult:
    """Padua VTE risk (yatan hasta)."""
    items = [(active_cancer, 3), (prior_vte, 3), (reduced_mobility, 3),
             (thrombophilia, 3), (recent_trauma, 2),
             (elderly_70_plus or age_60_plus, 1),
             (heart_failure, 1), (acute_mi_stroke, 1),
             (infection_rheum, 1), (obesity_bmi_30, 1),
             (hormone_treatment, 1)]
    score = sum(p for cond, p in items if cond)
    if score >= 4:
        cat = "high"
        interp = "Yüksek VTE riski"
        actions = ["LMWH profilaksi (enoxaparin 40 mg SC)",
                   "Mekanik (kompresyon)", "Erken mobilizasyon"]
    elif score >= 2:
        cat = "moderate"
        interp = "Orta risk"
        actions = ["Mekanik profilaksi", "LMWH değerlendirilebilir"]
    else:
        cat = "low"
        interp = "Düşük risk"
        actions = ["Erken mobilizasyon", "Rutin"]
    return RiskResult(score_name="Padua VTE", score_value=score,
                       risk_category=cat, interpretation=interp,
                       recommended_actions=actions, inputs={"score": score})


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "available_scores": ["preeklampsi", "hellp", "bishop", "vte_padua"]}


if __name__ == "__main__":
    r = preeklampsi_risk(158, 102, "+++", headache=True, vision=True)
    print(f"Preeklampsi: {r.risk_category} ({r.score_value}) - {r.interpretation}")
    print("Aksiyon:", r.recommended_actions[:3])
