# -*- coding: utf-8 -*-
"""VERIFY_HOME_RENDER - / ve /hastalar SAYFALARI mevcut kodla render oluyor mu?
Flask test client + dogrudan session (sifre kullanilmaz). 500/NameError arar."""
import os
import sys
os.environ.setdefault("YAZKLINIK_SIP_ENABLED", "0")
os.environ.setdefault("YAZKLINIK_ALEX_PREWARM", "0")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import yazklinik_web as yw  # noqa: E402

app = yw.app
app.config["PROPAGATE_EXCEPTIONS"] = False  # 500 dondursun, exception firlatmasin
c = app.test_client()
with c.session_transaction() as s:
    s["user"] = "doktor"
    s["role"] = "doktor"
    s["logged_in"] = True
    s["2fa_ok"] = True

ok = True
for path in ["/", "/hastalar", "/hastalar/"]:
    try:
        r = c.get(path)
        code = r.status_code
        note = ""
        if code >= 500:
            ok = False
            note = " <-- 500 HATA"
        elif code in (301, 302):
            note = " (redirect: " + (r.headers.get("Location", "")[:40]) + ")"
        print(f"  GET {path:14} -> {code}{note}")
    except Exception as e:
        ok = False
        print(f"  GET {path:14} -> EXCEPTION {type(e).__name__}: {repr(e)[:160]}")

print("VERIFY_HOME_RENDER", "OK" if ok else "DIKKAT (500/exception var)")
sys.exit(0 if ok else 1)
