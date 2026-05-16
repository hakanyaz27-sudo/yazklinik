"""Mojibake Bekci Ajani (TESPIT - OTOMATIK DUZELTME YOK).

Source dosyalarinda Win-1252 -> UTF-8 cift encode kaynakli bozuk karakterleri
tespit eder ve commit oncesi UYARI ciktisi verir. Memory kuralina gore
OTOMATIK FIX yapmaz - sadece "burada bozuk var, doktor/Codex el ile bakmali"
der.

Tespit ettigi tipik desenler:
    Ã , Ã‚, Ã„, Ã±, Ã¶, Ã¼, Ã§, Ã¢, Ãª, Ã®, Ã´, Ãª, Â§ vb.

Yontem:
    - Dosyayi UTF-8 ile oku
    - Bilinen mojibake desen sayisini cikar
    - Satir + sutun ciftleriyle rapor uret
    - Yuksek yogunluklu dosyalari "REVIEW" olarak isaretle

Asla:
    - Dosyayi yeniden yazmaz
    - Otomatik bytes.decode('cp1252').decode('utf-8') yapmaz
    - Git pre-commit hook icine yazilabilir ama kendi kendine kuramaz

Stdlib only.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


AGENT_VERSION = "2026.05.16-mojibake-bekci"
SOURCE_LABEL = "Mojibake encoding tespiti (read-only)"

# Klasik Win-1252 -> UTF-8 double encode tracelar
MOJIBAKE_TOKENS: Tuple[str, ...] = (
    "Ã¢", "Ã£", "Ã¤", "Ã¥", "Ã¦", "Ã§", "Ã¨", "Ã©", "Ãª", "Ã«",
    "Ã­", "Ã®", "Ã¯", "Ã°", "Ã±", "Ã²", "Ã³", "Ã´", "Ãµ", "Ã¶",
    "Ã¸", "Ã¹", "Ãº", "Ã»", "Ã¼", "Ã½", "Ã¾", "Ã¿",
    "Ä±", "Ä°", "Å", "Å¸", "Å¾",
    "â€™", "â€œ", "â€", "â€“", "â€”", "â€¦", "â€¢", "â€¨",
    "Â§", "Â£", "Â¥", "Â®", "Â©", "Â®", "Â°", "Â±",
    "Ã„", "Ã‡", "Ã–", "Ãœ", "Ã‰",
)

# Dosya uzanti white-list
DEFAULT_SCAN_EXTS: Tuple[str, ...] = (
    ".py", ".md", ".txt", ".html", ".css", ".js", ".json", ".env",
    ".bat", ".ps1", ".sh",
)

# Maksimum dosya boyutu (byte) - cok buyukleri tarama
MAX_FILE_BYTES = 5 * 1024 * 1024  # 5 MB

# Yogunluk esikleri (hit / 1000 char)
WARN_DENSITY = 1.0
CRITICAL_DENSITY = 5.0


@dataclass
class Hit:
    line: int
    col: int
    token: str
    snippet: str


@dataclass
class FileReport:
    path: str
    total_hits: int
    density_per_1k: float
    severity: str         # "ok" | "warn" | "critical"
    samples: List[Hit] = field(default_factory=list)
    skipped: bool = False
    skip_reason: Optional[str] = None


@dataclass
class ScanResult:
    scanned_root: str
    files_scanned: int
    files_flagged: int
    total_hits: int
    reports: List[FileReport] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""
    agent_version: str = AGENT_VERSION


def _scan_text(text: str, samples_cap: int = 8) -> Tuple[int, List[Hit]]:
    total = 0
    hits: List[Hit] = []
    lines = text.splitlines()
    for idx, line in enumerate(lines, start=1):
        for token in MOJIBAKE_TOKENS:
            if token not in line:
                continue
            for m in re.finditer(re.escape(token), line):
                total += 1
                if len(hits) < samples_cap:
                    start = max(0, m.start() - 15)
                    end = min(len(line), m.end() + 15)
                    snippet = line[start:end].strip()
                    hits.append(Hit(line=idx, col=m.start() + 1, token=token, snippet=snippet))
    return total, hits


def _severity(total_hits: int, char_count: int) -> Tuple[str, float]:
    if char_count <= 0:
        return "ok", 0.0
    density = (total_hits / char_count) * 1000
    if density >= CRITICAL_DENSITY:
        return "critical", round(density, 2)
    if density >= WARN_DENSITY or total_hits > 0:
        return "warn", round(density, 2)
    return "ok", round(density, 2)


def scan_file(file_path: str) -> FileReport:
    path = Path(file_path)
    report = FileReport(path=str(path), total_hits=0, density_per_1k=0.0, severity="ok")
    try:
        if not path.is_file():
            report.skipped = True
            report.skip_reason = "Dosya bulunamadi."
            return report
        size = path.stat().st_size
        if size > MAX_FILE_BYTES:
            report.skipped = True
            report.skip_reason = f"Dosya cok buyuk ({size} bayt)."
            return report
        text = path.read_text(encoding="utf-8", errors="strict")
    except UnicodeDecodeError as e:
        report.skipped = True
        report.skip_reason = f"UTF-8 olarak okunamadi: {e}"
        return report
    except (OSError, PermissionError) as e:
        report.skipped = True
        report.skip_reason = f"Okuma hatasi: {e}"
        return report

    total, samples = _scan_text(text)
    severity, density = _severity(total, len(text))
    report.total_hits = total
    report.density_per_1k = density
    report.severity = severity
    report.samples = samples
    return report


def scan_tree(root: str, scan_exts: Optional[Tuple[str, ...]] = None,
              exclude_dirs: Tuple[str, ...] = (".git", ".venv", "__pycache__", "node_modules", ".claude")) -> ScanResult:
    """Klasoru tara. Yalniz okuma yapar, hicbir dosyayi degistirmez."""
    exts = scan_exts or DEFAULT_SCAN_EXTS
    root_path = Path(root)
    result = ScanResult(
        scanned_root=str(root_path),
        files_scanned=0,
        files_flagged=0,
        total_hits=0,
        started_at=datetime.now().isoformat(timespec="seconds"),
    )

    if not root_path.exists():
        result.finished_at = datetime.now().isoformat(timespec="seconds")
        return result

    for dirpath, dirnames, filenames in os.walk(root_path):
        # Excluded dirs filtre (in-place)
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        for name in filenames:
            if not name.lower().endswith(exts):
                continue
            file_path = Path(dirpath) / name
            rep = scan_file(str(file_path))
            result.files_scanned += 1
            if rep.skipped:
                continue
            if rep.total_hits > 0:
                result.files_flagged += 1
                result.total_hits += rep.total_hits
                result.reports.append(rep)

    # Yogunluga gore sirala (kritik en uste)
    result.reports.sort(key=lambda r: r.density_per_1k, reverse=True)
    result.finished_at = datetime.now().isoformat(timespec="seconds")
    return result


def to_audit_payload(result: ScanResult) -> Dict[str, Any]:
    payload = asdict(result)
    payload["action"] = f"mojibake:scan ({result.files_flagged} flag, {result.total_hits} hit)"
    return payload


if __name__ == "__main__":
    import sys
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    r = scan_tree(target)
    print(f"Scanned: {r.files_scanned}  Flagged: {r.files_flagged}  Hits: {r.total_hits}")
    print("(BU AJAN SADECE TESPIT EDER - OTOMATIK DUZELTME YAPMAZ)")
    for rep in r.reports[:10]:
        print(f"\n[{rep.severity}] {rep.path}  hits={rep.total_hits} density={rep.density_per_1k}/1k")
        for h in rep.samples[:3]:
            print(f"    line {h.line:>4} col {h.col:>3}: {h.token!r} | ...{h.snippet}...")
