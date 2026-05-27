"""MedGemma Klinik YZ ajani.

Bu modul import aninda agir ML kutuphanesi yuklemez. MedGemma sadece
acikca etkinlestirilirse ve kullanici istek atarsa yuklenir/cagirilir.

Guvenlik ilkesi:
- Varsayilan kapali gelir.
- Hasta verisini uzak endpoint'e gondermez; uzak endpoint icin ayrica
  YAZKLINIK_MEDGEMMA_ALLOW_REMOTE=1 gerekir.
- Cikti tani/tedavi emri degil, doktor onayli karar destek taslagidir.
"""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional


AGENT_VERSION = "2026.05.20-medgemma-bridge-v1"
DEFAULT_MODEL = "google/medgemma-4b-it"
DEFAULT_TEXT_MODEL = "google/medgemma-27b-text-it"
NEWER_FAST_MODEL = "google/medgemma-1.5-4b-it"
OLLAMA_DEFAULT_MODEL = "medgemma:27b"
OFFICIAL_MEDGEMMA_MODELS = [
    "google/medgemma-1.5-4b-it",
    "google/medgemma-4b-it",
    "google/medgemma-4b-pt",
    "google/medgemma-27b-text-it",
    "google/medgemma-27b-it",
]
TASK_MODEL_RECOMMENDATIONS = {
    "clinical_note": "google/medgemma-4b-it",
    "usg_pdf": "google/medgemma-27b-text-it",
    "lab_triage": "google/medgemma-27b-text-it",
    "red_flags": "google/medgemma-4b-it",
    "patient_summary": "google/medgemma-27b-text-it",
}
TASK_MODEL_RECOMMENDATION_NOTES = {
    "clinical_note": "Dengeli kalite ve hiz.",
    "usg_pdf": "Uzun metin/PDF yorumunda daha guclu kalite.",
    "lab_triage": "Tetkik triyajinda daha derin analiz.",
    "red_flags": "Acil risk taramasinda hizli ve net.",
    "patient_summary": "Detayli dosya ozetinde daha yuksek kalite.",
}
HF_TO_OLLAMA_MODEL_MAP = {
    "google/medgemma-27b-it": "medgemma:27b",
    "google/medgemma-27b-text-it": "medgemma:27b",
    "google/medgemma-4b-it": "medgemma:4b",
    "google/medgemma-4b-pt": "medgemma:4b",
    "google/medgemma-1.5-4b-it": "medgemma:4b",
}
TASK_ASSIGNMENT_RECOMMENDATIONS = {
    "clinical_note": {
        "title": "Klinik not duzenleme",
        "note": "Muayene notunu kisa, okunur ve doktor onayli taslaga cevirir.",
        "yz_definition": "Kadin dogum klinigi karar destek asistani. Kisa, net, doktor onayli yaz.",
        "assignment": "Klinik notu sorun listesi, takip plani ve doktor notu taslagi olarak duzenle.",
        "patient_context": "Rutin kontrol hastasi. Acil bulgu yoksa net sekilde belirt.",
    },
    "usg_pdf": {
        "title": "USG/PDF analiz",
        "note": "USG/PDF metninden GA/EDD ve takip ihtiyacini ayiklar.",
        "yz_definition": "Obstetrik USG raporlarinda olcum odakli karar destek asistani.",
        "assignment": "SAT bilinmiyorsa son USG/PDF olcumlerini referans alip GA/EDD taslagi ver; eksik veriyi listele.",
        "patient_context": "Gebelik takibi. Son rapor onceliklidir.",
    },
    "lab_triage": {
        "title": "Lab/tetkik triyaj",
        "note": "Tetkikleri oncelik seviyesine gore ayirir.",
        "yz_definition": "Laboratuvar triyajinda kirmizi bayraklari one cikar.",
        "assignment": "Anormal degerleri yuksek/orta/dusuk oncelik olarak sinifla ve takip adimi taslagi yaz.",
        "patient_context": "Tetkikler karisik gelebilir; acil riskleri ilk satira yaz.",
    },
    "red_flags": {
        "title": "Kirmizi alarm tarama",
        "note": "Acil obstetrik riskleri hizla yakalar.",
        "yz_definition": "Acil bulgu tarama asistani. Risk varsa ilk satirda net bildir.",
        "assignment": "Metindeki acil riskleri ayikla; acil yonlendirme gereken durumlari ustte yaz.",
        "patient_context": "Gebelik/obstetrik semptom taramasi.",
    },
    "patient_summary": {
        "title": "Hasta ozet taslagi",
        "note": "Dosya verisini hekim okumasina uygun tek ozete toplar.",
        "yz_definition": "Hasta dosyasi ozetleme asistani. Gereksiz tekrar yapma.",
        "assignment": "Hastanin gelislerini, kritik bulgularini ve planini kisa ozet halinde derle.",
        "patient_context": "Coklu gelis ve dosya icerigi olabilir.",
    },
}

_PIPE_CACHE: Dict[str, Any] = {}
_CONFIG_CACHE: Optional[Dict[str, str]] = None


@dataclass
class MedGemmaRequest:
    task: str = "clinical_note"
    note: str = ""
    patient_context: str = ""
    image_path: str = ""
    prefer_model: str = ""
    preview_only: bool = False


def _config_env() -> Dict[str, str]:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is not None:
        return dict(_CONFIG_CACHE)
    cfg: Dict[str, str] = {}
    try:
        path = Path(__file__).resolve().parent / "config.env"
        if path.exists():
            for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                cfg[key.strip()] = value.strip()
    except Exception:
        cfg = {}
    _CONFIG_CACHE = cfg
    return dict(cfg)


def _setting(key: str, default: str = "") -> str:
    env_value = os.environ.get(key)
    if env_value not in (None, ""):
        return str(env_value)
    return str(_config_env().get(key, default) or default)


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return default
    return text in {"1", "true", "yes", "on", "evet", "enabled", "active"}


def _module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except Exception:
        return False


def _hf_cache_exists(model_id: str) -> bool:
    model_id = str(model_id or "").strip()
    if not model_id or "/" not in model_id:
        return False
    folder = "models--" + model_id.replace("/", "--")
    candidates = [
        Path.home() / ".cache" / "huggingface" / "hub" / folder,
        Path(os.environ.get("HF_HOME", "")) / "hub" / folder if os.environ.get("HF_HOME") else None,
        Path(_setting("YAZKLINIK_HF_HOME", "")) / "hub" / folder if _setting("YAZKLINIK_HF_HOME", "") else None,
        Path(_setting("YAZKLINIK_HF_HOME", "")) / folder if _setting("YAZKLINIK_HF_HOME", "") else None,
    ]
    return any(p and p.exists() for p in candidates)


def _nvidia_summary() -> Dict[str, Any]:
    out: Dict[str, Any] = {"available": False}
    try:
        exe = "nvidia-smi"
        cmd = [
            exe,
            "--query-gpu=name,memory.total,driver_version",
            "--format=csv,noheader",
        ]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        if p.returncode == 0 and p.stdout.strip():
            first = p.stdout.strip().splitlines()[0]
            bits = [b.strip() for b in first.split(",")]
            out.update({
                "available": True,
                "name": bits[0] if len(bits) > 0 else "",
                "memory_total": bits[1] if len(bits) > 1 else "",
                "driver": bits[2] if len(bits) > 2 else "",
            })
    except Exception as exc:  # noqa: BLE001
        out["error"] = f"{type(exc).__name__}: {exc}"
    return out


def _is_local_endpoint(url: str) -> bool:
    text = str(url or "").strip()
    if not text:
        return True
    try:
        parsed = urllib.parse.urlparse(text)
        host = (parsed.hostname or "").lower()
        if host in {"localhost", "127.0.0.1", "::1"}:
            return True
        if host.startswith("192.168.") or host.startswith("10.") or host.startswith("172.16."):
            return True
        try:
            ip = socket.gethostbyname(host)
            return ip.startswith("127.") or ip.startswith("192.168.") or ip.startswith("10.")
        except Exception:
            return False
    except Exception:
        return False


def _endpoint_status(endpoint: str) -> Dict[str, Any]:
    endpoint = str(endpoint or "").strip()
    if not endpoint:
        return {"configured": False, "reachable": False}
    safe_local = _is_local_endpoint(endpoint)
    allow_remote = _as_bool(_setting("YAZKLINIK_MEDGEMMA_ALLOW_REMOTE", "0"))
    if not safe_local and not allow_remote:
        return {
            "configured": True,
            "reachable": False,
            "blocked": True,
            "reason": "remote_endpoint_blocked",
        }
    try:
        parsed = urllib.parse.urlparse(endpoint)
        base = endpoint
        if parsed.path.endswith("/v1/chat/completions"):
            base = endpoint[: -len("/v1/chat/completions")]
        models_url = base.rstrip("/") + "/v1/models"
        req = urllib.request.Request(models_url, headers={"User-Agent": "YazKlinik-MedGemma"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            ok = 200 <= int(resp.status) < 300
        return {"configured": True, "reachable": bool(ok), "blocked": False}
    except Exception as exc:  # noqa: BLE001
        return {
            "configured": True,
            "reachable": False,
            "blocked": False,
            "error": f"{type(exc).__name__}: {exc}",
        }


def _ollama_url_candidates() -> list[tuple[str, str]]:
    raw_values = [
        _setting("YAZKLINIK_OLLAMA_URL", ""),
        _setting("OLLAMA_HOST", ""),
        "http://127.0.0.1:11434",
        "http://localhost:11434",
    ]
    out: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for raw in raw_values:
        val = str(raw or "").strip()
        if not val:
            continue
        if val.endswith("/api/generate"):
            base = val[: -len("/api/generate")]
        elif "/api/" in val:
            base = val.split("/api/", 1)[0]
        else:
            base = val
        base = base.rstrip("/")
        if not base:
            continue
        if not (base.startswith("http://") or base.startswith("https://")):
            base = "http://" + base
        tags_url = base + "/api/tags"
        gen_url = base + "/api/generate"
        key = (tags_url, gen_url)
        if key not in seen:
            seen.add(key)
            out.append(key)
    return out


def _ollama_fetch_tags() -> Dict[str, Any]:
    last_error = ""
    for tags_url, gen_url in _ollama_url_candidates():
        try:
            req = urllib.request.Request(tags_url, headers={"User-Agent": "YazKlinik-MedGemma"})
            with urllib.request.urlopen(req, timeout=2.5) as resp:
                data = json.loads(resp.read().decode("utf-8", errors="replace"))
            models = []
            for row in (data.get("models") or []):
                name = str(row.get("name") or row.get("model") or "").strip()
                if name:
                    models.append(name)
            return {
                "online": True,
                "tags_url": tags_url,
                "generate_url": gen_url,
                "models": models,
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001
            last_error = f"{type(exc).__name__}: {exc}"
            continue
    return {
        "online": False,
        "tags_url": "",
        "generate_url": "",
        "models": [],
        "error": last_error,
    }


def _extract_ollama_medgemma_models(models: Any) -> list[str]:
    out: list[str] = []
    for raw in (models or []):
        name = str(raw or "").strip()
        if not name:
            continue
        if "medgemma" in name.lower():
            out.append(name)
    return out


def _resolve_ollama_model_name(prefer_model: str, installed_models: list[str]) -> str:
    installed = [str(m or "").strip() for m in (installed_models or []) if str(m or "").strip()]
    if not installed:
        mapped = HF_TO_OLLAMA_MODEL_MAP.get(str(prefer_model or "").strip().lower(), "")
        return mapped or str(prefer_model or "").strip() or OLLAMA_DEFAULT_MODEL
    by_lower = {m.lower(): m for m in installed}
    wanted = str(prefer_model or "").strip()
    if wanted and wanted.lower() in by_lower:
        return by_lower[wanted.lower()]
    mapped = HF_TO_OLLAMA_MODEL_MAP.get(wanted.lower(), "")
    if mapped and mapped.lower() in by_lower:
        return by_lower[mapped.lower()]
    medgemma_only = _extract_ollama_medgemma_models(installed)
    if medgemma_only:
        for probe in ("medgemma:27b", "medgemma:4b", "medgemma"):
            for item in medgemma_only:
                if probe in item.lower():
                    return item
        return medgemma_only[0]
    return installed[0]


def _ollama_generate(prompt: str, model: str, timeout_sec: int = 120) -> Dict[str, Any]:
    state = _ollama_fetch_tags()
    if not state.get("online"):
        return {
            "ok": False,
            "backend": "ollama",
            "error": state.get("error") or "ollama_offline",
            "model": model,
        }
    installed = list(state.get("models") or [])
    resolved_model = _resolve_ollama_model_name(model, installed)
    payload_obj = {
        "model": resolved_model,
        "prompt": str(prompt or ""),
        "stream": False,
        "options": {
            "temperature": 0.15,
            "num_predict": int(_setting("YAZKLINIK_MEDGEMMA_MAX_NEW_TOKENS", "512") or "512"),
        },
    }
    started = time.time()
    try:
        body = json.dumps(payload_obj, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            str(state.get("generate_url") or ""),
            data=body,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "YazKlinik-MedGemma",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=max(10, int(timeout_sec))) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
        data = json.loads(raw)
        answer = str(data.get("response") or "").strip()
        return {
            "ok": bool(answer),
            "backend": "ollama",
            "model": resolved_model,
            "model_requested": model,
            "answer": answer,
            "duration_ms": int((time.time() - started) * 1000),
            "ollama_generate_url": state.get("generate_url"),
        }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "backend": "ollama",
            "model": resolved_model,
            "model_requested": model,
            "error": f"{type(exc).__name__}: {exc}",
            "ollama_generate_url": state.get("generate_url"),
        }


def medgemma_config() -> Dict[str, Any]:
    endpoint = _setting("YAZKLINIK_MEDGEMMA_ENDPOINT", "")
    return {
        "enabled": _as_bool(_setting("YAZKLINIK_MEDGEMMA_ENABLED", "0")),
        "backend": _setting("YAZKLINIK_MEDGEMMA_BACKEND", "auto"),
        "model": _setting("YAZKLINIK_MEDGEMMA_MODEL", DEFAULT_MODEL),
        "text_model": _setting("YAZKLINIK_MEDGEMMA_TEXT_MODEL", DEFAULT_TEXT_MODEL),
        "newer_fast_model": _setting("YAZKLINIK_MEDGEMMA_FAST_MODEL", NEWER_FAST_MODEL),
        "endpoint": endpoint,
        "device": _setting("YAZKLINIK_MEDGEMMA_DEVICE", "auto"),
        "dtype": _setting("YAZKLINIK_MEDGEMMA_DTYPE", "auto"),
        "max_new_tokens": int(_setting("YAZKLINIK_MEDGEMMA_MAX_NEW_TOKENS", "512") or "512"),
        "remote_allowed": _as_bool(_setting("YAZKLINIK_MEDGEMMA_ALLOW_REMOTE", "0")),
        "load_on_demand": _as_bool(_setting("YAZKLINIK_MEDGEMMA_LOAD_ON_DEMAND", "1"), True),
    }


def task_model_recommendations() -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for task, model_id in TASK_MODEL_RECOMMENDATIONS.items():
        out[str(task)] = {
            "model": str(model_id),
            "note": str(TASK_MODEL_RECOMMENDATION_NOTES.get(task) or ""),
        }
    out["__image_default__"] = {
        "model": "google/medgemma-27b-it",
        "note": "Goruntu+metin talepleri icin oncelikli onerilen model.",
    }
    return out


def task_assignment_recommendations() -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for task, row in TASK_ASSIGNMENT_RECOMMENDATIONS.items():
        out[str(task)] = {
            "title": str(row.get("title") or ""),
            "note": str(row.get("note") or ""),
            "yz_definition": str(row.get("yz_definition") or ""),
            "assignment": str(row.get("assignment") or ""),
            "patient_context": str(row.get("patient_context") or ""),
        }
    return out


def recommended_model_for_task(task: str, has_image: bool = False) -> str:
    if has_image:
        return "google/medgemma-27b-it"
    key = str(task or "").strip().lower()
    return str(TASK_MODEL_RECOMMENDATIONS.get(key) or DEFAULT_MODEL)


def resolve_model_for_request(
    task: str,
    prefer_model: str,
    cfg: Dict[str, Any],
    has_image: bool = False,
) -> Dict[str, str]:
    user_choice = str(prefer_model or "").strip()
    if user_choice:
        return {"model": user_choice, "source": "user_override"}

    recommended = recommended_model_for_task(task=task, has_image=has_image)
    if _hf_cache_exists(recommended):
        return {"model": recommended, "source": "task_recommended"}

    fallback = str(cfg["model"] if has_image else cfg["text_model"])
    if _hf_cache_exists(fallback):
        return {"model": fallback, "source": "config_fallback"}

    return {"model": recommended, "source": "task_recommended_not_cached"}


def health_check() -> Dict[str, Any]:
    cfg = medgemma_config()
    deps = {
        "torch": _module_available("torch"),
        "transformers": _module_available("transformers"),
        "accelerate": _module_available("accelerate"),
        "huggingface_hub": _module_available("huggingface_hub"),
        "pillow": _module_available("PIL"),
    }
    models_to_check = []
    for model_id in [
        cfg["model"],
        cfg["text_model"],
        cfg["newer_fast_model"],
        *OFFICIAL_MEDGEMMA_MODELS,
    ]:
        model_text = str(model_id or "").strip()
        if model_text and model_text not in models_to_check:
            models_to_check.append(model_text)
    cached = {model_id: _hf_cache_exists(model_id) for model_id in models_to_check}
    endpoint = _endpoint_status(str(cfg.get("endpoint") or ""))
    ollama_state = _ollama_fetch_tags()
    ollama_medgemma_models = _extract_ollama_medgemma_models(ollama_state.get("models") or [])
    transformers_ready = all([deps["torch"], deps["transformers"], deps["pillow"]])
    local_model_ready = transformers_ready and any(cached.values())
    endpoint_ready = bool(endpoint.get("configured") and endpoint.get("reachable") and not endpoint.get("blocked"))
    ollama_ready = bool(ollama_state.get("online") and ollama_medgemma_models)
    backend_mode = str(cfg.get("backend") or "auto").strip().lower()
    ready = bool(cfg["enabled"] and (endpoint_ready or local_model_ready or ollama_ready))
    blockers = []
    if not cfg["enabled"]:
        blockers.append("YAZKLINIK_MEDGEMMA_ENABLED=0")
    if not endpoint_ready and not local_model_ready and not ollama_ready:
        blockers.append("model_or_endpoint_not_ready")
    if backend_mode == "ollama" and not ollama_ready:
        blockers.append("ollama_medgemma_not_ready")
    if endpoint.get("blocked"):
        blockers.append(str(endpoint.get("reason") or "endpoint_blocked"))
    return {
        "ok": True,
        "agent": "medgemma",
        "agent_version": AGENT_VERSION,
        "ready": ready,
        "blockers": blockers,
        "backend_mode": backend_mode,
        "endpoint_ready": endpoint_ready,
        "local_model_ready": local_model_ready,
        "ollama_ready": ollama_ready,
        "config": cfg,
        "dependencies": deps,
        "model_cache": cached,
        "installed_official_models": {
            model_id: cached.get(model_id, False)
            for model_id in OFFICIAL_MEDGEMMA_MODELS
        },
        "task_model_recommendations": task_model_recommendations(),
        "task_assignment_recommendations": task_assignment_recommendations(),
        "endpoint": endpoint,
        "ollama": {
            "online": bool(ollama_state.get("online")),
            "models": list(ollama_state.get("models") or []),
            "medgemma_models": ollama_medgemma_models,
            "generate_url": str(ollama_state.get("generate_url") or ""),
            "error": str(ollama_state.get("error") or ""),
        },
        "gpu": _nvidia_summary(),
        "terms_note": (
            "Hugging Face kullanimi icin Google Health AI Developer Foundations "
            "terms of use onayi ve gerekirse HF token gerekir."
        ),
        "install_hint": install_hint(),
    }


def install_hint() -> Dict[str, Any]:
    return {
        "steps": [
            "Hugging Face'te google/medgemma-4b-it model sayfasinda terms of use onayla.",
            "Bu PC'de: huggingface-cli login",
            "Opsiyonel paketler: pip install transformers accelerate huggingface_hub pillow",
            "CUDA Torch gerekiyorsa PyTorch sitesindeki Windows CUDA komutuyla torch kur.",
            "config.env icinde YAZKLINIK_MEDGEMMA_ENABLED=1 yap ve server restart et.",
        ],
        "models": [DEFAULT_MODEL, DEFAULT_TEXT_MODEL, NEWER_FAST_MODEL],
    }


def _task_instruction(task: str) -> str:
    task = str(task or "clinical_note").strip().lower()
    table = {
        "clinical_note": "Klinik notu duzenle, sorun listesi ve kontrol plani taslagi uret.",
        "usg_pdf": "USG/PDF metninden gebelik haftasi, olcumler, eksik veri ve takip onerisi taslagi cikar.",
        "lab_triage": "Laboratuvar/tetkik verisini anormal-deger, oncelik ve takip ihtiyaci olarak sinifla.",
        "red_flags": "Acil uyarilari ve doktora hemen gosterilecek riskleri ayikla.",
        "patient_summary": "Hasta dosyasi icin kisa, okunur, doktor onayli ozet taslagi uret.",
    }
    return table.get(task, table["clinical_note"])


def build_prompt(req: MedGemmaRequest) -> str:
    context = str(req.patient_context or "").strip()
    note = str(req.note or "").strip()
    task = str(req.task or "clinical_note").strip()
    return (
        "Sen YazKlinik icinde calisan MedGemma tabanli medikal uzman ajansin.\n"
        "Dil: Turkce. Rol: Op. Dr. Hakan YAZ icin karar destek taslagi.\n"
        "Kurallar:\n"
        "- Tani koyma ve tedavi emri verme; 'doktor onayi gerekir' diye belirt.\n"
        "- Hasta kimligini gereksiz tekrar etme.\n"
        "- Kirmizi alarm varsa ilk satirda yaz.\n"
        "- Belirsiz/veri eksikse uydurma; eksik bilgiyi sor.\n"
        "- Cevabi su basliklarla ver: Kirmizi alarm, Ozet, Bulgular, Onerilen kontrol, Eksik veri, Doktor notu taslagi.\n\n"
        f"Gorev: {_task_instruction(task)}\n\n"
        f"Hasta baglami:\n{context or '-'}\n\n"
        f"Girdi:\n{note or '-'}\n"
    )


def _endpoint_chat(prompt: str, model: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    endpoint = str(cfg.get("endpoint") or "").strip()
    if not endpoint:
        return {"ok": False, "error": "endpoint_not_configured"}
    if not _is_local_endpoint(endpoint) and not bool(cfg.get("remote_allowed")):
        return {"ok": False, "error": "remote_endpoint_blocked"}
    url = endpoint
    if not url.rstrip("/").endswith("/v1/chat/completions"):
        url = url.rstrip("/") + "/v1/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a medical decision-support assistant inside YazKlinik."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.15,
        "max_tokens": int(cfg.get("max_new_tokens") or 512),
    }
    data = json.dumps(body, ensure_ascii=True).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={"Content-Type": "application/json", "User-Agent": "YazKlinik-MedGemma"},
    )
    try:
        started = time.time()
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        answer = (((payload.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
        return {
            "ok": bool(answer),
            "backend": "openai_compatible_endpoint",
            "model": model,
            "answer": answer,
            "duration_ms": int((time.time() - started) * 1000),
            "raw": payload if not answer else None,
        }
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        return {"ok": False, "backend": "openai_compatible_endpoint", "error": f"HTTP {exc.code}: {detail}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "backend": "openai_compatible_endpoint", "error": f"{type(exc).__name__}: {exc}"}


def _transformers_generate(prompt: str, req: MedGemmaRequest, model: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    hf_home = _setting("YAZKLINIK_HF_HOME", "")
    if hf_home and not os.environ.get("HF_HOME"):
        os.environ["HF_HOME"] = hf_home
    try:
        import torch  # type: ignore
        from transformers import pipeline  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "backend": "transformers", "error": f"dependency_missing: {exc}"}

    has_image = bool(str(req.image_path or "").strip())
    task_name = "image-text-to-text" if has_image and "text" not in model.lower() else "text-generation"
    cache_key = f"{task_name}:{model}"
    try:
        pipe = _PIPE_CACHE.get(cache_key)
        if pipe is None:
            dtype_setting = str(cfg.get("dtype") or "auto").lower()
            dtype = "auto"
            if dtype_setting in {"bf16", "bfloat16"}:
                dtype = torch.bfloat16
            elif dtype_setting in {"fp16", "float16"}:
                dtype = torch.float16
            kwargs: Dict[str, Any] = {"model": model, "torch_dtype": dtype}
            device = str(cfg.get("device") or "auto").lower()
            if device == "cuda" or (device == "auto" and torch.cuda.is_available()):
                kwargs["device"] = 0
            pipe = pipeline(task_name, **kwargs)
            _PIPE_CACHE[cache_key] = pipe
        started = time.time()
        if has_image:
            from PIL import Image  # type: ignore
            image = Image.open(str(req.image_path))
            result = pipe(images=image, text=prompt, max_new_tokens=int(cfg.get("max_new_tokens") or 512))
        else:
            result = pipe(prompt, max_new_tokens=int(cfg.get("max_new_tokens") or 512), do_sample=False)
        answer = ""
        if isinstance(result, list) and result:
            item = result[0]
            if isinstance(item, dict):
                answer = str(item.get("generated_text") or item.get("text") or item.get("answer") or "")
            else:
                answer = str(item)
        else:
            answer = str(result or "")
        if answer.startswith(prompt):
            answer = answer[len(prompt):].strip()
        return {
            "ok": bool(answer.strip()),
            "backend": "transformers",
            "task": task_name,
            "model": model,
            "answer": answer.strip(),
            "duration_ms": int((time.time() - started) * 1000),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "backend": "transformers", "model": model, "error": f"{type(exc).__name__}: {exc}"}


def analyze(req: MedGemmaRequest | Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(req, dict):
        req = MedGemmaRequest(**{k: v for k, v in req.items() if k in MedGemmaRequest.__annotations__})
    cfg = medgemma_config()
    prompt = build_prompt(req)
    if req.preview_only:
        return {
            "ok": True,
            "agent": "medgemma",
            "preview_only": True,
            "prompt": prompt,
            "config": cfg,
        }
    status = health_check()
    if not cfg.get("enabled"):
        return {
            "ok": False,
            "agent": "medgemma",
            "error": "disabled",
            "message": "MedGemma baglantisi hazir; etkinlestirmek icin config.env icinde YAZKLINIK_MEDGEMMA_ENABLED=1 yapin.",
            "prompt": prompt,
            "status": status,
        }
    model_pick = resolve_model_for_request(
        task=req.task,
        prefer_model=req.prefer_model,
        cfg=cfg,
        has_image=bool(req.image_path),
    )
    model = str(model_pick.get("model") or "")
    backend_mode = str(cfg.get("backend") or "auto").strip().lower()
    endpoint_ready = bool(status.get("endpoint_ready"))
    local_model_ready = bool(status.get("local_model_ready"))
    ollama_ready = bool(status.get("ollama_ready"))

    if backend_mode == "ollama":
        backend_order = ["ollama", "endpoint", "transformers"]
    elif backend_mode in {"endpoint", "openai_compat"}:
        backend_order = ["endpoint", "ollama", "transformers"]
    elif backend_mode == "transformers":
        backend_order = ["transformers", "ollama", "endpoint"]
    else:
        backend_order = ["endpoint", "transformers", "ollama"]

    out = {
        "ok": False,
        "backend": backend_mode or "auto",
        "error": "no_backend_attempted",
        "model": model,
    }
    attempts = []
    seen_backends = set()
    for backend in backend_order:
        if backend in seen_backends:
            continue
        seen_backends.add(backend)
        if backend == "endpoint" and not endpoint_ready:
            attempts.append({
                "backend": "openai_compatible_endpoint",
                "ok": False,
                "error": "endpoint_not_ready",
            })
            continue
        if backend == "transformers" and not local_model_ready:
            attempts.append({
                "backend": "transformers",
                "ok": False,
                "error": "local_model_not_ready",
            })
            continue
        if backend == "ollama" and not ollama_ready:
            attempts.append({
                "backend": "ollama",
                "ok": False,
                "error": "ollama_medgemma_not_ready",
            })
            continue

        if backend == "endpoint":
            candidate = _endpoint_chat(prompt, model=model, cfg=cfg)
        elif backend == "transformers":
            candidate = _transformers_generate(prompt, req=req, model=model, cfg=cfg)
        elif backend == "ollama":
            candidate = _ollama_generate(prompt, model=model)
        else:
            continue
        attempts.append({
            "backend": str(candidate.get("backend") or backend),
            "ok": bool(candidate.get("ok")),
            "model": str(candidate.get("model") or model),
            "error": str(candidate.get("error") or ""),
        })
        out = candidate
        if out.get("ok"):
            break
    out.update({
        "agent": "medgemma",
        "task": req.task,
        "backend_attempts": attempts,
        "model_resolution": model_pick,
        "task_model_recommendations": task_model_recommendations(),
        "task_assignment_recommendations": task_assignment_recommendations(),
        "requires_doctor_review": True,
        "prompt_preview": prompt[:1000],
        "request": asdict(req),
    })
    if out.get("ok"):
        out["safety_note"] = "Bu cikti karar destek taslagidir; tani/tedavi karari hekime aittir."
    else:
        out["status"] = status
    return out


if __name__ == "__main__":
    print(json.dumps(health_check(), ensure_ascii=False, indent=2))
