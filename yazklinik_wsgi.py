#!/usr/bin/env python
"""Linux/Gunicorn WSGI entrypoint for YazKlinik D700.

This module intentionally does not run the Windows launcher code in
``yazklinik_web.py``. Gunicorn imports ``application`` directly, while Nginx or
another reverse proxy handles TLS in front of it.
"""
from __future__ import annotations

import os

os.environ.setdefault("YAZKLINIK_SERVER_ENGINE", "gunicorn")
os.environ.setdefault("YAZKLINIK_LINUX_WSGI", "1")
os.environ.setdefault("YAZKLINIK_ENABLE_HTTPS", "0")

import yazklinik_web as _web  # noqa: E402


application = _web.app
app = application


def _call_optional_boot_hook(name: str) -> None:
    hook = getattr(_web, name, None)
    if not callable(hook):
        return
    try:
        hook()
    except Exception as exc:  # noqa: BLE001
        print(f"WSGI boot hook skipped: {name}: {exc}")


_call_optional_boot_hook("_yk_start_post_boot_tasks")
_call_optional_boot_hook("_rx_warm_catalog_cache_async")
