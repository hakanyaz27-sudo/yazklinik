"""Sentry Hata Izleme Entegrasyonu (opsiyonel).

DSN env yoksa hicbir sey yapmaz. Yazklinik_web.py icinde import:
    import yazklinik_sentry_init
    yazklinik_sentry_init.init_if_configured()
"""
from __future__ import annotations

import os
import logging
from typing import Any, Dict


AGENT_VERSION = "2026.05.17-sentry"

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
SENTRY_ENV = os.environ.get("SENTRY_ENV", "production")
SENTRY_SAMPLE_RATE = float(os.environ.get("SENTRY_SAMPLE_RATE", "0.1"))


_initialized = False
log = logging.getLogger("yazklinik_sentry")


def init_if_configured() -> Dict[str, Any]:
    """SENTRY_DSN env varsa Sentry baslat."""
    global _initialized
    if _initialized:
        return {"ok": True, "already": True}
    if not SENTRY_DSN:
        return {"ok": False, "reason": "SENTRY_DSN env yok"}
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=SENTRY_ENV,
            traces_sample_rate=SENTRY_SAMPLE_RATE,
            integrations=[FlaskIntegration(),
                           LoggingIntegration(level=logging.INFO,
                                                event_level=logging.ERROR)],
            send_default_pii=False,  # KVKK - PII gondermez
            before_send=_redact_pii,
        )
        _initialized = True
        return {"ok": True, "environment": SENTRY_ENV}
    except ImportError:
        return {"ok": False, "reason": "pip install sentry-sdk[flask]"}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


_TC_RE = None
_PHONE_RE = None
_EMAIL_RE = None


def _lazy_init_regex():
    global _TC_RE, _PHONE_RE, _EMAIL_RE
    if _TC_RE is None:
        import re
        _TC_RE = re.compile(r"\b\d{11}\b")
        _PHONE_RE = re.compile(r"\b5\d{9}\b")
        _EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _redact_value(v):
    """String tipinde PII pattern'lerini maskele. eval YOK - guvenli walk."""
    if isinstance(v, str):
        _lazy_init_regex()
        v = _TC_RE.sub("TC_REDACTED", v)
        v = _PHONE_RE.sub("PHONE_REDACTED", v)
        v = _EMAIL_RE.sub("EMAIL_REDACTED", v)
        return v
    if isinstance(v, dict):
        return {k: _redact_value(val) for k, val in v.items()}
    if isinstance(v, list):
        return [_redact_value(x) for x in v]
    if isinstance(v, tuple):
        return tuple(_redact_value(x) for x in v)
    return v


def _redact_pii(event, hint):
    """KVKK uyumlu - T.C. + telefon + e-mail maskele.

    GUVENLIK: Onceki versiyon eval(str(event)) yapiyordu - RCE riski.
    Yeni versiyon dict/list/string ortak recursive walk yapip
    sadece pattern match'i replace eder, eval cagrisi YOK.
    """
    try:
        return _redact_value(event)
    except Exception:
        return event


def health_check() -> Dict[str, Any]:
    return {"ok": True, "agent_version": AGENT_VERSION,
            "configured": bool(SENTRY_DSN), "initialized": _initialized}


if __name__ == "__main__":
    import json
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
