"""Alex behaviour contract matrix.

Deterministic characterization tests for the Alex decision layer. They pin the
observable behaviour of the central router (yazklinik_alex_router) and the SIP
safety guard (yazklinik_sip_alex_guard) across the call situations that matter
on a live clinic phone line: emergency, human handoff, appointment (with and
without phone/time), result/prescription, clinic info, internal doctor noise,
and unclear speech.

This file is the safety net for refactors. If a change alters any line below,
that is a behaviour change and must be intentional. Run before and after every
edit to the router or guard.

    python ALEX_CONTRACT_MATRIX.py            # assert against golden table
    python ALEX_CONTRACT_MATRIX.py --snapshot # print current behaviour
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Pin the environment so the contract is reproducible regardless of shell state.
os.environ.setdefault("YAZKLINIK_SIP_ALEX_SAFE_MODE", "1")
os.environ.setdefault("YAZKLINIK_SIP_ALEX_HANGUP_AFTER_SAFE_REPLY", "1")
os.environ.setdefault("YAZKLINIK_ALEX_CENTRAL_ROUTER", "1")

from yazklinik_alex_router import classify_alex_request  # noqa: E402
from yazklinik_sip_alex_guard import build_sip_safe_response  # noqa: E402


def _u(*texts: str) -> list:
    return [{"role": "user", "content": t} for t in texts]


# (name, text, caller, history, dtmf, triage)
GUARD_CASES = [
    ("emergency_patient", "Kanamam var suyum geldi", "05551112233", None, "", None),
    ("emergency_triage", "Kendimi iyi hissetmiyorum", "05551112233", None, "", {"intent": "urgent"}),
    ("internal_noise", "Ne yapiyorsun", "18", None, "", None),
    ("internal_appointment", "Randevu almak istiyorum", "18", None, "", None),
    ("human_handoff", "Sekreterle gorusmek istiyorum", "05551112233", None, "", None),
    ("human_callback", "Beni geri arayin lutfen", "05551112233", None, "", None),
    ("appointment_need_phone", "Randevu almak istiyorum", "", None, "", None),
    ("appointment_need_time", "Randevu almak istiyorum", "05551112233", None, "", None),
    ("appointment_full", "Yarin saat 14 te randevu istiyorum", "05551112233", None, "", None),
    ("appointment_dtmf_phone", "Randevu istiyorum", "", None, "05551112233", None),
    ("result_callback", "NIPT sonucum cikti mi", "05551112233", None, "", None),
    ("result_need_identity", "Tahlil sonucumu ogrenmek istiyorum", "", None, "", None),
    ("prescription_callback", "Recetemi yazdirabilir misiniz", "05551112233", None, "", None),
    ("clinic_info", "Adresiniz nerede ucret ne kadar", "05551112233", None, "", None),
    ("unclear_short", "ee", "05551112233", None, "", None),
    ("unclear_multiturn", "belki", "05551112233", _u("ne", "hmm"), "", None),
    ("callback_default", "merhaba size bir sey danismak istiyordum acaba", "05551112233", None, "", None),
]

# (name, text, caller, channel)
ROUTER_CASES = [
    ("doctor_meta_quality", "Alex sacma cevap veriyor, optimize et", "doktor", "web_test"),
    ("doctor_clinical", "Hiperemezis hastasinda ilk yaklasim nasil olmali", "doktor", "akilli-dialog"),
    ("sip_internal_noise", "Ne yapiyorsun", "18", "sip_alex"),
    ("phone_appointment", "Randevu almak istiyorum", "05551112233", "sip_alex"),
    ("phone_emergency", "Kanamam var, suyum geldi", "05551112233", "sip_alex"),
    ("phone_file_action", "Bunu hasta dosyasina kaydet", "05551112233", "sip_alex"),
    ("doctor_navigation", "Hastalar sayfasini ac", "doktor", "akilli-dialog"),
    ("phone_human_handoff", "Sekreterle gorusmek istiyorum", "05551112233", "sip_alex"),
    ("phone_clinic_info", "Adresiniz nerede acik misiniz", "05551112233", "sip_alex"),
]


def _guard_row(case) -> tuple:
    name, text, caller, history, dtmf, triage = case
    out = build_sip_safe_response(
        text, full_transcript=text, caller=caller, triage=triage,
        history=history, dtmf_digits=dtmf)
    return (
        name,
        bool(out.get("block_webhook")),
        str(out.get("status")),
        str(out.get("intent")),
        bool(out.get("terminal")),
        bool(out.get("should_hangup")),
    )


def _router_row(case) -> tuple:
    name, text, caller, channel = case
    out = classify_alex_request(
        text, caller=caller, channel=channel, source=channel)
    return (
        name,
        str(out.get("speaker_role")),
        str(out.get("intent")),
        str(out.get("action_policy")),
        bool(out.get("allow_autonomous_action")),
    )


def snapshot() -> None:
    print("# GUARD_GOLDEN")
    for case in GUARD_CASES:
        print(repr(_guard_row(case)) + ",")
    print("# ROUTER_GOLDEN")
    for case in ROUTER_CASES:
        print(repr(_router_row(case)) + ",")


# Frozen golden table (2026-05-21, booking-enabled design).
# The guard is a thin SAFETY FILTER: it blocks the line only for emergency,
# medical records, human handoff, and clinic info. Appointments, names, phone
# numbers, slot replies, general speech, and internal-extension callers PASS
# THROUGH (block_webhook=False) to the web booking flow. These rows are the
# live phone contract and must never change silently.
GUARD_GOLDEN: list = [
    ('emergency_patient', True, 'sip_safe_emergency', 'emergency', True, True),
    ('emergency_triage', True, 'sip_safe_emergency', 'emergency', True, True),
    ('internal_noise', False, 'sip_pass_to_booking', 'doctor_general', False, False),
    ('internal_appointment', False, 'sip_pass_to_booking', 'appointment_request', False, False),
    ('human_handoff', True, 'sip_safe_handoff', 'human_handoff', True, True),
    ('human_callback', True, 'sip_safe_handoff', 'human_handoff', True, True),
    ('appointment_need_phone', False, 'sip_pass_to_booking', 'appointment_request', False, False),
    ('appointment_need_time', False, 'sip_pass_to_booking', 'appointment_request', False, False),
    ('appointment_full', False, 'sip_pass_to_booking', 'appointment_request', False, False),
    ('appointment_dtmf_phone', False, 'sip_pass_to_booking', 'appointment_request', False, False),
    ('result_callback', True, 'sip_safe_result', 'result_request', True, True),
    ('result_need_identity', True, 'sip_safe_result', 'result_request', True, True),
    ('prescription_callback', True, 'sip_safe_result', 'result_request', True, True),
    ('clinic_info', True, 'sip_safe_clinic_info', 'clinic_info', True, True),
    ('unclear_short', False, 'sip_pass_to_booking', 'general_or_unclear', False, False),
    ('unclear_multiturn', False, 'sip_pass_to_booking', 'general_or_unclear', False, False),
    ('callback_default', False, 'sip_pass_to_booking', 'general_or_unclear', False, False),
]
ROUTER_GOLDEN: list = [
    ('doctor_meta_quality', 'doctor', 'alex_quality_control', 'system_improvement', False),
    ('doctor_clinical', 'doctor', 'clinical_question', 'senior_clinical_copilot', False),
    ('sip_internal_noise', 'doctor_internal', 'doctor_general', 'doctor_copilot_answer', False),
    ('phone_appointment', 'patient_phone', 'appointment_request', 'book_appointment', False),
    ('phone_emergency', 'patient_phone', 'emergency', 'urgent_handoff', False),
    ('phone_file_action', 'patient_phone', 'patient_file_action', 'deny_autonomous_file_action', False),
    ('doctor_navigation', 'doctor', 'navigation_command', 'doctor_confirmed_action_only', True),
    # Hamle A (2026-05-21): router now classifies human handoff and clinic info
    # directly instead of falling back to general_or_unclear. The guard is the
    # single consumer; these intents are the single source of truth.
    ('phone_human_handoff', 'patient_phone', 'human_handoff', 'human_handoff', False),
    ('phone_clinic_info', 'patient_phone', 'clinic_info', 'clinic_info_handoff', False),
]


def run_matrix() -> dict:
    """Compare current behaviour to the frozen golden table. No printing.

    Returns a structured result so other gates (e.g. the hardening check) can
    consume it directly. ``ok`` is False on any drift or an empty golden table.
    """
    actual_guard = {r[0]: r for r in (_guard_row(c) for c in GUARD_CASES)}
    actual_router = {r[0]: r for r in (_router_row(c) for c in ROUTER_CASES)}
    rows = []
    failed = []
    for kind, golden_table, actual in (
        ("guard", GUARD_GOLDEN, actual_guard),
        ("router", ROUTER_GOLDEN, actual_router),
    ):
        for golden in golden_table:
            name = golden[0]
            got = actual.get(name)
            ok = got == tuple(golden)
            row = {"kind": kind, "name": name, "ok": ok,
                   "golden": tuple(golden), "got": got}
            rows.append(row)
            if not ok:
                failed.append(row)
    empty = not GUARD_GOLDEN or not ROUTER_GOLDEN
    return {
        "ok": (not failed) and (not empty),
        "empty": empty,
        "total": len(rows),
        "passed": len(rows) - len(failed),
        "failed": failed,
        "rows": rows,
    }


def verify() -> int:
    result = run_matrix()
    for row in result["rows"]:
        if row["ok"]:
            got = row["got"]
            if row["kind"] == "guard":
                print(f"[OK] guard {row['name']}: status={got[2]} intent={got[3]}")
            else:
                print(f"[OK] router {row['name']}: role={got[1]} intent={got[2]}")
        else:
            print(f"[ERR] {row['kind']} {row['name']}\n"
                  f"  golden={row['golden']}\n  got   ={row['got']}")
    print("\n=== Sonuc ===")
    if result["empty"]:
        print("ALEX_CONTRACT_MATRIX_EMPTY (golden tablo bos; once --snapshot)")
        return 3
    if not result["ok"]:
        print(f"ALEX_CONTRACT_MATRIX_FAIL ({len(result['failed'])} sapma)")
        return 2
    print("ALEX_CONTRACT_MATRIX_OK")
    return 0


if __name__ == "__main__":
    if "--snapshot" in sys.argv:
        snapshot()
        raise SystemExit(0)
    raise SystemExit(verify())
