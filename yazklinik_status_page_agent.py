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
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional


AGENT_VERSION = "2026.05.17-status"

DEFAULT_DB_PATH = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")
STATUS_PROBE_TIMEOUT = float(os.environ.get("YAZKLINIK_STATUS_PROBE_TIMEOUT", "0.35"))


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

    for name, host, port, critical in SERVICES:
        up, latency = _tcp_probe(host, port)
        rpt.services.append(ServiceStatus(
            name=name, host=host, port=port, critical=critical,
            up=up, latency_ms=latency,
            error="" if up else "port erisilemiyor"))

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
        rpt.uptime_message = f"KRITIK: {len(crit_down)} servis kapali"
    elif noncrit_down:
        rpt.overall = "degraded"
        rpt.uptime_message = f"{len(noncrit_down)} yardimci servis kapali"
    else:
        rpt.overall = "operational"
        rpt.uptime_message = "Tum sistemler calisiyor"
    return rpt


def render_html(rpt: StatusReport) -> str:
    """Public HTML status sayfasi (tek dosya, link yok)."""
    badge = {"operational": ("#16a34a", "[OK] CALISIYOR"),
             "degraded": ("#f59e0b", "[!!] KISMI"),
             "down": ("#dc2626", "[XX] KESINTI")}
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
<meta charset="utf-8"><title>YazKlinik Durum</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{{font-family:-apple-system,Segoe UI,Arial,sans-serif;
background:#f7f9fb;color:#222;max-width:760px;margin:30px auto;padding:0 16px}}
.banner{{background:{color};color:#fff;padding:24px;border-radius:12px;
text-align:center;font-size:24px;margin-bottom:24px}}
table{{width:100%;border-collapse:collapse;background:#fff;border-radius:8px;
overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08)}}
th,td{{padding:12px;text-align:left;border-bottom:1px solid #eee}}
th{{background:#f3f4f6;font-weight:600}}
.foot{{margin-top:24px;color:#666;font-size:13px;text-align:center}}
</style></head><body>
<div class="banner"><b>{txt}</b><br><span style="font-size:14px;opacity:.9">{rpt.uptime_message}</span></div>
<table><thead><tr><th>Servis</th><th>Durum</th><th>Gecikme</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
<p class="foot">Op. Dr. Hakan Yaz Klinik / Son guncelleme: {rpt.generated_at}<br>
Bugun {rpt.db_visits_today} ziyaret kaydedildi.</p>
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
