#!/usr/bin/env python3
"""YazKlinik v1000 cross-platform desktop shell.

This is the new Windows/macOS desktop entry point. It deliberately treats the
Flask web UI as the source of truth and wraps it in a professional clinical
workbench instead of reviving the old native v68 desktop surface.
"""

from __future__ import annotations

import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


DESKTOP_RUNTIME_MODES = {"hybrid", "mirror", "shell"}
TERMINAL_TOKEN = os.environ.get("YAZKLINIK_TERMINAL_TOKEN", "")

try:
    from yazklinik_feature_sync import (
        desktop_menu_categories as _sync_desktop_menu_categories,
        desktop_route_groups as _sync_desktop_route_groups,
        doctor_control_routes as _sync_doctor_control_routes,
        route_category as _sync_route_category,
        simple_control_routes as _sync_simple_control_routes,
    )
except Exception:
    _sync_desktop_menu_categories = None
    _sync_desktop_route_groups = None
    _sync_doctor_control_routes = None
    _sync_route_category = None
    _sync_simple_control_routes = None


def _yk_state_root() -> Path:
    raw = (os.environ.get("YAZKLINIK_STATE_ROOT") or "").strip()
    return Path(raw).expanduser() if raw else Path(__file__).resolve().parent / "runtime_state"


def _normalize_desktop_runtime_mode(value: str, default: str = "hybrid") -> str:
    value = (value or "").strip().lower()
    return value if value in DESKTOP_RUNTIME_MODES else default


def _desktop_runtime_mode_paths_pre_qt() -> list[Path]:
    paths = []
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app and os.environ.get("YAZKLINIK_WRITE_LOCALAPPDATA_STATE") == "1":
        paths.append(Path(local_app) / "YazKlinik" / "desktop_mode.txt")
    paths.append(Path(__file__).resolve().parent / "desktop_mode.txt")
    return paths


def _write_desktop_runtime_mode_files(mode: str) -> str:
    mode = _normalize_desktop_runtime_mode(mode, "hybrid")
    for path in _desktop_runtime_mode_paths_pre_qt():
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(mode + "\n", encoding="ascii")
        except Exception:
            pass
    return mode


def _pre_qt_server_url_candidates() -> list[str]:
    candidates = [
        os.environ.get("YAZKLINIK_SERVER_URL", "").strip().rstrip("/"),
        os.environ.get("YAZKLINIK_WEB_URL", "").strip().rstrip("/"),
        os.environ.get("YAZKLINIK_AI_SERVER_URL", "").strip().rstrip("/"),
        os.environ.get("YAZKLINIK_DEFAULT_SERVER_URL", "").strip().rstrip("/"),
    ]
    local_app = os.environ.get("LOCALAPPDATA")
    file_candidates = [
        Path(__file__).resolve().parent / "terminal_server_url.txt",
        _yk_state_root() / "terminal_server_url.txt",
    ]
    if local_app:
        base = Path(local_app) / "YazKlinik"
        file_candidates.extend([
            base / "terminal_server_url.txt",
            base / "server_actual_url.txt",
            base / "Server" / "terminal_server_url.txt",
        ])
    for path in file_candidates:
        try:
            if path.exists():
                candidates.append(path.read_text(
                    encoding="utf-8", errors="ignore").strip().rstrip("/"))
        except Exception:
            pass
    return [c for c in candidates if c and c.startswith(("http://", "https://"))]


def _pre_qt_media_secure_origins() -> list[str]:
    port = (os.environ.get("YAZKLINIK_WEB_PORT") or "5443").strip() or "5443"
    candidates = [
        f"http://localhost:{port}",
        f"http://127.0.0.1:{port}",
        "https://192.168.1.40:5443",
    ]
    candidates.extend(_pre_qt_server_url_candidates())
    origins: list[str] = []
    seen: set[str] = set()
    for value in candidates:
        try:
            parsed = urllib.parse.urlsplit((value or "").strip().rstrip("/"))
            origin = (
                f"{parsed.scheme}://{parsed.netloc}"
                if parsed.scheme and parsed.netloc else "")
        except Exception:
            origin = ""
        if origin and origin not in seen:
            seen.add(origin)
            origins.append(origin)
    return origins


def _server_desktop_runtime_mode_pre_qt(timeout: float = 1.2) -> str:
    for base_url in _pre_qt_server_url_candidates():
        try:
            req = urllib.request.Request(
                base_url + "/api/terminal/performance",
                headers={"X-Terminal-Token": TERMINAL_TOKEN})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(
                    resp.read().decode("utf-8", errors="replace") or "{}")
            mode = _normalize_desktop_runtime_mode(
                str(payload.get("desktop_runtime_mode") or ""), "")
            if mode:
                return mode
        except Exception:
            pass
    return ""


def _read_desktop_runtime_mode_pre_qt(default: str = "hybrid") -> str:
    mode = ""
    force_env = os.environ.get("YAZKLINIK_DESKTOP_MODE_FORCE", "").strip() == "1"
    if force_env:
        mode = os.environ.get("YAZKLINIK_DESKTOP_MODE", "")
    if not mode and not force_env:
        mode = _server_desktop_runtime_mode_pre_qt()
    if not mode:
        for path in _desktop_runtime_mode_paths_pre_qt():
            try:
                if path.exists():
                    mode = path.read_text(
                        encoding="ascii", errors="ignore").strip()
                    if mode:
                        break
            except Exception:
                pass
    if not mode:
        mode = os.environ.get("YAZKLINIK_DESKTOP_MODE", "")
    return _write_desktop_runtime_mode_files(
        _normalize_desktop_runtime_mode(mode, default))


def _apply_desktop_runtime_mode_env(mode: str) -> str:
    mode = _normalize_desktop_runtime_mode(mode, "hybrid")
    os.environ["YAZKLINIK_DESKTOP_MODE"] = mode
    os.environ.setdefault("YAZKLINIK_DESKTOP_FAST_START", "1")
    os.environ.setdefault("YAZKLINIK_DESKTOP_START_ROUTE", "/giris")
    if mode == "mirror":
        os.environ["YAZKLINIK_DESKTOP_WEB_MIRROR"] = "1"
        os.environ["YAZKLINIK_DESKTOP_WEB_SHELL"] = "1"
        os.environ["YAZKLINIK_DESKTOP_ENABLE_WEBENGINE"] = "1"
        os.environ["YAZKLINIK_DESKTOP_DISABLE_WEBENGINE"] = "0"
        os.environ["YAZKLINIK_DESKTOP_WEB_CENTER_FIRST"] = "1"
    elif mode == "shell":
        os.environ["YAZKLINIK_DESKTOP_WEB_MIRROR"] = "0"
        os.environ["YAZKLINIK_DESKTOP_WEB_SHELL"] = "1"
        os.environ["YAZKLINIK_DESKTOP_ENABLE_WEBENGINE"] = "1"
        os.environ["YAZKLINIK_DESKTOP_DISABLE_WEBENGINE"] = "0"
        os.environ["YAZKLINIK_DESKTOP_WEB_CENTER_FIRST"] = "1"
    else:
        # Hybrid is the doctor-facing Windows shell: native chrome outside,
        # the real Flask web UI embedded in the center, and API panels around it.
        os.environ["YAZKLINIK_DESKTOP_WEB_MIRROR"] = "0"
        os.environ["YAZKLINIK_DESKTOP_WEB_SHELL"] = "1"
        os.environ["YAZKLINIK_DESKTOP_ENABLE_WEBENGINE"] = "1"
        os.environ["YAZKLINIK_DESKTOP_DISABLE_WEBENGINE"] = "0"
        os.environ["YAZKLINIK_DESKTOP_WEB_CENTER_FIRST"] = "1"
    return mode


_apply_desktop_runtime_mode_env(_read_desktop_runtime_mode_pre_qt())


def _configure_qt_runtime() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("QT_OPENGL", "software")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ.setdefault("QTWEBENGINE_DISABLE_GPU", "1")
    if os.environ.get("QSG_RHI_BACKEND", "").lower() == "software":
        os.environ.pop("QSG_RHI_BACKEND", None)
    os.environ.setdefault("QT_ANGLE_PLATFORM", "warp")
    os.environ.setdefault("QTWEBENGINE_DISABLE_SANDBOX", "1")
    os.environ.setdefault(
        "QT_LOGGING_RULES",
        "*.debug=false;qt.webenginecontext.debug=false;"
        "qt.webenginecontext.info=false",
    )
    frozen_default_web_shell = "1" if getattr(sys, "frozen", False) else "0"
    web_mirror_requested = (
        os.environ.get("YAZKLINIK_DESKTOP_WEB_MIRROR", frozen_default_web_shell) == "1")
    web_shell_requested = (
        os.environ.get("YAZKLINIK_DESKTOP_WEB_SHELL", frozen_default_web_shell) == "1")
    webengine_requested = os.environ.get("YAZKLINIK_DESKTOP_ENABLE_WEBENGINE") == "1"
    if web_mirror_requested or web_shell_requested or webengine_requested:
        os.environ["YAZKLINIK_DESKTOP_ENABLE_WEBENGINE"] = "1"
        os.environ["YAZKLINIK_DESKTOP_DISABLE_WEBENGINE"] = "0"
    elif os.environ.get("YAZKLINIK_DESKTOP_ALLOW_WEBENGINE_GPU_RISK") != "1":
        os.environ["YAZKLINIK_DESKTOP_DISABLE_WEBENGINE"] = "1"
        os.environ.pop("YAZKLINIK_DESKTOP_ENABLE_WEBENGINE", None)

    required_flags = [
        "--disable-gpu",
        "--disable-gpu-compositing",
        "--disable-gpu-rasterization",
        "--disable-gpu-vsync",
        "--disable-accelerated-2d-canvas",
        "--disable-accelerated-video-decode",
        "--disable-3d-apis",
        "--disable-direct-composition",
        "--disable-zero-copy",
        "--disable-webgl",
        "--autoplay-policy=no-user-gesture-required",
        "--use-gl=disabled",
        "--use-angle=warp",
        "--enable-unsafe-swiftshader",
        "--disable-features=Vulkan,UseSkiaRenderer,CanvasOopRasterization",
        "--disable-logging",
        "--log-level=3",
    ]
    media_origins = _pre_qt_media_secure_origins()
    if (
        media_origins
        and os.environ.get("YAZKLINIK_ENABLE_FAKE_MEDIA_UI", "0").strip() == "1"
        and os.environ.get("YAZKLINIK_ALLOW_UNSUPPORTED_MEDIA_FLAGS", "0").strip() == "1"
    ):
        required_flags.extend([
            "--use-fake-ui-for-media-stream",
        ])
    existing = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    # Unsupported/legacy flags create noisy warnings in WebShell startup.
    # Keep speech API enabled and strip fake-media UI flag unless explicitly requested.
    disabled_for_voice = {
        "--disable-speech-api",
        "--use-fake-ui-for-media-stream",
    }
    parts = [
        part for part in (existing.split() if existing else [])
        if part not in disabled_for_voice
    ]
    for flag in required_flags:
        if flag not in parts:
            parts.append(flag)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(parts)


_configure_qt_runtime()

from PySide6.QtCore import QEvent, Qt, QSettings, QTimer, QUrl
from PySide6.QtGui import (
    QColor, QDesktopServices, QFont, QIcon, QImage, QPageLayout, QPageSize,
    QPainter,
)
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QStyle,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
try:
    from PySide6.QtPrintSupport import QPrinter, QPrintDialog
except Exception:
    QPrinter = None
    QPrintDialog = None


_PRINT_SETTINGS_CACHE = {"ts": 0.0, "data": {}}


def _desktop_remote_print_settings() -> dict:
    defaults = {
        "paper": "A4",
        "orientation": "portrait",
        "printer_name": "",
        "show_dialog": "1",
        "copies": "1",
    }
    now = time.time()
    if now - float(_PRINT_SETTINGS_CACHE.get("ts") or 0) < 20:
        data = dict(defaults)
        data.update(_PRINT_SETTINGS_CACHE.get("data") or {})
        return data
    candidates = _pre_qt_server_url_candidates() + [DEFAULT_SERVER_URL]
    for base in candidates:
        base = (base or "").strip().rstrip("/")
        if not base:
            continue
        try:
            req = urllib.request.Request(
                base + "/api/yazici-ayarlari",
                headers={"X-Terminal-Token": TERMINAL_TOKEN})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                payload = json.loads(
                    resp.read().decode("utf-8", errors="replace") or "{}")
            data = payload.get("settings") if isinstance(payload, dict) else {}
            if not isinstance(data, dict):
                continue
            cleaned = dict(defaults)
            cleaned.update({k: str(v) for k, v in data.items()})
            _PRINT_SETTINGS_CACHE.update({"ts": now, "data": cleaned})
            return cleaned
        except Exception:
            continue
    return defaults


def _desktop_qt_page_size(name: str):
    value = (name or "A4").upper()
    mapping = {
        "A3": QPageSize.A3,
        "A4": QPageSize.A4,
        "A5": QPageSize.A5,
        "LETTER": QPageSize.Letter,
    }
    return QPageSize(mapping.get(value, QPageSize.A4))


def _desktop_apply_saved_print_settings(printer) -> dict:
    settings = _desktop_remote_print_settings()
    try:
        printer.setPageSize(_desktop_qt_page_size(settings.get("paper", "A4")))
    except Exception:
        pass
    try:
        orientation = str(settings.get("orientation", "portrait")).lower()
        printer.setPageOrientation(
            QPageLayout.Landscape if orientation == "landscape"
            else QPageLayout.Portrait)
    except Exception:
        pass
    try:
        name = str(settings.get("printer_name", "") or "").strip()
        if name:
            printer.setPrinterName(name)
    except Exception:
        pass
    try:
        printer.setCopyCount(max(1, min(9, int(float(settings.get("copies", "1"))))))
    except Exception:
        pass
    return settings


def _print_pdf_file_via_qt(pdf_path, parent=None, title="Yazdir - A4 / yazici sec"):
    if QPrinter is None or QPrintDialog is None:
        QMessageBox.warning(parent, "Yazdir", "Yazici destegi yuklu degil.")
        return False
    try:
        import fitz
    except Exception as ex:
        QMessageBox.warning(
            parent, "Yazdir",
            "Bu sistemde eski Qt yazdirma yolu icin PyMuPDF gerekiyor.\n"
            f"Kurulum: pip install PyMuPDF\n{ex}")
        return False
    try:
        printer = QPrinter(QPrinter.HighResolution)
        try:
            printer.setOutputFormat(QPrinter.NativeFormat)
        except Exception:
            pass
        settings = _desktop_apply_saved_print_settings(printer)
        dlg = QPrintDialog(printer, parent)
        dlg.setWindowTitle(title)
        if settings.get("show_dialog", "1") != "0":
            if dlg.exec() != QPrintDialog.Accepted:
                return False

        doc = fitz.open(str(pdf_path))
        painter = QPainter()
        if not painter.begin(printer):
            doc.close()
            QMessageBox.warning(parent, "Yazdir", "Yaziciya baglanilamadi.")
            return False
        try:
            for idx, page in enumerate(doc):
                if idx:
                    printer.newPage()
                pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                img = QImage(
                    pix.samples, pix.width, pix.height, pix.stride,
                    QImage.Format_RGB888).copy()
                rect = printer.pageRect(QPrinter.DevicePixel).toRect()
                scaled = img.scaled(
                    rect.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                x = rect.x() + (rect.width() - scaled.width()) // 2
                y = rect.y() + (rect.height() - scaled.height()) // 2
                painter.drawImage(x, y, scaled)
        finally:
            painter.end()
            doc.close()
        try:
            parent.statusBar().showMessage("Sayfa yaziciya gonderildi.", 5000)
        except Exception:
            pass
        return True
    except Exception as ex:
        QMessageBox.warning(
            parent, "Yazdir",
            "Yazici penceresi acildi ama sayfa yazdirilamadi.\n"
            f"{ex}")
        return False


try:
    if os.environ.get("YAZKLINIK_DESKTOP_DISABLE_WEBENGINE", "0") == "1":
        raise ImportError("QtWebEngine disabled for GPU-safe desktop mode")
    if (os.environ.get("YAZKLINIK_DESKTOP_ENABLE_WEBENGINE") != "1"
            and os.environ.get("YAZKLINIK_DESKTOP_WEB_SHELL") != "1"):
        raise ImportError("QtWebEngine disabled for GPU-safe desktop mode")
    from PySide6.QtWebEngineWidgets import QWebEngineView
    try:
        from PySide6.QtWebEngineCore import QWebEnginePage
    except Exception:  # pragma: no cover - optional Qt split package
        QWebEnginePage = None
    WEB_ENGINE_AVAILABLE = True
except Exception:  # pragma: no cover - depends on platform package split
    QWebEngineView = None
    QWebEnginePage = None
    WEB_ENGINE_AVAILABLE = False


APP_VERSION = "YazKlinik Final D700 Terminal Kabuk"
DEFAULT_SERVER_URL = "https://127.0.0.1:5443"
WEB_CENTER_FIRST = os.environ.get("YAZKLINIK_DESKTOP_WEB_CENTER_FIRST", "1") == "1"
LEAN_WEB_SHELL = os.environ.get("YAZKLINIK_DESKTOP_LEAN_SHELL", "1") == "1"
LOCAL_TERMINAL_PORTS = range(5152, 5173)
HYBRID_EXPERIENCE_MODES = {"simple", "doctor", "advanced"}
HYBRID_EXPERIENCE_LABELS = {
    "simple": "Basit",
    "doctor": "Doktor",
    "advanced": "Uzman",
}


def _normalize_hybrid_experience_mode(value: str) -> str:
    value = (value or "").strip().lower()
    if value in {"simple", "basit"}:
        return "simple"
    if value in {"doctor", "doktor"}:
        return "doctor"
    if value in {"advanced", "expert", "uzman"}:
        return "advanced"
    return "advanced"


def _print_web_view_native(view, parent=None) -> None:
    if view is None:
        QMessageBox.warning(parent, "Yazdir", "Yazdirilacak sayfa yok.")
        return
    try:
        page = view.page()
    except Exception:
        page = None
    if page is None:
        QMessageBox.warning(parent, "Yazdir", "Bu sayfa program icinde yazdirilamadi.")
        return

    if QPrinter is not None and QPrintDialog is not None and hasattr(page, "print"):
        try:
            printer = QPrinter(QPrinter.HighResolution)
            try:
                printer.setOutputFormat(QPrinter.NativeFormat)
            except Exception:
                pass
            settings = _desktop_apply_saved_print_settings(printer)
            try:
                printer.setFullPage(False)
            except Exception:
                pass
            dlg = QPrintDialog(printer, parent)
            dlg.setWindowTitle(
                f"Yazdir - {settings.get('paper', 'A4')} / yazici sec")
            if settings.get("show_dialog", "1") != "0":
                if dlg.exec() != QPrintDialog.Accepted:
                    return

            keepalive = {"printer": printer, "dialog": dlg}

            def _print_done(ok=True):
                keepalive.clear()
                try:
                    if hasattr(parent, "_yk_active_print_job"):
                        parent._yk_active_print_job = None
                except Exception:
                    pass
                if ok:
                    try:
                        parent.statusBar().showMessage(
                            "Sayfa yaziciya gonderildi.", 5000)
                    except Exception:
                        pass
                else:
                    QMessageBox.warning(
                        parent, "Yazdir",
                        "Yazdirma tamamlanamadi. Yaziciyi ve kagit boyutunu kontrol edin.")

            try:
                parent._yk_active_print_job = keepalive
            except Exception:
                pass
            try:
                page.print(printer, _print_done)
            except TypeError:
                page.print(printer)
                QTimer.singleShot(1200, lambda: _print_done(True))
            return
        except Exception as ex:
            QMessageBox.warning(
                parent, "Yazdir",
                "Yazici penceresi acilamadi. Yazici surucusunu ve kagit "
                f"ayarlarini kontrol edin.\n{ex}")
            return

    if hasattr(page, "printToPdf"):
        try:
            pdf_path = os.path.join(
                tempfile.gettempdir(),
                f"YazKlinik_Gecici_Yazdir_{int(time.time() * 1000)}.pdf")
            job = {"path": pdf_path, "done": False}

            def _cleanup():
                try:
                    if not job.get("keep_file") and os.path.exists(pdf_path):
                        os.remove(pdf_path)
                except Exception:
                    pass
                try:
                    if hasattr(parent, "_yk_pdf_print_job"):
                        parent._yk_pdf_print_job = None
                except Exception:
                    pass

            def _finish(path=None, ok=True):
                if job.get("done"):
                    return
                job["done"] = True
                target = str(path or pdf_path)
                try:
                    if ok and os.path.exists(target):
                        if QPrinter is not None and QPrintDialog is not None:
                            _print_pdf_file_via_qt(target, parent)
                        else:
                            job["keep_file"] = True
                            QDesktopServices.openUrl(QUrl.fromLocalFile(target))
                            try:
                                parent.statusBar().showMessage(
                                    "Yazdirma PDF'i acildi. Yaziciyi acilan pencereden secin.",
                                    7000)
                            except Exception:
                                pass
                    else:
                        QMessageBox.warning(
                            parent, "Yazdir",
                            "Yazdirma sayfasi hazirlanamadi. Sayfayi yenileyip tekrar deneyin.")
                finally:
                    _cleanup()

            job["finish"] = _finish
            try:
                parent._yk_pdf_print_job = job
            except Exception:
                pass
            try:
                page.pdfPrintingFinished.connect(_finish)
            except Exception:
                pass
            try:
                parent.statusBar().showMessage("Yazdirma ekrani hazirlaniyor...", 3000)
            except Exception:
                pass
            page.printToPdf(pdf_path)
            QTimer.singleShot(9000, lambda: _finish(pdf_path, os.path.exists(pdf_path)))
            return
        except Exception as ex:
            QMessageBox.warning(
                parent, "Yazdir",
                "Yazici penceresi acilamadi. Yazici surucusunu ve kagit "
                f"ayarlarini kontrol edin.\n{ex}")
            return

    try:
        page.runJavaScript("setTimeout(function(){ window.print(); }, 80);")
        try:
            parent.statusBar().showMessage(
                "Yazdirma komutu sayfaya gonderildi.", 6000)
        except Exception:
            pass
        return
    except Exception:
        pass
    try:
        QDesktopServices.openUrl(page.url())
        try:
            parent.statusBar().showMessage(
                "Sayfa sistem tarayicisinda acildi; oradan yazdirabilirsiniz.",
                7000)
        except Exception:
            pass
        return
    except Exception:
        pass
    QMessageBox.warning(
        parent, "Yazdir",
        "Yazdirma penceresi acilamadi. PySide6/QtWebEngine yazdirma "
        "bilesenlerini kontrol edin.")
DESKTOP_QSS = """
QMainWindow {
    background: #F3F5F7;
}
QWidget {
    color: #18232C;
    font-family: "Segoe UI", "SF Pro Display", "Arial";
    font-size: 10.5pt;
    letter-spacing: 0px;
}
QSplitter::handle {
    background: #D7DDE3;
}
QStatusBar {
    background: #FBFCFD;
    border-top: 1px solid #DDE3E8;
    color: #5B6875;
    padding: 3px 8px;
}
QFrame#sidebar {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #121820,
        stop:0.55 #172331,
        stop:1 #223447
    );
    border-right: 1px solid #0B1016;
}
QFrame#sidebar QLabel {
    color: #ECF3F7;
}
QLabel#brandTitle {
    color: #FFFFFF;
    font-size: 23px;
    font-weight: 850;
}
QLabel#brandSubtitle {
    color: #B8C7D3;
    font-size: 12px;
}
QLabel#sectionLabel {
    color: #8CA1B3;
    font-size: 10px;
    font-weight: 850;
    padding: 11px 3px 2px 3px;
    text-transform: uppercase;
}
QLabel#menuCaption {
    color: #8CA1B3;
    font-size: 10px;
    font-weight: 850;
    padding: 5px 3px 0px 3px;
}
QPushButton#categoryButton {
    background: #1A2836;
    color: #DDE8EF;
    border: 1px solid #32495D;
    border-radius: 8px;
    padding: 8px 6px;
    font-weight: 820;
}
QPushButton#categoryButton:hover {
    border-color: #2EC4B6;
    background: #22364A;
    color: #FFFFFF;
}
QPushButton#categoryButton:checked {
    background: #2EC4B6;
    color: #071F25;
    border: 1px solid #58D7CD;
}
QLineEdit#sidebarSearch {
    background: #F7FAFC;
    border: 1px solid #53697C;
    border-radius: 8px;
    padding: 9px 10px;
    color: #10202B;
    selection-background-color: #2EC4B6;
}
QLineEdit#sidebarSearch:focus {
    border: 1px solid #2EC4B6;
}
QPushButton#routeButton {
    text-align: left;
    padding: 9px 11px;
    border: 1px solid #2D4052;
    border-radius: 8px;
    background: #1A2836;
    color: #F7FBFD;
    font-weight: 720;
}
QPushButton#routeButton:hover {
    border-color: #2EC4B6;
    background: #22364A;
}
QPushButton#routeButton:checked {
    background: #243B50;
    color: #FFFFFF;
    border: 1px solid #2EC4B6;
}
QPushButton#routeButton:pressed {
    background: #DFF7F4;
}
QPushButton#sidebarToolButton {
    background: #F7FAFC;
    color: #122331;
    border: 1px solid #6E8191;
    border-radius: 8px;
    padding: 8px 10px;
    font-weight: 760;
}
QPushButton#sidebarToolButton:hover {
    background: #E7F7F5;
    border-color: #2EC4B6;
}
QWidget#centerPanel {
    background: #F3F5F7;
}
QFrame#topbar, QFrame#desktopHeader, QFrame#webFrame, QFrame#commandBand {
    background: #FFFFFF;
    border: 1px solid #DDE3E8;
    border-radius: 8px;
}
QFrame#nativePage {
    background: #FFFFFF;
    border: 1px solid #DDE3E8;
    border-radius: 8px;
}
QFrame#nativePanel {
    background: #FFFFFF;
    border: 1px solid #DDE3E8;
    border-radius: 8px;
}
QFrame#nativeAccentPanel {
    background: #122331;
    border: 1px solid #21384C;
    border-radius: 8px;
}
QFrame#nativeAccentPanel QLabel {
    color: #FFFFFF;
}
QLabel#nativeEyebrow {
    color: #72808D;
    font-size: 10px;
    font-weight: 850;
}
QLabel#nativeTitle {
    color: #121D26;
    font-size: 24px;
    font-weight: 900;
}
QLabel#nativeSub {
    color: #62717E;
    font-size: 12px;
}
QLabel#nativeCardTitle {
    color: #53616E;
    font-size: 11px;
    font-weight: 850;
}
QLabel#nativeCardValue {
    color: #111D26;
    font-size: 22px;
    font-weight: 900;
}
QLabel#nativeText {
    color: #243440;
    font-size: 12px;
}
QListWidget#nativeList {
    background: #F8FAFB;
    border: 1px solid #DDE3E8;
    border-radius: 8px;
    padding: 5px;
    outline: 0;
}
QListWidget#nativeList::item {
    border-radius: 7px;
    padding: 8px;
    margin: 2px;
    color: #1E2D38;
}
QListWidget#nativeList::item:selected {
    background: #DDF6F3;
    color: #0F3431;
}
QPushButton#nativeActionButton, QPushButton#nativePrimaryActionButton {
    border-radius: 8px;
    padding: 9px 11px;
    font-weight: 800;
}
QPushButton#nativeActionButton {
    background: #F8FAFB;
    color: #182A36;
    border: 1px solid #D6DEE5;
}
QPushButton#nativeActionButton:hover {
    background: #E7F7F5;
    border-color: #2EC4B6;
}
QPushButton#nativePrimaryActionButton {
    background: #122331;
    color: #FFFFFF;
    border: 1px solid #122331;
}
QPushButton#nativePrimaryActionButton:hover {
    background: #1E3446;
    border-color: #2EC4B6;
}
QFrame#desktopHeader QLabel#headerTitle {
    color: #121D26;
    font-size: 21px;
    font-weight: 850;
}
QFrame#desktopHeader QLabel#headerSub {
    color: #62717E;
    font-size: 12px;
}
QFrame#metricCard {
    background: #F8FAFB;
    border: 1px solid #E2E7EC;
    border-radius: 8px;
}
QLabel#metricTitle {
    color: #72808D;
    font-size: 10px;
    font-weight: 780;
}
QLabel#metricValue {
    color: #152330;
    font-size: 13px;
    font-weight: 850;
}
QLabel#bandTitle {
    color: #53616E;
    font-size: 11px;
    font-weight: 850;
}
QPushButton#primaryQuickButton, QPushButton#quickButton {
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 22px;
    font-weight: 800;
}
QPushButton#primaryQuickButton {
    background: #122331;
    color: #FFFFFF;
    border: 1px solid #122331;
}
QPushButton#primaryQuickButton:hover {
    background: #1E3446;
    border-color: #2EC4B6;
}
QPushButton#quickButton {
    background: #F7FAFC;
    color: #162532;
    border: 1px solid #D6DEE5;
}
QPushButton#quickButton:hover {
    background: #E7F7F5;
    border-color: #2EC4B6;
}
QToolButton#navButton, QPushButton#topButton {
    border: 1px solid #D6DEE5;
    border-radius: 8px;
    background: #F8FAFB;
    color: #1D2B37;
    padding: 7px 10px;
    font-weight: 760;
}
QToolButton#navButton:hover, QPushButton#topButton:hover {
    background: #E7F7F5;
    border-color: #2EC4B6;
}
QLineEdit#addressBar {
    border: 1px solid #D6DEE5;
    border-radius: 8px;
    padding: 8px 10px;
    background: #FBFCFD;
    color: #172528;
    selection-background-color: #2EC4B6;
}
QLineEdit#addressBar:focus {
    border: 1px solid #2EC4B6;
}
QLabel#statusChip {
    border-radius: 8px;
}
QFrame#worklist {
    background: #F7F9FB;
    border-left: 1px solid #D7DDE3;
}
QLabel#worklistTitle {
    color: #141F28;
    font-size: 17px;
    font-weight: 850;
}
QLabel#activePatientCard {
    padding: 12px;
    border-radius: 8px;
    background: #FFFFFF;
    border: 1px solid #DDE3E8;
    color: #1D2D3A;
}
QLineEdit#patientSearch {
    background: #FFFFFF;
    border: 1px solid #D6DEE5;
    border-radius: 8px;
    padding: 9px 10px;
}
QLineEdit#patientSearch:focus {
    border: 1px solid #2EC4B6;
}
QListWidget#patientList {
    background: #FFFFFF;
    border: 1px solid #DDE3E8;
    border-radius: 8px;
    padding: 5px;
    outline: 0;
}
QListWidget#patientList::item {
    border-radius: 7px;
    padding: 9px 8px;
    margin: 3px;
    color: #1E2D38;
}
QListWidget#patientList::item:selected {
    background: #DDF6F3;
    color: #0F3431;
}
QListWidget#patientList::item:hover {
    background: #F0F7FA;
}
QPushButton#worklistButton, QPushButton#worklistPrimaryButton {
    border-radius: 8px;
    padding: 9px;
    text-align: left;
    font-weight: 760;
}
QPushButton#worklistButton {
    border: 1px solid #DDE3E8;
    background: #FFFFFF;
    color: #1E2D38;
}
QPushButton#worklistButton:hover {
    background: #E7F7F5;
    border-color: #2EC4B6;
}
QPushButton#worklistPrimaryButton {
    border: 1px solid #122331;
    background: #122331;
    color: #FFFFFF;
}
QPushButton#worklistPrimaryButton:hover {
    background: #1E3446;
    border-color: #2EC4B6;
}
QScrollArea {
    border: 0;
    background: transparent;
}
QFrame#sidebar QScrollArea, QFrame#sidebar QScrollArea QWidget,
QWidget#routeContainer {
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 10px;
    margin: 3px;
}
QScrollBar::handle:vertical {
    background: #A8B4BF;
    border-radius: 5px;
    min-height: 28px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

/* v1000.1.1 premium native color pass + GPU safe */
QMainWindow {
    background: #EEF3F8;
}
QWidget#centerPanel {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #F5F8FB,
        stop:0.52 #ECF3F6,
        stop:1 #F7F4EF
    );
}
QFrame#sidebar {
    background: qlineargradient(
        x1:0, y1:0, x2:0.92, y2:1,
        stop:0 #151820,
        stop:0.38 #1D2630,
        stop:0.70 #17352F,
        stop:1 #3A2A34
    );
    border-right: 1px solid #0D1117;
}
QFrame#sidebar QLabel {
    color: #F5F8F9;
}
QLabel#brandTitle {
    color: #FFFFFF;
    font-size: 24px;
    font-weight: 900;
}
QLabel#brandSubtitle {
    color: #C8D4DE;
    font-size: 12px;
}
QLabel#sectionLabel, QLabel#menuCaption {
    color: #AFC1C4;
    letter-spacing: 0px;
}
QPushButton#categoryButton {
    background: #22303A;
    color: #E7EEF1;
    border: 1px solid #3B4F5E;
    border-radius: 8px;
}
QPushButton#categoryButton:hover {
    background: #274A49;
    border-color: #57D4C8;
}
QPushButton#categoryButton:checked {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #2EC4B6,
        stop:1 #F2C14E
    );
    color: #101820;
    border: 1px solid #F5D779;
}
QLineEdit#sidebarSearch {
    background: #F7FAFC;
    border: 1px solid #5D7680;
    color: #12202A;
}
QPushButton#routeButton {
    background: #202B36;
    color: #F3F7F8;
    border: 1px solid #374956;
    border-radius: 8px;
}
QPushButton#routeButton:hover {
    background: #274A49;
    border-color: #56D2C8;
}
QPushButton#routeButton:checked {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #193F47,
        stop:1 #2A625A
    );
    color: #FFFFFF;
    border: 1px solid #62D8CF;
}
QPushButton#sidebarToolButton {
    background: #F7FAFC;
    color: #14242D;
    border: 1px solid #8FA7AE;
}
QFrame#desktopHeader, QFrame#commandBand, QFrame#topbar, QFrame#webFrame {
    background: #FFFFFF;
    border: 1px solid #D8E2EA;
    border-radius: 8px;
}
QFrame#desktopHeader {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #FFFFFF,
        stop:0.56 #F7FBFC,
        stop:1 #F9F0DF
    );
}
QFrame#nativePage {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #FFFFFF,
        stop:0.64 #F7FBFC,
        stop:1 #EEF7F5
    );
    border: 1px solid #D8E5EA;
}
QFrame#nativePanel {
    background: #FFFFFF;
    border: 1px solid #D9E4EA;
    border-radius: 8px;
}
QFrame#nativePanel[tone="teal"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #FFFFFF, stop:1 #E5F8F5);
    border-left: 4px solid #2EC4B6;
}
QFrame#nativePanel[tone="gold"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #FFFFFF, stop:1 #FFF4D8);
    border-left: 4px solid #F2C14E;
}
QFrame#nativePanel[tone="coral"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #FFFFFF, stop:1 #FFECE5);
    border-left: 4px solid #EF6F6C;
}
QFrame#nativePanel[tone="plum"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #FFFFFF, stop:1 #F1EAF8);
    border-left: 4px solid #8A6BBE;
}
QFrame#nativeAccentPanel {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:1,
        stop:0 #131820,
        stop:0.42 #183A37,
        stop:0.72 #2B343C,
        stop:1 #4A3340
    );
    border: 1px solid #345B5A;
}
QFrame#nativeAccentPanel QLabel#nativeEyebrow {
    color: #9DE7DE;
}
QFrame#nativeAccentPanel QLabel#nativeTitle {
    color: #FFFFFF;
}
QFrame#nativeAccentPanel QLabel#nativeSub {
    color: #D5E4E4;
}
QLabel#nativeTitle {
    color: #15212A;
    font-size: 25px;
}
QLabel#nativeCardTitle {
    color: #5B6670;
}
QLabel#nativeCardValue {
    color: #111A22;
    font-size: 23px;
}
QListWidget#nativeList, QListWidget#patientList {
    background: #FBFDFE;
    border: 1px solid #D8E3EA;
}
QListWidget#nativeList::item:hover, QListWidget#patientList::item:hover {
    background: #EDF8F6;
}
QListWidget#nativeList::item:selected, QListWidget#patientList::item:selected {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #DDF7F4,
        stop:1 #FFF1D1
    );
    color: #12302D;
}
QPushButton#nativePrimaryActionButton, QPushButton#primaryQuickButton,
QPushButton#worklistPrimaryButton {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #14242D,
        stop:0.58 #17443F,
        stop:1 #8A6332
    );
    color: #FFFFFF;
    border: 1px solid #3D756E;
}
QPushButton#nativePrimaryActionButton:hover, QPushButton#primaryQuickButton:hover,
QPushButton#worklistPrimaryButton:hover {
    background: qlineargradient(
        x1:0, y1:0, x2:1, y2:0,
        stop:0 #1B3340,
        stop:0.58 #1F5E57,
        stop:1 #A97B3C
    );
    border-color: #F2C14E;
}
QPushButton#nativeActionButton, QPushButton#quickButton,
QPushButton#worklistButton, QToolButton#navButton, QPushButton#topButton {
    background: #FFFFFF;
    color: #1C2B36;
    border: 1px solid #D6E1E7;
}
QPushButton#nativeActionButton:hover, QPushButton#quickButton:hover,
QPushButton#worklistButton:hover, QToolButton#navButton:hover, QPushButton#topButton:hover {
    background: #EEF8F6;
    border-color: #2EC4B6;
}
QFrame#metricCard {
    background: #FFFFFF;
    border: 1px solid #D9E3EA;
    border-radius: 8px;
}
QFrame#metricCard[tone="mode"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #FFFFFF, stop:1 #F1EAF8);
    border-left: 4px solid #8A6BBE;
}
QFrame#metricCard[tone="server"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #FFFFFF, stop:1 #E5F8F5);
    border-left: 4px solid #2EC4B6;
}
QFrame#metricCard[tone="patient"] {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #FFFFFF, stop:1 #FFF4D8);
    border-left: 4px solid #F2C14E;
}
QFrame#worklist {
    background: qlineargradient(
        x1:0, y1:0, x2:0, y2:1,
        stop:0 #F9FBFC,
        stop:1 #EEF4F7
    );
    border-left: 1px solid #D2DEE7;
}
QLabel#activePatientCard {
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #FFFFFF, stop:1 #EEF8F6);
    border: 1px solid #D5E4EA;
}
QLineEdit#patientSearch, QLineEdit#addressBar {
    background: #FFFFFF;
    border: 1px solid #D4E0E7;
}
QStatusBar {
    background: #FFFFFF;
    border-top: 1px solid #D6E1E8;
}
"""


@dataclass(frozen=True)
class RouteItem:
    route: str
    label: str
    hint: str = ""
    group: str = ""


FALLBACK_GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("Merkez", [
        ("/dashboard", "Dashboard", "Klinik ana ekran"),
        ("/kullanim-kalitesi", "Klinik Akis", "Pratik kalite merkezi"),
        ("/", "Hastalar", "Hasta listesi ve arama"),
        ("/yeni-hasta", "Yeni Hasta", "Kayit olustur"),
        ("/arama", "Arama", "Hasta ve kayit arama"),
        ("/randevular", "Randevular", "Liste gorunumu"),
        ("/takvim", "Takvim", "Takvim"),
        ("/sohbet-merkezi", "Sohbet Merkezi", "Sohbet ve randevu talepleri"),
        ("/randevu-onay", "Randevu Onay", "YZ randevu taleplerini onayla"),
        ("/gun-plani", "Gun Plani", "Bugunun akisi"),
        ("/gun-sonu-ozeti", "Gun Sonu Ozeti", "Gunluk klinik ozet"),
        ("/gorevler", "Gorevler", "Is listesi"),
        ("/hizli-not", "Hizli Not", "Aninda not"),
        ("/akilli-bildirimler", "AkÄ±llÄ± Bildirimler", "BugÃ¼nÃ¼n takip ve hatÄ±rlatmalarÄ±"),
        ("/akilli-rehber", "AkÄ±llÄ± Rehber", "KullanÄ±mdan Ã¶ÄŸrenir"),
    ]),
    ("Klinik", [
        ("/obstetrik", "Obstetrik", "Gebelik takibi"),
        ("/hasta/{patient}/gebelik-takip-plani", "Gebelik Takip", "A4 tarihli takip formu"),
        ("/hasta/{patient}/gebelik-gelisim-takibi", "Gebelik Gelisim", "PDF USG buyume grafikleri"),
        ("/jinekoloji", "Jinekoloji", "Jinekolojik modul"),
        ("/medikal-estetik", "Medikal Estetik", "Estetik hasta akisi"),
        ("/riskli-gebelik", "Riskli Gebelik Takip Merkezi", "Yuksek risk ve kritik gebelik izlem merkezi"),
        ("/doguranlar", "Dogumlar", "Dogum kayitlari"),
        ("/onam-sablonlari", "Onam Formlari", "Database onam kutuphanesi"),
        ("/recete-sablonlari", "HazÄ±r ReÃ§eteler", "Database reÃ§ete kÃ¼tÃ¼phanesi"),
        ("/kontrol-listesi/menu", "Kontrol Listeleri", "Muayene checklist"),
    ]),
    ("PACS ve Medya", [
        ("/dicom", "DICOM/PACS", "Orthanc ve goruntu"),
        ("/dicom?mode=ai", "DICOM / USG Zeka", "Orthanc, viewer, olcum ve AI merkezi"),
        ("/dicom-servisleri", "DICOM Servisleri", "Orthanc plugin merkezi"),
        ("/dicom-alisveris", "DICOM Alisveris", "Voluson Worklist, C-STORE ve C-ECHO"),
        ("/hasta/{patient}/dosya-gezgini", "NAS/DICOM Gezgin", "Hasta klasoru ve DICOM gezgini"),
        ("/hasta/{patient}/dicom", "DICOM / USG Zeka", "Orthanc eslestirme, OCR olcum ve AI on inceleme"),
        ("/dicom-worklist", "DICOM Worklist", "Is listesi"),
        ("/takip-medya-arsivi", "Medya Arsivi", "Oncesi/sonrasi"),
        ("/hasta/{patient}/yz-resim-iyilestir", "HD Studio", "Onizlemeden resim/video isleme"),
        ("/hasta/{patient}/pdf-editor", "PDF Rapor Editoru", "Rapor duzenleme"),
    ]),
    ("YZ Asistanlar", [
        ("/yz-asistan", "YZ Asistan", "Klinik asistan"),
        ("/akilli-rehber", "AkÄ±llÄ± Rehber", "Yol gÃ¶sterici asistan"),
        ("/yz-komut-merkezi", "YZ Komut", "GÃ¼venli komut merkezi"),
    ]),
    ("Ses ve AkÄ±llÄ± Diyalog", [
        ("/ses-ve-alex", "Ses ve Alex Merkezi", "AkÄ±llÄ± Diyalog ve ses ayarlarÄ± tek yerde"),
        ("/akilli-dialog", "AkÄ±llÄ± Diyalog", "KonuÅŸan ve iÅŸ yapan YZ ajan"),
        ("/sessiz-alex", "Sessiz Alex", "Klavye ile sessiz AkÄ±llÄ± Diyalog"),
        ("/sesli-recete", "Sesli ReÃ§ete", "KonuÅŸarak reÃ§ete taslaÄŸÄ±"),
        ("/yz-ses-cevir", "Ses Ã‡evir", "Sesli notu metne Ã§evir"),
        ("/ses-profilleri", "Alex Ses SeÃ§imi", "Alex konuÅŸma sesi"),
        ("/mikrofon-tani", "Mikrofon TanÄ±", "Ses giriÅŸ testi"),
        ("/yz-telefon-diyalog", "YZ Diyalog", "Telefonsuz/telefonlu TÃ¼rkÃ§e sohbet"),
        ("/entegrasyon/yz-telesekreter", "YZ Telesekreter", "IP telefon/PBX"),
    ]),
    ("YZ Analiz ve Otomasyon", [
        ("/islem-zincirleri", "Ä°ÅŸlem Zincirleri", "ReÃ§ete, randevu ve WhatsApp taslaklarÄ±"),
        ("/yz-sistem-onerileri", "YZ Sistem Onerileri", "Randevu, recete, tahlil ve risk akislarini takip eder"),
        ("/ekran-yakala", "Ekran Yakala", "OCR + YZ"),
        ("/hasta/{patient}/gorsel-tani-destegi", "Resimle Ã–n TanÄ±", "Hasta resmiyle Ã¶n tanÄ± ve ilaÃ§ Ã¶n Ã¶nerisi"),
    ]),
    ("YZ Ayarlar", [
        ("/online-chatgpt", "Online ChatGPT", "OpenAI + Ollama ayarlari"),
        ("/yz-sihirbazi", "YZ Sihirbazi", "Model/ayar yardimcisi"),
        ("/yz-kurulum-rehberi", "YZ Kurulum", "Kurulum rehberi"),
        ("/yz-server-durum", "YZ Server", "Ollama durumu"),
    ]),
    ("Sistem", [
        ("/sistem-durumu", "Sistem Durumu", "Server, YZ, DICOM ve depolama durumu"),
        ("/ayarlar", "Ayarlar", "Web ayarlari"),
        ("/performans-ayarlari", "Performans", "RAM ve masaustu hiz modu"),
        ("/dicom-servisleri", "DICOM Servisleri", "Orthanc plugin merkezi"),
        ("/dicom-ayar", "DICOM Ayar", "Orthanc ve PACS parametreleri"),
        ("/sistem/dosya-konumlari", "Dosya Konumlari", "NAS, medya, cikti ve yedek yollari"),
        ("/tum-ayarlar", "Tum Ayarlar", "Butun kontrol anahtarlari"),
        ("/ayar-editoru", "Ayar Editoru", "Uzman ayar editoru"),
        ("/veritabani-saglik-kontrol", "DB Saglik / Onarim", "Veritabani kontrol, yedek, vacuum ve onarim"),
        ("/yedekleme-merkezi", "Yedekleme", "Otomatik yedek ve geri alma merkezi"),
        ("/sistem-guncelleme", "Guncelleme", "update.zip yukle"),
        ("/temiz-kurulum", "Temiz Kurulum", "Sifirlama/format"),
        ("/kurulum-sihirbazi", "Kurulum", "Sistem kurulum sihirbazi"),
    ]),
]

FALLBACK_SIMPLE_ROUTES = {
    "/dashboard", "/kullanim-kalitesi", "/", "/yeni-hasta", "/arama", "/randevular",
    "/sohbet-merkezi", "/randevu-onay", "/gun-plani", "/gun-sonu-ozeti",
    "/gorevler", "/jinekoloji", "/medikal-estetik",
    "/riskli-gebelik", "/doguranlar", "/onam-sablonlari",
    "/recete-sablonlari", "/dicom", "/dicom-servisleri", "/yz-asistan", "/online-chatgpt",
    "/ses-ve-alex", "/akilli-dialog", "/sessiz-alex", "/yz-komut-merkezi", "/sesli-recete",
    "/yz-ses-cevir", "/ses-profilleri", "/mikrofon-tani", "/islem-zincirleri",
    "/akilli-bildirimler", "/akilli-rehber", "/entegrasyon/yz-telesekreter",
    "/yz-telefon-diyalog", "/yz-sistem-onerileri",
    "/ayarlar", "/performans-ayarlari", "/sistem-durumu",
    "/veritabani-saglik-kontrol", "/temiz-kurulum",
}

PATIENT_ACTIONS = [
    ("Hasta Ozeti", "/hasta/{patient}"),
    ("Hasta Dosyasi", "/hasta/{patient}/hasta-dosyasi"),
    ("Gelisler", "/hasta/{patient}/gelisler"),
    ("Medikal Estetik", "/hasta/{patient}/takip-medya?module=medical_aesthetic"),
    ("Medya", "/hasta/{patient}/takip-medya"),
    ("NAS/DICOM Gezgin", "/hasta/{patient}/dosya-gezgini"),
    ("DICOM Medya", "/hasta/{patient}/dicom-medya"),
    ("DICOM / USG Zeka", "/hasta/{patient}/dicom"),
    ("DICOM/PACS", "/dicom?patient={patient}"),
    ("Tahliller", "/hasta/{patient}/tahliller"),
    ("Diyet", "/hasta/{patient}/yz-diyet"),
    ("Gebelik Takip", "/hasta/{patient}/gebelik-takip-plani"),
    ("Gebelik Gelisim", "/hasta/{patient}/gebelik-gelisim-takibi"),
    ("WhatsApp", "/hasta/{patient}/whatsapp"),
    ("AkÄ±llÄ± Asistan", "/hasta/{patient}/akilli-asistan"),
    ("Hasta HafÄ±zasÄ±", "/hasta/{patient}/hafiza"),
    ("KonuÅŸarak Not", "/hasta/{patient}/konusarak-not"),
    ("Sesli ReÃ§ete", "/hasta/{patient}/sesli-recete"),
    ("AkÄ±llÄ± Rehber", "/akilli-rehber"),
    ("Onam", "/hasta/{patient}/onam"),
    ("Onam Sablonlari", "/onam-sablonlari?patient={patient}"),
    ("YZ Anomali", "/hasta/{patient}/yz-anomali-tarama"),
    ("YZ Medya", "/hasta/{patient}/yz-medya-analiz"),
    ("Resimle Ã–n TanÄ±", "/hasta/{patient}/gorsel-tani-destegi"),
    ("HD Studio", "/hasta/{patient}/yz-resim-iyilestir"),
    ("HD Studio Medya Sec", "/hasta/{patient}/yz-resim-iyilestir"),
    ("ReÃ§ete", "/hasta/{patient}/recete-hazirla"),
    ("HazÄ±r ReÃ§eteler", "/recete-sablonlari?patient={patient}"),
    ("Randevu", "/randevu/yeni?hasta={patient}"),
    ("PDF Atolyesi", "/hasta/{patient}/pdf-atolyesi"),
    ("Rapor Editor", "/hasta/{patient}/pdf-editor"),
    ("PDF Yazdir", "/hasta/{patient}/rapor-pdf-yazdir"),
    ("Zaman Cizgisi", "/hasta/{patient}/zaman-cizgisi"),
]

OBSTETRIC_PATIENT_ROUTE_MARKERS = (
    "/gebelik-",
    "/yz-anomali-tarama",
)


MENU_CATEGORIES = [
    ("today", "Bugun"),
    ("patient", "Hasta"),
    ("clinical", "Klinik"),
    ("media", "Goruntu"),
    ("ai", "YZ"),
    ("system", "Sistem"),
]

if _sync_desktop_menu_categories is not None:
    try:
        synced_categories = _sync_desktop_menu_categories()
        if synced_categories:
            MENU_CATEGORIES = synced_categories
    except Exception:
        pass


MENU_CATEGORY_KEYS = {key for key, _label in MENU_CATEGORIES}


def _haystack(item: RouteItem) -> str:
    return " ".join([item.route, item.label, item.hint, item.group]).casefold()


def _has_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word in text for word in words)


def route_category(item: RouteItem) -> str:
    if _sync_route_category is not None:
        try:
            synced = _sync_route_category(item.route)
            if synced:
                return synced
        except Exception:
            pass
    text = _haystack(item)
    route = item.route.casefold()
    group = item.group.casefold()
    label = item.label.casefold()
    if route in {"/", "/arama", "/yeni-hasta"} or route.startswith("/hasta"):
        return "patient"
    if _has_any(route, (
        "ayar", "sistem", "kurulum", "guncelle", "veritabani", "db",
        "temiz", "veri-konum", "backup", "yedek", "bakim", "performans",
    )) or _has_any(group, ("sistem", "ayar", "bakim")):
        return "system"
    if _has_any(route, (
        "dicom", "pacs", "medya", "pdf", "rapor", "resim", "video",
        "hd-studio", "iyilestir", "goruntu", "media",
    )) or _has_any(group, ("pacs", "medya", "media", "goruntu")):
        return "media"
    if route.startswith("/yz") or _has_any(text, (
        "ollama", "anomali", "akilli rehber", "asistan", "sihirbaz",
        "telesekreter", "ekran yakala",
    )) or group.strip() == "yz" or group.startswith("yz "):
        return "ai"
    if _has_any(text, (
        "obstetrik", "jinekoloji", "medikal estetik", "perinatoloji",
        "dogum", "onam", "recete", "kontrol liste", "diyet", "tahlil",
        "infertil", "gebe",
    )) or _has_any(group, ("klinik", "obstetrik", "jinekoloji")):
        return "clinical"
    if _has_any(route, (
        "dashboard", "gun-plani", "gorev", "randevu", "takvim",
        "hizli-not", "kullanim-kalitesi", "akilli-bildirim",
    )) or _has_any(label, ("dashboard", "gun", "randevu", "takvim")):
        return "today"
    return "today"


def _clean_url(value: str) -> str:
    value = (value or "").strip().rstrip("/")
    if not value:
        return DEFAULT_SERVER_URL
    if not value.startswith(("http://", "https://")):
        value = "http://" + value
    try:
        parts = urllib.parse.urlsplit(value)
        host = parts.hostname or ""
    except Exception:
        return DEFAULT_SERVER_URL
    if host in {"localhost", "127.0.0.1", "::1"} and os.environ.get(
            "YAZKLINIK_ALLOW_LOCAL_TERMINAL_SERVER") != "1":
        return DEFAULT_SERVER_URL
    if not parts.netloc:
        return DEFAULT_SERVER_URL
    return f"{parts.scheme}://{parts.netloc}".rstrip("/")


def read_server_url() -> str:
    for key in ("YAZKLINIK_WEB_URL", "YAZKLINIK_SERVER_URL",
                "YAZKLINIK_AI_SERVER_URL"):
        if os.environ.get(key):
            return _clean_url(os.environ[key])
    candidates = [
        Path(__file__).resolve().parent / "terminal_server_url.txt",
        _yk_state_root() / "terminal_server_url.txt",
    ]
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app:
        candidates.append(Path(local_app) / "YazKlinik" / "terminal_server_url.txt")
    for path in candidates:
        try:
            if path.exists():
                value = path.read_text(encoding="utf-8").strip()
                if value:
                    return _clean_url(value)
        except Exception:
            pass
    return DEFAULT_SERVER_URL


def save_server_url(url: str) -> None:
    url = _clean_url(url)
    paths = [
        Path(__file__).resolve().parent / "terminal_server_url.txt",
        _yk_state_root() / "terminal_server_url.txt",
    ]
    local_app = os.environ.get("LOCALAPPDATA")
    if local_app and os.environ.get("YAZKLINIK_WRITE_LOCALAPPDATA_STATE") == "1":
        paths.append(Path(local_app) / "YazKlinik" / "terminal_server_url.txt")
    for path in paths:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(url + "\n", encoding="ascii")
        except Exception:
            pass


def route_url(base_url: str, route: str) -> str:
    route = route or "/dashboard"
    if route.startswith(("http://", "https://")):
        return route
    if not route.startswith("/"):
        route = "/" + route
    return base_url.rstrip("/") + route


def fetch_json(base_url: str, route: str, timeout: int = 5,
               method: str = "GET", body: Optional[dict] = None) -> dict:
    data = None
    headers = {"X-Terminal-Token": TERMINAL_TOKEN}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(
        route_url(base_url, route), data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw or "{}")


def ping_server_url(base_url: str, timeout: int = 2) -> bool:
    try:
        data = fetch_json(base_url, "/api/terminal/ping", timeout=timeout)
        return bool(data.get("ok", True))
    except Exception:
        return False


def _desktop_mode_from_runtime_server(base_url: str, default: str = "hybrid") -> str:
    if os.environ.get("YAZKLINIK_DESKTOP_MODE_FORCE", "").strip() == "1":
        return _normalize_desktop_runtime_mode(
            os.environ.get("YAZKLINIK_DESKTOP_MODE", default), default)
    try:
        data = fetch_json(base_url, "/api/terminal/performance", timeout=2)
        mode = _normalize_desktop_runtime_mode(
            str(data.get("desktop_runtime_mode") or ""), "")
        if mode:
            return _write_desktop_runtime_mode_files(mode)
    except Exception:
        pass
    return _read_desktop_runtime_mode_pre_qt(default)


def _current_process_desktop_mode() -> str:
    explicit = _normalize_desktop_runtime_mode(
        os.environ.get("YAZKLINIK_DESKTOP_MODE", ""), "")
    if explicit:
        return explicit
    if os.environ.get("YAZKLINIK_DESKTOP_WEB_MIRROR") == "1":
        return "mirror"
    if os.environ.get("YAZKLINIK_DESKTOP_WEB_SHELL") == "1":
        return "shell"
    return "hybrid"


def _windows_gui_python() -> str:
    exe = Path(sys.executable)
    if os.name == "nt" and exe.name.lower() == "python.exe":
        candidate = exe.with_name("pythonw.exe")
        if candidate.exists():
            return str(candidate)
    return str(exe)


def _launch_desktop_mode_process(mode: str, server_url: str) -> bool:
    mode = _apply_desktop_runtime_mode_env(_write_desktop_runtime_mode_files(mode))
    root = Path(__file__).resolve().parent
    if mode in {"shell", "hybrid"} and (root / "WebShell" / "main.py").exists():
        script = root / "WebShell" / "main.py"
        cwd = script.parent
    else:
        script = root / "yazklinik_desktop_v1000.py"
        cwd = root
    if not script.exists():
        return False
    env = os.environ.copy()
    env.update({
        "YAZKLINIK_DESKTOP_MODE": mode,
        "YAZKLINIK_SERVER_URL": server_url,
        "YAZKLINIK_WEB_URL": server_url,
        "YAZKLINIK_AI_SERVER_URL": server_url,
    })
    try:
        subprocess.Popen(
            [_windows_gui_python(), "-X", "utf8", str(script)],
            cwd=str(cwd),
            env=env,
            close_fds=True,
        )
        return True
    except Exception:
        return False


def _desktop_restart_requested_url(url) -> bool:
    try:
        if hasattr(url, "toString"):
            text = url.toString()
        else:
            text = str(url or "")
        parsed = urllib.parse.urlsplit(text)
        return (
            (parsed.path or "") == "/performans-ayarlari" and
            urllib.parse.parse_qs(parsed.query or {}).get("desktop_restart", [""])[0] == "1"
        )
    except Exception:
        return False


def _apply_runtime_mode_change_for_window(window, server_url: str) -> None:
    if getattr(window, "_desktop_restart_pending", False):
        return
    window._desktop_restart_pending = True
    mode = _desktop_mode_from_runtime_server(server_url, "hybrid")
    current = _current_process_desktop_mode()
    if mode == current:
        try:
            window.statusBar().showMessage(f"Masaustu {mode} modu zaten aktif.", 5000)
        except Exception:
            pass
        window._desktop_restart_pending = False
        return
    try:
        window.statusBar().showMessage(f"Masaustu {mode} modunda yeniden aciliyor...", 5000)
    except Exception:
        pass
    if _launch_desktop_mode_process(mode, server_url):
        QTimer.singleShot(700, QApplication.instance().quit)
        QTimer.singleShot(1800, lambda: os._exit(0))
    else:
        window._desktop_restart_pending = False
        try:
            QMessageBox.warning(
                window, "Masaustu modu",
                "Yeni masaustu modu baslatilamadi. Programi kapatip yeniden acin.")
        except Exception:
            pass


def local_terminal_status_path() -> Path:
    return _yk_state_root() / "terminal_runtime_status.json"


def write_terminal_runtime_status(payload: dict) -> None:
    try:
        path = local_terminal_status_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    except Exception:
        pass


def free_local_port() -> int:
    for port in LOCAL_TERMINAL_PORTS:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("Yerel terminal API portu bulunamadi")


class LocalTerminalWebRuntime:
    """Embedded web/API server used when the main server is unreachable."""

    def __init__(self):
        self.server = None
        self.thread: Optional[threading.Thread] = None
        self.url = ""
        self.error = ""

    def start(self) -> str:
        if self.url and self.thread and self.thread.is_alive():
            return self.url
        os.environ["YAZKLINIK_ALLOW_LOCAL_TERMINAL_SERVER"] = "1"
        os.environ["YAZKLINIK_TERMINAL_LOCAL_FALLBACK"] = "1"
        os.environ.setdefault("YAZKLINIK_TERMINAL_MODE", "1")
        last_error = None
        for port in LOCAL_TERMINAL_PORTS:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.2)
                if sock.connect_ex(("127.0.0.1", port)) == 0:
                    continue
            os.environ["YAZKLINIK_WEB_PORT"] = str(port)
            try:
                from werkzeug.serving import make_server
                from yazklinik_web import app as flask_app
                self.server = make_server(
                    "127.0.0.1", port, flask_app, threaded=True)
                self.thread = threading.Thread(
                    target=self.server.serve_forever,
                    name=f"YazKlinikLocalTerminal:{port}",
                    daemon=True,
                )
                self.thread.start()
                self.url = f"http://127.0.0.1:{port}"
                self.error = ""
                write_terminal_runtime_status({
                    "mode": "local_fallback",
                    "url": self.url,
                    "port": port,
                    "ok": True,
                })
                return self.url
            except OSError as ex:
                last_error = ex
                continue
            except Exception as ex:
                self.error = str(ex)
                raise
        self.error = str(last_error or "port yok")
        raise RuntimeError(f"Yerel terminal API baslatilamadi: {self.error}")


class YazKlinikWebMirror(QMainWindow):
    """Full-screen Windows window that mirrors the web UI without extra chrome."""

    def __init__(self):
        super().__init__()
        if QWebEngineView is None:
            raise RuntimeError("QtWebEngine bulunamadi")
        self.primary_server_url = _clean_url(read_server_url())
        self.server_url = self.primary_server_url
        self.connection_mode = "server"
        self.local_runtime = LocalTerminalWebRuntime()
        self.local_server_url = ""
        self._desktop_restart_pending = False
        self.fast_start = os.environ.get("YAZKLINIK_DESKTOP_FAST_START", "1") == "1"
        self.start_route = os.environ.get(
            "YAZKLINIK_DESKTOP_START_ROUTE", "/giris") or "/giris"
        save_server_url(self.primary_server_url)
        self._set_runtime_url(self.primary_server_url, mode="server", persist=True)
        if (not self.fast_start) and not ping_server_url(self.primary_server_url, timeout=2):
            self._switch_to_local_runtime("Ana server acilis kontrolunde yanit vermedi")

        self.setWindowTitle(f"{APP_VERSION} - Web Arayuz")
        self.resize(1500, 930)
        self.setMinimumSize(1120, 720)
        icon_path = Path(__file__).resolve().parent / "assets" / "yazklinik_app.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.view = QWebEngineView(self)
        if DesktopWebPage is not None:
            self.view.setPage(DesktopWebPage(self.view))
        self._configure_web_profile_cache()
        try:
            self.view.page().printRequested.connect(
                lambda: _print_web_view_native(self.view, self))
        except Exception:
            pass
        self.setCentralWidget(self.view)
        self.setStatusBar(QStatusBar())
        self.statusBar().hide()
        self.view.loadStarted.connect(self._load_started)
        self.view.urlChanged.connect(self._url_changed)
        self.view.loadFinished.connect(self._load_finished)
        try:
            QShortcut(QKeySequence("Ctrl+P"), self, lambda: _print_web_view_native(self.view, self))
        except Exception:
            pass

        # Mirror modu icin durum kontrolu daha seyrek yapilsin (5 dk).
        # Server kesilince fallback _load_finished icinde aninda devreye girer.
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_server_status)
        self.status_timer.start(300000)
        if self.fast_start:
            QTimer.singleShot(12000, self.refresh_server_status)
        else:
            QTimer.singleShot(800, self.refresh_server_status)
        # Pencere arka plan boyamasi - ilk paint flash'i azalsin.
        try:
            self.setAttribute(Qt.WA_OpaquePaintEvent, True)
            self.setAutoFillBackground(True)
        except Exception:
            pass
        self.load_route(self.start_route)

    def _configure_web_profile_cache(self) -> None:
        configure_webengine_profile_cache(self.view, "mirror")

    def _set_runtime_url(self, url: str, mode: str, persist: bool = False) -> None:
        url = (url or "").strip().rstrip("/")
        if mode == "server":
            url = _clean_url(url)
            if persist:
                save_server_url(url)
        else:
            os.environ["YAZKLINIK_ALLOW_LOCAL_TERMINAL_SERVER"] = "1"
        self.server_url = url
        self.connection_mode = "local" if mode == "local" else "server"
        os.environ["YAZKLINIK_WEB_URL"] = url
        os.environ["YAZKLINIK_SERVER_URL"] = url
        os.environ["YAZKLINIK_AI_SERVER_URL"] = url
        write_terminal_runtime_status({
            "mode": self.connection_mode,
            "url": self.server_url,
            "primary_server_url": self.primary_server_url,
            "local_server_url": self.local_server_url,
            "ok": True,
        })

    def _switch_to_local_runtime(self, reason: str = "") -> bool:
        try:
            self.local_server_url = self.local_runtime.start()
            self._set_runtime_url(self.local_server_url, mode="local", persist=False)
            return True
        except Exception as ex:
            write_terminal_runtime_status({
                "mode": "error",
                "url": self.server_url,
                "primary_server_url": self.primary_server_url,
                "error": str(ex) or reason,
                "ok": False,
            })
            return False

    def load_route(self, route: str) -> None:
        self.view.setUrl(QUrl(route_url(self.server_url, route)))

    def _url_changed(self, url: QUrl) -> None:
        if _desktop_restart_requested_url(url):
            QTimer.singleShot(
                700, lambda: _apply_runtime_mode_change_for_window(
                    self, self.server_url))

    def _load_started(self) -> None:
        self.statusBar().showMessage(f"Yukleniyor: {self.server_url}")

    def _load_finished(self, ok: bool) -> None:
        if ok:
            self.statusBar().showMessage(
                "Web arayÃ¼z hazÄ±r - " + (
                    "Ana Server" if self.connection_mode == "server"
                    else "Yerel Terminal API"), 3500)
            return
        if self.connection_mode == "server" and self._switch_to_local_runtime("Sayfa yÃ¼klenemedi"):
            self.load_route(self.start_route)

    def refresh_server_status(self) -> None:
        timeout = 0.75 if self.fast_start else 2
        if self.connection_mode == "local":
            if ping_server_url(self.primary_server_url, timeout=timeout):
                self._set_runtime_url(self.primary_server_url, mode="server", persist=True)
                if not self.fast_start:
                    self.load_route(self.start_route)
            return
        if self.fast_start:
            return
        if not ping_server_url(self.primary_server_url, timeout=timeout):
            if self._switch_to_local_runtime("Server periyodik kontrolde yanit vermedi"):
                self.load_route(self.start_route)


def short_text(value, default: str = "-") -> str:
    text = "" if value is None else str(value).strip()
    return text or default


def patient_display_name(patient: dict) -> str:
    for key in ("display_name", "name", "full_name", "patient_name"):
        if patient.get(key):
            return clean_patient_display_text(patient.get(key), patient_key_value(patient))
    return clean_patient_display_text(
        patient.get("folder_key") or patient.get("patient_key"), "")


def clean_patient_display_text(value, patient_key: str = "",
                               include_date: bool = False) -> str:
    def folder_person_name(raw_name: str) -> str:
        raw = re.sub(r"\s+", " ", str(raw_name or "").replace("_", " ")).strip()
        parts = [p for p in raw.split(" ") if p]
        if len(parts) >= 2:
            return f"{' '.join(parts[1:])} {parts[0]}".strip()
        return raw

    text = str(value or patient_key or "").strip()
    if not text:
        return "Hasta"
    text = re.split(r"[\\/]+", text)[-1].strip()
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    technical_prefix = (
        r"^(?P<prefix>[A-Za-z]?\d{3,}(?:-\d{2}){3}(?:-\d+)?)\s+"
        r"(?P<name>.+)$"
    )
    match = re.match(technical_prefix, text)
    if match:
        text = folder_person_name(match.group("name"))
    elif patient_key:
        match = re.match(technical_prefix, str(patient_key).replace("_", " "))
        if match:
            folder_text = re.sub(r"\s+", " ", match.group("name")).strip()
            if text == patient_key or text == folder_text or text == match.group("name"):
                text = folder_person_name(match.group("name"))
    if include_date and match:
        date_match = re.search(
            r"-(?P<yy>\d{2})-(?P<mm>\d{2})-(?P<dd>\d{2})(?:-\d+)?$",
            match.group("prefix"),
        )
        if date_match:
            yy = int(date_match.group("yy"))
            year = 2000 + yy if yy < 70 else 1900 + yy
            date_text = f"{date_match.group('dd')}.{date_match.group('mm')}.{year}"
            if date_text not in text:
                text = f"{text} ({date_text})"
    return text or "Hasta"


def patient_key_value(patient: dict) -> str:
    return short_text(patient.get("patient_key") or patient.get("folder_key"), "")


def patient_is_obstetric(patient: Optional[dict]) -> bool:
    patient = patient or {}
    type_info = patient.get("type_info") or {}
    demographics = patient.get("demographics") or {}
    raw_values = [
        patient.get("ptype"),
        patient.get("patient_type"),
        patient.get("type"),
        type_info.get("ptype"),
        type_info.get("patient_type"),
        type_info.get("type"),
        demographics.get("lmp_override"),
        demographics.get("lmp"),
        demographics.get("sat"),
        demographics.get("gravida"),
        demographics.get("para"),
        demographics.get("abortus"),
        demographics.get("living"),
    ]
    blob = " ".join(str(v or "") for v in raw_values).casefold()
    if any(word in blob for word in (
            "obstetric", "obstetrik", "gebelik", "gebe", "pregnan")):
        return True
    for key in ("lmp_override", "lmp", "sat", "gravida", "para", "abortus", "living"):
        if demographics.get(key) not in (None, "", "-", 0, "0"):
            return True
    return False


def patient_action_visible_for_patient(route: str, patient: Optional[dict]) -> bool:
    route_lower = str(route or "").casefold()
    if any(marker in route_lower for marker in OBSTETRIC_PATIENT_ROUTE_MARKERS):
        return patient_is_obstetric(patient)
    return True


def native_patient_key_from_route(route: str) -> str:
    path = urllib.parse.urlsplit(route_url("http://x", route)).path
    prefix = "/hasta/"
    if not path.startswith(prefix):
        return ""
    remainder = path[len(prefix):].strip("/")
    if not remainder or "/" in remainder:
        return ""
    return urllib.parse.unquote(remainder)


def load_route_groups() -> tuple[list[tuple[str, list[tuple[str, str, str]]]], set[str]]:
    """Load the full web route catalogue.

    The new shell owns the UI, but it can reuse the existing route catalogue so
    the desktop exposes the same web surface without manually drifting.
    """
    if _sync_desktop_route_groups is not None:
        try:
            groups = _sync_desktop_route_groups()
            simple = (
                set(_sync_simple_control_routes())
                if _sync_simple_control_routes is not None else set()
            )
            if groups:
                return groups, simple
        except Exception:
            pass
    try:
        from yazklinik_v68_navigation import SIMPLE_CONTROL_ROUTES, WebStyleSidebar
        groups = WebStyleSidebar._all_web_control_groups(None)
        simple = set(SIMPLE_CONTROL_ROUTES)
        if groups:
            return groups, simple
    except Exception:
        pass
    return FALLBACK_GROUPS, FALLBACK_SIMPLE_ROUTES


def load_doctor_routes(
    groups: list[tuple[str, list[tuple[str, str, str]]]],
    simple_routes: set[str],
) -> set[str]:
    if _sync_doctor_control_routes is not None:
        try:
            doctor = set(_sync_doctor_control_routes())
            if doctor:
                return doctor
        except Exception:
            pass
    doctor = set(simple_routes)
    for group_name, routes in groups:
        for route, label, hint in routes:
            item = RouteItem(route, label, hint, group_name)
            if route_category(item) != "system":
                doctor.add(route)
    return doctor


def add_shadow(widget: QWidget, blur: int = 24, y: int = 8,
               alpha: int = 34) -> None:
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(blur)
    effect.setOffset(0, y)
    effect.setColor(QColor(15, 38, 35, alpha))
    widget.setGraphicsEffect(effect)


class RouteButton(QPushButton):
    def __init__(self, item: RouteItem):
        super().__init__()
        self.item = item
        self.setObjectName("routeButton")
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self.setMinimumHeight(42)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setText(item.label)
        self.setToolTip(f"{item.group} / {item.label}\n{item.route}\n{item.hint}")


def _desktop_external_url_reason(url: QUrl) -> str:
    scheme = (url.scheme() or "").lower()
    host = (url.host() or "").lower()
    path = (url.path() or "").lower()
    if scheme == "yazklinik-print-photo":
        return "photo-print-helper"
    if scheme == "yazklinik-wa":
        return "whatsapp-local-helper"
    if scheme == "whatsapp" or host in {
        "wa.me", "web.whatsapp.com", "api.whatsapp.com",
    }:
        return "whatsapp"
    if path.endswith(".pdf") or ".pdf" in path:
        return "pdf"
    return ""


def _desktop_launch_whatsapp_local_helper(url: QUrl) -> bool:
    """Run the WhatsApp file-share helper on this workstation."""
    try:
        script = Path(__file__).resolve().with_name(
            "yazklinik_whatsapp_local_helper.py")
        if not script.exists():
            return False
        creationflags = 0x08000000 if os.name == "nt" else 0
        subprocess.Popen(
            [sys.executable, str(script), url.toString()],
            cwd=str(script.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags)
        return True
    except Exception:
        return False


def _desktop_launch_photo_print_helper(url: QUrl) -> bool:
    """Run the JPEG/photo print helper on this workstation."""
    try:
        script = Path(__file__).resolve().with_name(
            "yazklinik_photo_print_helper.py")
        if not script.exists():
            return False
        creationflags = 0x08000000 if os.name == "nt" else 0
        subprocess.Popen(
            [sys.executable, str(script), url.toString()],
            cwd=str(script.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags)
        return True
    except Exception:
        return False


if QWebEnginePage is not None:
    class DesktopWebPage(QWebEnginePage):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            try:
                self.featurePermissionRequested.connect(
                    self._handle_feature_permission)
            except Exception:
                pass

        def _permission_policy(self, granted: bool):
            policy_name = (
                "PermissionGrantedByUser" if granted
                else "PermissionDeniedByUser")
            try:
                return getattr(QWebEnginePage.PermissionPolicy, policy_name)
            except Exception:
                return getattr(QWebEnginePage, policy_name)

        def _handle_feature_permission(self, security_origin, feature):
            feature_name = getattr(feature, "name", None) or str(feature)
            folded = feature_name.lower()
            allow = (
                "mediaaudiocapture" in folded
                or "mediaaudiovideocapture" in folded
                or "notifications" in folded
            )
            try:
                self.setFeaturePermission(
                    security_origin, feature,
                    self._permission_policy(allow))
            except Exception:
                pass

        def acceptNavigationRequest(self, url, nav_type, is_main_frame):
            reason = _desktop_external_url_reason(url)
            if reason == "photo-print-helper":
                if not _desktop_launch_photo_print_helper(url):
                    QDesktopServices.openUrl(url)
                return False
            if reason == "whatsapp-local-helper":
                if not _desktop_launch_whatsapp_local_helper(url):
                    QDesktopServices.openUrl(url)
                return False
            if reason:
                QDesktopServices.openUrl(url)
                return False
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)
else:
    DesktopWebPage = None


def configure_webengine_profile_cache(view, namespace: str = "runtime") -> None:
    if view is None:
        return
    try:
        profile = view.page().profile()
        try:
            ua = profile.httpUserAgent()
            if "YazKlinikDesktop" not in ua:
                profile.setHttpUserAgent((ua + " YazKlinikDesktop/3.0").strip())
        except Exception:
            pass
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home())
        cache_root = base / "YazKlinik" / "WebEngineCache" / namespace
        storage_root = cache_root / "storage"
        cache_root.mkdir(parents=True, exist_ok=True)
        storage_root.mkdir(parents=True, exist_ok=True)
        profile.setCachePath(str(cache_root))
        profile.setPersistentStoragePath(str(storage_root))
        cache_type = getattr(type(profile), "HttpCacheType", None)
        disk_cache = getattr(cache_type, "DiskHttpCache", None) if cache_type else None
        if disk_cache is not None:
            profile.setHttpCacheType(disk_cache)
        try:
            cache_mb = int(float(os.environ.get("YAZKLINIK_WEBENGINE_CACHE_MB", "1024")))
        except Exception:
            cache_mb = 1024
        # Qt expects a signed 32-bit byte count here. Keep the cache below
        # 2 GB to avoid WebEngine overflow warnings and startup instability.
        profile.setHttpCacheMaximumSize(max(256, min(cache_mb, 1024)) * 1024 * 1024)
        cookie_policy = getattr(type(profile), "PersistentCookiesPolicy", None)
        force_cookies = getattr(cookie_policy, "ForcePersistentCookies", None) if cookie_policy else None
        if force_cookies is not None:
            profile.setPersistentCookiesPolicy(force_cookies)
        # SpellCheck'i kapat - CPU tasarrufu
        try:
            profile.setSpellCheckEnabled(False)
        except Exception:
            pass
        settings = view.settings()
        attrs = getattr(type(settings), "WebAttribute", None)
        gpu_turbo = os.environ.get("YAZKLINIK_DESKTOP_GPU_TURBO", "0") == "1"
        # Mirror/shell modunda gereksiz/agir ozellikleri kapat. GPU turbo
        # acikken WebGL ve 2D canvas hizlandirma acik kalsin.
        for name, enabled in (
            ("ScrollAnimatorEnabled", False),
            ("PluginsEnabled", False),
            ("JavascriptCanOpenWindows", False),
            ("PdfViewerEnabled", False),
            ("XSSAuditingEnabled", False),
            ("PlaybackRequiresUserGesture", False),
            ("SpatialNavigationEnabled", False),
            ("LinksIncludedInFocusChain", False),
            ("LocalContentCanAccessRemoteUrls", False),
            ("WebGLEnabled", gpu_turbo),
            ("Accelerated2dCanvasEnabled", gpu_turbo),
        ):
            attr = getattr(attrs, name, None) if attrs else None
            if attr is not None:
                try:
                    settings.setAttribute(attr, enabled)
                except Exception:
                    pass
        # Beyaz arka plan, ilk paint flashini engeller.
        try:
            from PySide6.QtGui import QColor as _QColor
            view.page().setBackgroundColor(_QColor("#ffffff"))
        except Exception:
            pass
    except Exception:
        pass


class WebSurface(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("webSurface")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        if WEB_ENGINE_AVAILABLE:
            self.view = QWebEngineView(self)
            if DesktopWebPage is not None:
                self.view.setPage(DesktopWebPage(self.view))
            configure_webengine_profile_cache(self.view, "shell")
            try:
                self.view.page().printRequested.connect(
                    lambda: _print_web_view_native(self.view, self))
            except Exception:
                pass
            layout.addWidget(self.view, 1)
        else:
            self.view = None
            frame = QFrame()
            frame.setObjectName("webFrame")
            box = QVBoxLayout(frame)
            box.setAlignment(Qt.AlignCenter)
            title = QLabel("Guvenli web modu")
            title.setObjectName("headerTitle")
            title.setFont(QFont("Segoe UI", 18, QFont.Bold))
            msg = QLabel(
                "GPU uyumsuzlugunu onlemek icin derin web ekranlari\n"
                "sistem tarayicisinda acilir. Kabuk burada server API durumunu izler.")
            msg.setAlignment(Qt.AlignCenter)
            box.addWidget(title)
            box.addWidget(msg)
            layout.addWidget(frame, 1)

    def load(self, url: str) -> None:
        if self.view is not None:
            self.view.load(QUrl(url))
        else:
            QDesktopServices.openUrl(QUrl(url))

    def reload(self) -> None:
        if self.view is not None:
            self.view.reload()

    def back(self) -> None:
        if self.view is not None:
            self.view.back()

    def forward(self) -> None:
        if self.view is not None:
            self.view.forward()


class YazKlinikDesktop(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("YazKlinik", "desktop_v1000")
        self.server_url = _clean_url(
            self.settings.value("server_url", read_server_url(), type=str))
        self.mode = _normalize_hybrid_experience_mode(
            self.settings.value("mode", "advanced", type=str) or "advanced")
        self.active_patient_key = ""
        self.active_patient_name = ""
        self.current_route = "/dashboard"
        self._desktop_restart_pending = False
        saved_category = self.settings.value("menu_category", "today", type=str) or "today"
        self.active_category = saved_category if saved_category in MENU_CATEGORY_KEYS else "today"
        self.groups, self.simple_routes = load_route_groups()
        self.doctor_routes = load_doctor_routes(self.groups, self.simple_routes)
        self.route_buttons: list[RouteButton] = []
        self.route_sections: list[tuple[QLabel, list[RouteButton]]] = []
        self.category_buttons: list[tuple[str, QPushButton]] = []
        self.patients_cache: list[dict] = []
        self.stats_cache: dict = {}
        self.status_cache: dict = {}

        self.setWindowTitle(f"{APP_VERSION} - Klinik Web Workbench")
        self.resize(1440, 900)
        icon_path = Path(__file__).resolve().parent / "assets" / "yazklinik_app.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self.setStyleSheet(DESKTOP_QSS)
        self._build_ui()
        self._apply_mode()
        self.navigate("/dashboard")
        QTimer.singleShot(400, self.refresh_status)
        QTimer.singleShot(650, self.refresh_stats)
        QTimer.singleShot(900, self.refresh_patients)
        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_status)
        self.status_timer.start(45000)

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("root")
        root_layout = QHBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(1)
        root_layout.addWidget(splitter, 1)

        self.sidebar = self._build_sidebar()
        self.center = self._build_center()
        self.worklist = self._build_worklist()

        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.center)
        splitter.addWidget(self.worklist)
        splitter.setSizes([300, 900, 320])
        self.setCentralWidget(root)

        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage("YazKlinik v1000.1.8 Web Kabuk hazÄ±r")

    def _build_sidebar(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("sidebar")
        panel.setMinimumWidth(280)
        panel.setMaximumWidth(360)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 16, 16, 14)
        layout.setSpacing(11)

        brand = QLabel("YazKlinik\nWorkbench")
        brand.setObjectName("brandTitle")
        brand.setFont(QFont("Segoe UI", 20, QFont.Bold))
        layout.addWidget(brand)

        sub = QLabel("v1000.1.8 Web Kabuk - web arayuz merkezli")
        sub.setObjectName("brandSubtitle")
        sub.setWordWrap(True)
        layout.addWidget(sub)

        mode_row = QHBoxLayout()
        self.simple_btn = QPushButton("Basit")
        self.doctor_btn = QPushButton("Doktor")
        self.advanced_btn = QPushButton("Uzman")
        for btn in (self.simple_btn, self.doctor_btn, self.advanced_btn):
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(34)
        group = QButtonGroup(self)
        group.setExclusive(True)
        group.addButton(self.simple_btn)
        group.addButton(self.doctor_btn)
        group.addButton(self.advanced_btn)
        self.simple_btn.clicked.connect(lambda: self.set_mode("simple"))
        self.doctor_btn.clicked.connect(lambda: self.set_mode("doctor"))
        self.advanced_btn.clicked.connect(lambda: self.set_mode("advanced"))
        mode_row.addWidget(self.simple_btn)
        mode_row.addWidget(self.doctor_btn)
        mode_row.addWidget(self.advanced_btn)
        layout.addLayout(mode_row)

        self.search = QLineEdit()
        self.search.setObjectName("sidebarSearch")
        self.search.setPlaceholderText("Menu ara veya /route yaz")
        self.search.textChanged.connect(self._filter_routes)
        self.search.returnPressed.connect(self._search_enter)
        layout.addWidget(self.search)

        caption = QLabel("MODULLER")
        caption.setObjectName("menuCaption")
        layout.addWidget(caption)

        self.category_group = QButtonGroup(self)
        self.category_group.setExclusive(True)
        category_grid = QGridLayout()
        category_grid.setHorizontalSpacing(7)
        category_grid.setVerticalSpacing(7)
        for index, (key, label) in enumerate(MENU_CATEGORIES):
            btn = QPushButton(label)
            btn.setObjectName("categoryButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(38)
            btn.clicked.connect(lambda _=False, k=key: self.set_menu_category(k))
            self.category_group.addButton(btn)
            self.category_buttons.append((key, btn))
            category_grid.addWidget(btn, index // 2, index % 2)
        layout.addLayout(category_grid)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        self.route_container = QWidget()
        self.route_container.setObjectName("routeContainer")
        self.route_container.setStyleSheet("background: transparent;")
        self.route_layout = QVBoxLayout(self.route_container)
        self.route_layout.setContentsMargins(0, 0, 0, 0)
        self.route_layout.setSpacing(7)
        scroll.setWidget(self.route_container)
        layout.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        open_btn = QPushButton("TarayÄ±cÄ±")
        open_btn.setObjectName("sidebarToolButton")
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.current_url())))
        refresh_btn = QPushButton("Yenile")
        refresh_btn.setObjectName("sidebarToolButton")
        refresh_btn.clicked.connect(self.refresh_all)
        bottom.addWidget(open_btn)
        bottom.addWidget(refresh_btn)
        layout.addLayout(bottom)

        return panel

    def _metric_card(self, title: str, value: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("metricCard")
        tone = {"MOD": "mode", "SERVER": "server", "HASTA": "patient"}.get(
            title.upper(), "server")
        card.setProperty("tone", tone)
        card.setMinimumWidth(118)
        card.setMaximumWidth(170)
        box = QVBoxLayout(card)
        box.setContentsMargins(12, 8, 12, 8)
        box.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")
        value_label = QLabel(value)
        value_label.setObjectName("metricValue")
        value_label.setWordWrap(False)
        box.addWidget(title_label)
        box.addWidget(value_label)
        add_shadow(card, blur=16, y=4, alpha=18)
        return card, value_label

    def _native_stat_card(self, title: str, value: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("nativePanel")
        tone_map = {
            "Hasta": "teal", "Bugun": "gold", "Risk": "coral", "YZ": "plum",
            "Gelis": "teal", "Tip": "plum", "Protokol": "gold",
        }
        card.setProperty("tone", tone_map.get(title, "teal"))
        card.setMinimumHeight(88)
        box = QVBoxLayout(card)
        box.setContentsMargins(14, 12, 14, 12)
        box.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName("nativeCardTitle")
        value_label = QLabel(value)
        value_label.setObjectName("nativeCardValue")
        box.addWidget(title_label)
        box.addWidget(value_label)
        add_shadow(card, blur=18, y=5, alpha=18)
        return card, value_label

    def _native_action(self, text: str, route: str, primary: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("nativePrimaryActionButton" if primary else "nativeActionButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(38)
        btn.clicked.connect(lambda _=False, r=route: self.navigate(r))
        return btn

    def _build_native_dashboard(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        page.setObjectName("nativeDashboard")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(12)

        hero = QFrame()
        hero.setObjectName("nativeAccentPanel")
        hero_l = QHBoxLayout(hero)
        hero_l.setContentsMargins(18, 16, 18, 16)
        hero_l.setSpacing(14)
        hero_text = QVBoxLayout()
        hero_text.setSpacing(4)
        eyebrow = QLabel("NATIVE KLINIK KOKPIT")
        eyebrow.setObjectName("nativeEyebrow")
        self.native_dashboard_title = QLabel("Bugunun klinik komuta merkezi")
        self.native_dashboard_title.setObjectName("nativeTitle")
        self.native_dashboard_sub = QLabel("Server verisi geldikce hasta, medya ve YZ durumu burada canli izlenir.")
        self.native_dashboard_sub.setObjectName("nativeSub")
        hero_text.addWidget(eyebrow)
        hero_text.addWidget(self.native_dashboard_title)
        hero_text.addWidget(self.native_dashboard_sub)
        hero_l.addLayout(hero_text, 1)
        open_web = self._native_action("Web panel", "/dashboard", primary=False)
        open_web.clicked.disconnect()
        open_web.clicked.connect(lambda: self.open_web_route("/dashboard"))
        hero_l.addWidget(open_web)
        add_shadow(hero, blur=20, y=5, alpha=20)
        layout.addWidget(hero)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        total_card, self.native_total_metric = self._native_stat_card("Hasta", "0")
        today_card, self.native_today_metric = self._native_stat_card("Bugun", "0")
        risk_card, self.native_risk_metric = self._native_stat_card("Risk", "0")
        ai_card, self.native_ai_metric = self._native_stat_card("YZ", "-")
        for card in (total_card, today_card, risk_card, ai_card):
            stats_row.addWidget(card)
        layout.addLayout(stats_row)

        body = QHBoxLayout()
        body.setSpacing(12)

        flow = QFrame()
        flow.setObjectName("nativePanel")
        flow_l = QVBoxLayout(flow)
        flow_l.setContentsMargins(14, 12, 14, 12)
        flow_l.setSpacing(8)
        flow_title = QLabel("Hizli klinik akis")
        flow_title.setObjectName("nativeCardTitle")
        flow_l.addWidget(flow_title)
        for text, route, primary in [
            ("Yeni hasta kaydi", "/yeni-hasta", True),
            ("Hasta ara ve sec", "/arama", False),
            ("Gun plani", "/gun-plani", False),
            ("DICOM/PACS", "/dicom", False),
            ("DICOM servisleri", "/dicom-servisleri", False),
            ("DICOM alisveris", "/dicom-alisveris", False),
            ("YZ asistan", "/yz-asistan", False),
            ("Sistem ayarlari", "/tum-ayarlar", False),
        ]:
            flow_l.addWidget(self._native_action(text, route, primary))
        flow_l.addStretch(1)
        add_shadow(flow, blur=18, y=5, alpha=18)
        body.addWidget(flow, 1)

        recent = QFrame()
        recent.setObjectName("nativePanel")
        recent_l = QVBoxLayout(recent)
        recent_l.setContentsMargins(14, 12, 14, 12)
        recent_l.setSpacing(8)
        recent_title = QLabel("Son hastalar")
        recent_title.setObjectName("nativeCardTitle")
        recent_l.addWidget(recent_title)
        self.native_recent_patients = QListWidget()
        self.native_recent_patients.setObjectName("nativeList")
        self.native_recent_patients.itemDoubleClicked.connect(self._patient_open)
        self.native_recent_patients.currentItemChanged.connect(
            lambda cur, _prev: self._select_patient(cur))
        recent_l.addWidget(self.native_recent_patients, 1)
        add_shadow(recent, blur=18, y=5, alpha=18)
        body.addWidget(recent, 2)

        status = QFrame()
        status.setObjectName("nativePanel")
        status_l = QVBoxLayout(status)
        status_l.setContentsMargins(14, 12, 14, 12)
        status_l.setSpacing(8)
        status_title = QLabel("Sistem durumu")
        status_title.setObjectName("nativeCardTitle")
        status_l.addWidget(status_title)
        self.native_server_line = QLabel("Server: kontrol")
        self.native_server_line.setObjectName("nativeText")
        self.native_ai_line = QLabel("YZ: kontrol")
        self.native_ai_line.setObjectName("nativeText")
        self.native_models_line = QLabel("Model: -")
        self.native_models_line.setObjectName("nativeText")
        self.native_data_line = QLabel("Veri: server uzerinden")
        self.native_data_line.setObjectName("nativeText")
        for label in (
            self.native_server_line, self.native_ai_line,
            self.native_models_line, self.native_data_line,
        ):
            label.setWordWrap(True)
            status_l.addWidget(label)
        status_l.addStretch(1)
        add_shadow(status, blur=18, y=5, alpha=18)
        body.addWidget(status, 1)

        layout.addLayout(body, 1)
        scroll.setWidget(page)
        return scroll

    def _build_native_patient(self) -> QWidget:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(12)

        header = QFrame()
        header.setObjectName("nativePage")
        header_l = QHBoxLayout(header)
        header_l.setContentsMargins(18, 16, 18, 16)
        header_l.setSpacing(14)
        text = QVBoxLayout()
        text.setSpacing(4)
        eyebrow = QLabel("NATIVE HASTA DOSYASI")
        eyebrow.setObjectName("nativeEyebrow")
        self.native_patient_title = QLabel("Hasta secilmedi")
        self.native_patient_title.setObjectName("nativeTitle")
        self.native_patient_sub = QLabel("Sagdaki worklist veya arama ile hasta sec.")
        self.native_patient_sub.setObjectName("nativeSub")
        text.addWidget(eyebrow)
        text.addWidget(self.native_patient_title)
        text.addWidget(self.native_patient_sub)
        header_l.addLayout(text, 1)
        open_patient_web = self._native_action("Web kart", "/hasta/{patient}", primary=True)
        open_patient_web.clicked.disconnect()
        open_patient_web.clicked.connect(lambda: self.open_patient_web("/hasta/{patient}"))
        header_l.addWidget(open_patient_web)
        add_shadow(header, blur=20, y=5, alpha=18)
        layout.addWidget(header)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(10)
        visit_card, self.native_patient_visit_metric = self._native_stat_card("Gelis", "0")
        type_card, self.native_patient_type_metric = self._native_stat_card("Tip", "-")
        protocol_card, self.native_patient_protocol_metric = self._native_stat_card("Protokol", "-")
        risk_card, self.native_patient_risk_metric = self._native_stat_card("Risk", "-")
        for card in (visit_card, type_card, protocol_card, risk_card):
            stats_row.addWidget(card)
        layout.addLayout(stats_row)

        body = QHBoxLayout()
        body.setSpacing(12)

        detail = QFrame()
        detail.setObjectName("nativePanel")
        detail_l = QVBoxLayout(detail)
        detail_l.setContentsMargins(14, 12, 14, 12)
        detail_l.setSpacing(8)
        detail_title = QLabel("Hasta ozeti")
        detail_title.setObjectName("nativeCardTitle")
        self.native_patient_summary = QLabel("Hasta secildiginde serverdan ozet alinir.")
        self.native_patient_summary.setObjectName("nativeText")
        self.native_patient_summary.setWordWrap(True)
        detail_l.addWidget(detail_title)
        detail_l.addWidget(self.native_patient_summary)
        detail_l.addStretch(1)
        add_shadow(detail, blur=18, y=5, alpha=18)
        body.addWidget(detail, 1)

        visits = QFrame()
        visits.setObjectName("nativePanel")
        visits_l = QVBoxLayout(visits)
        visits_l.setContentsMargins(14, 12, 14, 12)
        visits_l.setSpacing(8)
        visits_title = QLabel("Son gelisler")
        visits_title.setObjectName("nativeCardTitle")
        visits_l.addWidget(visits_title)
        self.native_visit_list = QListWidget()
        self.native_visit_list.setObjectName("nativeList")
        visits_l.addWidget(self.native_visit_list, 1)
        add_shadow(visits, blur=18, y=5, alpha=18)
        body.addWidget(visits, 1)

        actions = QFrame()
        actions.setObjectName("nativePanel")
        actions_l = QVBoxLayout(actions)
        actions_l.setContentsMargins(14, 12, 14, 12)
        actions_l.setSpacing(8)
        actions_title = QLabel("Hasta islemleri")
        actions_title.setObjectName("nativeCardTitle")
        actions_l.addWidget(actions_title)
        for text, route, primary in [
            ("Hasta dosyasÄ±", "/hasta/{patient}/hasta-dosyasi", True),
            ("Medya arÅŸivi", "/hasta/{patient}/takip-medya", False),
            ("DICOM medya", "/hasta/{patient}/dicom-medya", False),
            ("DICOM / USG Zeka", "/hasta/{patient}/dicom", False),
            ("Resimle Ã–n TanÄ±", "/hasta/{patient}/gorsel-tani-destegi", False),
            ("YZ anomali", "/hasta/{patient}/yz-anomali-tarama", False),
            ("PDF editor", "/hasta/{patient}/pdf-editor", False),
            ("ReÃ§ete hazÄ±rla", "/hasta/{patient}/recete-hazirla", False),
        ]:
            actions_l.addWidget(self._native_patient_action(text, route, primary))
        actions_l.addStretch(1)
        add_shadow(actions, blur=18, y=5, alpha=18)
        body.addWidget(actions, 1)

        layout.addLayout(body, 1)
        scroll.setWidget(page)
        return scroll

    def _native_patient_action(self, text: str, route: str, primary: bool = False) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName("nativePrimaryActionButton" if primary else "nativeActionButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(38)
        btn.clicked.connect(lambda _=False, r=route: self.navigate_patient(r))
        return btn

    def _build_web_shell(self) -> QWidget:
        web_shell = QFrame()
        web_shell.setObjectName("webFrame")
        web_layout = QVBoxLayout(web_shell)
        web_layout.setContentsMargins(1, 1, 1, 1)
        web_layout.setSpacing(0)
        self.surface = WebSurface()
        if self.surface.view is not None:
            self.surface.view.urlChanged.connect(self._surface_url_changed)
            self.surface.view.loadFinished.connect(self._load_finished)
        web_layout.addWidget(self.surface, 1)
        add_shadow(web_shell, blur=22, y=5, alpha=18)
        return web_shell

    def _surface_url_changed(self, url: QUrl) -> None:
        self.address.setText(url.toString())
        if _desktop_restart_requested_url(url):
            QTimer.singleShot(
                700, lambda: _apply_runtime_mode_change_for_window(
                    self, self.server_url))

    def _build_center(self) -> QWidget:
        panel = QWidget()
        panel.setObjectName("centerPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 14, 14, 12)
        layout.setSpacing(10)

        header = QFrame()
        header.setObjectName("desktopHeader")
        header_l = QHBoxLayout(header)
        header_l.setContentsMargins(16, 12, 16, 12)
        header_l.setSpacing(12)
        header_text = QVBoxLayout()
        header_text.setSpacing(2)
        title = QLabel("YazKlinik Web Kabugu")
        title.setObjectName("headerTitle")
        subtitle = QLabel("Web arayuz ortada, sol menu ve sag hasta paneli kabuk olarak server API ile senkron")
        subtitle.setObjectName("headerSub")
        header_text.addWidget(title)
        header_text.addWidget(subtitle)
        header_l.addLayout(header_text, 1)
        mode_card, self.mode_metric = self._metric_card("MOD", "Uzman")
        server_card, self.server_metric = self._metric_card("SERVER", "Kontrol")
        patient_card, self.patient_metric = self._metric_card("HASTA", "0")
        header_l.addWidget(mode_card)
        header_l.addWidget(server_card)
        header_l.addWidget(patient_card)
        add_shadow(header, blur=20, y=5, alpha=22)
        layout.addWidget(header)

        quick = QFrame()
        quick.setObjectName("commandBand")
        quick_l = QHBoxLayout(quick)
        quick_l.setContentsMargins(12, 10, 12, 10)
        quick_l.setSpacing(8)
        band = QLabel("Hizli akis")
        band.setObjectName("bandTitle")
        quick_l.addWidget(band)
        for text, route, primary in [
            ("Bugun", "/gun-plani", True),
            ("Hasta Bul", "/arama", False),
            ("Yeni Hasta", "/yeni-hasta", False),
            ("DICOM", "/dicom", False),
            ("DICOM Servis", "/dicom-servisleri", False),
            ("YZ Asistan", "/yz-asistan", False),
            ("Tum Ayarlar", "/tum-ayarlar", False),
        ]:
            btn = QPushButton(text)
            btn.setObjectName("primaryQuickButton" if primary else "quickButton")
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(38)
            btn.clicked.connect(lambda _=False, r=route: self.navigate(r))
            quick_l.addWidget(btn)
        quick_l.addStretch(1)
        add_shadow(quick, blur=18, y=4, alpha=14)
        layout.addWidget(quick)

        top = QFrame()
        top.setObjectName("topbar")
        top_l = QHBoxLayout(top)
        top_l.setContentsMargins(8, 8, 8, 8)
        for text, slot in [
            ("Geri", self.web_back),
            ("Ileri", self.web_forward),
            ("Yenile", self.web_reload),
            ("Ana", lambda: self.navigate("/dashboard")),
            ("Akis", lambda: self.navigate("/kullanim-kalitesi")),
        ]:
            btn = QToolButton()
            btn.setObjectName("navButton")
            btn.setText(text)
            btn.clicked.connect(slot)
            top_l.addWidget(btn)

        self.address = QLineEdit()
        self.address.setObjectName("addressBar")
        self.address.setText(self.server_url)
        self.address.returnPressed.connect(self._address_enter)
        top_l.addWidget(self.address, 1)

        self.status_chip = QLabel("Server kontrol")
        self.status_chip.setObjectName("statusChip")
        self.status_chip.setStyleSheet(
            "padding:8px 12px;border-radius:8px;"
            "background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            "stop:0 #FFFFFF,stop:1 #EEF8F6);"
            "color:#213340;font-weight:850;border:1px solid #D4E3E8;")
        top_l.addWidget(self.status_chip)

        settings_btn = QPushButton("Server")
        settings_btn.setObjectName("topButton")
        settings_btn.clicked.connect(self.change_server)
        top_l.addWidget(settings_btn)
        add_shadow(top, blur=18, y=4, alpha=18)
        layout.addWidget(top)

        self.content_stack = QStackedWidget()
        self.dashboard_page = self._build_native_dashboard()
        self.patient_native_page = self._build_native_patient()
        self.web_page = self._build_web_shell()
        self.content_stack.addWidget(self.dashboard_page)
        self.content_stack.addWidget(self.patient_native_page)
        self.content_stack.addWidget(self.web_page)
        layout.addWidget(self.content_stack, 1)
        return panel

    def _build_worklist(self) -> QWidget:
        panel = QFrame()
        panel.setObjectName("worklist")
        panel.setMinimumWidth(300)
        panel.setMaximumWidth(430)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(14, 16, 14, 14)
        layout.setSpacing(11)

        title = QLabel("Hasta Worklist")
        title.setObjectName("worklistTitle")
        title.setFont(QFont("Segoe UI", 15, QFont.Bold))
        layout.addWidget(title)

        self.active_label = QLabel("Aktif hasta secilmedi")
        self.active_label.setObjectName("activePatientCard")
        self.active_label.setWordWrap(True)
        add_shadow(self.active_label, blur=16, y=4, alpha=18)
        layout.addWidget(self.active_label)

        self.patient_search = QLineEdit()
        self.patient_search.setObjectName("patientSearch")
        self.patient_search.setPlaceholderText("Hasta listesinde ara")
        self.patient_search.textChanged.connect(self._filter_patients)
        layout.addWidget(self.patient_search)

        self.patient_list = QListWidget()
        self.patient_list.setObjectName("patientList")
        self.patient_list.itemDoubleClicked.connect(self._patient_open)
        self.patient_list.currentItemChanged.connect(
            lambda cur, _prev: self._select_patient(cur))
        layout.addWidget(self.patient_list, 1)

        refresh = QPushButton("Hasta listesini yenile")
        refresh.setObjectName("worklistPrimaryButton")
        refresh.clicked.connect(self.refresh_patients)
        layout.addWidget(refresh)

        actions_label = QLabel("Hasta islemleri")
        actions_label.setFont(QFont("Segoe UI", 12, QFont.Bold))
        layout.addWidget(actions_label)
        grid = QGridLayout()
        grid.setHorizontalSpacing(6)
        grid.setVerticalSpacing(6)
        self.patient_action_buttons = []
        for index, (label, route) in enumerate(PATIENT_ACTIONS):
            btn = QPushButton(label)
            btn.setObjectName("worklistButton")
            btn.setMinimumHeight(36)
            btn.clicked.connect(lambda _=False, r=route: self.navigate_patient(r))
            grid.addWidget(btn, index // 2, index % 2)
            self.patient_action_buttons.append((btn, route))
        layout.addLayout(grid)

        return panel

    def _populate_routes(self) -> None:
        while self.route_layout.count():
            item = self.route_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.route_buttons.clear()
        self.route_sections.clear()
        if self.mode == "advanced":
            allowed = None
        elif self.mode == "doctor":
            allowed = self.doctor_routes
        else:
            allowed = self.simple_routes
        for group_name, routes in self.groups:
            visible: list[RouteItem] = []
            for route, label, hint in routes:
                if allowed is not None and route not in allowed:
                    continue
                visible.append(RouteItem(route, label, hint, group_name))
            if not visible:
                continue
            group_label = QLabel(group_name)
            group_label.setObjectName("sectionLabel")
            group_label.setFont(QFont("Segoe UI", 11, QFont.Bold))
            self.route_layout.addWidget(group_label)
            for item in visible:
                btn = RouteButton(item)
                btn.clicked.connect(lambda _=False, r=item.route: self.navigate(r))
                self.route_buttons.append(btn)
                self.route_layout.addWidget(btn)
            self.route_sections.append((group_label, self.route_buttons[-len(visible):]))
        self.route_layout.addStretch(1)
        self._filter_routes(self.search.text())
        self._sync_active_route(self.current_route)

    def set_menu_category(self, key: str, persist: bool = True) -> None:
        if key not in MENU_CATEGORY_KEYS:
            key = "today"
        self.active_category = key
        if persist:
            self.settings.setValue("menu_category", key)
        for button_key, button in self.category_buttons:
            button.setChecked(button_key == key)
        if hasattr(self, "search") and not self.search.text().strip():
            self._filter_routes("")

    def _category_for_route(self, route: str) -> str:
        route_path = (route or "/dashboard").split("?", 1)[0]
        for btn in self.route_buttons:
            template = btn.item.route.split("?", 1)[0]
            if "{patient}" in template:
                prefix = template.split("{patient}", 1)[0]
                if prefix and route_path.startswith(prefix):
                    return route_category(btn.item)
            elif template == route_path:
                return route_category(btn.item)
        return route_category(RouteItem(route_path, "", "", ""))

    def set_mode(self, mode: str) -> None:
        self.mode = _normalize_hybrid_experience_mode(mode)
        self.settings.setValue("mode", self.mode)
        self._apply_mode()

    def _apply_mode(self) -> None:
        self.simple_btn.setChecked(self.mode == "simple")
        self.doctor_btn.setChecked(self.mode == "doctor")
        self.advanced_btn.setChecked(self.mode == "advanced")
        active = """
            QPushButton {
                background:qlineargradient(x1:0,y1:0,x2:1,y2:0,
                    stop:0 #2EC4B6, stop:1 #F2C14E);
                color:#101820;border-radius:8px;
                border:1px solid #F5D779;font-weight:850;padding:8px 10px;
            }
        """
        idle = """
            QPushButton {
                background:#22303A;color:#E5EEF1;border-radius:8px;
                border:1px solid #3B4F5E;font-weight:760;padding:8px 10px;
            }
            QPushButton:hover {
                border-color:#57D4C8;background:#274A49;color:#FFFFFF;
            }
        """
        self.simple_btn.setStyleSheet(active if self.mode == "simple" else idle)
        self.doctor_btn.setStyleSheet(active if self.mode == "doctor" else idle)
        self.advanced_btn.setStyleSheet(active if self.mode == "advanced" else idle)
        if hasattr(self, "mode_metric"):
            self.mode_metric.setText(HYBRID_EXPERIENCE_LABELS.get(self.mode, "Uzman"))
        self._populate_routes()
        self.set_menu_category(self.active_category, persist=False)
        self._sync_web_experience_mode()

    def _sync_web_experience_mode(self) -> None:
        mode = _normalize_hybrid_experience_mode(self.mode)
        script = """
        (function(mode) {
          try {
            localStorage.setItem('ykExperienceMode', mode);
            document.documentElement.setAttribute('data-experience', mode);
            if (typeof window.setExperienceMode === 'function') {
              window.setExperienceMode(mode, {silent: true});
            }
          } catch (e) {}
        })(%s);
        """ % json.dumps(mode)
        try:
            view = getattr(getattr(self, "surface", None), "view", None)
            if view is not None:
                view.page().runJavaScript(script)
        except Exception:
            pass

    def _filter_routes(self, text: str) -> None:
        needle = (text or "").strip().casefold()
        searching = bool(needle)
        for btn in self.route_buttons:
            hay = _haystack(btn.item)
            category_match = route_category(btn.item) == self.active_category
            search_match = needle in hay if searching else True
            btn.setVisible(search_match if searching else category_match)
        for label, buttons in self.route_sections:
            label.setVisible(any(button.isVisible() for button in buttons))

    def _search_enter(self) -> None:
        text = self.search.text().strip()
        if text.startswith("/"):
            self.navigate(text)

    def _sync_active_route(self, route: str) -> None:
        self.current_route = route or "/dashboard"
        active_path = self.current_route.split("?", 1)[0]
        for btn in self.route_buttons:
            template = btn.item.route
            template_path = template.split("?", 1)[0]
            if "{patient}" in template_path:
                prefix = template_path.split("{patient}", 1)[0]
                checked = bool(prefix and active_path.startswith(prefix))
            else:
                checked = active_path == template_path
            btn.setChecked(checked)

    def _address_enter(self) -> None:
        text = self.address.text().strip()
        if text.startswith("/"):
            self.navigate(text)
            return
        if text.startswith(("http://", "https://")):
            self.surface.load(text)

    def current_url(self) -> str:
        if self.surface.view is not None:
            url = self.surface.view.url().toString()
            if url:
                return url
        text = self.address.text().strip()
        if text.startswith(("http://", "https://")):
            return text
        return route_url(self.server_url, "/dashboard")

    def _native_dashboard_context(self, route: str) -> tuple[str, str]:
        path = urllib.parse.urlsplit(route_url(self.server_url, route)).path
        if path in {"/", "/arama"}:
            return "Hasta merkezi", "Sagdaki worklist ve arama ile serverdaki hasta verisine native erisim."
        if path in {"/gun-plani", "/gorevler", "/randevular", "/takvim"}:
            return "Gunluk akis", "Bugunun randevu, gorev ve klinik hareketleri tek ekranda."
        if path == "/kullanim-kalitesi":
            return "Klinik kalite merkezi", "Pratik akis, hazirlik ve sistem sagligi icin native kontrol paneli."
        return "Bugunun klinik komuta merkezi", "Server verisi geldikce hasta, medya ve YZ durumu burada canli izlenir."

    def _is_native_dashboard_route(self, route: str) -> bool:
        path = urllib.parse.urlsplit(route_url(self.server_url, route)).path
        return path in {
            "/", "/arama", "/dashboard", "/kullanim-kalitesi",
            "/gun-plani", "/gorevler", "/randevular", "/takvim",
        }

    def show_native_dashboard(self, route: str) -> None:
        title, sub = self._native_dashboard_context(route)
        self.native_dashboard_title.setText(title)
        self.native_dashboard_sub.setText(sub)
        self.content_stack.setCurrentWidget(self.dashboard_page)
        self.address.setText(route_url(self.server_url, route))
        self.statusBar().showMessage(f"Native: {route}", 2500)

    def open_web_route(self, route: str) -> None:
        url = route_url(self.server_url, route)
        self.current_route = route or "/dashboard"
        self.content_stack.setCurrentWidget(self.web_page)
        self.address.setText(url)
        self.surface.load(url)
        self.statusBar().showMessage(f"Web kabuk: {route}", 3000)

    def open_patient_web(self, route: str) -> None:
        if not self.active_patient_key:
            QMessageBox.information(
                self, "Hasta sec", "Once sagdaki worklist'ten hasta sec.")
            return
        encoded = urllib.parse.quote(self.active_patient_key, safe="")
        self.open_web_route(route.replace("{patient}", encoded))

    def show_native_patient(self, patient_key: str) -> None:
        if not patient_key:
            return
        self.content_stack.setCurrentWidget(self.patient_native_page)
        self.address.setText(route_url(
            self.server_url, "/hasta/" + urllib.parse.quote(patient_key, safe="")))
        self._load_native_patient_detail(patient_key)

    def navigate(self, route: str) -> None:
        if "{patient}" in route:
            self.navigate_patient(route)
            return
        if hasattr(self, "category_buttons"):
            self.set_menu_category(self._category_for_route(route), persist=True)
        self._sync_active_route(route)
        if WEB_CENTER_FIRST:
            self.open_web_route(route)
            return
        patient_key = native_patient_key_from_route(route)
        if patient_key:
            self.show_native_patient(patient_key)
            return
        if self._is_native_dashboard_route(route):
            self.show_native_dashboard(route)
            return
        self.open_web_route(route)

    def navigate_patient(self, route: str) -> None:
        if not self.active_patient_key:
            QMessageBox.information(
                self, "Hasta sec", "Once sagdaki worklist'ten hasta sec.")
            return
        encoded = urllib.parse.quote(self.active_patient_key, safe="")
        self.navigate(route.replace("{patient}", encoded))

    def web_back(self) -> None:
        self.surface.back()

    def web_forward(self) -> None:
        self.surface.forward()

    def web_reload(self) -> None:
        self.surface.reload()

    def change_server(self) -> None:
        new_url = self.address.text().strip()
        if not new_url.startswith(("http://", "https://")):
            new_url = self.server_url
        self.server_url = _clean_url(new_url)
        self.settings.setValue("server_url", self.server_url)
        save_server_url(self.server_url)
        os.environ["YAZKLINIK_WEB_URL"] = self.server_url
        self.navigate("/dashboard")
        self.refresh_all()

    def refresh_all(self) -> None:
        self.refresh_status()
        self.refresh_stats()
        self.refresh_patients()

    def refresh_stats(self) -> None:
        try:
            data = fetch_json(self.server_url, "/api/terminal/stats", timeout=5)
            stats = data.get("stats") or {}
            self.stats_cache = stats
            total = short_text(stats.get("total"), "0")
            today = short_text(stats.get("today_visits"), "0")
            risky = short_text(stats.get("risky"), "0")
            if hasattr(self, "native_total_metric"):
                self.native_total_metric.setText(total)
                self.native_today_metric.setText(today)
                self.native_risk_metric.setText(risky)
        except Exception as ex:
            if hasattr(self, "native_data_line"):
                self.native_data_line.setText(f"Stats: alinamadi ({ex})")

    def refresh_status(self) -> None:
        try:
            data = fetch_json(self.server_url, "/api/terminal/ping", timeout=4)
            self.status_cache = data
            ollama = "YZ OK" if data.get("ollama_online") else "YZ yok"
            version = data.get("app_version") or data.get("version") or "server"
            self.status_chip.setText(f"Server OK | {ollama}")
            self.status_chip.setStyleSheet(
                "padding:8px 12px;border-radius:8px;background:#DDF6F3;"
                "color:#0F3431;font-weight:850;border:1px solid #7ADBD0;")
            if hasattr(self, "server_metric"):
                self.server_metric.setText("Online")
            if hasattr(self, "native_server_line"):
                self.native_server_line.setText(f"Server: Online - {version}")
                self.native_ai_line.setText(f"YZ: {ollama}")
                models = data.get("models") or []
                model_text = ", ".join(map(str, models[:3])) if models else "-"
                self.native_models_line.setText(f"Model: {model_text}")
                self.native_ai_metric.setText("OK" if data.get("ollama_online") else "Yok")
            self.statusBar().showMessage(f"{version} - {self.server_url}", 5000)
        except Exception as ex:
            self.status_chip.setText("Server yok")
            self.status_chip.setStyleSheet(
                "padding:8px 12px;border-radius:8px;background:#FFF0EC;"
                "color:#7A241E;font-weight:850;border:1px solid #EAA18D;")
            if hasattr(self, "server_metric"):
                self.server_metric.setText("Offline")
            if hasattr(self, "native_server_line"):
                self.native_server_line.setText("Server: Offline")
                self.native_ai_line.setText("YZ: server bekleniyor")
                self.native_models_line.setText("Model: -")
                self.native_ai_metric.setText("Yok")
            self.statusBar().showMessage(f"Server kontrol edilemedi: {ex}", 8000)

    def refresh_patients(self) -> None:
        self.patient_list.clear()
        if hasattr(self, "native_recent_patients"):
            self.native_recent_patients.clear()
        try:
            data = fetch_json(self.server_url, "/api/terminal/patients", timeout=8)
            patients = data.get("patients") or []
            self.patients_cache = patients
            if hasattr(self, "patient_metric"):
                self.patient_metric.setText(str(len(patients)))
            for patient in patients:
                key = patient_key_value(patient)
                name = patient_display_name(patient)
                display = str(patient.get("display_label") or name).strip()
                last_visit = short_text(patient.get("last_visit"), "")
                item = QListWidgetItem(f"{display}\nSon gelis: {last_visit}")
                item.setData(Qt.UserRole, {"key": key, "name": name, "patient": patient})
                self.patient_list.addItem(item)
                if hasattr(self, "native_recent_patients") and self.native_recent_patients.count() < 12:
                    native_item = QListWidgetItem(f"{display}\nSon gelis: {last_visit}")
                    native_item.setData(Qt.UserRole, {"key": key, "name": name, "patient": patient})
                    self.native_recent_patients.addItem(native_item)
            self._filter_patients(self.patient_search.text())
        except Exception as ex:
            self.patients_cache = []
            if hasattr(self, "patient_metric"):
                self.patient_metric.setText("Yok")
            item = QListWidgetItem(f"Hasta listesi alinamadi\n{ex}")
            item.setFlags(Qt.NoItemFlags)
            self.patient_list.addItem(item)
            if hasattr(self, "native_recent_patients"):
                native_item = QListWidgetItem(f"Hasta listesi alinamadi\n{ex}")
                native_item.setFlags(Qt.NoItemFlags)
                self.native_recent_patients.addItem(native_item)

    def _select_patient(self, item: Optional[QListWidgetItem]) -> None:
        if not item:
            return
        data = item.data(Qt.UserRole) or {}
        key = data.get("key") or ""
        if not key:
            return
        self.active_patient_key = key
        self.active_patient_name = data.get("name") or key
        self._refresh_patient_action_visibility(data.get("patient") or {})
        self.active_label.setText(
            f"Aktif hasta\n{self.active_patient_name}")
        if self.content_stack.currentWidget() == self.patient_native_page:
            self._load_native_patient_detail(key)

    def _patient_open(self, item: QListWidgetItem) -> None:
        self._select_patient(item)
        self.navigate_patient("/hasta/{patient}")

    def _load_native_patient_detail(self, patient_key: str) -> None:
        encoded = urllib.parse.quote(patient_key, safe="")
        self.native_patient_title.setText(self.active_patient_name or patient_key)
        self.native_patient_sub.setText(patient_key)
        self.native_patient_summary.setText("Serverdan hasta ozeti aliniyor...")
        self.native_visit_list.clear()
        try:
            data = fetch_json(
                self.server_url, f"/api/terminal/patient/{encoded}", timeout=8)
            patient = data.get("patient") or {}
            if patient:
                self.active_patient_name = patient_display_name(patient)
                self.native_patient_title.setText(self.active_patient_name)
                self._refresh_patient_action_visibility(patient)
            visits = patient.get("visits") or []
            demographics = patient.get("demographics") or {}
            type_info = patient.get("type_info") or {}
            flags = patient.get("flags") or {}
            protocol = short_text(
                patient.get("protocol_no") or demographics.get("protocol_no") or patient.get("protocol"))
            patient_type = short_text(
                type_info.get("patient_type") or type_info.get("type") or patient.get("type"))
            risk_count = sum(1 for value in flags.values() if str(value) == "1")
            self.native_patient_visit_metric.setText(str(len(visits)))
            self.native_patient_type_metric.setText(patient_type)
            self.native_patient_protocol_metric.setText(protocol)
            self.native_patient_risk_metric.setText(str(risk_count) if flags else "-")
            summary_lines = [
                f"Protokol: {protocol}",
                f"Telefon: {short_text(patient.get('phone') or demographics.get('phone'))}",
                f"TC: {short_text(patient.get('tc') or demographics.get('tc'))}",
                f"Son gelis: {short_text(patient.get('last_visit'))}",
                f"Kayit: {short_text(patient.get('created_at'))}",
            ]
            self.native_patient_summary.setText("\n".join(summary_lines))
            for visit in visits[:12]:
                date = short_text(visit.get("visit_date") or visit.get("date"))
                note = short_text(
                    visit.get("summary") or visit.get("note") or visit.get("complaint"), "")
                self.native_visit_list.addItem(f"{date}\n{note[:90]}")
            if not visits:
                self.native_visit_list.addItem("Gelis kaydi yok")
        except Exception as ex:
            self.native_patient_summary.setText(f"Hasta detayi alinamadi:\n{ex}")

    def _refresh_patient_action_visibility(self, patient: Optional[dict]) -> None:
        for button, route in getattr(self, "patient_action_buttons", []):
            button.setVisible(patient_action_visible_for_patient(route, patient))

    def _filter_patients(self, text: str) -> None:
        needle = (text or "").strip().lower()
        for i in range(self.patient_list.count()):
            item = self.patient_list.item(i)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _load_finished(self, ok: bool) -> None:
        if ok:
            self._sync_web_experience_mode()
            self.statusBar().showMessage("Sayfa hazir", 1500)
        else:
            self.statusBar().showMessage("Sayfa yuklenemedi", 6000)


WEB_SHELL_THEMES = {
    "windows": {
        "window": "#ECF3F8",
        "chrome": "#FDFEFF",
        "surface": "#FFFFFF",
        "surface_soft": "#F4F8FC",
        "line": "#C9D8E6",
        "text": "#112033",
        "muted": "#5B6F84",
        "accent": "#0B5CAB",
        "accent_2": "#00AFA5",
        "accent_3": "#D44A28",
        "button": "#FEFFFF",
        "button_hover": "#EEF7FF",
        "button_checked": "#DDEEFF",
        "address": "#FFFFFF",
        "brand_bg": "#E7F3FF",
        "status_ok_bg": "#E5F6ED",
        "status_ok_text": "#0F6B43",
        "status_busy_bg": "#FFF5D7",
        "status_busy_text": "#7A5600",
        "status_bad_bg": "#FDE7E9",
        "status_bad_text": "#A4262C",
        "rail": "#F8FBFE",
        "rail_button": "#FFFFFF",
        "command": "#FFFFFF",
        "metric": "#F6FAFD",
        "glass": "#F8FBFE",
        "premium_bg": "#E7EFF7",
        "premium_ink": "#0F172A",
        "premium_gold": "#C58A1F",
        "premium_coral": "#D44A28",
        "premium_violet": "#6D5BD0",
    },
    "light": {
        "window": "#EEF3F8",
        "chrome": "#F8FAFD",
        "surface": "#FFFFFF",
        "surface_soft": "#F3F7FB",
        "line": "#D5E0EA",
        "text": "#17202A",
        "muted": "#637083",
        "accent": "#2563EB",
        "accent_2": "#2EC4B6",
        "accent_3": "#E85D75",
        "button": "#FFFFFF",
        "button_hover": "#EEF6FF",
        "button_checked": "#E7F0FF",
        "address": "#FFFFFF",
        "brand_bg": "#EEF6FF",
        "status_ok_bg": "#E8F7F0",
        "status_ok_text": "#146C43",
        "status_busy_bg": "#FFF4DB",
        "status_busy_text": "#8A5A00",
        "status_bad_bg": "#FFE8EA",
        "status_bad_text": "#A51D2D",
    },
    "dark": {
        "window": "#14171D",
        "chrome": "#1D222A",
        "surface": "#232A33",
        "surface_soft": "#191F27",
        "line": "#3A4655",
        "text": "#F4F7FA",
        "muted": "#A8B3C2",
        "accent": "#60A5FA",
        "accent_2": "#34D399",
        "accent_3": "#FB7185",
        "button": "#262E38",
        "button_hover": "#303A47",
        "button_checked": "#1E3A5F",
        "address": "#151A21",
        "brand_bg": "#202A36",
        "status_ok_bg": "#123629",
        "status_ok_text": "#8DE2B5",
        "status_busy_bg": "#3A2F16",
        "status_busy_text": "#FFD37A",
        "status_bad_bg": "#3C1D26",
        "status_bad_text": "#FF9DAA",
    },
    "clinical": {
        "window": "#F0F6F4",
        "chrome": "#FAFCFB",
        "surface": "#FFFFFF",
        "surface_soft": "#ECF7F3",
        "line": "#C9DED7",
        "text": "#142B2B",
        "muted": "#58706E",
        "accent": "#0F8B8D",
        "accent_2": "#2EC4B6",
        "accent_3": "#E85D75",
        "button": "#FFFFFF",
        "button_hover": "#E8F8F5",
        "button_checked": "#DDF4EF",
        "address": "#FFFFFF",
        "brand_bg": "#E5F7F2",
        "status_ok_bg": "#E0F6EC",
        "status_ok_text": "#116A4C",
        "status_busy_bg": "#FFF2D8",
        "status_busy_text": "#835200",
        "status_bad_bg": "#FFE8EA",
        "status_bad_text": "#A51D2D",
    },
}


class YazKlinikWebShell(QMainWindow):
    """Windows-first shell that renders the server web UI as a desktop app."""

    QUICK_ROUTES = (
        ("Hastalar", "/"),
        ("Dashboard", "/dashboard"),
        ("Gun Plani", "/gun-plani"),
        ("Randevular", "/randevular"),
        ("Yeni Hasta", "/yeni-hasta"),
        ("Doguranlar", "/doguranlar"),
        ("Dosya Konumlari", "/sistem/dosya-konumlari"),
    )

    RAIL_ROUTES = (
        ("Ana", "/dashboard", "SP_ComputerIcon"),
        ("Hastalar", "/", "SP_FileDialogContentsView"),
        ("Randevu", "/randevular", "SP_FileDialogDetailedView"),
        ("DICOM", "/dicom", "SP_DriveHDIcon"),
        ("DICOM Servis", "/dicom-servisleri", "SP_ComputerIcon"),
        ("DICOM Alis", "/dicom-alisveris", "SP_DialogApplyButton"),
        ("Medya", "/takip-medya-arsivi", "SP_FileIcon"),
        ("YZ", "/yz-asistan", "SP_MessageBoxInformation"),
        ("Ayar", "/tum-ayarlar", "SP_FileDialogInfoView"),
    )

    def __init__(self):
        super().__init__()
        self.settings = QSettings("YazKlinik", "desktop_web_shell")
        self.primary_server_url = _clean_url(read_server_url())
        self.server_url = self.primary_server_url
        self.connection_mode = "server"
        self.local_runtime = LocalTerminalWebRuntime()
        self.local_server_url = ""
        self.last_requested_route = "/dashboard"
        self._desktop_restart_pending = False
        save_server_url(self.primary_server_url)
        self._set_runtime_url(self.primary_server_url, mode="server", persist=True)
        if not ping_server_url(self.primary_server_url, timeout=2):
            self._switch_to_local_runtime("Ana server acilis kontrolunde yanit vermedi")

        self.theme_buttons: dict[str, QPushButton] = {}
        self.quick_buttons: dict[str, QPushButton] = {}
        self.rail_buttons: dict[str, QPushButton] = {}
        self.module_buttons: list[tuple[RouteItem, QPushButton]] = []
        self.module_sections: list[tuple[QLabel, list[QPushButton]]] = []
        self.active_patient_key = ""
        self.active_patient_name = ""
        self.shell_patients_cache: list[dict] = []
        self.groups, self.simple_routes = load_route_groups()
        saved_theme = str(self.settings.value("theme", "windows") or "windows")
        migrated = str(self.settings.value("fluent_shell_theme_migrated", "0") or "0")
        if saved_theme == "light" and migrated != "1":
            saved_theme = "windows"
            self.settings.setValue("theme", saved_theme)
            self.settings.setValue("fluent_shell_theme_migrated", "1")
        self.current_theme = saved_theme
        if self.current_theme not in WEB_SHELL_THEMES:
            self.current_theme = "windows"

        self.setWindowTitle(f"{APP_VERSION} - Windows Klinik Arayuz")
        self.resize(1500, 930)
        self.setMinimumSize(1120, 720)
        icon_path = Path(__file__).resolve().parent / "assets" / "yazklinik_app.ico"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        if QWebEngineView is None:
            raise RuntimeError("QtWebEngine bulunamadi")

        root = QWidget()
        root.setObjectName("webShellRoot")
        root.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        chrome = self._build_chrome()
        layout.addWidget(chrome, 0)
        if LEAN_WEB_SHELL:
            chrome.setVisible(False)

        self.progress = QProgressBar()
        self.progress.setObjectName("webShellProgress")
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress, 0)

        body = QFrame()
        self.shell_body = body
        body.setObjectName("webShellBody")
        body.installEventFilter(self)
        body_l = QHBoxLayout(body)
        body_l.setContentsMargins(8, 8, 8, 8)
        body_l.setSpacing(8)

        self.nav_rail = self._build_navigation_rail()
        body_l.addWidget(self.nav_rail, 0)

        workspace = QWidget()
        workspace.setObjectName("webShellWorkspace")
        workspace_l = QVBoxLayout(workspace)
        workspace_l.setContentsMargins(0, 0, 0, 0)
        workspace_l.setSpacing(10)

        self.command_strip = self._build_command_strip()
        workspace_l.addWidget(self.command_strip, 0)
        if LEAN_WEB_SHELL:
            self.command_strip.setVisible(False)

        self.center_stack = QStackedWidget()
        self.center_stack.setObjectName("webShellCenterStack")
        self.native_center = self._build_native_api_center()
        self.center_stack.addWidget(self.native_center)
        self.native_tool_center = self._build_native_professional_tool_center()
        self.center_stack.addWidget(self.native_tool_center)

        self.web_frame = QFrame()
        self.web_frame.setObjectName("webShellViewport")
        viewport_l = QVBoxLayout(self.web_frame)
        viewport_l.setContentsMargins(1, 1, 1, 1)
        viewport_l.setSpacing(0)

        self.web_window_bar = QFrame()
        self.web_window_bar.setObjectName("webShellWebTitlebar")
        titlebar_l = QHBoxLayout(self.web_window_bar)
        titlebar_l.setContentsMargins(12, 9, 12, 9)
        titlebar_l.setSpacing(10)
        self.web_module_icon = QLabel("YK")
        self.web_module_icon.setObjectName("webShellWebIcon")
        self.web_module_title = QLabel("Server modulu")
        self.web_module_title.setObjectName("webShellWebTitle")
        self.web_module_subtitle = QLabel("Windows kabugu icinde web motoru")
        self.web_module_subtitle.setObjectName("webShellWebSub")
        title_text = QVBoxLayout()
        title_text.setContentsMargins(0, 0, 0, 0)
        title_text.setSpacing(1)
        title_text.addWidget(self.web_module_title)
        title_text.addWidget(self.web_module_subtitle)
        titlebar_l.addWidget(self.web_module_icon, 0)
        titlebar_l.addLayout(title_text, 1)
        self.web_module_route = QLabel("/")
        self.web_module_route.setObjectName("webShellWebRoute")
        titlebar_l.addWidget(self.web_module_route, 0)
        viewport_l.addWidget(self.web_window_bar, 0)
        if LEAN_WEB_SHELL:
            self.web_window_bar.setVisible(False)

        self.view = QWebEngineView(self.web_frame)
        if DesktopWebPage is not None:
            self.view.setPage(DesktopWebPage(self.view))
        configure_webengine_profile_cache(self.view, "shell")
        try:
            self.view.page().printRequested.connect(
                lambda: _print_web_view_native(self.view, self))
        except Exception:
            pass
        viewport_l.addWidget(self.view, 1)
        add_shadow(self.web_frame, blur=26, y=8, alpha=24)
        self.center_stack.addWidget(self.web_frame)
        workspace_l.addWidget(self.center_stack, 1)
        body_l.addWidget(workspace, 1)

        self.api_panel = self._build_api_bridge_panel()
        self.api_panel.setParent(body)
        self.api_panel.raise_()
        if LEAN_WEB_SHELL:
            self.api_panel.setVisible(False)
        layout.addWidget(body, 1)

        self.setCentralWidget(root)
        self.setStatusBar(QStatusBar())
        self._apply_theme(self.current_theme, persist=False)
        self._update_runtime_labels()

        self.view.urlChanged.connect(self._url_changed)
        self.view.loadStarted.connect(self._load_started)
        self.view.loadFinished.connect(self._load_finished)
        try:
            self.view.loadProgress.connect(self._load_progress)
        except Exception:
            pass

        self.back_btn.clicked.connect(self.view.back)
        self.forward_btn.clicked.connect(self.view.forward)
        self.reload_btn.clicked.connect(self.view.reload)
        self.home_btn.clicked.connect(self.go_home)
        try:
            QShortcut(QKeySequence("Ctrl+P"), self, lambda: _print_web_view_native(self.view, self))
        except Exception:
            pass

        self.status_timer = QTimer(self)
        self.status_timer.timeout.connect(self.refresh_server_status)
        self.status_timer.start(45000)
        QTimer.singleShot(300, self.refresh_server_status)
        if not LEAN_WEB_SHELL:
            self.api_timer = QTimer(self)
            self.api_timer.timeout.connect(self.refresh_api_bridge)
            self.api_timer.start(30000)
            QTimer.singleShot(900, self.refresh_api_bridge)
            QTimer.singleShot(0, self._position_api_cockpit)

        self.go_home()

    def _set_runtime_url(self, url: str, mode: str, persist: bool = False) -> None:
        url = (url or "").strip().rstrip("/")
        if mode == "server":
            url = _clean_url(url)
            if persist:
                save_server_url(url)
        else:
            os.environ["YAZKLINIK_ALLOW_LOCAL_TERMINAL_SERVER"] = "1"
        self.server_url = url
        self.connection_mode = "local" if mode == "local" else "server"
        os.environ["YAZKLINIK_WEB_URL"] = url
        os.environ["YAZKLINIK_SERVER_URL"] = url
        os.environ["YAZKLINIK_AI_SERVER_URL"] = url
        write_terminal_runtime_status({
            "mode": self.connection_mode,
            "url": self.server_url,
            "primary_server_url": self.primary_server_url,
            "local_server_url": self.local_server_url,
            "ok": True,
        })
        self._update_runtime_labels()

    def _update_runtime_labels(self) -> None:
        mode_label = "Ana Server" if self.connection_mode == "server" else "Yerel Terminal API"
        try:
            if hasattr(self, "server_label"):
                self.server_label.setText(f"{mode_label}: {self.server_url}")
            if hasattr(self, "shell_server_value"):
                self.shell_server_value.setText(
                    "Server" if self.connection_mode == "server" else "Yerel")
            if hasattr(self, "command_subtitle"):
                self.command_subtitle.setText(
                    f"{mode_label} - veri DB/NAS ve API motorundan")
            if hasattr(self, "web_module_subtitle"):
                self.web_module_subtitle.setText(
                    "Web arayuz birebir, motor: " + mode_label)
        except Exception:
            pass

    def _current_route_for_reload(self) -> str:
        try:
            url = self.view.url()
            path = url.path() or self.last_requested_route or "/dashboard"
            query = url.query()
            return path + (("?" + query) if query else "")
        except Exception:
            return self.last_requested_route or "/dashboard"

    def _reload_current_route_after_runtime_change(self) -> None:
        if not hasattr(self, "view"):
            return
        route = self._current_route_for_reload()
        QTimer.singleShot(150, lambda r=route: self.load_url(r))

    def _switch_to_local_runtime(self, reason: str = "") -> bool:
        try:
            self.local_server_url = self.local_runtime.start()
            self._set_runtime_url(self.local_server_url, mode="local", persist=False)
            if hasattr(self, "status_label"):
                self._set_status("Yerel Terminal API aktif", "busy")
            if hasattr(self, "api_bridge_state"):
                self._set_api_state(
                    "Ana server yok; terminal kendi yerel web/API motoru ile devam ediyor.",
                    "busy",
                )
            if hasattr(self, "statusBar"):
                self.statusBar().showMessage(
                    f"Yerel terminal API aktif: {self.local_server_url} | {reason}",
                    9000,
                )
            return True
        except Exception as ex:
            if hasattr(self, "status_label"):
                self._set_status("Yerel API baslamadi", "bad")
            if hasattr(self, "statusBar"):
                self.statusBar().showMessage(
                    f"Yerel terminal API baslatilamadi: {ex}", 12000)
            return False

    def _switch_to_primary_runtime(self) -> bool:
        if not ping_server_url(self.primary_server_url, timeout=2):
            return False
        self._set_runtime_url(self.primary_server_url, mode="server", persist=True)
        if hasattr(self, "status_label"):
            self._set_status("Ana Server OK", "ok")
        if hasattr(self, "statusBar"):
            self.statusBar().showMessage(
                f"Ana server geri geldi: {self.primary_server_url}", 7000)
        return True

    def _build_navigation_rail(self) -> QFrame:
        rail = QFrame()
        rail.setObjectName("webShellRail")
        rail.setMinimumWidth(258 if LEAN_WEB_SHELL else 292)
        rail.setMaximumWidth(300 if LEAN_WEB_SHELL else 360)
        rail_l = QVBoxLayout(rail)
        rail_l.setContentsMargins(10, 10, 10, 10)
        rail_l.setSpacing(8)

        logo_row = QHBoxLayout()
        logo_row.setSpacing(8)
        logo = QLabel("YK")
        logo.setObjectName("webShellLogo")
        logo.setAlignment(Qt.AlignCenter)
        logo.setFixedSize(42, 42)
        logo_row.addWidget(logo, 0)
        logo_text = QVBoxLayout()
        logo_text.setSpacing(0)
        app_name = QLabel("YazKlinik")
        app_name.setObjectName("webShellRailTitle")
        app_sub = QLabel("WebShell") if LEAN_WEB_SHELL else QLabel("Windows API Panel")
        app_sub.setObjectName("webShellRailSub")
        logo_text.addWidget(app_name)
        logo_text.addWidget(app_sub)
        logo_row.addLayout(logo_text, 1)
        rail_l.addLayout(logo_row)

        line = QFrame()
        line.setObjectName("webShellDivider")
        line.setFrameShape(QFrame.HLine)
        rail_l.addWidget(line)

        section = QLabel("Menuler" if LEAN_WEB_SHELL else "Windows Pencereleri")
        section.setObjectName("webShellRailSection")
        rail_l.addWidget(section)
        for label, route, icon in self.RAIL_ROUTES:
            rail_l.addWidget(self._rail_button(label, route, icon))

        modules = self._build_module_browser()
        rail_l.addWidget(modules, 1)

        open_browser = self._rail_button("TarayÄ±cÄ±", "__browser__", "SP_DialogOpenButton")
        open_browser.clicked.disconnect()
        open_browser.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl(self.address.text() or self._entry_url())))
        rail_l.addWidget(open_browser)
        return rail

    def _build_module_browser(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("webShellModulePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 8, 0, 0)
        layout.setSpacing(7)

        section = QLabel("Tum Server Modulleri")
        section.setObjectName("webShellRailSection")
        layout.addWidget(section)

        self.module_search = QLineEdit()
        self.module_search.setObjectName("webShellModuleSearch")
        self.module_search.setClearButtonEnabled(True)
        self.module_search.setPlaceholderText("Modul ara")
        self.module_search.textChanged.connect(self._filter_web_modules)
        self.module_search.returnPressed.connect(self._module_search_enter)
        layout.addWidget(self.module_search)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        container.setObjectName("webShellModuleContainer")
        container_l = QVBoxLayout(container)
        container_l.setContentsMargins(0, 0, 0, 0)
        container_l.setSpacing(5)

        for group_name, rows in self.groups:
            group_label = QLabel(group_name)
            group_label.setObjectName("webShellModuleGroup")
            container_l.addWidget(group_label)
            group_buttons: list[QPushButton] = []
            for route, label, hint in rows:
                item = RouteItem(route=route, label=label, hint=hint, group=group_name)
                btn = QPushButton(label)
                btn.setObjectName("webShellModuleButton")
                btn.setCursor(Qt.PointingHandCursor)
                btn.setMinimumHeight(34)
                btn.setToolTip(f"{group_name} / {label}\n{route}\n{hint}")
                btn.setProperty("patientReady", "{patient}" not in route)
                btn.clicked.connect(lambda checked=False, r=route: self.load_template_route(r))
                container_l.addWidget(btn)
                group_buttons.append(btn)
                self.module_buttons.append((item, btn))
            self.module_sections.append((group_label, group_buttons))

        container_l.addStretch(1)
        scroll.setWidget(container)
        layout.addWidget(scroll, 1)
        return panel

    def _rail_button(self, label: str, route: str, icon_name: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("webShellRailButton")
        btn.setCheckable(route != "__browser__")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(42)
        btn.setIcon(self._standard_icon(icon_name))
        btn.clicked.connect(lambda checked=False, r=route: self.load_url(r))
        if route != "__browser__":
            self.rail_buttons[route] = btn
        return btn

    def _command_button(self, label: str, route: str, primary: bool = False) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("webShellCommandPrimary" if primary else "webShellCommandButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(38)
        btn.clicked.connect(lambda checked=False, r=route: self.load_url(r))
        return btn

    def _shell_metric(self, title: str, value: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("webShellMetric")
        card_l = QVBoxLayout(card)
        card_l.setContentsMargins(12, 8, 12, 8)
        card_l.setSpacing(1)
        title_label = QLabel(title)
        title_label.setObjectName("webShellMetricTitle")
        value_label = QLabel(value)
        value_label.setObjectName("webShellMetricValue")
        value_label.setMinimumWidth(96)
        card_l.addWidget(title_label)
        card_l.addWidget(value_label)
        return card, value_label

    def _build_command_strip(self) -> QFrame:
        strip = QFrame()
        strip.setObjectName("webShellCommandStrip")
        strip_l = QHBoxLayout(strip)
        strip_l.setContentsMargins(14, 12, 14, 12)
        strip_l.setSpacing(10)

        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        title = QLabel("Windows Klinik Penceresi")
        title.setObjectName("webShellCommandTitle")
        self.command_subtitle = QLabel(
            f"{self.server_url} - veri server API'den")
        self.command_subtitle.setObjectName("webShellCommandSub")
        title_box.addWidget(title)
        title_box.addWidget(self.command_subtitle)
        strip_l.addLayout(title_box, 1)

        for label, route, primary in (
            ("Hasta Listesi", "/", True),
            ("Yeni Hasta", "/yeni-hasta", False),
            ("Gun Plani", "/gun-plani", False),
            ("PACS", "/dicom", False),
            ("DICOM Servisleri", "/dicom-servisleri", False),
            ("YZ", "/yz-asistan", False),
        ):
            strip_l.addWidget(self._command_button(label, route, primary), 0)

        server_card, self.shell_server_value = self._shell_metric("SERVER", "Kontrol")
        ai_card, self.shell_ai_value = self._shell_metric("YZ", "Kontrol")
        route_card, self.shell_route_value = self._shell_metric("EKRAN", "/")
        patient_card, self.shell_patient_value = self._shell_metric("HASTA", "-")
        strip_l.addWidget(server_card, 0)
        strip_l.addWidget(ai_card, 0)
        strip_l.addWidget(route_card, 0)
        strip_l.addWidget(patient_card, 0)
        add_shadow(strip, blur=20, y=5, alpha=18)
        return strip

    def _center_button(self, label: str, route: str = "",
                       primary: bool = False) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("webShellCenterPrimary" if primary else "webShellCenterButton")
        tone_map = {
            "PDF": "violet",
            "NAS/DICOM": "teal",
            "DICOM/NAS": "teal",
            "HD Studio": "gold",
            "Resimle Ã–n TanÄ±": "coral",
            "WhatsApp": "green",
            "Diyet": "teal",
            "Gebe Plan": "gold",
            "Gebe Grafik": "teal",
            "Gebelik Gelisim": "teal",
            "Anomali": "coral",
            "Dosya Konumlari": "violet",
            "YZ Asistan": "violet",
            "YZ asistan": "violet",
            "YZ Diyalog": "violet",
            "DICOM merkezi": "teal",
            "NAS/Data senkron": "gold",
        }
        tone = tone_map.get(label)
        if tone:
            btn.setProperty("tone", tone)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(38)
        if route:
            btn.clicked.connect(lambda checked=False, r=route: self.load_url(r))
        return btn

    def _center_metric(self, title: str, value: str) -> tuple[QFrame, QLabel]:
        card = QFrame()
        card.setObjectName("webShellCenterMetric")
        tone_map = {
            "Hasta": "patient",
            "Bugun": "today",
            "Risk": "risk",
            "YZ": "ai",
        }
        card.setProperty("tone", tone_map.get(title, "patient"))
        box = QVBoxLayout(card)
        box.setContentsMargins(16, 12, 16, 12)
        box.setSpacing(3)
        t = QLabel(title)
        t.setObjectName("webShellCenterMetricTitle")
        v = QLabel(value)
        v.setObjectName("webShellCenterMetricValue")
        box.addWidget(t)
        box.addWidget(v)
        add_shadow(card, blur=18, y=5, alpha=16)
        return card, v

    def _build_native_api_center(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("webShellNativeCenter")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        page = QWidget()
        page.setObjectName("webShellNativePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        desktop = QFrame()
        desktop.setObjectName("webShellDesktopSurface")
        desktop_l = QVBoxLayout(desktop)
        desktop_l.setContentsMargins(16, 16, 16, 12)
        desktop_l.setSpacing(13)

        ribbon = QFrame()
        ribbon.setObjectName("webShellWinRibbon")
        ribbon_l = QHBoxLayout(ribbon)
        ribbon_l.setContentsMargins(18, 14, 18, 14)
        ribbon_l.setSpacing(12)
        mark = QLabel("YK")
        mark.setObjectName("webShellWinRibbonMark")
        mark.setAlignment(Qt.AlignCenter)
        mark.setFixedSize(54, 54)
        ribbon_l.addWidget(mark, 0)
        title_box = QVBoxLayout()
        title_box.setSpacing(2)
        self.center_title = QLabel("YazKlinik Premium Windows Masasi")
        self.center_title.setObjectName("webShellNativeTitle")
        self.center_subtitle = QLabel(
            "Windows gibi gorunur; hasta, NAS, DICOM, PDF ve YZ isleri server API'den akar")
        self.center_subtitle.setObjectName("webShellNativeSub")
        title_box.addWidget(self.center_title)
        title_box.addWidget(self.center_subtitle)
        ribbon_l.addLayout(title_box, 1)
        self.win_api_badge = QLabel("LIVE API: kontrol")
        self.win_api_badge.setObjectName("webShellWinBadge")
        self.win_api_badge.setProperty("tone", "api")
        self.win_active_badge = QLabel("HASTA: yok")
        self.win_active_badge.setObjectName("webShellWinBadge")
        self.win_active_badge.setProperty("tone", "patient")
        ribbon_l.addWidget(self.win_api_badge, 0)
        ribbon_l.addWidget(self.win_active_badge, 0)
        for label, route, primary in (
            ("Hasta Merkezi", "/", True),
            ("Gunluk Akis", "/gun-plani", False),
            ("DICOM/NAS", "/dicom", False),
            ("Ayarlar", "/tum-ayarlar", False),
        ):
            ribbon_l.addWidget(self._center_button(label, route, primary), 0)
        add_shadow(ribbon, blur=18, y=4, alpha=16)
        desktop_l.addWidget(ribbon, 0)

        metrics = QHBoxLayout()
        metrics.setSpacing(10)
        total_card, self.center_total_value = self._center_metric("Hasta", "0")
        today_card, self.center_today_value = self._center_metric("Bugun", "0")
        risk_card, self.center_risk_value = self._center_metric("Risk", "0")
        ai_card, self.center_ai_value = self._center_metric("YZ", "-")
        for card in (total_card, today_card, risk_card, ai_card):
            metrics.addWidget(card, 1)
        desktop_l.addLayout(metrics)

        panes = QSplitter(Qt.Horizontal)
        panes.setObjectName("webShellWinPanes")
        panes.setChildrenCollapsible(False)
        panes.setHandleWidth(1)

        explorer = QFrame()
        explorer.setObjectName("webShellNativePanel")
        explorer.setMinimumWidth(280)
        explorer_l = QVBoxLayout(explorer)
        explorer_l.setContentsMargins(14, 12, 14, 12)
        explorer_l.setSpacing(8)
        explorer_l.addWidget(self._native_panel_title("Hasta Gezgini"))
        self.center_patient_search = QLineEdit()
        self.center_patient_search.setObjectName("webShellCenterSearch")
        self.center_patient_search.setClearButtonEnabled(True)
        self.center_patient_search.setPlaceholderText("Server API hasta ara")
        self.center_patient_search.textChanged.connect(self._filter_center_patients)
        explorer_l.addWidget(self.center_patient_search)
        self.center_patient_list = QListWidget()
        self.center_patient_list.setObjectName("webShellCenterPatientList")
        self.center_patient_list.currentItemChanged.connect(
            lambda cur, _prev: self._select_center_patient(cur, open_patient=False))
        self.center_patient_list.itemDoubleClicked.connect(
            lambda item: self._select_center_patient(item, open_patient=True))
        explorer_l.addWidget(self.center_patient_list, 1)
        panes.addWidget(explorer)

        active = QFrame()
        active.setObjectName("webShellWinWorkbench")
        active_l = QVBoxLayout(active)
        active_l.setContentsMargins(16, 14, 16, 14)
        active_l.setSpacing(10)
        active_l.addWidget(self._native_panel_title("Aktif Hasta Calisma Masasi"))
        self.center_active_title = QLabel("Hasta secilmedi")
        self.center_active_title.setObjectName("webShellNativePatientTitle")
        self.center_active_sub = QLabel("Soldaki veya sagdaki API listesinden hasta secin")
        self.center_active_sub.setObjectName("webShellNativeSub")
        self.center_patient_summary = QLabel("Hasta secilince serverdan ozet alinir.")
        self.center_patient_summary.setObjectName("webShellNativeText")
        self.center_patient_summary.setWordWrap(True)
        active_l.addWidget(self.center_active_title)
        active_l.addWidget(self.center_active_sub)
        active_l.addWidget(self.center_patient_summary)

        detail_grid = QGridLayout()
        detail_grid.setHorizontalSpacing(8)
        detail_grid.setVerticalSpacing(8)
        self.center_phone_value = QLabel("-")
        self.center_last_visit_value = QLabel("-")
        self.center_protocol_value = QLabel("-")
        self.center_risk_detail_value = QLabel("-")
        for idx, (title, widget) in enumerate((
            ("Telefon", self.center_phone_value),
            ("Son Gelis", self.center_last_visit_value),
            ("Protokol", self.center_protocol_value),
            ("Risk", self.center_risk_detail_value),
        )):
            tile = QFrame()
            tile.setObjectName("webShellWinDetailTile")
            tile_l = QVBoxLayout(tile)
            tile_l.setContentsMargins(10, 8, 10, 8)
            tile_l.setSpacing(2)
            t = QLabel(title)
            t.setObjectName("webShellCenterMetricTitle")
            widget.setObjectName("webShellWinDetailValue")
            widget.setWordWrap(True)
            tile_l.addWidget(t)
            tile_l.addWidget(widget)
            detail_grid.addWidget(tile, idx // 2, idx % 2)
        active_l.addLayout(detail_grid)

        active_actions = QGridLayout()
        active_actions.setHorizontalSpacing(7)
        active_actions.setVerticalSpacing(7)
        patient_actions = (
            ("Kart", "/hasta/{patient}", True),
            ("Dosya", "/hasta/{patient}/hasta-dosyasi", False),
            ("ReÃ§ete", "/hasta/{patient}/recete-hazirla", False),
            ("PDF", "/hasta/{patient}/pdf-atolyesi", False),
            ("NAS/DICOM", "/hasta/{patient}/dosya-gezgini", False),
            ("DICOM AI", "/hasta/{patient}/dicom", False),
            ("HD Studio", "/hasta/{patient}/yz-resim-iyilestir", False),
            ("Resimle Ã–n TanÄ±", "/hasta/{patient}/gorsel-tani-destegi", False),
            ("WhatsApp", "/hasta/{patient}/whatsapp", False),
            ("Diyet", "/hasta/{patient}/yz-diyet", False),
            ("Gebe Plan", "/hasta/{patient}/gebelik-takip-plani", False),
            ("Gebe Grafik", "/hasta/{patient}/gebelik-gelisim-takibi", False),
            ("Anomali", "/hasta/{patient}/yz-anomali-tarama", False),
        )
        self.center_patient_action_buttons = []
        for idx, (label, route, primary) in enumerate(patient_actions):
            btn = self._center_button(label, "", primary)
            btn.clicked.connect(lambda checked=False, r=route: self.open_active_patient_route(r))
            active_actions.addWidget(btn, idx // 3, idx % 3)
            self.center_patient_action_buttons.append((btn, route))
        active_l.addLayout(active_actions)
        active_l.addWidget(self._native_panel_title("Server Modulu Pencereleri"))
        module_row = QGridLayout()
        module_row.setHorizontalSpacing(7)
        module_row.setVerticalSpacing(7)
        for idx, (label, route, primary) in enumerate((
            ("Randevu", "/randevular", False),
            ("Medya Arsivi", "/takip-medya-arsivi", False),
            ("YZ Asistan", "/yz-asistan", False),
            ("YZ Diyalog", "/yz-telefon-diyalog", False),
            ("Kullanim Kalitesi", "/kullanim-kalitesi", False),
            ("Dosya Konumlari", "/sistem/dosya-konumlari", False),
            ("Tum Moduller", "/menu-ara", False),
        )):
            module_row.addWidget(self._center_button(label, route, primary),
                                 idx // 3, idx % 3)
        active_l.addLayout(module_row)
        active_l.addStretch(1)
        panes.addWidget(active)

        flow = QFrame()
        flow.setObjectName("webShellWinOps")
        flow.setMinimumWidth(250)
        flow_l = QVBoxLayout(flow)
        flow_l.setContentsMargins(14, 12, 14, 12)
        flow_l.setSpacing(8)
        flow_l.addWidget(self._native_panel_title("Server Isleri"))
        self.win_data_source = QLabel(
            "Veri kaynaklari: /api/terminal/stats, /patients, /active-patient")
        self.win_data_source.setObjectName("webShellNativeText")
        self.win_data_source.setWordWrap(True)
        flow_l.addWidget(self.win_data_source)
        for label, route, primary in (
            ("Hasta listesi", "/", True),
            ("Gun plani", "/gun-plani", False),
            ("Randevular", "/randevular", False),
            ("DICOM merkezi", "/dicom", False),
            ("DICOM servisleri", "/dicom-servisleri", False),
            ("DICOM alisveris", "/dicom-alisveris", False),
            ("YZ asistan", "/yz-asistan", False),
            ("YZ Diyalog", "/yz-telefon-diyalog", False),
            ("Tum server modulleri", "/menu-ara", False),
        ):
            flow_l.addWidget(self._center_button(label, route, primary))
        nas = self._center_button("NAS/Data senkron", "")
        nas.clicked.connect(self.run_api_nas_sync)
        flow_l.addWidget(nas)
        self.win_flow_note = QLabel(
            "Bu orta ekran Windows gibi davranir; islem ve veri server PC'de calisir.")
        self.win_flow_note.setObjectName("webShellNativeText")
        self.win_flow_note.setWordWrap(True)
        flow_l.addWidget(self.win_flow_note)
        flow_l.addStretch(1)
        panes.addWidget(flow)
        panes.setSizes([300, 620, 280])
        for panel in (explorer, active, flow):
            add_shadow(panel, blur=22, y=6, alpha=18)
        desktop_l.addWidget(panes, 1)

        taskbar = QFrame()
        taskbar.setObjectName("webShellTaskbar")
        taskbar_l = QHBoxLayout(taskbar)
        taskbar_l.setContentsMargins(12, 8, 12, 8)
        taskbar_l.setSpacing(10)
        start = QLabel("YazKlinik")
        start.setObjectName("webShellTaskStart")
        self.win_task_patient = QLabel("Hasta: yok")
        self.win_task_patient.setObjectName("webShellTaskText")
        self.win_task_server = QLabel("Server API bekleniyor")
        self.win_task_server.setObjectName("webShellTaskText")
        taskbar_l.addWidget(start, 0)
        taskbar_l.addWidget(self.win_task_patient, 1)
        taskbar_l.addWidget(self.win_task_server, 0)
        add_shadow(taskbar, blur=18, y=4, alpha=14)
        desktop_l.addWidget(taskbar, 0)

        layout.addWidget(desktop, 1)
        scroll.setWidget(page)
        return scroll

    def _native_panel_title(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setObjectName("webShellNativePanelTitle")
        return label

    def _api_button(self, label: str, route: str = "",
                    primary: bool = False) -> QPushButton:
        btn = QPushButton(label)
        btn.setObjectName("webShellApiPrimary" if primary else "webShellApiButton")
        btn.setCursor(Qt.PointingHandCursor)
        btn.setMinimumHeight(36)
        if route:
            btn.clicked.connect(lambda checked=False, r=route: self.open_active_patient_route(r))
        return btn

    def _build_api_bridge_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("webShellApiPanel")
        panel.setMouseTracking(True)
        panel.installEventFilter(self)
        panel.setFixedWidth(344)
        panel.setFixedHeight(44)
        self.api_cockpit_expanded = False
        self.api_cockpit_pinned = False
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(10, 7, 10, 10)
        layout.setSpacing(8)

        title = QLabel("API Kokpit")
        title.setObjectName("webShellApiTitle")
        sub = QLabel("Windows yuz, server API motor")
        sub.setObjectName("webShellApiSub")
        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(0)
        title_box.addWidget(title)
        title_box.addWidget(sub)
        header = QFrame()
        header.setObjectName("webShellApiHandle")
        header.setMouseTracking(True)
        header_l = QHBoxLayout(header)
        header_l.setContentsMargins(0, 0, 0, 0)
        header_l.setSpacing(8)
        header_l.addLayout(title_box, 1)
        self.api_cockpit_hint = QLabel("hover")
        self.api_cockpit_hint.setObjectName("webShellApiHint")
        header_l.addWidget(self.api_cockpit_hint, 0)
        self.api_cockpit_toggle = QToolButton()
        self.api_cockpit_toggle.setObjectName("webShellApiToggle")
        self.api_cockpit_toggle.setText("v")
        self.api_cockpit_toggle.setToolTip("API kokpiti ac/kilitle")
        self.api_cockpit_toggle.clicked.connect(self.toggle_api_cockpit_pinned)
        header_l.addWidget(self.api_cockpit_toggle, 0)
        layout.addWidget(header, 0)

        self.api_panel_content = QWidget()
        content_l = QVBoxLayout(self.api_panel_content)
        content_l.setContentsMargins(0, 0, 0, 0)
        content_l.setSpacing(8)

        self.api_bridge_state = QLabel("API baglantisi kontrol ediliyor")
        self.api_bridge_state.setObjectName("webShellApiState")
        self.api_bridge_state.setWordWrap(True)
        content_l.addWidget(self.api_bridge_state)

        self.api_active_patient = QLabel("Aktif hasta yok")
        self.api_active_patient.setObjectName("webShellApiPatient")
        self.api_active_patient.setWordWrap(True)
        content_l.addWidget(self.api_active_patient)

        self.api_patient_search = QLineEdit()
        self.api_patient_search.setObjectName("webShellApiSearch")
        self.api_patient_search.setClearButtonEnabled(True)
        self.api_patient_search.setPlaceholderText("API hasta ara")
        self.api_patient_search.textChanged.connect(self._filter_api_patients)
        content_l.addWidget(self.api_patient_search)

        self.api_patient_list = QListWidget()
        self.api_patient_list.setObjectName("webShellApiPatientList")
        self.api_patient_list.currentItemChanged.connect(
            lambda cur, _prev: self._select_api_patient(cur, open_patient=False))
        self.api_patient_list.itemDoubleClicked.connect(
            lambda item: self._select_api_patient(item, open_patient=True))
        content_l.addWidget(self.api_patient_list, 1)

        grid = QGridLayout()
        grid.setHorizontalSpacing(7)
        grid.setVerticalSpacing(7)
        actions = [
            ("Hasta Kart", "/hasta/{patient}", True),
            ("Dosya", "/hasta/{patient}/hasta-dosyasi", False),
            ("PDF Sayfasi", "/hasta/{patient}/pdf-atolyesi", False),
            ("NAS/DICOM", "/hasta/{patient}/dosya-gezgini", False),
            ("DICOM AI", "/hasta/{patient}/dicom", False),
            ("WhatsApp", "/hasta/{patient}/whatsapp", False),
            ("Diyet", "/hasta/{patient}/yz-diyet", False),
            ("Gebelik Gelisim", "/hasta/{patient}/gebelik-gelisim-takibi", False),
        ]
        for index, (label, route, primary) in enumerate(actions):
            grid.addWidget(self._api_button(label, route, primary),
                           index // 2, index % 2)
        content_l.addLayout(grid)

        refresh_row = QHBoxLayout()
        refresh = self._api_button("API Yenile")
        refresh.clicked.connect(self.refresh_api_bridge)
        nas_sync = self._api_button("NAS Senkron")
        nas_sync.clicked.connect(self.run_api_nas_sync)
        refresh_row.addWidget(refresh)
        refresh_row.addWidget(nas_sync)
        content_l.addLayout(refresh_row)
        layout.addWidget(self.api_panel_content, 1)
        self.api_panel_content.setVisible(False)
        return panel

    def _set_api_cockpit_expanded(self, expanded: bool, pinned: bool = None) -> None:
        if pinned is not None:
            self.api_cockpit_pinned = bool(pinned)
        self.api_cockpit_expanded = bool(expanded)
        if hasattr(self, "api_panel_content"):
            self.api_panel_content.setVisible(self.api_cockpit_expanded)
        if hasattr(self, "api_panel"):
            height = 430 if self.api_cockpit_expanded else 44
            parent = self.api_panel.parentWidget()
            if parent is not None:
                height = min(height, max(44, parent.height() - 24))
            self.api_panel.setFixedHeight(height)
            self.api_panel.raise_()
        if hasattr(self, "api_cockpit_toggle"):
            self.api_cockpit_toggle.setText("^" if self.api_cockpit_expanded else "v")
            self.api_cockpit_toggle.setChecked(self.api_cockpit_pinned)
        if hasattr(self, "api_cockpit_hint"):
            if self.api_cockpit_pinned:
                text = "pinned"
            elif self.api_cockpit_expanded:
                text = "open"
            else:
                text = "hover"
            self.api_cockpit_hint.setText(text)
        self._position_api_cockpit()

    def toggle_api_cockpit_pinned(self) -> None:
        if self.api_cockpit_pinned:
            self._set_api_cockpit_expanded(False, pinned=False)
        else:
            self._set_api_cockpit_expanded(True, pinned=True)

    def _position_api_cockpit(self) -> None:
        try:
            panel = self.api_panel
            parent = panel.parentWidget()
            if parent is None:
                return
            width = panel.width() or 344
            x = max(12, parent.width() - width - 20)
            y = 12
            panel.move(x, y)
            panel.raise_()
        except Exception:
            pass

    def eventFilter(self, obj, event):
        try:
            if obj is getattr(self, "api_panel", None):
                if event.type() == QEvent.Enter:
                    self._set_api_cockpit_expanded(True)
                elif event.type() == QEvent.Leave and not self.api_cockpit_pinned:
                    self._set_api_cockpit_expanded(False)
            elif obj is getattr(self, "shell_body", None):
                if event.type() in (QEvent.Resize, QEvent.Show):
                    QTimer.singleShot(0, self._position_api_cockpit)
        except Exception:
            pass
        return super().eventFilter(obj, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._position_api_cockpit)

    def _set_api_state(self, text: str, state: str = "ok") -> None:
        try:
            self.api_bridge_state.setText(text)
            self.api_bridge_state.setProperty("state", state)
            self.api_bridge_state.style().unpolish(self.api_bridge_state)
            self.api_bridge_state.style().polish(self.api_bridge_state)
            self.api_bridge_state.update()
        except Exception:
            pass

    def _set_shell_active_patient(self, patient_key: str, display_name: str = "",
                                  sync_server: bool = False) -> None:
        patient_key = str(patient_key or "").strip()
        display_name = clean_patient_display_text(
            str(display_name or "").strip() or patient_key, patient_key)
        changed = (
            patient_key != self.active_patient_key or
            display_name != self.active_patient_name)
        self.active_patient_key = patient_key
        self.active_patient_name = display_name
        if not patient_key:
            self._refresh_center_patient_actions({})
        try:
            if patient_key:
                self.shell_patient_value.setText((display_name or patient_key)[:18])
                self.api_active_patient.setText(
                    f"Aktif hasta\n{display_name}")
                if hasattr(self, "center_active_title"):
                    self.center_active_title.setText(display_name or patient_key)
                    self.center_active_sub.setText("Hasta dosyasÄ± hazÄ±r")
                if hasattr(self, "win_task_patient"):
                    self.win_task_patient.setText(
                        f"Hasta: {display_name or patient_key} | {patient_key}")
                if hasattr(self, "win_active_badge"):
                    self.win_active_badge.setText(
                        f"HASTA: {(display_name or patient_key)[:28]}")
            else:
                self.shell_patient_value.setText("-")
                self.api_active_patient.setText("Aktif hasta yok")
                if hasattr(self, "center_active_title"):
                    self.center_active_title.setText("Hasta secilmedi")
                    self.center_active_sub.setText("Soldaki veya sagdaki API listesinden hasta secin")
                if hasattr(self, "win_task_patient"):
                    self.win_task_patient.setText("Hasta: yok")
                if hasattr(self, "win_active_badge"):
                    self.win_active_badge.setText("HASTA: yok")
        except Exception:
            pass
        for item, button in self.module_buttons:
            if "{patient}" in item.route:
                button.setProperty("patientReady", bool(patient_key))
                button.style().unpolish(button)
                button.style().polish(button)
                button.update()
        if sync_server and patient_key:
            try:
                fetch_json(
                    self.server_url,
                    "/api/terminal/active-patient/set",
                    timeout=5,
                    method="POST",
                    body={
                        "patient_key": patient_key,
                        "display_name": display_name,
                        "source": "windows_shell_api",
                    },
                )
                if changed:
                    self.statusBar().showMessage(
                        f"Aktif hasta API ile eslendi: {display_name}", 3000)
                    if hasattr(self, "center_patient_summary"):
                        self._load_center_patient_detail(patient_key)
            except Exception as ex:
                self.statusBar().showMessage(
                    f"Aktif hasta server'a yazilamadi: {ex}", 6000)

    def _select_api_patient(self, item: Optional[QListWidgetItem],
                            open_patient: bool = False) -> None:
        if not item:
            return
        data = item.data(Qt.UserRole) or {}
        key = data.get("key") or ""
        if not key:
            return
        self._set_shell_active_patient(
            key, data.get("name") or key, sync_server=True)
        self._refresh_center_patient_actions(data.get("patient") or {})
        if open_patient:
            self.open_active_patient_route("/hasta/{patient}")

    def _populate_api_patients(self) -> None:
        if not hasattr(self, "api_patient_list"):
            return
        needle = (self.api_patient_search.text() or "").strip().casefold()
        self.api_patient_list.clear()
        for patient in self.shell_patients_cache:
            key = patient_key_value(patient)
            name = patient_display_name(patient)
            display = str(patient.get("display_label") or name).strip()
            last_visit = short_text(patient.get("last_visit"), "")
            hay = f"{key} {name} {last_visit}".casefold()
            if needle and needle not in hay:
                continue
            item = QListWidgetItem(f"{display}\nSon gelis: {last_visit}")
            item.setData(Qt.UserRole, {"key": key, "name": name, "patient": patient})
            self.api_patient_list.addItem(item)

    def _populate_center_patients(self) -> None:
        if not hasattr(self, "center_patient_list"):
            return
        needle = (self.center_patient_search.text() or "").strip().casefold()
        self.center_patient_list.clear()
        for patient in self.shell_patients_cache[:900]:
            key = patient_key_value(patient)
            name = patient_display_name(patient)
            display = str(patient.get("display_label") or name).strip()
            last_visit = short_text(patient.get("last_visit"), "")
            protocol = short_text(patient.get("protocol_no"), "")
            hay = f"{key} {name} {last_visit} {protocol}".casefold()
            if needle and needle not in hay:
                continue
            text = display
            if protocol or last_visit:
                text += f"\nProtokol: {protocol or '-'}  Son gelis: {last_visit or '-'}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, {"key": key, "name": name, "patient": patient})
            self.center_patient_list.addItem(item)

    def _filter_api_patients(self, text: str = "") -> None:
        self._populate_api_patients()

    def _filter_center_patients(self, text: str = "") -> None:
        self._populate_center_patients()

    def _select_center_patient(self, item: Optional[QListWidgetItem],
                               open_patient: bool = False) -> None:
        if not item:
            return
        data = item.data(Qt.UserRole) or {}
        key = data.get("key") or ""
        if not key:
            return
        self._set_shell_active_patient(
            key, data.get("name") or key, sync_server=True)
        self._refresh_center_patient_actions(data.get("patient") or {})
        self._load_center_patient_detail(key)
        if open_patient:
            self.open_active_patient_route("/hasta/{patient}")

    def _update_center_stats(self, stats: Optional[dict] = None,
                             status: Optional[dict] = None) -> None:
        stats = stats or {}
        status = status or {}
        try:
            if stats:
                self.center_total_value.setText(short_text(stats.get("total"), "0"))
                self.center_today_value.setText(short_text(
                    stats.get("today_visits") or stats.get("today_appts"), "0"))
                self.center_risk_value.setText(short_text(stats.get("risky"), "0"))
                if hasattr(self, "win_task_server"):
                    self.win_task_server.setText(
                        "Server API | hasta {0} | bugun {1}".format(
                            short_text(stats.get("total"), "0"),
                            short_text(stats.get("today_visits") or stats.get("today_appts"), "0")))
            if status:
                self.center_ai_value.setText(
                    "HazÄ±r" if status.get("ollama_online") else "Beklemede")
                if hasattr(self, "win_api_badge"):
                    self.win_api_badge.setText(
                        "API: online" if status.get("ok", True) else "API: sorun")
        except Exception:
            pass

    def _center_context_for_route(self, route: str) -> tuple[str, str]:
        path = urllib.parse.urlsplit(route_url(self.server_url, route)).path
        if path in {"/", "/arama"}:
            return "Windows Native Hasta Merkezi", "Hasta listesi server API'den gelir"
        if path in {"/gun-plani", "/gorevler", "/randevular", "/takvim"}:
            return "Windows Native Gunluk Akis", "Randevu ve gunluk komutlar serverda calisir"
        if path == "/kullanim-kalitesi":
            return "Windows Native Klinik Kalite", "Kontrol ve akis komutlari API ile yenilenir"
        return "Windows Native Klinik Merkezi", "Server API ile canli calisir"

    def _is_native_shell_route(self, route: str) -> bool:
        path = urllib.parse.urlsplit(route_url(self.server_url, route)).path
        return path in {
            "/", "/arama", "/dashboard", "/kullanim-kalitesi",
            "/gun-plani", "/gorevler", "/randevular", "/takvim",
        }

    def _patient_key_from_route(self, route: str) -> str:
        path = urllib.parse.urlsplit(route_url(self.server_url, route)).path
        parts = [p for p in path.strip("/").split("/") if p]
        if len(parts) == 2 and parts[0].lower() == "hasta":
            return urllib.parse.unquote(parts[1])
        return ""

    def _route_title_for_shell(self, route: str) -> tuple[str, str]:
        path = urllib.parse.urlsplit(route_url(self.server_url, route)).path or "/"
        patient_parts = [p for p in path.strip("/").split("/") if p]
        if len(patient_parts) >= 2 and patient_parts[0].lower() == "hasta":
            action = patient_parts[2].replace("-", " ").title() if len(patient_parts) >= 3 else "Hasta Karti"
            return f"Hasta modulu - {action}", "Hasta verisi server API ve web motorundan beslenir"
        for group_name, routes in self.groups:
            for route_template, label, hint in routes:
                template_path = urllib.parse.urlsplit(
                    route_url(self.server_url, route_template)).path
                if template_path == path:
                    return label, hint or group_name
        title = path.strip("/").replace("-", " ").replace("/", " / ").title() or "Dashboard"
        return title, "Windows kabugu icinde server web modulu"

    def _update_web_module_chrome(self, route: str) -> None:
        title, subtitle = self._route_title_for_shell(route)
        try:
            path = urllib.parse.urlsplit(route_url(self.server_url, route)).path or "/"
        except Exception:
            path = str(route or "/")
        if hasattr(self, "web_module_title"):
            self.web_module_title.setText(title[:72])
            self.web_module_subtitle.setText(subtitle[:110])
            self.web_module_route.setText(path[:34])

    def show_native_center(self, route: str = "/dashboard") -> None:
        title, subtitle = self._center_context_for_route(route)
        self.center_title.setText(title)
        self.center_subtitle.setText(subtitle)
        self.center_stack.setCurrentWidget(self.native_center)
        self.address.setText(route_url(self.server_url, route))
        self._sync_quick_buttons(QUrl(route_url(self.server_url, route)))
        self.shell_route_value.setText((route or "/dashboard")[:18])
        self.statusBar().showMessage(f"Native API ekran: {route}", 2500)
        self.refresh_api_bridge()

    def _is_native_professional_tool_route(self, route: str) -> bool:
        try:
            path = urllib.parse.urlsplit(route_url(self.server_url, route)).path.lower()
        except Exception:
            path = str(route or "").lower()
        tokens = (
            "/pdf-atolyesi", "/pdf-editor", "/yz-resim-iyilestir",
            "/hd-studio", "/pdf-studio", "/rapor-editor"
        )
        return path.startswith("/hasta/") and any(token in path for token in tokens)

    def _build_native_professional_tool_center(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setObjectName("webShellNativeCenter")
        scroll.setWidgetResizable(True)
        page = QWidget()
        page.setObjectName("webShellNativePage")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(22, 22, 22, 22)
        layout.setSpacing(14)

        hero = QFrame()
        hero.setObjectName("webShellWinDetailTile")
        hero_l = QVBoxLayout(hero)
        hero_l.setContentsMargins(18, 16, 18, 16)
        hero_l.setSpacing(8)
        self.native_tool_title = QLabel("Native Studio")
        self.native_tool_title.setObjectName("webShellCommandTitle")
        self.native_tool_subtitle = QLabel(
            "PDF editor ve HD Studio gibi agir islemler icin hibrit/native calisma alani.")
        self.native_tool_subtitle.setObjectName("webShellCommandSub")
        self.native_tool_subtitle.setWordWrap(True)
        self.native_tool_route = QLabel("/")
        self.native_tool_route.setObjectName("webShellWebRoute")
        self.native_tool_route.setWordWrap(True)
        hero_l.addWidget(self.native_tool_title)
        hero_l.addWidget(self.native_tool_subtitle)
        hero_l.addWidget(self.native_tool_route)
        layout.addWidget(hero)

        grid = QGridLayout()
        grid.setSpacing(10)

        def add_button(row: int, col: int, label: str, route_builder, primary=False):
            btn = QPushButton(label)
            btn.setObjectName("webShellCenterPrimary" if primary else "webShellCenterButton")
            btn.clicked.connect(lambda _=False, rb=route_builder: self.load_url(rb()))
            grid.addWidget(btn, row, col)
            return btn

        web_btn = QPushButton("Web motorunda tam ac")
        web_btn.setObjectName("webShellCenterPrimary")
        web_btn.clicked.connect(self._open_professional_tool_in_web)
        grid.addWidget(web_btn, 0, 0)
        add_button(0, 1, "Hasta kartina don", lambda: f"/hasta/{urllib.parse.quote(self._patient_key_from_route(getattr(self, 'current_professional_tool_route', '')) or '', safe='')}")
        add_button(1, 0, "PDF Atolyesi", lambda: f"/hasta/{urllib.parse.quote(self._patient_key_from_route(getattr(self, 'current_professional_tool_route', '')) or '', safe='')}/pdf-atolyesi")
        add_button(1, 1, "PDF Rapor Editoru", lambda: f"/hasta/{urllib.parse.quote(self._patient_key_from_route(getattr(self, 'current_professional_tool_route', '')) or '', safe='')}/pdf-editor")
        add_button(2, 0, "HD Studio", lambda: f"/hasta/{urllib.parse.quote(self._patient_key_from_route(getattr(self, 'current_professional_tool_route', '')) or '', safe='')}/yz-resim-iyilestir")
        add_button(2, 1, "DICOM / USG Zeka", lambda: f"/hasta/{urllib.parse.quote(self._patient_key_from_route(getattr(self, 'current_professional_tool_route', '')) or '', safe='')}/dicom")
        add_button(3, 0, "ReÃ§ete", lambda: f"/hasta/{urllib.parse.quote(self._patient_key_from_route(getattr(self, 'current_professional_tool_route', '')) or '', safe='')}/recete-hazirla")
        add_button(3, 1, "Sesli ReÃ§ete", lambda: f"/hasta/{urllib.parse.quote(self._patient_key_from_route(getattr(self, 'current_professional_tool_route', '')) or '', safe='')}/sesli-recete")
        layout.addLayout(grid)

        note = QLabel(
            "Bu ekran web sayfasini kacirmadan profesyonel araclari native kabuktan yonlendirir. "
            "Asil PDF/HD/Recete motoru serverda calisir; agir onizleme, yazdirma ve hasta baglami burada korunur.")
        note.setObjectName("webShellCommandSub")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        scroll.setWidget(page)
        return scroll

    def show_native_professional_tool_center(self, route: str) -> None:
        self.current_professional_tool_route = route or "/dashboard"
        try:
            path = urllib.parse.urlsplit(route_url(self.server_url, route)).path
        except Exception:
            path = str(route or "/")
        patient_key = self._patient_key_from_route(path)
        title = "Native PDF Studio" if "pdf" in path.lower() else "Native HD Studio"
        subtitle = (
            "Hasta baglamini koruyan hibrit/native profesyonel islem alani. "
            "Tam arac gerekirse web motorunda ac dugmesiyle ayni sayfaya gecilir.")
        self.native_tool_title.setText(title)
        self.native_tool_subtitle.setText(subtitle)
        self.native_tool_route.setText(f"Hasta: {patient_key or '-'}  |  Yol: {path}")
        self.center_stack.setCurrentWidget(self.native_tool_center)
        self.address.setText(route_url(self.server_url, route))
        self.shell_route_value.setText("Native Studio")
        self._sync_quick_buttons(QUrl(route_url(self.server_url, route)))
        self.statusBar().showMessage(f"Native profesyonel arac: {path}", 2500)

    def _open_professional_tool_in_web(self) -> None:
        route = getattr(self, "current_professional_tool_route", "/dashboard") or "/dashboard"
        url = route_url(self.server_url, route)
        self._update_web_module_chrome(route)
        self.center_stack.setCurrentWidget(self.web_frame)
        self.address.setText(url)
        self.view.load(QUrl(url))
        self.statusBar().showMessage(f"Web arac acildi: {route}", 2500)

    def _load_center_patient_detail(self, patient_key: str) -> None:
        if not patient_key:
            return
        encoded = urllib.parse.quote(patient_key, safe="")
        self.center_active_title.setText(self.active_patient_name or patient_key)
        self.center_active_sub.setText(patient_key)
        self.center_patient_summary.setText("Serverdan hasta ozeti aliniyor...")
        try:
            data = fetch_json(
                self.server_url, f"/api/terminal/patient/{encoded}", timeout=8)
            patient = data.get("patient") or {}
            display = patient_display_name(patient) if patient else self.active_patient_name
            visits = patient.get("visits") or []
            demographics = patient.get("demographics") or {}
            flags = patient.get("flags") or {}
            protocol = short_text(
                patient.get("protocol_no") or demographics.get("protocol_no") or patient.get("protocol"))
            phone = short_text(patient.get("phone") or demographics.get("phone"))
            last_visit = short_text(patient.get("last_visit") or (
                visits[0].get("visit_date") if visits and isinstance(visits[0], dict) else ""))
            risk_count = 0
            for value in flags.values():
                if isinstance(value, dict):
                    risk_count += 1 if str(value.get("value")) == "1" else 0
                else:
                    risk_count += 1 if str(value) == "1" else 0
            self.center_active_title.setText(display or patient_key)
            self.center_active_sub.setText(f"Protokol {protocol or '-'}")
            self.center_patient_summary.setText(
                f"Telefon: {phone}\nSon gelis: {last_visit}\n"
                f"Gelis sayisi: {len(visits)} | Risk isareti: {risk_count}")
            self._refresh_center_patient_actions(patient)
            if hasattr(self, "center_phone_value"):
                self.center_phone_value.setText(phone)
                self.center_last_visit_value.setText(last_visit)
                self.center_protocol_value.setText(protocol)
                self.center_risk_detail_value.setText(str(risk_count))
            if hasattr(self, "win_active_badge"):
                self.win_active_badge.setText(f"HASTA: {(display or patient_key)[:28]}")
        except Exception as ex:
            self.center_patient_summary.setText(f"Hasta ozeti alinamadi: {ex}")

    def _refresh_center_patient_actions(self, patient: Optional[dict]) -> None:
        for button, route in getattr(self, "center_patient_action_buttons", []):
            button.setVisible(patient_action_visible_for_patient(route, patient))

    def open_active_patient_route(self, route: str) -> None:
        if not self.active_patient_key:
            QMessageBox.information(
                self,
                "Hasta sec",
                "Bu islem hasta ister. Sag API Kokpit'ten bir hasta secin.")
            return
        encoded = urllib.parse.quote(self.active_patient_key, safe="")
        self.load_template_route(route.replace("{patient}", encoded))

    def refresh_api_bridge(self) -> None:
        try:
            stats_data = fetch_json(
                self.server_url, "/api/terminal/stats", timeout=5)
            self._update_center_stats(stats=stats_data.get("stats") or {})
        except Exception:
            pass
        try:
            active = fetch_json(
                self.server_url, "/api/terminal/active-patient", timeout=4)
            if active.get("ok") and not active.get("empty"):
                self._set_shell_active_patient(
                    active.get("patient_key") or active.get("key") or "",
                    active.get("display_name") or active.get("name") or "",
                    sync_server=False)
        except Exception:
            pass
        try:
            data = fetch_json(
                self.server_url, "/api/terminal/patients?limit=900", timeout=8)
            patients = data.get("patients") or []
            self.shell_patients_cache = patients
            self._populate_api_patients()
            self._populate_center_patients()
            self._set_api_state(
                f"API aktif | {len(patients)} hasta serverdan okundu", "ok")
            if hasattr(self, "win_api_badge"):
                self.win_api_badge.setText(f"LIVE API: {len(patients)} hasta")
        except Exception as ex:
            self._set_api_state(f"API hasta listesi alinamadi: {ex}", "bad")
            if hasattr(self, "win_api_badge"):
                self.win_api_badge.setText("LIVE API: hata")

    def run_api_nas_sync(self) -> None:
        self._set_api_state("NAS/Data senkronu serverda baslatildi", "busy")
        try:
            result = fetch_json(
                self.server_url,
                "/api/terminal/nas-sync",
                timeout=120,
                method="POST",
                body={"clear_existing": True},
            )
            if not result.get("ok"):
                raise RuntimeError(result.get("error") or "senkron basarisiz")
            msg = (
                f"NAS senkron tamam | hasta {result.get('patients', '-')}"
                f" | dosya {result.get('files', '-')}")
            self._set_api_state(msg, "ok")
            self.refresh_api_bridge()
        except Exception as ex:
            self._set_api_state(f"NAS senkron hatasi: {ex}", "bad")

    def load_template_route(self, route: str) -> None:
        route = str(route or "").strip()
        if "{patient}" in route:
            if not self.active_patient_key:
                QMessageBox.information(
                    self,
                    "Hasta sec",
                    "Bu modul hasta dosyasi ister. Once web ekranda bir hasta acin; "
                    "sonra bu buton otomatik o hastaya gider.")
                return
            route = route.replace(
                "{patient}",
                urllib.parse.quote(self.active_patient_key, safe=""))
        self.load_url(route)

    def _module_search_enter(self) -> None:
        needle = (self.module_search.text() or "").strip().casefold()
        for item, button in self.module_buttons:
            if not button.isHidden() and (not needle or needle in _haystack(item)):
                self.load_template_route(item.route)
                return

    def _filter_web_modules(self, text: str) -> None:
        needle = (text or "").strip().casefold()
        for group_label, buttons in self.module_sections:
            visible = False
            for button in buttons:
                item = next((i for i, b in self.module_buttons if b is button), None)
                show = not needle or (item is not None and needle in _haystack(item))
                button.setHidden(not show)
                visible = visible or show
            group_label.setHidden(not visible)

    def _build_chrome(self) -> QFrame:
        chrome = QFrame()
        chrome.setObjectName("webShellChrome")
        chrome.setAttribute(Qt.WA_StyledBackground, True)
        shell = QVBoxLayout(chrome)
        shell.setContentsMargins(14, 12, 14, 10)
        shell.setSpacing(10)

        top = QHBoxLayout()
        top.setSpacing(10)

        brand = QFrame()
        brand.setObjectName("webShellBrand")
        brand_l = QVBoxLayout(brand)
        brand_l.setContentsMargins(12, 8, 14, 8)
        brand_l.setSpacing(1)
        title = QLabel("YazKlinik Pro")
        title.setObjectName("webShellTitle")
        subtitle = QLabel("Windows API arayuz")
        subtitle.setObjectName("webShellSubtitle")
        brand_l.addWidget(title)
        brand_l.addWidget(subtitle)
        top.addWidget(brand, 0)

        self.back_btn = self._tool_button("Geri", "SP_ArrowBack")
        self.forward_btn = self._tool_button("Ileri", "SP_ArrowForward")
        self.reload_btn = self._tool_button("Yenile", "SP_BrowserReload")
        self.home_btn = self._tool_button("Ana sayfa", "SP_DirHomeIcon")
        for button in (self.back_btn, self.forward_btn,
                       self.reload_btn, self.home_btn):
            top.addWidget(button, 0)

        self.address = QLineEdit()
        self.address.setObjectName("webShellAddress")
        self.address.setClearButtonEnabled(True)
        self.address.setPlaceholderText("Server API yolu veya modul")
        self.address.returnPressed.connect(self._address_enter)
        top.addWidget(self.address, 1)

        self.status_label = QLabel("Server kontrol")
        self.status_label.setObjectName("webShellStatus")
        self.status_label.setProperty("state", "busy")
        self.status_label.setMinimumWidth(160)
        self.status_label.setAlignment(Qt.AlignCenter)
        top.addWidget(self.status_label, 0)

        for key, text in (("windows", "Windows"), ("light", "Acik"),
                          ("clinical", "Klinik"), ("dark", "Koyu")):
            btn = QPushButton(text)
            btn.setObjectName("webShellThemeButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, k=key: self._apply_theme(k))
            self.theme_buttons[key] = btn
            top.addWidget(btn, 0)
        shell.addLayout(top)

        quick = QHBoxLayout()
        quick.setSpacing(8)
        for label, route in self.QUICK_ROUTES:
            btn = QPushButton(label)
            btn.setObjectName("webShellQuickButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda checked=False, r=route: self.load_url(r))
            self.quick_buttons[route] = btn
            quick.addWidget(btn, 0)
        quick.addStretch(1)
        self.server_label = QLabel(self.server_url)
        self.server_label.setObjectName("webShellServerLabel")
        quick.addWidget(self.server_label, 0)
        shell.addLayout(quick)
        return chrome

    def _standard_icon(self, name: str) -> QIcon:
        standard_pixmap = getattr(getattr(QStyle, "StandardPixmap", QStyle),
                                  name, None)
        if standard_pixmap is None:
            standard_pixmap = getattr(QStyle, name, None)
        if standard_pixmap is None:
            return QIcon()
        return self.style().standardIcon(standard_pixmap)

    def _tool_button(self, tooltip: str, standard_icon: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName("webShellIconButton")
        button.setCursor(Qt.PointingHandCursor)
        button.setToolTip(tooltip)
        button.setIcon(self._standard_icon(standard_icon))
        button.setFixedSize(38, 38)
        return button

    def _theme_qss(self, theme: dict) -> str:
        rail = theme.get("rail", theme["surface_soft"])
        rail_button = theme.get("rail_button", theme["button"])
        command = theme.get("command", theme["surface"])
        metric = theme.get("metric", theme["surface_soft"])
        glass = theme.get("glass", theme["surface"])
        premium_bg = theme.get("premium_bg", theme["window"])
        premium_ink = theme.get("premium_ink", theme["text"])
        premium_gold = theme.get("premium_gold", "#C58A1F")
        premium_coral = theme.get("premium_coral", theme["accent_3"])
        premium_violet = theme.get("premium_violet", "#6D5BD0")
        premium_teal = theme.get("accent_2", "#00AFA5")
        return f"""
        QWidget#webShellRoot {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {premium_bg},
                stop:0.52 {theme['window']},
                stop:1 {theme['brand_bg']}
            );
        }}
        QWidget {{
            font-family: "Segoe UI", "Arial";
            font-size: 10.5pt;
            letter-spacing: 0px;
        }}
        QFrame#webShellChrome {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {theme['chrome']},
                stop:0.42 {glass},
                stop:0.74 {theme['surface_soft']},
                stop:1 {theme['brand_bg']}
            );
            border-bottom: 1px solid {theme['line']};
        }}
        QFrame#webShellBody {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {premium_bg},
                stop:0.38 {theme['window']},
                stop:0.72 {theme['surface_soft']},
                stop:1 {theme['brand_bg']}
            );
        }}
        QWidget#webShellWorkspace {{
            background: transparent;
        }}
        QStackedWidget#webShellCenterStack {{
            background: transparent;
            border: 0;
        }}
        QScrollArea#webShellNativeCenter {{
            background: transparent;
            border: 0;
        }}
        QWidget#webShellNativePage {{
            background: transparent;
        }}
        QFrame#webShellDesktopSurface {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {glass},
                stop:0.30 {theme['surface_soft']},
                stop:0.68 {premium_bg},
                stop:1 {theme['brand_bg']}
            );
            border: 1px solid {theme['line']};
            border-radius: 20px;
        }}
        QFrame#webShellWinRibbon {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {premium_ink},
                stop:0.42 #17324A,
                stop:0.76 {theme['accent']},
                stop:1 {premium_teal}
            );
            border: 1px solid {theme['accent']};
            border-radius: 16px;
        }}
        QLabel#webShellWinRibbonMark {{
            background: rgba(255, 255, 255, 0.18);
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.42);
            border-radius: 14px;
            font-size: 18px;
            font-weight: 950;
            qproperty-alignment: AlignCenter;
        }}
        QFrame#webShellWinRibbon QLabel#webShellNativeTitle {{
            color: #FFFFFF;
            font-size: 22px;
            font-weight: 950;
        }}
        QFrame#webShellWinRibbon QLabel#webShellNativeSub {{
            color: #E7F7FF;
            font-size: 11px;
            font-weight: 760;
        }}
        QLabel#webShellWinBadge {{
            background: rgba(255, 255, 255, 0.16);
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.36);
            border-radius: 11px;
            padding: 9px 12px;
            font-size: 10px;
            font-weight: 900;
        }}
        QLabel#webShellWinBadge[tone="patient"] {{
            background: rgba(197, 138, 31, 0.25);
            border-color: {premium_gold};
        }}
        QLabel#webShellWinBadge[tone="api"] {{
            background: rgba(0, 175, 165, 0.22);
            border-color: {premium_teal};
        }}
        QSplitter#webShellWinPanes::handle {{
            background: {theme['line']};
        }}
        QFrame#webShellWinWorkbench {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {theme['surface']},
                stop:0.72 {glass},
                stop:1 #F7FBFF
            );
            border: 1px solid {theme['line']};
            border-radius: 18px;
        }}
        QFrame#webShellWinOps {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {theme['surface']},
                stop:1 {theme['surface_soft']}
            );
            border: 1px solid {theme['line']};
            border-radius: 18px;
        }}
        QFrame#webShellWinDetailTile {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {theme['surface']},
                stop:1 {theme['surface_soft']}
            );
            border: 1px solid {theme['line']};
            border-radius: 12px;
        }}
        QLabel#webShellWinDetailValue {{
            color: {theme['text']};
            font-size: 12px;
            font-weight: 850;
        }}
        QFrame#webShellTaskbar {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {premium_ink},
                stop:0.52 #172536,
                stop:1 #183B3A
            );
            border: 1px solid {theme['line']};
            border-radius: 14px;
        }}
        QLabel#webShellTaskStart {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {theme['accent']},
                stop:1 {premium_teal}
            );
            color: #FFFFFF;
            border: 1px solid rgba(255, 255, 255, 0.24);
            border-radius: 9px;
            padding: 8px 14px;
            font-weight: 950;
        }}
        QLabel#webShellTaskText {{
            color: #D9EAF5;
            font-weight: 750;
        }}
        QFrame#webShellNativeHero {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {theme['surface']},
                stop:0.62 {theme['surface_soft']},
                stop:1 {theme['brand_bg']}
            );
            border: 1px solid {theme['line']};
            border-radius: 16px;
        }}
        QLabel#webShellNativeTitle {{
            color: {theme['text']};
            font-size: 20px;
            font-weight: 920;
        }}
        QLabel#webShellNativeSub, QLabel#webShellNativeText {{
            color: {theme['muted']};
            font-size: 11px;
            font-weight: 650;
        }}
        QLabel#webShellNativePatientTitle {{
            color: {theme['text']};
            font-size: 18px;
            font-weight: 900;
        }}
        QLabel#webShellNativePanelTitle {{
            color: {theme['text']};
            font-size: 14px;
            font-weight: 900;
        }}
        QFrame#webShellNativePanel {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {theme['surface']},
                stop:1 {glass}
            );
            border: 1px solid {theme['line']};
            border-radius: 18px;
        }}
        QFrame#webShellCenterMetric {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {theme['surface']},
                stop:1 {theme['surface_soft']}
            );
            border: 1px solid {theme['line']};
            border-radius: 16px;
        }}
        QFrame#webShellCenterMetric[tone="patient"] {{
            border-left: 5px solid {theme['accent']};
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #FFFFFF, stop:1 #EAF4FF);
        }}
        QFrame#webShellCenterMetric[tone="today"] {{
            border-left: 5px solid {premium_teal};
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #FFFFFF, stop:1 #E7F8F6);
        }}
        QFrame#webShellCenterMetric[tone="risk"] {{
            border-left: 5px solid {premium_coral};
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #FFFFFF, stop:1 #FFF0EA);
        }}
        QFrame#webShellCenterMetric[tone="ai"] {{
            border-left: 5px solid {premium_violet};
            background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #FFFFFF, stop:1 #F1EDFF);
        }}
        QLabel#webShellCenterMetricTitle {{
            color: {theme['muted']};
            font-size: 10px;
            font-weight: 850;
        }}
        QLabel#webShellCenterMetricValue {{
            color: {theme['text']};
            font-size: 22px;
            font-weight: 930;
        }}
        QPushButton#webShellCenterButton, QPushButton#webShellCenterPrimary {{
            border-radius: 12px;
            padding: 9px 12px;
            font-weight: 850;
            border: 1px solid {theme['line']};
        }}
        QPushButton#webShellCenterButton {{
            background: {theme['button']};
            color: {theme['text']};
        }}
        QPushButton#webShellCenterButton:hover {{
            background: {theme['button_hover']};
            border-color: {theme['accent']};
        }}
        QPushButton#webShellCenterPrimary {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {theme['accent']},
                stop:1 {premium_teal}
            );
            color: #FFFFFF;
            border-color: {theme['accent']};
        }}
        QPushButton#webShellCenterPrimary:hover {{
            background: {theme['accent_2']};
            border-color: {theme['accent_2']};
        }}
        QPushButton#webShellCenterButton[tone="teal"] {{
            background: #E7F8F6;
            border-color: {premium_teal};
        }}
        QPushButton#webShellCenterButton[tone="gold"] {{
            background: #FFF5DC;
            border-color: {premium_gold};
        }}
        QPushButton#webShellCenterButton[tone="coral"] {{
            background: #FFF0EA;
            border-color: {premium_coral};
        }}
        QPushButton#webShellCenterButton[tone="violet"] {{
            background: #F1EDFF;
            border-color: {premium_violet};
        }}
        QPushButton#webShellCenterButton[tone="green"] {{
            background: #E8F7F0;
            border-color: #24A36A;
        }}
        QLineEdit#webShellCenterSearch {{
            background: {theme['address']};
            color: {theme['text']};
            border: 1px solid {theme['line']};
            border-radius: 12px;
            padding: 10px 12px;
            selection-background-color: {theme['accent']};
            font-weight: 650;
        }}
        QListWidget#webShellCenterPatientList {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {theme['address']},
                stop:1 {theme['surface_soft']}
            );
            color: {theme['text']};
            border: 1px solid {theme['line']};
            border-radius: 14px;
            padding: 7px;
        }}
        QListWidget#webShellCenterPatientList::item {{
            border-radius: 10px;
            padding: 9px;
            margin: 3px;
        }}
        QListWidget#webShellCenterPatientList::item:hover {{
            background: {theme['button_hover']};
        }}
        QListWidget#webShellCenterPatientList::item:selected {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {theme['button_checked']},
                stop:1 #E8F8F6
            );
            color: {theme['text']};
        }}
        QFrame#webShellRail {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {glass},
                stop:0.58 {rail},
                stop:1 {theme['surface']}
            );
            border: 1px solid {theme['line']};
            border-radius: 18px;
        }}
        QFrame#webShellApiPanel {{
            background: qlineargradient(
                x1:0, y1:0, x2:0, y2:1,
                stop:0 {theme['surface']},
                stop:0.66 {glass},
                stop:1 {theme['surface_soft']}
            );
            border: 1px solid {theme['line']};
            border-radius: 18px;
            padding: 0px;
        }}
        QFrame#webShellApiHandle {{
            background: transparent;
            border: 0px;
            min-height: 30px;
            max-height: 30px;
        }}
        QLabel#webShellApiTitle {{
            color: {theme['text']};
            font-size: 15px;
            font-weight: 900;
        }}
        QLabel#webShellApiSub {{
            color: {theme['muted']};
            font-size: 10px;
            font-weight: 750;
        }}
        QLabel#webShellApiHint {{
            background: {theme['brand_bg']};
            color: {theme['muted']};
            border: 1px solid {theme['line']};
            border-radius: 9px;
            padding: 3px 8px;
            font-size: 10px;
            font-weight: 850;
        }}
        QToolButton#webShellApiToggle {{
            background: {theme['accent']};
            color: #FFFFFF;
            border: 1px solid {theme['accent']};
            border-radius: 9px;
            min-width: 28px;
            min-height: 26px;
            font-weight: 950;
        }}
        QToolButton#webShellApiToggle:hover {{
            background: {theme['accent_2']};
            border-color: {theme['accent_2']};
        }}
        QLabel#webShellApiState {{
            background: {theme['status_ok_bg']};
            color: {theme['status_ok_text']};
            border: 1px solid {theme['accent_2']};
            border-radius: 10px;
            padding: 9px 10px;
            font-weight: 780;
        }}
        QLabel#webShellApiState[state="busy"] {{
            background: {theme['status_busy_bg']};
            color: {theme['status_busy_text']};
            border-color: #E5B94C;
        }}
        QLabel#webShellApiState[state="bad"] {{
            background: {theme['status_bad_bg']};
            color: {theme['status_bad_text']};
            border-color: {theme['accent_3']};
        }}
        QLabel#webShellApiPatient {{
            background: {theme['brand_bg']};
            color: {theme['text']};
            border: 1px solid {theme['line']};
            border-radius: 12px;
            padding: 10px;
            font-weight: 850;
        }}
        QLineEdit#webShellApiSearch {{
            background: {theme['address']};
            color: {theme['text']};
            border: 1px solid {theme['line']};
            border-radius: 10px;
            padding: 8px 10px;
            selection-background-color: {theme['accent']};
            font-weight: 650;
        }}
        QListWidget#webShellApiPatientList {{
            background: {theme['address']};
            color: {theme['text']};
            border: 1px solid {theme['line']};
            border-radius: 12px;
            padding: 5px;
        }}
        QListWidget#webShellApiPatientList::item {{
            border-radius: 8px;
            padding: 7px;
            margin: 2px;
        }}
        QListWidget#webShellApiPatientList::item:selected {{
            background: {theme['button_checked']};
            color: {theme['text']};
        }}
        QPushButton#webShellApiButton, QPushButton#webShellApiPrimary {{
            border-radius: 9px;
            padding: 7px 9px;
            font-weight: 800;
            border: 1px solid {theme['line']};
        }}
        QPushButton#webShellApiButton {{
            background: {theme['button']};
            color: {theme['text']};
        }}
        QPushButton#webShellApiButton:hover {{
            background: {theme['button_hover']};
            border-color: {theme['accent']};
        }}
        QPushButton#webShellApiPrimary {{
            background: {theme['accent']};
            color: #FFFFFF;
            border-color: {theme['accent']};
        }}
        QPushButton#webShellApiPrimary:hover {{
            background: {theme['accent_2']};
            border-color: {theme['accent_2']};
        }}
        QLabel#webShellLogo {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {theme['accent']},
                stop:1 {premium_teal}
            );
            color: #FFFFFF;
            border: 1px solid {theme['accent']};
            border-radius: 12px;
            font-size: 16px;
            font-weight: 950;
        }}
        QLabel#webShellRailTitle {{
            color: {theme['text']};
            font-size: 15px;
            font-weight: 900;
        }}
        QLabel#webShellRailSub {{
            color: {theme['muted']};
            font-size: 10px;
            font-weight: 650;
        }}
        QFrame#webShellDivider {{
            color: {theme['line']};
            background: {theme['line']};
            max-height: 1px;
        }}
        QLabel#webShellRailSection, QLabel#webShellModuleGroup {{
            color: {theme['muted']};
            font-size: 10px;
            font-weight: 900;
            padding: 7px 2px 2px 2px;
        }}
        QPushButton#webShellRailButton {{
            text-align: left;
            background: {rail_button};
            color: {theme['text']};
            border: 1px solid {theme['line']};
            border-radius: 12px;
            padding: 10px 11px;
            font-weight: 830;
        }}
        QPushButton#webShellRailButton:hover {{
            background: {theme['button_hover']};
            border-color: {theme['accent']};
        }}
        QPushButton#webShellRailButton:checked {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {theme['button_checked']},
                stop:1 #E8F8F6
            );
            border-color: {theme['accent']};
            color: {theme['text']};
        }}
        QFrame#webShellModulePanel {{
            background: transparent;
            border: 0;
        }}
        QWidget#webShellModuleContainer {{
            background: transparent;
        }}
        QLineEdit#webShellModuleSearch {{
            background: {theme['address']};
            color: {theme['text']};
            border: 1px solid {theme['line']};
            border-radius: 10px;
            padding: 8px 10px;
            selection-background-color: {theme['accent']};
            font-weight: 650;
        }}
        QLineEdit#webShellModuleSearch:focus {{
            border-color: {theme['accent']};
        }}
        QPushButton#webShellModuleButton {{
            text-align: left;
            background: {theme['button']};
            color: {theme['text']};
            border: 1px solid {theme['line']};
            border-radius: 9px;
            padding: 7px 9px;
            font-weight: 740;
        }}
        QPushButton#webShellModuleButton:hover {{
            background: {theme['button_hover']};
            border-color: {theme['accent']};
        }}
        QPushButton#webShellModuleButton[patientReady="false"] {{
            color: {theme['muted']};
            border-style: dashed;
        }}
        QFrame#webShellCommandStrip {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {command},
                stop:0.58 {theme['surface']},
                stop:0.84 {glass},
                stop:1 {theme['brand_bg']}
            );
            border: 1px solid {theme['line']};
            border-radius: 18px;
        }}
        QLabel#webShellCommandTitle {{
            color: {theme['text']};
            font-size: 18px;
            font-weight: 900;
        }}
        QLabel#webShellCommandSub {{
            color: {theme['muted']};
            font-size: 11px;
            font-weight: 650;
        }}
        QPushButton#webShellCommandButton, QPushButton#webShellCommandPrimary {{
            border-radius: 12px;
            padding: 9px 13px;
            font-weight: 850;
            border: 1px solid {theme['line']};
        }}
        QPushButton#webShellCommandButton {{
            background: {theme['button']};
            color: {theme['text']};
        }}
        QPushButton#webShellCommandButton:hover {{
            background: {theme['button_hover']};
            border-color: {theme['accent']};
        }}
        QPushButton#webShellCommandPrimary {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {theme['accent']},
                stop:1 {premium_teal}
            );
            color: #FFFFFF;
            border-color: {theme['accent']};
        }}
        QPushButton#webShellCommandPrimary:hover {{
            background: {theme['accent_2']};
            border-color: {theme['accent_2']};
        }}
        QFrame#webShellMetric {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {metric},
                stop:1 {theme['surface']}
            );
            border: 1px solid {theme['line']};
            border-radius: 12px;
        }}
        QLabel#webShellMetricTitle {{
            color: {theme['muted']};
            font-size: 9px;
            font-weight: 850;
        }}
        QLabel#webShellMetricValue {{
            color: {theme['text']};
            font-size: 12px;
            font-weight: 900;
        }}
        QFrame#webShellBrand {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {theme['brand_bg']},
                stop:1 {glass}
            );
            border: 1px solid {theme['line']};
            border-radius: 12px;
        }}
        QLabel#webShellTitle {{
            color: {theme['text']};
            font-size: 16px;
            font-weight: 850;
        }}
        QLabel#webShellSubtitle, QLabel#webShellServerLabel {{
            color: {theme['muted']};
            font-size: 10px;
            font-weight: 650;
        }}
        QToolButton#webShellIconButton {{
            background: {theme['button']};
            border: 1px solid {theme['line']};
            border-radius: 9px;
            padding: 7px;
        }}
        QToolButton#webShellIconButton:hover {{
            background: {theme['button_hover']};
            border-color: {theme['accent']};
        }}
        QToolButton#webShellIconButton:pressed {{
            background: {theme['button_checked']};
        }}
        QLineEdit#webShellAddress {{
            background: {theme['address']};
            color: {theme['text']};
            border: 1px solid {theme['line']};
            border-radius: 10px;
            padding: 8px 12px;
            selection-background-color: {theme['accent']};
            font-weight: 650;
        }}
        QLineEdit#webShellAddress:focus {{
            border-color: {theme['accent']};
        }}
        QLabel#webShellStatus {{
            border-radius: 10px;
            padding: 8px 12px;
            font-weight: 850;
        }}
        QLabel#webShellStatus[state="ok"] {{
            background: {theme['status_ok_bg']};
            color: {theme['status_ok_text']};
            border: 1px solid {theme['accent_2']};
        }}
        QLabel#webShellStatus[state="busy"] {{
            background: {theme['status_busy_bg']};
            color: {theme['status_busy_text']};
            border: 1px solid #E5B94C;
        }}
        QLabel#webShellStatus[state="bad"] {{
            background: {theme['status_bad_bg']};
            color: {theme['status_bad_text']};
            border: 1px solid {theme['accent_3']};
        }}
        QPushButton#webShellThemeButton, QPushButton#webShellQuickButton {{
            background: {theme['button']};
            color: {theme['text']};
            border: 1px solid {theme['line']};
            border-radius: 9px;
            padding: 8px 12px;
            font-weight: 760;
        }}
        QPushButton#webShellThemeButton:hover,
        QPushButton#webShellQuickButton:hover {{
            background: {theme['button_hover']};
            border-color: {theme['accent']};
        }}
        QPushButton#webShellThemeButton:checked,
        QPushButton#webShellQuickButton:checked {{
            background: {theme['button_checked']};
            border-color: {theme['accent']};
            color: {theme['text']};
        }}
        QFrame#webShellViewport {{
            background: {theme['surface']};
            border: 1px solid {theme['line']};
            border-radius: 20px;
        }}
        QFrame#webShellWebTitlebar {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {theme['surface']},
                stop:0.55 {glass},
                stop:1 {theme['brand_bg']}
            );
            border-bottom: 1px solid {theme['line']};
            border-top-left-radius: 20px;
            border-top-right-radius: 20px;
        }}
        QLabel#webShellWebIcon {{
            min-width: 34px;
            max-width: 34px;
            min-height: 34px;
            max-height: 34px;
            border-radius: 10px;
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {theme['accent']},
                stop:1 {premium_teal}
            );
            color: #FFFFFF;
            font-weight: 900;
            qproperty-alignment: AlignCenter;
        }}
        QLabel#webShellWebTitle {{
            color: {theme['text']};
            font-size: 13px;
            font-weight: 900;
        }}
        QLabel#webShellWebSub {{
            color: {theme['muted']};
            font-size: 10px;
            font-weight: 700;
        }}
        QLabel#webShellWebRoute {{
            background: {theme['button_checked']};
            color: {theme['text']};
            border: 1px solid {theme['line']};
            border-radius: 9px;
            padding: 7px 10px;
            font-size: 10px;
            font-weight: 850;
        }}
        QProgressBar#webShellProgress {{
            background: {theme['surface_soft']};
            border: 0px;
            min-height: 3px;
            max-height: 3px;
        }}
        QProgressBar#webShellProgress::chunk {{
            background: {theme['accent']};
            border-radius: 1px;
        }}
        /* v1000.1.7 executive polish */
        QWidget#webShellRoot {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {premium_bg},
                stop:0.42 {theme['window']},
                stop:0.72 {theme['surface_soft']},
                stop:1 {theme['brand_bg']}
            );
        }}
        QFrame#webShellChrome {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {theme['surface']},
                stop:0.46 {glass},
                stop:0.78 {theme['surface_soft']},
                stop:1 {theme['brand_bg']}
            );
            border-bottom: 1px solid {theme['line']};
        }}
        QFrame#webShellDesktopSurface {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {theme['surface']},
                stop:0.42 {theme['surface_soft']},
                stop:0.73 {glass},
                stop:1 {theme['brand_bg']}
            );
            border: 1px solid {theme['line']};
            border-radius: 22px;
        }}
        QFrame#webShellWinRibbon {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {premium_ink},
                stop:0.34 {theme['accent']},
                stop:0.72 {premium_teal},
                stop:1 {premium_gold}
            );
            border: 1px solid rgba(255, 255, 255, 0.24);
            border-radius: 18px;
        }}
        QLabel#webShellWinRibbonMark {{
            background: rgba(255, 255, 255, 0.20);
            border: 1px solid rgba(255, 255, 255, 0.48);
            border-radius: 15px;
            font-size: 19px;
            font-weight: 950;
        }}
        QLabel#webShellWinBadge {{
            background: rgba(255, 255, 255, 0.18);
            border: 1px solid rgba(255, 255, 255, 0.40);
            border-radius: 12px;
            padding: 9px 13px;
            font-weight: 920;
        }}
        QFrame#webShellWinWorkbench,
        QFrame#webShellWinOps,
        QFrame#webShellNativePanel,
        QFrame#webShellCommandStrip,
        QFrame#webShellApiPanel,
        QFrame#webShellRail {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {theme['surface']},
                stop:0.62 {glass},
                stop:1 {theme['surface_soft']}
            );
            border: 1px solid {theme['line']};
            border-radius: 20px;
        }}
        QFrame#webShellNativeHero,
        QFrame#webShellBrand,
        QFrame#webShellWebTitlebar {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {theme['surface']},
                stop:0.52 {glass},
                stop:1 {theme['brand_bg']}
            );
            border: 1px solid {theme['line']};
            border-radius: 16px;
        }}
        QFrame#webShellCenterMetric,
        QFrame#webShellMetric,
        QFrame#webShellWinDetailTile {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {theme['surface']},
                stop:1 {theme['surface_soft']}
            );
            border: 1px solid {theme['line']};
            border-radius: 17px;
        }}
        QLabel#webShellNativeTitle,
        QFrame#webShellWinRibbon QLabel#webShellNativeTitle,
        QLabel#webShellCommandTitle,
        QLabel#webShellApiTitle,
        QLabel#webShellTitle {{
            letter-spacing: 0px;
            font-weight: 950;
        }}
        QLabel#webShellCenterMetricValue {{
            font-size: 23px;
            font-weight: 950;
            color: {premium_ink};
        }}
        QPushButton#webShellCenterPrimary,
        QPushButton#webShellCommandPrimary,
        QPushButton#webShellApiPrimary {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:0,
                stop:0 {theme['accent']},
                stop:0.62 {premium_teal},
                stop:1 {premium_gold}
            );
            color: #FFFFFF;
            border: 1px solid {theme['accent']};
            border-radius: 13px;
            padding: 10px 14px;
            font-weight: 900;
        }}
        QPushButton#webShellCenterButton,
        QPushButton#webShellCommandButton,
        QPushButton#webShellApiButton,
        QPushButton#webShellRailButton,
        QPushButton#webShellModuleButton,
        QPushButton#webShellThemeButton,
        QPushButton#webShellQuickButton,
        QToolButton#webShellIconButton {{
            background: qlineargradient(
                x1:0, y1:0, x2:1, y2:1,
                stop:0 {theme['button']},
                stop:1 {theme['surface_soft']}
            );
            color: {theme['text']};
            border: 1px solid {theme['line']};
            border-radius: 12px;
            font-weight: 840;
        }}
        QPushButton#webShellCenterButton:hover,
        QPushButton#webShellCommandButton:hover,
        QPushButton#webShellApiButton:hover,
        QPushButton#webShellRailButton:hover,
        QPushButton#webShellModuleButton:hover,
        QPushButton#webShellThemeButton:hover,
        QPushButton#webShellQuickButton:hover,
        QToolButton#webShellIconButton:hover {{
            background: {theme['button_hover']};
            border-color: {theme['accent']};
        }}
        QLineEdit#webShellAddress,
        QLineEdit#webShellCenterSearch,
        QLineEdit#webShellApiSearch,
        QLineEdit#webShellModuleSearch,
        QListWidget#webShellCenterPatientList,
        QListWidget#webShellApiPatientList {{
            background: {theme['address']};
            color: {theme['text']};
            border: 1px solid {theme['line']};
            border-radius: 13px;
            selection-background-color: {theme['accent']};
            font-weight: 700;
        }}
        QStatusBar {{
            background: {theme['surface_soft']};
            color: {theme['muted']};
            border-top: 1px solid {theme['line']};
            padding: 3px 10px;
            font-size: 10px;
        }}
        """

    def _apply_theme(self, name: str, persist: bool = True) -> None:
        if name not in WEB_SHELL_THEMES:
            name = "light"
        self.current_theme = name
        if persist:
            self.settings.setValue("theme", name)
        self.setStyleSheet(self._theme_qss(WEB_SHELL_THEMES[name]))
        for key, button in self.theme_buttons.items():
            button.setChecked(key == name)

    def _set_status(self, text: str, state: str) -> None:
        self.status_label.setText(text)
        self.status_label.setProperty("state", state)
        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)
        self.status_label.update()

    def _entry_url(self) -> str:
        route = os.environ.get("YAZKLINIK_DESKTOP_INITIAL_ROUTE", "/giris")
        return route_url(self.server_url, route)

    def go_home(self) -> None:
        self.load_url("/dashboard")

    def load_url(self, url: str) -> None:
        url = (url or "").strip()
        if not url:
            url = self._entry_url()
        route_for_native = url
        if url.startswith("/"):
            url = route_url(self.server_url, url)
        elif not url.startswith(("http://", "https://")):
            route_for_native = "/" + url
            url = route_url(self.server_url, route_for_native)
        else:
            try:
                parsed = urllib.parse.urlsplit(url)
                base = urllib.parse.urlsplit(self.server_url)
                if parsed.netloc == base.netloc:
                    route_for_native = parsed.path or "/"
                    if parsed.query:
                        route_for_native += "?" + parsed.query
            except Exception:
                route_for_native = url

        self.last_requested_route = route_for_native or "/dashboard"
        patient_key = self._patient_key_from_route(route_for_native)
        if self._is_native_professional_tool_route(route_for_native) and not WEB_CENTER_FIRST:
            if patient_key:
                self._set_shell_active_patient(patient_key, patient_key, sync_server=True)
            self.show_native_professional_tool_center(route_for_native)
            return
        if WEB_CENTER_FIRST:
            if patient_key:
                self._set_shell_active_patient(patient_key, patient_key, sync_server=True)
            self._update_web_module_chrome(route_for_native)
            self.center_stack.setCurrentWidget(self.web_frame)
            self.address.setText(url)
            self.view.load(QUrl(url))
            return

        if patient_key:
            self._set_shell_active_patient(patient_key, patient_key, sync_server=True)
            self.center_stack.setCurrentWidget(self.native_center)
            self.address.setText(url)
            self.shell_route_value.setText("/hasta")
            self._load_center_patient_detail(patient_key)
            return

        if self._is_native_shell_route(route_for_native):
            self.show_native_center(route_for_native)
            return

        self._update_web_module_chrome(route_for_native)
        self.center_stack.setCurrentWidget(self.web_frame)
        self.address.setText(url)
        self.view.load(QUrl(url))

    def _address_enter(self) -> None:
        self.load_url(self.address.text())

    def _url_changed(self, url: QUrl) -> None:
        self.address.setText(url.toString())
        self._sync_quick_buttons(url)
        self._sync_active_patient_from_url(url)
        self._update_web_module_chrome(url.toString())
        if _desktop_restart_requested_url(url):
            QTimer.singleShot(
                700, lambda: _apply_runtime_mode_change_for_window(
                    self, self.server_url))
        try:
            self.shell_route_value.setText((url.path() or "/")[:18])
        except Exception:
            pass
        try:
            history = self.view.history()
            self.back_btn.setEnabled(history.canGoBack())
            self.forward_btn.setEnabled(history.canGoForward())
        except Exception:
            pass

    def _sync_active_patient_from_url(self, url: QUrl) -> None:
        path = url.path() or ""
        parts = [p for p in path.strip("/").split("/") if p]
        patient_key = ""
        if len(parts) >= 2 and parts[0].lower() == "hasta":
            patient_key = urllib.parse.unquote(parts[1])
        if patient_key != self.active_patient_key:
            self._set_shell_active_patient(
                patient_key, patient_key, sync_server=bool(patient_key))

    def _load_started(self) -> None:
        self._set_status("Yukleniyor", "busy")
        self.progress.setValue(8)
        self.progress.setVisible(True)
        self.statusBar().showMessage("Server web arayuzu yukleniyor...")

    def _load_progress(self, value: int) -> None:
        self.progress.setVisible(True)
        self.progress.setValue(max(0, min(100, int(value or 0))))

    def _load_finished(self, ok: bool) -> None:
        self.progress.setValue(100)
        QTimer.singleShot(450, lambda: self.progress.setVisible(False))
        self._set_status("HazÄ±r" if ok else "Sayfa hatasÄ±",
                         "ok" if ok else "bad")
        if ok:
            self._apply_web_shell_mask()
        self.statusBar().showMessage(
            "Windows Fluent kabuk hazÄ±r" if ok else "Sayfa yÃ¼klenemedi",
            2500 if ok else 6000,
        )
        QTimer.singleShot(250, self.refresh_server_status)

    def _apply_web_shell_mask(self) -> None:
        if not getattr(self, "view", None):
            return
        script = r"""
        (function(){
          document.documentElement.setAttribute('data-yazklinik-webshell', '1');
          if (document.body) document.body.classList.add('yk-webshell-embedded');
          if (!window.ykNativeOpenUrl) {
            window.ykNativeOpenUrl = function(url) {
              if (!url) return false;
              try {
                window.location.href = String(url);
                return true;
              } catch (e) {
                return false;
              }
            };
          }
          window.ykNativeOpenOrNavigate = window.ykNativeOpenOrNavigate || window.ykNativeOpenUrl;
          try { window.dispatchEvent(new Event('yazklinik-native-ready')); } catch (e) {}
          document.documentElement.classList.add('yk-desktop-shell-mask');
          if (document.getElementById('ykDesktopShellMaskStyle')) return;
          var style = document.createElement('style');
          style.id = 'ykDesktopShellMaskStyle';
          style.textContent = `
            html.yk-desktop-shell-mask body {
              background:#F4F7FA !important;
            }
            html.yk-desktop-shell-mask .sidebar,
            html.yk-desktop-shell-mask .sidebar-overlay,
            html.yk-desktop-shell-mask .top-header,
            html.yk-desktop-shell-mask .mobile-bottom-nav {
              display:none !important;
            }
            html.yk-desktop-shell-mask .main-content {
              margin-left:0 !important;
              padding-top:0 !important;
              min-height:auto !important;
            }
            html.yk-desktop-shell-mask .main-container {
              max-width:none !important;
              width:100% !important;
              padding:14px 16px 24px !important;
            }
            html.yk-desktop-shell-mask .active-patient-banner {
              position:relative !important;
              top:auto !important;
              margin:0 0 12px !important;
              border-radius:10px !important;
            }
            html.yk-desktop-shell-mask .page-header {
              margin-top:0 !important;
            }
          `;
          document.head.appendChild(style);
        })();
        """
        try:
            self.view.page().runJavaScript(script)
        except Exception:
            pass

    def _sync_quick_buttons(self, url: QUrl) -> None:
        path = url.path() or "/"
        for route, button in self.quick_buttons.items():
            button.setChecked(path == route)
        for route, button in self.rail_buttons.items():
            if route == "/":
                button.setChecked(path == "/")
            else:
                button.setChecked(path == route or path.startswith(route + "/"))

    def refresh_server_status(self) -> None:
        if self.connection_mode == "local":
            if self._switch_to_primary_runtime():
                self._reload_current_route_after_runtime_change()
                return
            try:
                data = fetch_json(self.server_url, "/api/terminal/ping", timeout=3)
                ollama = "AI hazÄ±r" if data.get("ollama_online") else "AI beklemede"
                self._set_status(f"Yerel API | {ollama}", "busy")
                try:
                    self.shell_server_value.setText("Yerel")
                    self.shell_ai_value.setText(
                        "HazÄ±r" if data.get("ollama_online") else "Beklemede")
                    if hasattr(self, "win_api_badge"):
                        self.win_api_badge.setText("LOCAL API: aktif")
                    self._update_center_stats(status=data)
                except Exception:
                    pass
                self.statusBar().showMessage(
                    f"Ana server bekleniyor; terminal yerel API ile devam ediyor | {self.server_url}",
                    4500,
                )
                return
            except Exception as ex:
                self._set_status("Yerel API sorunu", "bad")
                self.statusBar().showMessage(
                    f"Yerel terminal API de yanit vermedi: {ex}", 8000)
                return

        try:
            data = fetch_json(self.server_url, "/api/terminal/ping", timeout=4)
            if not data.get("ok", True):
                raise RuntimeError(data.get("error") or "server yaniti hatali")
            ollama = "AI hazÄ±r" if data.get("ollama_online") else "AI beklemede"
            self._set_status(f"Server OK | {ollama}", "ok")
            try:
                self.shell_server_value.setText("OK")
                self.shell_ai_value.setText("HazÄ±r" if data.get("ollama_online") else "Beklemede")
                if hasattr(self, "win_api_badge"):
                    self.win_api_badge.setText("LIVE API: online")
                self._update_center_stats(status=data)
            except Exception:
                pass
            version = data.get("version") or data.get("app_version") or APP_VERSION
            self.statusBar().showMessage(f"{version} | {self.server_url}", 4500)
        except Exception as ex:
            self._set_status("Baglanti yok", "bad")
            try:
                self.shell_server_value.setText("Yok")
                self.shell_ai_value.setText("-")
                if hasattr(self, "win_api_badge"):
                    self.win_api_badge.setText("LIVE API: offline")
                if hasattr(self, "win_task_server"):
                    self.win_task_server.setText("Server API baglantisi yok")
            except Exception:
                pass
            if self._switch_to_local_runtime(str(ex)):
                self._reload_current_route_after_runtime_change()
            else:
                self.statusBar().showMessage(
                    f"Server kontrol edilemedi: {ex}", 8000)


def main(argv: Optional[Iterable[str]] = None) -> int:
    try:
        from yazklinik_runtime_cleanup import run_startup_cleanup
        run_startup_cleanup(version=APP_VERSION, stop_stale_servers=False)
    except Exception:
        pass
    selected_mode = _apply_desktop_runtime_mode_env(
        _read_desktop_runtime_mode_pre_qt())
    _configure_qt_runtime()
    for attr_name in ("AA_ShareOpenGLContexts", "AA_UseSoftwareOpenGL"):
        attr = getattr(Qt, attr_name, None)
        if attr is not None:
            QApplication.setAttribute(attr, True)
    app = QApplication(list(argv or sys.argv))
    app.setApplicationName(APP_VERSION)
    app.setOrganizationName("YazKlinik")
    use_web_mirror = selected_mode == "mirror"
    use_web_shell = selected_mode == "shell"
    if use_web_mirror and WEB_ENGINE_AVAILABLE:
        window = YazKlinikWebMirror()
    elif use_web_shell and WEB_ENGINE_AVAILABLE:
        window = YazKlinikWebShell()
    else:
        window = YazKlinikDesktop()
    if isinstance(window, (YazKlinikWebMirror, YazKlinikWebShell)):
        window.showMaximized()
    else:
        window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())








