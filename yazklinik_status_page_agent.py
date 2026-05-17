"""Public Status Page Agent - Klinik servisleri canli mi?

Hastaya / personele gosterilen umumi durum sayfasi:
    /status -> http endpoint
    /api/status -> JSON

Kontrol noktalari:
    - Flask web (kendisi)
    - SQLite DB (visit say)
    - Ollama (port 11434)
    - PostgreSQL (port 5432)
    - Redis (port 6379)
    - MeiliSearch (port 7700)
    - n8n (port 5678)
    - Uptime Kuma (port 3001)
"""
from __future__ import annotations

import json
import os
import socket
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-status"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")
STATUS_PROBE_TIMEOUT = float(os.environ.get("YAZKLINIK_STATUS_PROBE_TIMEOUT", "0.35"))
STATUS_PROBE_WORKERS = max(1, int(os.environ.get("YAZKLINIK_STATUS_PROBE_WORKERS", "10")))


SERVICES = [
    ("Web (Flask)", "127.0.0.1", 5443, True),
    ("Ollama LLM", "127.0.0.1", 11434, False),
    ("Whisper STT", "127.0.0.1", 9000, False),
    ("PostgreSQL", "127.0.0.1", 5432, False),
    ("Redis Cache", "127.0.0.1", 6379, False),
    ("MeiliSearch", "127.0.0.1", 7700, False),
    ("n8n", "127.0.0.1", 5678, False),
    ("Uptime Kuma", "127.0.0.1", 3001, False),
    ("Open WebUI", "127.0.0.1", 3010, False),
    ("Vaultwarden", "127.0.0.1", 8222, False),
]


@dataclass
class ServiceStatus:
    name: str
    host: str
    port: int
    critical: bool
    up: bool = False
    latency_ms: int = 0
    error: str = ""


@dataclass
class StatusReport:
    generated_at: str
    overall: str = "operational"   # operational | degraded | down
    services: List[ServiceStatus] = field(default_factory=list)
    db_visits_today: int = 0
    uptime_message: str = ""
    agent_version: str = AGENT_VERSION


def _tcp_probe(host: str, port: int, timeout: float = STATUS_PROBE_TIMEOUT) -> tuple[bool, int]:
    t0 = time.time()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, int((time.time() - t0) * 1000)
    except Exception:
        return False, 0


def build_report(db_path: Optional[str] = None) -> StatusReport:
    db_path = db_path or DEFAULT_DB_PATH
    rpt = StatusReport(generated_at=datetime.now().isoformat(timespec="seconds"))

    def probe_service(service: tuple[str, str, int, bool]) -> ServiceStatus:
        name, host, port, critical = service
        up, latency = _tcp_probe(host, port)
        return ServiceStatus(
            name=name, host=host, port=port, critical=critical,
            up=up, latency_ms=latency,
            error="" if up else "port erisilemiyor")

    worker_count = min(STATUS_PROBE_WORKERS, max(1, len(SERVICES)))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        rpt.services.extend(executor.map(probe_service, SERVICES))

    # DB visit count
    if os.path.exists(db_path):
        try:
            con = sqlite3.connect(db_path)
            r = con.execute(
                "SELECT COUNT(*) FROM visits WHERE date(visit_date) = date('now')"
            ).fetchone()
            rpt.db_visits_today = int(r[0]) if r else 0
            con.close()
        except Exception:
            pass

    # Overall
    crit_down = [s for s in rpt.services if s.critical and not s.up]
    noncrit_down = [s for s in rpt.services if not s.critical and not s.up]
    if crit_down:
        rpt.overall = "down"
        rpt.uptime_message = f"KRİTİK: {len(crit_down)} servis kapalı"
    elif noncrit_down:
        rpt.overall = "degraded"
        rpt.uptime_message = f"{len(noncrit_down)} yardımcı servis kapalı"
    else:
        rpt.overall = "operational"
        rpt.uptime_message = "Tüm sistemler çalışıyor"
    return rpt


def render_html(rpt: StatusReport) -> str:
    """Public HTML status sayfasi (tek dosya, link yok)."""
    badge = {"operational": ("#16a34a", "[OK] ÇALIŞIYOR"),
             "degraded": ("#f59e0b", "[!!] KISMI"),
             "down": ("#dc2626", "[XX] KESİNTİ")}
    color, txt = badge.get(rpt.overall, ("#666", "?"))
    rows = []
    for s in rpt.services:
        sym = "[OK]" if s.up else "[XX]"
        c = "#16a34a" if s.up else "#dc2626"
        lat = f"{s.latency_ms}ms" if s.up else "-"
        rows.append(f"""<tr><td>{s.name}</td>
            <td><span style="color:{c}">{sym}</span></td>
            <td>{lat}</td></tr>""")
    return f"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8">
<title>YazKlinik Durum</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="{color}">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Durum">
<meta name="format-detection" content="telephone=no">
<link rel="apple-touch-icon" sizes="180x180" href="/static/icons/apple-touch-icon-180.png">
<link rel="icon" type="image/png" sizes="32x32" href="/static/icons/favicon-32.png">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="stylesheet" href="/static/yk-ios-mobile.css?v=d300-ios-2026-05-17">
<style>
:root{{--safe-top:env(safe-area-inset-top,0px);--safe-bottom:env(safe-area-inset-bottom,0px)}}
*{{box-sizing:border-box;margin:0;padding:0}}
html,body{{-webkit-text-size-adjust:100%;-webkit-tap-highlight-color:transparent}}
body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Helvetica Neue",Arial,sans-serif;
background:#f7f9fb;color:#222;max-width:760px;margin:0 auto;
padding:calc(20px + var(--safe-top)) 16px calc(20px + var(--safe-bottom));
min-height:100vh;min-height:100dvh}}
.banner{{background:{color};color:#fff;padding:20px;border-radius:14px;
text-align:center;font-size:20px;font-weight:600;margin-bottom:20px;
box-shadow:0 4px 16px rgba(0,0,0,.08)}}
.banner small{{font-size:13px;font-weight:400;opacity:.92;display:block;margin-top:6px}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:10px;
overflow:hidden;box-shadow:0 1px 4px rgba(0,0,0,.06)}}
th,td{{padding:14px 12px;text-align:left;border-bottom:1px solid #eef3f8;font-size:15px}}
th{{background:#eff5fb;font-weight:600;color:#0d4f8b;font-size:13px;text-transform:uppercase;letter-spacing:.3px}}
td:nth-child(2){{text-align:center;font-weight:600}}
td:nth-child(3){{text-align:right;color:#5e7185;font-variant-numeric:tabular-nums}}
tr:last-child td{{border-bottom:none}}
.foot{{margin-top:20px;color:#5e7185;font-size:13px;text-align:center;line-height:1.6}}
@media(max-width:480px){{
  body{{padding-left:12px;padding-right:12px}}
  .banner{{font-size:18px;padding:16px}}
  th,td{{padding:11px 8px;font-size:14px}}
  th{{font-size:11px}}
}}
@media(display-mode:standalone){{
  body{{padding-top:calc(40px + var(--safe-top))}}
}}
</style></head><body>
<div class="banner"><b>{txt}</b><small>{rpt.uptime_message}</small></div>
<table><thead><tr><th>Servis</th><th>Durum</th><th>Gecikme</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<p class="foot"><b>Op. Dr. Hakan Yaz Kliniği</b><br>
Son güncelleme: {rpt.generated_at}<br>
Bugün {rpt.db_visits_today} ziyaret kaydedildi.</p>
</body></html>"""


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "services_monitored": len(SERVICES)}


if __name__ == "__main__":
    r = build_report()
    print(f"Overall: {r.overall} - {r.uptime_message}")
    for s in r.services:
        sym = "[OK]" if s.up else "[XX]"
        print(f"  {sym} {s.name} ({s.host}:{s.port}) {s.latency_ms}ms")
