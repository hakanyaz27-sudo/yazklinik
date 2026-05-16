"""Server discovery helpers for the native WebShell."""
from __future__ import annotations
import json
import os
import socket
import subprocess
import sys
import urllib.parse
import urllib.request
import re
from pathlib import Path

DEFAULT_BASE = os.environ.get("YAZKLINIK_DEFAULT_SERVER_URL", "http://127.0.0.1:5052").rstrip("/")
TERMINAL_TOKEN = os.environ.get("YAZKLINIK_TERMINAL_TOKEN", "")


def app_data_dir() -> Path:
    override = os.environ.get("YAZKLINIK_APPDATA_DIR", "").strip()
    if override:
        return Path(override)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "YazKlinik"


def _allow_local() -> bool:
    return os.environ.get("YAZKLINIK_ALLOW_LOCAL_TERMINAL_SERVER", "").strip().lower() in {
        "1", "true", "evet", "yes", "on"
    }


def _local_names() -> set[str]:
    names = {"localhost", "127.0.0.1", "::1"}
    try:
        host = socket.gethostname()
        if host:
            names.add(host.lower())
            try:
                names.add(socket.getfqdn(host).lower())
            except Exception:
                pass
            try:
                for item in socket.getaddrinfo(host, None):
                    addr = item[4][0]
                    if addr:
                        names.add(addr.lower())
            except Exception:
                pass
    except Exception:
        pass
    return names


def _is_local_url(value: str) -> bool:
    if _allow_local():
        return False
    try:
        host = urllib.parse.urlparse(value).hostname or ""
    except Exception:
        return False
    return host.lower() in _local_names()

def _read(p):
    try:
        if p.exists():
            return p.read_text(encoding="utf-8", errors="ignore").strip().rstrip("/")
    except Exception:
        pass
    return ""


def normalize_desktop_mode(value: str, default: str = "shell") -> str:
    value = (value or "").strip().lower()
    return value if value in {"hybrid", "mirror", "shell"} else default


def desktop_mode_paths() -> list[Path]:
    paths = []
    paths.append(app_data_dir() / "desktop_mode.txt")
    paths.append(Path(__file__).resolve().parents[1] / "desktop_mode.txt")
    return paths


def read_local_desktop_mode(default: str = "shell") -> str:
    env_mode = os.environ.get("YAZKLINIK_DESKTOP_MODE", "")
    if os.environ.get("YAZKLINIK_DESKTOP_MODE_FORCE", "").strip() == "1" and env_mode:
        return normalize_desktop_mode(env_mode, default)
    for path in desktop_mode_paths():
        text = _read(path)
        if text:
            return normalize_desktop_mode(text, default)
    if env_mode:
        return normalize_desktop_mode(env_mode, default)
    return default


def write_desktop_mode(mode: str) -> str:
    mode = normalize_desktop_mode(mode, "shell")
    for path in desktop_mode_paths():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(mode + "\n", encoding="ascii")
        except Exception:
            pass
    return mode

def _unique_urls(cands: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for c in cands:
        c = (c or "").strip().rstrip("/")
        if not c or not c.startswith(("http://", "https://")):
            continue
        key = c.lower()
        if key not in seen:
            seen.add(key)
            out.append(c)
    return out


def _with_alt_ports(cands: list[str]) -> list[str]:
    """Add known YazKlinik live ports for the same server host.

    This prevents the hybrid shell from sticking to an older service on 5052
    while a newer repaired web server is temporarily live on another port.
    """
    ports_raw = os.environ.get("YAZKLINIK_WEBSHELL_ALT_PORTS", "5052,5068,5051,5000")
    ports = []
    for item in ports_raw.split(","):
        item = item.strip()
        if item.isdigit() and item not in ports:
            ports.append(item)
    expanded = list(cands)
    for c in cands:
        try:
            parsed = urllib.parse.urlsplit(c)
            if not parsed.scheme or not parsed.hostname:
                continue
            for port in ports:
                netloc = parsed.hostname
                if ":" in netloc and not netloc.startswith("["):
                    netloc = f"[{netloc}]"
                expanded.append(urllib.parse.urlunsplit((
                    parsed.scheme, f"{netloc}:{port}", "", "", "")))
        except Exception:
            pass
    return _unique_urls(expanded)


def _version_score(payload: dict) -> int:
    text = " ".join(str(payload.get(k) or "") for k in (
        "app_version", "version", "server", "release"))
    m = re.search(r"\b(?:A|D)(\d{2,5})\b", text, flags=re.IGNORECASE)
    if m:
        try:
            return int(m.group(1))
        except Exception:
            pass
    return 0


def ping_payload(url: str, timeout: float = 0.9) -> dict:
    try:
        with urllib.request.urlopen(url.rstrip("/") + "/api/terminal/ping", timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
    except urllib.error.HTTPError as ex:
        return {"ok": True, "http_status": ex.code}
    except Exception:
        return {}


def discover() -> str:
    base = app_data_dir()
    raw_cands = [
        os.environ.get("YAZKLINIK_SERVER_URL","").strip().rstrip("/"),
        os.environ.get("YAZKLINIK_AI_SERVER_URL","").strip().rstrip("/"),
        os.environ.get("YAZKLINIK_WEB_URL","").strip().rstrip("/"),
        _read(base/"terminal_server_url.txt"),
        _read(base/"server_actual_url.txt"),
        _read(base/"Server"/"terminal_server_url.txt"),
        DEFAULT_BASE,
    ]
    cands = _with_alt_ports(_unique_urls(raw_cands))
    allowed = [c for c in cands if not _is_local_url(c)]
    if _allow_local() or not allowed:
        allowed = cands
    best_url = ""
    best_score = -1
    first_reachable = ""
    for c in allowed:
        payload = ping_payload(c, timeout=0.65)
        if not payload:
            continue
        if not first_reachable:
            first_reachable = c
        score = _version_score(payload)
        if score > best_score:
            best_score = score
            best_url = c
    if best_url:
        return best_url
    if first_reachable:
        return first_reachable
    for c in allowed:
        return c
    if _allow_local():
        for c in cands:
            return c
    return DEFAULT_BASE


def server_desktop_mode(url: str, timeout: float = 1.2) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    try:
        req = urllib.request.Request(
            url + "/api/terminal/performance",
            headers={"X-Terminal-Token": TERMINAL_TOKEN})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
        mode = normalize_desktop_mode(str(data.get("desktop_runtime_mode") or ""), "")
        if mode:
            return mode
    except Exception:
        pass
    return ""


def feature_manifest(url: str, timeout: float = 1.5) -> dict:
    url = (url or "").strip().rstrip("/")
    if not url:
        return {}
    try:
        req = urllib.request.Request(
            url + "/api/ozellik-senkron",
            headers={"X-Terminal-Token": TERMINAL_TOKEN})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
    except Exception:
        return {}


def resolve_desktop_mode(url: str = "", default: str = "shell") -> str:
    if os.environ.get("YAZKLINIK_DESKTOP_MODE_FORCE", "").strip() != "1":
        mode = server_desktop_mode(url or discover())
        if mode:
            return write_desktop_mode(mode)
    return write_desktop_mode(read_local_desktop_mode(default))


def desktop_mode_env(mode: str, server_url: str = "") -> dict[str, str]:
    mode = normalize_desktop_mode(mode, "shell")
    env = {
        "YAZKLINIK_DESKTOP_MODE": mode,
        "YAZKLINIK_DESKTOP_FAST_START": "1",
        "YAZKLINIK_DESKTOP_START_ROUTE": "/giris",
    }
    if server_url:
        env["YAZKLINIK_SERVER_URL"] = server_url
        env["YAZKLINIK_WEB_URL"] = server_url
        env["YAZKLINIK_AI_SERVER_URL"] = server_url
    if mode == "mirror":
        env.update({
            "YAZKLINIK_DESKTOP_WEB_MIRROR": "1",
            "YAZKLINIK_DESKTOP_WEB_SHELL": "1",
            "YAZKLINIK_DESKTOP_ENABLE_WEBENGINE": "1",
            "YAZKLINIK_DESKTOP_DISABLE_WEBENGINE": "0",
            "YAZKLINIK_DESKTOP_WEB_CENTER_FIRST": "1",
        })
    elif mode == "shell":
        env.update({
            "YAZKLINIK_DESKTOP_WEB_MIRROR": "0",
            "YAZKLINIK_DESKTOP_WEB_SHELL": "1",
            "YAZKLINIK_DESKTOP_ENABLE_WEBENGINE": "1",
            "YAZKLINIK_DESKTOP_DISABLE_WEBENGINE": "0",
            "YAZKLINIK_DESKTOP_WEB_CENTER_FIRST": "0",
        })
    else:
        env.update({
            "YAZKLINIK_DESKTOP_WEB_MIRROR": "0",
            "YAZKLINIK_DESKTOP_WEB_SHELL": "1",
            "YAZKLINIK_DESKTOP_ENABLE_WEBENGINE": "1",
            "YAZKLINIK_DESKTOP_DISABLE_WEBENGINE": "0",
            "YAZKLINIK_DESKTOP_WEB_CENTER_FIRST": "1",
        })
    return env


def _gui_python() -> str:
    exe = Path(sys.executable)
    if os.name == "nt" and exe.name.lower() == "python.exe":
        candidate = exe.with_name("pythonw.exe")
        if candidate.exists():
            return str(candidate)
    return str(exe)


def launch_desktop_mode(mode: str, server_url: str = "") -> bool:
    mode = write_desktop_mode(mode)
    root = Path(__file__).resolve().parents[1]
    if mode in {"shell", "hybrid"}:
        script = Path(__file__).resolve().parent / "main.py"
    else:
        script = root / "yazklinik_desktop_v1000.py"
    if not script.exists():
        return False
    env = os.environ.copy()
    env.update(desktop_mode_env(mode, server_url))
    try:
        subprocess.Popen(
            [_gui_python(), "-X", "utf8", str(script)],
            cwd=str(script.parent if mode in {"shell", "hybrid"} else root),
            env=env,
            close_fds=True,
        )
        return True
    except Exception:
        return False

def ping(url: str, timeout: float = 1.5) -> bool:
    return bool(ping_payload(url, timeout=timeout))


def save_terminal_server_url(url: str) -> str:
    """Terminal modda kullanici tarafindan girilen server URL'sini
    LOCALAPPDATA/YazKlinik/terminal_server_url.txt dosyasina yazar.
    Sonraki acilislarda discover() bunu okur."""
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    if not (url.startswith("http://") or url.startswith("https://")):
        url = "http://" + url
    base = app_data_dir()
    try:
        base.mkdir(parents=True, exist_ok=True)
        (base / "terminal_server_url.txt").write_text(url, encoding="utf-8")
    except Exception:
        pass
    return url


def normalize_url(value: str, default_port: str = "5052") -> str:
    """Kullanici inputunu kanonik URL'ye cevir: '192.168.1.40' -> 'http://192.168.1.40:5052'."""
    raw = (value or "").strip().rstrip("/")
    if not raw:
        return ""
    if not (raw.startswith("http://") or raw.startswith("https://")):
        raw = "http://" + raw
    try:
        parsed = urllib.parse.urlsplit(raw)
        host = parsed.hostname or ""
        port = parsed.port
        if not host:
            return ""
        if not port:
            scheme = parsed.scheme or "http"
            if scheme == "http" and default_port:
                netloc = f"{host}:{default_port}"
            elif scheme == "https" and default_port == "5052":
                netloc = f"{host}:5443"
            else:
                netloc = host
            return f"{scheme}://{netloc}"
    except Exception:
        return raw
    return raw

