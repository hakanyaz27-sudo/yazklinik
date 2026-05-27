from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "runtime_state" / "system_capability"


def _read_config() -> dict:
    out = {}
    path = ROOT / "config.env"
    if not path.exists():
        return out
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip()
    return out


def _server_base(config: dict) -> str:
    port = config.get("YAZKLINIK_WEB_PORT") or os.environ.get("YAZKLINIK_WEB_PORT") or "5052"
    return f"http://127.0.0.1:{port}"


def _timed_fetch(opener, url: str, timeout: int = 12) -> dict:
    start = time.perf_counter()
    try:
        with opener.open(url, timeout=timeout) as resp:
            body = resp.read(300000)
            elapsed = round((time.perf_counter() - start) * 1000, 1)
            ctype = resp.headers.get("Content-Type", "")
            parsed = None
            if "json" in ctype.lower() or body[:1] in (b"{", b"["):
                try:
                    parsed = json.loads(body.decode("utf-8", "replace"))
                except Exception:
                    parsed = None
            return {
                "ok": 200 <= int(resp.status) < 400,
                "status": int(resp.status),
                "ms": elapsed,
                "json": parsed,
            }
    except Exception as exc:
        elapsed = round((time.perf_counter() - start) * 1000, 1)
        return {"ok": False, "status": 0, "ms": elapsed, "error": f"{type(exc).__name__}: {exc}"}


def _login_opener(base: str) -> tuple[object, dict]:
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    data = urllib.parse.urlencode({"username": "doktor", "password": "1133"}).encode("utf-8")
    login = _timed_fetch(opener, base + "/giris", timeout=15)
    try:
        opener.open(urllib.request.Request(base + "/giris", data=data, method="POST"), timeout=15).read()
        login["logged_in"] = True
    except Exception as exc:
        login["logged_in"] = False
        login["error"] = f"{type(exc).__name__}: {exc}"
    return opener, login


def _offline_checks() -> dict:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from yazklinik_agents_routes import get_agent_module_health

    health = get_agent_module_health(force=True)
    helper = {}
    try:
        import yazklinik_web as web
        helper = web._integration_workbench_payload()
    except Exception as exc:
        helper = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    return {
        "agent_health": health,
        "integration_helper": helper,
    }


def _live_checks(base: str, config: dict) -> dict:
    opener, login = _login_opener(base)
    routes = [
        "/api/agents?force=1",
        "/api/hizmet-ajanlari?force=1",
        "/api/entegrasyonlar/yardimci",
        "/api/pdf-destek-durumu",
        "/api/sistem-durumu",
    ]
    pg_enabled = (config.get("YAZKLINIK_ENABLE_POSTGRES") == "1") or (
        (config.get("YAZKLINIK_DB_DIALECT") or "").lower() in {"postgres", "postgresql"}
    )
    if pg_enabled:
        routes.append("/api/db/postgres/health")
    results = {path: _timed_fetch(opener, base + path) for path in routes}
    return {"base": base, "login": login, "routes": results}


def _summarize(report: dict) -> dict:
    offline = report.get("offline") or {}
    agent = offline.get("agent_health") or {}
    helper = offline.get("integration_helper") or {}
    live = report.get("live") or {}
    routes = live.get("routes") or {}
    slow_routes = [
        {"route": route, "ms": data.get("ms")}
        for route, data in routes.items()
        if float(data.get("ms") or 0) >= 1500
    ]
    live_agents = ((routes.get("/api/agents?force=1") or {}).get("json") or {}).get("focus_health") or {}
    live_helper = ((routes.get("/api/entegrasyonlar/yardimci") or {}).get("json") or {})
    warnings = []
    if agent.get("failed"):
        warnings.append("agent_import_failed")
    if agent.get("focus_needs_attention"):
        warnings.append("agent_focus_needs_attention")
    if not (helper.get("summary") or {}).get("support_ready"):
        warnings.append("offline_support_not_ready")
    if not live_agents.get("total"):
        warnings.append("live_agent_focus_missing_restart_required")
    if live_helper and not (live_helper.get("summary") or {}).get("support_ready"):
        warnings.append("live_support_not_ready_restart_required")
    for route, data in routes.items():
        if not data.get("ok"):
            warnings.append(f"route_failed:{route}")
    if slow_routes:
        warnings.append("slow_routes_detected")
    return {
        "ok": not warnings,
        "warnings": warnings,
        "agent_modules": f"{agent.get('loaded', 0)}/{agent.get('total', 0)}",
        "agent_focus": f"{agent.get('focus_ok', 0)}/{agent.get('total', 0)}",
        "registry_guardrails": f"{(agent.get('registry_focus') or {}).get('guardrails_ok', 0)}/{(agent.get('registry_focus') or {}).get('total', 0)}",
        "offline_support_ready": bool((helper.get("summary") or {}).get("support_ready")),
        "live_agent_focus": f"{live_agents.get('focus_ok')}/{live_agents.get('total')}" if live_agents else "missing",
        "live_support_ready": bool((live_helper.get("summary") or {}).get("support_ready")) if live_helper else None,
        "slow_routes": slow_routes,
    }


def _write_text(report: dict, path: Path) -> None:
    s = report.get("summary") or {}
    lines = [
        "YazKlinik System Capability Audit",
        f"Generated: {report.get('generated_at', '')}",
        f"Base: {(report.get('live') or {}).get('base', '')}",
        "",
        f"Agent modules: {s.get('agent_modules')}",
        f"Agent focus: {s.get('agent_focus')}",
        f"Registry guardrails: {s.get('registry_guardrails')}",
        f"Offline support ready: {s.get('offline_support_ready')}",
        f"Live agent focus: {s.get('live_agent_focus')}",
        f"Live support ready: {s.get('live_support_ready')}",
        "",
        "Warnings:",
    ]
    warnings = s.get("warnings") or []
    lines.extend([f"- {w}" for w in warnings] if warnings else ["- none"])
    lines.append("")
    lines.append("Live route timings:")
    for route, data in ((report.get("live") or {}).get("routes") or {}).items():
        status = data.get("status")
        ms = data.get("ms")
        ok = "OK" if data.get("ok") else "FAIL"
        lines.append(f"- {route}: {ok} HTTP {status} {ms}ms")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    os.chdir(ROOT)
    config = _read_config()
    base = _server_base(config)
    report = {
        "ok": True,
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "offline": _offline_checks(),
        "live": _live_checks(base, config),
    }
    report["summary"] = _summarize(report)
    report["ok"] = bool(report["summary"].get("ok"))

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORT_DIR / "last_report.json"
    txt_path = REPORT_DIR / "last_report.txt"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_text(report, txt_path)

    s = report["summary"]
    print(f"AGENT_MODULES {s['agent_modules']}")
    print(f"AGENT_FOCUS {s['agent_focus']}")
    print(f"REGISTRY_GUARDRAILS {s['registry_guardrails']}")
    print(f"OFFLINE_SUPPORT_READY {s['offline_support_ready']}")
    print(f"LIVE_AGENT_FOCUS {s['live_agent_focus']}")
    print(f"LIVE_SUPPORT_READY {s['live_support_ready']}")
    print(f"REPORT_JSON {json_path}")
    print(f"REPORT_TXT {txt_path}")
    warnings = s.get("warnings") or []
    if warnings:
        print("SYSTEM_CAPABILITY_AUDIT_WARN " + ",".join(warnings))
        return 1
    print("SYSTEM_CAPABILITY_AUDIT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
