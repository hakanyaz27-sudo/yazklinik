"""Medula (SGK Provizyon) Entegrasyon Stub.

Medula SGK'nin saglik tesisleri icin provizyon + e-recete + rapor sistemi.
Bu modul yapi iskeletini sunar - production icin SGK SOAP API gerek.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-medula"

MEDULA_USERNAME = os.environ.get("MEDULA_USERNAME", "")
MEDULA_PASSWORD = os.environ.get("MEDULA_PASSWORD", "")
MEDULA_TESIS_KODU = os.environ.get("MEDULA_TESIS_KODU", "")
MEDULA_ENDPOINT = os.environ.get("MEDULA_ENDPOINT",
                                   "https://medeczane.sgk.gov.tr/eczane/")


@dataclass
class MedulaProvizyon:
    tc: str
    provizyon_no: str = ""
    aktif: bool = False
    sigorta_tipi: str = ""    # 4A | 4B | 4C | yesil_kart
    katki_pay_pct: int = 0
    response_raw: Dict[str, Any] = field(default_factory=dict)


def is_configured() -> bool:
    return bool(MEDULA_USERNAME and MEDULA_PASSWORD and MEDULA_TESIS_KODU)


def query_provizyon(tc: str) -> MedulaProvizyon:
    """SGK provizyon sorgula (stub)."""
    if not is_configured():
        return MedulaProvizyon(tc=tc, response_raw={"note": "Medula creds eksik"})
    # Production: SOAP cagrisi
    return MedulaProvizyon(tc=tc, aktif=True, sigorta_tipi="4A", katki_pay_pct=20,
                            provizyon_no=f"PV-{int(datetime.now().timestamp())}")


def submit_recete(tc: str, drugs: List[Dict[str, Any]],
                   tani_kodlari: List[str]) -> Dict[str, Any]:
    """E-recete Medula'ya bildir (stub)."""
    if not is_configured():
        return {"ok": False, "note": "Medula creds eksik - stub", "drugs": drugs}
    return {"ok": True, "recete_no": f"RX-{int(datetime.now().timestamp())}",
            "drugs": drugs, "tani": tani_kodlari}


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "configured": is_configured(),
            "endpoint": MEDULA_ENDPOINT}


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
