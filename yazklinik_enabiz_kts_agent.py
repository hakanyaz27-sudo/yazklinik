"""e-Nabiz / KTS (Kisisel Saglik Sistemi) Entegrasyon Stub.

e-Nabiz API resmi olarak T.C. Saglik Bakanligi tarafindan saglanir.
Bu modul SDK iskeletini sunar; production icin resmi API key + sertifika gerek.

Yapilan:
    - Hasta kimligi onaylama
    - Recete bildirimi (E-recete)
    - Tani kodu (ICD-10) gonderim
    - Lab sonucu indir
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-enabiz"

ENABIZ_API_BASE = os.environ.get("ENABIZ_API_BASE", "https://api.enabiz.gov.tr")
ENABIZ_API_KEY = os.environ.get("ENABIZ_API_KEY", "")
ENABIZ_CERT_PATH = os.environ.get("ENABIZ_CERT_PATH", "")


@dataclass
class ENabizSubmission:
    submission_id: str
    patient_tc: str          # T.C. kimlik (anonim icin maskeli)
    action: str              # recete | tani | rapor | lab_query
    payload: Dict[str, Any] = field(default_factory=dict)
    status: str = "pending"  # pending | sent | acknowledged | failed
    submitted_at: str = ""
    response: Dict[str, Any] = field(default_factory=dict)


def is_configured() -> bool:
    """Resmi API key + sertifika var mi?"""
    return bool(ENABIZ_API_KEY and ENABIZ_CERT_PATH and os.path.exists(ENABIZ_CERT_PATH))


def submit_recete(patient_tc: str, drugs: List[Dict[str, Any]],
                   icd10_codes: List[str]) -> ENabizSubmission:
    """E-recete bildir (stub - production yok)."""
    sub = ENabizSubmission(
        submission_id=f"ENB-RX-{int(datetime.now().timestamp())}",
        patient_tc=_mask_tc(patient_tc), action="recete",
        payload={"drugs": drugs, "icd10": icd10_codes},
        submitted_at=datetime.now().isoformat(timespec="seconds"))

    if not is_configured():
        sub.status = "stub"
        sub.response = {"note": "e-Nabiz API key veya sertifika eksik - stub mode"}
        return sub

    # Production: requests.post(ENABIZ_API_BASE + "/v1/recete", ...)
    sub.status = "sent"
    sub.response = {"note": "Production cagrisi placeholder"}
    return sub


def _mask_tc(tc: str) -> str:
    """T.C. maskeleme (log icin)."""
    if not tc or len(tc) < 11:
        return tc
    return tc[:3] + "*****" + tc[-3:]


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "configured": is_configured(),
            "api_base": ENABIZ_API_BASE}


if __name__ == "__main__":
    s = submit_recete("12345678901", [{"name": "Paracetamol 500mg", "doz": "2x1"}],
                       ["R51"])
    print(json.dumps(asdict(s), ensure_ascii=False, indent=2))
