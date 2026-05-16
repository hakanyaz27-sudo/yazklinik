"""NAS Yedek Izleyici Ajani.

Asustor NAS uzerindeki hasta dosyalari, USG goruntu klasoru ve otomatik
yedeklerin durumunu periyodik kontrol eder. Eksik, bozuk, eski veya
yer kalmamis ise doktora uyari ciktisi verir.

Ne yapar:
    - auto_backups klasorundeki son N yedegi listeler
    - Boyut sapmasini hesaplar (son yedek son 7 yedekten %50+ kucukse uyari)
    - NAS sharesi erisilebilir mi (path mevcut + read denemesi)
    - Eski yedekleri sayar (degil silmez, sadece raporlar)
    - Disk doluluk yuzdesi tahmini

Asla yapmaz:
    - Hicbir dosyayi silmez/tasimaz (KRITIK kural)
    - Hasta verisini ag uzerinden tasimaz
    - Otomatik yedek yapmaz (mevcut yedek scripti zaten var)

Stdlib + os/pathlib. shutil sadece read-only stat icin.
"""

from __future__ import annotations

import os
import shutil
import stat
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.16-nas-yedek-izleyici"
SOURCE_LABEL = "NAS yedek saglik kontrolu"

# Esikler
FRESH_BACKUP_HOURS = 26          # son yedek > 26 saat eski ise uyari
MIN_BACKUPS_RETAINED = 7
SIZE_DROP_THRESHOLD = 0.50       # son yedek son 7'nin medyaninin %50 alti ise uyari
DISK_USAGE_WARN_PCT = 85.0
DISK_USAGE_CRITICAL_PCT = 95.0


@dataclass
class BackupFile:
    path: str
    size_bytes: int
    modified_at: str


@dataclass
class NASHealthReport:
    nas_root: str
    nas_reachable: bool
    last_backup: Optional[BackupFile]
    backup_count: int
    recent_backups: List[BackupFile] = field(default_factory=list)
    disk_total_gb: Optional[float] = None
    disk_free_gb: Optional[float] = None
    disk_used_pct: Optional[float] = None
    warnings: List[str] = field(default_factory=list)
    critical: List[str] = field(default_factory=list)
    suggested_actions: List[str] = field(default_factory=list)
    checked_at: str = ""
    agent_version: str = AGENT_VERSION


def _safe_stat(path: Path) -> Optional[os.stat_result]:
    try:
        return path.stat()
    except (OSError, PermissionError):
        return None


def _list_backups(backup_dir: Path, pattern: str = "*.zip") -> List[BackupFile]:
    """Backup dosyalarini listele (sadece okur, hicbir sey silmez)."""
    if not backup_dir.exists():
        return []
    items: List[BackupFile] = []
    try:
        for p in backup_dir.iterdir():
            if not p.is_file():
                continue
            if pattern == "*.zip" and p.suffix.lower() not in (".zip", ".7z", ".tar", ".gz", ".bak"):
                continue
            st = _safe_stat(p)
            if not st:
                continue
            items.append(BackupFile(
                path=str(p),
                size_bytes=int(st.st_size),
                modified_at=datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
            ))
    except (OSError, PermissionError):
        return []
    items.sort(key=lambda b: b.modified_at, reverse=True)
    return items


def _is_nas_reachable(root: Path) -> bool:
    """Read-only mevcudiyet kontrolu."""
    try:
        if not root.exists():
            return False
        # iterdir cagrisi izin/ag hatalarini yakalamak icin
        next(iter(root.iterdir()), None)
        return True
    except (OSError, PermissionError):
        return False


def _disk_usage(root: Path) -> Dict[str, Optional[float]]:
    try:
        usage = shutil.disk_usage(str(root))
        total_gb = usage.total / (1024 ** 3)
        free_gb = usage.free / (1024 ** 3)
        used_pct = (1 - usage.free / usage.total) * 100 if usage.total else None
        return {"total_gb": round(total_gb, 1), "free_gb": round(free_gb, 1),
                "used_pct": round(used_pct, 1) if used_pct is not None else None}
    except (OSError, PermissionError, ValueError):
        return {"total_gb": None, "free_gb": None, "used_pct": None}


def _median(values: List[int]) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2:
        return float(s[mid])
    return (s[mid - 1] + s[mid]) / 2.0


def check_health(nas_root: str, backup_subdir: str = "auto_backups",
                 now: Optional[datetime] = None) -> NASHealthReport:
    """Ana giris noktasi. nas_root genelde 'D:\\YazKlinik_Final_D300' veya '\\\\asustor\\Voluson\\Hastalar'."""
    now = now or datetime.now()
    root = Path(nas_root)
    backup_dir = root / backup_subdir

    report = NASHealthReport(
        nas_root=str(root),
        nas_reachable=False,
        last_backup=None,
        backup_count=0,
        checked_at=now.isoformat(timespec="seconds"),
    )

    reachable = _is_nas_reachable(root)
    report.nas_reachable = reachable
    if not reachable:
        report.critical.append(f"NAS erisilemiyor: {root}")
        report.suggested_actions.append("Ag baglantisini ve Asustor cihazinin acik olmasini kontrol edin.")
        return report

    # Disk kullanim
    du = _disk_usage(root)
    report.disk_total_gb = du["total_gb"]
    report.disk_free_gb = du["free_gb"]
    report.disk_used_pct = du["used_pct"]

    if du["used_pct"] is not None:
        if du["used_pct"] >= DISK_USAGE_CRITICAL_PCT:
            report.critical.append(f"Disk doluluk kritik: %{du['used_pct']}")
            report.suggested_actions.append("Eski yedekleri ARSIVE TASIYIN (silmeyin), yer acin.")
        elif du["used_pct"] >= DISK_USAGE_WARN_PCT:
            report.warnings.append(f"Disk doluluk yuksek: %{du['used_pct']}")
            report.suggested_actions.append("Yakin zamanda eski yedek arsivlemesi planlanmali.")

    # Yedekler
    backups = _list_backups(backup_dir)
    report.backup_count = len(backups)
    report.recent_backups = backups[:MIN_BACKUPS_RETAINED]

    if not backups:
        report.critical.append(f"Hic yedek bulunamadi: {backup_dir}")
        report.suggested_actions.append("Otomatik yedek scriptinin calistigini kontrol edin.")
        return report

    last = backups[0]
    report.last_backup = last
    try:
        last_dt = datetime.fromisoformat(last.modified_at)
        age_hours = (now - last_dt).total_seconds() / 3600
        if age_hours > FRESH_BACKUP_HOURS:
            report.warnings.append(f"Son yedek {age_hours:.1f} saat eski (esik {FRESH_BACKUP_HOURS}).")
            report.suggested_actions.append("Yedek hattini elle calistirin ve cron'u dogrulayin.")
    except Exception:
        report.warnings.append("Son yedek zaman damgasi okunamadi.")

    if len(backups) < MIN_BACKUPS_RETAINED:
        report.warnings.append(f"Saklanan yedek sayisi az: {len(backups)} < {MIN_BACKUPS_RETAINED}")

    # Boyut sapmasi
    if len(backups) >= 4:
        med = _median([b.size_bytes for b in backups[1:MIN_BACKUPS_RETAINED]])
        if med and last.size_bytes < med * SIZE_DROP_THRESHOLD:
            pct = (last.size_bytes / med) * 100 if med else 0
            report.warnings.append(
                f"Son yedek boyutu medyanin %{pct:.0f}'i ({last.size_bytes // (1024*1024)} MB vs medyan {int(med) // (1024*1024)} MB)."
            )
            report.suggested_actions.append("Yedek icerigini elle acip dogrulayin; veri kaybi olabilir.")

    return report


def to_audit_payload(report: NASHealthReport) -> Dict[str, Any]:
    payload = asdict(report)
    status = "ok"
    if report.critical:
        status = "critical"
    elif report.warnings:
        status = "warning"
    payload["action"] = f"nas_yedek:{status}"
    return payload


if __name__ == "__main__":
    # NAS yoksa lokal proje kokuyle test et
    sample_root = "D:\\YazKlinik_Final_D300"
    r = check_health(sample_root)
    print(f"NAS reachable: {r.nas_reachable}")
    print(f"Backups found: {r.backup_count}")
    if r.last_backup:
        print(f"Last backup: {r.last_backup.modified_at} ({r.last_backup.size_bytes // (1024*1024)} MB)")
    print(f"Disk used: %{r.disk_used_pct}")
    if r.critical:
        print("CRITICAL:", r.critical)
    if r.warnings:
        print("WARN:", r.warnings)
    for a in r.suggested_actions:
        print("  ->", a)
