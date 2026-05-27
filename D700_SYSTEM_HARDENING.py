#!/usr/bin/env python
"""D700_SYSTEM_HARDENING.py - YazKlinik D700 stability guard.

Safe operations only:
- no patient row deletes
- no NAS deletes
- generated verified backups are kept under auto_backups/verified
- archived logs are moved under runtime_state/archived_logs
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "runtime_state" / "hardening"
STATE.mkdir(parents=True, exist_ok=True)


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def load_env():
    cfg = {}
    path = ROOT / "config.env"
    if path.exists():
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            cfg[k.strip()] = v.strip()
    for k, v in cfg.items():
        os.environ.setdefault(k, v)
    return cfg


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def env_int(name, default, lo=None, hi=None):
    try:
        value = int(str(os.environ.get(name, default)).strip())
    except Exception:
        value = int(default)
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


def resolve_path(value, default):
    text = str(value or default)
    return Path(text).expanduser()


def write_report(name, data):
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / f"{name}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [f"D700 {name} report", f"time={data.get('time', now_iso())}"]
    for key, value in data.items():
        if key == "time":
            continue
        if isinstance(value, (dict, list)):
            lines.append(f"{key}={json.dumps(value, ensure_ascii=False)}")
        else:
            lines.append(f"{key}={value}")
    (STATE / f"{name}.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run(cmd, timeout=None):
    return subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, timeout=timeout)


def cmd_lock(args):
    load_env()
    proc = run([sys.executable, "-m", "pip", "freeze", "--local"], timeout=180)
    if proc.returncode != 0:
        print(proc.stderr.strip() or proc.stdout.strip())
        return 0 if args.soft else proc.returncode
    lines = []
    for line in proc.stdout.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.lower().startswith("-e "):
            continue
        lines.append(s)
    lines = sorted(dict.fromkeys(lines), key=str.lower)
    out = ROOT / "requirements-lock.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    meta = {
        "time": now_iso(),
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "count": len(lines),
        "file": str(out),
    }
    write_report("requirements_lock", meta)
    print(f"LOCK_OK count={len(lines)} file={out}")
    return 0


def _lock_lines():
    lock = ROOT / "requirements-lock.txt"
    if not lock.exists():
        return []
    return [x.strip() for x in lock.read_text(encoding="utf-8", errors="replace").splitlines() if x.strip() and not x.strip().startswith("#")]


def _downloadable_lines(lines):
    keep = []
    skipped = []
    for line in lines:
        low = line.lower()
        if low.startswith("-e ") or " @ file:" in low or low.startswith("file:"):
            skipped.append({"requirement": line, "reason": "local_or_editable"})
            continue
        keep.append(line)
    return keep, skipped


def _wheelhouse_summary(wheelhouse):
    files = [p for p in wheelhouse.glob("*") if p.is_file()]
    total = sum((p.stat().st_size for p in files), 0)
    return {"count": len(files), "size_mb": round(total / 1024 / 1024, 2), "path": str(wheelhouse)}


def cmd_wheelhouse_download(args):
    load_env()
    if not (ROOT / "requirements-lock.txt").exists():
        rc = cmd_lock(argparse.Namespace(soft=True))
        if rc != 0:
            return 0 if args.soft else rc
    wheelhouse = resolve_path(os.environ.get("YAZKLINIK_WHEELHOUSE_DIR"), ROOT / "wheelhouse")
    wheelhouse.mkdir(parents=True, exist_ok=True)
    lines, skipped = _downloadable_lines(_lock_lines())
    filtered = STATE / "requirements-lock-download.txt"
    filtered.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = {"time": now_iso(), "wheelhouse": str(wheelhouse), "requested": len(lines), "skipped": skipped, "fallback": [], "ok": False}
    if not lines:
        report["ok"] = True
        report["summary"] = _wheelhouse_summary(wheelhouse)
        write_report("wheelhouse_download", report)
        print("WHEELHOUSE_OK requested=0")
        return 0
    base = [sys.executable, "-m", "pip", "download", "--no-deps", "--timeout", "60", "--retries", "2", "--dest", str(wheelhouse)]
    proc = run(base + ["-r", str(filtered)], timeout=3600)
    report["bulk_returncode"] = proc.returncode
    report["bulk_stdout_tail"] = proc.stdout[-4000:]
    report["bulk_stderr_tail"] = proc.stderr[-4000:]
    if proc.returncode != 0:
        failures = []
        successes = 0
        for req in lines:
            one = run(base + [req], timeout=900)
            item = {"requirement": req, "returncode": one.returncode}
            if one.returncode == 0:
                successes += 1
            else:
                item["stderr_tail"] = one.stderr[-1200:]
                item["stdout_tail"] = one.stdout[-1200:]
                failures.append(item)
            report["fallback"].append(item)
        special_index_downloads = []
        remaining_failures = []
        for item in failures:
            req = str(item.get("requirement") or "")
            if req.startswith(("torch==", "torchaudio==", "torchvision==")) and "+cu128" in req:
                one = run(
                    base + ["--pre", "--index-url", "https://download.pytorch.org/whl/nightly/cu128", req],
                    timeout=1800,
                )
                special_item = {"requirement": req, "returncode": one.returncode, "index": "pytorch-nightly-cu128"}
                if one.returncode != 0:
                    special_item["stderr_tail"] = one.stderr[-1200:]
                    special_item["stdout_tail"] = one.stdout[-1200:]
                    remaining_failures.append(item)
                special_index_downloads.append(special_item)
            else:
                remaining_failures.append(item)
        failures = remaining_failures
        report["fallback_successes"] = successes
        report["special_index_downloads"] = special_index_downloads
        report["failures"] = failures
        report["ok"] = len(failures) == 0
    else:
        report["ok"] = True
    report["summary"] = _wheelhouse_summary(wheelhouse)
    write_report("wheelhouse_download", report)
    status = "WHEELHOUSE_OK" if report["ok"] else "WHEELHOUSE_PARTIAL"
    print(f"{status} files={report['summary']['count']} size_mb={report['summary']['size_mb']} report={STATE / 'wheelhouse_download.json'}")
    return 0 if (report["ok"] or args.soft) else 1


def cmd_backup_restore_check(args):
    cfg = load_env()
    db_path = resolve_path(os.environ.get("YAZKLINIK_DB_PATH") or cfg.get("YAZKLINIK_DB_PATH"), ROOT / "local_db" / "yazklinik_v68.sqlite3")
    backup_root = resolve_path(os.environ.get("YAZKLINIK_BACKUP_ROOT") or cfg.get("YAZKLINIK_BACKUP_ROOT"), ROOT / "auto_backups")
    verified = backup_root / "verified"
    verified.mkdir(parents=True, exist_ok=True)
    report = {"time": now_iso(), "db": str(db_path), "backup_dir": str(verified), "ok": False}
    try:
        if not db_path.exists():
            raise FileNotFoundError(str(db_path))
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        target = verified / f"D700_verified_{stamp}.sqlite3"
        src = sqlite3.connect(str(db_path), timeout=10)
        dst = sqlite3.connect(str(target), timeout=10)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()
        con = sqlite3.connect(str(target), timeout=10)
        try:
            integrity = (con.execute("PRAGMA integrity_check").fetchone() or [""])[0]
            quick = (con.execute("PRAGMA quick_check").fetchone() or [""])[0]
            tables = con.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0]
            patients = None
            try:
                patients = con.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
            except Exception:
                pass
        finally:
            con.close()
        report.update({
            "backup": str(target),
            "size_mb": round(target.stat().st_size / 1024 / 1024, 2),
            "integrity_check": integrity,
            "quick_check": quick,
            "tables": tables,
            "patients": patients,
            "ok": str(integrity).lower() == "ok" and str(quick).lower() == "ok" and tables > 0,
        })
        keep = env_int("YAZKLINIK_BACKUP_VERIFY_KEEP", 14, 1, 200)
        old = sorted(verified.glob("D700_verified_*.sqlite3"), key=lambda p: p.stat().st_mtime, reverse=True)
        pruned = []
        for p in old[keep:]:
            try:
                p.unlink()
                pruned.append(str(p))
            except Exception:
                pass
        report["pruned_generated_backups"] = pruned
    except Exception as ex:
        report["error"] = str(ex)
    write_report("backup_restore_check", report)
    print(("BACKUP_RESTORE_OK" if report.get("ok") else "BACKUP_RESTORE_FAIL") + f" report={STATE / 'backup_restore_check.json'}")
    return 0 if (report.get("ok") or args.soft) else 1


def cmd_log_rotate(args):
    load_env()
    archive = ROOT / "runtime_state" / "archived_logs" / datetime.now().strftime("%Y-%m")
    archive.mkdir(parents=True, exist_ok=True)
    min_age_days = env_int("YAZKLINIK_LOG_ROTATE_MIN_AGE_DAYS", 2, 0, 365)
    max_mb = env_int("YAZKLINIK_LOG_ROTATE_MAX_MB", 20, 1, 2048)
    retention = env_int("YAZKLINIK_LOG_RETENTION_DAYS", 60, 7, 3650)
    cutoff = time.time() - (min_age_days * 86400)
    moved = []
    skipped = []
    for p in ROOT.glob("*.log"):
        try:
            st = p.stat()
            too_old = st.st_mtime < cutoff
            too_big = st.st_size > max_mb * 1024 * 1024
            if not (too_old or too_big):
                continue
            target = archive / p.name
            if target.exists():
                target = archive / f"{p.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{p.suffix}"
            shutil.move(str(p), str(target))
            moved.append({"from": str(p), "to": str(target)})
        except Exception as ex:
            skipped.append({"file": str(p), "error": str(ex)})
    pruned = []
    prune_cutoff = time.time() - (retention * 86400)
    root_archive = ROOT / "runtime_state" / "archived_logs"
    if root_archive.exists():
        for p in root_archive.rglob("*.log"):
            try:
                if p.stat().st_mtime < prune_cutoff:
                    p.unlink()
                    pruned.append(str(p))
            except Exception:
                pass
    report = {"time": now_iso(), "ok": True, "moved": moved, "skipped": skipped, "pruned_archived_logs": pruned}
    write_report("log_rotate", report)
    print(f"LOG_ROTATE_OK moved={len(moved)} pruned={len(pruned)} report={STATE / 'log_rotate.json'}")
    return 0


def _nas_status(cfg):
    root = os.environ.get("YAZKLINIK_NAS_ROOT") or cfg.get("YAZKLINIK_NAS_ROOT", "")
    if not root:
        return {"configured": False, "ok": False, "path": ""}
    test = root[:-len("\\Hastalar")] if root.lower().endswith("\\hastalar") else root
    return {"configured": True, "ok": Path(test).exists(), "path": test, "soft_fail": env_bool("YAZKLINIK_NAS_SOFT_FAIL", True)}


def cmd_boot_check(args):
    cfg = load_env()
    hardening_enabled = env_bool("YAZKLINIK_HARDENING_ENABLED", True)
    report = {"time": now_iso(), "ok": True, "enabled": hardening_enabled, "checks": {}}
    if not hardening_enabled:
        write_report("boot_check", report)
        print("BOOT_CHECK_DISABLED")
        return 0
    db_path = resolve_path(os.environ.get("YAZKLINIK_DB_PATH") or cfg.get("YAZKLINIK_DB_PATH"), ROOT / "local_db" / "yazklinik_v68.sqlite3")
    report["checks"]["db_exists"] = db_path.exists()
    if not db_path.exists():
        report["ok"] = False
    report["checks"]["nas"] = _nas_status(cfg)
    if report["checks"]["nas"].get("configured") and not report["checks"]["nas"].get("ok") and not report["checks"]["nas"].get("soft_fail"):
        report["ok"] = False
    lock = ROOT / "requirements-lock.txt"
    wheelhouse = resolve_path(os.environ.get("YAZKLINIK_WHEELHOUSE_DIR"), ROOT / "wheelhouse")
    report["checks"]["requirements_lock"] = lock.exists()
    report["checks"]["wheelhouse"] = _wheelhouse_summary(wheelhouse) if wheelhouse.exists() else {"count": 0, "size_mb": 0, "path": str(wheelhouse)}
    if env_bool("YAZKLINIK_LOG_ROTATE_ON_BOOT", True):
        cmd_log_rotate(argparse.Namespace(soft=True))
    if env_bool("YAZKLINIK_BACKUP_RESTORE_CHECK_ON_BOOT", True):
        marker = STATE / "backup_restore_check.json"
        due = True
        if marker.exists():
            age_hours = (time.time() - marker.stat().st_mtime) / 3600.0
            due = age_hours >= env_int("YAZKLINIK_BACKUP_RESTORE_INTERVAL_HOURS", 24, 1, 720)
        if due:
            cmd_backup_restore_check(argparse.Namespace(soft=True))
            report["checks"]["backup_restore_due_ran"] = True
        else:
            report["checks"]["backup_restore_due_ran"] = False
    write_report("boot_check", report)
    print(("BOOT_CHECK_OK" if report["ok"] else "BOOT_CHECK_WARN") + f" report={STATE / 'boot_check.json'}")
    return 0 if (report["ok"] or args.soft) else 1


def cmd_all(args):
    rc = 0
    for fn in (cmd_lock, cmd_backup_restore_check, cmd_log_rotate, cmd_wheelhouse_download, cmd_boot_check):
        one = fn(argparse.Namespace(soft=True))
        rc = max(rc, one)
    return 0 if args.soft else rc


def main():
    parser = argparse.ArgumentParser(description="YazKlinik D700 hardening guard")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("lock", "wheelhouse-download", "backup-restore-check", "log-rotate", "boot-check", "all"):
        p = sub.add_parser(name)
        p.add_argument("--soft", action="store_true", help="write report but return success for launcher flow")
    args = parser.parse_args()
    return {
        "lock": cmd_lock,
        "wheelhouse-download": cmd_wheelhouse_download,
        "backup-restore-check": cmd_backup_restore_check,
        "log-rotate": cmd_log_rotate,
        "boot-check": cmd_boot_check,
        "all": cmd_all,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())

