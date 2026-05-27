"""D700 infrastructure guard.

This module keeps runtime checks outside the large Flask file. It is designed
to be safe for UI calls: fast by default, deeper checks only when requested.
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import ssl
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "runtime_state" / "infra_guard"
REPORT_JSON = RUNTIME_DIR / "last_report.json"
REPORT_TXT = RUNTIME_DIR / "last_report.txt"


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _hidden_subprocess_kwargs() -> dict:
    if os.name != "nt":
        return {}
    kwargs = {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0
        kwargs["startupinfo"] = startupinfo
    except Exception:
        pass
    return kwargs


def _read_config() -> dict[str, str]:
    out: dict[str, str] = {}
    path = ROOT / "config.env"
    if not path.exists():
        return out
    try:
        for raw in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    except Exception:
        pass
    return out


def _mask_secret(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if "://" in text and "@" in text:
        try:
            from urllib.parse import urlsplit, urlunsplit

            parsed = urlsplit(text)
            host = parsed.hostname or ""
            if parsed.port:
                host = f"{host}:{parsed.port}"
            user = parsed.username or ""
            return urlunsplit((
                parsed.scheme,
                f"{user}:***@{host}" if user else host,
                parsed.path,
                parsed.query,
                parsed.fragment,
            ))
        except Exception:
            return "***"
    if len(text) > 12:
        return text[:4] + "..." + text[-4:]
    return "***"


def _http_probe(url: str, timeout: float = 2.5) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        kwargs: dict[str, Any] = {}
        if url.lower().startswith("https://"):
            kwargs["context"] = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers={"User-Agent": "D700-InfraGuard/1.0"})
        with urllib.request.urlopen(req, timeout=timeout, **kwargs) as resp:
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return {
                "ok": 200 <= int(resp.status) < 400,
                "status": int(resp.status),
                "elapsed_ms": elapsed_ms,
            }
    except Exception as ex:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "status": 0,
            "elapsed_ms": elapsed_ms,
            "error": type(ex).__name__,
        }


def _tcp_probe(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


def _port_owner_pid(port: int) -> int:
    if os.name != "nt":
        return 0
    try:
        cmd = (
            "Get-NetTCPConnection -LocalPort "
            f"{int(port)} -State Listen -ErrorAction SilentlyContinue | "
            "Select-Object -First 1 -ExpandProperty OwningProcess"
        )
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", cmd],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=4,
            **_hidden_subprocess_kwargs(),
        ).strip()
        return int(out.splitlines()[0]) if out else 0
    except Exception:
        return 0


def _process_info(pid: int) -> dict[str, Any]:
    if os.name != "nt" or pid <= 0:
        return {"pid": int(pid or 0)}
    try:
        ps = (
            "$p=Get-CimInstance Win32_Process -Filter "
            f"'ProcessId={int(pid)}' -ErrorAction SilentlyContinue; "
            "if($p){[pscustomobject]@{"
            "ProcessId=$p.ProcessId;Name=$p.Name;CommandLine=$p.CommandLine;"
            "CreationDate=$p.CreationDate"
            "} | ConvertTo-Json -Compress}"
        )
        raw = subprocess.check_output(
            ["powershell", "-NoProfile", "-Command", ps],
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
            **_hidden_subprocess_kwargs(),
        ).strip()
        data = json.loads(raw) if raw else {}
        cmd = str(data.get("CommandLine") or "")
        return {
            "pid": int(data.get("ProcessId") or pid),
            "name": str(data.get("Name") or ""),
            "command_line_available": bool(cmd),
            "command_line": cmd[:420],
            "creation_date": str(data.get("CreationDate") or ""),
        }
    except Exception:
        return {
            "pid": int(pid),
            "command_line_available": False,
            "command_line": "",
            "creation_date": "",
        }


def _ps_date_to_epoch(value: str) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    if text.startswith("/Date("):
        try:
            number = text.split("(", 1)[1].split(")", 1)[0]
            # PowerShell ConvertTo-Json may serialize CIM datetime values as
            # /Date(milliseconds)/. It is already UTC-ish epoch milliseconds.
            return float(number) / 1000.0
        except Exception:
            return 0.0
    # PowerShell CIM dates usually look like 20260519161840.123456+180.
    try:
        base = text.split(".", 1)[0]
        dt = datetime.strptime(base[:14], "%Y%m%d%H%M%S")
        return dt.timestamp()
    except Exception:
        return 0.0


def _item(name: str, ok: bool, detail: str = "", severity: str = "info",
          action: str = "", data: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "name": name,
        "ok": bool(ok),
        "severity": "ok" if ok else severity,
        "detail": str(detail or ""),
        "action": str(action or ""),
        "data": data or {},
    }


def _db_guard_summary() -> dict[str, Any]:
    path = ROOT / "runtime_state" / "db_guard" / "last_report.json"
    txt_path = ROOT / "runtime_state" / "db_guard" / "last_report.txt"
    out: dict[str, Any] = {"exists": path.exists() or txt_path.exists()}
    try:
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            out.update(data if isinstance(data, dict) else {"raw": data})
        if txt_path.exists():
            out["text_tail"] = "\n".join(
                txt_path.read_text(encoding="utf-8", errors="replace").splitlines()[-12:]
            )
    except Exception as ex:
        out["error"] = str(ex)
    return out


def _service_definitions(cfg: dict[str, str]) -> list[dict[str, Any]]:
    web_port = int(cfg.get("YAZKLINIK_WEB_PORT") or os.environ.get("YAZKLINIK_WEB_PORT") or 5052)
    https_port = int(cfg.get("YAZKLINIK_HTTPS_PORT") or os.environ.get("YAZKLINIK_HTTPS_PORT") or 5443)
    return [
        {"name": "Web HTTPS", "url": f"https://127.0.0.1:{https_port}/giris", "port": https_port, "critical": True},
        {"name": "Web HTTP fallback", "url": f"http://127.0.0.1:{web_port}/api/terminal/ping", "port": web_port, "critical": False},
        {"name": "Whisper STT", "url": "http://127.0.0.1:9000/health", "port": 9000, "critical": False},
        {"name": "Piper TTS", "url": "http://127.0.0.1:9001/health", "port": 9001, "critical": False},
        {"name": "XTTS TTS", "url": "http://127.0.0.1:9002/health", "port": 9002, "critical": False},
        {"name": "SIP Alex", "url": "http://127.0.0.1:9019/status", "port": 9019, "critical": False},
        {"name": "ComfyUI", "url": "http://127.0.0.1:8188/system_stats", "port": 8188, "critical": False},
        {"name": "Ollama", "url": "http://127.0.0.1:11434/api/tags", "port": 11434, "critical": False},
        {"name": "Orthanc", "url": "http://127.0.0.1:8042/system", "port": 8042, "critical": False},
    ]


def build_report(deep: bool = False, write: bool = True) -> dict[str, Any]:
    cfg = _read_config()
    items: list[dict[str, Any]] = []

    db_path = Path(cfg.get("YAZKLINIK_DB_PATH") or os.environ.get("YAZKLINIK_DB_PATH") or ROOT / "local_db" / "yazklinik_v68.sqlite3")
    db_ok = db_path.exists() and db_path.is_file()
    items.append(_item(
        "SQLite ana veritabani",
        db_ok,
        f"{db_path} ({round(db_path.stat().st_size / 1048576, 2)} MB)" if db_ok else str(db_path),
        "critical",
        "config.env icindeki YAZKLINIK_DB_PATH yolunu duzeltin.",
    ))

    nas_root = Path(cfg.get("YAZKLINIK_NAS_ROOT") or os.environ.get("YAZKLINIK_NAS_ROOT") or r"\\ASUSTOR\Voluson\Hastalar")
    nas_ok = nas_root.exists()
    items.append(_item(
        "NAS hasta klasoru",
        nas_ok,
        str(nas_root),
        "warning",
        "NAS baglantisini acin veya /sistem-ayarlari icinden yolu duzeltin.",
    ))

    db_guard = _db_guard_summary()
    guard_text = str(db_guard.get("text_tail") or "")
    guard_ok = bool(db_guard.get("ok")) or "DATABASE_GUARD_OK" in guard_text
    items.append(_item(
        "Database Guard",
        guard_ok,
        "son rapor OK" if guard_ok else "son DB guard raporu net OK degil",
        "critical",
        "YAZKLINIK_DB_GUARD.py --repair --keep-backups 21 calistirin.",
        {"report_exists": bool(db_guard.get("exists"))},
    ))

    web_py = ROOT / "yazklinik_web.py"
    web_mtime = web_py.stat().st_mtime if web_py.exists() else 0.0
    seen_web_pid: set[int] = set()
    services = _service_definitions(cfg)
    for svc in services:
        port = int(svc["port"])
        probe = _http_probe(str(svc["url"]), timeout=2.5 if not deep else 6.0)
        if not probe.get("ok") and _tcp_probe("127.0.0.1", port):
            probe["tcp_open"] = True
        pid = _port_owner_pid(port)
        proc = _process_info(pid) if pid else {"pid": 0}
        detail = f"{svc['url']} status={probe.get('status', 0)} {probe.get('elapsed_ms', 0)}ms"
        if pid:
            detail += f" pid={pid}"
        ok = bool(probe.get("ok") or probe.get("tcp_open"))
        action = "D500_BASLAT.bat ile servisleri yeniden baslatin."
        severity = "critical" if svc.get("critical") else "warning"
        items.append(_item(str(svc["name"]), ok, detail, severity, action, {
            "probe": probe,
            "process": proc,
            "critical": bool(svc.get("critical")),
        }))
        if str(svc["name"]).startswith("Web") and pid:
            seen_web_pid.add(pid)

    for pid in sorted(seen_web_pid):
        proc = _process_info(pid)
        start_epoch = _ps_date_to_epoch(str(proc.get("creation_date") or ""))
        cmd = str(proc.get("command_line") or "").lower()
        managed = "d700_service_runner.py" in cmd
        cmd_available = bool(proc.get("command_line_available"))
        older_than_code = bool(start_epoch and web_mtime and start_epoch < web_mtime - 3)
        ok = bool(not older_than_code and (managed or not cmd_available))
        if older_than_code:
            detail = "canli web sureci kod dosyasindan eski; yeni yamalar icin restart gerekli"
        elif not cmd_available:
            detail = "canli web koddan yeni; komut satiri Windows tarafindan gizli"
        elif not managed:
            detail = "canli web D500_SERVICE_RUNNER disinda baslamis"
        else:
            detail = "canli web runner uzerinden guncel gorunuyor"
        items.append(_item(
            "Canli web surec yonetimi",
            ok,
            f"PID {pid}: {detail}",
            "critical",
            "D500_ADMIN_WEB_RESTART.bat dosyasini yonetici olarak calistirin.",
            {
                "pid": pid,
                "managed": managed,
                "command_line_available": cmd_available,
                "older_than_code": older_than_code,
                "web_py_modified": datetime.fromtimestamp(web_mtime).isoformat(timespec="seconds") if web_mtime else "",
                "process": proc,
            },
        ))

    critical_bad = [x for x in items if not x.get("ok") and x.get("severity") == "critical"]
    warning_bad = [x for x in items if not x.get("ok") and x.get("severity") != "critical"]
    ok_count = len([x for x in items if x.get("ok")])
    score = int(round((ok_count / max(1, len(items))) * 100))
    if critical_bad:
        score = min(score, 69)
    report = {
        "ok": not critical_bad,
        "score": score,
        "generated_at": _now(),
        "root": str(ROOT),
        "summary": {
            "total": len(items),
            "ok": ok_count,
            "critical_bad": len(critical_bad),
            "warnings": len(warning_bad),
        },
        "items": items,
        "safe_restart": str(ROOT / "D500_ADMIN_WEB_RESTART.bat"),
        "masked_database_url": _mask_secret(cfg.get("YAZKLINIK_DATABASE_URL", "")),
    }
    if write:
        write_report(report)
    return report


def write_report(report: dict[str, Any]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        f"D500_INFRA_GUARD {'OK' if report.get('ok') else 'WARN'}",
        f"generated_at={report.get('generated_at')}",
        f"score={report.get('score')}",
    ]
    for item in report.get("items", []):
        mark = "OK" if item.get("ok") else item.get("severity", "warn").upper()
        lines.append(f"[{mark}] {item.get('name')}: {item.get('detail')}")
        if not item.get("ok") and item.get("action"):
            lines.append(f"  action: {item.get('action')}")
    REPORT_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="YazKlinik D700 infrastructure guard")
    parser.add_argument("--deep", action="store_true", help="Use longer service timeouts")
    parser.add_argument("--json", action="store_true", help="Print JSON report")
    args = parser.parse_args(argv)
    report = build_report(deep=bool(args.deep), write=True)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(REPORT_TXT.read_text(encoding="utf-8", errors="replace"))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))


