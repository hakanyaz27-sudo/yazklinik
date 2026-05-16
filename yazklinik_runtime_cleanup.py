"""Safe startup cleanup for YazKlinik FINAL3000.

This module removes only generated runtime leftovers. It must never touch
patient uploads, databases, configuration, certificates, or virtualenvs.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional


ROOT_ARTIFACT_FILES = (
    "server_stdout.log",
    "server_stderr.log",
    "_apply_final3000_config.log",
    "orthanc_preflight_status.json",
    "active_patient.json",
)

TEMP_ARTIFACT_DIRS = (
    "yazklinik_wa_share",
    "yazklinik_wa_zip",
    "YazKlinikWhatsAppShare",
    "YazKlinikWhatsAppHelper",
)

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "uploads",
    "certs",
}


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except Exception:
        return False


def _remove_file(path: Path, dry_run: bool, removed: List[str],
                 errors: List[str]) -> None:
    try:
        if not path.exists() or not path.is_file():
            return
        if not dry_run:
            path.unlink()
        removed.append(str(path))
    except Exception as ex:
        errors.append(f"{path}: {ex}")


def _remove_dir(path: Path, dry_run: bool, removed: List[str],
                errors: List[str]) -> None:
    try:
        if not path.exists() or not path.is_dir():
            return
        if not dry_run:
            shutil.rmtree(path, ignore_errors=False)
        removed.append(str(path))
    except Exception as ex:
        errors.append(f"{path}: {ex}")


def _iter_pycache_dirs(root: Path) -> Iterable[Path]:
    for current, dirnames, _filenames in os.walk(root):
        current_path = Path(current)
        dirnames[:] = [
            name for name in dirnames
            if name not in SKIP_DIR_NAMES
        ]
        if current_path.name == "__pycache__":
            dirnames[:] = []
            yield current_path


def _iter_orphan_pyc(root: Path) -> Iterable[Path]:
    for current, dirnames, filenames in os.walk(root):
        current_path = Path(current)
        dirnames[:] = [
            name for name in dirnames
            if name not in SKIP_DIR_NAMES and name != "__pycache__"
        ]
        for name in filenames:
            if name.lower().endswith((".pyc", ".pyo")):
                yield current_path / name


def _env_int(name: str, default: int) -> int:
    try:
        raw = (os.environ.get(name) or "").strip()
        return int(raw) if raw else int(default)
    except Exception:
        return int(default)


def _stop_stale_yazklinik_servers(
    dry_run: bool,
    stopped: List[str],
    errors: List[str],
) -> None:
    """Stop old YazKlinik web processes bound to the configured local ports."""
    if os.name != "nt":
        return
    ports = sorted({
        _env_int("YAZKLINIK_WEB_PORT", 5052),
        _env_int("YAZKLINIK_HTTPS_PORT", 5443),
    })
    port_list = ",".join(str(port) for port in ports if port > 0)
    if not port_list:
        return
    current_pid = os.getpid()
    dry_run_ps = "$true" if dry_run else "$false"
    script = f"""
$ErrorActionPreference = 'Stop'
$ports = @({port_list})
$currentPid = {current_pid}
$dryRun = {dry_run_ps}
$seen = @{{}}
$hits = @()
$connections = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | Where-Object {{ $ports -contains $_.LocalPort }}
foreach ($conn in $connections) {{
    $pidNum = [int]$conn.OwningProcess
    if ($pidNum -eq $currentPid -or $seen.ContainsKey([string]$pidNum)) {{ continue }}
    $proc = Get-CimInstance Win32_Process -Filter ("ProcessId=" + $pidNum) -ErrorAction SilentlyContinue
    if ($null -eq $proc -or $null -eq $proc.CommandLine) {{ continue }}
    if ($proc.CommandLine -notmatch 'yazklinik_web\\.py') {{ continue }}
    $seen[[string]$pidNum] = $true
    $hits += [pscustomobject]@{{
        pid = $pidNum
        port = [int]$conn.LocalPort
        commandLine = [string]$proc.CommandLine
    }}
    if (-not $dryRun) {{
        Stop-Process -Id $pidNum -Force -ErrorAction Stop
    }}
}}
$hits | ConvertTo-Json -Compress
"""
    try:
        completed = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                script,
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            if detail:
                errors.append(f"stale server cleanup: {detail}")
            return
        output = (completed.stdout or "").strip()
        if not output:
            return
        try:
            import json

            payload = json.loads(output)
            rows = payload if isinstance(payload, list) else [payload]
            for row in rows:
                pid = row.get("pid")
                port = row.get("port")
                if pid:
                    label = f"pid={pid}"
                    if port:
                        label += f" port={port}"
                    stopped.append(label)
        except Exception:
            stopped.append(output)
    except Exception as ex:
        errors.append(f"stale server cleanup: {ex}")


def run_startup_cleanup(
    app_root: Optional[Path | str] = None,
    version: str = "",
    dry_run: bool = False,
    temp_root: Optional[Path | str] = None,
    stop_stale_servers: bool = True,
) -> Dict[str, object]:
    """Clean generated leftovers from previous runs.

    The target list is intentionally narrow. This function is safe to call from
    the server launcher, web app startup, and desktop shell startup.
    """
    root = Path(app_root or Path(__file__).resolve().parent).resolve()
    tmp = Path(temp_root or tempfile.gettempdir()).resolve()
    removed: List[str] = []
    errors: List[str] = []
    stopped_servers: List[str] = []

    if stop_stale_servers:
        _stop_stale_yazklinik_servers(dry_run, stopped_servers, errors)

    for name in ROOT_ARTIFACT_FILES:
        target = (root / name).resolve()
        if _is_relative_to(target, root):
            _remove_file(target, dry_run, removed, errors)

    for pycache_dir in list(_iter_pycache_dirs(root)):
        target = pycache_dir.resolve()
        if _is_relative_to(target, root):
            _remove_dir(target, dry_run, removed, errors)

    for pyc_file in list(_iter_orphan_pyc(root)):
        target = pyc_file.resolve()
        if _is_relative_to(target, root):
            _remove_file(target, dry_run, removed, errors)

    for name in TEMP_ARTIFACT_DIRS:
        target = (tmp / name).resolve()
        if _is_relative_to(target, tmp):
            _remove_dir(target, dry_run, removed, errors)

    return {
        "ok": not errors,
        "version": str(version or ""),
        "root": str(root),
        "temp_root": str(tmp),
        "removed_count": len(removed),
        "removed": removed,
        "stopped_servers_count": len(stopped_servers),
        "stopped_servers": stopped_servers,
        "errors": errors,
        "dry_run": bool(dry_run),
    }


if __name__ == "__main__":
    result = run_startup_cleanup()
    print(
        "YAZKLINIK_CLEANUP "
        f"removed={result['removed_count']} "
        f"errors={len(result['errors'])}"
    )
