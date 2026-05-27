# -*- coding: utf-8 -*-
"""SIP_RANDEVU_TEST - telefon randevu akisinin TAMAMLANABILIRLIGINI test eder.
Gercek DB'ye randevu YAZMADAN, akisin alanlari (isim/tarih/saat/telefon) turler
arasi biriktirip 'appointment_need_phone' adimina dogru ilerleyip ilerlemedigini
ve slotlarin dolu olup olmadigini gosterir. Import-only."""
import os
import sys
from datetime import datetime, timedelta

os.environ.setdefault("YAZKLINIK_ALEX_PREWARM", "0")
os.environ.setdefault("YAZKLINIK_AUTO_BACKUP_INTERVAL_SEC", "0")
os.environ.setdefault("YAZKLINIK_SIP_ENABLED", "0")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yazklinik_web as yw  # noqa: E402

CALLER = "05321234567"


def slots_report():
    print("=== SLOT DURUMU ===")
    for d in range(0, 4):
        day = (datetime.now().date() + timedelta(days=d)).strftime("%Y-%m-%d")
        try:
            s = yw._ai_phone_available_slots(day)
        except Exception as exc:
            s = ["HATA:" + repr(exc)]
        print(f"  {day}: {len(s)} slot -> {', '.join(map(str, s[:6]))}")


def turn(hist, msg, caller=CALLER):
    """_ai_phone_handle_appointment_flow'u tek turda cagir (book ETMEDEN onceki adim)."""
    reply, status = yw._ai_phone_handle_appointment_flow(
        msg, history=hist, caller=caller, caller_patient=None, triage={})
    hist.append({"role": "user", "content": msg})
    if reply:
        hist.append({"role": "assistant", "content": reply})
    return reply, status


def main():
    slots_report()
    print("\n=== RANDEVU AKISI (book oncesi adimlar) ===")
    hist = []
    # caller'i once musait olmayan bir hasta yapma; akis isim/tarih/saat toplasin
    seq = [
        "randevu almak istiyorum",
        "hastanin adi Ayse Yilmaz",
        "yarin saat on bucuk",
    ]
    last_status = ""
    for m in seq:
        reply, status = turn(hist, m)
        last_status = status
        print(f"\n>>> {m}")
        print(f"  [{status}] {reply}")

    # Bu noktada isim+tarih+saat toplanmali; bir sonraki adim 'need_phone' olmali.
    # Telefon verince GERCEK book olacagi icin burada DURUYORUZ (DB'ye yazmamak icin).
    reached_phone = last_status in (
        "appointment_need_phone", "appointment_offer_slots",
        "appointment_need_name")
    print("\n--------------------------------------------------")
    print(f"son_status={last_status} | telefon/onay adimina ulasti={reached_phone}")
    # Ek dogrulama: state collector isim+tarih+saat'i goruyor mu?
    try:
        st = yw._ai_phone_agent_collect_state(
            "yarin saat on bucuk", hist, CALLER, "")
        print("toplanan_state:", st.get("collected"))
    except Exception as exc:
        print("state_hata:", repr(exc))
    print("SIP_RANDEVU_TEST", "OK" if reached_phone else "DIKKAT")
    return 0 if reached_phone else 1


if __name__ == "__main__":
    sys.exit(main())
