#!/usr/bin/env python
"""D700_PERF_AUDIT.py - safe performance audit for YazKlinik D700.

This script is read-only for patient/NAS data. It measures:
- live route latency, when the web server is up
- SQLite health/query/index signals
- NAS first-hop latency
- local AI/helper service health
- recent slow-route JSONL entries emitted by yazklinik_web.py
"""
from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sqlite3
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STATE_DIR = ROOT / "runtime_state" / "perf"


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def now_iso() -> str:
    return datetime.now().isoformat(sep=" ", timespec="seconds")


def load_env() -> dict:
    cfg = {}
    env_path = ROOT / "config.env"
    if env_path.exists():
        for raw in env_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            cfg[key] = value
            os.environ.setdefault(key, value)
    return cfg


def env_int(name: str, default: int, lo: int | None = None, hi: int | None = None) -> int:
    try:
        value = int(str(os.environ.get(name, default)).strip())
    except Exception:
        value = int(default)
    if lo is not None:
        value = max(lo, value)
    if hi is not None:
        value = min(hi, value)
    return value


def resolve_path(raw: str | None, default: Path) -> Path:
    text = str(raw or default)
    return Path(text).expanduser()


def read_smoke_credentials() -> tuple[str, str]:
    user = os.environ.get("YAZKLINIK_SMOKE_USER", "doktor").strip() or "doktor"
    password = os.environ.get("YAZKLINIK_SMOKE_PASSWORD", "").strip()
    if password:
        return user, password
    try:
        users = json.loads((ROOT / "users.json").read_text(encoding="utf-8-sig", errors="replace"))
        item = users.get(user) or {}
        if isinstance(item, dict):
            password = str(
                item.get("password")
                or item.get("sifre")
                or item.get("pin")
                or ""
            ).strip()
    except Exception:
        password = ""
    return user, password or "1234"


class HttpProbe:
    def __init__(self, base_url: str, timeout: float, max_read: int):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_read = max_read
        self.cookie_jar = http.cookiejar.CookieJar()
        handlers = [urllib.request.HTTPCookieProcessor(self.cookie_jar)]
        if self.base_url.lower().startswith("https://"):
            handlers.append(urllib.request.HTTPSHandler(context=ssl._create_unverified_context()))
        self.opener = urllib.request.build_opener(*handlers)

    def request(self, path: str, data: dict | None = None, label: str | None = None) -> dict:
        url = self.base_url + (path if path.startswith("/") else "/" + path)
        body = None
        headers = {"User-Agent": "D700_PERF_AUDIT/1.0"}
        if data is not None:
            body = urllib.parse.urlencode(data).encode("utf-8")
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        started = time.perf_counter()
        try:
            req = urllib.request.Request(url, data=body, headers=headers)
            with self.opener.open(req, timeout=self.timeout) as resp:
                payload = resp.read(self.max_read)
                elapsed_ms = int((time.perf_counter() - started) * 1000)
                return {
                    "path": path,
                    "label": label or path,
                    "ok": True,
                    "status": int(getattr(resp, "status", 0) or 0),
                    "elapsed_ms": elapsed_ms,
                    "bytes_sampled": len(payload or b""),
                    "perf_header_ms": resp.headers.get("X-YK-Perf-Ms"),
                    "final_path": urllib.parse.urlsplit(getattr(resp, "url", url)).path,
                }
        except urllib.error.HTTPError as ex:
            try:
                payload = ex.read(self.max_read)
            except Exception:
                payload = b""
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return {
                "path": path,
                "label": label or path,
                "ok": int(getattr(ex, "code", 0) or 0) < 500,
                "status": int(getattr(ex, "code", 0) or 0),
                "elapsed_ms": elapsed_ms,
                "bytes_sampled": len(payload or b""),
                "error": str(ex)[:240],
            }
        except Exception as ex:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return {
                "path": path,
                "label": label or path,
                "ok": False,
                "status": 0,
                "elapsed_ms": elapsed_ms,
                "bytes_sampled": 0,
                "error": str(ex)[:240],
            }


def sample_patient_keys(limit: int = 40) -> list[str]:
    cfg = load_env()
    db_path = resolve_path(
        os.environ.get("YAZKLINIK_DB_PATH") or cfg.get("YAZKLINIK_DB_PATH"),
        ROOT / "local_db" / "yazklinik_v68.sqlite3",
    )
    if not db_path.exists():
        return []
    try:
        con = sqlite3.connect(str(db_path), timeout=3)
        rows = con.execute(
            "SELECT folder_key FROM patients "
            "WHERE coalesce(archived_at, '') = '' "
            "ORDER BY folder_key LIMIT ?",
            (max(1, min(int(limit), 60)),),
        ).fetchall()
        con.close()
        return [str(row[0]) for row in rows if row and row[0]]
    except Exception:
        return []


def route_audit(base_url: str, repeat: int, timeout: float, max_read: int) -> dict:
    probe = HttpProbe(base_url, timeout=timeout, max_read=max_read)
    login_user, login_password = read_smoke_credentials()
    ping = probe.request("/giris")
    login = probe.request("/giris", {"username": login_user, "password": login_password})
    keys = sample_patient_keys(limit=40)
    ga_query = urllib.parse.urlencode({"keys": ",".join(keys)}) if keys else "keys=__none__"
    routes = [
        ("/", "/"),
        ("/hastalar", "/hastalar"),
        ("/hasta-islemleri", "/hasta-islemleri"),
        ("/doguranlar", "/doguranlar"),
        ("/yaklasan-dogumlar", "/yaklasan-dogumlar"),
        ("/tedavi-planla", "/tedavi-planla"),
        ("/sistem-ayarlari", "/sistem-ayarlari"),
        ("/ses-ve-alex", "/ses-ve-alex"),
        ("/akilli-dialog", "/akilli-dialog"),
        ("/api/sistem-durumu", "/api/sistem-durumu"),
        ("/api/pdf-destek-durumu", "/api/pdf-destek-durumu"),
        ("/api/hizmet-ajanlari?force=1", "/api/hizmet-ajanlari?force=1"),
        ("/api/phone/voice-capabilities", "/api/phone/voice-capabilities"),
        ("/api/mikrofon/tani", "/api/mikrofon/tani"),
        (f"/api/hasta-ga-batch[{len(keys)}]", f"/api/hasta-ga-batch?{ga_query}"),
    ]
    results = []
    if not ping.get("ok"):
        return {
            "base_url": base_url,
            "server_up": False,
            "ping": ping,
            "login": login,
            "routes": results,
            "slowest": [],
        }
    for _ in range(max(1, repeat)):
        for label, route in routes:
            results.append(probe.request(route, label=label))
    grouped = defaultdict(list)
    for item in results:
        grouped[item.get("label") or item["path"]].append(item)
    summary = []
    for path, items in grouped.items():
        times = [int(x.get("elapsed_ms") or 0) for x in items]
        errors = [x for x in items if not x.get("ok")]
        summary.append({
            "path": path,
            "count": len(items),
            "ok": len(errors) == 0,
            "max_ms": max(times) if times else 0,
            "avg_ms": round(sum(times) / len(times), 1) if times else 0,
            "statuses": sorted({int(x.get("status") or 0) for x in items}),
            "perf_header_ms": [x.get("perf_header_ms") for x in items if x.get("perf_header_ms")],
            "errors": [str(x.get("error") or "")[:160] for x in errors[:3]],
        })
    summary.sort(key=lambda x: int(x.get("max_ms") or 0), reverse=True)
    return {
        "base_url": base_url,
        "server_up": True,
        "ping": ping,
        "login": login,
        "routes": results,
        "slowest": summary[:8],
    }


def timed_db_query(con: sqlite3.Connection, label: str, sql: str, params: tuple = ()) -> dict:
    started = time.perf_counter()
    try:
        row = con.execute(sql, params).fetchone()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {"label": label, "ok": True, "elapsed_ms": elapsed_ms, "value": list(row or [])[:4]}
    except Exception as ex:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {"label": label, "ok": False, "elapsed_ms": elapsed_ms, "error": str(ex)[:240]}


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    try:
        return {str(row[1]) for row in con.execute(f"PRAGMA table_info({table})").fetchall()}
    except Exception:
        return set()


def table_index_columns(con: sqlite3.Connection, table: str) -> list[list[str]]:
    found = []
    try:
        for item in con.execute(f"PRAGMA index_list({table})").fetchall():
            idx_name = str(item[1])
            cols = [str(row[2]) for row in con.execute(f"PRAGMA index_info({idx_name})").fetchall()]
            if cols:
                found.append(cols)
    except Exception:
        pass
    return found


def has_index_prefix(indexes: list[list[str]], wanted: tuple[str, ...]) -> bool:
    wanted_list = list(wanted)
    for cols in indexes:
        if cols[: len(wanted_list)] == wanted_list:
            return True
    return False


def db_audit(cfg: dict) -> dict:
    db_path = resolve_path(
        os.environ.get("YAZKLINIK_DB_PATH") or cfg.get("YAZKLINIK_DB_PATH"),
        ROOT / "local_db" / "yazklinik_v68.sqlite3",
    )
    report = {"db_path": str(db_path), "exists": db_path.exists(), "queries": [], "missing_indexes": []}
    if not db_path.exists():
        report["ok"] = False
        report["error"] = "db_not_found"
        return report
    wal_path = Path(str(db_path) + "-wal")
    shm_path = Path(str(db_path) + "-shm")
    report["size_mb"] = round(db_path.stat().st_size / 1024 / 1024, 2)
    report["wal_mb"] = round(wal_path.stat().st_size / 1024 / 1024, 2) if wal_path.exists() else 0
    report["shm_mb"] = round(shm_path.stat().st_size / 1024 / 1024, 2) if shm_path.exists() else 0
    started = time.perf_counter()
    try:
        con = sqlite3.connect(str(db_path), timeout=3)
        con.execute("PRAGMA busy_timeout=3000")
        report["connect_ms"] = int((time.perf_counter() - started) * 1000)
        report["journal_mode"] = (con.execute("PRAGMA journal_mode").fetchone() or ["?"])[0]
        report["quick_check"] = (con.execute("PRAGMA quick_check").fetchone() or ["?"])[0]
        queries = [
            ("patients_count", "SELECT COUNT(*) FROM patients", ()),
            ("visits_count", "SELECT COUNT(*) FROM visits", ()),
            ("files_count", "SELECT COUNT(*) FROM files", ()),
            ("pdf_files_count", "SELECT COUNT(*) FROM files WHERE lower(file_kind)='pdf'", ()),
            ("recent_visits", "SELECT COUNT(*) FROM visits WHERE date(created_at) >= date('now','-30 day')", ()),
        ]
        try:
            hot = con.execute(
                "SELECT patient_folder_key, COUNT(*) AS c FROM files "
                "GROUP BY patient_folder_key ORDER BY c DESC LIMIT 1"
            ).fetchone()
            if hot and hot[0]:
                queries.append((
                    "hot_patient_files",
                    "SELECT COUNT(*) FROM files WHERE patient_folder_key=?",
                    (str(hot[0]),),
                ))
                report["hot_patient_file_count"] = int(hot[1] or 0)
        except Exception:
            pass
        for label, sql, params in queries:
            report["queries"].append(timed_db_query(con, label, sql, params))
        wanted_indexes = {
            "files": [
                ("patient_folder_key",),
                ("patient_folder_key", "visit_key", "file_kind"),
                ("file_kind",),
            ],
            "visits": [("patient_folder_key",), ("created_at",)],
            "usg_measurements": [("patient_key",)],
            "patient_demographics": [("patient_key",)],
            "web_audit_log": [("patient_key",)],
        }
        for table, wants in wanted_indexes.items():
            cols = table_columns(con, table)
            indexes = table_index_columns(con, table)
            for want in wants:
                if set(want).issubset(cols) and not has_index_prefix(indexes, want):
                    report["missing_indexes"].append({
                        "table": table,
                        "columns": list(want),
                        "sql": f"CREATE INDEX IF NOT EXISTS idx_perf_{table}_{'_'.join(want)} ON {table}({', '.join(want)});",
                    })
        lock_started = time.perf_counter()
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute("ROLLBACK")
            report["write_lock_probe"] = {
                "ok": True,
                "elapsed_ms": int((time.perf_counter() - lock_started) * 1000),
            }
        except Exception as ex:
            report["write_lock_probe"] = {
                "ok": False,
                "elapsed_ms": int((time.perf_counter() - lock_started) * 1000),
                "error": str(ex)[:240],
            }
        con.close()
        report["ok"] = str(report.get("quick_check", "")).lower() == "ok"
    except Exception as ex:
        report["ok"] = False
        report["error"] = str(ex)[:240]
    return report


def nas_audit(cfg: dict) -> dict:
    nas = os.environ.get("YAZKLINIK_NAS_ROOT") or cfg.get("YAZKLINIK_NAS_ROOT") or r"\\asustor\Voluson"
    roots = [nas]
    if not nas.lower().rstrip("\\/").endswith("hastalar"):
        roots.append(str(Path(nas) / "Hastalar"))
    results = []
    for raw in roots:
        started = time.perf_counter()
        item = {"path": raw}
        try:
            exists = os.path.exists(raw)
            item["exists"] = bool(exists)
            item["exists_ms"] = int((time.perf_counter() - started) * 1000)
            if exists:
                scan_started = time.perf_counter()
                dirs = 0
                files = 0
                seen = 0
                with os.scandir(raw) as it:
                    for entry in it:
                        seen += 1
                        try:
                            if entry.is_dir():
                                dirs += 1
                            elif entry.is_file():
                                files += 1
                        except Exception:
                            pass
                        if seen >= 120:
                            break
                item["scan_first_120_ms"] = int((time.perf_counter() - scan_started) * 1000)
                item["sample_dirs"] = dirs
                item["sample_files"] = files
        except Exception as ex:
            item["exists"] = False
            item["error"] = str(ex)[:240]
            item["exists_ms"] = int((time.perf_counter() - started) * 1000)
        results.append(item)
    return {"roots": results, "ok": any(x.get("exists") for x in results)}


def service_audit(cfg: dict, timeout: float) -> dict:
    comfy = (cfg.get("YAZKLINIK_COMFYUI_URL") or os.environ.get("YAZKLINIK_COMFYUI_URL") or "http://127.0.0.1:8188").rstrip("/")
    orthanc = (cfg.get("YAZKLINIK_ORTHANC_URL") or os.environ.get("YAZKLINIK_ORTHANC_URL") or "http://127.0.0.1:8042").rstrip("/")
    patient_portal_enabled = str(
        cfg.get("YAZKLINIK_PATIENT_PORTAL_ENABLED")
        or os.environ.get("YAZKLINIK_PATIENT_PORTAL_ENABLED")
        or "0"
    ).strip().lower() in {"1", "true", "yes", "on", "evet", "aktif"}
    patient_portal_port = env_int("YAZKLINIK_PATIENT_PORTAL_PORT", 5053, 1, 65535)
    checks = [
        ("Ollama", "http://127.0.0.1:11434/api/tags"),
        ("Orthanc", orthanc + "/system"),
        ("Whisper", "http://127.0.0.1:9000/health"),
        ("Piper", "http://127.0.0.1:9001/health"),
        ("SIP Alex", "http://127.0.0.1:9019/status"),
        ("ComfyUI", comfy + "/system_stats"),
    ]
    if patient_portal_enabled:
        checks.insert(
            2,
            ("Hasta Portal", f"http://127.0.0.1:{patient_portal_port}/healthz"),
        )
    results = []
    for label, url in checks:
        started = time.perf_counter()
        try:
            with urllib.request.urlopen(url, timeout=timeout) as resp:
                _ = resp.read(2048)
                results.append({
                    "label": label,
                    "ok": True,
                    "status": int(getattr(resp, "status", 0) or 0),
                    "elapsed_ms": int((time.perf_counter() - started) * 1000),
                })
        except Exception as ex:
            results.append({
                "label": label,
                "ok": False,
                "status": 0,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "error": str(ex)[:180],
            })
    return {"services": results, "ok": all(x.get("ok") for x in results)}


def slow_log_summary(limit: int = 300) -> dict:
    path = STATE_DIR / "slow_routes.jsonl"
    out = {"path": str(path), "exists": path.exists(), "top": []}
    if not path.exists():
        return out
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()[-limit:]
        by_rule = defaultdict(list)
        recent_by_rule = defaultdict(list)
        recent_cutoff = datetime.now() - timedelta(minutes=10)
        latest_ts = ""
        for line in lines:
            try:
                item = json.loads(line)
            except Exception:
                continue
            rule = str(item.get("rule") or item.get("path") or "?")
            duration = int(item.get("duration_ms") or 0)
            by_rule[rule].append(duration)
            ts_text = str(item.get("ts") or "")
            if ts_text > latest_ts:
                latest_ts = ts_text
            try:
                ts = datetime.strptime(ts_text, "%Y-%m-%d %H:%M:%S")
                if ts >= recent_cutoff:
                    recent_by_rule[rule].append(duration)
            except Exception:
                pass
        top = []
        for rule, vals in by_rule.items():
            top.append({
                "rule": rule,
                "count": len(vals),
                "max_ms": max(vals),
                "avg_ms": round(sum(vals) / len(vals), 1),
            })
        top.sort(key=lambda x: int(x.get("max_ms") or 0), reverse=True)
        out["top"] = top[:10]
        recent_top = []
        for rule, vals in recent_by_rule.items():
            recent_top.append({
                "rule": rule,
                "count": len(vals),
                "max_ms": max(vals),
                "avg_ms": round(sum(vals) / len(vals), 1),
            })
        recent_top.sort(key=lambda x: int(x.get("max_ms") or 0), reverse=True)
        out["recent_top"] = recent_top[:10]
        out["recent_minutes"] = 10
        out["latest_ts"] = latest_ts
        out["line_count_sampled"] = len(lines)
    except Exception as ex:
        out["error"] = str(ex)[:240]
    return out


def recommendations(report: dict) -> list[str]:
    recs = []
    route = report.get("route") or {}
    if route.get("skipped"):
        pass
    elif not route.get("server_up"):
        recs.append("Web server kapali: route hiz olcumu icin once 5052/5443 ayaga alinmali.")
    for item in (route.get("slowest") or [])[:3]:
        if int(item.get("max_ms") or 0) >= 1200:
            recs.append(f"Yavas route: {item.get('path')} max={item.get('max_ms')}ms; once bu route cache/lazy-load icin incelenmeli.")
    db = report.get("db") or {}
    if db.get("missing_indexes"):
        recs.append(f"SQLite: {len(db.get('missing_indexes') or [])} olasi eksik index bulundu; yedek + compile sonrasi tek tek eklenebilir.")
    lock = db.get("write_lock_probe") or {}
    if lock and not lock.get("ok"):
        recs.append("SQLite: write-lock probe bekledi/basarisiz oldu; uzun transaction yapan route/job aranacak.")
    for root in (report.get("nas") or {}).get("roots", []):
        if root.get("exists") and int(root.get("scan_first_120_ms") or 0) >= 800:
            recs.append(f"NAS: {root.get('path')} ilk listeleme {root.get('scan_first_120_ms')}ms; route icinde rglob yerine manifest/cache kullanilmali.")
    if not recs:
        recs.append("Kritik yavaslik sinyali yok; canli trafik altinda slow_routes.jsonl birikince tekrar calistir.")
    return recs


def write_reports(report: dict) -> tuple[Path, Path]:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = now_stamp()
    json_path = STATE_DIR / f"perf_audit_{stamp}.json"
    txt_path = STATE_DIR / f"perf_audit_{stamp}.txt"
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = [
        "D700 PERF AUDIT",
        f"time={report.get('time')}",
        f"base_url={(report.get('route') or {}).get('base_url')}",
        "",
        "SLOWEST ROUTES",
    ]
    for item in (report.get("route") or {}).get("slowest") or []:
        lines.append(
            f"- {item.get('path')} max={item.get('max_ms')}ms avg={item.get('avg_ms')}ms ok={item.get('ok')}"
        )
    lines.extend(["", "DB"])
    db = report.get("db") or {}
    lines.append(
        f"- ok={db.get('ok')} journal={db.get('journal_mode')} size={db.get('size_mb')}MB wal={db.get('wal_mb')}MB"
    )
    lines.append(f"- missing_indexes={len(db.get('missing_indexes') or [])}")
    lines.extend(["", "NAS"])
    for root in (report.get("nas") or {}).get("roots", []):
        lines.append(
            f"- {root.get('path')} exists={root.get('exists')} exists_ms={root.get('exists_ms')} scan_ms={root.get('scan_first_120_ms')}"
        )
    lines.extend(["", "SERVICES"])
    for svc in (report.get("services") or {}).get("services", []):
        lines.append(f"- {svc.get('label')} ok={svc.get('ok')} ms={svc.get('elapsed_ms')}")
    slow_log = report.get("slow_log") or {}
    lines.extend(["", "SLOW LOG"])
    lines.append(
        f"- sampled={slow_log.get('line_count_sampled', 0)} latest={slow_log.get('latest_ts', '')}"
    )
    for item in slow_log.get("recent_top") or []:
        lines.append(
            f"- recent {item.get('rule')} count={item.get('count')} max={item.get('max_ms')}ms avg={item.get('avg_ms')}ms"
        )
    lines.extend(["", "RECOMMENDATIONS"])
    for rec in report.get("recommendations") or []:
        lines.append(f"- {rec}")
    txt_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, txt_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Safe D700 performance audit")
    parser.add_argument("--base", default="", help="Base URL, default from config port")
    parser.add_argument("--repeat", type=int, default=1, help="Route repeat count")
    parser.add_argument("--timeout", type=float, default=12.0, help="HTTP timeout seconds")
    parser.add_argument("--max-read", type=int, default=2_000_000, help="Max response bytes to sample")
    parser.add_argument("--no-route", action="store_true", help="Skip live route checks")
    args = parser.parse_args(argv)
    cfg = load_env()
    port = env_int("YAZKLINIK_WEB_PORT", 5052, 1, 65535)
    base_url = args.base.strip() or f"http://127.0.0.1:{port}"
    report = {
        "time": now_iso(),
        "root": str(ROOT),
        "route": {"skipped": True, "base_url": base_url},
        "db": db_audit(cfg),
        "nas": nas_audit(cfg),
        "services": service_audit(cfg, timeout=min(max(args.timeout, 1.0), 20.0)),
        "slow_log": slow_log_summary(),
    }
    if not args.no_route:
        report["route"] = route_audit(
            base_url=base_url,
            repeat=max(1, min(args.repeat, 5)),
            timeout=max(1.0, args.timeout),
            max_read=max(1024, args.max_read),
        )
    report["recommendations"] = recommendations(report)
    json_path, txt_path = write_reports(report)
    print(f"D700_PERF_AUDIT_OK report={json_path}")
    print(f"D700_PERF_AUDIT_TXT report={txt_path}")
    for rec in report["recommendations"][:5]:
        print(f"- {rec}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
