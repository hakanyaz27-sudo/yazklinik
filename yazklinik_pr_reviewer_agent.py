"""PR Reviewer Ajani.

Codex'in actigi GitHub PR'larini ya da yerel diff'i hizli on review eder.
Bu modul KOD ANALIZI yapmaz; sadece sablon kontrolu yapar:

    - Diff icinde v68 dosyasi degistirilmis mi? (KRITIK - dokunulamaz)
    - Hasta verisi silen SQL var mi? (DELETE FROM patients/visits/files/usg_*)
    - NAS klasoru icin Python remove/unlink var mi?
    - Yeni route eklendiyse feature_sync'a kayit eklenmis mi?
    - Inline HTML/JS bloklari icinde mojibake var mi?
    - Mass formatlama yapilmis mi (cok dosya + cok satir)?

Asla:
    - PR'i otomatik onaylamaz/reddetmez
    - Push yapmaz
    - GitHub'a yorum birakmaz (web layer/kullanici manuel yapar)

Stdlib only. Diff metnini girdi alir.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple


AGENT_VERSION = "2026.05.16-pr-reviewer"
SOURCE_LABEL = "PR diff sablon kontrol"

# Asla degisemez dosyalar
PROTECTED_FILES = (
    "yazklinik_v68.py",
)

# Hasta verisi tablolari (silinmez)
SENSITIVE_TABLES = (
    "patients", "visits", "files", "usg_measurements", "patient_files",
)

# NAS path desenleri (Python silinmez)
NAS_PATH_HINTS = (
    r"\\\\asustor\\Voluson\\",
    r"\\\\asustor\\",
    r"Voluson\\Hastalar",
)

# Diff line markerlari
ADD_RE = re.compile(r"^\+(?!\+\+)")
REMOVE_RE = re.compile(r"^-(?!\-\-)")
FILE_HEADER_RE = re.compile(r"^\+\+\+ b/(.+)$")


@dataclass
class Finding:
    severity: str         # "block" | "warn" | "info"
    file: str
    line_hint: Optional[int]
    rule: str
    message: str
    snippet: str = ""


@dataclass
class ReviewResult:
    files_touched: List[str] = field(default_factory=list)
    findings: List[Finding] = field(default_factory=list)
    has_blockers: bool = False
    summary: str = ""
    total_added: int = 0
    total_removed: int = 0
    reviewed_at: str = ""
    agent_version: str = AGENT_VERSION


def _iter_diff_files(diff_text: str):
    """Diff'i (dosya_yolu, added_lines, removed_lines) ucluleriyle gez."""
    current_file: Optional[str] = None
    added: List[Tuple[int, str]] = []
    removed: List[Tuple[int, str]] = []
    hunk_added_lineno = 0
    hunk_removed_lineno = 0

    for raw in diff_text.splitlines():
        m = FILE_HEADER_RE.match(raw)
        if m:
            if current_file is not None:
                yield current_file, added, removed
            current_file = m.group(1)
            added = []
            removed = []
            hunk_added_lineno = 0
            hunk_removed_lineno = 0
            continue

        if raw.startswith("@@"):
            # @@ -A,B +C,D @@
            mm = re.search(r"\+(\d+)", raw)
            mr = re.search(r"-(\d+)", raw)
            hunk_added_lineno = int(mm.group(1)) if mm else 0
            hunk_removed_lineno = int(mr.group(1)) if mr else 0
            continue

        if current_file is None:
            continue

        if ADD_RE.match(raw):
            added.append((hunk_added_lineno, raw[1:]))
            hunk_added_lineno += 1
        elif REMOVE_RE.match(raw):
            removed.append((hunk_removed_lineno, raw[1:]))
            hunk_removed_lineno += 1
        else:
            hunk_added_lineno += 1
            hunk_removed_lineno += 1

    if current_file is not None:
        yield current_file, added, removed


def _check_protected(file: str, findings: List[Finding]):
    base = file.split("/")[-1]
    if base in PROTECTED_FILES:
        findings.append(Finding(
            severity="block", file=file, line_hint=None,
            rule="protected_file",
            message=f"DOKUNMA kuralina aykiri: {base} degistirilmis. PR reddedilmeli.",
        ))


def _check_patient_delete(file: str, added_lines, findings: List[Finding]):
    pattern = re.compile(r"DELETE\s+FROM\s+(\w+)", re.IGNORECASE)
    for lineno, line in added_lines:
        for m in pattern.finditer(line):
            tbl = m.group(1).lower()
            if tbl in SENSITIVE_TABLES:
                findings.append(Finding(
                    severity="block", file=file, line_hint=lineno,
                    rule="patient_data_delete",
                    message=f"Hasta verisi silme tespit edildi: DELETE FROM {tbl}. archived_at kullanin.",
                    snippet=line.strip(),
                ))


def _check_nas_unlink(file: str, added_lines, findings: List[Finding]):
    unlink_pattern = re.compile(r"\b(os\.remove|os\.unlink|shutil\.rmtree|Path\(.*\)\.unlink)\b")
    for lineno, line in added_lines:
        if unlink_pattern.search(line):
            for hint in NAS_PATH_HINTS:
                if re.search(hint, line):
                    findings.append(Finding(
                        severity="block", file=file, line_hint=lineno,
                        rule="nas_python_delete",
                        message="NAS path icin Python silme cagrisi tespit edildi.",
                        snippet=line.strip(),
                    ))
                    break
            else:
                # NAS path olmasa bile genel uyari
                findings.append(Finding(
                    severity="warn", file=file, line_hint=lineno,
                    rule="filesystem_delete",
                    message="Dosya silme cagrisi - hasta/NAS path icin kullanilmadigindan emin olun.",
                    snippet=line.strip(),
                ))


def _check_new_route_registered(file: str, added_lines, all_diff_files, findings: List[Finding]):
    # @app.route veya @bp.route eklenmis mi?
    route_re = re.compile(r"@\w+\.route\(['\"]([^'\"]+)['\"]")
    new_routes = []
    for lineno, line in added_lines:
        m = route_re.search(line)
        if m:
            new_routes.append((lineno, m.group(1)))
    if new_routes:
        if not any(f.endswith("yazklinik_feature_sync.py") for f in all_diff_files):
            for lineno, path in new_routes:
                findings.append(Finding(
                    severity="warn", file=file, line_hint=lineno,
                    rule="route_not_registered",
                    message=f"Yeni route {path} eklendi ama yazklinik_feature_sync.py guncellenmemis.",
                ))


MOJIBAKE_TOKENS_SHORT = ("Ã¢", "Ã©", "Ã±", "Ã¶", "Ã¼", "Ã§", "Â§", "â€™", "Â©")


def _check_mojibake_added(file: str, added_lines, findings: List[Finding]):
    for lineno, line in added_lines:
        for token in MOJIBAKE_TOKENS_SHORT:
            if token in line:
                findings.append(Finding(
                    severity="warn", file=file, line_hint=lineno,
                    rule="mojibake_new",
                    message=f"PR yeni mojibake getiriyor ({token!r}). ASCII-safe yazin veya UTF-8 kontrol edin.",
                    snippet=line.strip()[:120],
                ))
                break


def _check_mass_format(files_touched, total_added, total_removed, findings: List[Finding]):
    # Cok dosya + cok satir = mass reformat suphesi
    if len(files_touched) > 10 and (total_added + total_removed) > 500:
        findings.append(Finding(
            severity="warn", file="(PR genel)", line_hint=None,
            rule="mass_format_suspect",
            message=f"{len(files_touched)} dosya + {total_added + total_removed} satir. "
                    "Toplu formatlama olabilir; AGENTS.md kurali geregi kucuk hedefli patch tercih edilir.",
        ))


def review_diff(diff_text: str) -> ReviewResult:
    """Ana giris noktasi. Diff metnini al, sablonsuz bul."""
    result = ReviewResult(reviewed_at=datetime.now().isoformat(timespec="seconds"))
    if not diff_text or not diff_text.strip():
        result.summary = "Bos diff."
        return result

    # Once dosyalari ve eklenen/silinen satirlari topla
    files_data: List[Tuple[str, list, list]] = list(_iter_diff_files(diff_text))
    all_files = [f for f, _, _ in files_data]
    result.files_touched = all_files

    for file, added, removed in files_data:
        result.total_added += len(added)
        result.total_removed += len(removed)

        _check_protected(file, result.findings)
        _check_patient_delete(file, added, result.findings)
        _check_nas_unlink(file, added, result.findings)
        _check_new_route_registered(file, added, all_files, result.findings)
        _check_mojibake_added(file, added, result.findings)

    _check_mass_format(all_files, result.total_added, result.total_removed, result.findings)

    blockers = [f for f in result.findings if f.severity == "block"]
    warns = [f for f in result.findings if f.severity == "warn"]
    result.has_blockers = bool(blockers)
    result.summary = (
        f"{len(all_files)} dosya, +{result.total_added}/-{result.total_removed} satir. "
        f"Blocker: {len(blockers)}, Uyari: {len(warns)}."
    )
    return result


def to_audit_payload(result: ReviewResult) -> Dict[str, Any]:
    payload = asdict(result)
    status = "block" if result.has_blockers else ("warn" if result.findings else "ok")
    payload["action"] = f"pr_review:{status}"
    return payload


if __name__ == "__main__":
    sample_diff = """diff --git a/yazklinik_v68.py b/yazklinik_v68.py
--- a/yazklinik_v68.py
+++ b/yazklinik_v68.py
@@ -10,3 +10,5 @@
 import os
+# yeni satir
+print('hello')
 print('world')
diff --git a/yazklinik_web.py b/yazklinik_web.py
--- a/yazklinik_web.py
+++ b/yazklinik_web.py
@@ -100,3 +100,4 @@
+@app.route('/api/new')
+def new_route():
+    conn.execute("DELETE FROM patients WHERE id=1")
+    return "ok"
"""
    r = review_diff(sample_diff)
    print(r.summary)
    for f in r.findings:
        print(f"  [{f.severity}] {f.file}:{f.line_hint} ({f.rule}) -> {f.message}")
