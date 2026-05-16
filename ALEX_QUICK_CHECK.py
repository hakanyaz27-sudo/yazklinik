"""YazKlinik D250 Alex module smoke check.

Runs against the local Flask server and verifies the sales-critical Alex
communication contract without calling external AI models.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar


BASE_URL = os.environ.get("YAZKLINIK_TEST_BASE_URL", "https://127.0.0.1:5443")
USERNAME = os.environ.get("YAZKLINIK_TEST_USER", "doktor")
PASSWORD = os.environ.get("YAZKLINIK_TEST_PASSWORD", "1234")


class CheckError(RuntimeError):
    pass


def _opener() -> urllib.request.OpenerDirector:
    jar = CookieJar()
    handlers = [urllib.request.HTTPCookieProcessor(jar)]
    if BASE_URL.lower().startswith("https://"):
        handlers.append(
            urllib.request.HTTPSHandler(
                context=ssl._create_unverified_context()))
    return urllib.request.build_opener(*handlers)


def _request(opener: urllib.request.OpenerDirector, path: str, data=None, headers=None):
    url = BASE_URL.rstrip("/") + path
    body = None
    if data is not None:
        if isinstance(data, (dict, list)):
            body = json.dumps(data).encode("utf-8")
            headers = dict(headers or {})
            headers.setdefault("Content-Type", "application/json")
        elif isinstance(data, bytes):
            body = data
        else:
            body = str(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers or {})
    try:
        with opener.open(req, timeout=15) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        return exc.code, text


def _login(opener: urllib.request.OpenerDirector) -> None:
    form = urllib.parse.urlencode({
        "username": USERNAME,
        "password": PASSWORD,
    }).encode("utf-8")
    status, _ = _request(
        opener,
        "/giris",
        data=form,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    if status not in (200, 302):
        raise CheckError(f"LOGIN_FAILED status={status}")


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise CheckError(message)


def main() -> int:
    opener = _opener()
    _login(opener)

    routes = [
        "/ses-ve-alex",
        "/akilli-dialog",
        "/sessiz-alex",
        "/sesli-recete",
        "/yz-ses-cevir",
        "/ses-profilleri",
        "/mikrofon-tani",
        "/yz-telefon-diyalog",
    ]
    for route in routes:
        status, text = _request(opener, route)
        _assert(status == 200, f"ROUTE_FAILED {route} status={status}")
        _assert("ykVoiceAgent" in text, f"ALEX_AGENT_MISSING {route}")
        _assert("yk-alex-bar-emergency" in text, f"EMERGENCY_HANDLER_MISSING {route}")

    status, ses_html = _request(opener, "/ses-ve-alex")
    _assert(status == 200, "SES_VE_ALEX_FAILED")
    for token in (
        "ykVcAlexQa",
        "ykVcOpenSilentBar",
        "ykVcOpenVoiceBar",
        "ykVcHideBar",
        "ykVoiceSelfTest",
        "ykVoiceAgent.selfTest",
        "ykVoiceQuickAction",
        "ykVoiceTouchBridge",
        "data-yk-voice-touch",
        "data-yk-vc-action",
        "D250 2026-05-13 v8",
        "_handleEmergencyEvent",
        "pointerup",
        "touchend",
        "D250-quickbar-hardfix-1",
    ):
        _assert(token in ses_html, f"SES_ALEX_TOKEN_MISSING {token}")

    status, qa_text = _request(opener, "/api/alex/qa")
    _assert(status == 200, f"ALEX_QA_API_FAILED status={status}")
    qa = json.loads(qa_text)
    _assert(qa.get("ok") is True, f"ALEX_QA_NOT_OK {qa_text[:300]}")
    _assert("ykVoiceSelfTest" in qa.get("ui_contract", {}).get("required_dom_ids", []),
            "ALEX_QA_CONTRACT_MISSING_SELFTEST")

    status, status_text = _request(opener, "/api/akilli-dialog/status")
    _assert(status == 200, f"SMART_DIALOG_STATUS_FAILED status={status}")
    json.loads(status_text)

    status, command_text = _request(
        opener,
        "/api/sesli-komut/uygula",
        data={"message": "akilli dialog", "speak": 0},
    )
    _assert(status == 200, f"VOICE_COMMAND_ROUTE_FAILED status={status}")
    command_data = json.loads(command_text)
    _assert(command_data.get("ok") is True, f"VOICE_COMMAND_NOT_OK {command_text[:300]}")

    print("ALEX_D250_QUICK_CHECK_OK")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ALEX_D250_QUICK_CHECK_FAIL: {exc}")
        raise SystemExit(1)
