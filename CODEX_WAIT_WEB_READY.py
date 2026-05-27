#!/usr/bin/env python3
"""Wait until D700 web endpoints are stably ready."""

from __future__ import annotations

import argparse
import ssl
import time
import urllib.error
import urllib.request


def _probe(url: str, timeout: float = 5.0) -> tuple[int, str]:
    try:
        kwargs = {}
        if url.lower().startswith("https://"):
            kwargs["context"] = ssl._create_unverified_context()
        req = urllib.request.Request(url, headers={"User-Agent": "D700-WaitReady/1.0"})
        with urllib.request.urlopen(req, timeout=timeout, **kwargs) as resp:
            return int(getattr(resp, "status", 0) or 0), ""
    except urllib.error.HTTPError as ex:
        return int(getattr(ex, "code", 0) or 0), str(ex)
    except Exception as ex:
        return 0, str(ex)


def main() -> int:
    parser = argparse.ArgumentParser(description="Wait for D700 web readiness.")
    parser.add_argument("--wait-sec", type=int, default=420)
    parser.add_argument("--interval-sec", type=float, default=8.0)
    parser.add_argument("--streak", type=int, default=2)
    parser.add_argument("--http-url", default="http://127.0.0.1:5052/giris")
    parser.add_argument("--https-url", default="https://127.0.0.1:5443/giris")
    parser.add_argument("--require-both", action="store_true")
    args = parser.parse_args()

    deadline = time.time() + max(15, int(args.wait_sec))
    need_both = bool(args.require_both)
    ok_http = 0
    ok_https = 0
    last_http = ""
    last_https = ""

    while time.time() < deadline:
        code_http, detail_http = _probe(args.http_url, timeout=5.0)
        code_https, detail_https = _probe(args.https_url, timeout=5.0)

        ok_http = ok_http + 1 if code_http == 200 else 0
        if need_both:
            ok_https = ok_https + 1 if code_https == 200 else 0

        if detail_http:
            last_http = detail_http
        elif code_http:
            last_http = f"HTTP {code_http}"

        if detail_https:
            last_https = detail_https
        elif code_https:
            last_https = f"HTTP {code_https}"

        print(
            f"[wait] http={code_http} streak_http={ok_http} "
            f"https={code_https} streak_https={ok_https}"
        )

        if ok_http >= args.streak and (not need_both or ok_https >= args.streak):
            print("[OK] WEB_READY")
            return 0

        time.sleep(max(1.0, float(args.interval_sec)))

    print(f"[ERR] WEB_NOT_READY http={last_http or '-'} https={last_https or '-'}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
