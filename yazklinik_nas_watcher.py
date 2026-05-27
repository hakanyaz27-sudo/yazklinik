"""Lightweight NAS media watcher helpers for YazKlinik.

This module is intentionally conservative.  It keeps the web server startup
stable even when the configured NAS share is offline, and it provides the
patient-name extraction helper used by the NAS mapping screens.
"""

from __future__ import annotations

import os
import re
import threading
import time
import unicodedata
from pathlib import Path
from typing import Callable, Dict, Optional


_WATCHERS: Dict[str, dict] = {}
_WATCHERS_LOCK = threading.Lock()


_DATE_PATTERNS = (
    re.compile(r"(?<!\d)20\d{2}[-_. ]?\d{2}[-_. ]?\d{2}(?!\d)"),
    re.compile(r"(?<!\d)\d{2}[-_. ]?\d{2}[-_. ]?20\d{2}(?!\d)"),
    re.compile(r"(?<!\d)\d{8}(?:[_-]?\d{4,6})?(?!\d)"),
)


def _safe_text(value) -> str:
    if value is None:
        return ""
    text = str(value)
    try:
        from yazklinik_textfix import fix_mojibake_text

        text = fix_mojibake_text(text)
    except Exception:
        pass
    return text.strip()


def _ascii_fold(value: str) -> str:
    text = _safe_text(value)
    table = str.maketrans(
        {
            "ç": "c",
            "Ç": "C",
            "ğ": "g",
            "Ğ": "G",
            "ı": "i",
            "İ": "I",
            "ö": "o",
            "Ö": "O",
            "ş": "s",
            "Ş": "S",
            "ü": "u",
            "Ü": "U",
        }
    )
    text = text.translate(table)
    text = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in text if not unicodedata.combining(ch))


def _clean_tokens(parts) -> list:
    cleaned = []
    for part in parts:
        token = _safe_text(part).strip(" -_.()[]{}")
        if not token:
            continue
        folded = _ascii_fold(token).lower()
        if folded in {
            "img",
            "image",
            "jpeg",
            "jpg",
            "png",
            "mp4",
            "avi",
            "mov",
            "pdf",
            "rep",
            "report",
            "rapor",
            "gelis",
            "hasta",
            "usg",
            "dicom",
            "voluson",
            "expert",
            "demo",
            "sonolyst",
        }:
            continue
        if re.fullmatch(r"[A-Z]?\d+", token, flags=re.IGNORECASE):
            continue
        if re.fullmatch(r"[A-Z]\d{3,}.*", token, flags=re.IGNORECASE):
            continue
        cleaned.append(token)
    return cleaned


def extract_patient_name_from_filename(name: str) -> str:
    """Return a readable patient name from a NAS folder/file name.

    Examples:
    - F137230-26-04-08-1_Arslan_Hatice -> Hatice Arslan
    - 20260428_095305_Arslan_Hatice_IMG_1.jpg -> Hatice Arslan
    """

    raw = _safe_text(name)
    if not raw:
        return ""

    stem = Path(raw).stem
    stem = re.sub(r"^F\d+(?:[-_]\d+){2,5}[-_]*", "", stem, flags=re.IGNORECASE)
    stem = re.sub(r"\bF\d{5,}(?:[-_]\d+)*\b", " ", stem, flags=re.IGNORECASE)
    for pattern in _DATE_PATTERNS:
        stem = pattern.sub(" ", stem)
    stem = re.sub(r"\b(?:IMG|VID|MOV|MP4|JPEG|JPG|PNG|PDF)[-_ ]*\d*\b", " ", stem, flags=re.IGNORECASE)
    stem = re.sub(r"[_\-]+", " ", stem)
    stem = re.sub(r"\s+", " ", stem).strip()

    parts = _clean_tokens(stem.split())
    if not parts:
        return ""

    # Common NAS convention is Surname_Name after the protocol/date prefix.
    if len(parts) == 2:
        return f"{parts[1].title()} {parts[0].title()}".strip()
    if len(parts) == 3 and len(parts[0]) <= 2:
        return f"{parts[2].title()} {parts[1].title()}".strip()

    return " ".join(part.title() for part in parts).strip()


def _scan_once(folder: str, scan_callback: Optional[Callable] = None, **kwargs) -> dict:
    path = Path(folder)
    result = {"folder": str(path), "exists": path.exists(), "items": 0}
    if not path.exists() or not path.is_dir():
        return result

    items = []
    try:
        for child in path.iterdir():
            if child.name.startswith("."):
                continue
            items.append(
                {
                    "path": str(child),
                    "name": child.name,
                    "is_dir": child.is_dir(),
                    "patient_name": extract_patient_name_from_filename(child.name),
                }
            )
            if len(items) >= 200:
                break
    except Exception as exc:
        result["error"] = str(exc)
        return result

    result["items"] = len(items)
    if scan_callback:
        try:
            scan_callback(items, result=result, **kwargs)
        except TypeError:
            scan_callback(items)
        except Exception as exc:
            result["callback_error"] = str(exc)
    return result


def _watch_loop(key: str, folder: str, interval_seconds: float, kwargs: dict) -> None:
    while True:
        with _WATCHERS_LOCK:
            state = _WATCHERS.get(key)
            if not state or state.get("stop"):
                return
        try:
            summary = _scan_once(folder, **kwargs)
        except Exception as exc:
            summary = {"folder": folder, "error": str(exc)}
        with _WATCHERS_LOCK:
            state = _WATCHERS.get(key)
            if state is not None:
                state["last_scan"] = time.time()
                state["last_summary"] = summary
        time.sleep(max(float(interval_seconds or 10), 3.0))


def start_nas_watcher(
    watch_folder: str = "",
    db_conn_func: Optional[Callable] = None,
    data_root: Optional[str] = None,
    accepted_prefix: str = "F137230",
    interval_seconds: float = 15.0,
    scan_callback: Optional[Callable] = None,
    **kwargs,
) -> bool:
    """Start a background NAS watcher if the share is reachable.

    The function returns False instead of raising when the folder is missing or
    offline.  That keeps YazKlinik usable while the NAS is unavailable.
    """

    folder = _safe_text(watch_folder)
    if not folder:
        return False
    folder = os.path.abspath(folder)
    if not os.path.isdir(folder):
        return False

    key = os.path.normcase(folder)
    callback_kwargs = dict(kwargs)
    callback_kwargs.update(
        {
            "db_conn_func": db_conn_func,
            "data_root": data_root,
            "accepted_prefix": accepted_prefix,
            "scan_callback": scan_callback,
        }
    )

    with _WATCHERS_LOCK:
        existing = _WATCHERS.get(key)
        if existing and existing.get("thread") and existing["thread"].is_alive():
            return True
        thread = threading.Thread(
            target=_watch_loop,
            args=(key, folder, interval_seconds, callback_kwargs),
            name="YazKlinikNASWatcher",
            daemon=True,
        )
        _WATCHERS[key] = {
            "folder": folder,
            "started": time.time(),
            "stop": False,
            "thread": thread,
            "last_scan": None,
            "last_summary": None,
        }
        thread.start()
    return True


def stop_nas_watcher(watch_folder: Optional[str] = None) -> None:
    with _WATCHERS_LOCK:
        if watch_folder:
            key = os.path.normcase(os.path.abspath(_safe_text(watch_folder)))
            state = _WATCHERS.get(key)
            if state:
                state["stop"] = True
            return
        for state in _WATCHERS.values():
            state["stop"] = True


def watcher_status() -> dict:
    with _WATCHERS_LOCK:
        return {
            key: {
                "folder": state.get("folder"),
                "started": state.get("started"),
                "last_scan": state.get("last_scan"),
                "last_summary": state.get("last_summary"),
                "alive": bool(state.get("thread") and state["thread"].is_alive()),
            }
            for key, state in _WATCHERS.items()
        }
