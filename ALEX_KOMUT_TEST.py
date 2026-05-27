# -*- coding: utf-8 -*-
"""ALEX_KOMUT_TEST - web Alex 'hasta ac/bul/ozet' komut katmanini dogrular.
Gercek hastalarla _alex_try_command ciktilarini gosterir. Import-only."""
import os
import sys

os.environ.setdefault("YAZKLINIK_ALEX_PREWARM", "0")
os.environ.setdefault("YAZKLINIK_AUTO_BACKUP_INTERVAL_SEC", "0")
os.environ.setdefault("YAZKLINIK_SIP_ENABLED", "0")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yazklinik_web as yw  # noqa: E402

# Komut olmasi gerekenler + olmamasi gerekenler (sohbet/tibbi soru):
CMD_INPUTS = [
    "Ebru Erdogan'i ac",
    "ebruyu bul",
    "Buket Guler dosyasini ac",
    "Seval'in ozeti",
    "Esra'yi getir",
]
# NOT: "Bugun kac randevu var?" artik gecerli bir KOMUT (randevu listele) -
# bilerek cikarildi. Asagidakiler gercek sohbet/tibbi sorulardir.
NONCMD_INPUTS = [
    "Gebelik takibinde NT taramasi nedir?",
    "bana yardim et",
    "12 haftalik gebede folik asit dozu nedir",
    "tesekkurler cok yardimci oldun",
]


def main():
    print("=== KOMUT olmasi beklenenler ===")
    ok_cmd = 0
    for m in CMD_INPUTS:
        try:
            res = yw._alex_try_command(m)
        except Exception as exc:
            res = {"_err": repr(exc)}
        if res and not res.get("_err"):
            ok_cmd += 1
            links = res.get("links") or []
            first_line = (res.get("reply") or "").splitlines()[0] if res.get("reply") else ""
            print(f"  OK  '{m}'")
            print(f"      status={res.get('status')} | link={links[0]['url'] if links else '-'}")
            print(f"      ozet1: {first_line}")
        else:
            print(f"  -- '{m}' -> KOMUT DEGIL (beklenmiyordu) {res}")
    print(f"komut_yakalanan={ok_cmd}/{len(CMD_INPUTS)}")

    print("\n=== KOMUT OLMAMASI beklenenler (sohbet/tibbi) ===")
    false_pos = 0
    for m in NONCMD_INPUTS:
        try:
            res = yw._alex_try_command(m)
        except Exception as exc:
            res = {"_err": repr(exc)}
        if res and not res.get("_err"):
            false_pos += 1
            print(f"  YANLIS-POZITIF '{m}' -> {res.get('status')}")
        else:
            print(f"  OK (sohbete birakildi) '{m}'")
    print(f"yanlis_pozitif={false_pos}/{len(NONCMD_INPUTS)}")

    print("\n=== Ornek tam ozet (Ebru) ===")
    res = yw._alex_try_command("Ebru Erdogan'i ac")
    if res:
        print(res.get("reply"))
        print("LINKLER:", res.get("links"))

    ok = (ok_cmd >= 3 and false_pos == 0)
    print("\nALEX_KOMUT_TEST", "OK" if ok else "DIKKAT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
