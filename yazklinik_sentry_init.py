"""Sentry Hata Izleme Entegrasyonu (opsiyonel).

DSN env yoksa hicbir sey yapmaz. Yazklinik_web.py icinde import:
    import yazklinik_sentry_init
    yazklinik_sentry_init.init_if_configured()
"""
from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any, Dict


AGENT_VERSION = "2026.05.23-sentry-runtime-env"

_initialized = False
_initialized_settings: Dict[str, Any] = {}
log = logging.getLogger("yazklinik_sentry")


def _read_config_env_fallback() -> Dict[str, str]:
    cfg_path = Path(__file__).resolve().parent / "config.env"
    if not cfg_path.exists():
        return {}
    values: Dict[str, str] = {}
    try:
        for raw_line in cfg_path.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = str(raw_line or "").strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            k = key.strip()
            if not k:
                continue
            values[k] = value.strip()
    except Exception:
        return {}
    return values


def _safe_sample_rate(raw: Any, default: float = 0.10) -> float:
    try:
        value = float(str(raw).strip())
    except Exception:
        return float(default)
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def _read_runtime_settings() -> Dict[str, Any]:
    fallback = _read_config_env_fallback()
    dsn = str(os.environ.get("SENTRY_DSN", fallback.get("SENTRY_DSN", "")) or "").strip()
    environment = str(
        os.environ.get("SENTRY_ENV", fallback.get("SENTRY_ENV", "production")) or "production"
    ).strip() or "production"
    sample_rate = _safe_sample_rate(
        os.environ.get("SENTRY_SAMPLE_RATE", fallback.get("SENTRY_SAMPLE_RATE", "0.1")),
        default=0.10,
    )
    release = str(os.environ.get("YAZKLINIK_RELEASE", "") or "").strip()
    return {
        "dsn": dsn,
        "environment": environment,
        "sample_rate": sample_rate,
        "release": release,
    }


def init_if_configured() -> Dict[str, Any]:
    """SENTRY_DSN env varsa Sentry baslat."""
    global _initialized, _initialized_settings
    settings = _read_runtime_settings()
    if _initialized:
        return {
            "ok": True,
            "already": True,
            "environment": _initialized_settings.get("environment", settings.get("environment")),
            "sample_rate": _initialized_settings.get("sample_rate", settings.get("sample_rate")),
        }
    if not settings.get("dsn"):
        return {"ok": False, "reason": "SENTRY_DSN env yok"}
    try:
        import sentry_sdk
        from sentry_sdk.integrations.flask import FlaskIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        release_name = settings.get("release") or None
        sentry_sdk.init(
            dsn=settings.get("dsn"),
            environment=settings.get("environment"),
            traces_sample_rate=settings.get("sample_rate"),
            release=release_name,
            integrations=[FlaskIntegration(),
                           LoggingIntegration(level=logging.INFO,
                                                event_level=logging.ERROR)],
            send_default_pii=False,  # KVKK - PII gondermez
            before_send=_redact_pii,
        )
        _initialized = True
        _initialized_settings = settings
        return {
            "ok": True,
            "environment": settings.get("environment"),
            "sample_rate": settings.get("sample_rate"),
            "release": release_name,
        }
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
    settings = _read_runtime_settings()
    return {"ok": True, "agent_version": AGENT_VERSION,
            "configured": bool(settings.get("dsn")), "initialized": _initialized,
            "environment": settings.get("environment"),
            "sample_rate": settings.get("sample_rate")}


if __name__ == "__main__":
    import json
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
