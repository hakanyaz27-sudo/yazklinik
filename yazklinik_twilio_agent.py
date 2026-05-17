"""Twilio Voice/SMS Bridge - Yazklinik Telesekreter + Geri Cagirma kopru.

Telesekreter ajaninin gercek bir telefon hatti uzerinden cagri almasi icin
Twilio webhook + SMS gonderme iskeleti. SIP bridge alternatifi (Twilio = bulut).

ENV gerekli:
    TWILIO_ACCOUNT_SID
    TWILIO_AUTH_TOKEN
    TWILIO_FROM_NUMBER  (orn +905551234567)

Kullanim:
    from yazklinik_twilio_agent import send_sms, twilio_voice_webhook_response
    send_sms("+90...", "Randevu hatirlatmaniz: yarin 10:00")

YazKlinik webhook (web layer'da):
    @app.route("/webhook/twilio/voice", methods=["POST"])
    def twilio_voice():
        from yazklinik_twilio_agent import twilio_voice_webhook_response
        return twilio_voice_webhook_response(request)

Asla:
    - Hasta verisi log'a yazma
    - Onaysiz SMS gonderme (KVKK acik riza zorunlu)
"""
from __future__ import annotations

import os
import urllib.parse
import urllib.request
import urllib.error
import base64
import json
from typing import Optional, Dict, Any


AGENT_VERSION = "2026.05.17-twilio"

DEFAULT_FROM = os.environ.get("TWILIO_FROM_NUMBER", "")
DEFAULT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
DEFAULT_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")


def _http_post_form(url: str, body: dict, auth: tuple) -> Dict[str, Any]:
    data = urllib.parse.urlencode(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    b64 = base64.b64encode(f"{auth[0]}:{auth[1]}".encode("ascii")).decode("ascii")
    req.add_header("Authorization", f"Basic {b64}")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as e:
        return {"ok": False, "error": f"HTTP {e.code}: {e.reason}",
                "body": e.read().decode("utf-8", errors="replace")[:200]}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}


def send_sms(to_number: str, message: str,
              account_sid: Optional[str] = None,
              auth_token: Optional[str] = None,
              from_number: Optional[str] = None) -> Dict[str, Any]:
    """SMS gonder. ENV varsa default kullan, yoksa parametreler zorunlu.
    Returns: Twilio response dict (sid, status) veya {"ok": False, "error":...}
    """
    sid = account_sid or DEFAULT_SID
    token = auth_token or DEFAULT_TOKEN
    frm = from_number or DEFAULT_FROM
    if not (sid and token and frm):
        return {"ok": False, "error": "TWILIO_ACCOUNT_SID/AUTH_TOKEN/FROM_NUMBER eksik"}
    url = f"https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json"
    return _http_post_form(url, {"To": to_number, "From": frm, "Body": message},
                            auth=(sid, token))


def twilio_voice_webhook_response(stt_text: str = "",
                                    forward_to: Optional[str] = None) -> str:
    """Twilio Voice webhook icin TwiML XML response.
    Gelen cagri:
        - forward_to verilirse: dial et
        - yoksa: <Record> + <Hangup>; sonra recording URL'i ile telesekreter ajani triyaj

    Donus: XML string (Flask: return Response(xml, mimetype='text/xml'))
    """
    if forward_to:
        return (f'<?xml version="1.0" encoding="UTF-8"?>'
                f'<Response><Dial>{forward_to}</Dial></Response>')
    return ('<?xml version="1.0" encoding="UTF-8"?>'
            '<Response>'
            '<Say language="tr-TR">Lutfen mesajinizi sinyal sesinden sonra birakin.</Say>'
            '<Record maxLength="120" transcribe="true" '
            'transcribeCallback="/webhook/twilio/transcribe" />'
            '<Hangup/></Response>')


def integration_health() -> Dict[str, Any]:
    return {
        "ok": True,
        "agent_version": AGENT_VERSION,
        "twilio_configured": bool(DEFAULT_SID and DEFAULT_TOKEN and DEFAULT_FROM),
        "from_number": DEFAULT_FROM if DEFAULT_FROM else "(set TWILIO_FROM_NUMBER)",
    }


if __name__ == "__main__":
    print(json.dumps(integration_health(), ensure_ascii=False, indent=2))
    print("\nTest SMS (kuru):")
    print(send_sms("+905551234567", "Test"))
    print("\nVoice TwiML ornek:")
    print(twilio_voice_webhook_response())
