#!/usr/bin/env python3
"""Local WhatsApp share helper for YazKlinik.

This script runs on the client PC, not on the server. It first uses the real
NAS/local file paths from the prepared manifest and puts them on the Windows
clipboard as CF_HDROP in one operation. HTTP download is kept only as a fallback
for client PCs that cannot see the NAS path.
"""

from __future__ import annotations

import argparse
import ctypes
import ipaddress
import json
import os
import re
import ssl
import struct
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path


APP_USER_AGENT = "YazKlinik-FINAL3000-WhatsApp-Local-Helper/1.0"
CUSTOM_SCHEME = "yazklinik-wa"


def _log_path() -> Path:
    base = Path(tempfile.gettempdir()) / "YazKlinikWhatsAppShare"
    base.mkdir(parents=True, exist_ok=True)
    return base / "helper.log"


def log(message: str) -> None:
    line = time.strftime("%Y-%m-%d %H:%M:%S") + " " + str(message)
    try:
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    print(line)


def _clean_digits(value: str) -> str:
    digits = re.sub(r"\D+", "", value or "")
    if digits.startswith("0") and len(digits) == 11:
        digits = "90" + digits[1:]
    return digits


def _safe_file_name(value: str, fallback: str) -> str:
    name = Path(value or fallback).name.strip() or fallback
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", name)
    name = name.rstrip(". ")
    return (name or fallback)[:180]


def _is_private_or_local_host(host: str) -> bool:
    host = str(host or "").strip().lower()
    if not host:
        return False
    if host in {"localhost", "::1"} or host.startswith("127."):
        return True
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
        return bool(ip.is_private or ip.is_loopback or ip.is_link_local)
    except Exception:
        return host.endswith(".local")


def _ssl_context_for_url(url: str):
    try:
        parsed = urllib.parse.urlsplit(str(url or ""))
    except Exception:
        return None
    if parsed.scheme.lower() != "https":
        return None
    if not _is_private_or_local_host(parsed.hostname or ""):
        return None
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _urlopen_with_context(req: urllib.request.Request, timeout: float):
    target = req.full_url if hasattr(req, "full_url") else ""
    ctx = _ssl_context_for_url(target)
    if ctx is not None:
        try:
            log(f"https local SSL verify bypass enabled for host: {urllib.parse.urlsplit(target).hostname}")
        except Exception:
            pass
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)
    return urllib.request.urlopen(req, timeout=timeout)


def _http_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": APP_USER_AGENT, "Accept": "application/json"},
    )
    with _urlopen_with_context(req, timeout=30) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8-sig", errors="replace"))


def _download_file(url: str, dest: Path) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": APP_USER_AGENT})
    with _urlopen_with_context(req, timeout=60) as resp:
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            while True:
                chunk = resp.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
    return dest


def _manifest_direct_path(row: dict) -> Path | None:
    """Return an existing local/NAS path from a manifest row, if available."""
    for key in ("path", "local_path", "file_path", "unc_path"):
        raw = str((row or {}).get(key) or "").strip()
        if not raw:
            continue
        try:
            path = Path(raw).expanduser()
            if path.exists() and path.is_file():
                return path
        except Exception:
            continue
    return None


def _cleanup_old_share_dirs(root: Path, max_age_days: int = 7) -> None:
    deadline = time.time() - (max_age_days * 86400)
    try:
        for child in root.iterdir():
            if not child.is_dir():
                continue
            try:
                if child.stat().st_mtime < deadline:
                    for item in child.rglob("*"):
                        if item.is_file():
                            item.unlink(missing_ok=True)
                    for item in sorted(child.rglob("*"), reverse=True):
                        if item.is_dir():
                            item.rmdir()
                    child.rmdir()
            except Exception:
                continue
    except Exception:
        pass


def prepare_files_from_manifest(manifest_url: str, dry_run: bool = False) -> list[Path]:
    data = _http_json(manifest_url)
    if not data.get("ok"):
        raise RuntimeError(data.get("error") or "Paylasim listesi okunamadi.")
    token_hint = ""
    try:
        token_hint = Path(urllib.parse.urlparse(manifest_url).path).parts[-2]
    except Exception:
        token_hint = ""
    stamp = time.strftime("%Y%m%d_%H%M%S")
    patient = _safe_file_name(data.get("patient_key") or "hasta", "hasta")
    visit = _safe_file_name(data.get("visit_key") or stamp, stamp)
    files: list[Path] = []
    downloads_needed: list[tuple[int, dict, str]] = []
    for index, row in enumerate(data.get("files") or []):
        if not isinstance(row, dict):
            continue
        direct_path = _manifest_direct_path(row)
        if direct_path is not None:
            files.append(direct_path)
            continue
        name = _safe_file_name(row.get("name") or f"dosya-{index + 1}", f"dosya-{index + 1}")
        url = urllib.parse.urljoin(manifest_url, row.get("download_url") or row.get("url") or "")
        if not url:
            continue
        downloads_needed.append((index, row, url))

    if files:
        log(f"{len(files)} dosya NAS/yerel yoldan dogrudan kullanilacak; indirme atlandi.")

    if downloads_needed:
        root = Path(tempfile.gettempdir()) / "YazKlinikWhatsAppShare"
        _cleanup_old_share_dirs(root)
        target_dir = root / f"{patient}_{visit}_{token_hint[:10] or stamp}"
        target_dir.mkdir(parents=True, exist_ok=True)
    else:
        target_dir = None

    for index, row, url in downloads_needed:
        name = _safe_file_name(row.get("name") or f"dosya-{index + 1}", f"dosya-{index + 1}")
        dest = target_dir / f"{index + 1:02d}_{name}"
        if dry_run:
            files.append(dest)
            continue
        log(f"NAS yolu gorunmedi, HTTP yedek indiriliyor: {name}")
        files.append(_download_file(url, dest))
    return [p for p in files if dry_run or p.exists()]


def win32_copy_files_to_clipboard(paths: list[Path]) -> None:
    if os.name != "nt":
        raise RuntimeError("Windows dosya panosu sadece Windows'ta desteklenir.")
    real_paths = [str(Path(p).resolve()) for p in paths if Path(p).exists()]
    if not real_paths:
        raise RuntimeError("Panoya kopyalanacak dosya yok.")

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = ctypes.c_void_p
    kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
    kernel32.GlobalUnlock.restype = ctypes.c_int
    kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
    kernel32.GlobalFree.restype = ctypes.c_void_p
    user32.OpenClipboard.argtypes = [ctypes.c_void_p]
    user32.OpenClipboard.restype = ctypes.c_int
    user32.EmptyClipboard.argtypes = []
    user32.EmptyClipboard.restype = ctypes.c_int
    user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
    user32.SetClipboardData.restype = ctypes.c_void_p
    user32.CloseClipboard.argtypes = []
    user32.CloseClipboard.restype = ctypes.c_int

    CF_HDROP = 15
    GMEM_MOVEABLE = 0x0002
    GMEM_ZEROINIT = 0x0040
    file_list = ("\0".join(real_paths) + "\0\0").encode("utf-16le")
    header = struct.pack("<IiiII", 20, 0, 0, 0, 1)
    payload = header + file_list
    h_mem = kernel32.GlobalAlloc(GMEM_MOVEABLE | GMEM_ZEROINIT, len(payload))
    if not h_mem:
        raise RuntimeError("GlobalAlloc basarisiz.")

    handed_to_clipboard = False
    try:
        ptr = kernel32.GlobalLock(h_mem)
        if not ptr:
            raise RuntimeError("GlobalLock basarisiz.")
        try:
            ctypes.memmove(ptr, payload, len(payload))
        finally:
            kernel32.GlobalUnlock(h_mem)

        for _ in range(12):
            if user32.OpenClipboard(None):
                break
            time.sleep(0.12)
        else:
            raise RuntimeError("Windows clipboard acilamadi.")
        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(CF_HDROP, h_mem):
                raise RuntimeError("SetClipboardData(CF_HDROP) basarisiz.")
            handed_to_clipboard = True
        finally:
            user32.CloseClipboard()
    finally:
        if not handed_to_clipboard and h_mem:
            kernel32.GlobalFree(h_mem)


def win32_clipboard_has_files() -> bool:
    if os.name != "nt":
        return False
    try:
        CF_HDROP = 15
        return bool(ctypes.windll.user32.IsClipboardFormatAvailable(CF_HDROP))
    except Exception:
        return False


def _keybd_event(vk: int, down: bool) -> None:
    flags = 0 if down else 0x0002
    ctypes.windll.user32.keybd_event(vk, 0, flags, 0)


def _send_ctrl_v() -> None:
    if os.name != "nt":
        return
    try:
        _keybd_event(0x11, False)
        _keybd_event(0x56, False)
    except Exception:
        pass
    try:
        time.sleep(0.08)
        _keybd_event(0x11, True)
        time.sleep(0.06)
        _keybd_event(0x56, True)
        time.sleep(0.10)
        _keybd_event(0x56, False)
        time.sleep(0.06)
        _keybd_event(0x11, False)
        log("Ctrl+V keybd_event ile gonderildi.")
        return
    except Exception as ex:
        log(f"keybd_event hata verdi, SendKeys yedegi deneniyor: {ex}")
    try:
        cmd = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "$ws = New-Object -ComObject WScript.Shell; "
            "foreach($t in @('WhatsApp','web.whatsapp','Google Chrome','Microsoft Edge')){"
            "  try { if($ws.AppActivate($t)){ Start-Sleep -Milliseconds 300; break } } catch {}"
            "} "
            "[System.Windows.Forms.SendKeys]::SendWait('^v')"
        )
        completed = subprocess.run(
            [
                "powershell", "-NoProfile", "-STA",
                "-ExecutionPolicy", "Bypass", "-Command", cmd,
            ],
            timeout=6,
            capture_output=True,
            text=True,
            creationflags=0x08000000,
        )
        if completed.returncode == 0:
            log("Ctrl+V SendKeys ile gonderildi.")
            return
        log("SendKeys basarisiz, keybd_event yedegi deneniyor: " +
            ((completed.stderr or completed.stdout or "").strip()[:300]))
    except Exception as ex:
        log(f"SendKeys hata verdi, keybd_event yedegi deneniyor: {ex}")
    time.sleep(0.05)
    _keybd_event(0x11, True)
    time.sleep(0.04)
    _keybd_event(0x56, True)
    time.sleep(0.08)
    _keybd_event(0x56, False)
    time.sleep(0.04)
    _keybd_event(0x11, False)


def _stabilize_whatsapp_focus(timeout: float = 18.0) -> bool:
    terms = ["whatsapp", "web.whatsapp", "google chrome", "microsoft edge", "chrome", "edge"]
    hwnd = _find_window_with_any_title(terms, timeout=timeout)
    if not hwnd:
        log("WhatsApp/Browser penceresi bulunamadi; aktif pencereye paste denenebilir.")
        return False
    ok = False
    for _ in range(3):
        ok = _focus_window(hwnd) or ok
        time.sleep(0.35)
    log(f"WhatsApp/Browser penceresi odaklandi hwnd={hwnd} ok={ok}.")
    return ok


def _send_enter() -> None:
    if os.name != "nt":
        return
    _keybd_event(0x0D, True)
    _keybd_event(0x0D, False)


def _find_window_with_title(term: str, timeout: float = 8.0) -> int | None:
    if os.name != "nt":
        return None
    term = (term or "").lower()
    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

    user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.c_void_p]
    user32.EnumWindows.restype = ctypes.c_int
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.GetWindow.restype = ctypes.c_void_p

    found: list[int] = []

    def callback(hwnd, _param):
        try:
            if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):
                return True
            buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, buf, 512)
            title = (buf.value or "").lower()
            if term in title:
                found.append(int(hwnd))
                return False
        except Exception:
            return True
        return True

    deadline = time.time() + timeout
    cb = WNDENUMPROC(callback)
    while time.time() < deadline:
        found.clear()
        try:
            user32.EnumWindows(cb, None)
        except Exception:
            return None
        if found:
            return found[0]
        time.sleep(0.25)
    return None


def _find_window_with_any_title(terms: list[str], timeout: float = 10.0) -> int | None:
    if os.name != "nt":
        return None
    terms = [str(t or "").lower() for t in terms if str(t or "").strip()]
    if not terms:
        return None
    user32 = ctypes.windll.user32
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    user32.EnumWindows.argtypes = [WNDENUMPROC, ctypes.c_void_p]
    user32.EnumWindows.restype = ctypes.c_int
    user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
    user32.IsWindowVisible.restype = ctypes.c_int
    user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
    user32.GetWindowTextW.restype = ctypes.c_int
    user32.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
    user32.GetWindow.restype = ctypes.c_void_p

    def scan_once() -> int | None:
        matches: dict[int, list[int]] = {i: [] for i in range(len(terms))}

        def callback(hwnd, _param):
            try:
                if not user32.IsWindowVisible(hwnd) or user32.GetWindow(hwnd, 4):
                    return True
                buf = ctypes.create_unicode_buffer(512)
                user32.GetWindowTextW(hwnd, buf, 512)
                title = (buf.value or "").lower()
                for idx, term in enumerate(terms):
                    if term in title:
                        matches[idx].append(int(hwnd))
                        if idx == 0:
                            return False
                        break
            except Exception:
                return True
            return True

        cb = WNDENUMPROC(callback)
        try:
            user32.EnumWindows(cb, None)
        except Exception:
            return None
        for idx in range(len(terms)):
            if matches[idx]:
                return matches[idx][0]
        return None

    deadline = time.time() + max(0.2, float(timeout or 0))
    while time.time() < deadline:
        hwnd = scan_once()
        if hwnd:
            return hwnd
        time.sleep(0.25)
    return scan_once()


def _focus_window(hwnd: int | None) -> bool:
    if os.name != "nt" or not hwnd:
        return False
    user32 = ctypes.windll.user32
    try:
        _keybd_event(0x12, True)
        _keybd_event(0x12, False)
        user32.ShowWindow(hwnd, 9)
        try:
            user32.SwitchToThisWindow(hwnd, True)
            time.sleep(0.15)
        except Exception:
            pass
        _keybd_event(0x12, True)
        _keybd_event(0x12, False)
        user32.ShowWindow(hwnd, 5)
        user32.BringWindowToTop(hwnd)
        return bool(user32.SetForegroundWindow(hwnd))
    except Exception:
        return False


def _tasklist_has_image(image_name: str) -> bool:
    if os.name != "nt":
        return False
    image_name = str(image_name or "").strip()
    if not image_name:
        return False
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", f"IMAGENAME eq {image_name}", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=0x08000000,
        )
        if completed.returncode != 0:
            return False
        out = (completed.stdout or "").strip().lower()
        return image_name.lower() in out and "no tasks are running" not in out
    except Exception:
        return False


def _wait_whatsapp_desktop_window(timeout: float = 8.0) -> int | None:
    if os.name != "nt":
        return None
    deadline = time.time() + max(0.5, float(timeout or 0))
    while time.time() < deadline:
        if _tasklist_has_image("WhatsApp.exe"):
            hwnd = _find_window_with_any_title(["whatsapp"], timeout=0.6)
            if hwnd:
                return hwnd
        time.sleep(0.25)
    return None


def open_whatsapp(phone: str, app_url: str = "", web_url: str = "", allow_web_fallback: bool = False) -> str:
    """B202: allow_web_fallback default=False. Eskiden App pencere 4.8 sn'de
    gorunmezse otomatik Web acilir, App de yavas yavas acilirsa cift WhatsApp
    olusurdu. Artik default sadece App denenir; Web fallback sadece caller
    explicitly istiyorsa acilir. Caller hatadan haberdar olur, kullanici
    isterse manuel Web butonuna basar.
    """
    digits = _clean_digits(phone)
    app_url = app_url or (f"whatsapp://send?phone={digits}" if digits else "whatsapp://send")
    web_url = web_url or (f"https://web.whatsapp.com/send?phone={digits}" if digits else "https://web.whatsapp.com/")
    if os.name == "nt":
        try:
            os.startfile(app_url)  # type: ignore[attr-defined]
            hwnd = _wait_whatsapp_desktop_window(timeout=6.0)
            if hwnd:
                _focus_window(hwnd)
                return "app"
            if _tasklist_has_image("WhatsApp.exe"):
                log("WhatsApp Desktop sureci calisiyor (pencere yavas geldi); app akisiyla devam.")
                return "app"
            log("WhatsApp Desktop pencere dogrulanamadi.")
        except Exception as ex:
            log(f"whatsapp:// acilamadi: {ex}")
    if not allow_web_fallback:
        # Cift acilmayi engellemek icin web fallback'i kapatildi.
        # Caller "app_failed" gorurse kullaniciya manuel WhatsApp Web butonu sunar.
        log("Web fallback devre disi (allow_web_fallback=False); 'app_failed' donuluyor.")
        return "app_failed"
    if os.name == "nt":
        try:
            os.startfile(web_url)  # type: ignore[attr-defined]
        except Exception:
            webbrowser.open(web_url)
    else:
        webbrowser.open(web_url)
    return "web"


def run_helper(args: argparse.Namespace) -> int:
    files = prepare_files_from_manifest(args.manifest, dry_run=args.dry_run)
    if not files:
        raise RuntimeError("Paylasilacak dosya bulunamadi.")
    if args.dry_run:
        print(json.dumps({
            "ok": True,
            "dry_run": True,
            "count": len(files),
            "files": [str(p) for p in files],
            "phone": _clean_digits(args.phone),
            "auto_send": bool(args.auto_send),
        }, ensure_ascii=False))
        return 0
    win32_copy_files_to_clipboard(files)
    if not win32_clipboard_has_files():
        log("Clipboard CF_HDROP dogrulanamadi; dosyalar tekrar kopyalaniyor.")
        time.sleep(0.35)
        win32_copy_files_to_clipboard(files)
    if not win32_clipboard_has_files():
        raise RuntimeError("Dosyalar Windows panosunda dogrulanamadi.")
    log(f"{len(files)} dosya Windows panosuna kopyalandi.")
    # B202: allow_web_fallback=False - cift acilmayi engellemek icin sadece App.
    launch_kind = open_whatsapp(args.phone, args.app_url, args.web_url, allow_web_fallback=False)
    if launch_kind == "app_failed":
        log("WhatsApp App acilamadi; paste atlandi. Dosyalar panoda; doktor manuel WhatsApp Web butonuna basabilir.")
        return 0
    if not args.no_paste:
        base_delay = max(1.0, float(args.paste_delay))
        if launch_kind == "web":
            base_delay = max(base_delay, 9.0)
        else:
            base_delay = max(base_delay, 4.5)
        time.sleep(base_delay)
        focused = _stabilize_whatsapp_focus(timeout=20.0 if launch_kind == "web" else 14.0)
        if launch_kind == "web" and not focused:
            time.sleep(0.9)
            focused = _stabilize_whatsapp_focus(timeout=8.0)
        # B202: WhatsApp foreground dogrula - eger SetForegroundWindow basarisizsa
        # Ctrl+V baska pencereye gider (browser, Notepad, vs.). focused False ise
        # paste yapmamak daha guvenli.
        if not focused:
            log("WhatsApp penceresi foreground'a alinmadi; Ctrl+V atlandi (yanlis pencereye yapistirma riski). Doktor manuel Ctrl+V yapsin.")
            return 0
        if not win32_clipboard_has_files():
            log("Paste oncesi CF_HDROP kayboldu; dosyalar tekrar panoya aliniyor.")
            win32_copy_files_to_clipboard(files)
            time.sleep(0.25)
            if not win32_clipboard_has_files():
                log("Pano hala dosya icermiyor; Ctrl+V atlandi.")
                return 0
        _send_ctrl_v()
        log(f"Ctrl+V gonderildi ({launch_kind}).")
        if args.auto_send:
            time.sleep(max(0.8, float(args.send_delay)))
            _send_enter()
            log("Enter/Gonder tusu denendi.")
    return 0


def parse_args(argv: list[str]) -> argparse.Namespace:
    if len(argv) >= 2 and argv[1].lower().startswith(CUSTOM_SCHEME + ":"):
        parsed = urllib.parse.urlparse(argv[1])
        query = urllib.parse.parse_qs(parsed.query)
        return argparse.Namespace(
            manifest=(query.get("manifest") or [""])[0],
            phone=(query.get("phone") or [""])[0],
            app_url=(query.get("app") or [""])[0],
            web_url=(query.get("web") or [""])[0],
            paste_delay=float((query.get("delay") or ["7"])[0] or 7),
            auto_send=(query.get("send") or ["0"])[0] in {"1", "true", "True"},
            send_delay=float((query.get("send_delay") or ["3"])[0] or 3),
            no_paste=(query.get("paste") or ["1"])[0] in {"0", "false", "False"},
            dry_run=(query.get("dry_run") or ["0"])[0] in {"1", "true", "True"},
        )
    parser = argparse.ArgumentParser(description="YazKlinik WhatsApp local share helper")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--phone", default="")
    parser.add_argument("--app-url", default="")
    parser.add_argument("--web-url", default="")
    parser.add_argument("--paste-delay", type=float, default=7.0)
    parser.add_argument("--auto-send", action="store_true")
    parser.add_argument("--send-delay", type=float, default=3.0)
    parser.add_argument("--no-paste", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args(argv[1:])


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        if not args.manifest:
            raise RuntimeError("Manifest URL bos.")
        return run_helper(args)
    except Exception as ex:
        log(f"HATA: {ex}")
        return 1


def _outbox_path() -> Path:
    """Server-side WhatsApp outbox queue (JSON-Lines).
    Client helper bunu periyodik okur, WhatsApp Desktop ile gonderir."""
    base = Path(os.environ.get("YAZKLINIK_WA_OUTBOX",
                                r"D:\YazKlinik_Final_D500\runtime_state\wa_outbox.jsonl"))
    base.parent.mkdir(parents=True, exist_ok=True)
    return base


def send_whatsapp_message(phone: str, text: str,
                            patient_id: str = "",
                            metadata: dict | None = None) -> dict:
    """Server-side: WhatsApp mesajini outbox kuyruguna yazar.

    Backend (cron veya WatsapDesktop ajan) outbox'i okuyup gercek gonderim
    yapar. Asagidaki Session 7 ajanlari bunu cagiriyor:
        - yazklinik_hatira_usg_agent
        - yazklinik_memnuniyet_agent
        - yazklinik_pubmed_cron_agent
        - yazklinik_backup_verify_agent

    Returns: {ok, queued_at, phone (maskeli), id}
    """
    digits = _clean_digits(phone or "")
    if not digits or not (text or "").strip():
        return {"ok": False, "error": "phone veya text eksik"}
    record = {
        "id": time.strftime("WA%Y%m%d%H%M%S") + str(int(time.time() * 1000))[-4:],
        "phone": digits,
        "text": text,
        "patient_id": patient_id,
        "metadata": metadata or {},
        "queued_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "type": "text",
        "status": "queued",
    }
    try:
        with _outbox_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        log(f"WA queued -> {digits[:3]}***{digits[-2:]}: {text[:40]}")
        return {"ok": True, "queued_at": record["queued_at"],
                "phone": f"{digits[:3]}***{digits[-2:]}", "id": record["id"]}
    except Exception as ex:
        log(f"WA queue HATA: {ex}")
        return {"ok": False, "error": str(ex)}


def send_whatsapp_message_with_image(phone: str, text: str,
                                       image_path: str,
                                       patient_id: str = "") -> dict:
    """Server-side: Resimli WhatsApp mesajini outbox'a yazar."""
    digits = _clean_digits(phone or "")
    if not digits or not (text or "").strip():
        return {"ok": False, "error": "phone veya text eksik"}
    if not image_path or not os.path.exists(image_path):
        return {"ok": False, "error": f"image_path yok: {image_path}"}
    record = {
        "id": time.strftime("WA%Y%m%d%H%M%S") + str(int(time.time() * 1000))[-4:],
        "phone": digits,
        "text": text,
        "patient_id": patient_id,
        "image_path": image_path,
        "queued_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "type": "image",
        "status": "queued",
    }
    try:
        with _outbox_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        log(f"WA image queued -> {digits[:3]}***{digits[-2:]}: {image_path}")
        return {"ok": True, "queued_at": record["queued_at"],
                "phone": f"{digits[:3]}***{digits[-2:]}", "id": record["id"]}
    except Exception as ex:
        log(f"WA image queue HATA: {ex}")
        return {"ok": False, "error": str(ex)}


def read_outbox(limit: int = 50) -> list[dict]:
    """Cron/Daemon icin: bekleyen mesajlari oku."""
    out_path = _outbox_path()
    if not out_path.exists():
        return []
    items = []
    try:
        with out_path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    pass
        return items[:limit]
    except Exception:
        return []


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
