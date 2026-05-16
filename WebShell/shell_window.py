"""WebShell - Native sidebar + header + QtWebEngineView merkez (v3.0)."""
from __future__ import annotations
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional


def _merge_qtwebengine_chromium_flags(*extra_flags: str) -> None:
    """QtWebEngine flags must be present before the web engine spins up."""
    current = os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "").strip()
    parts = current.split() if current else []
    secure_prefix = "--unsafely-treat-insecure-origin-as-secure="
    for flag in extra_flags:
        flag = str(flag or "").strip()
        if flag.startswith(secure_prefix):
            origins = []
            for item in list(parts):
                if item.startswith(secure_prefix):
                    origins.extend([x for x in item[len(secure_prefix):].split(",") if x])
                    parts.remove(item)
            origins.extend([x for x in flag[len(secure_prefix):].split(",") if x])
            deduped = []
            seen = set()
            for origin in origins:
                key = origin.lower()
                if key not in seen:
                    seen.add(key)
                    deduped.append(origin)
            flag = secure_prefix + ",".join(deduped)
        if flag and flag not in parts:
            parts.append(flag)
    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(parts)


_merge_qtwebengine_chromium_flags(
    "--autoplay-policy=no-user-gesture-required",
    "--enable-media-stream",
    "--use-fake-ui-for-media-stream",
    "--unsafely-treat-insecure-origin-as-secure=http://127.0.0.1:5052,http://localhost:5052,http://192.168.1.40:5052,http://192.168.1.148:5052,http://127.0.0.1:5053,http://localhost:5053,http://192.168.1.40:5053,http://192.168.1.148:5053",
)

from PySide6.QtCore import Qt, QUrl, QTimer, QSettings, QSize, QObject, Slot
from PySide6.QtGui import (
    QKeySequence, QShortcut, QIcon, QColor, QDesktopServices, QPageSize, QPageLayout,
    QPainter, QImage, QFont, QPen, QBrush, QLinearGradient, QPainterPath,
)
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QPushButton, QLabel,
    QFrame, QButtonGroup, QStatusBar, QLineEdit, QScrollArea, QListWidget,
    QListWidgetItem, QDialog, QMessageBox, QStackedWidget, QFileDialog,
)
try:
    from PySide6.QtPrintSupport import QPrinter, QPrintDialog
except Exception:
    QPrinter = None
    QPrintDialog = None
try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtWebEngineCore import QWebEngineProfile, QWebEngineSettings
    try:
        from PySide6.QtWebChannel import QWebChannel
    except Exception:
        QWebChannel = None
    try:
        from PySide6.QtWebEngineCore import QWebEnginePage
    except Exception:
        QWebEnginePage = None
    HAS_WEB = True
except Exception:
    QWebEngineView = None
    QWebEnginePage = None
    QWebChannel = None
    HAS_WEB = False

from theme import COLORS, apply
from web_routes import all_routes, nav_groups_for_mode
import api_client

try:
    from yazklinik_textfix import fix_mojibake_text as _fix_mojibake_text
except Exception:
    def _fix_mojibake_text(value):
        return str(value or "")


MENU_MODE_LABELS = {
    "simple": "Basit",
    "doctor": "Doktor",
    "advanced": "Uzman",
}

MENU_MODE_TOOLTIPS = {
    "simple": "Sade menü: temel işlemler.",
    "doctor": "Doktor menüsü: günlük klinik akış.",
    "advanced": "Uzman menüsü: tüm araçlar ve ayarlar.",
}


def _mode_button_style(active: bool, mode: str) -> str:
    active_colors = {
        "simple": ("#2563EB", "#0EA5E9", "#1D4ED8"),
        "doctor": ("#0F766E", "#14B8A6", "#0B5F59"),
        "advanced": ("#7C3AED", "#0EA5E9", "#5B21B6"),
    }
    if active:
        c0, c1, border = active_colors.get(mode, active_colors["advanced"])
        return (
            "QPushButton{font:900 12px 'Segoe UI';padding:5px 7px;"
            f"border:2px solid {border};border-radius:12px;"
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {c0},stop:1 {c1});"
            "color:#FFFFFF;min-height:34px;}"
            "QPushButton:hover{border-color:#0F172A;}"
        )
    return (
        "QPushButton{font:800 12px 'Segoe UI';padding:5px 7px;"
        "border:1px solid #BBD6E7;border-radius:12px;"
        "background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #FFFFFF,stop:1 #F2FBFF);"
        "color:#17324D;min-height:34px;}"
        "QPushButton:hover{border-color:#0EA5E9;background:#F5FCFF;color:#0F2A3D;}"
    )


def _normalize_menu_mode(mode: str) -> str:
    mode = str(mode or "").strip().lower()
    if mode in {"simple", "basit"}:
        return "simple"
    if mode in {"doctor", "doktor"}:
        return "doctor"
    if mode in {"advanced", "expert", "uzman"}:
        return "advanced"
    return "advanced"


def _webshell_helper_log(message: str) -> None:
    try:
        base = Path(tempfile.gettempdir()) / "YazKlinikWebShell"
        base.mkdir(parents=True, exist_ok=True)
        line = time.strftime("%Y-%m-%d %H:%M:%S ") + str(message)
        with (base / "native_helper.log").open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception:
        pass


def _helper_python_candidates(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for raw in (
        Path(str(sys.executable or "")),
        root / ".venv" / "Scripts" / "python.exe",
        root / "venv" / "Scripts" / "python.exe",
    ):
        if not str(raw):
            continue
        try:
            resolved = raw.resolve()
        except Exception:
            resolved = raw
        if resolved.exists() and resolved.is_file():
            if resolved not in candidates:
                candidates.append(resolved)
    return candidates


def _launch_local_helper(script_name: str, url: QUrl, helper_tag: str) -> bool:
    try:
        root = Path(__file__).resolve().parent.parent
        script = root / script_name
        if not script.exists():
            _webshell_helper_log(f"{helper_tag}: script not found: {script}")
            return False
        creationflags = 0x08000000 if os.name == "nt" else 0
        for python_exe in _helper_python_candidates(root):
            try:
                subprocess.Popen(
                    [str(python_exe), str(script), url.toString()],
                    cwd=str(root),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=creationflags,
                )
                _webshell_helper_log(
                    f"{helper_tag}: launched with {python_exe} url={url.toString()[:220]}"
                )
                return True
            except Exception as ex:
                _webshell_helper_log(
                    f"{helper_tag}: launch failed with {python_exe}: {ex}"
                )
        _webshell_helper_log(f"{helper_tag}: no usable python executable found.")
        return False
    except Exception as ex:
        _webshell_helper_log(f"{helper_tag}: unexpected launch error: {ex}")
        return False


def _launch_whatsapp_local_helper(url: QUrl) -> bool:
    """Run the local file clipboard helper from WebShell."""
    return _launch_local_helper(
        "yazklinik_whatsapp_local_helper.py", url, "whatsapp-local-helper")


def _launch_photo_print_helper(url: QUrl) -> bool:
    """Open a real image file in the local Windows photo print flow."""
    return _launch_local_helper(
        "yazklinik_photo_print_helper.py", url, "photo-print-helper")


def _launch_open_folder_helper(url: QUrl) -> bool:
    """Open a NAS/visit folder on the local WebShell PC."""
    return _launch_local_helper(
        "yazklinik_open_folder_helper.py", url, "open-folder-helper")


def _audio_name_key(value) -> str:
    text = str(value or "")
    try:
        text = unicodedata.normalize("NFKD", text)
        text = text.encode("ascii", "ignore").decode("ascii")
    except Exception:
        pass
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _audio_default_input_index(sd) -> int | None:
    try:
        default_device = sd.default.device
        if hasattr(default_device, "input"):
            default_device = default_device.input
        elif isinstance(default_device, (tuple, list)) and default_device:
            default_device = default_device[0]
        idx = int(default_device)
        return idx if idx >= 0 else None
    except Exception:
        return None


def _audio_input_score(index: int, item: dict, default_index: int | None = None) -> int:
    name = _audio_name_key(item.get("name") or "")
    try:
        channels = int(item.get("max_input_channels") or 0)
    except Exception:
        channels = 0
    if channels <= 0:
        return -10000
    score = 0
    if default_index is not None and int(index) == int(default_index):
        score += 120
    if any(token in name for token in (
            "mikrofon", "microphone", "mic input", "mic in", "realtek hd audio mic")):
        score += 90
    elif re.search(r"(^| )mic( |$)", name):
        score += 70
    if any(token in name for token in ("array", "giris", "input")):
        score += 12
    if "realtek" in name:
        score += 5
    if any(token in name for token in (
            "stereo mix", "stereo kar", "hoparlor", "speaker", "output",
            "loopback", "monitor", "what u hear")):
        score -= 180
    return score


def _audio_check_input(sd, index: int, rate: int) -> bool:
    try:
        sd.check_input_settings(
            device=int(index), channels=1,
            samplerate=int(rate or 16000), dtype="int16")
        return True
    except Exception:
        return False


def _focus_local_voice_samples(samples) -> tuple[object, dict]:
    """Keep the selected mic voice-forward and reduce steady background audio."""
    meta = {"enabled": True, "mode": "voice_focus_gate"}
    try:
        import numpy as np

        arr = np.asarray(samples, dtype=np.int16)
        if arr.size <= 0:
            meta["empty"] = True
            return samples, meta
        shaped = arr.reshape((-1, 1)) if arr.ndim == 1 else arr
        x = shaped.astype(np.float32)
        abs_before = np.abs(x)
        peak_before = float(abs_before.max()) if abs_before.size else 0.0
        rms_before = float(np.sqrt(np.mean(np.square(x)))) if x.size else 0.0
        meta.update({
            "peak_before": round(peak_before, 2),
            "rms_before": round(rms_before, 2),
        })
        if peak_before < 160:
            meta["too_quiet"] = True
            return shaped.astype(np.int16), meta

        x = x - float(np.mean(x))
        if x.shape[0] > 1:
            hp = np.empty_like(x)
            hp[0] = x[0]
            hp[1:] = x[1:] - (0.965 * x[:-1])
            x = (0.72 * x) + (0.28 * hp)

        absx = np.abs(x)
        floor = float(np.percentile(absx, 38)) if absx.size else 0.0
        threshold = max(220.0, floor * 2.2)
        quiet = absx < threshold
        x[quiet] *= 0.18
        peak_after = float(np.max(np.abs(x))) if x.size else 0.0
        if peak_after > 0 and peak_after < 12000:
            x *= min(3.0, 12000.0 / peak_after)
        x = np.clip(x, -32768, 32767).astype(np.int16)
        meta.update({
            "noise_floor": round(floor, 2),
            "gate_threshold": round(threshold, 2),
            "peak_after": int(np.max(np.abs(x))) if x.size else 0,
        })
        return x, meta
    except Exception as ex:
        meta["error"] = str(ex)
        return samples, meta


def _select_local_audio_input(sd) -> dict | None:
    devices = list(sd.query_devices() or [])
    default_index = _audio_default_input_index(sd)
    env_pick = (
        os.environ.get("YAZKLINIK_WEBSHELL_MIC_DEVICE")
        or os.environ.get("YAZKLINIK_MIC_DEVICE")
        or ""
    ).strip()
    candidates = []
    for idx, item in enumerate(devices):
        try:
            max_in = int(item.get("max_input_channels") or 0)
        except Exception:
            max_in = 0
        if max_in <= 0:
            continue
        rate = int(float(item.get("default_samplerate") or 16000))
        score = _audio_input_score(idx, item, default_index)
        candidate = {
            "index": idx,
            "name": str(item.get("name") or f"Input {idx}"),
            "channels": max_in,
            "default_samplerate": rate,
            "score": score,
        }
        candidates.append(candidate)
    if env_pick:
        env_key = _audio_name_key(env_pick)
        for candidate in candidates:
            if (
                env_pick.isdigit() and int(candidate["index"]) == int(env_pick)
            ) or (env_key and env_key in _audio_name_key(candidate["name"])):
                if _audio_check_input(sd, candidate["index"], candidate["default_samplerate"]):
                    candidate["selected_by"] = "env"
                    return candidate
    valid = [
        c for c in candidates
        if _audio_check_input(sd, c["index"], c["default_samplerate"])
    ]
    if not valid:
        return None
    valid.sort(key=lambda c: (int(c.get("score") or 0), -int(c["index"])), reverse=True)
    selected = dict(valid[0])
    selected["selected_by"] = "default" if selected["index"] == default_index else "auto"
    return selected


def _local_audio_input_payload() -> dict:
    devices = []
    errors = []
    selected = None
    try:
        import sounddevice as sd
        selected = _select_local_audio_input(sd)
        for idx, item in enumerate(sd.query_devices() or []):
            try:
                max_in = int(item.get("max_input_channels") or 0)
            except Exception:
                max_in = 0
            if max_in > 0:
                devices.append({
                    "index": idx,
                    "name": str(item.get("name") or f"Input {idx}"),
                    "channels": max_in,
                    "default_samplerate": item.get("default_samplerate"),
                    "score": _audio_input_score(idx, item, _audio_default_input_index(sd)),
                    "selected": bool(selected and int(selected.get("index")) == idx),
                })
    except Exception as ex:
        errors.append(str(ex))
    return {
        "ok": bool(devices),
        "devices": devices,
        "selected": selected,
        "selected_index": selected.get("index") if selected else None,
        "selected_name": selected.get("name") if selected else "",
        "error": "; ".join(errors),
    }


def _record_local_audio_wav_payload(seconds: float = 7.0) -> dict:
    try:
        seconds = max(2.0, min(12.0, float(seconds or 7.0)))
    except Exception:
        seconds = 7.0
    try:
        import base64
        import io
        import wave
        import sounddevice as sd

        selected = _select_local_audio_input(sd)
        if not selected:
            return {
                "ok": False,
                "error": "Sistemde aktif mikrofon bulunamadi.",
            }
        device_index = int(selected["index"])
        device_name = str(selected.get("name") or f"Input {device_index}")
        device_rate = int(float(selected.get("default_samplerate") or 16000))

        def _capture(rate: int):
            frames = int(max(1, rate * seconds))
            data = sd.rec(
                frames,
                samplerate=rate,
                channels=1,
                dtype="int16",
                device=device_index,
            )
            sd.wait()
            return data, rate

        try:
            samples, samplerate = _capture(16000)
        except Exception:
            fallback_rate = max(8000, min(48000, int(device_rate or 16000)))
            samples, samplerate = _capture(fallback_rate)

        samples, focus_meta = _focus_local_voice_samples(samples)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(int(samplerate))
            wav.writeframes(samples.tobytes())
        raw = base64.b64encode(buf.getvalue()).decode("ascii")
        return {
            "ok": True,
            "audio_base64": "data:audio/wav;base64," + raw,
            "audio_b64": raw,
            "mime_type": "audio/wav",
            "filename": "webshell-mic.wav",
            "seconds": seconds,
            "samplerate": int(samplerate),
            "device_index": device_index,
            "device_name": device_name,
            "voice_focus": True,
            "voice_focus_meta": focus_meta,
        }
    except Exception as ex:
        return {"ok": False, "error": str(ex)}


class WebShellNativeBridge(QObject):
    @Slot(str, result=bool)
    def openUrl(self, raw_url: str) -> bool:
        try:
            url = QUrl(str(raw_url or ""))
            scheme = (url.scheme() or "").lower()
            if scheme == "yazklinik-print-photo":
                return _launch_photo_print_helper(url)
            if scheme == "yazklinik-wa":
                return _launch_whatsapp_local_helper(url)
            if scheme == "yazklinik-open-folder":
                return _launch_open_folder_helper(url)
            if scheme in {"http", "https", "file", "whatsapp"}:
                return QDesktopServices.openUrl(url)
        except Exception:
            return False
        return False

    @Slot(result=str)
    def audioInputsJson(self) -> str:
        try:
            return json.dumps(_local_audio_input_payload(), ensure_ascii=False)
        except Exception as ex:
            return json.dumps({"ok": False, "devices": [], "error": str(ex)})

    @Slot(int, result=str)
    def recordWavJson(self, seconds: int) -> str:
        try:
            return json.dumps(
                _record_local_audio_wav_payload(seconds), ensure_ascii=False)
        except Exception as ex:
            return json.dumps({"ok": False, "error": str(ex)})


_ROUTE_ICON_MAP: dict[str, str] = {
    "/": "\u25c9",
    "/dashboard": "\u2302",
    "/komuta-merkezi": "\u25ce",
    "/kullanim-kalitesi": "\u2726",
    "/akilli-dialog": "\u25cc",
    "/gun-plani": "\u2600",
    "/gunluk-ozet": "\u25a4",
    "/aylik-rapor": "\u25a3",
    "/istatistikler": "\u2197",
    "/yeni-hasta": "\uff0b",
    "/arama": "\u2315",
    "/gelismis-arama": "\u2295",
    "/jinekoloji": "\u2640",
    "/obstetrik": "\u2661",
    "/riskli-gebelik": "\u26a0",
    "/medikal-estetik": "\u2727",
    "/doguranlar": "\u2665",
    "/yaklasan-dogumlar": "\u25f7",
    "/karsilastir": "\u21c4",
    "/hizli-not": "\u270e",
    "/randevular": "\u25a6",
    "/takvim": "\u25a7",
    "/randevu/yeni": "\u229e",
    "/toplu-hatirlatma": "\u25d4",
    "/dicom": "\u25a7",
    "/dicom?mode=ai": "\u25c8",
    "/dicom-servisleri": "\u2699",
    "/dicom-alisveris": "\u21c6",
    "/dicom-worklist": "\u2611",
    "/dicom-ayar": "\u2699",
    "/takip-medya-arsivi": "\u25a7",
    "/ekran-yakala": "\u25a3",
    "/entegrasyonlar/usg-nas": "\u25a7",
    "/yz-asistan": "\u2739",
    "/yz-sihirbazi": "\u2726",
    "/yz-server-durum": "\u25a7",
    "/yz-tahlil-yorumla": "\u25a4",
    "/yz-ses-cevir": "\u266b",
    "/yz-telefon-diyalog": "\u260e",
    "/entegrasyon/yz-telesekreter": "\u260e",
    "/araclar": "\u2695",
    "/araclar/bmi-hesapla": "\u25c7",
    "/araclar/gebelik-hesapla": "\u2661",
    "/araclar/fetal-tartim": "\u25ce",
    "/araclar/bishop-skoru": "\u25a4",
    "/araclar/preeklampsi-risk": "\u26a0",
    "/araclar/ilac-rehberi": "\u271a",
    "/araclar/karar-agaci": "\u22b9",
    "/dogum-geri-sayim": "\u25f7",
    "/gorevler": "\u2611",
    "/gorev/yeni": "\u229e",
    "/akilli-bildirimler": "\u25d4",
    "/akilli-rehber": "\u25cc",
    "/onam-sablonlari": "\u25a4",
    "/recete-sablonlari": "\u271a",
    "/wa-sablonlar": "\u260e",
    "/bulutklinik-aktarim": "\u2601",
    "/entegrasyonlar": "\u22b9",
    "/entegrasyon/ip-cihazlar": "\u25a7",
    "/nas-senkronizasyon": "\u21c6",
    "/whatsapp-ayarlari": "\u260e",
    "/wa-toplu": "\u260e",
    "/telefon-ara": "\u260e",
    "/ayarlar": "\u2699",
    "/tum-ayarlar": "\u2699",
    "/ayar-editoru": "\u2699",
    "/sistem-parametreleri": "\u2699",
    "/yazici-ayarlari": "\u2399",
    "/sistem-durumu": "\u25cc",
    "/performans-ayarlari": "\u25ce",
    "/protokol-ayarlari": "\u2116",
    "/veri-konumlari": "\u25a7",
    "/veritabani-saglik-kontrol": "\u25a3",
    "/sistem-cache-temizle": "\u21bb",
    "/audit-log": "\u25a4",
    "/otomatik-yedekler": "\u25a3",
    "/otomatik-yedek/simdi-al": "\u25a3",
    "/sistem-format": "\u26a0",
    "/sistem-guncelleme": "\u21bb",
    "/sistem-sifirla": "\u26a0",
    "/export/hastalar.csv": "\u25a4",
    "/export/randevular.csv": "\u25a4",
    "/kullanici-ekle": "\u2295",
    "/sifre-degistir": "\u25c8",
    "/yardim": "?",
    "/cikis": "\u23fb",
}

_ROUTE_ICON_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("risk", "preeklampsi", "format", "sifirla"), "\u26a0"),
    (("whatsapp", "telefon", "telesekreter", "wa-"), "\u260e"),
    (("randevu", "takvim", "hatirlatma"), "\u25a6"),
    (("hasta", "kullanici"), "\u25c9"),
    (("arama", "search"), "\u2315"),
    (("gebelik", "obstetrik", "dogum"), "\u2661"),
    (("jinekoloji",), "\u2640"),
    (("medikal-estetik", "estetik"), "\u2727"),
    (("dicom", "usg", "pacs", "medya", "ekran-yakala"), "\u25a7"),
    (("yz", "akilli", "ai", "asistan"), "\u2739"),
    (("rapor", "ozet", "log", "csv"), "\u25a4"),
    (("istatistik", "performans"), "\u2197"),
    (("ayar", "parametre"), "\u2699"),
    (("yedek", "db", "database", "veritabani"), "\u25a3"),
    (("gorev", "checklist", "kontrol"), "\u2611"),
    (("arac", "ilac", "recete"), "\u271a"),
    (("senkron", "entegrasyon", "aktarim"), "\u21c6"),
)


def _ascii_badge(value: str = "", route: str = "") -> str:
    """Return a short, encoding-safe menu badge for Qt/Windows shells."""
    raw = str(value or "").strip()
    if raw.startswith("[") and raw.endswith("]"):
        raw = raw[1:-1].strip()
    raw = re.sub(r"[^A-Za-z0-9+\-?<>=!]", "", raw).upper()
    if raw:
        return raw[:4]

    parsed = urllib.parse.urlsplit(str(route or "").strip())
    path = (parsed.path or "/").strip("/")
    if not path:
        return "A"
    aliases = {
        "dashboard": "P",
        "komuta": "K",
        "merkezi": "M",
        "hasta": "H",
        "hastalar": "H",
        "arama": "AR",
        "randevu": "R",
        "randevular": "R",
        "dicom": "D",
        "yz": "YZ",
        "ai": "YZ",
        "whatsapp": "WA",
        "wa": "WA",
        "enabiz": "EN",
        "ayar": "AY",
        "ayarlar": "AY",
        "sistem": "S",
        "rapor": "RP",
        "pdf": "PDF",
        "medya": "MD",
        "nas": "NAS",
        "telefon": "TEL",
        "takvim": "TV",
        "gorev": "G",
        "gorevler": "G",
        "yazici": "YZC",
    }
    parts = [p for p in re.split(r"[/\\?&=_\-.]+", path.lower()) if p and "{" not in p]
    for part in parts:
        if part in aliases:
            return aliases[part]
    initials = "".join(part[:1] for part in parts[:3]).upper()
    return initials[:4] or "A"


def _route_symbol(route: str = "") -> str:
    raw = str(route or "").strip()
    parsed = urllib.parse.urlsplit(raw)
    path = parsed.path or "/"
    key = path
    if parsed.query:
        key += "?" + parsed.query
    if key in _ROUTE_ICON_MAP:
        return _ROUTE_ICON_MAP[key]
    if path in _ROUTE_ICON_MAP:
        return _ROUTE_ICON_MAP[path]
    haystack = (key or raw).lower()
    for needles, symbol in _ROUTE_ICON_KEYWORDS:
        if any(needle in haystack for needle in needles):
            return symbol
    return ""


def route_icon(route: str, fallback: str = "") -> str:
    """Resolve a route to a compact WebShell sidebar symbol."""
    symbol = _route_symbol(route)
    if symbol:
        return symbol
    raw = str(fallback or "").strip()
    if raw in {"+", "?", "??", "<>", "->"}:
        return raw
    return _ascii_badge(fallback, route)


def _nav_badge(icon: str) -> str:
    """Geriye doneuk: legacy text-badge donemi icin kisa metin uretir."""
    return _ascii_badge(icon, "")


_NAV_ACCENT_PALETTES: dict[str, tuple[str, str]] = {
    "primary": ("#0ea5e9", "#14b8a6"),
    "patient": ("#0ea5e9", "#2563eb"),
    "flow": ("#06b6d4", "#22c55e"),
    "ob": ("#08b6d1", "#10b981"),
    "risk": ("#ff7a45", "#f43f5e"),
    "birth": ("#0ea5e9", "#ec4899"),
    "media": ("#0891b2", "#6366f1"),
    "ai": ("#7c3aed", "#0ea5e9"),
    "task": ("#14b8a6", "#22c55e"),
    "admin": ("#64748b", "#0ea5e9"),
    "export": ("#2563eb", "#475569"),
}


def _nav_visual_kind(route: str = "", label: str = "") -> str:
    text = f"{route or ''} {label or ''}".lower()
    if "risk" in text or "preeklampsi" in text or "sifirla" in text or "format" in text:
        return "risk"
    if "dogum" in text or "doguran" in text or "gebelik" in text or "obstetrik" in text:
        return "ob"
    if "jinekoloji" in text:
        return "female"
    if "medikal-estetik" in text or "estetik" in text:
        return "spark"
    if "randevu" in text or "takvim" in text or "plan" in text:
        return "calendar"
    if "arama" in text or "search" in text:
        return "search"
    if "hasta" in text or "kullanici" in text or route == "/":
        return "patient"
    if "dicom" in text or "usg" in text or "medya" in text or "ekran-yakala" in text:
        return "media"
    if "yz" in text or "ai" in text or "akilli" in text or "asistan" in text:
        return "ai"
    if "gorev" in text or "onam" in text or "recete" in text or "ilac" in text:
        return "task"
    if "ayar" in text or "sistem" in text or "parametre" in text:
        return "settings"
    if "rapor" in text or "istatistik" in text or "csv" in text or "export" in text:
        return "chart"
    if "yedek" in text or "veritabani" in text or "db" in text or "nas" in text:
        return "storage"
    if "komuta" in text or "entegrasyon" in text or "senkron" in text or "aktarim" in text:
        return "flow"
    return "dashboard"


def _nav_palette_for_kind(kind: str) -> tuple[str, str]:
    if kind in {"ob", "female"}:
        return _NAV_ACCENT_PALETTES["ob"]
    if kind in {"risk"}:
        return _NAV_ACCENT_PALETTES["risk"]
    if kind in {"birth"}:
        return _NAV_ACCENT_PALETTES["birth"]
    if kind in {"media", "storage"}:
        return _NAV_ACCENT_PALETTES["media"]
    if kind in {"ai"}:
        return _NAV_ACCENT_PALETTES["ai"]
    if kind in {"task", "calendar"}:
        return _NAV_ACCENT_PALETTES["task"]
    if kind in {"settings"}:
        return _NAV_ACCENT_PALETTES["admin"]
    if kind in {"chart"}:
        return _NAV_ACCENT_PALETTES["export"]
    if kind in {"patient", "search"}:
        return _NAV_ACCENT_PALETTES["patient"]
    if kind in {"flow", "spark"}:
        return _NAV_ACCENT_PALETTES["flow"]
    return _NAV_ACCENT_PALETTES["primary"]


def _display_route(route: str) -> str:
    route = (route or "/").strip() or "/"
    parsed = urllib.parse.urlsplit(route)
    path = parsed.path or "/"
    suffix = ""
    if parsed.query:
        suffix += "?" + parsed.query
    if parsed.fragment:
        suffix += "#" + parsed.fragment
    if path.startswith("/hasta/"):
        rest = path[len("/hasta/"):].strip("/")
        if rest:
            return urllib.parse.unquote(rest) + suffix
    return path + suffix


_PATIENT_ACTION_LABELS = {
    "recete-hazirla": "Recete hazirla",
    "whatsapp": "WhatsApp",
    "gelis": "Gelis",
    "medya": "Medya",
    "takip-medya": "Takip medya",
    "raporlar": "Raporlar",
    "dosyalar": "Dosyalar",
    "dicom": "DICOM",
    "konusarak-not": "Konusarak not",
    "notlar": "Notlar",
    "tahliller": "Tahliller",
    "diyet-plani": "Diyet plani",
    "randevu": "Randevu",
}


_PRINT_SETTINGS_CACHE = {"ts": 0.0, "data": {}}


def _remote_print_settings() -> dict:
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
    try:
        base = api_client.discover().rstrip("/")
        req = urllib.request.Request(
            base + "/api/yazici-ayarlari",
            headers={"X-Terminal-Token": api_client.TERMINAL_TOKEN})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace") or "{}")
        data = payload.get("settings") if isinstance(payload, dict) else {}
        if not isinstance(data, dict):
            data = {}
        cleaned = dict(defaults)
        cleaned.update({k: str(v) for k, v in data.items()})
        _PRINT_SETTINGS_CACHE.update({"ts": now, "data": cleaned})
        return cleaned
    except Exception:
        return defaults


def _qt_page_size(name: str):
    value = (name or "A4").upper()
    mapping = {
        "A3": QPageSize.A3,
        "A4": QPageSize.A4,
        "A5": QPageSize.A5,
        "LETTER": QPageSize.Letter,
    }
    return QPageSize(mapping.get(value, QPageSize.A4))


def _apply_saved_print_settings(printer) -> dict:
    settings = _remote_print_settings()
    try:
        printer.setPageSize(_qt_page_size(settings.get("paper", "A4")))
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


def _clean_patient_key_label(patient_key: str) -> str:
    raw = urllib.parse.unquote(str(patient_key or "")).replace("_", " ").strip()
    if not raw:
        return "Hasta"
    visit_date = ""
    m = re.match(r"^F\d+-(\d{2})-(\d{2})-(\d{2})-\d+[\s_-]*(.*)$", raw)
    if m:
        visit_date = f"{m.group(3)}.{m.group(2)}.20{m.group(1)}"
        raw = m.group(4).strip()
    raw = re.sub(r"^\d{2}[\s._-]\d{2}[\s._-]\d{1,2}[\s._-]\d+\s*", "", raw)
    raw = re.sub(r"^\d{4,}\s*", "", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" -_/")
    if not raw:
        raw = "Hasta"
    if visit_date:
        return f"{raw} ({visit_date})"
    return raw


def _address_route_label(route: str) -> str:
    route = (route or "/").strip() or "/"
    parsed = urllib.parse.urlsplit(route)
    path = parsed.path or "/"
    suffix = ""
    if parsed.query:
        suffix += "?" + parsed.query
    if parsed.fragment:
        suffix += "#" + parsed.fragment
    parts = [p for p in path.split("/") if p]
    if len(parts) >= 2 and parts[0] == "hasta":
        patient = _clean_patient_key_label(parts[1])
        if len(parts) >= 3:
            action_key = parts[2]
            action = _PATIENT_ACTION_LABELS.get(
                action_key, action_key.replace("-", " ").strip().title())
            return f"Hasta: {patient} / {action}{suffix}"
        return f"Hasta: {patient}{suffix}"
    return _display_route(route)


def _address_text_to_route(text: str, saved_route: str = "") -> str:
    text = (text or "").strip()
    if not text:
        return "/dashboard"
    if text.startswith("http://") or text.startswith("https://"):
        return text
    if text.startswith("/"):
        return text
    if saved_route and text in {_display_route(saved_route), _address_route_label(saved_route)}:
        return saved_route
    return "/" + text


def _webshell_mark_internal_url(raw_url: str, server_url: str = "") -> str:
    text = str(raw_url or "").strip()
    try:
        parsed = urllib.parse.urlsplit(text)
        if parsed.scheme.lower() not in {"http", "https"}:
            return text
        if server_url:
            base = urllib.parse.urlsplit(str(server_url or ""))
            host = (parsed.hostname or "").lower()
            base_host = (base.hostname or "").lower()
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
            base_port = base.port or (443 if base.scheme == "https" else 80)
            if host != base_host or port != base_port:
                return text
        pairs = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        if not any(k.lower() == "yk_webshell" for k, _ in pairs):
            pairs.append(("yk_webshell", "1"))
        return urllib.parse.urlunsplit((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            urllib.parse.urlencode(pairs, doseq=True),
            parsed.fragment,
        ))
    except Exception:
        return text


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
        settings = _apply_saved_print_settings(printer)
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


def _remove_later(path):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


def _print_pdf_file_via_system(pdf_path, parent=None):
    try:
        if os.name == "nt" and hasattr(os, "startfile"):
            os.startfile(str(pdf_path), "print")
            try:
                parent.statusBar().showMessage(
                    "PDF varsayilan yaziciya gonderildi.", 5000)
            except Exception:
                pass
            return True
    except Exception:
        pass
    try:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(pdf_path)))
        QMessageBox.information(
            parent, "Yazdir",
            "Qt yazici penceresi yok. Sayfa PDF olarak acildi; acilan "
            "pencereden yazdirabilirsiniz.")
        return True
    except Exception as ex:
        QMessageBox.warning(
            parent, "Yazdir",
            "Sayfa PDF olarak hazirlandi ama yazdirma baslatilamadi.\n"
            f"{pdf_path}\n{ex}")
        return False


def _browser_print_exe():
    names = [
        ("Microsoft", "Edge", "Application", "msedge.exe"),
        ("Google", "Chrome", "Application", "chrome.exe"),
    ]
    roots = [
        os.environ.get("ProgramFiles", ""),
        os.environ.get("ProgramFiles(x86)", ""),
        os.environ.get("LOCALAPPDATA", ""),
    ]
    for root in roots:
        if not root:
            continue
        for parts in names:
            path = os.path.join(root, *parts)
            if os.path.exists(path):
                return path
    for exe in ("msedge.exe", "chrome.exe"):
        return exe
    return ""


def _print_html_snapshot(html, parent=None):
    stamp = int(time.time() * 1000)
    html_path = os.path.join(tempfile.gettempdir(),
                             f"YazKlinik_Gecici_Yazdir_{stamp}.html")
    pdf_path = os.path.join(tempfile.gettempdir(),
                            f"YazKlinik_Gecici_Yazdir_{stamp}.pdf")
    try:
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html or "")
        browser = _browser_print_exe()
        if browser:
            cmd = [
                browser,
                "--headless",
                "--disable-gpu",
                "--no-pdf-header-footer",
                f"--print-to-pdf={pdf_path}",
                QUrl.fromLocalFile(html_path).toString(),
            ]
            try:
                subprocess.run(cmd, timeout=20, check=False,
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL)
            except Exception:
                pass
        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
            if QPrinter is not None and QPrintDialog is not None:
                _print_pdf_file_via_qt(pdf_path, parent)
                QTimer.singleShot(120000, lambda p=pdf_path: _remove_later(p))
            else:
                _print_pdf_file_via_system(pdf_path, parent)
                QTimer.singleShot(120000, lambda p=pdf_path: _remove_later(p))
            QTimer.singleShot(120000, lambda p=html_path: _remove_later(p))
            return True
        try:
            os.startfile(html_path, "print")
            QTimer.singleShot(120000, lambda p=html_path: _remove_later(p))
            return True
        except Exception:
            QDesktopServices.openUrl(QUrl.fromLocalFile(html_path))
            QMessageBox.information(
                parent, "Yazdir",
                "Yazdirma penceresi acilamadi. Sayfa HTML olarak acildi; "
                "acilan pencereden yazdirabilirsiniz.")
            return True
    except Exception as ex:
        QMessageBox.warning(
            parent, "Yazdir",
            "Yazdirma sayfasi hazirlanamadi.\n"
            f"{ex}")
        return False


def _print_web_page_to_pdf(page, parent=None):
    if not hasattr(page, "printToPdf"):
        return False
    pdf_path = os.path.join(
        tempfile.gettempdir(),
        f"YazKlinik_Gecici_Yazdir_{int(time.time() * 1000)}.pdf")
    job = {"done": False, "path": pdf_path}

    def _finish(path=None, ok=True):
        if job["done"]:
            return
        job["done"] = True
        target = str(path or pdf_path)
        try:
            page.pdfPrintingFinished.disconnect(_finish)
        except Exception:
            pass
        try:
            if not ok or not os.path.exists(target):
                QMessageBox.warning(
                    parent, "Yazdir",
                    "Yazdirma sayfasi hazirlanamadi. Yaziciyi tekrar deneyin.")
                return
            if QPrinter is not None and QPrintDialog is not None:
                _print_pdf_file_via_qt(target, parent)
                QTimer.singleShot(120000, lambda p=target: _remove_later(p))
            else:
                _print_pdf_file_via_system(target, parent)
                QTimer.singleShot(120000, lambda p=target: _remove_later(p))
        finally:
            try:
                if hasattr(parent, "_yk_pdf_print_job"):
                    parent._yk_pdf_print_job = None
            except Exception:
                pass

    try:
        parent._yk_pdf_print_job = job
    except Exception:
        pass
    try:
        page.pdfPrintingFinished.connect(_finish)
    except Exception:
        pass
    try:
        page.printToPdf(pdf_path)
        QTimer.singleShot(
            9000, lambda: _finish(pdf_path, os.path.exists(pdf_path)))
        try:
            parent.statusBar().showMessage(
                "Yazdirma ekrani hazirlaniyor...", 3000)
        except Exception:
            pass
        return True
    except Exception:
        try:
            page.pdfPrintingFinished.disconnect(_finish)
        except Exception:
            pass
        return False


def _print_web_page_snapshot(page, parent=None):
    if not hasattr(page, "toHtml"):
        return False
    job = {"done": False}

    def _got_html(html):
        if job["done"]:
            return
        job["done"] = True
        try:
            _print_html_snapshot(html, parent)
        finally:
            try:
                if hasattr(parent, "_yk_html_print_job"):
                    parent._yk_html_print_job = None
            except Exception:
                pass

    try:
        parent._yk_html_print_job = job
    except Exception:
        pass
    try:
        page.toHtml(_got_html)
        return True
    except Exception:
        try:
            if hasattr(parent, "_yk_html_print_job"):
                parent._yk_html_print_job = None
        except Exception:
            pass
        return False


def _print_web_view_native(view, parent=None):
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

    if _print_web_page_to_pdf(page, parent):
        return

    if QPrinter is not None and QPrintDialog is not None and hasattr(page, "print"):
        try:
            printer = QPrinter(QPrinter.HighResolution)
            try:
                printer.setOutputFormat(QPrinter.NativeFormat)
            except Exception:
                pass
            settings = _apply_saved_print_settings(printer)
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
        except Exception:
            try:
                parent.statusBar().showMessage(
                    "Yerel yazdirma desteklenmedi; PDF yolu deneniyor...", 4000)
            except Exception:
                pass

    if hasattr(page, "printToPdf"):
        pdf_path = os.path.join(
            tempfile.gettempdir(),
            f"YazKlinik_Gecici_Yazdir_{int(time.time() * 1000)}.pdf")
        job = {"done": False, "path": pdf_path}

        def _finish(path=None, ok=True):
            if job["done"]:
                return
            job["done"] = True
            target = str(path or pdf_path)
            try:
                page.pdfPrintingFinished.disconnect(_finish)
            except Exception:
                pass
            try:
                if not ok or not os.path.exists(target):
                    QMessageBox.warning(
                        parent, "Yazdir",
                        "Yazdirma sayfasi hazirlanamadi. Yaziciyi tekrar deneyin.")
                    return
                if QPrinter is not None and QPrintDialog is not None:
                    _print_pdf_file_via_qt(target, parent)
                    try:
                        os.remove(target)
                    except Exception:
                        pass
                else:
                    _print_pdf_file_via_system(target, parent)
                    QTimer.singleShot(120000, lambda p=target: _remove_later(p))
            finally:
                try:
                    if hasattr(parent, "_yk_pdf_print_job"):
                        parent._yk_pdf_print_job = None
                except Exception:
                    pass

        try:
            parent._yk_pdf_print_job = job
        except Exception:
            pass
        try:
            page.pdfPrintingFinished.connect(_finish)
        except Exception:
            pass
        try:
            page.printToPdf(pdf_path)
            QTimer.singleShot(
                9000, lambda: _finish(pdf_path, os.path.exists(pdf_path)))
            try:
                parent.statusBar().showMessage(
                    "Yazdirma ekrani hazirlaniyor...", 3000)
            except Exception:
                pass
            return
        except Exception as ex:
            QMessageBox.warning(
                parent, "Yazdir",
                "Yazdirma ekrani hazirlanamadi.\n"
                f"{ex}")
            return

    if _print_web_page_snapshot(page, parent):
        try:
            parent.statusBar().showMessage(
                "Yazdirma sayfasi hazirlaniyor...", 3000)
        except Exception:
            pass
        return

    QMessageBox.warning(
        parent, "Yazdir",
        "Bu sayfa program icinde yazdirilamadi. Sayfa PDF/HTML olarak "
        "hazirlanamadi.")

def _webshell_cache_dir() -> str:
    override = os.environ.get("YAZKLINIK_WEBSHELL_CACHE_DIR", "").strip()
    if override:
        base = override
    elif os.name == "nt":
        base = os.path.join(
            os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local"),
            "YazKlinik", "WebShellCache")
    elif sys.platform == "darwin":
        base = str(Path.home() / "Library" / "Application Support" / "YazKlinik" / "WebShellCache")
    else:
        base = os.path.join(
            os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache"),
            "YazKlinik", "WebShellCache")
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        pass
    return base


def _configure_web_profile(view, server_url):
    if not HAS_WEB or not view: return
    try:
        prof = view.page().profile()
        base = _webshell_cache_dir()
        prof.setCachePath(base)
        prof.setPersistentStoragePath(os.path.join(base, "storage"))
        try:
            ua = str(prof.httpUserAgent() or "").strip()
            marker = "YazKlinikWebShell/1.0"
            if marker not in ua:
                prof.setHttpUserAgent((ua + " " + marker).strip())
        except Exception:
            pass
        cache_mb = int(os.environ.get("YAZKLINIK_WEBSHELL_CACHE_MB", "512"))
        prof.setHttpCacheMaximumSize(max(256, min(cache_mb, 1024)) * 1024 * 1024)
        try:
            ct = type(prof).HttpCacheType.DiskHttpCache
            prof.setHttpCacheType(ct)
        except: pass
        try:
            cp = type(prof).PersistentCookiesPolicy.ForcePersistentCookies
            prof.setPersistentCookiesPolicy(cp)
        except: pass
        try: prof.setSpellCheckEnabled(False)
        except: pass

        s = view.settings()
        a = type(s).WebAttribute
        gpu_turbo = os.environ.get("YAZKLINIK_WEBSHELL_GPU_TURBO", "1") == "1"
        for name, on in (
            ("JavascriptEnabled", True),
            ("ScrollAnimatorEnabled", False),
            ("PluginsEnabled", True),
            ("PdfViewerEnabled", True),
            ("XSSAuditingEnabled", False),
            ("PlaybackRequiresUserGesture", False),
            ("AllowRunningInsecureContent", True),
            ("WebGLEnabled", gpu_turbo),
            ("Accelerated2dCanvasEnabled", gpu_turbo),
            ("LocalContentCanAccessRemoteUrls", True),
            ("LocalContentCanAccessFileUrls", True),
        ):
            attr = getattr(a, name, None)
            if attr is not None:
                try: s.setAttribute(attr, on)
                except: pass
        try: view.page().setBackgroundColor(QColor("#FFFFFF"))
        except: pass
    except Exception as e:
        print(f"profile config: {e}")


def _windows_terminal_accelerator_enabled() -> bool:
    if os.environ.get("YAZKLINIK_WEBSHELL_SAFE_MODE", "").strip() == "1":
        return False
    return (
        os.name == "nt"
        and os.environ.get("YAZKLINIK_WEBSHELL_ROUTE_PREWARM", "0").strip() == "1"
    )


def _terminal_buffer_headers() -> dict:
    headers = {
        "User-Agent": "YazKlinik-WebShell-Windows-Buffer/1.0",
        "X-YazKlinik-WebShell-Buffer": "1",
    }
    try:
        token = str(getattr(api_client, "TERMINAL_TOKEN", "") or "")
        if token:
            headers["X-Terminal-Token"] = token
    except Exception:
        pass
    return headers


def _terminal_buffer_core_paths() -> list[str]:
    return [
        "/api/terminal/ping",
        "/api/ozellik-senkron",
        "/api/sistem-durumu",
        "/api/web-mic/context",
        "/brand-logo.png",
        "/favicon.ico",
    ]


class TerminalPcBuffer:
    """Small native pre-warmer so Windows WebShell feels ahead of the web UI."""

    def __init__(self, server_url: str):
        self.server_url = (server_url or "").strip().rstrip("/")
        self._seen: set[str] = set()
        self._lock = threading.Lock()

    def warm_start(self) -> None:
        self._spawn(_terminal_buffer_core_paths())

    def warm_route(self, route: str) -> None:
        route = str(route or "").strip()
        if not route or route.startswith("http"):
            return
        if not route.startswith("/"):
            route = "/" + route
        safe_neighbors = [
            "/api/terminal/ping",
            "/api/ozellik-senkron",
        ]
        if route.startswith("/hasta/"):
            safe_neighbors.append("/hastalar")
        elif route.startswith("/dicom"):
            safe_neighbors.extend(["/api/orthanc/status", "/api/dicom/exchange/status"])
        elif route.startswith("/obstetrik") or route.startswith("/yaklasan-dogumlar"):
            safe_neighbors.append("/yaklasan-dogumlar?refresh=1")
        self._spawn(safe_neighbors)

    def _spawn(self, paths: list[str]) -> None:
        if not _windows_terminal_accelerator_enabled() or not self.server_url:
            return
        todo = []
        with self._lock:
            for path in paths:
                path = str(path or "").strip()
                if not path or path in self._seen:
                    continue
                self._seen.add(path)
                todo.append(path)
        if not todo:
            return
        threading.Thread(target=self._run, args=(todo,), daemon=True).start()

    def _run(self, paths: list[str]) -> None:
        headers = _terminal_buffer_headers()
        for path in paths:
            try:
                url = self.server_url + path
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=1.6) as resp:
                    resp.read(64 * 1024)
            except Exception:
                pass


_WEBSHELL_WINDOWS_ACCELERATOR_JS = r"""
(function(){
  try {
    if (!/Windows/i.test(navigator.userAgent || '')) return;
    if (window.__ykWindowsTerminalBuffer) return;
    window.__ykWindowsTerminalBuffer = true;
    document.documentElement.setAttribute('data-terminal-buffer', 'windows');
    var routes = [
      '/dashboard','/hastalar','/arama','/yeni-hasta','/randevular',
      '/gun-plani','/klinik-akis','/obstetrik','/yaklasan-dogumlar',
      '/gorevler','/kontrol-listesi/menu','/onam-sablonlari','/hazir-receteler',
      '/api/terminal/ping','/api/ozellik-senkron','/api/sistem-durumu'
    ];
    var assets = ['/brand-logo.png','/favicon.ico'];
    function warm(url, delay) {
      setTimeout(function(){
        try {
          fetch(url, {credentials:'same-origin', cache:'force-cache'}).catch(function(){});
        } catch(e) {}
      }, delay);
    }
    function run() {
      var all = routes.concat(assets);
      for (var i = 0; i < all.length; i++) warm(all[i], 120 + i * 140);
    }
    if ('requestIdleCallback' in window) {
      requestIdleCallback(run, {timeout: 1400});
    } else {
      setTimeout(run, 650);
    }
  } catch(e) {}
})();
"""


_WEBSHELL_EMBED_FIX_JS = r"""
(function(){
  try {
    var d = document;
    var root = d.documentElement;
    var body = d.body || d.documentElement;
    d.cookie = 'yk_webshell=1; Path=/; SameSite=Lax';
    root.setAttribute('data-yazklinik-webshell', '1');
    window.ykForceNativeMic = true;
    try {
      Object.defineProperty(window, 'SpeechRecognition', {
        configurable: true, writable: true, value: undefined
      });
      Object.defineProperty(window, 'webkitSpeechRecognition', {
        configurable: true, writable: true, value: undefined
      });
    } catch (_speechPatchErr) {
      window.SpeechRecognition = undefined;
      window.webkitSpeechRecognition = undefined;
    }
    if (d.body) d.body.classList.add('yk-webshell-embedded');
    var css = `
      html[data-yazklinik-webshell="1"],
      html[data-yazklinik-webshell="1"] body {
        width: 100% !important;
        min-width: 0 !important;
        overflow-x: hidden !important;
        background: #f6fbff !important;
      }
      html[data-yazklinik-webshell="1"] .sidebar,
      html[data-yazklinik-webshell="1"] .top-header,
      html[data-yazklinik-webshell="1"] .mobile-bottom-nav,
      html[data-yazklinik-webshell="1"] .sidebar-overlay {
        display: none !important;
        visibility: hidden !important;
        opacity: 0 !important;
        pointer-events: none !important;
      }
      html[data-yazklinik-webshell="1"] .app-layout {
        display: block !important;
        min-height: 100vh !important;
        width: 100% !important;
      }
      html[data-yazklinik-webshell="1"] .main-content,
      html[data-yazklinik-webshell="1"] .content-area {
        margin-left: 0 !important;
        padding-top: 0 !important;
        min-height: 100vh !important;
        width: 100% !important;
        max-width: none !important;
      }
      html[data-yazklinik-webshell="1"] .main-container,
      html[data-yazklinik-webshell="1"] .container,
      html[data-yazklinik-webshell="1"] .container-fluid {
        max-width: none !important;
      }
      html[data-yazklinik-webshell="1"] .main-container {
        margin: 0 !important;
        padding: 18px 20px 82px !important;
        width: 100% !important;
      }
      html[data-yazklinik-webshell="1"] .smart-guide-widget {
        right: 18px !important;
        bottom: 18px !important;
        z-index: 2000 !important;
      }
      html[data-yazklinik-webshell="1"] .yk-global-voice-widget {
        right: 18px !important;
        bottom: 92px !important;
        z-index: 1999 !important;
      }
      html[data-yazklinik-webshell="1"] .modal,
      html[data-yazklinik-webshell="1"] .offcanvas {
        z-index: 3000 !important;
      }
    `;
    var style = d.getElementById('yk-webshell-embed-fix');
    if (!style) {
      style = d.createElement('style');
      style.id = 'yk-webshell-embed-fix';
      (d.head || root).appendChild(style);
    }
    if (style.textContent !== css) style.textContent = css;
    function applyOnce(){
      try {
        ['.sidebar','.top-header','.mobile-bottom-nav','.sidebar-overlay'].forEach(function(sel){
          d.querySelectorAll(sel).forEach(function(el){
            el.style.setProperty('display', 'none', 'important');
            el.style.setProperty('visibility', 'hidden', 'important');
          });
        });
        d.querySelectorAll('.main-content,.content-area').forEach(function(el){
          el.style.setProperty('margin-left', '0', 'important');
          el.style.setProperty('padding-top', '0', 'important');
          el.style.setProperty('width', '100%', 'important');
        });
      } catch(e) {}
    }
    applyOnce();
    if (!window.__ykWebShellEmbedFixObserver) {
      var hits = 0;
      window.__ykWebShellEmbedFixObserver = new MutationObserver(function(){
        hits += 1;
        if (hits < 80) applyOnce();
      });
      window.__ykWebShellEmbedFixObserver.observe(root, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['class', 'style']
      });
    }
  } catch(e) {}
})();
"""

_WEBSHELL_NATIVE_BRIDGE_JS = r"""
(function(){
  if (window.__ykNativeBridgeBooting) return;
  window.__ykNativeBridgeBooting = true;
  function expose(bridge){
    try {
      window.yazklinikNative = bridge;
      window.ykNativeOpenUrl = function(url, callback){
        try {
          if (!url || !window.yazklinikNative || !window.yazklinikNative.openUrl) return false;
          var done = false;
          var cb = function(ok){
            done = true;
            try {
              if (typeof callback === 'function') callback(!!ok);
              if (!ok) {
                window.dispatchEvent(new CustomEvent('yazklinik-native-url-failed', {
                  detail: {url: String(url || '')}
                }));
              }
            } catch(e) {}
          };
          var result = window.yazklinikNative.openUrl(String(url), cb);
          if (typeof result === 'boolean') {
            cb(result);
            return result;
          }
          window.setTimeout(function(){
            if (!done && typeof callback === 'function') {
              try { callback(true); } catch(e) {}
            }
          }, 1200);
          return true;
        } catch(e) { return false; }
      };
      window.ykNativeOpenOrNavigate = function(url){
        if (!url) return false;
        try {
          if (window.ykNativeOpenUrl && window.ykNativeOpenUrl(url)) return true;
        } catch(e) {}
        try { window.location.href = String(url); return true; } catch(e) {}
        return false;
      };
      if (!window.__ykNativeClickBridge) {
        window.__ykNativeClickBridge = true;
        document.addEventListener('click', function(ev){
          try {
            var target = ev.target && ev.target.closest
              ? ev.target.closest('a[href^="yazklinik-"],a[href^="whatsapp:"],a[href*="://wa.me/"],a[href*="web.whatsapp.com"],a[href*="api.whatsapp.com"]')
              : null;
            if (!target) return;
            var url = target.getAttribute('href') || '';
            if (!url) return;
            if (window.ykNativeOpenOrNavigate && window.ykNativeOpenOrNavigate(url)) {
              ev.preventDefault();
            }
          } catch(e) {}
        }, true);
      }
      window.ykNativeAudioInputs = function(){
        return new Promise(function(resolve){
          try {
            if (!window.yazklinikNative || !window.yazklinikNative.audioInputsJson) {
              resolve({ok:false, devices:[], error:'native bridge yok'});
              return;
            }
            window.yazklinikNative.audioInputsJson(function(raw){
              try { resolve(JSON.parse(raw || '{}')); }
              catch(e) { resolve({ok:false, devices:[], error:String(e || '')}); }
            });
          } catch(e) {
            resolve({ok:false, devices:[], error:String(e || '')});
          }
        });
      };
      window.ykNativeRecordWav = function(seconds){
        return new Promise(function(resolve){
          try {
            if (!window.yazklinikNative || !window.yazklinikNative.recordWavJson) {
              resolve({ok:false, error:'native kayit koprusu yok'});
              return;
            }
            var sec = Math.max(2, Math.min(12, parseInt(seconds || 7, 10) || 7));
            window.yazklinikNative.recordWavJson(sec, function(raw){
              try { resolve(JSON.parse(raw || '{}')); }
              catch(e) { resolve({ok:false, error:String(e || '')}); }
            });
          } catch(e) {
            resolve({ok:false, error:String(e || '')});
          }
        });
      };
      window.dispatchEvent(new Event('yazklinik-native-ready'));
    } catch(e) {}
  }
  function init(){
    try {
      if (typeof qt === 'undefined' || !qt.webChannelTransport || typeof QWebChannel === 'undefined') {
        window.__ykNativeBridgeBooting = false;
        return;
      }
      new QWebChannel(qt.webChannelTransport, function(channel){
        expose(channel.objects.yazklinikNativeBridge);
        window.__ykNativeBridgeBooting = false;
      });
    } catch(e) {
      window.__ykNativeBridgeBooting = false;
    }
  }
  if (typeof QWebChannel === 'undefined') {
    try {
      var s = document.createElement('script');
      s.src = 'qrc:///qtwebchannel/qwebchannel.js';
      s.onload = init;
      s.onerror = function(){ window.__ykNativeBridgeBooting = false; };
      (document.head || document.documentElement).appendChild(s);
    } catch(e) {
      window.__ykNativeBridgeBooting = false;
    }
  } else {
    init();
  }
})();
"""


def _webshell_permission_policy(granted: bool):
    if QWebEnginePage is None:
        return None
    policy_name = (
        "PermissionGrantedByUser" if granted
        else "PermissionDeniedByUser"
    )
    try:
        return getattr(QWebEnginePage.PermissionPolicy, policy_name)
    except Exception:
        return getattr(QWebEnginePage, policy_name, None)


_WEBSHELL_TRUSTED_ORIGIN_PREFIXES = (
    "http://127.0.0.1",
    "http://localhost",
    "https://127.0.0.1",
    "https://localhost",
    "http://192.168.",
    "https://192.168.",
    "http://10.",
    "https://10.",
)


def _webshell_origin_is_trusted(origin: str) -> bool:
    if not origin:
        return False
    o = origin.lower()
    if any(o.startswith(p) for p in _WEBSHELL_TRUSTED_ORIGIN_PREFIXES):
        return True
    if o.startswith("https://"):
        return True
    return False


def _webshell_permissions_path() -> str:
    return os.path.join(_webshell_cache_dir(), "permissions.json")


def _webshell_load_permissions() -> dict:
    path = _webshell_permissions_path()
    try:
        import json as _json
        with open(path, "r", encoding="utf-8") as fh:
            data = _json.load(fh)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _webshell_save_permissions(data: dict) -> None:
    path = _webshell_permissions_path()
    try:
        import json as _json
        with open(path, "w", encoding="utf-8") as fh:
            _json.dump(data or {}, fh, ensure_ascii=False, indent=2)
    except Exception as ex:
        print(f"webshell permissions save: {ex}")


if QWebEnginePage is not None:
    class WebShellPage(QWebEnginePage):
        # Origin -> {feature_name: granted_bool} grant cache (session bazli)
        _granted_cache: dict = {}
        # Disk'ten yuklenen kalici permissions (origin -> {feature: bool})
        _persisted: dict = _webshell_load_permissions()

        def __init__(self, parent=None):
            super().__init__(parent)
            try:
                self.featurePermissionRequested.connect(
                    self._handle_feature_permission)
            except Exception:
                pass

        @classmethod
        def _persisted_lookup(cls, origin: str, feature_name: str):
            origin_map = cls._persisted.get(origin) or {}
            if feature_name in origin_map:
                return bool(origin_map[feature_name])
            # Fallback: bu origin icin baska bir audio izni varsa onu kullan
            folded = feature_name.lower()
            for k, v in origin_map.items():
                kl = k.lower()
                if (("audio" in folded and "audio" in kl)
                        or ("video" in folded and "video" in kl)
                        or ("notification" in folded and "notification" in kl)):
                    return bool(v)
            return None

        @classmethod
        def _persist(cls, origin: str, feature_name: str, granted: bool):
            if not origin:
                return
            origin_map = cls._persisted.setdefault(origin, {})
            origin_map[feature_name] = bool(granted)
            _webshell_save_permissions(cls._persisted)

        def _handle_feature_permission(self, security_origin, feature):
            feature_name = getattr(feature, "name", None) or str(feature)
            folded = feature_name.lower()
            origin = ""
            try:
                origin = security_origin.toString().lower()
            except Exception:
                origin = ""

            is_audio = (
                "mediaaudiocapture" in folded
                or "mediaaudiovideocapture" in folded
                or ("media" in folded and "audio" in folded)
                or ("capture" in folded and "audio" in folded)
                or "desktopaudio" in folded
            )
            is_notify = "notifications" in folded
            is_video = ("mediavideocapture" in folded
                        or ("media" in folded and "video" in folded
                            and "audio" not in folded))

            # 1) Disk'te kayitli karar varsa once onu uygula
            persisted = WebShellPage._persisted_lookup(origin, feature_name)

            allow = False
            if persisted is True:
                allow = True
            elif persisted is False:
                allow = False
            else:
                # 2) Trusted origin + ilgili feature ise otomatik izin ver
                if (is_audio or is_notify) and _webshell_origin_is_trusted(origin):
                    allow = True
                if is_video and _webshell_origin_is_trusted(origin):
                    allow = True

            # 3) Session cache (calisma anindaki kararlar)
            cache_key = (origin, feature_name)
            cached = WebShellPage._granted_cache.get(cache_key)
            if cached is True:
                allow = True
            elif cached is False:
                allow = False

            policy = _webshell_permission_policy(allow)
            if policy is None:
                return
            try:
                self.setFeaturePermission(security_origin, feature, policy)
                WebShellPage._granted_cache[cache_key] = bool(allow)
                # Trusted origin + audio/video/notification iznini diske yaz
                if (is_audio or is_video or is_notify) and origin:
                    WebShellPage._persist(origin, feature_name, allow)
            except Exception:
                pass

        def createWindow(self, window_type):
            try:
                view = self.parent()
                popup = WebShellPage(view)
                if not hasattr(self, "_yk_popup_pages"):
                    self._yk_popup_pages = []
                self._yk_popup_pages.append(popup)

                def _forward_url(url, popup_page=popup):
                    try:
                        if view is not None and hasattr(view, "setUrl"):
                            view.setUrl(url)
                    finally:
                        try:
                            popup_page.urlChanged.disconnect(_forward_url)
                        except Exception:
                            pass
                        try:
                            self._yk_popup_pages.remove(popup_page)
                        except Exception:
                            pass
                        try:
                            popup_page.deleteLater()
                        except Exception:
                            pass

                popup.urlChanged.connect(_forward_url)
                return popup
            except Exception:
                return super().createWindow(window_type)

        def acceptNavigationRequest(self, url, nav_type, is_main_frame):
            scheme = (url.scheme() or "").lower()
            host = (url.host() or "").lower()
            if scheme == "yazklinik-open-folder":
                if not _launch_open_folder_helper(url):
                    QDesktopServices.openUrl(url)
                return False
            if scheme == "yazklinik-print-photo":
                if not _launch_photo_print_helper(url):
                    QDesktopServices.openUrl(url)
                return False
            if scheme == "yazklinik-wa":
                if not _launch_whatsapp_local_helper(url):
                    QDesktopServices.openUrl(url)
                return False
            if scheme == "whatsapp" or host in {
                "wa.me", "web.whatsapp.com", "api.whatsapp.com",
            }:
                QDesktopServices.openUrl(url)
                return False
            return super().acceptNavigationRequest(url, nav_type, is_main_frame)
else:
    WebShellPage = None


class Sidebar(QFrame):
    def __init__(self, on_select, on_mode_change=None, menu_mode: str = "advanced", parent=None):
        super().__init__(parent)
        self.setProperty("role", "sidebar")
        self.setFixedWidth(286)
        self._on = on_select
        self._on_mode_change = on_mode_change
        self.menu_mode = _normalize_menu_mode(menu_mode)
        self._current_route = ""
        self.buttons = {}
        v = QVBoxLayout(self); v.setContentsMargins(12,12,12,10); v.setSpacing(10)
        head = QFrame()
        head.setProperty("role", "sidebarHead")
        head_lay = QVBoxLayout(head); head_lay.setContentsMargins(14,12,14,12); head_lay.setSpacing(7)
        brand = QLabel("YazKlinik"); brand.setProperty("role", "brand")
        head_lay.addWidget(brand)
        sub = QLabel(os.environ.get("YAZKLINIK_WEBSHELL_VERSION", "WebShell v3.0 - Final D104"))
        sub.setProperty("role", "muted")
        head_lay.addWidget(sub)
        mode_row = QHBoxLayout(); mode_row.setContentsMargins(0,4,0,0); mode_row.setSpacing(4)
        self._mode_group = QButtonGroup(self); self._mode_group.setExclusive(True)
        self.mode_buttons = {}
        for mode, label in MENU_MODE_LABELS.items():
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setMinimumHeight(36)
            btn.setToolTip(MENU_MODE_TOOLTIPS.get(mode, label))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setProperty("role", "mode")
            btn.setStyleSheet(_mode_button_style(False, mode))
            btn.clicked.connect(lambda _=False, m=mode: self.set_menu_mode(m, notify=True))
            self._mode_group.addButton(btn)
            self.mode_buttons[mode] = btn
            mode_row.addWidget(btn)
        head_lay.addLayout(mode_row)
        v.addWidget(head)
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;border:none;}")
        self.body = QFrame()
        self.inner = QVBoxLayout(self.body); self.inner.setContentsMargins(0,2,0,4); self.inner.setSpacing(5)
        self._group = None
        self.scroll.setWidget(self.body)
        v.addWidget(self.scroll, 1)
        self.set_menu_mode(self.menu_mode, notify=False)

    def _rebuild_nav(self):
        while self.inner.count():
            item = self.inner.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.buttons = {}
        self._group = QButtonGroup(self); self._group.setExclusive(True)
        for cat, items in nav_groups_for_mode(self.menu_mode):
            cat_text = _fix_mojibake_text(str(cat or ""))
            lbl = QLabel(cat_text); lbl.setProperty("role", "cat")
            self.inner.addWidget(lbl)
            for route, label, icon in items:
                label_text = _fix_mojibake_text(str(label or route))
                b = NavButton(label_text, icon, route=route)
                b.setProperty("role","nav"); b.setCheckable(True)
                b.clicked.connect(lambda _, r=route: self._on(r))
                self._group.addButton(b)
                self.buttons[route] = b
                self.inner.addWidget(b)
        self.inner.addStretch()
        if self._current_route:
            self.select(self._current_route)

    def set_menu_mode(self, mode: str, notify: bool = False):
        mode = _normalize_menu_mode(mode)
        self.menu_mode = mode
        for key, button in self.mode_buttons.items():
            active = key == mode
            button.setChecked(active)
            label = MENU_MODE_LABELS.get(key, key)
            button.setText(("✓ " if active else "") + label)
            button.setStyleSheet(_mode_button_style(active, key))
        self._rebuild_nav()
        if notify and self._on_mode_change:
            self._on_mode_change(mode)

    def select(self, route: str):
        self._current_route = route
        if route in self.buttons:
            self.buttons[route].setChecked(True)


class NavButton(QPushButton):
    def __init__(self, label: str, icon: str, parent=None, route: str = ""):
        super().__init__(parent)
        self.label = label
        self.route = str(route or "")
        self.icon_kind = _nav_visual_kind(self.route, label)
        self.icon_text = route_icon(self.route, fallback=icon) if self.route else _nav_badge(icon)
        self.legacy_badge = _nav_badge(icon)
        self.setText("")
        self.setToolTip(label)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(54)
        self.setCheckable(True)

    def _draw_icon(self, painter: QPainter, r, kind: str):
        white = QColor("#FFFFFF")
        soft = QColor(255, 255, 255, 205)
        pen = QPen(white, 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)

        x, y, w, h = r.left(), r.top(), r.width(), r.height()
        cx, cy = r.center().x(), r.center().y()

        if kind == "patient":
            painter.setBrush(QBrush(soft))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(x + 9, y + 8, 9, 9)
            painter.drawEllipse(x + 20, y + 10, 7, 7)
            painter.drawRoundedRect(x + 7, y + 22, 23, 8, 4, 4)
            return
        if kind == "search":
            painter.drawEllipse(x + 9, y + 9, 14, 14)
            painter.drawLine(x + 21, y + 22, x + 29, y + 29)
            return
        if kind == "calendar":
            painter.drawRoundedRect(x + 8, y + 8, 22, 22, 4, 4)
            painter.drawLine(x + 8, y + 15, x + 30, y + 15)
            painter.drawLine(x + 14, y + 6, x + 14, y + 11)
            painter.drawLine(x + 24, y + 6, x + 24, y + 11)
            painter.setPen(QPen(white, 3))
            painter.drawPoint(x + 15, y + 21)
            painter.drawPoint(x + 23, y + 21)
            return
        if kind in {"ob", "female"}:
            painter.drawEllipse(x + 12, y + 7, 14, 14)
            painter.drawLine(cx, y + 21, cx, y + 30)
            painter.drawLine(cx - 5, y + 26, cx + 5, y + 26)
            if kind == "ob":
                painter.setBrush(QBrush(soft))
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(x + 22, y + 22, 7, 7)
            return
        if kind == "risk":
            path = QPainterPath()
            path.moveTo(cx, y + 7)
            path.lineTo(x + 30, y + 29)
            path.lineTo(x + 8, y + 29)
            path.closeSubpath()
            painter.drawPath(path)
            painter.drawLine(cx, y + 15, cx, y + 22)
            painter.setPen(QPen(white, 3))
            painter.drawPoint(cx, y + 26)
            return
        if kind == "media":
            painter.drawRoundedRect(x + 7, y + 8, 24, 21, 4, 4)
            painter.drawLine(x + 10, y + 24, x + 16, y + 18)
            painter.drawLine(x + 16, y + 18, x + 21, y + 23)
            painter.drawLine(x + 20, y + 22, x + 27, y + 15)
            painter.drawEllipse(x + 23, y + 11, 4, 4)
            return
        if kind == "ai":
            painter.drawRoundedRect(x + 8, y + 11, 22, 18, 6, 6)
            painter.drawLine(cx, y + 7, cx, y + 11)
            painter.setPen(QPen(white, 3))
            painter.drawPoint(x + 15, y + 20)
            painter.drawPoint(x + 23, y + 20)
            painter.setPen(QPen(white, 2))
            painter.drawLine(x + 15, y + 25, x + 23, y + 25)
            return
        if kind == "task":
            painter.drawRoundedRect(x + 9, y + 8, 22, 22, 5, 5)
            painter.drawLine(x + 14, y + 20, x + 18, y + 24)
            painter.drawLine(x + 18, y + 24, x + 26, y + 15)
            return
        if kind == "chart":
            painter.drawLine(x + 9, y + 29, x + 30, y + 29)
            painter.drawLine(x + 10, y + 29, x + 10, y + 11)
            painter.drawLine(x + 14, y + 24, x + 18, y + 18)
            painter.drawLine(x + 18, y + 18, x + 23, y + 21)
            painter.drawLine(x + 23, y + 21, x + 29, y + 12)
            return
        if kind == "settings":
            painter.drawEllipse(x + 12, y + 12, 14, 14)
            painter.drawLine(cx, y + 7, cx, y + 12)
            painter.drawLine(cx, y + 26, cx, y + 31)
            painter.drawLine(x + 7, cy, x + 12, cy)
            painter.drawLine(x + 26, cy, x + 31, cy)
            return
        if kind == "storage":
            painter.drawRoundedRect(x + 9, y + 10, 21, 19, 5, 5)
            painter.drawLine(x + 12, y + 17, x + 27, y + 17)
            painter.setPen(QPen(white, 3))
            painter.drawPoint(x + 24, y + 24)
            return
        if kind == "flow":
            painter.drawLine(x + 13, y + 14, x + 25, y + 14)
            painter.drawLine(x + 19, y + 14, x + 19, y + 26)
            painter.drawLine(x + 13, y + 26, x + 25, y + 26)
            painter.setBrush(QBrush(soft))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(x + 9, y + 10, 8, 8)
            painter.drawEllipse(x + 22, y + 10, 8, 8)
            painter.drawEllipse(x + 15, y + 22, 8, 8)
            return
        if kind == "spark":
            painter.drawLine(cx, y + 7, cx, y + 31)
            painter.drawLine(x + 8, cy, x + 30, cy)
            painter.drawLine(x + 12, y + 12, x + 26, y + 26)
            painter.drawLine(x + 26, y + 12, x + 12, y + 26)
            return

        # Dashboard / fallback.
        painter.setBrush(QBrush(QColor(255, 255, 255, 185)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(x + 8, y + 8, 9, 9, 3, 3)
        painter.drawRoundedRect(x + 21, y + 8, 9, 9, 3, 3)
        painter.drawRoundedRect(x + 8, y + 21, 9, 9, 3, 3)
        painter.drawRoundedRect(x + 21, y + 21, 9, 9, 3, 3)

    def paintEvent(self, event):
        del event
        C = COLORS
        dark = QColor(C["bg"]).lightness() < 120
        checked = self.isChecked()
        hover = self.underMouse()
        rect = self.rect().adjusted(4, 3, -4, -3)
        accent_a, accent_b = _nav_palette_for_kind(self.icon_kind)

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if checked:
            bg1 = QColor("#F8FDFF") if not dark else QColor("#16384A")
            bg2 = QColor("#E6F8FF") if not dark else QColor("#0F2E45")
            border = QColor("#8BD8F7") if not dark else QColor("#3EA8D6")
            text_color = QColor("#0B2A44") if not dark else QColor("#F4FBFF")
        elif hover:
            bg1 = QColor("#FFFFFF") if not dark else QColor("#26313A")
            bg2 = QColor("#EDF9FF") if not dark else QColor("#1F2A34")
            border = QColor("#B8DFF1") if not dark else QColor("#3A4D5A")
            text_color = QColor(C["text"])
        else:
            bg1 = QColor(255, 255, 255, 210) if not dark else QColor("#252C34")
            bg2 = QColor(244, 251, 255, 170) if not dark else QColor("#20272F")
            border = QColor("#D7E8F2") if not dark else QColor("#303B45")
            text_color = QColor(C["text"])

        painter.setPen(border)
        card_grad = QLinearGradient(rect.left(), rect.top(), rect.right(), rect.bottom())
        card_grad.setColorAt(0.0, bg1)
        card_grad.setColorAt(1.0, bg2)
        painter.setBrush(QBrush(card_grad))
        painter.drawRoundedRect(rect, 12, 12)

        accent_grad = QLinearGradient(rect.left() + 10, rect.top(), rect.right() - 10, rect.top())
        accent_grad.setColorAt(0.0, QColor(accent_a))
        accent_grad.setColorAt(0.55, QColor(accent_b))
        accent_grad.setColorAt(1.0, QColor("#ec4899"))
        if checked or hover:
            painter.setPen(QPen(QBrush(accent_grad), 3))
            painter.drawLine(rect.left() + 14, rect.top() + 1, rect.right() - 14, rect.top() + 1)

        icon_size = 38
        icon_rect = rect.adjusted(
            10, (rect.height() - icon_size) // 2,
            -(rect.width() - 10 - icon_size),
            -((rect.height() - icon_size) // 2),
        )
        icon_grad = QLinearGradient(icon_rect.left(), icon_rect.top(), icon_rect.right(), icon_rect.bottom())
        icon_grad.setColorAt(0.0, QColor(accent_a))
        icon_grad.setColorAt(1.0, QColor(accent_b))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(icon_grad))
        painter.drawRoundedRect(icon_rect, 12, 12)
        self._draw_icon(painter, icon_rect, self.icon_kind)

        label_font = QFont(self.font())
        label_font.setPointSize(10)
        label_font.setBold(checked)
        painter.setFont(label_font)
        painter.setPen(text_color)
        text_x = icon_rect.right() + 12
        text_rect = rect.adjusted(text_x, 0, -12, 0)
        label = painter.fontMetrics().elidedText(self.label, Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)

        if checked:
            painter.setPen(QPen(QColor(accent_b), 2))
            mid = rect.center().y()
            painter.drawLine(rect.right() - 18, mid - 4, rect.right() - 12, mid)
            painter.drawLine(rect.right() - 12, mid, rect.right() - 18, mid + 4)


class Header(QFrame):
    def __init__(
        self, on_back, on_forward, on_reload, on_home, on_search, on_theme,
        on_open_browser, on_print, on_zoom_out, on_zoom_in, on_zoom_reset,
        on_fullscreen, parent=None):
        super().__init__(parent)
        self.setProperty("role","header"); self.setFixedHeight(54)
        h = QHBoxLayout(self); h.setContentsMargins(12,8,12,8); h.setSpacing(8)
        self.btn_back = QPushButton("<"); self.btn_back.setFixedSize(36,36); self.btn_back.clicked.connect(on_back)
        self.btn_fwd  = QPushButton(">"); self.btn_fwd.setFixedSize(36,36); self.btn_fwd.clicked.connect(on_forward)
        self.btn_rel  = QPushButton("R"); self.btn_rel.setFixedSize(36,36); self.btn_rel.clicked.connect(on_reload); self.btn_rel.setShortcut("F5")
        self.btn_home = QPushButton("H"); self.btn_home.setFixedSize(36,36); self.btn_home.clicked.connect(on_home)
        h.addWidget(self.btn_back); h.addWidget(self.btn_fwd); h.addWidget(self.btn_rel); h.addWidget(self.btn_home)
        self.btn_back.setToolTip("Geri")
        self.btn_fwd.setToolTip("Ileri")
        self.btn_rel.setToolTip("Yenile")
        self.btn_home.setToolTip("Ana sayfa")
        self.url = QLineEdit(); self.url.setMinimumHeight(34); self.url.setPlaceholderText("Rota, hasta veya sayfa...")
        h.addWidget(self.url, 1)
        self.btn_search = QPushButton("Ara (Ctrl+K)"); self.btn_search.clicked.connect(on_search)
        self.btn_search.setMinimumHeight(34); h.addWidget(self.btn_search)
        self.btn_print = QPushButton("P"); self.btn_print.setFixedSize(36,36)
        self.btn_print.clicked.connect(on_print); h.addWidget(self.btn_print)
        self.btn_zoom_out = QPushButton("-"); self.btn_zoom_out.setFixedSize(34,36)
        self.btn_zoom_out.clicked.connect(on_zoom_out); h.addWidget(self.btn_zoom_out)
        self.btn_zoom_reset = QPushButton("100"); self.btn_zoom_reset.setFixedSize(42,36)
        self.btn_zoom_reset.clicked.connect(on_zoom_reset); h.addWidget(self.btn_zoom_reset)
        self.btn_zoom_in = QPushButton("+"); self.btn_zoom_in.setFixedSize(34,36)
        self.btn_zoom_in.clicked.connect(on_zoom_in); h.addWidget(self.btn_zoom_in)
        self.btn_browser = QPushButton("O"); self.btn_browser.setFixedSize(36,36)
        self.btn_browser.clicked.connect(on_open_browser); h.addWidget(self.btn_browser)
        self.btn_full = QPushButton("[]"); self.btn_full.setFixedSize(36,36)
        self.btn_full.clicked.connect(on_fullscreen); h.addWidget(self.btn_full)
        self.btn_theme = QPushButton("T"); self.btn_theme.setFixedSize(36,36)
        self.btn_theme.clicked.connect(on_theme); h.addWidget(self.btn_theme)
        self.btn_print.setToolTip("Yazdir")
        self.btn_zoom_out.setToolTip("Kucult")
        self.btn_zoom_reset.setToolTip("Yakinlastirmayi sifirla")
        self.btn_zoom_in.setToolTip("Buyut")
        self.btn_browser.setToolTip("Tarayicida ac")
        self.btn_full.setToolTip("Tam ekran")
        self.btn_theme.setToolTip("Tema")
        self.user = QLabel(""); self.user.setProperty("role","muted"); h.addWidget(self.user)


class QuickSearch(QDialog):
    def __init__(self, on_select, parent=None, menu_mode: str = "advanced"):
        super().__init__(parent)
        self.setWindowTitle("Hizli Ara")
        self.setMinimumSize(560, 480); self.setModal(True)
        self._on_select = on_select
        self._menu_mode = _normalize_menu_mode(menu_mode)
        v = QVBoxLayout(self); v.setContentsMargins(20,20,20,20); v.setSpacing(10)
        v.addWidget(QLabel("Web sayfasi ara"))
        self.q = QLineEdit(); self.q.setPlaceholderText("dashboard, hasta..."); self.q.setMinimumHeight(40)
        self.q.textChanged.connect(self._refresh); self.q.returnPressed.connect(self._activate_first)
        v.addWidget(self.q)
        self.list = QListWidget(); self.list.itemClicked.connect(self._activate); self.list.itemActivated.connect(self._activate)
        v.addWidget(self.list, 1)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, self.close)
        self._refresh("")
    def _refresh(self, q):
        self.list.clear()
        ql = (q or "").lower()
        for route, label, icon, cat in all_routes(self._menu_mode):
            label_text = _fix_mojibake_text(str(label or ""))
            cat_text = _fix_mojibake_text(str(cat or ""))
            if not ql or ql in label_text.lower() or ql in route.lower() or ql in cat_text.lower():
                badge = route_icon(route, fallback=icon)
                it = QListWidgetItem(f"  {badge:<4}  {label_text}  -  {cat_text}")
                it.setData(Qt.ItemDataRole.UserRole, route)
                it.setToolTip(route)
                self.list.addItem(it)
        if self.list.count() > 0: self.list.setCurrentRow(0)
    def _activate_first(self):
        if self.list.count() > 0: self._activate(self.list.item(self.list.currentRow()))
    def _activate(self, it):
        if not it: return
        self._on_select(it.data(Qt.ItemDataRole.UserRole))
        self.accept()


class ShellWindow(QMainWindow):
    def __init__(self, server_url: str, parent=None):
        super().__init__(parent)
        self.server_url = server_url.rstrip("/")
        self._terminal_buffer = TerminalPcBuffer(self.server_url)
        self._desktop_restart_pending = False
        s = QSettings("YazKlinik","webshell")
        self._menu_mode = _normalize_menu_mode(s.value("menu_mode", "advanced"))
        self.setWindowTitle(os.environ.get("YAZKLINIK_WEBSHELL_VERSION", "YazKlinik WebShell v3.0 - Final D104"))
        self.resize(1500, 900); self.setMinimumSize(1100, 700)
        central = QWidget(); self.setCentralWidget(central)
        h = QHBoxLayout(central); h.setContentsMargins(0,0,0,0); h.setSpacing(0)
        self.sidebar = Sidebar(
            self._on_nav,
            on_mode_change=self._on_menu_mode_change,
            menu_mode=self._menu_mode)
        h.addWidget(self.sidebar)
        right = QFrame(); rv = QVBoxLayout(right); rv.setContentsMargins(0,0,0,0); rv.setSpacing(0)
        self.header = Header(
            self._back, self._forward, self._reload, self._home,
            self._search, self._toggle_theme, self._open_browser,
            self._print_current, self._zoom_out, self._zoom_in,
            self._zoom_reset, self._toggle_fullscreen)
        if _windows_terminal_accelerator_enabled():
            self.header.user.setProperty("role", "accelerator")
            self.header.user.setText("Windows Buffer AKTIF")
            self.header.user.setToolTip(
                "Terminal PC disk cache, GPU ve arka plan rota isitma aktif.")
        rv.addWidget(self.header)
        if HAS_WEB:
            self.view = QWebEngineView()
            if WebShellPage is not None:
                try:
                    self.view.setPage(WebShellPage(self.view))
                except Exception:
                    pass
            self._native_bridge = None
            self._web_channel = None
            if QWebChannel is not None:
                try:
                    self._native_bridge = WebShellNativeBridge(self)
                    self._web_channel = QWebChannel(self.view.page())
                    self._web_channel.registerObject(
                        "yazklinikNativeBridge", self._native_bridge)
                    self.view.page().setWebChannel(self._web_channel)
                except Exception:
                    self._native_bridge = None
                    self._web_channel = None
            _configure_web_profile(self.view, self.server_url)
            try:
                self.view.page().printRequested.connect(
                    lambda: _print_web_view_native(self.view, self))
            except Exception:
                pass
            try:
                self.view.page().profile().downloadRequested.connect(
                    self._handle_download)
            except Exception:
                pass
            self.view.urlChanged.connect(self._on_url_changed)
            self.view.loadFinished.connect(self._on_load_finished)
            rv.addWidget(self.view, 1)
        else:
            self.view = None
            err = QLabel("QtWebEngine yok. py -m pip install PySide6-Addons")
            err.setAlignment(Qt.AlignmentFlag.AlignCenter)
            err.setStyleSheet("padding:40px; color:#D13438;")
            rv.addWidget(err, 1)
        h.addWidget(right, 1)
        self.setStatusBar(QStatusBar())
        self.statusBar().showMessage(
            f"Server: {self.server_url}  .  Menu: {MENU_MODE_LABELS.get(self._menu_mode, 'Uzman')}  .  Ctrl+K hizli ara  .  Ctrl+J tema")
        QShortcut(QKeySequence("Ctrl+K"), self, self._search)
        QShortcut(QKeySequence("Ctrl+J"), self, self._toggle_theme)
        QShortcut(QKeySequence("Ctrl+L"), self, lambda: self.header.url.setFocus())
        QShortcut(QKeySequence("Ctrl+R"), self, self._reload)
        QShortcut(QKeySequence("Ctrl+P"), self, self._print_current)
        QShortcut(QKeySequence("Ctrl+H"), self, self._home)
        QShortcut(QKeySequence(QKeySequence.StandardKey.ZoomIn), self, self._zoom_in)
        QShortcut(QKeySequence(QKeySequence.StandardKey.ZoomOut), self, self._zoom_out)
        QShortcut(QKeySequence("Ctrl+0"), self, self._zoom_reset)
        QShortcut(QKeySequence("F11"), self, self._toggle_fullscreen)
        QShortcut(QKeySequence("Esc"), self, self._leave_fullscreen)
        QShortcut(QKeySequence("Alt+Left"), self, self._back)
        QShortcut(QKeySequence("Alt+Right"), self, self._forward)
        all_r = all_routes(self._menu_mode)
        for i, (route, _, _, _) in enumerate(all_r[:9], 1):
            QShortcut(QKeySequence(f"Ctrl+Alt+{i}"), self, lambda r=route: self.go(r))
        self.header.url.returnPressed.connect(self._url_submit)
        self._dark = bool(s.value("dark_mode", False, type=bool))
        start_route = os.environ.get("YAZKLINIK_DESKTOP_START_ROUTE", "/giris").strip() or "/giris"
        if _windows_terminal_accelerator_enabled():
            QTimer.singleShot(260, self._start_terminal_buffer)
        QTimer.singleShot(120, lambda r=start_route: self.go(r))
        QTimer.singleShot(900, self._show_feature_sync_status)

    def _handle_download(self, download):
        try:
            name = download.downloadFileName() or "YazKlinik-dosya"
        except Exception:
            name = "YazKlinik-dosya"
        downloads = Path.home() / "Downloads"
        suggested = str(downloads / name)
        try:
            target, _ = QFileDialog.getSaveFileName(
                self, "YazKlinik dosya kaydet", suggested)
        except Exception:
            target = suggested
        if not target:
            try:
                download.cancel()
            except Exception:
                pass
            return
        target_path = Path(target)
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            download.setDownloadDirectory(str(target_path.parent))
            download.setDownloadFileName(target_path.name)
            download.accept()
            self.statusBar().showMessage(
                f"Indirme basladi: {target_path.name}", 4000)
        except Exception as ex:
            try:
                download.cancel()
            except Exception:
                pass
            QMessageBox.warning(self, "Indirme", f"Dosya indirilemedi:\n{ex}")

    def go(self, route: str):
        if not self.view: return
        if not route.startswith("/"): route = "/" + route
        self._warm_terminal_buffer(route)
        url = self.server_url + route
        target = QUrl(_webshell_mark_internal_url(url, self.server_url))
        if self.view.url().toString().rstrip("/") != target.toString().rstrip("/"):
            self.view.setUrl(target)
        self.sidebar.select(route)
        self._set_address_route(route)
    def _on_nav(self, route): self.go(route)
    def _on_menu_mode_change(self, mode: str):
        self._menu_mode = _normalize_menu_mode(mode)
        QSettings("YazKlinik","webshell").setValue("menu_mode", self._menu_mode)
        self._sync_web_experience_mode()
        self.statusBar().showMessage(
            f"Hibrit menu modu: {MENU_MODE_LABELS.get(self._menu_mode, 'Uzman')}",
            3500)
    def _back(self):
        if self.view: self.view.back()
    def _forward(self):
        if self.view: self.view.forward()
    def _reload(self):
        if self.view: self.view.reload()
    def _print_current(self):
        _print_web_view_native(self.view, self)
    def _zoom_in(self):
        if not self.view:
            return
        z = min(2.0, float(self.view.zoomFactor() or 1.0) + 0.1)
        self.view.setZoomFactor(z)
        self.statusBar().showMessage(f"Zoom: {int(round(z * 100))}%", 1600)
    def _zoom_out(self):
        if not self.view:
            return
        z = max(0.7, float(self.view.zoomFactor() or 1.0) - 0.1)
        self.view.setZoomFactor(z)
        self.statusBar().showMessage(f"Zoom: {int(round(z * 100))}%", 1600)
    def _zoom_reset(self):
        if not self.view:
            return
        self.view.setZoomFactor(1.0)
        self.statusBar().showMessage("Zoom: 100%", 1600)
    def _toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.statusBar().showMessage("Pencere modu", 1600)
        else:
            self.showFullScreen()
            self.statusBar().showMessage("Tam ekran", 1600)
    def _leave_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
    def _home(self): self.go("/dashboard")
    def _open_browser(self):
        import webbrowser
        cur = _address_text_to_route(
            self.header.url.text(), self.header.url.property("actualRoute") or "")
        if cur.startswith("http://") or cur.startswith("https://"):
            webbrowser.open(cur)
        else:
            webbrowser.open(self.server_url + cur)
    def _on_url_changed(self, qurl):
        path = qurl.path() or "/"
        route = path
        if qurl.query():
            route += "?" + qurl.query()
        self._set_address_route(route)
        for route in self.sidebar.buttons:
            if route == path or (route != "/" and path.startswith(route)):
                self.sidebar.select(route); break
        self._maybe_apply_desktop_mode_url(qurl)

    def _maybe_apply_desktop_mode_url(self, qurl):
        if self._desktop_restart_pending:
            return
        try:
            query = urllib.parse.parse_qs(qurl.query() or "")
        except Exception:
            query = {}
        if (qurl.path() or "") != "/performans-ayarlari":
            return
        if str(query.get("desktop_restart", [""])[0]) != "1":
            return
        self._desktop_restart_pending = True
        QTimer.singleShot(700, self._apply_desktop_mode_from_server)

    def _apply_desktop_mode_from_server(self):
        mode = api_client.resolve_desktop_mode(self.server_url, default="hybrid")
        if mode in {"shell", "hybrid"}:
            os.environ.update(api_client.desktop_mode_env(mode, self.server_url))
            label = "Hibrit WebShell v3.0" if mode == "hybrid" else "WebShell"
            self.statusBar().showMessage(
                f"{label} modu aktif. Sol native menu ve orta web arayuz korunuyor.",
                5000)
            self._desktop_restart_pending = False
            return
        self.statusBar().showMessage(f"Masaustu {mode} modunda yeniden aciliyor...", 5000)
        if api_client.launch_desktop_mode(mode, self.server_url):
            QTimer.singleShot(700, QApplication.instance().quit)
        else:
            self._desktop_restart_pending = False
            QMessageBox.warning(
                self, "Masaustu modu",
                "Yeni masaustu modu baslatilamadi. Programi kapatip yeniden acin.")
    def _on_load_finished(self, ok):
        route = self.header.url.property("actualRoute") or self.header.url.text()
        self.statusBar().showMessage(f"Yuklendi: {self.server_url}{route}" if ok else "Yuklenemedi")
        if ok:
            self._apply_embedded_web_layout()
            self._apply_windows_accelerator()
            self._warm_terminal_buffer(str(route or ""))

    def _apply_embedded_web_layout(self):
        if not self.view:
            return
        try:
            page = self.view.page()
            page.runJavaScript(_WEBSHELL_NATIVE_BRIDGE_JS)
            page.runJavaScript(_WEBSHELL_EMBED_FIX_JS)
            QTimer.singleShot(60, lambda: page.runJavaScript(_WEBSHELL_NATIVE_BRIDGE_JS))
            QTimer.singleShot(80, lambda: page.runJavaScript(_WEBSHELL_EMBED_FIX_JS))
            QTimer.singleShot(300, lambda: page.runJavaScript(_WEBSHELL_NATIVE_BRIDGE_JS))
            QTimer.singleShot(350, lambda: page.runJavaScript(_WEBSHELL_EMBED_FIX_JS))
            self._sync_web_experience_mode()
        except Exception:
            pass

    def _apply_windows_accelerator(self):
        if not self.view or not _windows_terminal_accelerator_enabled():
            return
        try:
            page = self.view.page()
            page.runJavaScript(_WEBSHELL_WINDOWS_ACCELERATOR_JS)
            QTimer.singleShot(220, lambda: page.runJavaScript(_WEBSHELL_WINDOWS_ACCELERATOR_JS))
        except Exception:
            pass

    def _start_terminal_buffer(self):
        if not _windows_terminal_accelerator_enabled():
            return
        try:
            self._terminal_buffer.warm_start()
            self.statusBar().showMessage(
                "Windows Buffer aktif: cache, GPU ve rota isitma hazir.", 4500)
        except Exception:
            pass

    def _warm_terminal_buffer(self, route: str):
        if not _windows_terminal_accelerator_enabled():
            return
        try:
            self._terminal_buffer.warm_route(route)
        except Exception:
            pass

    def _sync_web_experience_mode(self):
        if not self.view:
            return
        mode = _normalize_menu_mode(getattr(self, "_menu_mode", "advanced"))
        js = (
            "(function(){try{"
            f"var mode={json.dumps(mode)};"
            "localStorage.setItem('ykExperienceMode', mode);"
            "document.documentElement.setAttribute('data-experience', mode);"
            "document.body && document.body.setAttribute('data-experience', mode);"
            "if (window.setExperienceMode) window.setExperienceMode(mode,{silent:true});"
            "window.dispatchEvent(new CustomEvent('yk:experience-mode',{detail:{mode:mode}}));"
            "}catch(e){}})();"
        )
        try:
            page = self.view.page()
            page.runJavaScript(js)
            QTimer.singleShot(180, lambda: page.runJavaScript(js))
        except Exception:
            pass

    def _show_feature_sync_status(self):
        payload = api_client.feature_manifest(self.server_url, timeout=1.2)
        if not payload:
            return
        try:
            route_count = int(payload.get("route_count") or 0)
        except Exception:
            route_count = 0
        digest = str(payload.get("hash") or "")[:8]
        self.statusBar().showMessage(
            f"Hibrit/Web senkron: {route_count} rota ({digest})", 5000)
    def _url_submit(self):
        t = _address_text_to_route(
            self.header.url.text(), self.header.url.property("actualRoute") or "")
        if not t: return
        if t.startswith("http://") or t.startswith("https://"):
            self.view.setUrl(QUrl(_webshell_mark_internal_url(t, self.server_url)))
        else: self.go(t)
    def _set_address_route(self, route: str):
        self.header.url.setProperty("actualRoute", route)
        self.header.url.setText(_address_route_label(route))
    def _search(self):
        dlg = QuickSearch(self.go, parent=self, menu_mode=self._menu_mode); dlg.exec()
    def _toggle_theme(self):
        from PySide6.QtWidgets import QApplication
        self._dark = not self._dark
        apply(QApplication.instance(), dark=self._dark)
        QSettings("YazKlinik","webshell").setValue("dark_mode", self._dark)
        self.statusBar().showMessage("Koyu" if self._dark else "Acik", 2000)



