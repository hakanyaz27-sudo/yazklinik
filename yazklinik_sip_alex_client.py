"""Local SIP bridge for Alex.

This file is intentionally standalone and uses only the Python standard library.
It registers a clinic extension to the PBX, answers incoming SIP calls, plays
Alex replies through RTP/PCMU, and exposes a tiny localhost control API for
YazKlinik voice commands such as "18 numarayi ara".

Secrets must come from config.env / environment. Do not hard-code SIP passwords.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import http.client
import io
import json
import os
import random
import re
import secrets
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import warnings
import wave
import ipaddress
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple

warnings.filterwarnings("ignore", message=".*audioop.*", category=DeprecationWarning)
import audioop


ROOT = Path(__file__).resolve().parent
USER_AGENT = "YazKlinik-Alex-SIP/0.1"
CRLF = "\r\n"
_INSTANCE_LOCK_HANDLE = None

try:
    from yazklinik_textfix import fix_mojibake_text
except Exception:
    def fix_mojibake_text(value):
        return value

try:
    from yazklinik_turkish_phone_text import (
        normalize_turkish_stt_text,
        normalize_turkish_tts_text,
    )
except Exception:
    def normalize_turkish_stt_text(value, **_kwargs):
        return str(fix_mojibake_text(value or "") or "")

    def normalize_turkish_tts_text(value, **_kwargs):
        return str(fix_mojibake_text(value or "") or "")

try:
    from yazklinik_sip_alex_guard import (
        build_sip_safe_response,
        public_guard_status,
    )
except Exception:
    def build_sip_safe_response(*_args, **_kwargs):
        return {"enabled": False, "block_webhook": False, "status": "sip_guard_missing"}

    def public_guard_status():
        return {
            "safe_mode": False,
            "autonomous_actions_disabled": False,
            "hangup_after_safe_reply": False,
            "version": "missing",
        }


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


def env_float(name: str, default: float) -> float:
    try:
        return float(env(name, str(default)))
    except Exception:
        return default


def env_bool(name: str, default: bool = False) -> bool:
    raw = env(name, "1" if default else "0").lower()
    return raw in {"1", "true", "yes", "on", "evet", "aktif"}


def read_web_setting(key: str, default: str = "") -> str:
    """Read one YazKlinik web setting directly from SQLite for SIP resilience."""
    db_path = env(
        "YAZKLINIK_DB_PATH",
        str(ROOT / "local_db" / "yazklinik_v68.sqlite3"),
    )
    if not key or not db_path or not os.path.exists(db_path):
        return default
    try:
        import sqlite3
        con = __import__("yazklinik_db_adapter").agent_connection(sqlite_path=db_path)  # PG-primary aware
        try:
            row = con.execute(
                "SELECT value FROM settings WHERE key=?",
                (key,),
            ).fetchone()
            if row and row[0] is not None:
                value = str(row[0]).strip()
                return value or default
        finally:
            con.close()
    except Exception:
        pass
    return default


def local_https_context_for(url: str):
    """Allow YazKlinik's own self-signed HTTPS cert for local SIP webhooks only."""
    parsed = urllib.parse.urlparse(str(url or ""))
    if parsed.scheme.lower() != "https":
        return None
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return None
    allow = host in {"localhost", "127.0.0.1", "::1"}
    if not allow:
        try:
            ip = ipaddress.ip_address(host)
            allow = ip.is_loopback or ip.is_private or ip.is_link_local
        except Exception:
            allow = host.endswith(".local")
    if not allow and env_bool("YAZKLINIK_SIP_ALLOW_SELF_SIGNED_WEBHOOK", True):
        # This client only posts to the configured YazKlinik webhook. In clinics
        # the server is normally a self-signed HTTPS address, sometimes exposed
        # through a public modem IP. Do not let certificate trust break Alex.
        allow = True
    if not allow:
        return None
    import ssl
    return ssl._create_unverified_context()


def ai_webhook_urls(web_base_url: str) -> list[str]:
    """Build ordered webhook targets for Alex SIP -> web handoff."""
    out = []
    seen = set()

    def _add(root: str) -> None:
        value = str(root or "").strip()
        if not value:
            return
        url = value.rstrip("/") + "/api/phone/ai-webhook"
        key = url.lower()
        if key in seen:
            return
        seen.add(key)
        out.append(url)

    _add(web_base_url)
    # D700 2026-05-19: HTTPS 5443 gecici down olsa bile HTTP 5052 ile devam et.
    _add(env("YAZKLINIK_SIP_WEBHOOK_FALLBACK_1", "http://127.0.0.1:5052"))
    _add(env("YAZKLINIK_SIP_WEBHOOK_FALLBACK_2", "https://127.0.0.1:5443"))

    extra = env("YAZKLINIK_SIP_WEBHOOK_FALLBACK_URLS", "")
    if extra:
        for part in str(extra).split(","):
            _add(part)
    return out


def acquire_single_instance_lock() -> bool:
    """Keep only one live SIP bridge, even if pythonw wrapper starts twice."""
    global _INSTANCE_LOCK_HANDLE
    lock_dir = ROOT / "runtime_state" / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    handle = open(lock_dir / "sip_alex.lock", "a+b")
    try:
        try:
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except ImportError:
            import fcntl
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        handle.seek(0)
        handle.truncate()
        handle.write(str(os.getpid()).encode("ascii", errors="ignore"))
        handle.flush()
        _INSTANCE_LOCK_HANDLE = handle
        return True
    except OSError:
        try:
            handle.close()
        except Exception:
            pass
        return False


def is_control_api_alive(control_host: str, control_port: int, timeout: float = 1.2) -> bool:
    """Best-effort probe for an already-running Alex SIP bridge control endpoint."""
    host = (control_host or "127.0.0.1").strip() or "127.0.0.1"
    port = int(control_port or 0)
    if port <= 0:
        return False
    url = f"http://{host}:{port}/status"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(getattr(resp, "status", 0) or 0) == 200
    except Exception:
        return False


def normalize_sip_tts_text(text: str) -> str:
    """Make SIP TTS text short, Turkish-friendly, and phone-line safe."""
    text = str(fix_mojibake_text(text or "") or "")
    try:
        text = normalize_turkish_tts_text(text)
    except Exception:
        pass
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    # D700 2026-05-18: Edge Emel bazen yabanci kelime/karakter gorunce o cumleyi
    # yabanci aksanli okuyor (kullanici "Rusca aksanli" diye sikayet etti).
    # Cyrillic / Greek / Arabic / Hebrew / CJK / Hiragana / Katakana bloklarini
    # tamamen sil. Yaygin Ingilizce filler kelimeleri Turkce'ye cevir veya at.
    text = re.sub(
        "["
        "Í°-Ï¿"  # Greek
        "Ğ€-Ó¿"  # Cyrillic
        "Ô€-Ô¯"  # Cyrillic Supplement
        "Ö-×¿"  # Hebrew
        "Ø€-Û¿"  # Arabic
        "Ü€-İ"  # Syriac
        "ã€-ã‚Ÿ"  # Hiragana
        "ã‚ -ãƒ¿"  # Katakana
        "ä¸€-é¿¿"  # CJK Unified
        "á¼€-á¿¿"  # Greek Extended
        "]+",
        "", text)
    _en_filler = [
        (r"\b(?:thank\s*you|thanks|thank\s*u)\b", "tesekkurler"),
        (r"\b(?:please)\b", "lutfen"),
        (r"\b(?:ok(?:ay)?)\b", "tamam"),
        (r"\b(?:yes)\b", "evet"),
        (r"\b(?:no)\b", "hayir"),
        (r"\b(?:hi|hello)\b", "merhaba"),
        (r"\b(?:bye|goodbye)\b", "gorusmek uzere"),
        (r"\b(?:the\s+first|the\s+second|the\s+third)\b", ""),
        (r"\b(?:one|two|three|four|five|six|seven|eight|nine|ten)\b", ""),
    ]
    for pat, repl in _en_filler:
        text = re.sub(pat, repl, text, flags=re.IGNORECASE)
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return ""
    replacements = (
        (r"\bAlex\b", "Aleks"),
        (r"\bALEX\b", "Aleks"),
        (r"\bOp\s*\.\s*Dr\s*\.?\s*", "Operator Doktor "),
        (r"\bop\s*\.\s*dr\s*\.?\s*", "Operator Doktor "),
        (r"\bUzm\s*\.\s*Dr\s*\.?\s*", "Uzman Doktor "),
        (r"\buzm\s*\.\s*dr\s*\.?\s*", "Uzman Doktor "),
        (r"\bProf\s*\.\s*Dr\s*\.?\s*", "Profesor Doktor "),
        (r"\bprof\s*\.\s*dr\s*\.?\s*", "Profesor Doktor "),
        (r"\bDr\s*\.?\s*", "Doktor "),
        (r"\bdr\s*\.?\s*", "Doktor "),
        (r"\bOp\s*\.\s*", "Operator "),
        (r"\bop\s*\.\s*", "Operator "),
        (r"\bHakan\s+YAZ\b", "Doktor"),
        (r"\bHakan\s+Yaz\b", "Doktor"),
        (r"\bUSG\b", "ultrason"),
        (r"\bYZ\b", "yapay zeka"),
        (r"\bLLM\b", "dil modeli"),
        (r"\bSIP\b", "telefon"),
        (r"\bD500\b", "de ucyuz"),
        (r"\b112\b", "yuz on iki"),
        (r"\b19\b", "on dokuz"),
        (r"\b18\b", "on sekiz"),
    )
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)
    text = re.sub(
        r"\b(Operator|Uzman|Profesor)\s+Doktor\s+Doktor\b",
        r"\1 Doktor",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"\bDoktor\s+Doktor\b", "Doktor", text,
                  flags=re.IGNORECASE)
    text = text.replace("/", " ")
    text = re.sub(r"([.!?]){2,}", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    max_len = max(80, min(env_int("YAZKLINIK_SIP_TTS_MAX_CHARS", 200), 320))
    if len(text) > max_len:
        text = text[:max_len].rsplit(" ", 1)[0].rstrip(" ,;:")
        if text and text[-1] not in ".!?":
            text += "."
    return text


def normalize_sip_stt_text(text: str) -> str:
    """Normalize Whisper transcript before routing it to clinic logic."""
    try:
        text = normalize_turkish_stt_text(text)
    except Exception:
        text = str(fix_mojibake_text(text or "") or "")
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _sip_stt_noise_text(text: str) -> bool:
    """Best-effort filter for subtitle/voicemail artifacts on SIP lines."""
    folded = normalize_sip_stt_text(text).lower()
    if not folded:
        return True
    # Very short crumbs are usually unusable over narrowband PBX audio.
    if len(folded) <= 2:
        return True
    markers = (
        "altyazi",
        "abone ol",
        "izlediginiz icin tesekkur",
        "sinyal sesinden sonra",
        "mesajinizi birakiniz",
        "gorusmeniz bitince",
        "kare tusuna basin",
        "thank you for watching",
        "subscribe",
    )
    return any(marker in folded for marker in markers)


def find_ffmpeg_exe() -> str:
    configured = env("YAZKLINIK_FFMPEG_PATH", "")
    candidates = [
        configured,
        str(ROOT / ".venv" / "Lib" / "site-packages" / "imageio_ffmpeg" / "binaries" / "ffmpeg.exe"),
        str(ROOT / "models" / "ffmpeg" / "extracted" / "ffmpeg-n7.1-latest-win64-gpl-shared-7.1" / "bin" / "ffmpeg.exe"),
        shutil.which("ffmpeg") or "",
    ]
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    try:
        import imageio_ffmpeg
        candidate = imageio_ffmpeg.get_ffmpeg_exe()
        if candidate and os.path.isfile(candidate):
            return candidate
    except Exception:
        pass
    return ""


def edge_neural_tts_wav(text: str) -> bytes:
    voice = env("YAZKLINIK_SIP_EDGE_VOICE", "tr-TR-EmelNeural")
    rate = env("YAZKLINIK_SIP_EDGE_RATE", "-8%")
    pitch = env("YAZKLINIK_SIP_EDGE_PITCH", "+0Hz")
    tts_timeout = max(8.0, min(env_float("YAZKLINIK_SIP_TTS_TIMEOUT", 24.0), 90.0))
    ffmpeg = find_ffmpeg_exe()
    if not ffmpeg:
        return b""
    try:
        import edge_tts
    except Exception:
        return b""

    async def collect_mp3() -> bytes:
        audio = bytearray()
        communicate = edge_tts.Communicate(text, voice=voice, rate=rate, pitch=pitch)
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio" and chunk.get("data"):
                audio.extend(chunk["data"])
        return bytes(audio)

    try:
        mp3 = asyncio.run(asyncio.wait_for(collect_mp3(), timeout=tts_timeout))
        if not mp3:
            return b""
        with tempfile.TemporaryDirectory(prefix="yk_sip_tts_") as tmp:
            mp3_path = os.path.join(tmp, "in.mp3")
            wav_path = os.path.join(tmp, "out.wav")
            with open(mp3_path, "wb") as fh:
                fh.write(mp3)
            subprocess.run(
                [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", mp3_path,
                 "-ac", "1", "-ar", "16000", "-f", "wav", wav_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=tts_timeout,
            )
            with open(wav_path, "rb") as fh:
                wav = fh.read()
        return wav if wav.startswith(b"RIFF") else b""
    except Exception as exc:
        log(f"Edge Neural TTS fallback: {exc}")
        return b""


def cached_edge_neural_tts_wav(text: str) -> bytes:
    """Cache Edge Neural WAVs so live SIP calls do not fall back to old voices."""
    voice = env("YAZKLINIK_SIP_EDGE_VOICE", "tr-TR-EmelNeural")
    rate = env("YAZKLINIK_SIP_EDGE_RATE", "-8%")
    pitch = env("YAZKLINIK_SIP_EDGE_PITCH", "+0Hz")
    key_src = "\n".join([voice, rate, pitch, text])
    digest = hashlib.sha256(key_src.encode("utf-8", errors="replace")).hexdigest()[:24]
    cache_dir = ROOT / "runtime_state" / "sip_tts_cache"
    cache_path = cache_dir / f"edge_{digest}.wav"
    try:
        if cache_path.exists():
            data = cache_path.read_bytes()
            if data.startswith(b"RIFF"):
                return data
    except Exception:
        pass
    data = edge_neural_tts_wav(text)
    if data.startswith(b"RIFF"):
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            cache_path.write_bytes(data)
        except Exception:
            pass
    return data


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


def sip_uri_from_header(value: str) -> str:
    """Extract the first sip: URI from a From/To header."""
    text = str(value or "")
    match = re.search(r"<\s*(sip:[^>]+)\s*>", text, flags=re.I)
    if not match:
        match = re.search(r"\b(sip:[^\s;>]+)", text, flags=re.I)
    return match.group(1).strip() if match else ""


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


def sip_silence_closing_text(silence_seconds: float = 15.0) -> str:
    """Polite closing line before Alex hangs up after prolonged silence."""
    try:
        hour = datetime.now().hour
        greeting = "iyi akÅŸamlar" if hour >= 18 or hour < 6 else "iyi gÃ¼nler"
    except Exception:
        greeting = "iyi gÃ¼nler"
    try:
        seconds = max(5, int(round(float(silence_seconds or 15.0))))
    except Exception:
        seconds = 15
    if seconds == 20:
        spoken = "yirmi saniyedir"
    else:
        spoken = f"{seconds} saniyedir"
    return (
        f"Doktorum, {spoken} ses alamÄ±yorum. "
        f"GÃ¶rÃ¼ÅŸmeyi kapatÄ±yorum, {greeting}."
    )

def local_ip_for(remote_host: str, remote_port: int) -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((remote_host, int(remote_port)))
        return sock.getsockname()[0]
    except Exception:
        return "0.0.0.0"
    finally:
        sock.close()


def local_ip_is_usable(local_ip: str) -> bool:
    value = (local_ip or "").strip()
    if not value or value == "0.0.0.0":
        return True
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.bind((value, 0))
        return True
    except OSError:
        return False
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


def preferred_audio_payload() -> int:
    codec = env("YAZKLINIK_SIP_CODEC", "pcma").strip().lower()
    if codec in {"pcma", "alaw", "a-law", "g711a", "g.711a", "8"}:
        return 8
    return 0


def choose_audio_payload(offered: Iterable[int]) -> int:
    offered_set = set()
    for item in offered or []:
        try:
            payload = int(item)
        except Exception:
            continue
        if payload in {0, 8}:
            offered_set.add(payload)
    preferred = preferred_audio_payload()
    if preferred in offered_set:
        return preferred
    if 8 in offered_set:
        return 8
    if 0 in offered_set:
        return 0
    return preferred


def make_sdp(local_ip: str, rtp_port: int) -> bytes:
    session_id = random.randint(100000, 999999)
    payloads = "8 0" if preferred_audio_payload() == 8 else "0 8"
    # D700 2026-05-18: PBX'in DTMF tuslarini RFC 4733 (RTP payload 101) ile
    # gondermesi icin telephone-event/8000 advertise et. PBX bu varsa BIP
    # gondermek yerine event packet'i yollar; record_turn parse ediyor.
    body = (
        "v=0\r\n"
        f"o=alex {session_id} {session_id} IN IP4 {local_ip}\r\n"
        "s=YazKlinik Alex\r\n"
        f"c=IN IP4 {local_ip}\r\n"
        "t=0 0\r\n"
        f"m=audio {rtp_port} RTP/AVP {payloads} 101\r\n"
        "a=rtpmap:0 PCMU/8000\r\n"
        "a=rtpmap:8 PCMA/8000\r\n"
        "a=rtpmap:101 telephone-event/8000\r\n"
        "a=fmtp:101 0-15\r\n"
        "a=ptime:20\r\n"
        "a=sendrecv\r\n"
    )
    return body.encode("utf-8")


def parse_sdp_audio(body: str, fallback_ip: str) -> Tuple[str, int, int]:
    remote_ip = fallback_ip
    remote_port = 0
    offered_payloads = []
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
                    offered_payloads.append(int(item))
    return remote_ip, remote_port, choose_audio_payload(offered_payloads)


def build_wav(pcm16: bytes, sample_rate: int = 16000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16)
    return buf.getvalue()


def boost_wav_for_stt(wav_bytes: bytes) -> bytes:
    """Apply conservative RMS gain for quiet SIP turns before STT retry."""
    if not wav_bytes:
        return b""
    try:
        target_rms = max(
            800,
            min(env_int("YAZKLINIK_SIP_STT_TARGET_RMS", 1800), 6000),
        )
        max_gain = max(
            1.2,
            min(env_float("YAZKLINIK_SIP_STT_MAX_GAIN", 5.5), 12.0),
        )
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            channels = int(wf.getnchannels() or 1)
            width = int(wf.getsampwidth() or 2)
            rate = int(wf.getframerate() or 16000)
            pcm = wf.readframes(wf.getnframes())
        if not pcm:
            return b""
        if width != 2:
            pcm = audioop.lin2lin(pcm, width, 2)
            width = 2
        if channels > 1:
            pcm = audioop.tomono(pcm, width, 0.5, 0.5)
        if rate != 16000:
            pcm, _ = audioop.ratecv(pcm, width, 1, rate, 16000, None)
            rate = 16000
        rms = audioop.rms(pcm, width)
        if rms <= 0:
            return b""
        gain = min(max_gain, float(target_rms) / float(max(1, rms)))
        if gain <= 1.08:
            return b""
        boosted = audioop.mul(pcm, width, gain)
        return build_wav(boosted, rate)
    except Exception:
        return b""


# Spoken when live TTS fails mid-call so the caller never hears dead air.
TTS_FALLBACK_NOTICE = (
    "Teknik bir aksaklik nedeniyle sesli yanit veremiyorum. "
    "Sizi klinik ekibine aktariyorum, lutfen kliniyi tekrar arayin."
)


def tone_wav(seconds: float = 1.1, freq: int = 440, sample_rate: int = 16000) -> bytes:
    """Last-resort audible tone. Better an alive-sounding line than silence."""
    import math
    frames = int(sample_rate * max(0.2, float(seconds)))
    pcm = bytearray()
    for n in range(frames):
        # gentle fade so it does not click; low amplitude to avoid harshness
        env_gain = min(1.0, n / 800.0, (frames - n) / 800.0)
        sample = int(6000 * env_gain * math.sin(2.0 * math.pi * freq * (n / sample_rate)))
        pcm += struct.pack("<h", sample)
    return build_wav(bytes(pcm), sample_rate)


def wav_to_pcm16_8k(wav_bytes: bytes) -> bytes:
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
    return pcm


def wav_to_pcmu_8k(wav_bytes: bytes) -> bytes:
    pcm = wav_to_pcm16_8k(wav_bytes)
    return audioop.lin2ulaw(pcm, 2)


def wav_to_pcma_8k(wav_bytes: bytes) -> bytes:
    pcm = wav_to_pcm16_8k(wav_bytes)
    return audioop.lin2alaw(pcm, 2)


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
    silence_hangup_seconds: float

    @classmethod
    def from_env(cls) -> "AlexSIPConfig":
        pbx_host = env("YAZKLINIK_SIP_PBX_HOST", "192.168.1.250")
        pbx_port = env_int("YAZKLINIK_SIP_PBX_PORT", 5060)
        configured_local_ip = env("YAZKLINIK_SIP_LOCAL_IP", "").strip()
        local_ip = configured_local_ip
        if configured_local_ip and not local_ip_is_usable(configured_local_ip):
            local_ip = local_ip_for(pbx_host, pbx_port)
            log(
                "SIP local IP Windows uzerinde yok; otomatik secildi: "
                f"{configured_local_ip} -> {local_ip}"
            )
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
                "Merhaba doktorum. Ben Aleks. Sizi net duyuyorum. Buyurun.",
            ),
            web_base_url=web_base,
            webhook_secret=env(
                "YAZKLINIK_SIP_WEBHOOK_SECRET",
                read_web_setting("ai_phone_webhook_secret",
                                 "yazklinik-phone-2026"),
            ),
            whisper_url=env(
                "YAZKLINIK_SIP_WHISPER_URL",
                f"http://127.0.0.1:{whisper_port}/asr?output=text",
            ),
            piper_url=env("YAZKLINIK_SIP_PIPER_URL", f"http://127.0.0.1:{piper_port}/tts"),
            xtts_url=env("YAZKLINIK_SIP_XTTS_URL", f"http://127.0.0.1:{xtts_port}/tts"),
            tts_voice=env("YAZKLINIK_SIP_TTS_VOICE", "emel"),
            max_turns=max(1, min(env_int("YAZKLINIK_SIP_MAX_TURNS", 8), 16)),
            record_seconds=max(
                2.5, min(env_float("YAZKLINIK_SIP_RECORD_SECONDS", 5.0), 8.0)),
            silence_seconds=max(
                0.6, min(env_float("YAZKLINIK_SIP_SILENCE_SECONDS", 1.0), 2.0)),
            silence_hangup_seconds=max(
                8.0, min(env_float("YAZKLINIK_SIP_SILENCE_HANGUP_SECONDS", 15.0), 60.0)),
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
    last_ai_status: str = ""
    last_ai_terminal: bool = False
    last_ai_should_hangup: bool = False
    started_ms: int = field(default_factory=now_ms)
    audio_started: bool = False
    # D700 2026-05-18: DTMF (telefon tusu) buffer - RFC 4733 (RTP payload 101)
    # veya SIP INFO ile gelen tuslar burada birikir, webhook payload'una eklenir.
    dtmf_digits: str = ""
    _last_dtmf_ts: int = -1


class RTPAudioSession:
    def __init__(self, cfg: AlexSIPConfig, call: CallState) -> None:
        self.cfg = cfg
        self.call = call
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        bind_host = cfg.local_ip if cfg.local_ip != "0.0.0.0" else ""
        try:
            self.sock.bind((bind_host, call.local_rtp_port))
        except OSError as exc:
            if bind_host:
                log(
                    "RTP bind fallback: "
                    f"{bind_host}:{call.local_rtp_port} -> 0.0.0.0 "
                    f"({type(exc).__name__}: {exc})"
                )
                self.sock.bind(("", call.local_rtp_port))
            else:
                raise
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

    def send_rtp_payload(self, encoded: bytes, payload_type: int, codec_name: str) -> None:
        if not self.call.remote_ip or not self.call.remote_rtp_port:
            return
        remote = (self.call.remote_ip, int(self.call.remote_rtp_port))
        offset = 0
        frame_size = 160
        payload_type = int(payload_type or 0) & 0x7F
        log(
            f"RTP send start codec={codec_name} payload={payload_type} "
            f"bytes={len(encoded)} remote={remote[0]}:{remote[1]}"
        )
        while offset < len(encoded) and not self.closed and self.call.active:
            frame = encoded[offset:offset + frame_size]
            if len(frame) < frame_size:
                pad = b"\xd5" if payload_type == 8 else b"\xff"
                frame += pad * (frame_size - len(frame))
            header = struct.pack("!BBHII", 0x80, payload_type, self.seq & 0xFFFF,
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
            payload_type = choose_audio_payload([self.call.remote_payload])
            if payload_type == 8:
                self.send_rtp_payload(wav_to_pcma_8k(wav_bytes), 8, "PCMA")
            else:
                self.send_rtp_payload(wav_to_pcmu_8k(wav_bytes), 0, "PCMU")
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
            # D700 2026-05-18: RFC 4733 DTMF event (payload type 101) - hasta
            # telefon tusladiginda payload[0]=event byte (0-15 -> 0123456789*#ABCD).
            # Ayni event multiple packet ile gelir (duration boyunca); timestamp
            # ile dedupe et.
            if payload_type == 101 and len(payload) >= 4:
                try:
                    event = payload[0]
                    ts = int.from_bytes(data[4:8], "big")
                    if ts != self.call._last_dtmf_ts and event < 16:
                        digit = "0123456789*#ABCD"[event]
                        self.call.dtmf_digits += digit
                        self.call._last_dtmf_ts = ts
                        log(
                            f"DTMF (RTP 4733): call={self.call.call_id} "
                            f"digit={digit} buffer={self.call.dtmf_digits}"
                        )
                except Exception:
                    pass
                continue
            if payload_type == 0 and payload:
                packets.append(payload)
            elif payload_type == 8 and payload:
                alaw_packets.append(payload)
            else:
                continue
            silence_bytes = {0xD5, 0x55} if payload_type == 8 else {0xFF, 0x7F}
            if payload and any(b not in silence_bytes for b in payload):
                seen_audio = True
                last_audio = time.time()
        if alaw_packets and len(alaw_packets) >= len(packets):
            log(f"RTP record codec=PCMA packets={len(alaw_packets)}")
            return pcma_to_wav16k(alaw_packets), len(alaw_packets)
        if packets:
            log(f"RTP record codec=PCMU packets={len(packets)}")
            return pcmu_to_wav16k(packets), len(packets)
        if alaw_packets:
            log(f"RTP record codec=PCMA packets={len(alaw_packets)}")
            return pcma_to_wav16k(alaw_packets), len(alaw_packets)
        return b"", 0


class SIPAlexBridge:
    def __init__(self, cfg: AlexSIPConfig) -> None:
        self.cfg = cfg
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            try:
                self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            except OSError:
                pass
        else:
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        bind_host = cfg.local_ip if cfg.local_ip != "0.0.0.0" else ""
        try:
            self.sock.bind((bind_host, cfg.local_port))
        except OSError as exc:
            if bind_host:
                fallback_ip = local_ip_for(cfg.pbx_host, cfg.pbx_port)
                fallback_host = fallback_ip if fallback_ip != "0.0.0.0" else ""
                log(
                    "SIP bind fallback: "
                    f"{bind_host}:{cfg.local_port} -> {fallback_ip}:{cfg.local_port} "
                    f"({type(exc).__name__}: {exc})"
                )
                self.cfg.local_ip = fallback_ip
                self.sock.bind((fallback_host, cfg.local_port))
            else:
                raise
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
        self.tts_healthy: Optional[bool] = None
        self.stt_healthy: Optional[bool] = None
        self._fallback_notice_wav: bytes = b""
        self._tone_cache: bytes = b""

    def cleanup_calls(self, max_age_sec: Optional[int] = None) -> int:
        """Drop finished or stale call objects from the public status map."""
        if max_age_sec is None:
            max_age_sec = int(os.environ.get("YAZKLINIK_SIP_CALL_TTL_SEC", "900"))
        cutoff_ms = now_ms() - max(30, int(max_age_sec)) * 1000
        removed = 0
        for call_id, call in list(self.active_calls.items()):
            if (not call.active) or call.started_ms < cutoff_ms:
                call.active = False
                self.active_calls.pop(call_id, None)
                removed += 1
        return removed

    def public_status(self) -> Dict[str, object]:
        self.cleanup_calls()
        with self.status_lock:
            active_count = sum(1 for c in self.active_calls.values() if c.active)
            return {
                "ok": bool(self.registered),
                "enabled": self.cfg.enabled,
                "registered": self.registered,
                "extension": self.cfg.extension,
                "pid": os.getpid(),
                "pbx": f"{self.cfg.pbx_host}:{self.cfg.pbx_port}",
                "local": f"{self.cfg.local_ip}:{self.cfg.local_port}",
                "control": f"{self.cfg.control_host}:{self.cfg.control_port}",
                "last_register_ms": self.last_register_ms,
                "last_sip_code": self.last_sip_code,
                "last_error": self.last_error,
                "active_calls": active_count,
                "has_password": bool(self.cfg.password),
                "tts_engine": env("YAZKLINIK_SIP_TTS_ENGINE", "edge").lower(),
                "edge_voice": env("YAZKLINIK_SIP_EDGE_VOICE", "tr-TR-EmelNeural"),
                "legacy_tts_fallback": env_bool("YAZKLINIK_SIP_TTS_ALLOW_LEGACY_FALLBACK", False),
                "tts_healthy": self.tts_healthy,
                "tts_fallback_ready": bool(self._fallback_notice_wav),
                "stt_healthy": self.stt_healthy,
                "sip_codec": "PCMA" if preferred_audio_payload() == 8 else "PCMU",
                "record_seconds": self.cfg.record_seconds,
                "silence_seconds": self.cfg.silence_seconds,
                "silence_hangup_seconds": self.cfg.silence_hangup_seconds,
                "guard": public_guard_status(),
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
                if call and call.direction == "incoming" and not call.audio_started:
                    call.audio_started = True
                    threading.Thread(target=self.run_call_audio, args=(call,), daemon=True).start()
                return
            # D700 2026-05-18: SIP INFO method - bazi PBX'ler DTMF'i RFC 4733
            # yerine SIP INFO body'sinde 'Signal=X' veya 'd=X' formatinda gonderir.
            # RTP DTMF zaten record_turn'de parse ediliyor; bu yedek yol.
            if method == "INFO":
                call = self.active_calls.get(header(headers, "call-id"))
                self.send(self.response_for_request(200, "OK", headers), addr)
                if call:
                    try:
                        m = re.search(
                            r"(?:Signal|d|Digit)\s*=\s*([0-9*#A-D])",
                            body or "", re.IGNORECASE)
                        if m:
                            digit = m.group(1).upper()
                            call.dtmf_digits += digit
                            log(
                                f"DTMF (SIP INFO): call={call.call_id} "
                                f"digit={digit} buffer={call.dtmf_digits}"
                            )
                    except Exception:
                        pass
                return
            if method == "BYE":
                call = self.active_calls.get(header(headers, "call-id"))
                if call:
                    call.active = False
                    self.active_calls.pop(call.call_id, None)
                self.send(self.response_for_request(200, "OK", headers), addr)
                return
            if method == "CANCEL":
                call = self.active_calls.get(header(headers, "call-id"))
                if call:
                    call.active = False
                    self.active_calls.pop(call.call_id, None)
                self.send(self.response_for_request(200, "OK", headers), addr)
                return
        except Exception as exc:
            self.set_error(f"packet hata: {exc}")
            log(traceback.format_exc())

    def handle_invite(self, headers: Dict[str, str], body: str, addr: Tuple[str, int]) -> None:
        call_id = header(headers, "call-id")
        if not call_id:
            return
        # Field stability: one active incoming conversation at a time.
        if not env_bool("YAZKLINIK_SIP_ALLOW_CONCURRENT_CALLS", False):
            for existing in list(self.active_calls.values()):
                if (
                    existing
                    and existing.active
                    and existing.direction == "incoming"
                    and existing.call_id != call_id
                ):
                    self.send(
                        self.response_for_request(
                            486, "Busy Here", headers
                        ),
                        addr,
                    )
                    log(
                        "Incoming INVITE rejected (busy): "
                        f"call_id={call_id} active_call={existing.call_id}"
                    )
                    return
        remote_ip, remote_port, payload = parse_sdp_audio(body, addr[0])
        if not remote_port:
            self.send(self.response_for_request(488, "Not Acceptable Here", headers), addr)
            return
        existing = self.active_calls.get(call_id)
        if existing and existing.active:
            existing.remote_ip = remote_ip
            existing.remote_rtp_port = remote_port
            existing.remote_payload = payload
            body_bytes = make_sdp(self.cfg.local_ip, existing.local_rtp_port)
            self.send(self.response_for_request(
                200, "OK", headers, body=body_bytes, local_tag=existing.local_tag,
                extra_headers={"Contact": f"<sip:{self.cfg.extension}@{self.cfg.local_ip}:{self.cfg.local_port};transport=udp>"}
            ), addr)
            log(
                f"Duplicate INVITE refreshed: call_id={call_id} "
                f"rtp={remote_ip}:{remote_port} payload={payload}"
            )
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
        log(
            f"Incoming call answered: call_id={call_id} "
            f"rtp={remote_ip}:{remote_port} payload={payload}"
        )

    def _engine_synthesize(self, text: str) -> bytes:
        """Raw TTS engine attempt. Returns b'' on failure (no safety net).

        Use this for health checks and probes. Live calls must use synthesize(),
        which never lets a non-empty reply turn into dead air.
        """
        text = normalize_sip_tts_text(text)
        if not text:
            return b""
        engine = env("YAZKLINIK_SIP_TTS_ENGINE", "edge").lower()
        if engine in {"edge", "edge_tts", "neural", "emel_neural"}:
            data = cached_edge_neural_tts_wav(text)
            if data:
                log(
                    "SIP TTS edge ok: "
                    f"voice={env('YAZKLINIK_SIP_EDGE_VOICE', 'tr-TR-EmelNeural')} "
                    f"chars={len(text)} bytes={len(data)}"
                )
                return data
            log("SIP TTS edge failed; legacy fallback disabled unless explicitly enabled.")
            if not env_bool("YAZKLINIK_SIP_TTS_ALLOW_LEGACY_FALLBACK", False):
                return b""
        payload = json.dumps({"text": text, "voice": self.cfg.tts_voice}).encode("utf-8")
        tts_timeout = max(8.0, min(env_float("YAZKLINIK_SIP_TTS_TIMEOUT", 24.0), 90.0))
        for url in (self.cfg.xtts_url, self.cfg.piper_url):
            try:
                req = urllib.request.Request(
                    url, data=payload,
                    headers={"Content-Type": "application/json"},
                    method="POST")
                with urllib.request.urlopen(req, timeout=tts_timeout) as resp:
                    data = resp.read()
                if data.startswith(b"RIFF"):
                    return data
            except Exception as exc:
                log(f"TTS fallback: {url} -> {exc}")
        return b""

    def _fallback_audio(self) -> bytes:
        """Audible bytes for a failed turn: cached spoken notice, else a tone."""
        notice = self._fallback_notice_wav
        if isinstance(notice, (bytes, bytearray)) and bytes(notice[:4]) == b"RIFF":
            return bytes(notice)
        if not self._tone_cache:
            try:
                self._tone_cache = tone_wav()
            except Exception as exc:
                log(f"SIP TTS tone fallback uretilemedi: {exc}")
                self._tone_cache = b""
        return self._tone_cache

    def synthesize(self, text: str) -> bytes:
        """Live-call TTS. For non-empty text this never returns silence: on
        engine failure it plays a spoken notice (or a tone) and marks TTS
        unhealthy, so a broken engine is observable instead of dead air.
        """
        clean = normalize_sip_tts_text(text)
        if not clean:
            return b""
        data = self._engine_synthesize(clean)
        if data:
            self.tts_healthy = True
            return data
        with self.status_lock:
            self.tts_healthy = False
            self.last_error = "TTS motoru ses uretemedi; fallback bildirim calindi"
        log("SIP TTS FAILED -> fallback notice/tone calindi (TTS UNHEALTHY)")
        return self._fallback_audio()

    def tts_health_check(self) -> bool:
        """Probe the real engine, cache a spoken fallback notice, log LOUD on
        failure. Called at startup so a silent phone line is never a surprise.
        """
        greeting_ok = bool(self._engine_synthesize(self.cfg.greeting))
        notice = self._engine_synthesize(TTS_FALLBACK_NOTICE)
        if notice:
            self._fallback_notice_wav = notice
        self.tts_healthy = greeting_ok
        if greeting_ok:
            log(
                "SIP TTS health OK "
                f"(fallback_notice={'ready' if notice else 'tone-only'})"
            )
        else:
            log(
                "SIP TTS health FAILED: engine produced no audio. Live calls will "
                "play a fallback notice/tone instead of dead air. Check edge-tts, "
                "ffmpeg ve ag baglantisi."
            )
            self.set_error("TTS health check failed at startup")
        return greeting_ok

    def transcribe(self, wav_bytes: bytes) -> str:
        if not wav_bytes:
            return ""
        stt_timeout = max(
            8.0, min(env_float("YAZKLINIK_SIP_STT_TIMEOUT", 25.0), 90.0))
        attempts = [("base", wav_bytes)]
        if env_bool("YAZKLINIK_SIP_STT_AUDIO_BOOST", True):
            boosted = boost_wav_for_stt(wav_bytes)
            if boosted and boosted != wav_bytes:
                attempts.append(("boost", boosted))
        last_exc = None
        for idx, (label, audio_bytes) in enumerate(attempts, start=1):
            try:
                data = multipart_post(
                    self.cfg.whisper_url,
                    "audio_file",
                    f"sip-turn-{label}.wav",
                    audio_bytes,
                    fields={"language": "tr"},
                    timeout=stt_timeout,
                )
                text = normalize_sip_stt_text(
                    data.decode("utf-8", errors="replace").strip()
                )
                self.stt_healthy = True
                if text and not _sip_stt_noise_text(text):
                    if idx > 1:
                        log(
                            f"SIP STT retry success mode={label} chars={len(text)}"
                        )
                    return text
                if text:
                    log(
                        f"SIP STT filtered mode={label} text={text!r}"
                    )
            except Exception as exc:
                last_exc = exc
                continue
        if last_exc is not None:
            with self.status_lock:
                self.stt_healthy = False
                self.last_error = f"Whisper STT erisilemedi: {last_exc}"[:500]
            log(f"Whisper hata (STT UNHEALTHY): {last_exc}")
        return ""

    def ai_reply(self, text: str, caller: str, history: list,
                 triage: Optional[dict] = None,
                 full_transcript: str = "",
                 dtmf_digits: str = "",
                 call: Optional[CallState] = None) -> str:
        text = normalize_sip_stt_text(text)
        full_text = normalize_sip_stt_text(full_transcript or text)
        dtmf_clean = "".join(ch for ch in str(dtmf_digits or "") if ch.isdigit())
        if call is not None:
            call.last_ai_status = ""
            call.last_ai_terminal = False
            call.last_ai_should_hangup = False
        if not text and not full_text and len(dtmf_clean) >= 10:
            text = f"Telefon numaram {dtmf_clean[-10:]}"
            full_text = text
        if not text and not full_text:
            return "Doktorum, sizi duyamadim. Tekrar eder misiniz?"
        caller_clean = sip_header_user(caller) or caller or "sip"
        try:
            guard = build_sip_safe_response(
                text, full_transcript=full_text, caller=caller_clean,
                triage=triage, history=history, dtmf_digits=dtmf_clean)
        except Exception as guard_exc:
            guard = {"enabled": False, "block_webhook": False, "error": str(guard_exc)}
            log(f"SIP safe guard hata: {guard_exc}")
        if guard.get("block_webhook"):
            status = str(guard.get("status") or "sip_safe_guard")
            terminal = bool(guard.get("terminal"))
            if call is not None:
                call.last_ai_status = status
                call.last_ai_terminal = terminal
                call.last_ai_should_hangup = bool(
                    guard.get("should_hangup") or terminal)
            log(
                "SIP safe guard: "
                f"intent={guard.get('intent') or '-'} "
                f"status={status} "
                f"terminal={terminal} "
                f"reason={guard.get('reason') or '-'}"
            )
            return str(guard.get("reply") or "").strip() or (
                "Mesajinizi klinik ekibine not olarak iletiyorum; "
                "telefonda kesin islem yapmadim."
            )
        # Not a safety-blocked intent: hand the turn to the web booking +
        # assistant flow. It is history-aware and owns appointment creation
        # (collect slot -> confirm -> create). The SIP line never books on its
        # own; it relays the caller's speech and plays back the web reply.
        history_turns = max(2, min(env_int("YAZKLINIK_SIP_AI_HISTORY_TURNS", 16), 24))
        payload = {
            "secret": self.cfg.webhook_secret,
            "transcript": text or full_text,
            "full_transcript": full_text or text,
            "caller": caller_clean,
            "history": (history or [])[-history_turns:],
            "triage": triage or {},
            "source": "sip_alex",
            "mode": "sip_live",
            "dtmf_digits": dtmf_digits or "",
            "sip_guard": guard,
        }
        ai_timeout = max(6.0, min(env_float("YAZKLINIK_SIP_AI_TIMEOUT", 18.0), 60.0))
        last_exc = None

        def _post_once(url: str, secret_value: str) -> dict:
            body = dict(payload, secret=secret_value)
            ctx = local_https_context_for(url)
            req = urllib.request.Request(
                url, data=json.dumps(body).encode("utf-8"),
                headers={"Content-Type": "application/json"}, method="POST")
            with urllib.request.urlopen(req, timeout=ai_timeout, context=ctx) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))

        for web_url in ai_webhook_urls(self.cfg.web_base_url):
            try:
                try:
                    data = _post_once(web_url, self.cfg.webhook_secret)
                except urllib.error.HTTPError as http_exc:
                    if http_exc.code != 401:
                        raise
                    db_secret = read_web_setting(
                        "ai_phone_webhook_secret", self.cfg.webhook_secret)
                    if db_secret and db_secret != self.cfg.webhook_secret:
                        log("AI webhook secret DB ile yenilendi; tekrar deneniyor.")
                        self.cfg.webhook_secret = db_secret
                        data = _post_once(web_url, self.cfg.webhook_secret)
                    else:
                        raise
                reply = str(data.get("reply") or "").strip()
                status = str(data.get("status") or "").strip()
                terminal = bool(data.get("terminal") or data.get("should_hangup"))
                if call is not None:
                    call.last_ai_status = status
                    call.last_ai_terminal = terminal
                    call.last_ai_should_hangup = bool(
                        data.get("should_hangup") or terminal)
                if reply:
                    log(
                        "AI webhook ok: "
                        f"url={web_url} status={status or '-'} "
                        f"terminal={terminal} chars={len(reply)}"
                    )
                    return reply
            except Exception as exc:
                last_exc = exc
                log(f"AI webhook hata: {exc} | url={web_url}")
                continue
        if last_exc is not None:
            log(f"AI webhook tum hedeflerde basarisiz: {last_exc}")
        if call is not None:
            call.last_ai_status = "ai_webhook_unreachable"
        return "Doktorum, su an klinik yaniti gecikti. Tekrar dener misiniz?"

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

            # D700 2026-05-17: Sesli onay entegrasyonu.
            # Hasta "randevu icin geldim" + "evet onaylyorum" diyebilir.
            # Sesli onay ajani bunu yakalar; appointment_id varsa state degisir.
            if payload.get("intent") in ("appointment_new", "appointment_cancel", "other"):
                try:
                    from yazklinik_sesli_onay_agent import (
                        decide as confirm_decide, ConfirmationRequest, can_auto_apply
                    )
                    pending_appt = getattr(call, "pending_appointment_id", None)
                    if pending_appt:
                        req = ConfirmationRequest(
                            appointment_id=str(pending_appt),
                            patient_phone=caller,
                            patient_name=caller_name or "",
                            appointment_at="",  # web layer doldurur
                            spoken_response=transcript,
                        )
                        c_result = confirm_decide(req)
                        c_payload = asdict(c_result)
                        call.last_confirm = c_payload
                        log(
                            "Sesli onay: "
                            f"decision={c_payload.get('decision')} "
                            f"confidence={c_payload.get('confidence')} "
                            f"auto={can_auto_apply(c_result)}"
                        )
                        payload["sesli_onay"] = c_payload
                except Exception as cexc:
                    log(f"Sesli onay skip: {cexc}")

            return payload
        except Exception as exc:
            self.set_error(f"telesekreter triage hata: {exc}")
            log(f"Telesekreter triage hata: {exc}")
            return {}

    def run_call_audio(self, call: CallState) -> None:
        rtp = RTPAudioSession(self.cfg, call)
        try:
            post_tts_pause = max(
                0.0, min(env_float("YAZKLINIK_SIP_POST_TTS_PAUSE_SEC", 0.2), 1.0))
            wav = self.synthesize(self.cfg.greeting)
            if wav:
                rtp.send_wav(wav)
                time.sleep(post_tts_pause)
            kickoff = (
                "Size nasil yardimci olabilirim? "
                "Randevu icin aradiysaniz randevu olusturalim; "
                "genel bilgi icin sorunuzu alabilirim."
            )
            kickoff_wav = self.synthesize(kickoff)
            if kickoff_wav:
                rtp.send_wav(kickoff_wav)
                time.sleep(post_tts_pause)
            call.history.append({"role": "assistant", "content": kickoff})
            caller = sip_header_user(call.from_header) or call.from_header or call.direction
            missed_turns = 0
            silent_since = None
            last_dtmf_len = 0
            silence_hangup_seconds = max(
                5.0, float(self.cfg.silence_hangup_seconds or 15.0))
            for idx in range(max(1, self.cfg.max_turns)):
                if not call.active:
                    break
                log(
                    f"SIP listening turn={idx + 1} call={call.call_id} "
                    f"seconds={self.cfg.record_seconds}"
                )
                turn_started = time.time()
                wav_in, packet_count = rtp.record_turn(
                    seconds=self.cfg.record_seconds,
                    silence_seconds=self.cfg.silence_seconds)
                text = ""
                if not wav_in or packet_count < 8:
                    log(
                        f"SIP silence turn={idx + 1} packets={packet_count} "
                        f"call={call.call_id}"
                    )
                else:
                    text = normalize_sip_stt_text(self.transcribe(wav_in))
                    log(f"SIP STT turn={idx + 1} text={text!r}")
                dtmf_raw = "".join(
                    ch for ch in str(call.dtmf_digits or "")
                    if ch in "0123456789*#"
                )
                dtmf_clean = "".join(ch for ch in dtmf_raw if ch.isdigit())
                dtmf_changed = len(dtmf_raw) > last_dtmf_len
                if dtmf_changed:
                    last_dtmf_len = len(dtmf_raw)
                dtmf_last = dtmf_raw[-1] if dtmf_raw else ""
                dtmf_feedback_cmd = ""
                if dtmf_changed and dtmf_last in ("#", "*"):
                    dtmf_feedback_cmd = dtmf_last
                elif (
                    dtmf_changed
                    and dtmf_last in ("3", "5")
                    and len(dtmf_clean) == 1
                    and missed_turns >= 1
                ):
                    dtmf_feedback_cmd = dtmf_last
                if not text and len(dtmf_clean) >= 10:
                    text = f"Telefon numaram {dtmf_clean[-10:]}"
                    log(
                        f"SIP DTMF-only turn={idx + 1} "
                        f"digits={dtmf_clean[-10:]}"
                    )
                if not text:
                    if dtmf_feedback_cmd:
                        missed_turns = 0
                        silent_since = None
                        call.dtmf_digits = ""
                        last_dtmf_len = 0
                        if dtmf_feedback_cmd == "5":
                            reply = (
                                "Doktorum, tekrar dinliyorum. "
                                "Lutfen daha yavas ve net konusur musunuz?"
                            )
                            wav_out = self.synthesize(reply)
                            if wav_out:
                                rtp.send_wav(wav_out)
                                time.sleep(post_tts_pause)
                            continue
                        if dtmf_feedback_cmd == "3":
                            reply = (
                                "Doktorum, notunuzu asistana iletiyorum. "
                                "En kisa surede sizi geri arayacagiz."
                            )
                            wav_out = self.synthesize(reply)
                            if wav_out:
                                rtp.send_wav(wav_out)
                                time.sleep(post_tts_pause)
                            self.send_bye(call, reason="dtmf-3-callback")
                            call.active = False
                            break
                        if dtmf_feedback_cmd == "#":
                            reply = (
                                "Doktorum, kisa not birakma modunu aciyorum. "
                                "Lutfen bip sesinden sonra notunuzu birakip bekleyin."
                            )
                            wav_out = self.synthesize(reply)
                            if wav_out:
                                rtp.send_wav(wav_out)
                                time.sleep(post_tts_pause)
                            continue
                        if dtmf_feedback_cmd == "*":
                            reply = "Doktorum, gorusmeyi simdi nazikce sonlandiriyorum."
                            wav_out = self.synthesize(reply)
                            if wav_out:
                                rtp.send_wav(wav_out)
                                time.sleep(post_tts_pause)
                            self.send_bye(call, reason="dtmf-star-end")
                            call.active = False
                            break
                    if dtmf_clean and dtmf_changed and len(dtmf_clean) < 10:
                        missed_turns = 0
                        silent_since = None
                        reply = (
                            f"Numara tuslamasini aliyorum. {len(dtmf_clean)} rakam geldi; "
                            "lutfen kalan rakamlari tuslayin."
                        )
                        wav_out = self.synthesize(reply)
                        if wav_out:
                            rtp.send_wav(wav_out)
                            time.sleep(post_tts_pause)
                        continue
                    if packet_count >= 8:
                        # Audio arrived but STT could not produce a clean sentence.
                        # Do not treat this as pure silence timeout.
                        missed_turns += 1
                        silent_since = None
                        reply = (
                            "Doktorum sesiniz geldi ama net anlayamadim. "
                            "Lutfen telefona biraz daha yakin ve daha yavas tekrar eder misiniz?"
                        )
                        if missed_turns >= 2:
                            reply = (
                                "Hatta parazit olabilir. "
                                "Tekrar dinlemem icin 5'e basin. "
                                "Asistan geri arasin isterseniz 3'e basin."
                            )
                        wav_out = self.synthesize(reply)
                        if wav_out:
                            rtp.send_wav(wav_out)
                            time.sleep(post_tts_pause)
                        continue
                    missed_turns += 1
                    if silent_since is None:
                        silent_since = turn_started
                    silent_for = time.time() - silent_since
                    if silent_for >= silence_hangup_seconds:
                        reply = sip_silence_closing_text(silence_hangup_seconds)
                        log(
                            f"SIP silence hangup call={call.call_id} "
                            f"silent_for={silent_for:.1f}s"
                        )
                        wav_out = self.synthesize(reply)
                        if wav_out:
                            rtp.send_wav(wav_out)
                            time.sleep(post_tts_pause)
                        self.send_bye(call, reason="silence-timeout")
                        call.active = False
                        break
                    reply = (
                        "Doktorum, sesinizi alamadÄ±m. Telefona biraz daha yakÄ±n konuÅŸup "
                        "tekrar eder misiniz?"
                    )
                    if missed_turns >= 2:
                        reply = (
                            "Doktorum, ses hattinda sorun olabilir. "
                            "Tekrar dinlemem icin 5'e basin. "
                            "Asistan geri arasin isterseniz 3'e basin. "
                            "Not birakmak icin kareye, gorusmeyi bitirmek icin yildiza basin."
                        )
                else:
                    missed_turns = 0
                    silent_since = None
                    call.transcript_parts.append(text)
                    full_transcript = "\n".join(call.transcript_parts)
                    triage = self.triage_call_turn(call, full_transcript)
                    call.history.append({"role": "user", "content": text})
                    reply = self.ai_reply(
                        text, caller=caller, history=call.history,
                        triage=triage, full_transcript=full_transcript,
                        dtmf_digits=call.dtmf_digits, call=call)
                    if triage and triage.get("intent") == "urgent":
                        reply = (
                            "Bu anlattÄ±ÄŸÄ±nÄ±z acil olabilir. LÃ¼tfen beklemeden kliniÄŸi "
                            "veya 112'yi arayÄ±n. Ben notu doktor ekranÄ±na acil olarak iÅŸaretliyorum. "
                            + reply
                        )
                    call.history.append({"role": "assistant", "content": reply})
                wav_out = self.synthesize(reply)
                if wav_out:
                    rtp.send_wav(wav_out)
                    time.sleep(post_tts_pause)
                if call.last_ai_should_hangup:
                    log(
                        f"SIP AI terminal hangup call={call.call_id} "
                        f"status={call.last_ai_status or '-'}"
                    )
                    self.send_bye(call, reason=call.last_ai_status or "ai-terminal")
                    call.active = False
                    break
            if call.last_triage:
                log(f"Call loop ended: {call.call_id} triage={json.dumps(call.last_triage, ensure_ascii=False)}")
            else:
                log(f"Call loop ended: {call.call_id}")
        except Exception as exc:
            self.set_error(f"call audio hata: {exc}")
            log(traceback.format_exc())
        finally:
            was_active = bool(call.active)
            call.active = False
            if was_active:
                self.send_bye(call, reason="call-loop-finalize")
                time.sleep(0.08)
            rtp.close()
            self.active_calls.pop(call.call_id, None)

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
                call.audio_started = True
                log(
                    f"Outgoing call connected: call_id={call_id} target={target} "
                    f"rtp={remote_ip}:{remote_port} payload={payload}"
                )
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
                    call.audio_started = True
                    log(
                        f"Outgoing call connected: call_id={call_id} target={target} "
                        f"rtp={remote_ip}:{remote_port} payload={payload}"
                    )
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

    def send_bye(self, call: CallState, reason: str = "", attempts: Optional[int] = None) -> None:
        """Politely terminate a live call from Alex side."""
        if not call.call_id:
            return
        remote_header = call.from_header if call.direction == "incoming" else call.to_header
        remote_uri = sip_uri_from_header(remote_header)
        if not remote_uri:
            remote_user = sip_header_user(remote_header) or call.direction or "unknown"
            remote_uri = f"sip:{remote_user}@{self.cfg.domain}"
        retry_count = attempts if attempts is not None else env_int("YAZKLINIK_SIP_BYE_RETRIES", 2)
        retry_count = max(1, min(int(retry_count or 1), 5))
        retry_delay = max(
            0.0, min(env_float("YAZKLINIK_SIP_BYE_RETRY_DELAY_SEC", 0.15), 1.0))
        try:
            for idx in range(retry_count):
                msg = self.build_request(
                    "BYE",
                    remote_uri,
                    call.call_id,
                    call.local_tag,
                    remote_uri,
                    cseq=self.next_cseq(),
                    to_tag=call.remote_tag,
                )
                self.send(msg)
                log(
                    f"SIP BYE sent call={call.call_id} "
                    f"reason={reason or 'normal'} uri={remote_uri} "
                    f"attempt={idx + 1}/{retry_count}"
                )
                if idx + 1 < retry_count and retry_delay > 0.0:
                    time.sleep(retry_delay)
        except Exception as exc:
            log(f"SIP BYE send hata call={call.call_id}: {exc}")

    def serve(self) -> None:
        log(f"SIP bridge starting ext={self.cfg.extension} pbx={self.cfg.pbx_host}:{self.cfg.pbx_port} local={self.cfg.local_ip}:{self.cfg.local_port}")
        if not self.cfg.enabled:
            self.set_error("YAZKLINIK_SIP_ENABLED=1 degil")
        if env_bool("YAZKLINIK_SIP_TTS_WARMUP", True):
            self.tts_health_check()
        next_register = 0.0
        while not self.stop_event.is_set():
            self.cleanup_calls()
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
        cfg = self.bridge.cfg
        self.sock.bind((cfg.control_host, cfg.control_port))
        self.sock.listen(20)

    def run(self) -> None:
        cfg = self.bridge.cfg
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


def tts_test(cfg: AlexSIPConfig, out_path: Optional[str] = None) -> int:
    text = normalize_sip_tts_text(cfg.greeting)
    data = b""
    if env("YAZKLINIK_SIP_TTS_ENGINE", "edge").lower() in {"edge", "edge_tts", "neural", "emel_neural"}:
        data = cached_edge_neural_tts_wav(text)
    if not data:
        print(json.dumps({
            "ok": False,
            "error": "tts_failed",
            "engine": env("YAZKLINIK_SIP_TTS_ENGINE", "edge"),
            "voice": env("YAZKLINIK_SIP_EDGE_VOICE", "tr-TR-EmelNeural"),
        }, ensure_ascii=False, indent=2))
        return 2
    if not out_path:
        out_path = str(ROOT / "voice_records" / "sip_edge_neural_greeting_test.wav")
    target = Path(out_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    with wave.open(io.BytesIO(data), "rb") as wf:
        meta = {
            "channels": wf.getnchannels(),
            "sample_width": wf.getsampwidth(),
            "sample_rate": wf.getframerate(),
            "frames": wf.getnframes(),
            "duration_sec": round(wf.getnframes() / float(wf.getframerate() or 1), 2),
        }
    print(json.dumps({
        "ok": True,
        "engine": env("YAZKLINIK_SIP_TTS_ENGINE", "edge"),
        "voice": env("YAZKLINIK_SIP_EDGE_VOICE", "tr-TR-EmelNeural"),
        "fallback_enabled": env_bool("YAZKLINIK_SIP_TTS_ALLOW_LEGACY_FALLBACK", False),
        "path": str(target),
        "bytes": len(data),
        "normalized_text": text,
        "wav": meta,
    }, ensure_ascii=False, indent=2))
    return 0


def main(argv: Optional[list] = None) -> int:
    load_config_env()
    parser = argparse.ArgumentParser(description="YazKlinik Alex SIP bridge")
    parser.add_argument("--probe", action="store_true", help="Only test SIP REGISTER")
    parser.add_argument("--tts-test", nargs="?", const="", help="Generate the current SIP greeting WAV")
    parser.add_argument("--call", help="Originate a call to extension")
    args = parser.parse_args(argv)
    cfg = AlexSIPConfig.from_env()
    if args.tts_test is not None:
        return tts_test(cfg, args.tts_test or None)
    if args.probe:
        return sip_probe(cfg)
    if not acquire_single_instance_lock():
        if is_control_api_alive(cfg.control_host, cfg.control_port):
            log("Another Alex SIP bridge instance already healthy; exiting quietly.")
            return 0
        log("Another Alex SIP bridge instance is already running; exiting.")
        return 4
    bridge = None
    try:
        bridge = SIPAlexBridge(cfg)
        control = ControlServer(bridge)
    except OSError as exc:
        if bridge is not None:
            try:
                bridge.sock.close()
            except Exception:
                pass
        log(f"SIP instance already running or port busy: {exc}")
        return 4
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

