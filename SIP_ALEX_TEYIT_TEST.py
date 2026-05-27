# -*- coding: utf-8 -*-
"""SIP_ALEX_TEYIT_TEST - telefon Alex'in gercek cevap kalitesini olcer.

Hem default yol (_ai_phone_generate_reply) hem agent yolu (_ai_phone_agent_loop)
icin ornek girdilerle gercek Ollama cevabini uretir ve yazdirir.
Boylece 'salak' davranisin kaynagi (model? prompt? klinik bilgisi eksik?) gozlemlenir.
Import-only; SIP/server baslatmaz. Ollama'nin acik olmasi gerekir.
"""
import os
import sys
import time

os.environ.setdefault("YAZKLINIK_ALEX_PREWARM", "0")
os.environ.setdefault("YAZKLINIK_AUTO_BACKUP_INTERVAL_SEC", "0")
os.environ.setdefault("YAZKLINIK_SIP_ENABLED", "0")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yazklinik_web as yw  # noqa: E402

INPUTS = [
    "merhaba randevu almak istiyorum",
    "kliniginiz nerede, calisma saatleriniz nedir",
    "carsamba saat ona uygun musunuz",
    "12 haftalik gebeyim, mide bulantisi icin ne yapabilirim",
]


def _phone_model():
    try:
        return yw._alex_pick_phone_model()
    except Exception as exc:
        return "MODEL_HATA:" + repr(exc)


def main():
    print("phone_model:", _phone_model())
    print("agent_mode_enabled:", yw._ai_phone_agent_mode_enabled())
    print("=" * 72)
    hist = []
    for msg in INPUTS:
        print(f"\n>>> HASTA: {msg}")
        # 1) default yol
        t0 = time.time()
        try:
            reply, status = yw._ai_phone_generate_reply(
                msg, caller="05551112233", history=hist, triage={})
        except Exception as exc:
            reply, status = ("DEFAULT_HATA:" + repr(exc), "err")
        dt = time.time() - t0
        print(f"  [default {dt:0.1f}s status={status}]")
        print(f"    {reply}")
        # 2) agent yol
        t0 = time.time()
        try:
            a_reply, a_status = yw._ai_phone_agent_loop(
                msg, history=hist, caller="05551112233", triage={})
        except Exception as exc:
            a_reply, a_status = ("AGENT_HATA:" + repr(exc), "err")
        dt = time.time() - t0
        print(f"  [agent   {dt:0.1f}s status={a_status}]")
        print(f"    {a_reply}")
        hist.append({"role": "user", "content": msg})
        hist.append({"role": "assistant", "content": str(reply)})
    print("\n" + "=" * 72)
    print("SIP_ALEX_TEYIT_TEST DONE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
