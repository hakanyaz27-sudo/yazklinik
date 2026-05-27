# -*- coding: utf-8 -*-
"""ALEX_ONLINE_GATE_TEST - ChatGPT(OpenAI) yonlendirme + KVKK kapisini dogrular.
Genel sorular -> online (ChatGPT). Hasta verisi/adi/baglami -> YEREL kalir."""
import os
import sys
os.environ.setdefault("YAZKLINIK_SIP_ENABLED", "0")
os.environ.setdefault("YAZKLINIK_ALEX_PREWARM", "0")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yazklinik_web as yw  # noqa: E402


def gate(t):
    pd = yw._alex_message_has_patient_data(t)
    try:
        nm = yw._alex_message_mentions_known_patient(t)
    except Exception:
        nm = False
    related = yw._alex_message_is_patient_related(t)
    online = yw.openai_available() and not related
    return online, pd, nm


GENERAL = [
    "Merhaba nasilsin",
    "12 haftalik gebede folik asit dozu nedir",
    "bana kisa bir motivasyon sozu yaz",
    "preeklampsi nedir kisaca anlat",
]
PATIENT = [
    "Ebru Erdogan in son tahlili ne",
    "hastamin durumu hakkinda bilgi ver",
    "0555 123 45 67 numarali danisan",
    "12345678901 hastasinin recetesi",
]


def main():
    print("openai_available=", yw.openai_available())
    print("=== GENEL (online=True beklenir) ===")
    gok = 0
    for t in GENERAL:
        o, pd, pi = gate(t)
        if o:
            gok += 1
        print(f"  online={o!s:5} pd={pd!s:5} pi={pi!s:5} <- {t!r}")
    print("=== HASTA (online=False beklenir = YEREL) ===")
    pok = 0
    for t in PATIENT:
        o, pd, pi = gate(t)
        if not o:
            pok += 1
        print(f"  online={o!s:5} pd={pd!s:5} pi={pi!s:5} <- {t!r}")
    print(f"\ngenel_online={gok}/{len(GENERAL)} | hasta_yerel={pok}/{len(PATIENT)}")
    # KVKK kapisi (hasta -> yerel) HER ZAMAN gecmeli. Genel -> online sadece
    # OpenAI anahtari aktifse beklenir; anahtar yoksa hepsi yerel olur (dogru).
    openai_on = yw.openai_available()
    if not openai_on:
        print("NOT: ChatGPT KAPALI (OpenAI anahtari aktif DB'de yok) -> genel "
              "sorular yerel modele gidiyor. Bu DOGRU davranis; online testleri "
              "atlandi. Anahtari /ayarlar/yapay-zeka'dan girince aktiflesir.")
    ok = (pok == len(PATIENT)) and (gok == len(GENERAL) if openai_on else True)
    print("ALEX_ONLINE_GATE_TEST", "OK" if ok else "DIKKAT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
