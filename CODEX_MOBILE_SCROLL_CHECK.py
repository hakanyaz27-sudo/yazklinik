#!/usr/bin/env python3
"""D700 mobile Chrome scroll smoke check.

Runs mobile-emulated login + /hastalar scroll probe using Playwright.
Includes startup retry so brief 5052/5443 restart windows do not create false fail.
"""

from __future__ import annotations

import json
import os
import ssl
import time
from datetime import datetime
from pathlib import Path
from urllib import error as url_error
from urllib import request as url_request

from playwright.sync_api import TimeoutError as PwTimeoutError
from playwright.sync_api import sync_playwright


def _env(name: str, default: str) -> str:
    value = os.environ.get(name, "").strip()
    return value if value else default


def _metrics(page) -> dict:
    return page.evaluate(
        """() => {
          const el = document.scrollingElement || document.documentElement;
          const bodyStyle = getComputedStyle(document.body);
          const htmlStyle = getComputedStyle(document.documentElement);
          return {
            scrollTop: el ? (el.scrollTop || 0) : (window.scrollY || 0),
            scrollHeight: el ? (el.scrollHeight || 0) : 0,
            clientHeight: el ? (el.clientHeight || 0) : 0,
            bodyOverflowY: bodyStyle.overflowY || "",
            htmlOverflowY: htmlStyle.overflowY || "",
            bodyPosition: bodyStyle.position || "",
            bodyTopInline: document.body.style.top || "",
            hasOverlay: !!document.querySelector(
              '#sidebarOverlay.show, .sidebar-overlay.show, .modal.show, .modal-backdrop.show, .offcanvas-backdrop.show, #ykMediaViewer.show, .yk-media-viewer.show, [data-scroll-lock="1"], body.modal-open'
            )
          };
        }"""
    )


def _build_bases(primary_base: str) -> list[str]:
    bases: list[str] = []
    env_bases = _env("YAZKLINIK_MOBILE_SCROLL_BASES", "")
    if env_bases:
        for raw in env_bases.split(","):
            one = raw.strip().rstrip("/")
            if one and one not in bases:
                bases.append(one)
    for one in (
        primary_base.strip().rstrip("/"),
        "http://127.0.0.1:5052",
        "https://127.0.0.1:5443",
    ):
        if one and one not in bases:
            bases.append(one)
    return bases


def _probe_base(base: str, timeout_sec: float = 4.0) -> tuple[int | None, str | None]:
    try:
        kwargs = {}
        if base.lower().startswith("https://"):
            kwargs["context"] = ssl._create_unverified_context()
        req = url_request.Request(
            f"{base}/giris",
            headers={"User-Agent": "D700-MobileScrollCheck/1.0"},
        )
        with url_request.urlopen(req, timeout=timeout_sec, **kwargs) as resp:
            return int(getattr(resp, "status", 0) or 0), None
    except url_error.HTTPError as ex:
        return int(getattr(ex, "code", 0) or 0), str(ex)
    except Exception as ex:
        return None, str(ex)


def _wait_ready_base(bases: list[str], wait_sec: int) -> tuple[str | None, str]:
    deadline = time.time() + max(10, int(wait_sec))
    last_detail = ""
    while time.time() < deadline:
        for base in bases:
            code, detail = _probe_base(base, timeout_sec=4.0)
            if code in (200, 302, 303, 307, 308):
                return base, f"HTTP {code}"
            if code is not None:
                last_detail = f"{base} -> HTTP {code}"
            elif detail:
                last_detail = f"{base} -> {detail}"
        time.sleep(3)
    return None, last_detail or "timeout waiting for /giris"


def main() -> int:
    primary_base = _env("YAZKLINIK_HTTPS_BASE", "http://127.0.0.1:5052")
    username = _env("YAZKLINIK_SMOKE_USER", "doktor")
    password = _env("YAZKLINIK_SMOKE_PASSWORD", "1133")
    threshold = int(_env("YAZKLINIK_MOBILE_SCROLL_DELTA_MIN", "120"))
    wait_sec = int(_env("YAZKLINIK_MOBILE_SCROLL_WAIT_SEC", "150"))

    bases = _build_bases(primary_base)
    selected_base, ready_info = _wait_ready_base(bases, wait_sec)

    out_dir = Path("webui_tools")
    out_dir.mkdir(parents=True, exist_ok=True)
    shot = out_dir / f"mobile-scroll-proof-{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"

    result = {
        "ok": False,
        "delta": 0,
        "screenshot": str(shot),
        "base": primary_base,
        "candidates": bases,
        "selected_base": selected_base,
    }
    if not selected_base:
        result["error"] = f"server not ready: {ready_info}"
        print(json.dumps(result, ensure_ascii=False))
        return 2

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(
                ignore_https_errors=True,
                viewport={"width": 393, "height": 852},
                is_mobile=True,
                has_touch=True,
                device_scale_factor=2.625,
                user_agent=(
                    "Mozilla/5.0 (Linux; Android 14; Pixel 7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Mobile Safari/537.36"
                ),
            )
            page = context.new_page()

            page.goto(f"{selected_base}/giris", wait_until="domcontentloaded", timeout=90000)
            page.fill('input[name="username"], input#username, input[type="text"]', username)
            page.fill(
                'input[name="password"], input#password, input[type="password"]', password
            )
            with page.expect_navigation(wait_until="domcontentloaded", timeout=90000):
                page.click('button[type="submit"], button:has-text("Giris")')

            page.goto(f"{selected_base}/hastalar", wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(1200)

            before = _metrics(page)
            page.mouse.wheel(0, 1200)
            page.wait_for_timeout(300)
            page.mouse.wheel(0, 1000)
            page.wait_for_timeout(300)
            page.evaluate("window.scrollBy(0, 900)")
            page.wait_for_timeout(300)
            after = _metrics(page)

            delta = int(after.get("scrollTop", 0)) - int(before.get("scrollTop", 0))
            ok = delta > threshold and not bool(after.get("hasOverlay"))
            page.screenshot(path=str(shot), full_page=False)

            result.update(
                {
                    "ok": ok,
                    "delta": delta,
                    "threshold": threshold,
                    "ready_info": ready_info,
                    "before": before,
                    "after": after,
                }
            )

            context.close()
            browser.close()

    except PwTimeoutError as ex:
        result["error"] = f"timeout: {ex}"
    except Exception as ex:
        result["error"] = str(ex)

    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
