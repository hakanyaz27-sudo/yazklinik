"""MHRS (Merkezi Hekim Randevu Sistemi) Entegrasyon Stub.

MHRS resmi T.C. Saglik Bakanligi randevu sistemidir.
Bu modul muayene haneden kendi randevu sistemine import + export iskeletini sunar.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-mhrs"

MHRS_API_KEY = os.environ.get("MHRS_API_KEY", "")
MHRS_HEKIM_KODU = os.environ.get("MHRS_HEKIM_KODU", "")


@dataclass
class MHRSAppointment:
    tc: str
    hasta_adi: str
    tarih: str
    saat: str
    durum: str = "randevulu"  # randevulu | iptal | tamam
    branş: str = "Kadin Dogum"


def is_configured() -> bool:
    return bool(MHRS_API_KEY and MHRS_HEKIM_KODU)


def import_today() -> List[MHRSAppointment]:
    """Bugunun MHRS randevularini cek (stub)."""
    if not is_configured():
        return []
    # Production: requests.get + parse JSON
    return []


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "configured": is_configured()}


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
