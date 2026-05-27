"""Shared YazKlinik helpers used by web, desktop and terminal shells."""

from __future__ import annotations

import copy
import json
import os
import re
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Mapping


_LOCK = threading.RLock()
_PATIENT_KEY_RE = re.compile(r"^[A-Za-z]?\d+(?:[-_\s]\d+){3,}[-_\s]+(?P<name>.+)$")
_SPACES_RE = re.compile(r"\s+")


def _base_dir() -> Path:
    return Path(__file__).resolve().parent


def _settings_path() -> Path:
    raw = os.environ.get("YAZKLINIK_SETTINGS_PATH", "").strip()
    return Path(raw) if raw else _base_dir() / "yazklinik_settings.json"


def _active_patient_path() -> Path:
    raw = os.environ.get("YAZKLINIK_ACTIVE_PATIENT_PATH", "").strip()
    return Path(raw) if raw else _base_dir() / "active_patient.json"


def _load_runtime_config() -> Dict[str, str]:
    try:
        from yazklinik_config import load_config

        cfg = load_config()
        return {str(k): str(v) for k, v in cfg.items() if v is not None}
    except Exception:
        return {}


def _cfg(key: str, fallback: str) -> str:
    cfg = _load_runtime_config()
    value = os.environ.get(f"YAZKLINIK_{key.upper()}", "") or cfg.get(key, "")
    return str(value or fallback)


DEFAULT_SETTINGS: Dict[str, Any] = {
    "version": 2,
    "integrations": {
        "usg_nas": {
            "enabled": True,
            "name": "USG NAS Klasoru",
            "icon": "USG",
            "description": "NAS uzerindeki USG medya klasorlerini hasta kayitlarina baglar.",
            "config": {
                "watch_folder": r"\\Sam\usg\Hastalar",
                "data_root": r"\\Sam\usg\Hastalar",
                "accepted_prefix": "F137230",
                "multimedia_root": r"E:\USG\Multimedia",
            },
        },
        "dicom_orthanc": {
            "enabled": True,
            "name": "DICOM / Orthanc",
            "icon": "DICOM",
            "description": "Orthanc, Voluson worklist ve DICOM senkron katmani.",
            "config": {
                "orthanc_url": "http://127.0.0.1:8042",
                "orthanc_user": "",
                "orthanc_pass": "",
                "dicom_aet": "ORTHANC",
                "orthanc_aet": "ORTHANC",
                "voluson_aet": "VOLUSON",
                "dicom_port": "4242",
                "orthanc_dicom_port": "4242",
                "orthanc_allow_find": "1",
                "orthanc_allow_find_worklist": "1",
                "orthanc_config_required_flags": (
                    "DicomAlwaysAllowFind=true; "
                    "DicomAlwaysAllowFindWorklist=true"
                ),
                "voluson_worklist_server_aet": "ORTHANC",
                "voluson_worklist_server_ip": "192.168.1.148",
                "voluson_worklist_server_port": "4242",
                "voluson_worklist_tls": "Kapali",
            },
        },
        "ollama": {
            "enabled": True,
            "name": "Ollama Yerel YZ",
            "icon": "YZ",
            "description": "Yerel akilli asistan, sohbet ve rapor yardimcisi.",
            "config": {
                "url": "http://localhost:11434/api/generate",
                "provider": "auto",
            },
        },
        "openai": {
            "enabled": False,
            "name": "Online ChatGPT",
            "icon": "AI",
            "description": "Istek uzerine bulut YZ baglantisi.",
            "config": {
                "base_url": "https://api.openai.com/v1/responses",
                "model": "gpt-5.4-mini",
                "timeout": "60",
            },
        },
        "comfyui": {
            "enabled": True,
            "name": "ComfyUI HD Studio",
            "icon": "HD",
            "description": "HD Studio goruntu iyilestirme ve sunum is akislari.",
            "config": {
                "url": "http://127.0.0.1:8188",
                "checkpoint": "RealVisXL_V5.0_fp16.safetensors",
                "upscale_model": "RealESRGAN_x4plus.pth",
            },
        },
        "paths": {
            "enabled": True,
            "name": "YazKlinik Klasorleri",
            "icon": "PATH",
            "description": "Veritabani, cikti, yedek ve multimedia klasorleri.",
            "config": {
                "db_root": r"\\Sam\usg\DATABASE",
                "multimedia_root": r"E:\USG\Multimedia",
                "temp_dir": "E:\\USG\\\u00c7\u0131kt\u0131lar",
                "export_root": "E:\\USG\\\u00c7\u0131kt\u0131lar",
                "backup_root": r"E:\USG\Backup",
            },
        },
    },
}


def _runtime_default_settings() -> Dict[str, Any]:
    settings = copy.deepcopy(DEFAULT_SETTINGS)
    cfg = _load_runtime_config()
    integrations = settings["integrations"]

    integrations["usg_nas"]["config"].update(
        {
            "watch_folder": cfg.get("nas_root") or cfg.get("data_root") or r"\\Sam\usg\Hastalar",
            "data_root": cfg.get("data_root") or cfg.get("nas_root") or r"\\Sam\usg\Hastalar",
            "multimedia_root": cfg.get("multimedia_root") or r"E:\USG\Multimedia",
        }
    )
    integrations["dicom_orthanc"]["config"].update(
        {
            "orthanc_url": cfg.get("orthanc_url") or "http://127.0.0.1:8042",
            "orthanc_user": cfg.get("orthanc_user") or "",
            "orthanc_pass": cfg.get("orthanc_pass") or "",
            "dicom_aet": cfg.get("orthanc_aet") or "ORTHANC",
            "orthanc_aet": cfg.get("orthanc_aet") or "ORTHANC",
            "voluson_aet": cfg.get("voluson_aet") or "VOLUSON",
            "dicom_port": cfg.get("orthanc_dicom_port") or "4242",
            "orthanc_dicom_port": cfg.get("orthanc_dicom_port") or "4242",
            "orthanc_allow_find": cfg.get("orthanc_allow_find") or "1",
            "orthanc_allow_find_worklist": cfg.get("orthanc_allow_find_worklist") or "1",
            "voluson_worklist_server_aet": cfg.get("orthanc_aet") or "ORTHANC",
            "voluson_worklist_server_ip": cfg.get("orthanc_host") or "192.168.1.148",
            "voluson_worklist_server_port": cfg.get("orthanc_dicom_port") or "4242",
        }
    )
    integrations["ollama"]["config"].update(
        {
            "url": cfg.get("ollama_url") or "http://localhost:11434/api/generate",
            "provider": cfg.get("ai_provider") or "auto",
        }
    )
    integrations["openai"]["config"].update(
        {
            "base_url": cfg.get("openai_base_url") or "https://api.openai.com/v1/responses",
            "model": cfg.get("openai_model") or "gpt-5.4-mini",
            "timeout": cfg.get("openai_timeout") or "60",
        }
    )
    integrations["paths"]["config"].update(
        {
            "db_root": cfg.get("db_root") or r"\\Sam\usg\DATABASE",
            "multimedia_root": cfg.get("multimedia_root") or r"E:\USG\Multimedia",
            "temp_dir": cfg.get("temp_dir") or "E:\\USG\\\u00c7\u0131kt\u0131lar",
            "export_root": cfg.get("export_root") or "E:\\USG\\\u00c7\u0131kt\u0131lar",
            "backup_root": cfg.get("backup_root") or r"E:\USG\Backup",
        }
    )
    return settings


def _deep_merge(defaults: Mapping[str, Any], override: Mapping[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = copy.deepcopy(dict(defaults))
    for key, value in dict(override).items():
        if isinstance(value, Mapping) and isinstance(merged.get(key), Mapping):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _read_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_json(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_settings() -> Dict[str, Any]:
    """Load integration settings with current defaults filled in."""
    with _LOCK:
        settings = _deep_merge(_runtime_default_settings(), _read_json(_settings_path()))
        save_settings(settings)
        return settings


def save_settings(settings: Mapping[str, Any]) -> Path:
    """Persist integration settings and return the settings file path."""
    with _LOCK:
        merged = _deep_merge(_runtime_default_settings(), settings if isinstance(settings, Mapping) else {})
        _write_json(_settings_path(), merged)
        return _settings_path()


def get_integration_config(name: str) -> Dict[str, Any]:
    settings = load_settings()
    integ = settings.get("integrations", {}).get(str(name), {})
    config = integ.get("config", {})
    return copy.deepcopy(config) if isinstance(config, dict) else {}


def is_integration_enabled(name: str) -> bool:
    settings = load_settings()
    return bool(settings.get("integrations", {}).get(str(name), {}).get("enabled", False))


def set_integration_enabled(name: str, enabled: bool) -> Dict[str, Any]:
    settings = load_settings()
    integrations = settings.setdefault("integrations", {})
    item = integrations.setdefault(str(name), {"name": str(name), "config": {}, "custom": True})
    item["enabled"] = bool(enabled)
    save_settings(settings)
    return settings


def clean_patient_name(value: Any) -> str:
    """Turn technical folder keys into a patient-facing display name.

    Example: F137230-26-04-08-1_Arslan_Hatice -> Hatice Arslan
    """
    raw = str(value or "").strip().strip("\\/")
    if not raw:
        return ""

    raw = Path(raw).name if ("\\" in raw or "/" in raw) else raw
    raw = raw.strip()
    from_key = False

    match = _PATIENT_KEY_RE.match(raw)
    if match:
        raw = match.group("name")
        from_key = True

    raw = raw.replace("_", " ")
    raw = raw.replace(".", " ")
    raw = _SPACES_RE.sub(" ", raw).strip(" -_")
    raw = re.sub(r"^\d{2}\s+\d{2}\s+\d{2}\s+\d+\s+", "", raw).strip()
    if not raw:
        return ""

    parts = [part for part in raw.split(" ") if part]
    if from_key and len(parts) >= 2:
        parts = parts[1:] + parts[:1]
    return " ".join(parts)


def set_active_patient(patient_key: str, display_name: str = "", source: str = "manual") -> Dict[str, Any]:
    patient_key = str(patient_key or "").strip()
    source = str(source or "manual")
    updated_at = datetime.now().isoformat(timespec="seconds")
    if not patient_key:
        payload = {
            "patient_key": "",
            "display_name": "",
            "source": source,
            "updated_at": updated_at,
            "empty": True,
        }
        with _LOCK:
            path = _active_patient_path()
            if path.exists():
                path.unlink()
        return payload
    display_name = clean_patient_name(display_name) or clean_patient_name(patient_key) or patient_key
    payload = {
        "patient_key": patient_key,
        "display_name": display_name,
        "source": source,
        "updated_at": updated_at,
    }
    with _LOCK:
        _write_json(_active_patient_path(), payload)
    return payload


def get_active_patient() -> Dict[str, Any]:
    with _LOCK:
        payload = _read_json(_active_patient_path())
    if not isinstance(payload, dict):
        return {}
    patient_key = str(payload.get("patient_key") or "").strip()
    if not patient_key:
        try:
            clear_active_patient()
        except Exception:
            pass
        return {}
    payload["patient_key"] = patient_key
    payload["display_name"] = (
        clean_patient_name(payload.get("display_name"))
        or clean_patient_name(patient_key)
        or patient_key
    )
    payload["source"] = str(payload.get("source") or "manual")
    return payload


def clear_active_patient() -> None:
    with _LOCK:
        path = _active_patient_path()
        if path.exists():
            path.unlink()
