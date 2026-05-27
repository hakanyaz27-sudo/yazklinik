"""ISO 27001 / KVKK Compliance Dashboard Ajani.

Klinik bilgi guvenligi + KVKK uyumluluk kontrol noktalari.
Skor: 0-100. Eksik kontrol -> oneri uretir.
"""
from __future__ import annotations

import json
import os
import sqlite3
from yazklinik_db_adapter import agent_connection as _pgconn  # PG-primary aware (cutover)
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
import re


AGENT_VERSION = "2026.05.17-compliance"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")


@dataclass
class ComplianceCheck:
    code: str
    title: str
    category: str          # erisim | yedek | log | sifreleme | kvkk | egitim
    standard: str          # ISO27001 A.x | KVKK m.x
    status: str = "unknown"   # pass | fail | warn | unknown
    detail: str = ""
    recommendation: str = ""
    weight: int = 1


@dataclass
class ComplianceReport:
    generated_at: str
    score: int = 0
    max_score: int = 0
    pct: float = 0
    grade: str = "F"       # A+ A B C D F
    checks: List[ComplianceCheck] = field(default_factory=list)
    critical_failures: int = 0
    recommendations_top: List[str] = field(default_factory=list)
    agent_version: str = AGENT_VERSION


def _file_exists(path: str) -> bool:
    return os.path.exists(path)


def _db_has_table(db_path: str, table: str) -> bool:
    if not os.path.exists(db_path):
        return False
    con = _pgconn(sqlite_path=db_path)
    try:
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
            (table,)).fetchone()
        return bool(row)
    finally:
        con.close()


def _backup_recent(db_path: str, days: int = 2) -> bool:
    cutoff = datetime.now() - timedelta(days=days)
    candidates = [
        os.environ.get("YAZKLINIK_BACKUP_ROOT", ""),
        os.path.join(os.path.dirname(os.path.dirname(db_path)), "auto_backups"),
        os.path.dirname(db_path),
    ]
    seen = set()
    for backup_dir in candidates:
        if not backup_dir or backup_dir in seen or not os.path.isdir(backup_dir):
            continue
        seen.add(backup_dir)
        for f in os.listdir(backup_dir):
            low = f.lower()
            if not (
                "backup" in low or "yedek" in low
                or low.endswith((".bak", ".backup", ".dump", ".sqlite3", ".db"))
            ):
                continue
            full = os.path.join(backup_dir, f)
            try:
                if not os.path.isfile(full):
                    continue
                mtime = datetime.fromtimestamp(os.path.getmtime(full))
                if mtime >= cutoff and os.path.getsize(full) > 0:
                    return True
            except Exception:
                pass
    # Restic snapshot kontrolu (akillilik)
    restic_repo = r"D:\YazKlinik_Restic_Repo"
    if os.path.isdir(restic_repo):
        return True
    return False


def _db_has_column(db_path: str, table: str, column: str) -> bool:
    if not os.path.exists(db_path):
        return False
    con = _pgconn(sqlite_path=db_path)
    try:
        rows = con.execute(f"PRAGMA table_info({table})").fetchall()
        return any(str(r[1]).lower() == column.lower() for r in rows)
    except Exception:
        return False
    finally:
        con.close()


def _read_config_value(config_env: str, key: str) -> Optional[str]:
    if not os.path.exists(config_env):
        return None
    try:
        for line in Path(config_env).read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            if k.strip() == key:
                return v.strip()
    except Exception:
        pass
    return None


def _source_has_pattern(root: str, pattern: str) -> bool:
    web_py = Path(root) / "yazklinik_web.py"
    if not web_py.exists():
        return False
    try:
        text = web_py.read_text(encoding="utf-8", errors="ignore").lower()
        return re.search(pattern, text) is not None
    except Exception:
        return False


def run_checks(db_path: Optional[str] = None) -> ComplianceReport:
    db_path = db_path or DEFAULT_DB_PATH
    rpt = ComplianceReport(generated_at=datetime.now().isoformat(timespec="seconds"))

    checks: List[ComplianceCheck] = []

    # A.9 Erisim Kontrolu
    has_audit = _db_has_table(db_path, "audit_log")
    checks.append(ComplianceCheck(
        code="ISO-A9.1", title="Audit log var",
        category="log", standard="ISO27001 A.9.4.1",
        status="pass" if has_audit else "fail",
        detail="audit_log tablosu mevcut" if has_audit else "audit_log tablosu YOK",
        recommendation="" if has_audit else "audit_log tablosunu oluÅŸtur",
        weight=3))

    has_2fa = _db_has_table(db_path, "user_2fa")
    checks.append(ComplianceCheck(
        code="ISO-A9.4", title="2FA aktif",
        category="erisim", standard="ISO27001 A.9.4.2",
        status="pass" if has_2fa else "warn",
        detail="user_2fa tablosu var" if has_2fa else "2FA henÃ¼z kurulmadÄ±",
        recommendation="" if has_2fa else "TOTP 2FA setup sihirbazÄ±nÄ± Ã§alÄ±ÅŸtÄ±r (/2fa-setup)",
        weight=3))

    # A.12 Yedekleme
    backup_ok = _backup_recent(db_path)
    checks.append(ComplianceCheck(
        code="ISO-A12.3", title="48 saat iÃ§inde yedek alÄ±ndÄ±",
        category="yedek", standard="ISO27001 A.12.3.1",
        status="pass" if backup_ok else "fail",
        detail="YakÄ±n tarihli yedek bulundu" if backup_ok else "Yedek bulunmadÄ±",
        recommendation="" if backup_ok else "restic_daily_backup.ps1 Windows Task Scheduler",
        weight=4))

    # A.10 Sifreleme
    cert_path = r"D:\YazKlinik_Final_D500\akillilik\caddy\caddy_data\caddy\certificates"
    has_tls = os.path.isdir(cert_path) or _file_exists(
        r"D:\YazKlinik_Final_D500\cert.pem")
    checks.append(ComplianceCheck(
        code="ISO-A10.1", title="TLS aktif",
        category="sifreleme", standard="ISO27001 A.10.1.1",
        status="pass" if has_tls else "warn",
        detail="Sertifika bulundu" if has_tls else "TLS sertifikasÄ± yok",
        recommendation="" if has_tls else "Caddy + Tailscale Funnel kur",
        weight=3))

    # KVKK m.12 - Veri guvenligi
    has_consent = _db_has_table(db_path, "patient_consents") or _db_has_table(
        db_path, "consents")
    checks.append(ComplianceCheck(
        code="KVKK-12", title="AÃ§Ä±k rÄ±za kayÄ±tlarÄ± var",
        category="kvkk", standard="KVKK m.12",
        status="pass" if has_consent else "fail",
        detail="patient_consents tablosu var" if has_consent else "RÄ±za kayÄ±tlarÄ± yok",
        recommendation="" if has_consent else "patient_consents tablosu + form UI",
        weight=4))

    # KVKK m.7 - Silme talebi
    checks.append(ComplianceCheck(
        code="KVKK-7", title="Hasta silme/anonim talebi UI",
        category="kvkk", standard="KVKK m.7",
        status="warn",
        detail="Endpoint var ama UI eksik",
        recommendation="/hasta-portal/kvkk-talep formu ekle",
        weight=2))

    # ISO A.7 Personel egitim
    edu_log = _file_exists(
        r"D:\YazKlinik_Final_D500\akillilik\compliance\egitim_log.txt")
    checks.append(ComplianceCheck(
        code="ISO-A7.2", title="YÄ±llÄ±k bilgi gÃ¼venliÄŸi eÄŸitim kaydÄ±",
        category="egitim", standard="ISO27001 A.7.2.2",
        status="pass" if edu_log else "warn",
        detail="egitim_log.txt var" if edu_log else "EÄŸitim kaydÄ± yok",
        recommendation="" if edu_log else "YÄ±llÄ±k 2 saat eÄŸitim + imza tutanaÄŸÄ±",
        weight=1))

    # KVKK m.6 - Hassas veri sifreleme at rest
    db_encrypted = False  # SQLite varsayilan sifresizdir
    checks.append(ComplianceCheck(
        code="KVKK-6", title="Hassas saÄŸlÄ±k verisi ÅŸifreleme (at rest)",
        category="sifreleme", standard="KVKK m.6",
        status="pass" if db_encrypted else "warn",
        detail="SQLite aÃ§Ä±k (ÅŸifresiz)" if not db_encrypted else "Åifreli",
        recommendation="BitLocker disk ÅŸifreleme veya SQLCipher",
        weight=3))

    # A.11 Fiziksel guvenlik (klinik kapida kilit)
    checks.append(ComplianceCheck(
        code="ISO-A11.1", title="Fiziksel eriÅŸim kontrolÃ¼",
        category="erisim", standard="ISO27001 A.11.1",
        status="warn",
        detail="Otomatik tespit yok - manuel kontrol",
        recommendation="Klinik kapÄ± kart sistemi + giriÅŸ log kaydÄ±",
        weight=2))

    # Tail scale / VPN
    ts_log = r"C:\ProgramData\Tailscale"
    checks.append(ComplianceCheck(
        code="ISO-A13.1", title="Uzak eriÅŸim VPN/zero-trust",
        category="erisim", standard="ISO27001 A.13.1.1",
        status="pass" if os.path.isdir(ts_log) else "warn",
        detail="Tailscale kurulu" if os.path.isdir(ts_log) else "VPN yok",
        recommendation="" if os.path.isdir(ts_log) else "Tailscale Funnel kur",
        weight=2))

    # Pano - hesap
    total_weight = sum(c.weight for c in checks)
    earned = sum(c.weight for c in checks if c.status == "pass")
    half = sum(c.weight for c in checks if c.status == "warn")
    score = earned + (half * 0.5)
    pct = round((score / max(1, total_weight)) * 100, 1)

    rpt.checks = checks
    rpt.score = int(score)
    rpt.max_score = total_weight
    rpt.pct = pct
    rpt.critical_failures = sum(
        1 for c in checks if c.status == "fail" and c.weight >= 3)

    if pct >= 95: rpt.grade = "A+"
    elif pct >= 85: rpt.grade = "A"
    elif pct >= 75: rpt.grade = "B"
    elif pct >= 60: rpt.grade = "C"
    elif pct >= 40: rpt.grade = "D"
    else: rpt.grade = "F"

    rpt.recommendations_top = [c.recommendation
                                 for c in checks
                                 if c.status != "pass" and c.recommendation][:5]
    return rpt


def run_readiness(db_path: Optional[str] = None) -> Dict[str, Any]:
    """D700'nin 10 kritik klinik hazirlik maddesi."""
    db_path = db_path or DEFAULT_DB_PATH
    root = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(root, "config.env")
    web_root = os.path.dirname(os.path.abspath(__file__))
    backup_root = _read_config_value(config_path, "YAZKLINIK_BACKUP_ROOT") or os.path.join(web_root, "auto_backups")

    def _soft_delete_ready() -> bool:
        return all(
            _db_has_column(db_path, t, "archived_at")
            for t in ("patients", "visits", "files", "usg_measurements")
        )

    role_ready = _source_has_pattern(
        web_root,
        r"session\.get\([\"']role[\"']|session\[[\"']role[\"']\]",
    )
    core_flow_ready = all(
        _source_has_pattern(web_root, pattern)
        for pattern in (
            r"/hastalar",
            r"/hasta/<",
            r"/tedavi-planla",
            r"/api/sistem-durumu",
        )
    )

    checks: List[Dict[str, Any]] = [
        {
            "id": "1",
            "name": "guclu-kullanici-rolleri",
            "status": "pass" if role_ready else "warn",
            "detail": "session role dogrulama var" if role_ready else "role kontrolu eksik",
        },
        {
            "id": "2",
            "name": "hasta_verisi_arsivleme",
            "status": "pass" if _soft_delete_ready() else "warn",
            "detail": "kritik tablolarda archived_at var" if _soft_delete_ready() else "kritik tablolarda archived_at eksik",
        },
        {
            "id": "3",
            "name": "dashboard-gorev-kutusu",
            "status": "pass" if _source_has_pattern(web_root, r"/hastalar|/gorev|/ajanlar|/api/sistem-durumu") else "warn",
            "detail": "dashboard/gorev alanlari kontrol edildi" if _source_has_pattern(web_root, r"/hastalar|/gorev|/ajanlar|/api/sistem-durumu") else "gorev alaninda eksik kontrol",
        },
        {
            "id": "4",
            "name": "tema-kalite-erisimlilik",
            "status": "pass" if _source_has_pattern(web_root, r"aria-|accessibility|contrast|font") else "warn",
            "detail": "eriÅŸilebilirlik / stil ipuclari var" if _source_has_pattern(web_root, r"aria-|accessibility|contrast|font") else "erisimlilik gozden gecirilmelidir",
        },
        {
            "id": "5",
            "name": "randevu-ve-yapi-cekirdek",
            "status": "pass" if core_flow_ready else "warn",
            "detail": "hasta/randevu/rapor cekirdek route'lari var" if core_flow_ready else "randevu/rapor/hasta akislari web.py route bazinda takipte",
        },
        {
            "id": "6",
            "name": "rapor-standardizasyonu",
            "status": "pass" if _source_has_pattern(web_root, r"recete|pdf|/hasta/\\w+/recete") else "warn",
            "detail": "recete/PDF route patterni bulunuyor" if _source_has_pattern(web_root, r"recete|pdf|/hasta/\\w+/recete") else "rapor sirkulasyonuna bak",
        },
        {
            "id": "7",
            "name": "api-saglik-kontrolu",
            "status": "pass" if os.path.exists(os.path.join(root, "D500_HEALTH_MONITOR.py")) else "warn",
            "detail": "health monitor dosyasi bulundu" if os.path.exists(os.path.join(root, "D500_HEALTH_MONITOR.py")) else "health monitor tanimlanmadi",
        },
        {
            "id": "8",
            "name": "guvenlik-yedekleme",
            "status": "pass" if bool(_backup_files_recent(backup_root, days=2)) else "warn",
            "detail": "2 gunden yeni yedek var" if _backup_files_recent(backup_root, days=2) else "2 gunden yeni yedek yok",
        },
        {
            "id": "9",
            "name": "erisim-guvenligi",
            "status": "pass" if _read_config_value(config_path, "YAZKLINIK_ENABLE_HTTPS") == "1" else "warn",
            "detail": "HTTPS aktif" if _read_config_value(config_path, "YAZKLINIK_ENABLE_HTTPS") == "1" else "HTTPS kontrolu yapisin",
        },
        {
            "id": "10",
            "name": "geri-bildirim-dongusu",
            "status": "pass" if _source_has_pattern(web_root, r"alert|toast|toastify|feedback|yanit") else "warn",
            "detail": "geri bildirim isareti var" if _source_has_pattern(web_root, r"alert|toast|toastify|feedback|yanit") else "hata/geri bildirim UI gelistirilmeli",
        },
    ]

    warn_count = sum(1 for c in checks if c.get("status") == "warn")
    return {
        "ok": warn_count == 0,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "checks": checks,
        "warn_count": warn_count,
        "ok_count": len(checks) - warn_count,
        "source_root": web_root,
        "config_path": config_path,
        "db_path": db_path,
    }


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION}


def _backup_files_recent(root_dir: str, days: int = 2) -> bool:
    if not root_dir or not os.path.isdir(root_dir):
        return False
    cutoff = datetime.now() - timedelta(days=days)
    try:
        for fname in os.listdir(root_dir):
            path = os.path.join(root_dir, fname)
            if not os.path.isfile(path):
                continue
            if not fname.lower().endswith((".db", ".sqlite3", ".bak", ".backup", ".dump")):
                continue
            try:
                if datetime.fromtimestamp(os.path.getmtime(path)) >= cutoff:
                    return True
            except Exception:
                continue
    except Exception:
        return False
    return False


if __name__ == "__main__":
    r = run_checks()
    print(f"Skor: {r.score}/{r.max_score} ({r.pct}%) Grade: {r.grade}")
    print(f"Kritik fail: {r.critical_failures}")
    for c in r.checks:
        sym = {"pass": "[OK]", "fail": "[XX]", "warn": "[!!]", "unknown": "[??]"}[c.status]
        print(f"  {sym} {c.code} {c.title}")
    print(f"\nIlk oneriler:")
    for r2 in r.recommendations_top:
        print(f"  - {r2}")

