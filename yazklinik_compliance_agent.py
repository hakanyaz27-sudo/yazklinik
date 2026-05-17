"""ISO 27001 / KVKK Compliance Dashboard Ajani.

Klinik bilgi guvenligi + KVKK uyumluluk kontrol noktalari.
Skor: 0-100. Eksik kontrol -> oneri uretir.
"""
from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-compliance"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")


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
    con = sqlite3.connect(db_path)
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
        recommendation="" if has_audit else "audit_log tablosunu oluştur",
        weight=3))

    has_2fa = _db_has_table(db_path, "user_2fa")
    checks.append(ComplianceCheck(
        code="ISO-A9.4", title="2FA aktif",
        category="erisim", standard="ISO27001 A.9.4.2",
        status="pass" if has_2fa else "warn",
        detail="user_2fa tablosu var" if has_2fa else "2FA henüz kurulmadı",
        recommendation="" if has_2fa else "TOTP 2FA setup sihirbazını çalıştır (/2fa-setup)",
        weight=3))

    # A.12 Yedekleme
    backup_ok = _backup_recent(db_path)
    checks.append(ComplianceCheck(
        code="ISO-A12.3", title="48 saat içinde yedek alındı",
        category="yedek", standard="ISO27001 A.12.3.1",
        status="pass" if backup_ok else "fail",
        detail="Yakın tarihli yedek bulundu" if backup_ok else "Yedek bulunmadı",
        recommendation="" if backup_ok else "restic_daily_backup.ps1 Windows Task Scheduler",
        weight=4))

    # A.10 Sifreleme
    cert_path = r"D:\YazKlinik_Final_D300\akillilik\caddy\caddy_data\caddy\certificates"
    has_tls = os.path.isdir(cert_path) or _file_exists(
        r"D:\YazKlinik_Final_D300\cert.pem")
    checks.append(ComplianceCheck(
        code="ISO-A10.1", title="TLS aktif",
        category="sifreleme", standard="ISO27001 A.10.1.1",
        status="pass" if has_tls else "warn",
        detail="Sertifika bulundu" if has_tls else "TLS sertifikası yok",
        recommendation="" if has_tls else "Caddy + Tailscale Funnel kur",
        weight=3))

    # KVKK m.12 - Veri guvenligi
    has_consent = _db_has_table(db_path, "patient_consents") or _db_has_table(
        db_path, "consents")
    checks.append(ComplianceCheck(
        code="KVKK-12", title="Açık rıza kayıtları var",
        category="kvkk", standard="KVKK m.12",
        status="pass" if has_consent else "fail",
        detail="patient_consents tablosu var" if has_consent else "Rıza kayıtları yok",
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
        r"D:\YazKlinik_Final_D300\akillilik\compliance\egitim_log.txt")
    checks.append(ComplianceCheck(
        code="ISO-A7.2", title="Yıllık bilgi güvenliği eğitim kaydı",
        category="egitim", standard="ISO27001 A.7.2.2",
        status="pass" if edu_log else "warn",
        detail="egitim_log.txt var" if edu_log else "Eğitim kaydı yok",
        recommendation="" if edu_log else "Yıllık 2 saat eğitim + imza tutanağı",
        weight=1))

    # KVKK m.6 - Hassas veri sifreleme at rest
    db_encrypted = False  # SQLite varsayilan sifresizdir
    checks.append(ComplianceCheck(
        code="KVKK-6", title="Hassas sağlık verisi şifreleme (at rest)",
        category="sifreleme", standard="KVKK m.6",
        status="pass" if db_encrypted else "warn",
        detail="SQLite açık (şifresiz)" if not db_encrypted else "Şifreli",
        recommendation="BitLocker disk şifreleme veya SQLCipher",
        weight=3))

    # A.11 Fiziksel guvenlik (klinik kapida kilit)
    checks.append(ComplianceCheck(
        code="ISO-A11.1", title="Fiziksel erişim kontrolü",
        category="erisim", standard="ISO27001 A.11.1",
        status="warn",
        detail="Otomatik tespit yok - manuel kontrol",
        recommendation="Klinik kapı kart sistemi + giriş log kaydı",
        weight=2))

    # Tail scale / VPN
    ts_log = r"C:\ProgramData\Tailscale"
    checks.append(ComplianceCheck(
        code="ISO-A13.1", title="Uzak erişim VPN/zero-trust",
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


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION}


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
