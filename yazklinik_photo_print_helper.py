#!/usr/bin/env python3
"""Open Windows photo printing for a real image file.

This helper is intentionally small because it is launched from WebShell via
the yazklinik-print-photo:// scheme. The important bit is that Windows receives
an actual .jpg/.jpeg/.png path, not an HTML preview page.
"""
from __future__ import annotations

import os
import ipaddress
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path


CUSTOM_SCHEME = "yazklinik-print-photo"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".gif", ".tif", ".tiff"}


def _log(message: str) -> None:
    try:
        base = Path(tempfile.gettempdir()) / "YazKlinikPhotoPrint"
        base.mkdir(parents=True, exist_ok=True)
        with (base / "photo_print.log").open("a", encoding="utf-8") as fh:
            fh.write(time.strftime("%Y-%m-%dT%H:%M:%S ") + str(message) + "\n")
    except Exception:
        pass


def _printer_name_from_url(url: str) -> str:
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
        return (qs.get("printer") or [""])[0].strip()
    except Exception:
        return ""


def _action_from_url(url: str) -> str:
    try:
        parsed = urllib.parse.urlsplit(str(url or ""))
        qs = urllib.parse.parse_qs(parsed.query)
        action = (qs.get("action") or [parsed.netloc or parsed.path or "print"])[0]
        action = str(action or "print").strip().lower()
        if action in {"open", "preview", "view"}:
            return "preview"
    except Exception:
        pass
    return "print"


def _source_url_from_arg(url: str) -> str:
    try:
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(str(url or "")).query)
        return (qs.get("src") or qs.get("url") or [""])[0].strip()
    except Exception:
        return ""


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
            _log(f"https local SSL verify bypass enabled for host: {urllib.parse.urlsplit(target).hostname}")
        except Exception:
            pass
        return urllib.request.urlopen(req, timeout=timeout, context=ctx)
    return urllib.request.urlopen(req, timeout=timeout)


def _file_path_from_arg(value: str) -> Path:
    value = str(value or "").strip()
    if value.lower().startswith(CUSTOM_SCHEME + "://"):
        qs = urllib.parse.parse_qs(urllib.parse.urlsplit(value).query)
        value = (qs.get("file") or qs.get("path") or [""])[0]
    value = urllib.parse.unquote(value).strip().strip('"')
    return Path(value)


def _looks_like_image_bytes(data: bytes) -> bool:
    if not data:
        return False
    head = data[:32]
    return (
        head.startswith(b"\xff\xd8\xff") or
        head.startswith(b"\x89PNG\r\n\x1a\n") or
        head.startswith((b"GIF87a", b"GIF89a")) or
        head.startswith(b"BM") or
        head.startswith((b"II*\x00", b"MM\x00*")) or
        (head.startswith(b"RIFF") and b"WEBP" in head[:16])
    )


def _is_valid_image_payload(data: bytes, content_type: str = "") -> bool:
    ctype = str(content_type or "").split(";", 1)[0].strip().lower()
    if ctype.startswith("image/") and data:
        return True
    if _looks_like_image_bytes(data):
        return True
    try:
        from PIL import Image
        from io import BytesIO
        Image.open(BytesIO(data)).verify()
        return True
    except Exception:
        return False


def _download_image_to_temp(src_url: str, fallback_name: str = "yazklinik-photo.jpg") -> Path | None:
    src_url = str(src_url or "").strip()
    if not src_url.lower().startswith(("http://", "https://")):
        return None
    try:
        name = Path(urllib.parse.urlsplit(src_url).path).name or fallback_name
        suffix = Path(name).suffix.lower()
        if suffix not in IMAGE_EXTS:
            suffix = ".jpg"
        safe = "".join(c if c.isalnum() or c in "._-" else "_" for c in Path(name).stem)[:70] or "yazklinik-photo"
        req = urllib.request.Request(src_url, headers={"User-Agent": "YazKlinik-PhotoPrint/1.0"})
        with _urlopen_with_context(req, timeout=45) as resp:
            content_type = resp.headers.get("Content-Type", "")
            data = resp.read()
        if not _is_valid_image_payload(data, content_type):
            _log(
                "download rejected: response is not an image "
                f"ctype={content_type!r} bytes={len(data) if data else 0} url={src_url}"
            )
            return None
        ctype = str(content_type or "").lower()
        if suffix in {".webp", ".gif", ".tif", ".tiff"} or "webp" in ctype:
            try:
                from PIL import Image
                from io import BytesIO
                buf = BytesIO()
                with Image.open(BytesIO(data)) as img:
                    img = img.convert("RGB")
                    img.save(buf, format="JPEG", quality=95, optimize=True)
                data = buf.getvalue()
                suffix = ".jpg"
                _log("download normalized to jpg for Windows Photos compatibility")
            except Exception as ex:
                _log(f"download normalization skipped: {ex}")
        dest = Path(tempfile.gettempdir()) / f"YazKlinikPhotoPrint_{int(time.time())}_{safe}{suffix}"
        dest.write_bytes(data)
        _log(f"downloaded src to temp: {dest}")
        return dest
    except Exception as ex:
        _log(f"download src failed: {ex}")
        return None


def _open_hiti_preferences(printer_name: str) -> None:
    printer_name = str(printer_name or "").strip()
    if not printer_name or os.name != "nt":
        return
    for cmd in (
        ["rundll32", "printui.dll,PrintUIEntry", "/e", "/n", printer_name],
        ["rundll32", "printui.dll,PrintUIEntry", "/p", "/n", printer_name],
    ):
        try:
            subprocess.Popen(cmd, shell=False)
            time.sleep(0.4)
            return
        except Exception:
            continue


def _system32_dll(name: str) -> str:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    candidate = Path(root) / "System32" / name
    return str(candidate) if candidate.exists() else name


def _photo_print_commands(path: Path, preferred_printer: str = "") -> list[list[str]]:
    """Build Windows commands that receive the actual JPG file path."""
    printer = str(preferred_printer or "").strip()
    shimgvw = _system32_dll("shimgvw.dll")
    commands: list[list[str]] = []
    # First open the Windows photo print wizard/preview so the doctor can
    # confirm HiTi 525L and 6x8. Direct PrintTo/MSPaint are only fallbacks.
    commands.append(["rundll32.exe", f"{shimgvw},ImageView_PrintTo", str(path)])
    if printer:
        commands.append([
            "rundll32.exe",
            f"{shimgvw},ImageView_PrintTo",
            str(path),
            printer,
        ])
        commands.append(["mspaint.exe", "/pt", str(path), printer])
    return commands


def open_photo_print_dialog(
    image_path: str | Path,
    preferred_printer: str = "",
    open_preferences: bool = False,
) -> tuple[bool, str]:
    path = Path(image_path)
    try:
        path = path.resolve()
    except Exception:
        pass
    if not path.exists() or not path.is_file():
        return False, f"Resim dosyasi bulunamadi: {path}"
    if path.suffix.lower() not in IMAGE_EXTS:
        return False, f"Bu dosya resim/JPEG olarak yazdirilamaz: {path.name}"
    if os.name != "nt":
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(path))
                return True, "Resim dosyasi acildi."
        except Exception as ex:
            return False, str(ex)
        return False, "JPEG foto baski yardimcisi Windows icin hazirlandi."

    if open_preferences:
        _open_hiti_preferences(preferred_printer)

    # D78: "Foto Yazdir" once Windows'un resim yazdirma sihirbazini acar.
    # Sadece resmi onizlemede acip basarili saymak doktorun yazdiramamasina
    # neden oluyordu. Komutlar dogrudan gercek JPG dosya yolunu alir.
    attempts = _photo_print_commands(path, preferred_printer) + [None]
    last_error = ""
    for cmd in attempts:
        try:
            if cmd is None:
                _log(f"startfile print: {path}")
                os.startfile(str(path), "print")
            else:
                _log("command: " + " ".join(f'"{p}"' if " " in str(p) else str(p) for p in cmd))
                subprocess.Popen(cmd, shell=False)
            printer_hint = f" {preferred_printer} / 6x8 secin." if preferred_printer else " 6x8 foto kagidi secin."
            return True, "JPG/JPEG dosyasi Windows foto baski akisi ile yaziciya gonderildi." + printer_hint
        except Exception as ex:
            last_error = str(ex)
            _log(f"failed: {last_error}")

    # Son care: en azindan resmi ac, kullanici elle Ctrl+P yapabilsin.
    try:
        _log(f"startfile preview fallback after print failure: {path}")
        os.startfile(str(path))
        return True, "JPEG dosyasi acildi; acilan pencereden Yazdir secin."
    except Exception as ex:
        return False, last_error or str(ex)


def open_photo_preview(image_path: str | Path) -> tuple[bool, str]:
    path = Path(image_path)
    try:
        path = path.resolve()
    except Exception:
        pass
    if not path.exists() or not path.is_file():
        return False, f"Resim dosyasi bulunamadi: {path}"
    if path.suffix.lower() not in IMAGE_EXTS:
        return False, f"Bu dosya resim/JPEG olarak acilamaz: {path.name}"
    if os.name == "nt" and hasattr(os, "startfile"):
        try:
            _log(f"startfile preview: {path}")
            os.startfile(str(path))  # type: ignore[attr-defined]
            return True, "JPEG dosyasi Windows Foto onizlemede acildi. Ctrl+P ile foto baski penceresini acin."
        except Exception as ex:
            return False, str(ex)
    return False, "Foto onizleme sadece Windows masaustu oturumunda acilir."


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Kullanim: yazklinik_photo_print_helper.py <dosya-veya-url>")
        return 2
    raw = argv[1]
    path = _file_path_from_arg(raw)
    if not path.exists() or not path.is_file():
        downloaded = _download_image_to_temp(_source_url_from_arg(raw), path.name or "yazklinik-photo.jpg")
        if downloaded:
            path = downloaded
    action = _action_from_url(raw)
    printer = _printer_name_from_url(raw)
    if action == "preview":
        ok, message = open_photo_preview(path)
    else:
        ok, message = open_photo_print_dialog(path, printer, open_preferences=True)
    print(message)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
