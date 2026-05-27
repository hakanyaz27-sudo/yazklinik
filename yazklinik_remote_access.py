"""Reverse-proxy / Tailscale Funnel destek modulu.

YazKlinik web sunucusu artik 3 farkli yoldan acilabilir:

    1. Lokal:           https://127.0.0.1:5443         (doktor PC'si)
    2. Tailnet:         https://<host>.tailnet.ts.net  (Tailscale Serve)
    3. Public (Funnel): https://<funnel-host>          ya da
                        https://176.236.92.142:65187/  (router NAT)

Bu modul:
    - ProxyFix middleware ile X-Forwarded-* basliklarina guven (proxy arkasinda
      dogru URL/IP/protokol gorulsun, redirect'ler bozulmasin)
    - is_remote_request() helper: istek dis ag'dan mi geliyor (lokal/tailnet/public)
    - before_request hook: uzak istekleri yapilandirilmis sekilde print/log
    - Yetki gate'i degildir; mevcut login_required cozulmemis kalir
    - Hicbir hasta verisi disariya yazilmaz; sadece IP/host/UA/path loglanir

Bagimlilik: Flask + Werkzeug (zaten yuklu).
"""

from __future__ import annotations

import logging
import os
from typing import Iterable, Optional


MODULE_VERSION = "2026.05.16-remote-access"

# Lokal kabul edilen IP prefiksleri (uzak sayilmaz)
LOCAL_PREFIXES_DEFAULT = (
    "127.", "localhost",
    "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
    "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
    "172.30.", "172.31.",
    "192.168.",
    "100.",          # Tailscale CGNAT (100.64.0.0/10)
    "fe80::", "::1", # IPv6 link-local + loopback
)


def _is_local_addr(addr: str, prefixes: Iterable[str] = LOCAL_PREFIXES_DEFAULT) -> bool:
    addr = (addr or "").strip().lower()
    if not addr:
        return True  # bos addr'i guvenli kabul et
    # IPv6 koselemeli prefix [::1]:port halinde gelebilir
    addr = addr.lstrip("[").split("]", 1)[0]
    # Port'u dusur
    if ":" in addr and addr.count(":") == 1:
        addr = addr.split(":", 1)[0]
    for p in prefixes:
        if addr.startswith(p):
            return True
    return False


def is_remote_request(request, extra_local_prefixes: Optional[Iterable[str]] = None) -> bool:
    """Bu istek dis ag'dan mi? Tailscale (100.x) ve LAN icindekiler 'lokal' sayilir.
    Sadece public IP'den gelen / public-host'ta acilmis isim uzak sayilir.
    """
    prefixes = tuple(LOCAL_PREFIXES_DEFAULT)
    if extra_local_prefixes:
        prefixes = prefixes + tuple(extra_local_prefixes)

    try:
        # 1) X-Forwarded-For ilk IP (orijinal client)
        xff = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        if xff and not _is_local_addr(xff, prefixes):
            return True
        # 2) X-Forwarded-Host (reverse proxy varsa orijinal host)
        xfh = request.headers.get("X-Forwarded-Host", "")
        if xfh:
            host_part = xfh.split(":", 1)[0]
            if not _is_local_addr(host_part, prefixes) and \
               not host_part.endswith(".ts.net"):  # Tailscale Serve hostnames
                # Public IP / domain
                if "." in host_part:
                    return True
        # 3) Direct remote_addr fallback
        ra = (request.remote_addr or "").strip()
        if ra and not _is_local_addr(ra, prefixes):
            return True
    except Exception:
        pass
    return False


def client_ip(request) -> str:
    """Gercek client IP'sini cikar (proxy header'lara saygi)."""
    try:
        xff = request.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
        if xff:
            return xff
        return request.remote_addr or ""
    except Exception:
        return ""


def register_remote_access(app, *,
                            trust_x_for: int = 1,
                            trust_x_proto: int = 1,
                            trust_x_host: int = 1,
                            trust_x_port: int = 1,
                            log_remote_requests: bool = True,
                            logger: Optional[logging.Logger] = None) -> dict:
    """Flask app'e ProxyFix + before_request audit hook tak.

    Args:
        trust_x_for/proto/host/port: ProxyFix katman sayisi (zincirde kac hop?)
            Tek bir reverse proxy varsa 1. Tailscale Funnel + nginx zinciri 2 olabilir.
        log_remote_requests: True ise uzak istekleri logger ile yazdir
        logger: kullanilacak logger; None ise modulun kendi logger'i

    Returns:
        {"ok": bool, "wired": [...], "errors": [...]}
    """
    log = logger or logging.getLogger("yazklinik.remote")
    result = {"ok": True, "wired": [], "errors": [], "version": MODULE_VERSION}

    # 1) ProxyFix middleware
    try:
        from werkzeug.middleware.proxy_fix import ProxyFix
        # Cift uygulama korumasi - daha once register edildiyse atla
        if not getattr(app.wsgi_app, "_yk_proxy_fixed", False):
            app.wsgi_app = ProxyFix(
                app.wsgi_app,
                x_for=trust_x_for,
                x_proto=trust_x_proto,
                x_host=trust_x_host,
                x_port=trust_x_port,
            )
            try:
                # Mark, tekrar register edilmesin
                app.wsgi_app._yk_proxy_fixed = True  # type: ignore[attr-defined]
            except Exception:
                pass
            result["wired"].append("ProxyFix")
    except ImportError:
        result["errors"].append("werkzeug.middleware.proxy_fix yok")
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"ProxyFix hata: {exc}")

    # 2) before_request remote audit hook
    if log_remote_requests:
        try:
            from flask import request as _flask_req, g

            @app.before_request
            def _yk_remote_audit():
                try:
                    g.yk_is_remote = is_remote_request(_flask_req)
                    g.yk_client_ip = client_ip(_flask_req)
                    if g.yk_is_remote:
                        path = _flask_req.path or "?"
                        method = _flask_req.method
                        ua = _flask_req.headers.get("User-Agent", "")[:80]
                        host = (_flask_req.headers.get("X-Forwarded-Host")
                                or _flask_req.host)
                        log.info(
                            "REMOTE %s %s from=%s host=%s ua=%s",
                            method, path, g.yk_client_ip, host, ua
                        )
                except Exception:
                    pass

            result["wired"].append("before_request:yk_remote_audit")
        except Exception as exc:  # noqa: BLE001
            result["errors"].append(f"before_request hata: {exc}")

    # 3) Yardimci response header (debug: hangi mod calistim)
    try:
        @app.after_request
        def _yk_remote_header(response):
            try:
                from flask import g as _g
                if getattr(_g, "yk_is_remote", False):
                    response.headers.setdefault("X-YK-Remote-Detected", "1")
                response.headers.setdefault("X-YK-Server", "D700")
            except Exception:
                pass
            return response
        result["wired"].append("after_request:headers")
    except Exception as exc:  # noqa: BLE001
        result["errors"].append(f"after_request hata: {exc}")

    if result["errors"]:
        result["ok"] = False
    return result


# --- Standalone test ---

if __name__ == "__main__":
    # Lokal IP testleri
    cases = [
        ("127.0.0.1", True),
        ("localhost", True),
        ("192.168.1.50", True),
        ("10.0.0.5", True),
        ("100.102.239.42", True),   # Tailscale
        ("100.64.10.5", True),      # Tailscale
        ("172.20.10.3", True),
        ("8.8.8.8", False),
        ("176.236.92.142", False),  # Public TR IP (kullanicinin)
        ("203.0.113.10", False),
        ("[::1]", True),
        ("fe80::1", True),
    ]
    print("=== _is_local_addr testleri ===")
    ok = 0
    for addr, expected in cases:
        actual = _is_local_addr(addr)
        mark = "OK" if actual == expected else "FAIL"
        if actual == expected:
            ok += 1
        print(f"  {mark}  {addr:20} expected={expected}  got={actual}")
    print(f"\n{ok}/{len(cases)} pass")

    # Sahte Flask request ile is_remote_request testi
    class FakeReq:
        def __init__(self, headers=None, remote_addr=""):
            self.headers = headers or {}
            self.remote_addr = remote_addr
            self.host = self.headers.get("Host", "")
            self.path = "/"
            self.method = "GET"
    print("\n=== is_remote_request testleri ===")
    samples = [
        ("Lokal", FakeReq(remote_addr="127.0.0.1"), False),
        ("Tailscale", FakeReq(remote_addr="100.102.239.42"), False),
        ("LAN", FakeReq(remote_addr="192.168.1.50"), False),
        ("Public X-FF", FakeReq(headers={"X-Forwarded-For": "176.236.92.142"},
                                 remote_addr="127.0.0.1"), True),
        ("Public direct", FakeReq(remote_addr="8.8.8.8"), True),
        ("Tailscale ts.net host", FakeReq(headers={"X-Forwarded-Host": "doktor.tailnet.ts.net"},
                                            remote_addr="127.0.0.1"), False),
    ]
    for name, req, expected in samples:
        actual = is_remote_request(req)
        mark = "OK" if actual == expected else "FAIL"
        print(f"  {mark}  {name:25} expected={expected}  got={actual}")

