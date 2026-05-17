"""PHQ-9 Postpartum / Depresyon Tarama Ajani.

Patient Health Questionnaire-9 (9 soru, 0-27 puan).
Postpartum (lohusa) hastalar icin onemli; loglar + uyari uretir.

Klinik kullanım:
    - Hasta cevaplari (0-3 her soru) ver
    - Skor + risk seviyesi + oneri
    - Yuksek riskte (>=15) doktora uyari + ruh sagligi sevki
    - Soru 9 (intihar dusuncesi) >=1 ise: ACIL uyari
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-phq9"


PHQ9_QUESTIONS = [
    "Az ilgi/keyif aldigim seyleri yapmaktan zevk almama",
    "Kendimi cokmus, depresif veya umutsuz hissetme",
    "Uykuya dalmakta zorluk veya cok fazla uyuma",
    "Yorgun hissetme veya enerji eksikligi",
    "Istahsizlik veya asiri yeme",
    "Kendim hakkinda kotu hisler - basarisiz hissetme",
    "Konsantrasyon zorlugu (TV, gazete vs)",
    "Yavas hareket etme / huzursuzluk",
    "Olmek/kendine zarar verme dusunceleri",
]
SCORE_LABELS = {0: "Hicbir zaman", 1: "Birkac gun",
                  2: "Yarisindan fazla", 3: "Hemen her gun"}


@dataclass
class PHQ9Result:
    patient_id: str
    test_date: str
    answers: List[int]
    total_score: int
    severity: str          # minimal | mild | moderate | moderate-severe | severe
    suicide_risk: bool
    recommendations: List[str] = field(default_factory=list)
    urgent_referral: bool = False
    agent_version: str = AGENT_VERSION


def score(patient_id: str, answers: List[int]) -> PHQ9Result:
    """9 cevap (0-3 her biri) -> skor + uyari."""
    if len(answers) != 9:
        raise ValueError("PHQ-9: 9 cevap gerek (0-3)")
    for a in answers:
        if a < 0 or a > 3:
            raise ValueError(f"Her cevap 0-3 olmali: {a}")

    total = sum(answers)
    result = PHQ9Result(
        patient_id=patient_id,
        test_date=datetime.now().date().isoformat(),
        answers=answers, total_score=total,
        severity="minimal", suicide_risk=False)

    # Severity (DSM-5 / NICE guideline)
    if total <= 4: result.severity = "minimal"
    elif total <= 9: result.severity = "mild"
    elif total <= 14: result.severity = "moderate"
    elif total <= 19: result.severity = "moderate-severe"
    else: result.severity = "severe"

    # Intihar riski (Q9 >= 1)
    if answers[8] >= 1:
        result.suicide_risk = True
        result.urgent_referral = True
        result.recommendations.append(
            "ACIL: Intihar dusuncesi pozitif - psikiyatri konsult, ailesini bilgilendir")

    # Genel oneriler
    if total >= 15:
        result.urgent_referral = True
        result.recommendations.append("Ruh sagligi uzmanina yonlendir")
        result.recommendations.append("Antidepresan (SSRI) degerlendirilmeli")
    elif total >= 10:
        result.recommendations.append("Takip + psikolojik destek oner")
        result.recommendations.append("4 hafta sonra tekrar PHQ-9 uygula")
    elif total >= 5:
        result.recommendations.append("Hafif depresyon - destek + egzersiz")
        result.recommendations.append("8 hafta sonra tekrar test")
    else:
        result.recommendations.append("Risk yok, rutin takip")

    return result


def get_questionnaire() -> Dict[str, Any]:
    """Frontend icin soru listesi + cevap secenekleri."""
    return {
        "title": "PHQ-9 Depresyon Tarama (Son 2 Hafta)",
        "intro": "Son 2 haftada asagidakilerden hangileri sizi ne kadar rahatsiz etti?",
        "questions": [{"id": i+1, "text": q} for i, q in enumerate(PHQ9_QUESTIONS)],
        "options": [{"value": v, "label": l} for v, l in SCORE_LABELS.items()],
    }


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "questions": len(PHQ9_QUESTIONS)}


if __name__ == "__main__":
    # Demo: orta-siddetli vaka
    r = score("PAT-001", [2, 2, 3, 2, 1, 2, 2, 1, 1])
    print(f"Skor: {r.total_score} | Seviye: {r.severity}")
    print(f"Intihar riski: {r.suicide_risk}")
    for rec in r.recommendations:
        print(f"  - {rec}")
