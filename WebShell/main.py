"""YazKlinik WebShell v3.0 - Web arayuz + Native kabuk."""
from __future__ import annotations
import argparse
import ctypes
import json
import os
import sys
import socket
import urllib.parse
from pathlib import Path

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
os.environ.setdefault("QT_LOGGING_RULES", "*.debug=false")

IS_WINDOWS = sys.platform.startswith("win")
IS_MACOS = sys.platform == "darwin"
DEFAULT_TERMINAL_SERVER_URL = os.environ.get(
    "YAZKLINIK_TERMINAL_DEFAULT_SERVER_URL",
    "http://127.0.0.1:5052",
).strip().rstrip("/") or "http://127.0.0.1:5052"

if "--safe-mode" in sys.argv:
    os.environ["YAZKLINIK_WEBSHELL_GPU_TURBO"] = "0"
    os.environ["YAZKLINIK_WEBSHELL_SAFE_MODE"] = "1"

if IS_MACOS:
    os.environ.setdefault("QT_MAC_WANTS_LAYER", "1")

_GPU_DEFAULT = "1"
if os.environ.get("YAZKLINIK_WEBSHELL_GPU_TURBO", _GPU_DEFAULT) == "1":
    os.environ.setdefault("QT_OPENGL", "desktop")
    os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS",
        "--ignore-gpu-blocklist --enable-gpu-rasterization "
        "--enable-zero-copy --enable-accelerated-video-decode "
        "--num-raster-threads=4 --disable-background-networking "
        "--disable-sync --disable-extensions "
        "--disable-features=Translate,MediaRouter,Vulkan")


def _append_qtwebengine_flags(*flags: str) -> None:
    existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    parts = existing.split() if existing else []
    for flag in flags:
        flag = (flag or "").strip()
        if flag and flag not in parts:
            parts.append(flag)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(parts)


def _int_env(name: str, default: int, low: int, high: int) -> int:
    try:
        value = int(float(os.environ.get(name, str(default))))
    except Exception:
        value = default
    return max(low, min(high, value))


def _configure_windows_terminal_accelerator() -> None:
    """Use the terminal PC as a native Windows performance buffer."""
    if not IS_WINDOWS:
        return
    if os.environ.get("YAZKLINIK_WEBSHELL_SAFE_MODE", "").strip() == "1":
        return
    if os.environ.get("YAZKLINIK_WEBSHELL_WINDOWS_ACCELERATOR", "1").strip() == "0":
        return
    os.environ.setdefault("YAZKLINIK_WEBSHELL_WINDOWS_ACCELERATOR", "1")
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("QT_SCALE_FACTOR_ROUNDING_POLICY", "PassThrough")
    try:
        # Per-monitor DPI awareness keeps the WebShell crisp on modern Windows displays.
        ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except Exception:
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    priority = os.environ.get("YAZKLINIK_WEBSHELL_PRIORITY", "normal").strip().lower()
    if priority in {"above", "above_normal", "high_ui", "1"}:
        try:
            ctypes.windll.kernel32.SetPriorityClass(
                ctypes.windll.kernel32.GetCurrentProcess(), 0x00008000)
        except Exception:
            pass
    flags = [
        "--enable-oop-rasterization",
        "--enable-native-gpu-memory-buffers",
        "--enable-smooth-scrolling",
        "--enable-features=CanvasOopRasterization",
    ]
    if os.environ.get("YAZKLINIK_WEBSHELL_KEEP_BACKGROUND_ACTIVE", "0").strip() == "1":
        flags.extend([
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--disable-background-timer-throttling",
        ])
    _append_qtwebengine_flags(*flags)


def _configure_cross_platform_webengine() -> None:
    cache_mb = _int_env("YAZKLINIK_WEBSHELL_CACHE_MB", 512, 64, 768)
    cache_bytes = cache_mb * 1024 * 1024
    _append_qtwebengine_flags(
        "--autoplay-policy=no-user-gesture-required",
        "--enable-media-stream",
        "--disable-background-networking",
        "--disable-sync",
        "--disable-extensions",
        f"--disk-cache-size={cache_bytes}",
        f"--media-cache-size={cache_bytes}",
    )
    _configure_windows_terminal_accelerator()
    if IS_MACOS:
        _append_qtwebengine_flags(
            "--disable-features=Translate,MediaRouter,Vulkan",
            "--enable-features=NetworkServiceInProcess",
        )
    if os.environ.get("YAZKLINIK_WEBSHELL_SAFE_MODE", "").strip() == "1":
        _append_qtwebengine_flags(
            "--disable-gpu",
            "--disable-gpu-compositing",
            "--disable-accelerated-video-decode",
        )


def _safe_read_text(path: Path) -> str:
    try:
        if path.exists():
            return path.read_text(encoding="utf-8", errors="ignore").strip().rstrip("/")
    except Exception:
        pass
    return ""


def _webshell_config() -> dict:
    try:
        cfg_path = Path(__file__).resolve().parents[1] / "yazklinik_config.json"
        if cfg_path.exists():
            return json.loads(cfg_path.read_text(encoding="utf-8-sig"))
    except Exception:
        pass
    return {}


def _platform_app_data_dir() -> Path:
    override = os.environ.get("YAZKLINIK_APPDATA_DIR", "").strip()
    if override:
        return Path(override)
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    elif IS_MACOS:
        base = str(Path.home() / "Library" / "Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "YazKlinik"


def _local_http_hosts() -> list[str]:
    hosts = ["localhost", "127.0.0.1"]
    seen = {h.lower() for h in hosts}
    try:
        names = [socket.gethostname()]
        try:
            names.append(socket.getfqdn(names[0]))
        except Exception:
            pass
        for name in names:
            if name and name.lower() not in seen:
                seen.add(name.lower())
                hosts.append(name)
            try:
                for item in socket.getaddrinfo(name, None, family=socket.AF_INET):
                    addr = item[4][0]
                    if addr and addr.lower() not in seen:
                        seen.add(addr.lower())
                        hosts.append(addr)
            except Exception:
                pass
    except Exception:
        pass
    return hosts


def _argv_server_url(argv: list[str] | None = None) -> str:
    """Return --server value early, before api_client is imported."""
    args = list(sys.argv[1:] if argv is None else argv)
    for idx, arg in enumerate(args):
        raw = str(arg or "").strip()
        if raw in {"--server", "-s"} and idx + 1 < len(args):
            return str(args[idx + 1] or "").strip().rstrip("/")
        if raw.startswith("--server="):
            return raw.split("=", 1)[1].strip().rstrip("/")
    return ""


def _media_secure_origin_flag() -> str:
    cfg = _webshell_config()
    web_port = (
        os.environ.get("YAZKLINIK_WEB_PORT")
        or str(cfg.get("web_port") or "")
        or "5052"
    ).strip() or "5052"
    https_port = (
        os.environ.get("YAZKLINIK_HTTPS_PORT")
        or str(cfg.get("https_port") or "")
        or "5443"
    ).strip() or "5443"
    raw = [
        f"http://localhost:{web_port}",
        f"http://127.0.0.1:{web_port}",
        DEFAULT_TERMINAL_SERVER_URL,
        "http://192.168.1.40:5052",
        "http://192.168.1.148:5052",
        str(cfg.get("server_url") or "").strip().rstrip("/"),
        str(cfg.get("https_url") or "").strip().rstrip("/"),
        _argv_server_url(),
    ]
    for host in _local_http_hosts():
        raw.append(f"http://{host}:{web_port}")
        raw.append(f"https://{host}:{https_port}")
    root = Path(__file__).resolve().parents[1]
    local_app = _platform_app_data_dir()
    for path in (
        root / "terminal_server_url.txt",
        local_app / "terminal_server_url.txt",
        local_app / "server_actual_url.txt",
        local_app / "Server" / "terminal_server_url.txt",
    ):
        value = _safe_read_text(path)
        if value:
            raw.append(value)
    for key in (
        "YAZKLINIK_SERVER_URL",
        "YAZKLINIK_WEB_URL",
        "YAZKLINIK_AI_SERVER_URL",
        "YAZKLINIK_DEFAULT_SERVER_URL",
        "YAZKLINIK_HTTPS_URL",
    ):
        value = os.environ.get(key, "").strip().rstrip("/")
        if value:
            raw.append(value)
    origins = []
    seen = set()
    for value in raw:
        value = str(value or "").strip().rstrip("/")
        if value and "://" not in value:
            value = "http://" + value
        try:
            parsed = urllib.parse.urlsplit(value)
            origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
        except Exception:
            origin = ""
        if origin and origin not in seen:
            seen.add(origin)
            origins.append(origin)
    return ",".join(origins)


_media_origins = _media_secure_origin_flag()
if _media_origins:
    _append_qtwebengine_flags(
        "--use-fake-ui-for-media-stream",
        "--unsafely-treat-insecure-origin-as-secure=" + _media_origins,
    )
_configure_cross_platform_webengine()

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QSettings

from theme import apply
import api_client
from shell_window import ShellWindow

APP_VERSION = "YazKlinik WebShell v3.0 - Final D200"
os.environ.setdefault("YAZKLINIK_WEBSHELL_VERSION", APP_VERSION)


def _parse_args(argv: list[str]):
    parser = argparse.ArgumentParser(
        prog="YazKlinik WebShell",
        description="YazKlinik web arayuzunu native Windows/macOS WebShell icinde acar.",
    )
    parser.add_argument("--server", "-s", help="Baglanilacak YazKlinik server URL")
    parser.add_argument("--check", action="store_true", help="GUI acmadan ortam kontrolu yap")
    parser.add_argument("--safe-mode", action="store_true", help="GPU hizlandirmasini kapat")
    parser.add_argument("--start-route", default="", help="Ilk acilacak web rotasi")
    args, _unknown = parser.parse_known_args(argv)
    return args


def _set_server_env(server: str) -> str:
    server = api_client.normalize_url(server or "", default_port="5052") or (server or "")
    server = server.rstrip("/")
    if server:
        os.environ["YAZKLINIK_SERVER_URL"] = server
        os.environ["YAZKLINIK_WEB_URL"] = server
        os.environ["YAZKLINIK_AI_SERVER_URL"] = server
        os.environ["YAZKLINIK_DEFAULT_SERVER_URL"] = server
    return server


def _server_host_is_this_machine(server: str) -> bool:
    try:
        parsed = urllib.parse.urlsplit(server or "")
        host = (parsed.hostname or "").strip().lower()
    except Exception:
        host = ""
    if not host:
        return False
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    local_hosts = {str(item or "").strip().lower() for item in _local_http_hosts()}
    if host in local_hosts:
        return True
    try:
        resolved = {
            item[4][0].strip().lower()
            for item in socket.getaddrinfo(host, None, family=socket.AF_INET)
            if item and item[4] and item[4][0]
        }
        return bool(resolved & local_hosts)
    except Exception:
        return False


def _prefer_loopback_for_local_webshell(server: str) -> str:
    """Use localhost inside WebShell when the LAN URL points to this PC.

    Qt/Chromium can hide getUserMedia on plain LAN HTTP. Loading the same
    local server through 127.0.0.1 keeps terminal defaults intact while making
    microphone APIs available in the desktop shell.
    """
    server = api_client.normalize_url(server or "", default_port="5052") or (server or "")
    server = server.rstrip("/")
    try:
        parsed = urllib.parse.urlsplit(server)
    except Exception:
        return server
    if (parsed.scheme or "").lower() != "http":
        return server
    if not _server_host_is_this_machine(server):
        return server
    port = parsed.port or 5052
    loopback = f"http://127.0.0.1:{port}"
    if loopback == server:
        return server
    if api_client.ping(loopback, timeout=0.7):
        os.environ["YAZKLINIK_WEBSHELL_UPSTREAM_SERVER_URL"] = server
        os.environ["YAZKLINIK_WEBSHELL_RUNTIME_LOCAL_URL"] = loopback
        return loopback
    return server


def _persistable_server_url(server: str) -> str:
    return (
        os.environ.get("YAZKLINIK_WEBSHELL_UPSTREAM_SERVER_URL", "").strip().rstrip("/")
        or (server or "").strip().rstrip("/")
    )


def _resolve_server(args) -> str:
    if args.server:
        raw_server = _set_server_env(args.server)
        server = _set_server_env(_prefer_loopback_for_local_webshell(raw_server))
        if server:
            api_client.save_terminal_server_url(_persistable_server_url(server))
            return server
    discovered = _set_server_env(api_client.discover())
    return _set_server_env(_prefer_loopback_for_local_webshell(discovered))


def _run_check(server: str) -> int:
    ok = api_client.ping(server, timeout=1.3)
    print("YAZKLINIK_WEBSHELL_CHECK_OK")
    print(f"version={APP_VERSION}")
    print(f"platform={sys.platform}")
    print(f"server={server}")
    print(f"server_ping={'ok' if ok else 'offline'}")
    print("qtwebengine_flags=" + os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", ""))
    return 0

def _prompt_server_url(default_url: str) -> str:
    """Terminal modda server'a erisemiyorsak kullaniciya sor.
    Bos birakirsa default 192.168.1.40:5052 kullanilir."""
    try:
        from PySide6.QtWidgets import QInputDialog, QApplication, QMessageBox
    except Exception:
        return default_url
    app = QApplication.instance() or QApplication(sys.argv)
    cur = (default_url or "").replace("http://", "").replace("https://", "")
    if not cur:
        cur = DEFAULT_TERMINAL_SERVER_URL.replace("http://", "").replace("https://", "")
    text, ok = QInputDialog.getText(
        None,
        "YazKlinik Terminal - Server Adresi",
        "Server PC'sinin adresini girin.\n\n"
        "Server bu PC degilse, server'in LAN IP'si ve portu (orn: "
        "192.168.1.40:5052 veya https://192.168.1.40:5443).\n\n"
        "Bos birakir veya iptal edersen varsayilan "
        f"{DEFAULT_TERMINAL_SERVER_URL} kullanilir.",
        text=cur)
    if not ok:
        return default_url
    typed = (text or "").strip()
    if not typed:
        return DEFAULT_TERMINAL_SERVER_URL
    normalized = api_client.normalize_url(typed, default_port="5052")
    return normalized or default_url


def main() -> int:
    args = _parse_args(sys.argv[1:])
    if args.safe_mode:
        os.environ["YAZKLINIK_WEBSHELL_SAFE_MODE"] = "1"
    if args.start_route:
        route = args.start_route.strip()
        if route:
            os.environ["YAZKLINIK_DESKTOP_START_ROUTE"] = route if route.startswith("/") else "/" + route
    server = _resolve_server(args)

    if args.check:
        return _run_check(server)

    # Terminal mod: server'a erisilebilir mi kontrol et, yoksa kullaniciya
    # sor. Saved value veya 192.168.1.40:5052 default'a duser.
    skip_prompt = (
        os.environ.get("YAZKLINIK_SKIP_SERVER_PROMPT", "").strip() in
        {"1", "true", "yes"})
    if not skip_prompt and not api_client.ping(server, timeout=1.5):
        new_url = _prompt_server_url(server)
        if new_url and new_url != server:
            raw_server = _set_server_env(new_url)
            api_client.save_terminal_server_url(_persistable_server_url(raw_server))
            server = _set_server_env(_prefer_loopback_for_local_webshell(raw_server))
            # Yeni adresi tekrar ping et - hala yok ise kullaniciyi
            # uyar ama yine de baslat (offline calismaya razi)
            if not api_client.ping(server, timeout=2.0):
                try:
                    from PySide6.QtWidgets import QMessageBox, QApplication as _QApplication
                    app2 = _QApplication.instance() or _QApplication(sys.argv)
                    QMessageBox.warning(
                        None,
                        "YazKlinik - Server Erisilemiyor",
                        f"{server} adresine henuz erisilemiyor.\n\n"
                        "Server PC'si acik mi ve YazKlinik calisir durumda mi "
                        "kontrol edin.\nWebShell yine de acilacak; server "
                        "geldiginde sayfa yenilenebilir.")
                except Exception:
                    pass
    elif server:
        api_client.save_terminal_server_url(_persistable_server_url(server))

    mode = api_client.resolve_desktop_mode(server, default="hybrid")
    desktop_env = api_client.desktop_mode_env(mode, server)
    if args.start_route:
        route = args.start_route.strip()
        if route:
            desktop_env["YAZKLINIK_DESKTOP_START_ROUTE"] = route if route.startswith("/") else "/" + route
    os.environ.update(desktop_env)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName(APP_VERSION); app.setOrganizationName("YazKlinik")
    s = QSettings("YazKlinik","webshell")
    apply(app, dark=bool(s.value("dark_mode", False, type=bool)))
    win = ShellWindow(server)
    win.show()
    return app.exec()

if __name__ == "__main__":
    sys.exit(main())
