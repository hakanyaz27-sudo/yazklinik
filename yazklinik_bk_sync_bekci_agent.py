"""BulutKlinik Sync Bekci Ajani.

BulutKlinik OAuth token / cookie / CDP koprusu bagli mi diye periyodik soran
ve kopuklugu doktora bildiren bekci. Ayrica son senkron zamanini hatirlayip
"X saattir senkron yok" uyarisi cikarir.

Ne yapar:
    - Saglik durumu kaydi: ok / stale / expired / unreachable
    - Son basarili senkrondan bu yana gecen sure
    - Kac arka arkaya hata aldi
    - Onerilen aksiyon (token yenile, cookie tazele, CDP yeniden bagla)

Asla yapmaz:
    - Otomatik sifre yenilemez
    - Token saklamaz (web layer state'i tutar)
    - BulutKlinik panelinde tarama yapmaz

Stdlib only. Web layer 5 dakikada bir check_status(...) cagirir.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.16-bk-sync-bekci"
SOURCE_LABEL = "BulutKlinik baglanti saglik kontrolu"

HEALTH_OK = "ok"
HEALTH_STALE = "stale"
HEALTH_EXPIRED = "expired"
HEALTH_UNREACHABLE = "unreachable"
HEALTH_UNKNOWN = "unknown"

# Esikler (dakika)
STALE_AFTER_MIN = 60          # 1 saat senkron yoksa "stale"
WARN_CONSECUTIVE_FAILURES = 3
PAGE_DOCTOR_AFTER_FAILURES = 6


@dataclass
class SyncProbe:
    """Web layer'in son bildirdigi durum."""
    last_success_at: Optional[str] = None      # ISO datetime
    last_attempt_at: Optional[str] = None
    consecutive_failures: int = 0
    auth_mode: str = "oauth"                   # "oauth" | "cookie" | "cdp"
    last_error: Optional[str] = None
    token_expires_at: Optional[str] = None     # ISO datetime
    reachable: bool = True


@dataclass
class HealthReport:
    status: str
    minutes_since_success: Optional[int]
    consecutive_failures: int
    auth_mode: str
    last_error: Optional[str]
    suggested_action: str
    should_alert_doctor: bool
    should_page_doctor: bool
    checked_at: str = ""
    agent_version: str = AGENT_VERSION


def _minutes_between(iso_from: Optional[str], iso_to: datetime) -> Optional[int]:
    if not iso_from:
        return None
    try:
        a = datetime.fromisoformat(iso_from)
    except Exception:
        return None
    delta = iso_to - a
    return int(delta.total_seconds() // 60)


def _suggested_action(status: str, auth_mode: str, last_error: Optional[str]) -> str:
    if status == HEALTH_OK:
        return "Aksiyon gerek yok."
    if status == HEALTH_EXPIRED:
        if auth_mode == "oauth":
            return "Token suresi dolmus. /bulutklinik > 'Token yenile' calistirin."
        if auth_mode == "cookie":
            return "Cookie suresi dolmus. /bulutklinik > 'Cookie ile baglan' tekrar yapilmali."
        return "Yetkilendirme yenilenmeli."
    if status == HEALTH_STALE:
        return "1 saatten uzun sure senkron yok. Manuel 'Baglanti Testi' baslatin."
    if status == HEALTH_UNREACHABLE:
        return "Sunucuya erisilemiyor (ag/proxy/SSL). Internet baglantisini kontrol edin."
    if status == HEALTH_UNKNOWN:
        return "Hic basarili senkron yok. /bulutklinik > 'Baglanti Testi' calistirin."
    return last_error or "Bilinmeyen sebep; log dosyasini kontrol edin."


def check_status(probe: SyncProbe, now: Optional[datetime] = None) -> HealthReport:
    """Probe -> rapor."""
    now = now or datetime.now()
    minutes_since = _minutes_between(probe.last_success_at, now)

    # 1. Token expired explicit
    token_expired = False
    if probe.token_expires_at:
        try:
            exp = datetime.fromisoformat(probe.token_expires_at)
            token_expired = exp <= now
        except Exception:
            pass

    if token_expired:
        status = HEALTH_EXPIRED
    elif not probe.reachable:
        status = HEALTH_UNREACHABLE
    elif probe.last_success_at is None:
        status = HEALTH_UNKNOWN
    elif minutes_since is not None and minutes_since > STALE_AFTER_MIN:
        status = HEALTH_STALE
    elif probe.consecutive_failures >= WARN_CONSECUTIVE_FAILURES:
        status = HEALTH_STALE
    else:
        status = HEALTH_OK

    should_alert = status != HEALTH_OK
    should_page = (
        status in (HEALTH_EXPIRED, HEALTH_UNREACHABLE)
        or probe.consecutive_failures >= PAGE_DOCTOR_AFTER_FAILURES
    )

    return HealthReport(
        status=status,
        minutes_since_success=minutes_since,
        consecutive_failures=int(probe.consecutive_failures),
        auth_mode=str(probe.auth_mode),
        last_error=probe.last_error,
        suggested_action=_suggested_action(status, probe.auth_mode, probe.last_error),
        should_alert_doctor=should_alert,
        should_page_doctor=should_page,
        checked_at=now.isoformat(timespec="seconds"),
    )


def to_audit_payload(report: HealthReport) -> Dict[str, Any]:
    payload = asdict(report)
    payload["action"] = f"bk_sync:{report.status}"
    return payload


if __name__ == "__main__":
    now = datetime.now()
    cases = [
        ("Saglikli", SyncProbe(
            last_success_at=(now - timedelta(minutes=5)).isoformat(timespec="seconds"),
            consecutive_failures=0, reachable=True,
        )),
        ("Stale (90 dk)", SyncProbe(
            last_success_at=(now - timedelta(minutes=90)).isoformat(timespec="seconds"),
            consecutive_failures=0, reachable=True,
        )),
        ("Token expired", SyncProbe(
            last_success_at=(now - timedelta(minutes=10)).isoformat(timespec="seconds"),
            token_expires_at=(now - timedelta(minutes=1)).isoformat(timespec="seconds"),
            reachable=True,
        )),
        ("Ag yok", SyncProbe(last_success_at=(now - timedelta(minutes=2)).isoformat(timespec="seconds"),
                              reachable=False, last_error="ConnectionError")),
        ("Hic baglanmadi", SyncProbe(last_success_at=None, reachable=True)),
    ]
    for name, probe in cases:
        r = check_status(probe, now=now)
        print(f"[{name:20}] {r.status:11} alert={r.should_alert_doctor} page={r.should_page_doctor} -> {r.suggested_action}")
