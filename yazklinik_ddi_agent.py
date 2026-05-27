"""Drug-Drug Interaction (DDI) Ajani.

Recete yazinca otomatik ilac-ilac etkilesim kontrolu.
- Mevcut TR ilac katalogu (static/tr_ilac_katalogu.txt) baz
- Bilinen kritik etkilesim cifti (genisletilebilir DB)
- Gebelik kategorisi (FDA A/B/C/D/X) uyari
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


AGENT_VERSION = "2026.05.17-ddi"


# Kritik DDI ciftleri (basit DB - genisletilebilir)
CRITICAL_DDI: Dict[Tuple[str, str], Dict[str, str]] = {
    ("warfarin", "asetilsalisilik asit"): {
        "severity": "major", "effect": "Kanama riski belirgin artar",
        "action": "Birleştirmeden kaçın veya INR çok sık takip"
    },
    ("warfarin", "ibuprofen"): {
        "severity": "major", "effect": "GI kanama riski",
        "action": "Asetaminofen tercih et"
    },
    ("metformin", "iv kontrast"): {
        "severity": "major", "effect": "Laktik asidoz",
        "action": "Kontrast öncesi-sonrası 48 saat metformin durdur"
    },
    ("methotrexate", "amoksisilin"): {
        "severity": "major", "effect": "Methotrexate seviyesi artar",
        "action": "Penisiline alternatif kullan"
    },
    ("methotrexate", "trimetoprim"): {
        "severity": "major", "effect": "Folik asit antagonizmi",
        "action": "Birleştirmeden kaçın"
    },
    ("ssri", "tramadol"): {
        "severity": "major", "effect": "Serotonin sendromu",
        "action": "Birleştirmeden kaçın veya yakın gözlem"
    },
    ("ssri", "linezolid"): {
        "severity": "major", "effect": "Serotonin sendromu",
        "action": "2 hafta washout şart"
    },
    ("kombine ohk", "rifampin"): {
        "severity": "moderate", "effect": "OHK etkinliği azalır",
        "action": "Alternatif kontrasepsiyon (kondom)"
    },
    ("levothyroxine", "demir"): {
        "severity": "moderate", "effect": "Levothyroxine emilimi azalır",
        "action": "4 saat ara ile al"
    },
    ("levothyroxine", "kalsiyum"): {
        "severity": "moderate", "effect": "Levothyroxine emilimi azalır",
        "action": "4 saat ara ile al"
    },
    ("oxytocin", "prostaglandin"): {
        "severity": "major", "effect": "Hipertonik kontraksiyon, uterus rüptürü",
        "action": "PGE2 dozdan 4 saat sonra oksitosin başlanabilir"
    },
}

# Gebelik FDA kategorileri (kritik liste)
PREGNANCY_CATEGORY_X = {
    "isotretinoin", "thalidomide", "warfarin", "valproate",
    "ribavirin", "methotrexate", "misoprostol",  # not for ongoing pregnancy
    "leflunomide", "raloxifene", "atorvastatin",
}
PREGNANCY_CATEGORY_D = {
    "ace inhibitor", "lisinopril", "enalapril", "captopril",
    "lithium", "tetracycline", "doxycycline", "minocycline",
    "phenytoin", "carbamazepine", "amiodarone", "spironolactone",
}


@dataclass
class DDIWarning:
    drug_a: str
    drug_b: str
    severity: str            # major | moderate | minor
    effect: str
    action: str


@dataclass
class PregnancyWarning:
    drug: str
    category: str            # X | D | C
    message: str


@dataclass
class DDIResult:
    drugs: List[str]
    is_pregnant: bool
    ddi_warnings: List[DDIWarning] = field(default_factory=list)
    pregnancy_warnings: List[PregnancyWarning] = field(default_factory=list)
    overall_safe: bool = True
    requires_doctor_review: bool = True
    agent_version: str = AGENT_VERSION


def _normalize(name: str) -> str:
    return (name or "").strip().lower().replace("ı", "i").replace("İ", "i")


def check_interactions(drugs: List[str], is_pregnant: bool = False,
                        trimester: Optional[int] = None) -> DDIResult:
    """Ilac listesi DDI + gebelik kontrolu."""
    norm = [_normalize(d) for d in drugs]
    result = DDIResult(drugs=drugs, is_pregnant=is_pregnant)

    # Cift cift kontrol
    for i, a in enumerate(norm):
        for j, b in enumerate(norm):
            if i >= j:
                continue
            for (k_a, k_b), info in CRITICAL_DDI.items():
                if (k_a in a and k_b in b) or (k_b in a and k_a in b):
                    result.ddi_warnings.append(DDIWarning(
                        drug_a=drugs[i], drug_b=drugs[j],
                        severity=info["severity"], effect=info["effect"],
                        action=info["action"]))

    # Gebelik kategorisi
    if is_pregnant:
        for orig, n in zip(drugs, norm):
            for x in PREGNANCY_CATEGORY_X:
                if x in n:
                    result.pregnancy_warnings.append(PregnancyWarning(
                        drug=orig, category="X",
                        message="FDA Kategori X: Gebede KONTRENDİKE"))
                    break
            else:
                for d_drug in PREGNANCY_CATEGORY_D:
                    if d_drug in n:
                        result.pregnancy_warnings.append(PregnancyWarning(
                            drug=orig, category="D",
                            message="FDA Kategori D: Risk var, fayda lehte ise"))
                        break

    result.overall_safe = (not any(w.severity == "major" for w in result.ddi_warnings)
                            and not any(w.category == "X" for w in result.pregnancy_warnings))
    return result


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "ddi_pairs_db": len(CRITICAL_DDI),
            "pregnancy_x_drugs": len(PREGNANCY_CATEGORY_X),
            "pregnancy_d_drugs": len(PREGNANCY_CATEGORY_D)}


if __name__ == "__main__":
    r = check_interactions(["Warfarin 5mg", "Asetilsalisilik asit 100mg", "Atorvastatin"],
                            is_pregnant=True)
    print(f"DDI: {len(r.ddi_warnings)}, Gebelik: {len(r.pregnancy_warnings)}, Safe: {r.overall_safe}")
    for w in r.ddi_warnings:
        print(f"  ! {w.drug_a} + {w.drug_b}: {w.effect}")
    for w in r.pregnancy_warnings:
        print(f"  ! {w.drug} ({w.category}): {w.message}")
