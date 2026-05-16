"""Local SIP bridge for Alex.

This file is intentionally standalone and uses only the Python standard library.
It registers a clinic extension to the PBX, answers incoming SIP calls, plays
Alex replies through RTP/PCMU, and exposes a tiny localhost control API for
YazKlinik voice commands such as "18 numarayi ara".

Secrets must come from config.env / environment. Do not hard-code SIP passwords.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import io
import json
import os
import random
import re
import secrets
import socket
import struct
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import warnings
import wave
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

warnings.filterwarnings("ignore", message=".*audioop.*", category=DeprecationWarning)
import audioop


ROOT = Path(__file__).resolve().parent
USER_AGENT = "YazKlinik-Alex-SIP/0.1"
CRLF = "\r\n"


def load_config_env(path: Optional[Path] = None) -> None:
    """Load KEY=VALUE lines without overriding already-set environment vars."""
    env_path = path or (ROOT / "config.env")
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key and key not in os.environ:
                os.environ[key] = value.strip()
    except Exception as exc:
        log(f"config.env okunamadi: {exc}")


def env(name: str, default: str = "") -> str:
    return str(os.environ.get(name, default) or default).strip()


def env_int(name: str, default: int) -> int:
    try:
        return int(env(name, str(default)))
    except Exception:
        return default


def env_bool(name: str, default: bool = False) -> bool:
    raw = env(name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on", "evet", "aktif"}


def log(message: str) -> None:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def now_ms() -> int:
    return int(time.time() * 1000)


def safe_extension(value: str) -> str:
    return re.sub(r"[^0-9*#+]", "", str(value or ""))[:16]


def sip_header_user(value: str) -> str:
    """Extract caller user/extension from a SIP From header."""
    text = str(value or "")
    match = re.search(r"sip:([^@;>]+)", text, flags=re.I)
    if not match:
        return safe_extension(text)
    raw = urllib.parse.unquote(match.group(1))
    return safe_extension(raw) or raw[:32]


def sip_header_display_name(value: str) -> str:
    """Best-effort display name extraction from a SIP From header."""
    text = str(value or "").strip()
    match = re.match(r'"([^"]+)"', text)
    if match:
        return match.group(1).strip()
    match = re.match(r"([^<;]+)<", text)
    if match:
        return match.group(1).strip().strip('"')
    return ""


def local_ip_for(remote_host: str, remote_port: int) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((remote_host, int(remote_port)))
        return sock.getsockname()[0]
    except Exception:
        return "0.0.0.0"
    finally:
        sock.close()


def parse_sip_message(data: bytes) -> Tuple[str, Dict[str, str], str]:
    text = data.decode("utf-8", errors="replace")
    head, _, body = text.partition("\r\n\r\n")
    lines = head.splitlines()
    start = lines[0].strip() if lines else ""
    headers: Dict[str, str] = {}
    current = ""
    for raw in lines[1:]:
        if raw.startswith((" ", "\t")) and current:
            headers[current] += " " + raw.strip()
            continue
        if ":" not in raw:
            continue
        key, value = raw.split(":", 1)
        current = key.strip().lower()
        headers[current] = value.strip()
    return start, headers, body


def header(headers: Dict[str, str], name: str, default: str = "") -> str:
    return headers.get(name.lower(), default)


def extract_tag(value: str) -> str:
    match = re.search(r"(?:^|;)tag=([^;\s]+)", value or "")
    return match.group(1) if match else ""


def extract_branch(via: str) -> str:
    match = re.search(r"(?:^|;)branch=([^;\s]+)", via or "")
    return match.group(1) if match else ""


def extract_cseq_method(cseq: str) -> str:
    parts = str(cseq or "").split()
    return parts[-1].upper() if parts else ""


def extract_cseq_number(cseq: str) -> str:
    parts = str(cseq or "").split()
    return parts[0] if parts else "1"


def parse_auth_header(value: str) -> Dict[str, str]:
    text = str(value or "").strip()
    if text.lower().startswith("digest "):
        text = text[7:].strip()
    out: Dict[str, str] = {}
    for match in re.finditer(r'(\w+)=("([^"]*)"|([^,\s]+))', text):
        out[match.group(1).lower()] = match.group(3) if match.group(3) is not None else match.group(4)
    return out


def md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8")).hexdigest()


def build_digest_authorization(
    username: str,
    password: str,
    method: str,
    uri: str,
    challenge_header: str,
    nonce_count: int = 1,
) -> str:
    challenge = parse_auth_header(challenge_header)
    realm = challenge.get("realm", "")
    nonce = challenge.get("nonce", "")
    opaque = challenge.get("opaque", "")
    qop_raw = challenge.get("qop", "")
    algorithm = challenge.get("algorithm", "MD5") or "MD5"
    qop = "auth" if "auth" in qop_raw.lower() else ""
    cnonce = secrets.token_hex(8)
    nc = f"{nonce_count:08x}"
    ha1 = md5_hex(f"{username}:{realm}:{password}")
    ha2 = md5_hex(f"{method}:{uri}")
    if qop:
        response = md5_hex(f"{ha1}:{nonce}:{nc}:{cnonce}:{qop}:{ha2}")
    else:
        response = md5_hex(f"{ha1}:{nonce}:{ha2}")
    parts = [
        f'Digest username="{username}"',
        f'realm="{realm}"',
        f'nonce="{nonce}"',
        f'uri="{uri}"',
        f'response="{response}"',
        f"algorithm={algorithm}",
    ]
    if opaque:
        parts.append(f'opaque="{opaque}"')
    if qop:
        parts.extend([f"qop={qop}", f"nc={nc}", f'cnonce="{cnonce}"'])
    return ", ".join(parts)


def make_sdp(local_ip: str, rtp_port: int) -> bytes:
    session_id = random.randint(100000, 999999)
    body = (
        "v=0\r\n"
        f"o=alex {session_id} {session_id} IN IP4 {local_ip}\r\n"
        "s=YazKlinik Alex\r\n"
        f"c=IN IP4 {local_ip}\r\n"
        "t=0 0\r\n"
        f"m=audio {rtp_port} RTP/AVP 0 8\r\n"
        "a=rtpmap:0 PCMU/8000\r\n"
        "a=rtpmap:8 PCMA/8000\r\n"
        "a=ptime:20\r\n"
        "a=sendrecv\r\n"
    )
    return body.encode("utf-8")


def parse_sdp_audio(body: str, fallback_ip: str) -> Tuple[str, int, int]:
    remote_ip = fallback_ip
    remote_port = 0
    payload = 0
    for line in str(body or "").splitlines():
        line = line.strip()
        if line.startswith("c=IN IP4 "):
            remote_ip = line.split()[-1].strip()
        elif line.startswith("m=audio "):
            parts = line.split()
            if len(parts) >= 2:
                try:
                    remote_port = int(parts[1])
                except Exception:
                    remote_port = 0
            for item in parts[3:]:
                if item in {"0", "8"}:
                    payload = int(item)
                    break
    return remote_ip, remote_port, payload


def build_wav(pcm16: bytes, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16)
    return buf.getvalue()


def wav_to_pcmu_8k(wav_bytes: bytes) -> bytes:
    with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        pcm = wf.readframes(wf.getnframes())
    if width != 2:
        pcm = audioop.lin2lin(pcm, width, 2)
        width = 2
    if channels > 1:
        pcm = audioop.tomono(pcm, width, 0.5, 0.5)
    if rate != 8000:
        pcm, _ = audioop.ratecv(pcm, width, 1, rate, 8000, None)
    return audioop.lin2ulaw(pcm, 2)


def pcmu_to_wav16k(packets: Iterable[bytes]) -> bytes:
    pcm8 = b"".join(audioop.ulaw2lin(bytes(p), 2) for p in packets if p)
    if not pcm8:
        return b""
    pcm16, _ = audioop.ratecv(pcm8, 2, 1, 8000, 16000, None)
    return build_wav(pcm16, 16000)


def pcma_to_wav16k(packets: Iterable[bytes]) -> bytes:
    pcm8 = b"".join(audioop.alaw2lin(bytes(p), 2) for p in packets if p)
    if not pcm8:
        return b""
    pcm16, _ = audioop.ratecv(pcm8, 2, 1, 8000, 16000, None)
    return build_wav(pcm16, 16000)


def multipart_post(url: str, field: str, filename: str, data: bytes, fields: Optional[Dict[str, str]] = None,
                   timeout: float = 30.0) -> bytes:
    boundary = "----yk_sip_" + secrets.token_hex(10)
    body = bytearray()
    for key, value in (fields or {}).items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
        body.extend(str(value).encode("utf-8"))
        body.extend(b"\r\n")
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
        "Content-Type: audio/wav\r\n\r\n".encode())
    body.extend(data)
    body.extend(f"\r\n--{boundary}--\r\n".encode())
    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


@dataclass
class AlexSIPConfig:
    enabled: bool
    pbx_host: str
    pbx_port: int
    domain: str
    extension: str
    password: str
    display_name: str
    local_ip: str
    local_port: int
    rtp_start_port: int
    control_host: str
    control_port: int
    register_expires: int
    auto_answer: bool
    greeting: str
    web_base_url: str
    webhook_secret: str
    whisper_url: str
    piper_url: str
    xtts_url: str
    tts_voice: str
    max_turns: int
    record_seconds: float
    silence_seconds: float

    @classmethod
    def from_env(cls) -> "AlexSIPConfig":
        pbx_host = env("YAZKLINIK_SIP_PBX_HOST", "192.168.1.250")
        pbx_port = env_int("YAZKLINIK_SIP_PBX_PORT", 5060)
        local_ip = env("YAZKLINIK_SIP_LOCAL_IP", "")
        if not local_ip:
            local_ip = local_ip_for(pbx_host, pbx_port)
        web_base = env(
            "YAZKLINIK_SIP_WEB_BASE_URL",
            env("YAZKLINIK_SERVER_URL", "https://127.0.0.1:5443"),
        ).rstrip("/")
        whisper_port = env_int("YAZKLINIK_WHISPER_SERVICE_PORT", 9000)
        piper_port = env_int("YAZKLINIK_PIPER_SERVICE_PORT", 9001)
        xtts_port = env_int("YAZKLINIK_XTTS_SERVICE_PORT", 9002)
        return cls(
            enabled=env_bool("YAZKLINIK_SIP_ENABLED", False),
            pbx_host=pbx_host,
            pbx_port=pbx_port,
            domain=env("YAZKLINIK_SIP_DOMAIN", pbx_host),
            extension=safe_extension(env("YAZKLINIK_SIP_EXTENSION", "19")),
            password=env("YAZKLINIK_SIP_PASSWORD", ""),
            display_name=env("YAZKLINIK_SIP_DISPLAY_NAME", "Alex"),
            local_ip=local_ip,
            local_port=env_int("YAZKLINIK_SIP_LOCAL_PORT", 5079),
            rtp_start_port=env_int("YAZKLINIK_SIP_RTP_PORT", 40190),
            control_host=env("YAZKLINIK_SIP_CONTROL_HOST", "127.0.0.1"),
            control_port=env_int("YAZKLINIK_SIP_CONTROL_PORT", 9019),
            register_expires=env_int("YAZKLINIK_SIP_REGISTER_EXPIRES", 300),
            auto_answer=env_bool("YAZKLINIK_SIP_AUTO_ANSWER", True),
            greeting=env(
                "YAZKLINIK_SIP_GREETING",
                "Merhaba doktorum. Ben Alex, dahili hattan sizi dinliyorum.",
            ),
            web_base_url=web_base,
            webhook_secret=env("YAZKLINIK_SIP_WEBHOOK_SECRET", "yazklinik-phone-2026"),
            whisper_url=env(
                "YAZKLINIK_SIP_WHISPER_URL",
                f"http://127.0.0.1:{whisper_port}/asr?output=text",
            ),
            piper_url=env("YAZKLINIK_SIP_PIPER_URL", f"http://127.0.0.1:{piper_port}/tts"),
            xtts_url=env("YAZKLINIK_SIP_XTTS_URL", f"http://127.0.0.1:{xtts_port}/tts"),
            tts_voice=env("YAZKLINIK_SIP_TTS_VOICE", "emel"),
            max_turns=env_int("YAZKLINIK_SIP_MAX_TURNS", 8),
            record_seconds=float(env("YAZKLINIK_SIP_RECORD_SECONDS", "5.5") or "5.5"),
            silence_seconds=float(env("YAZKLINIK_SIP_SILENCE_SECONDS", "1.2") or "1.2"),
        )


@dataclass
class CallState:
    call_id: str
    from_header: str
    to_header: str
    via: str
    cseq: str
    local_tag: str
    remote_tag: str = ""
    remote_ip: str = ""
    remote_rtp_port: int = 0
    remote_payload: int = 0
    local_rtp_port: int = 0
    direction: str = "incoming"
    active: bool = True
    history: list = field(default_factory=list)
    transcript_parts: list = field(default_factory=list)
    last_triage: dict = field(default_factory=dict)
    started_ms: int = field(default_factory=now_ms)


class RTPAudioSession:
    def __init__(self, cfg: AlexSIPConfig, call: CallState) -> None:
        self.cfg = cfg
        self.call = call
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((cfg.local_ip if cfg.local_ip != "0.0.0.0" else "", call.local_rtp_port))
        self.sock.settimeout(0.12)
        self.seq = random.randint(1, 60000)
        self.ts = random.randint(1, 200000)
        self.ssrc = random.randint(1, 0xFFFFFFFF)
        self.closed = False

    def close(self) -> None:
        self.closed = True
        try:
            self.sock.close()
        except Exception:
            pass

    def send_pcmu(self, pcmu: bytes) -> None:
        if not self.call.remote_ip or not self.call.remote_rtp_port:
            return
        remote = (self.call.remote_ip, int(self.call.remote_rtp_port))
        offset = 0
        frame_size = 160
        while offset < len(pcmu) and not self.closed and self.call.active:
            frame = pcmu[offset:offset + frame_size]
            if len(frame) < frame_size:
                frame += b"\xff" * (frame_size - len(frame))
            header = struct.pack("!BBHII", 0x80, 0x00, self.seq & 0xFFFF,
                                 self.ts & 0xFFFFFFFF, self.ssrc)
            try:
                self.sock.sendto(header + frame, remote)
            except Exception as exc:
                log(f"RTP send hata: {exc}")
                break
            self.seq = (self.seq + 1) & 0xFFFF
            self.ts = (self.ts + frame_size) & 0xFFFFFFFF
            offset += frame_size
            time.sleep(0.020)

    def send_wav(self, wav_bytes: bytes) -> None:
        if not wav_bytes:
            return
        try:
            self.send_pcmu(wav_to_pcmu_8k(wav_bytes))
        except Exception as exc:
            log(f"WAV->RTP hata: {exc}")

    def record_turn(self, seconds: float = 5.5, silence_seconds: float = 1.2) -> Tuple[bytes, int]:
        packets = []
        alaw_packets = []
        start = time.time()
        last_audio = 0.0
        seen_audio = False
        max_seconds = max(1.5, float(seconds or 5.5))
        silence_limit = max(0.6, float(silence_seconds or 1.2))
        while not self.closed and self.call.active and time.time() - start < max_seconds:
            try:
                data, _addr = self.sock.recvfrom(2048)
            except socket.timeout:
                if seen_audio and last_audio and time.time() - last_audio >= silence_limit:
                    break
                continue
            except Exception:
                break
            if len(data) < 12:
                continue
            payload_type = data[1] & 0x7F
            payload = data[12:]
            if payload_type == 0 and payload:
                packets.append(payload)
            elif payload_type == 8 and payload:
                alaw_packets.append(payload)
            else:
                continue
            if payload and any(b != 0xFF for b in payload):
                seen_audio = True
                last_audio = time.time()
        if packets:
            return pcmu_to_wav16k(packets), len(packets)
        if alaw_packets:
            return pcma_to_wav16k(alaw_packets), len(alaw_packets)
        return b"", 0


class SIPAlexBridge:
    def __init__(self, cfg: AlexSIPConfig) -> None:
        self.cfg = cfg
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((cfg.local_ip if cfg.local_ip != "0.0.0.0" else "", cfg.local_port))
        self.sock.settimeout(0.5)
        self.cseq = random.randint(100, 900)
        self.stop_event = threading.Event()
        self.status_lock = threading.Lock()
        self.registered = False
        self.last_register_ms = 0
        self.last_error = ""
        self.last_sip_code = 0
        self.active_calls: Dict[str, CallState] = {}
        self.rtp_port_next = cfg.rtp_start_port

    def public_status(self) -> Dict[str, object]:
        with self.status_lock:
            return {
                "ok": bool(self.registered),
                "enabled": self.cfg.enabled,
                "registered": self.registered,
                "extension": self.cfg.extension,
                "pbx": f"{self.cfg.pbx_host}:{self.cfg.pbx_port}",
                "local": f"{self.cfg.local_ip}:{self.cfg.local_port}",
                "control": f"{self.cfg.control_host}:{self.cfg.control_port}",
                "last_register_ms": self.last_register_ms,
                "last_sip_code": self.last_sip_code,
                "last_error": self.last_error,
                "active_calls": len([c for c in self.active_calls.values() if c.active]),
                "has_password": bool(self.cfg.password),
            }

    def set_error(self, message: str, code: int = 0) -> None:
        with self.status_lock:
            self.last_error = str(message or "")[:500]
            self.last_sip_code = int(code or 0)

    def next_cseq(self) -> int:
        self.cseq += 1
        return self.cseq

    def next_rtp_port(self) -> int:
        port = self.rtp_port_next
        self.rtp_port_next += 2
        if self.rtp_port_next > self.cfg.rtp_start_port + 200:
            self.rtp_port_next = self.cfg.rtp_start_port
        return port

    def send(self, message: bytes, target: Optional[Tuple[str, int]] = None) -> None:
        self.sock.sendto(message, target or (self.cfg.pbx_host, self.cfg.pbx_port))

    def build_request(
        self,
        method: str,
        uri: str,
        call_id: str,
        from_tag: str,
        to_uri: str,
        contact_user: Optional[str] = None,
        cseq: Optional[int] = None,
        extra_headers: Optional[Dict[str, str]] = None,
        body: bytes = b"",
        to_tag: str = "",
    ) -> bytes:
        cseq = cseq or self.next_cseq()
        branch = "z9hG4bK" + secrets.token_hex(8)
        from_uri = f"sip:{self.cfg.extension}@{self.cfg.domain}"
        contact_user = contact_user or self.cfg.extension
        to_value = f"<{to_uri}>"
        if to_tag:
            to_value += f";tag={to_tag}"
        headers = [
            f"{method} {uri} SIP/2.0",
            f"Via: SIP/2.0/UDP {self.cfg.local_ip}:{self.cfg.local_port};branch={branch};rport",
            "Max-Forwards: 70",
            f'From: "{self.cfg.display_name}" <{from_uri}>;tag={from_tag}',
            f"To: {to_value}",
            f"Call-ID: {call_id}",
            f"CSeq: {cseq} {method}",
            f"Contact: <sip:{contact_user}@{self.cfg.local_ip}:{self.cfg.local_port};transport=udp>",
            f"User-Agent: {USER_AGENT}",
            "Allow: INVITE, ACK, BYE, CANCEL, OPTIONS, REGISTER",
        ]
        for key, value in (extra_headers or {}).items():
            headers.append(f"{key}: {value}")
        if body:
            headers.extend(["Content-Type: application/sdp", f"Content-Length: {len(body)}", "", ""])
        else:
            headers.extend(["Content-Length: 0", "", ""])
        return CRLF.join(headers).encode("utf-8") + body

    def register_once(self, timeout: float = 4.0) -> Tuple[bool, str]:
        if not self.cfg.extension or not self.cfg.password:
            self.set_error("SIP extension/password eksik")
            return False, "extension/password eksik"
        start_ms = now_ms()
        call_id = secrets.token_hex(12) + f"@{self.cfg.local_ip}"
        from_tag = secrets.token_hex(6)
        uri = f"sip:{self.cfg.domain}"
        cseq = self.next_cseq()
        extra = {
            "Expires": str(self.cfg.register_expires),
        }
        req = self.build_request(
            "REGISTER", uri, call_id, from_tag, f"sip:{self.cfg.extension}@{self.cfg.domain}",
            cseq=cseq, extra_headers=extra)
        self.send(req)
        deadline = time.time() + timeout
        challenge = ""
        challenge_code = 0
        while time.time() < deadline:
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            start, headers, _body = parse_sip_message(data)
            if header(headers, "call-id") != call_id:
                self.handle_packet(data, addr)
                continue
            match = re.match(r"SIP/2.0\s+(\d+)", start)
            if not match:
                continue
            code = int(match.group(1))
            if code in {401, 407}:
                challenge = header(headers, "www-authenticate") or header(headers, "proxy-authenticate")
                challenge_code = code
                break
            if 200 <= code < 300:
                with self.status_lock:
                    self.registered = True
                    self.last_register_ms = now_ms() - start_ms
                    self.last_sip_code = code
                    self.last_error = ""
                return True, f"REGISTER OK {code}"
            if code >= 300:
                self.set_error(f"REGISTER yaniti {code}: {start}", code)
                return False, start
        if not challenge:
            self.set_error("REGISTER timeout/challenge yok")
            return False, "REGISTER timeout"
        auth_name = "Authorization" if challenge_code == 401 else "Proxy-Authorization"
        auth = build_digest_authorization(
            self.cfg.extension, self.cfg.password, "REGISTER", uri, challenge)
        cseq2 = self.next_cseq()
        extra = {
            "Expires": str(self.cfg.register_expires),
            auth_name: auth,
        }
        req2 = self.build_request(
            "REGISTER", uri, call_id, from_tag, f"sip:{self.cfg.extension}@{self.cfg.domain}",
            cseq=cseq2, extra_headers=extra)
        self.send(req2)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            start, headers, _body = parse_sip_message(data)
            if header(headers, "call-id") != call_id:
                self.handle_packet(data, addr)
                continue
            match = re.match(r"SIP/2.0\s+(\d+)", start)
            if not match:
                continue
            code = int(match.group(1))
            if 200 <= code < 300:
                with self.status_lock:
                    self.registered = True
                    self.last_register_ms = now_ms() - start_ms
                    self.last_sip_code = code
                    self.last_error = ""
                return True, f"REGISTER OK {code}"
            if code >= 300:
                self.set_error(f"REGISTER auth yaniti {code}: {start}", code)
                return False, start
        self.set_error("REGISTER auth timeout")
        return False, "REGISTER auth timeout"

    def response_for_request(
        self,
        code: int,
        reason: str,
        headers: Dict[str, str],
        body: bytes = b"",
        local_tag: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> bytes:
        to_value = header(headers, "to")
        if local_tag and "tag=" not in to_value:
            to_value += f";tag={local_tag}"
        lines = [
            f"SIP/2.0 {code} {reason}",
            f"Via: {header(headers, 'via')}",
            f"From: {header(headers, 'from')}",
            f"To: {to_value}",
            f"Call-ID: {header(headers, 'call-id')}",
            f"CSeq: {header(headers, 'cseq')}",
            f"User-Agent: {USER_AGENT}",
        ]
        for key, value in (extra_headers or {}).items():
            lines.append(f"{key}: {value}")
        if body:
            lines.extend(["Content-Type: application/sdp", f"Content-Length: {len(body)}", "", ""])
        else:
            lines.extend(["Content-Length: 0", "", ""])
        return CRLF.join(lines).encode("utf-8") + body

    def handle_packet(self, data: bytes, addr: Tuple[str, int]) -> None:
        try:
            start, headers, body = parse_sip_message(data)
            if not start:
                return
            if start.startswith("SIP/2.0"):
                return
            method = start.split()[0].upper()
            if method == "OPTIONS":
                self.send(self.response_for_request(200, "OK", headers), addr)
                return
            if method == "INVITE":
                self.handle_invite(headers, body, addr)
                return
            if method == "ACK":
                call = self.active_calls.get(header(headers, "call-id"))
                if call and call.direction == "incoming":
                    threading.Thread(target=self.run_call_audio, args=(call,), daemon=True).start()
                return
            if method == "BYE":
                call = self.active_calls.get(header(headers, "call-id"))
                if call:
                    call.active = False
                self.send(self.response_for_request(200, "OK", headers), addr)
                return
            if method == "CANCEL":
                call = self.active_calls.get(header(headers, "call-id"))
                if call:
                    call.active = False
                self.send(self.response_for_request(200, "OK", headers), addr)
                return
        except Exception as exc:
            self.set_error(f"packet hata: {exc}")
            log(traceback.format_exc())

    def handle_invite(self, headers: Dict[str, str], body: str, addr: Tuple[str, int]) -> None:
        call_id = header(headers, "call-id")
        if not call_id:
            return
        remote_ip, remote_port, payload = parse_sdp_audio(body, addr[0])
        if not remote_port:
            self.send(self.response_for_request(488, "Not Acceptable Here", headers), addr)
            return
        local_tag = secrets.token_hex(6)
        call = CallState(
            call_id=call_id,
            from_header=header(headers, "from"),
            to_header=header(headers, "to"),
            via=header(headers, "via"),
            cseq=header(headers, "cseq"),
            local_tag=local_tag,
            remote_tag=extract_tag(header(headers, "from")),
            remote_ip=remote_ip,
            remote_rtp_port=remote_port,
            remote_payload=payload,
            local_rtp_port=self.next_rtp_port(),
            direction="incoming",
        )
        self.active_calls[call_id] = call
        self.send(self.response_for_request(100, "Trying", headers), addr)
        self.send(self.response_for_request(180, "Ringing", headers, local_tag=local_tag), addr)
        if not self.cfg.auto_answer:
            return
        body_bytes = make_sdp(self.cfg.local_ip, call.local_rtp_port)
        self.send(self.response_for_request(
            200, "OK", headers, body=body_bytes, local_tag=local_tag,
            extra_headers={"Contact": f"<sip:{self.cfg.extension}@{self.cfg.local_ip}:{self.cfg.local_port};transport=udp>"}
        ), addr)
        log(f"Incoming call answered: call_id={call_id} rtp={remote_ip}:{remote_port}")

    def synthesize(self, text: str) -> bytes:
        text = re.sub(r"\s+", " ", str(text or "").strip())
        if not text:
            return b""
        payload = json.dumps({"text": text, "voice": self.cfg.tts_voice}).encode("utf-8")
        for url in (self.cfg.xtts_url, self.cfg.piper_url):
            try:
                req = urllib.request.Request(
                    url, data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST")
                with urllib.request.urlopen(req, timeout=45) as resp:
                    data = resp.read()
                if data.startswith(b"RIFF"):
                    return data
            except Exception as exc:
                log(f"TTS fallback: {url} -> {exc}")
        return b""

    def transcribe(self, wav_bytes: bytes) -> str:
        if not wav_bytes:
            return ""
        try:
            data = multipart_post(
                self.cfg.whisper_url, "audio_file", "sip-turn.wav", wav_bytes,
                fields={"language": "tr"}, timeout=60)
            return data.decode("utf-8", errors="replace").strip()
        except Exception as exc:
            log(f"Whisper hata: {exc}")
            return ""

    def ai_reply(self, text: str, caller: str, history: list) -> str:
        text = str(text or "").strip()
        if not text:
            return "Doktorum, sizi duyamadim. Tekrar eder misiniz?"
        payload = {
            "secret": self.cfg.webhook_secret,
            "transcript": text,
            "caller": caller or "sip",
            "history": history[-8:],
            "source": "sip_alex",
        }
        web_url = self.cfg.web_base_url.rstrip("/") + "/api/phone/ai-webhook"
        try:
            ctx = None
            if web_url.lower().startswith("https://127.0.0.1") or web_url.lower().startswith("https://localhost"):
                import ssl
                ctx = ssl._create_unverified_context()
            req = urllib.request.Request(
                web_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST")
            with urllib.request.urlopen(req, timeout=120, context=ctx) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            reply = str(data.get("reply") or "").strip()
            if reply:
                return reply
        except Exception as exc:
            log(f"AI webhook hata: {exc}")
        return "Doktorum, su an klinik zeka yaniti gecikti. Duyuyorum, tekrar deneyelim."

    def triage_call_turn(self, call: CallState, transcript: str) -> dict:
        """Run the telesekreter agent on the cumulative incoming transcript."""
        if not transcript.strip():
            return {}
        try:
            from yazklinik_telesekreter_agent import CallRecord, parse_call
            caller = sip_header_user(call.from_header) or call.from_header or call.direction
            caller_name = sip_header_display_name(call.from_header) or None
            duration_sec = max(0, int((now_ms() - call.started_ms) / 1000))
            record = CallRecord(
                caller_phone=caller,
                caller_name=caller_name,
                transcript=transcript,
                duration_sec=duration_sec,
            )
            triaged = parse_call(record)
            payload = asdict(triaged)
            call.last_triage = payload
            log(
                "Telesekreter triage: "
                f"intent={payload.get('intent')} "
                f"urgency={payload.get('urgency')} "
                f"phone={payload.get('extracted_phone') or payload.get('caller_phone')} "
                f"doctor_action={payload.get('requires_doctor_action')}"
            )
            return payload
        except Exception as exc:
            self.set_error(f"telesekreter triage hata: {exc}")
            log(f"Telesekreter triage hata: {exc}")
            return {}

    def run_call_audio(self, call: CallState) -> None:
        rtp = RTPAudioSession(self.cfg, call)
        try:
            wav = self.synthesize(self.cfg.greeting)
            if wav:
                rtp.send_wav(wav)
            caller = call.from_header or call.direction
            for idx in range(max(1, self.cfg.max_turns)):
                if not call.active:
                    break
                wav_in, packet_count = rtp.record_turn(
                    seconds=self.cfg.record_seconds,
                    silence_seconds=self.cfg.silence_seconds)
                if not wav_in or packet_count < 8:
                    reply = "Doktorum, sesinizi alamadim. Tekrar eder misiniz?"
                else:
                    text = self.transcribe(wav_in)
                    log(f"SIP STT turn={idx + 1} text={text!r}")
                    if not text:
                        reply = "Doktorum, sizi net duyamadim. Bir kez daha soyler misiniz?"
                    else:
                        call.transcript_parts.append(text)
                        triage = self.triage_call_turn(call, "\n".join(call.transcript_parts))
                        call.history.append({"role": "user", "content": text})
                        reply = self.ai_reply(text, caller=caller, history=call.history)
                        if triage and triage.get("intent") == "urgent":
                            reply = (
                                "Bu anlattiginiz acil olabilir. Lutfen beklemeden klinigi "
                                "veya 112'yi arayin. Ben notu doktor ekranina acil olarak isaretliyorum. "
                                + reply
                            )
                        call.history.append({"role": "assistant", "content": reply})
                wav_out = self.synthesize(reply)
                if wav_out:
                    rtp.send_wav(wav_out)
            if call.last_triage:
                log(f"Call loop ended: {call.call_id} triage={json.dumps(call.last_triage, ensure_ascii=False)}")
            else:
                log(f"Call loop ended: {call.call_id}")
        except Exception as exc:
            self.set_error(f"call audio hata: {exc}")
            log(traceback.format_exc())
        finally:
            call.active = False
            rtp.close()

    def originate(self, target_ext: str) -> Tuple[bool, str]:
        target = safe_extension(target_ext)
        if not target:
            return False, "Dahili numara gecersiz."
        call_id = secrets.token_hex(12) + f"@{self.cfg.local_ip}"
        from_tag = secrets.token_hex(6)
        local_rtp = self.next_rtp_port()
        uri = f"sip:{target}@{self.cfg.domain}"
        body = make_sdp(self.cfg.local_ip, local_rtp)
        cseq = self.next_cseq()
        req = self.build_request(
            "INVITE", uri, call_id, from_tag, f"sip:{target}@{self.cfg.domain}",
            cseq=cseq, body=body)
        self.send(req)
        challenge = ""
        challenge_code = 0
        to_tag = ""
        remote_ip = ""
        remote_port = 0
        deadline = time.time() + 25
        while time.time() < deadline:
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            start, headers, resp_body = parse_sip_message(data)
            if header(headers, "call-id") != call_id:
                self.handle_packet(data, addr)
                continue
            match = re.match(r"SIP/2.0\s+(\d+)", start)
            if not match:
                continue
            code = int(match.group(1))
            if code in {401, 407}:
                challenge = header(headers, "www-authenticate") or header(headers, "proxy-authenticate")
                challenge_code = code
                break
            if code in {100, 180, 183}:
                continue
            if 200 <= code < 300:
                to_tag = extract_tag(header(headers, "to"))
                remote_ip, remote_port, payload = parse_sdp_audio(resp_body, addr[0])
                self.send_ack(uri, call_id, from_tag, f"sip:{target}@{self.cfg.domain}",
                              cseq, to_tag)
                call = CallState(
                    call_id=call_id, from_header="", to_header=header(headers, "to"),
                    via="", cseq=str(cseq), local_tag=from_tag, remote_tag=to_tag,
                    remote_ip=remote_ip, remote_rtp_port=remote_port,
                    remote_payload=payload, local_rtp_port=local_rtp,
                    direction="outgoing")
                self.active_calls[call_id] = call
                threading.Thread(target=self.run_call_audio, args=(call,), daemon=True).start()
                return True, f"{target} araniyor; Alex gorusme hattina baglandi."
            if code >= 300:
                return False, f"Arama reddedildi: {start}"
        if challenge:
            auth_name = "Authorization" if challenge_code == 401 else "Proxy-Authorization"
            auth = build_digest_authorization(
                self.cfg.extension, self.cfg.password, "INVITE", uri, challenge)
            cseq2 = self.next_cseq()
            req2 = self.build_request(
                "INVITE", uri, call_id, from_tag, f"sip:{target}@{self.cfg.domain}",
                cseq=cseq2, extra_headers={auth_name: auth}, body=body)
            self.send(req2)
            deadline = time.time() + 35
            while time.time() < deadline:
                try:
                    data, addr = self.sock.recvfrom(65535)
                except socket.timeout:
                    continue
                start, headers, resp_body = parse_sip_message(data)
                if header(headers, "call-id") != call_id:
                    self.handle_packet(data, addr)
                    continue
                match = re.match(r"SIP/2.0\s+(\d+)", start)
                if not match:
                    continue
                code = int(match.group(1))
                if code in {100, 180, 183}:
                    continue
                if 200 <= code < 300:
                    to_tag = extract_tag(header(headers, "to"))
                    remote_ip, remote_port, payload = parse_sdp_audio(resp_body, addr[0])
                    self.send_ack(uri, call_id, from_tag, f"sip:{target}@{self.cfg.domain}",
                                  cseq2, to_tag)
                    call = CallState(
                        call_id=call_id, from_header="", to_header=header(headers, "to"),
                        via="", cseq=str(cseq2), local_tag=from_tag, remote_tag=to_tag,
                        remote_ip=remote_ip, remote_rtp_port=remote_port,
                        remote_payload=payload, local_rtp_port=local_rtp,
                        direction="outgoing")
                    self.active_calls[call_id] = call
                    threading.Thread(target=self.run_call_audio, args=(call,), daemon=True).start()
                    return True, f"{target} araniyor; Alex gorusme hattina baglandi."
                if code >= 300:
                    return False, f"Arama reddedildi: {start}"
        return False, "Arama zaman asimina ugradi veya santral cevap vermedi."

    def send_ack(self, uri: str, call_id: str, from_tag: str, to_uri: str,
                 invite_cseq: int, to_tag: str) -> None:
        msg = self.build_request(
            "ACK", uri, call_id, from_tag, to_uri,
            cseq=invite_cseq, to_tag=to_tag)
        self.send(msg)

    def serve(self) -> None:
        log(f"SIP bridge starting ext={self.cfg.extension} pbx={self.cfg.pbx_host}:{self.cfg.pbx_port} local={self.cfg.local_ip}:{self.cfg.local_port}")
        if not self.cfg.enabled:
            self.set_error("YAZKLINIK_SIP_ENABLED=1 degil")
        next_register = 0.0
        while not self.stop_event.is_set():
            if self.cfg.enabled and time.time() >= next_register:
                ok, msg = self.register_once(timeout=3.5)
                log(msg)
                next_register = time.time() + max(60, self.cfg.register_expires - 45)
                if not ok:
                    next_register = time.time() + 20
            try:
                data, addr = self.sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError as exc:
                if self.stop_event.is_set():
                    break
                self.set_error(f"SIP socket hata: {exc}")
                log(f"SIP socket hata, dinleme devam: {exc}")
                time.sleep(0.2)
                continue
            self.handle_packet(data, addr)


class ControlServer(threading.Thread):
    def __init__(self, bridge: SIPAlexBridge) -> None:
        super().__init__(daemon=True)
        self.bridge = bridge
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    def run(self) -> None:
        cfg = self.bridge.cfg
        self.sock.bind((cfg.control_host, cfg.control_port))
        self.sock.listen(20)
        log(f"Control API: http://{cfg.control_host}:{cfg.control_port}/status")
        while not self.bridge.stop_event.is_set():
            try:
                conn, _addr = self.sock.accept()
            except OSError:
                break
            threading.Thread(target=self.handle_conn, args=(conn,), daemon=True).start()

    def handle_conn(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(5)
            raw = b""
            while b"\r\n\r\n" not in raw and len(raw) < 65536:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                raw += chunk
            if not raw:
                return
            head, _, body = raw.partition(b"\r\n\r\n")
            first = head.splitlines()[0].decode("latin1", errors="replace")
            method, path, _version = (first.split() + ["", ""])[:3]
            content_length = 0
            for line in head.splitlines()[1:]:
                if line.lower().startswith(b"content-length:"):
                    try:
                        content_length = int(line.split(b":", 1)[1].strip())
                    except Exception:
                        content_length = 0
            while len(body) < content_length:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                body += chunk
            payload = {}
            if body:
                try:
                    payload = json.loads(body.decode("utf-8", errors="replace"))
                except Exception:
                    payload = {}
            result, code = self.route(method.upper(), path, payload)
            self.send_json(conn, result, code)
        except Exception as exc:
            try:
                self.send_json(conn, {"ok": False, "error": str(exc)}, 500)
            except Exception:
                pass
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def route(self, method: str, path: str, payload: Dict[str, object]) -> Tuple[Dict[str, object], int]:
        parsed = urllib.parse.urlsplit(path)
        query = urllib.parse.parse_qs(parsed.query)
        route = parsed.path.rstrip("/") or "/"
        if route in {"/", "/status"}:
            return self.bridge.public_status(), 200
        if route == "/register-test":
            ok, msg = self.bridge.register_once(timeout=5)
            data = self.bridge.public_status()
            data.update({"ok": ok, "message": msg})
            return data, 200 if ok else 502
        if route == "/call":
            if method not in {"POST", "GET"}:
                return {"ok": False, "error": "POST veya GET kullanin"}, 405
            target = str(
                payload.get("to")
                or payload.get("extension")
                or (query.get("to") or [""])[0]
                or (query.get("extension") or [""])[0]
                or ""
            )
            ok, msg = self.bridge.originate(target)
            return {"ok": ok, "message": msg, "to": safe_extension(target)}, 200 if ok else 502
        return {"ok": False, "error": "not found"}, 404

    @staticmethod
    def send_json(conn: socket.socket, payload: Dict[str, object], code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        reason = "OK" if code < 400 else "Error"
        headers = (
            f"HTTP/1.1 {code} {reason}\r\n"
            "Content-Type: application/json; charset=utf-8\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Cache-Control: no-store\r\n"
            "Connection: close\r\n\r\n"
        ).encode("ascii")
        conn.sendall(headers + body)


def sip_probe(cfg: AlexSIPConfig) -> int:
    bridge = SIPAlexBridge(cfg)
    try:
        ok, msg = bridge.register_once(timeout=6)
        print(json.dumps({**bridge.public_status(), "ok": ok, "message": msg},
                         ensure_ascii=False, indent=2))
        return 0 if ok else 2
    finally:
        bridge.stop_event.set()
        try:
            bridge.sock.close()
        except Exception:
            pass


def main(argv: Optional[list] = None) -> int:
    load_config_env()
    parser = argparse.ArgumentParser(description="YazKlinik Alex SIP bridge")
    parser.add_argument("--probe", action="store_true", help="Only test SIP REGISTER")
    parser.add_argument("--call", help="Originate a call to extension")
    args = parser.parse_args(argv)
    cfg = AlexSIPConfig.from_env()
    if args.probe:
        return sip_probe(cfg)
    bridge = SIPAlexBridge(cfg)
    control = ControlServer(bridge)
    control.start()
    if args.call:
        ok, msg = bridge.register_once(timeout=5)
        if not ok:
            print(msg)
            return 2
        ok, msg = bridge.originate(args.call)
        print(msg)
        return 0 if ok else 3
    try:
        bridge.serve()
    except KeyboardInterrupt:
        log("Stopping...")
    finally:
        bridge.stop_event.set()
        try:
            bridge.sock.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
