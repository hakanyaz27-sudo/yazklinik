"""Backup Verify Ajani - Restic + SQLite yedek butunluk kontrolu.

Her gece (cron) calistirilir:
    - Restic repo erisilebilir mi?
    - Son snapshot ne kadar eski?
    - SQLite DB integrity check (PRAGMA)
    - NAS yedek yolu erisilebilir mi?

Sorun varsa WhatsApp ile doktora bildir.
"""
from __future__ import annotations

import json
import os
import subprocess
import sqlite3
from dataclasses import dataclass, field, asdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-backup-verify"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")
RESTIC_REPO = os.environ.get("RESTIC_REPOSITORY", r"D:\YazKlinik_Restic_Repo")
RESTIC_PASSWORD_FILE = os.environ.get(
    "RESTIC_PASSWORD_FILE",
    r"D:\YazKlinik_Final_D500\akillilik\restic_password.txt")
NAS_BACKUP_DIR = os.environ.get("YAZKLINIK_NAS_BACKUP_DIR",
                                  r"\\asustor\YazKlinik_Backups")


@dataclass
class BackupCheck:
    name: str
    status: str            # ok | warn | fail
    detail: str = ""
    age_hours: Optional[float] = None


@dataclass
class BackupVerifyReport:
    generated_at: str
    overall_status: str = "ok"
    checks: List[BackupCheck] = field(default_factory=list)
    critical_issues: List[str] = field(default_factory=list)
    last_snapshot_iso: Optional[str] = None
    last_snapshot_age_hours: float = 0
    agent_version: str = AGENT_VERSION


def _restic_available() -> bool:
    try:
        r = subprocess.run(["restic", "version"], capture_output=True,
                            text=True, timeout=8)
        return r.returncode == 0
    except Exception:
        return False


def _check_restic_snapshots() -> BackupCheck:
    if not _restic_available():
        return BackupCheck(name="restic_binary", status="warn",
                            detail="restic kurulu değil (paket eksik)")
    if not os.path.isdir(RESTIC_REPO):
        return BackupCheck(name="restic_repo", status="fail",
                            detail=f"Repo yok: {RESTIC_REPO}")
    if not os.path.isfile(RESTIC_PASSWORD_FILE):
        return BackupCheck(name="restic_password", status="fail",
                            detail=f"Şifre dosyası yok: {RESTIC_PASSWORD_FILE}")
    env = os.environ.copy()
    env["RESTIC_REPOSITORY"] = RESTIC_REPO
    env["RESTIC_PASSWORD_FILE"] = RESTIC_PASSWORD_FILE
    try:
        r = subprocess.run(
            ["restic", "snapshots", "--json", "--latest", "1"],
            capture_output=True, text=True, timeout=30, env=env)
        if r.returncode != 0:
            return BackupCheck(name="restic_snapshots", status="fail",
                                detail=f"restic hata: {r.stderr[:200]}")
        snaps = json.loads(r.stdout or "[]")
        if not snaps:
            return BackupCheck(name="restic_snapshots", status="fail",
                                detail="Hiçbir snapshot yok")
        last = snaps[-1]
        ts_iso = last.get("time", "")
        try:
            ts = datetime.fromisoformat(ts_iso.replace("Z", "+00:00"))
            age_h = (datetime.now(ts.tzinfo) - ts).total_seconds() / 3600
        except Exception:
            age_h = -1
        status = "ok" if 0 <= age_h <= 36 else "warn" if age_h <= 96 else "fail"
        return BackupCheck(
            name="restic_snapshots", status=status,
            detail=f"Son snapshot: {ts_iso} ({age_h:.1f} saat önce)",
            age_hours=age_h)
    except Exception as e:
        return BackupCheck(name="restic_snapshots", status="fail",
                            detail=f"{type(e).__name__}: {e}")


def _check_sqlite_integrity(db_path: str) -> BackupCheck:
    if not os.path.exists(db_path):
        return BackupCheck(name="sqlite_db", status="fail",
                            detail=f"DB yok: {db_path}")
    try:
        con = sqlite3.connect(db_path)
        r = con.execute("PRAGMA integrity_check").fetchone()
        con.close()
        if r and r[0] == "ok":
            return BackupCheck(name="sqlite_integrity", status="ok",
                                detail="PRAGMA integrity_check = ok")
        return BackupCheck(name="sqlite_integrity", status="fail",
                            detail=f"integrity = {r}")
    except Exception as e:
        return BackupCheck(name="sqlite_integrity", status="fail",
                            detail=f"{type(e).__name__}: {e}")


def _check_nas_backup_dir() -> BackupCheck:
    if not os.path.isdir(NAS_BACKUP_DIR):
        return BackupCheck(name="nas_backup_dir", status="warn",
                            detail=f"NAS yedek klasörü erişilemez: {NAS_BACKUP_DIR}")
    try:
        files = os.listdir(NAS_BACKUP_DIR)
        recent = []
        cutoff = datetime.now() - timedelta(days=2)
        for f in files:
            full = os.path.join(NAS_BACKUP_DIR, f)
            try:
                m = datetime.fromtimestamp(os.path.getmtime(full))
                if m >= cutoff:
                    recent.append(f)
            except Exception:
                pass
        if not recent:
            return BackupCheck(name="nas_backup_recent", status="warn",
                                detail=f"48 saat içinde yedek yok ({len(files)} dosya var)")
        return BackupCheck(name="nas_backup_recent", status="ok",
                            detail=f"{len(recent)} yeni yedek (48 saat)")
    except Exception as e:
        return BackupCheck(name="nas_backup_recent", status="fail",
                            detail=f"{type(e).__name__}: {e}")


def _check_db_size_reasonable(db_path: str) -> BackupCheck:
    if not os.path.exists(db_path):
        return BackupCheck(name="db_size", status="fail", detail="DB yok")
    size_mb = os.path.getsize(db_path) / (1024 * 1024)
    if size_mb < 0.01:
        return BackupCheck(name="db_size", status="fail",
                            detail=f"DB boş? {size_mb:.2f} MB")
    if size_mb > 5000:
        return BackupCheck(name="db_size", status="warn",
                            detail=f"DB çok büyük: {size_mb:.0f} MB - bölme düşün")
    return BackupCheck(name="db_size", status="ok",
                        detail=f"DB boyutu: {size_mb:.1f} MB (sağlıklı)")


def verify_all(db_path: Optional[str] = None) -> BackupVerifyReport:
    db_path = db_path or DEFAULT_DB_PATH
    rpt = BackupVerifyReport(
        generated_at=datetime.now().isoformat(timespec="seconds"))

    rpt.checks.append(_check_restic_snapshots())
    rpt.checks.append(_check_sqlite_integrity(db_path))
    rpt.checks.append(_check_db_size_reasonable(db_path))
    rpt.checks.append(_check_nas_backup_dir())

    fails = [c for c in rpt.checks if c.status == "fail"]
    warns = [c for c in rpt.checks if c.status == "warn"]

    if fails:
        rpt.overall_status = "fail"
        rpt.critical_issues = [f"{c.name}: {c.detail}" for c in fails]
    elif warns:
        rpt.overall_status = "warn"
    else:
        rpt.overall_status = "ok"

    # Son snapshot yas
    for c in rpt.checks:
        if c.name == "restic_snapshots" and c.age_hours is not None:
            rpt.last_snapshot_age_hours = c.age_hours
            break

    return rpt


def notify_doctor_if_failed(rpt: BackupVerifyReport) -> bool:
    """Sorun varsa WhatsApp ile bildir."""
    if rpt.overall_status != "fail":
        return False
    try:
        from yazklinik_whatsapp_local_helper import send_whatsapp_message
        doctor = os.environ.get("DOCTOR_WHATSAPP", "")
        if not doctor:
            return False
        msg = (f"YEDEK ALARMI ({rpt.generated_at[:16]})\n"
               + "\n".join(rpt.critical_issues[:3])
               + "\nDetay için: /api/agents/backup-verify/report")
        send_whatsapp_message(doctor, msg)
        return True
    except Exception:
        return False


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "restic_available": _restic_available(),
            "repo_path": RESTIC_REPO}


if __name__ == "__main__":
    r = verify_all()
    print(f"Overall: {r.overall_status.upper()}")
    for c in r.checks:
        sym = {"ok": "[OK]", "warn": "[!!]", "fail": "[XX]"}.get(c.status, "[??]")
        print(f"  {sym} {c.name}: {c.detail}")
    if r.critical_issues:
        print("\nKRITIK:")
        for i in r.critical_issues:
            print(f"  - {i}")
