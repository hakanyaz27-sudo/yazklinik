# -*- coding: utf-8 -*-
"""ALEX_STREAM_HIZ_TEST - OpenAI streaming ilk-token gecikmesini olcer.
Sesli Alex'in 'cok gec devreye giriyor' sikayeti icin: ilk token ~1sn olmali."""
import os
import sys
import time
os.environ.setdefault("YAZKLINIK_SIP_ENABLED", "0")
os.environ.setdefault("YAZKLINIK_ALEX_PREWARM", "0")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yazklinik_web as yw  # noqa: E402


def main():
    cfg = yw._alex_online_llm_config()
    print("online cfg:", bool(cfg), cfg.get("model") if cfg else None)
    if not cfg:
        print("NO ONLINE CFG"); return 1
    msgs = [
        {"role": "system", "content": "Sen Alexsin, sesli klinik asistan. Kisa, 2 cumle Turkce cevap ver."},
        {"role": "user", "content": "Merhaba doktorum, bugun bana nasil yardimci olabilirsin?"},
    ]
    t0 = time.time()
    first = None
    full = ""
    n = 0
    for tok in yw._alex_online_chat_tokens(msgs, cfg, timeout=30):
        if first is None:
            first = time.time() - t0
        full += tok
        n += 1
    total = time.time() - t0
    print(f"ilk_token={first:.2f}s | toplam={total:.2f}s | token={n}")
    print("cevap:", full[:200])
    ok = (first is not None and first < 3.0 and len(full.strip()) > 5)
    print("ALEX_STREAM_HIZ_TEST", "OK" if ok else "DIKKAT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
