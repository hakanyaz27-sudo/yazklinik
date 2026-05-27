from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
REPORT_DIR = ROOT / "runtime_state" / "agent_focus"


def _write_text_report(report: dict, path: Path) -> None:
    health = report.get("health") or {}
    registry = health.get("registry_focus") or {}
    lines = [
        "YazKlinik Agent Focus Audit",
        f"Generated: {report.get('generated_at', '')}",
        "",
        f"Modules: {health.get('loaded', 0)}/{health.get('total', 0)} loaded",
        f"Focus OK: {health.get('focus_ok', 0)}/{health.get('total', 0)}",
        f"Registry guardrails: {registry.get('guardrails_ok', 0)}/{registry.get('total', 0)}",
        "",
        "Needs attention:",
    ]
    weak = health.get("focus_needs_attention") or []
    if weak:
        lines.extend([f"- {name}" for name in weak])
    else:
        lines.append("- none")
    reg_weak = registry.get("needs_attention") or []
    lines.append("")
    lines.append("Registry guardrail attention:")
    if reg_weak:
        lines.extend([f"- {name}" for name in reg_weak])
    else:
        lines.append("- none")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    os.chdir(ROOT)
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from yazklinik_agents_routes import get_agent_module_health

    health = get_agent_module_health(force=True)
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    report = {
        "ok": True,
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "health": health,
    }
    json_path = REPORT_DIR / "last_report.json"
    txt_path = REPORT_DIR / "last_report.txt"
    json_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_text_report(report, txt_path)

    failed = int(health.get("failed") or 0)
    focus_weak = health.get("focus_needs_attention") or []
    registry_weak = (health.get("registry_focus") or {}).get("needs_attention") or []
    print(f"AGENT_MODULES_LOADED {health.get('loaded', 0)}/{health.get('total', 0)}")
    print(f"AGENT_FOCUS_OK {health.get('focus_ok', 0)}/{health.get('total', 0)}")
    print(f"AGENT_REGISTRY_GUARDRAILS_OK {(health.get('registry_focus') or {}).get('guardrails_ok', 0)}/{(health.get('registry_focus') or {}).get('total', 0)}")
    print(f"REPORT_JSON {json_path}")
    print(f"REPORT_TXT {txt_path}")
    if failed or focus_weak or registry_weak:
        print("AGENT_FOCUS_AUDIT_WARN")
        return 1
    print("AGENT_FOCUS_AUDIT_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
