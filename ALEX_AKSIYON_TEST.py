# -*- coding: utf-8 -*-
"""ALEX_AKSIYON_TEST - web Alex'in eylem (aksiyon) katmanini dogrular:
hasta ac, randevu olustur (sozel onay), randevu listele, navigasyon, iptal.
Randevu YAZMA testi kendi olusturdugu kaydi sonra 'cancelled' yapip temizler
(gercek aktif randevu birakmaz). Import-only."""
import os
import sys

os.environ.setdefault("YAZKLINIK_ALEX_PREWARM", "0")
os.environ.setdefault("YAZKLINIK_AUTO_BACKUP_INTERVAL_SEC", "0")
os.environ.setdefault("YAZKLINIK_SIP_ENABLED", "0")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yazklinik_web as yw  # noqa: E402

UK = "alex_test_doktor"


def show(title, res):
    st = (res or {}).get("status") if res else None
    rep = (res or {}).get("reply") if res else None
    first = (rep or "").splitlines()[0] if rep else ""
    links = (res or {}).get("links") or []
    print(f"  {title}")
    print(f"    status={st} | link={links[0]['url'] if links else '-'}")
    print(f"    > {first}")
    return res


def main():
    print("=== 1) HASTA AC (read) ===")
    show("Ebru Erdogan'i ac", yw._alex_try_command("Ebru Erdogan'i ac", UK))

    print("\n=== 2) RANDEVU LISTELE (read) ===")
    show("bugunku randevular", yw._alex_try_command("bugunku randevular", UK))

    print("\n=== 3) NAVIGASYON (read) ===")
    show("takvimi ac", yw._alex_try_command("takvimi ac", UK))
    show("ayarlari ac", yw._alex_try_command("ayarlari ac", UK))

    print("\n=== 4) RANDEVU OLUSTUR - eksik bilgi akisi ===")
    show("randevu ver", yw._alex_try_command("randevu ver", UK))  # kim?
    show("Ebru Erdogan'a randevu ver", yw._alex_try_command("Ebru Erdogan'a randevu ver", UK))  # ne zaman?

    print("\n=== 5) RANDEVU OLUSTUR - tam + ONAY ===")
    yw._alex_cmd_clear_pending(UK)
    r = show("Ebru Erdogan'a 31.12.2026 09:00 randevu ver",
             yw._alex_try_command("Ebru Erdogan'a 31.12.2026 saat 09:00 randevu ver", UK))
    pend = yw._alex_cmd_get_pending(UK)
    print(f"    pending_set={bool(pend)} kind={pend.get('kind') if pend else None} "
          f"date={pend.get('date') if pend else None} time={pend.get('time') if pend else None}")
    confirm_ok = False
    cleaned = False
    if pend:
        r2 = show("evet (onay)", yw._alex_try_command("evet", UK))
        confirm_ok = bool(r2 and r2.get("status") == "alex_appt_booked")
        # temizle: az once olusturdugumuz test randevusunu cancelled yap
        try:
            with yw.db_conn() as con:
                con.execute(
                    "UPDATE appointments SET status='cancelled' "
                    "WHERE appointment_date='2026-12-31' AND created_by='web-alex'")
                con.commit()
                cleaned = True
        except Exception as exc:
            print("    cleanup_hata:", repr(exc))
    print(f"    booked={confirm_ok} | test_kaydi_temizlendi(cancelled)={cleaned}")

    print("\n=== 6) IPTAL akisi ===")
    yw._alex_cmd_clear_pending(UK)
    yw._alex_try_command("Ebru Erdogan'a 30.12.2026 saat 10:00 randevu ver", UK)
    show("hayir (iptal)", yw._alex_try_command("hayir", UK))
    print(f"    iptal_sonrasi_pending={yw._alex_cmd_get_pending(UK)}")

    print("\n=== 7) KOMUT DEGIL (sohbete birakilmali) ===")
    for m in ("Gebelikte NT taramasi nedir?", "bana yardim et", "tesekkurler"):
        res = yw._alex_try_command(m, UK)
        print(f"    '{m}' -> {'KOMUT('+res['status']+')' if res else 'sohbet (None)'}")

    ok = confirm_ok
    print("\nALEX_AKSIYON_TEST", "OK" if ok else "DIKKAT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
