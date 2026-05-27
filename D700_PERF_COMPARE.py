#!/usr/bin/env python
"""Compare two D700_PERF_AUDIT JSON reports."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "runtime_state" / "perf"


def load_report(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def route_avgs(report: dict[str, Any]) -> dict[str, float]:
    buckets: dict[str, list[int]] = defaultdict(list)
    for item in (report.get("route") or {}).get("routes") or []:
        label = str(item.get("label") or item.get("path") or "?")
        if item.get("ok"):
            buckets[label].append(int(item.get("elapsed_ms") or 0))
    return {
        key: round(sum(vals) / len(vals), 1)
        for key, vals in buckets.items()
        if vals
    }


def db_query_avgs(report: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for item in (report.get("db") or {}).get("queries") or []:
        if item.get("ok"):
            out[str(item.get("label") or "?")] = float(item.get("elapsed_ms") or 0)
    return out


def percent_change(old: float, new: float) -> str:
    if old <= 0:
        return "n/a"
    change = ((new - old) / old) * 100.0
    sign = "+" if change >= 0 else ""
    return f"{sign}{change:.1f}%"


def compare_group(name: str, left: dict[str, float], right: dict[str, float]) -> list[str]:
    keys = sorted(set(left) & set(right), key=lambda k: max(left[k], right[k]), reverse=True)
    lines = [name]
    if not keys:
        lines.append("- ortak veri yok")
        return lines
    for key in keys[:20]:
        a = left[key]
        b = right[key]
        faster = "HIZLI" if b < a else "YAVAS"
        lines.append(
            f"- {key}: once={a:.1f}ms sonra={b:.1f}ms degisim={percent_change(a, b)} {faster}"
        )
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description="D700 perf report compare")
    parser.add_argument("before", type=Path, help="Windows/before perf_audit JSON")
    parser.add_argument("after", type=Path, help="Linux/after perf_audit JSON")
    args = parser.parse_args()

    before = load_report(args.before)
    after = load_report(args.after)
    lines = [
        "D700 PERF COMPARE",
        f"before={args.before}",
        f"after={args.after}",
        f"before_time={before.get('time')}",
        f"after_time={after.get('time')}",
        "",
    ]
    lines.extend(compare_group("ROUTES", route_avgs(before), route_avgs(after)))
    lines.append("")
    lines.extend(compare_group("DB QUERIES", db_query_avgs(before), db_query_avgs(after)))
    lines.append("")
    lines.append("NAS")
    b_roots = (before.get("nas") or {}).get("roots") or []
    a_roots = (after.get("nas") or {}).get("roots") or []
    for b, a in zip(b_roots, a_roots):
        b_ms = float(b.get("scan_first_120_ms") or 0)
        a_ms = float(a.get("scan_first_120_ms") or 0)
        lines.append(
            f"- {b.get('path')} -> {a.get('path')}: once={b_ms:.1f}ms sonra={a_ms:.1f}ms degisim={percent_change(b_ms, a_ms)}"
        )

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / ("perf_compare_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".txt")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nD700_PERF_COMPARE_OK report={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
