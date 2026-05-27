"""Alex communication hardening regression check.

This check is intentionally local and deterministic. It verifies that Alex
does not mix doctor-chat, SIP phone, appointment, emergency, and patient-file
roles before any LLM is allowed to answer.
"""
from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _print(label: str, ok: bool, detail: str = "") -> None:
    prefix = "[OK]" if ok else "[ERR]"
    print(f"{prefix} {label}{(': ' + detail) if detail else ''}")


def _simple_get_json(url: str, timeout: int = 8):
    kwargs = {}
    if url.lower().startswith("https://"):
        kwargs["context"] = ssl._create_unverified_context()
    with urllib.request.urlopen(url, timeout=timeout, **kwargs) as resp:
        body = resp.read(2_000_000).decode("utf-8", errors="replace")
        return resp.status, json.loads(body)


def main() -> int:
    errors = 0
    sys.path.insert(0, str(ROOT))

    print("=== Alex Router Regression ===")
    try:
        from yazklinik_alex_router import (
            public_alex_router_status,
            run_alex_router_regression,
        )
        status = public_alex_router_status()
        regression = run_alex_router_regression()
        _print("router import", True, status.get("version", ""))
        _print(
            "router regression",
            bool(regression.get("ok")),
            f"{regression.get('passed')}/{regression.get('total')}",
        )
        if not regression.get("ok"):
            errors += 1
            for row in regression.get("failed") or []:
                print(json.dumps(row, ensure_ascii=False, indent=2))
    except Exception as exc:
        errors += 1
        _print("router import/regression", False, str(exc))

    print("\n=== SIP Guard Regression ===")
    try:
        from yazklinik_sip_alex_guard import (
            build_sip_safe_response,
            public_guard_status,
        )
        guard_status = public_guard_status()
        _print("sip guard import", True, guard_status.get("version", ""))
        # Booking-enabled contract: guard blocks ONLY safety-critical intents.
        # Appointments and internal-extension callers pass through to booking.
        cases = [
            ("emergency", "Kanamam var suyum geldi", "05551112233", True, "sip_safe_emergency"),
            ("result_safe", "NIPT sonucum cikti mi?", "05551112233", True, "sip_safe_result"),
            ("appointment_pass", "Randevu almak istiyorum", "05551112233", False, "sip_pass_to_booking"),
            ("internal_pass", "Ne yapiyorsun?", "18", False, "sip_pass_to_booking"),
        ]
        for name, text, caller, expected_block, expected_status in cases:
            out = build_sip_safe_response(
                text,
                full_transcript=text,
                caller=caller,
                history=[{"role": "user", "content": text}],
            )
            ok = (bool(out.get("block_webhook")) == expected_block
                  and out.get("status") == expected_status)
            _print(
                f"sip guard {name}",
                bool(ok),
                f"block={out.get('block_webhook')} status={out.get('status')} intent={out.get('intent')}",
            )
            if not ok:
                errors += 1
    except Exception as exc:
        errors += 1
        _print("sip guard regression", False, str(exc))

    print("\n=== Alex Contract Matrix ===")
    try:
        from ALEX_CONTRACT_MATRIX import run_matrix
        matrix = run_matrix()
        _print(
            "contract matrix",
            bool(matrix.get("ok")),
            f"{matrix.get('passed')}/{matrix.get('total')}",
        )
        if not matrix.get("ok"):
            errors += 1
            for row in matrix.get("failed") or []:
                print(
                    f"  drift {row['kind']} {row['name']}: "
                    f"golden={row['golden']} got={row['got']}"
                )
    except Exception as exc:
        errors += 1
        _print("contract matrix", False, str(exc))

    print("\n=== Live SIP Guard ===")
    try:
        status_code, live = _simple_get_json("http://127.0.0.1:9019/status", timeout=8)
        guard = live.get("guard") or {}
        central = guard.get("central_router") or {}
        ok = (
            status_code == 200
            and bool(live.get("registered"))
            and bool(guard.get("safe_mode"))
            and bool(central.get("enabled"))
        )
        _print(
            "live sip central router",
            ok,
            f"registered={live.get('registered')} router={central.get('version')}",
        )
        if not ok:
            errors += 1
        # Informational: TTS/STT health is None until the SIP process is
        # restarted onto the fail-loud build. Not a hard gate yet.
        _print(
            "live tts/stt health (info)",
            True,
            f"tts_healthy={live.get('tts_healthy')} "
            f"fallback_ready={live.get('tts_fallback_ready')} "
            f"stt_healthy={live.get('stt_healthy')}",
        )
    except Exception as exc:
        _print("live sip central router", False, str(exc))
        errors += 1

    print("\n=== Sonuc ===")
    if errors:
        print(f"CODEX_ALEX_HARDENING_CHECK_FAIL ({errors} hata)")
        return 2
    print("CODEX_ALEX_HARDENING_CHECK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
