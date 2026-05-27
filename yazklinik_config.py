import json
import os
from pathlib import Path


DEFAULT_CONFIG_NAME = "yazklinik_config.json"

DEFAULT_CONFIG = {
    "role": "server",
    "web_port": "5443",
    "https_port": "5443",
    "enable_https": "1",
    "https_hosts": "localhost,127.0.0.1,192.168.1.50,176.236.92.142",
    "server_engine": "waitress",
    "waitress_threads": "auto",
    "nas_root": r"\\Sam\usg\Hastalar",
    "data_root": r"\\Sam\usg\Hastalar",
    "db_root": r"\\Sam\usg\DATABASE",
    "db_path": r"\\Sam\usg\DATABASE\yazklinik_v68.sqlite3",
    "multimedia_root": r"E:\USG\Multimedia",
    "temp_dir": r"E:\USG\Çıktılar",
    "export_root": r"E:\USG\Çıktılar",
    "backup_root": r"E:\USG\Backup",
    "orthanc_host": "127.0.0.1",
    "orthanc_port": "8042",
    "orthanc_url": "http://127.0.0.1:8042",
    "orthanc_user": "",
    "orthanc_pass": "",
    "orthanc_dicom_port": "4242",
    "orthanc_aet": "ORTHANC",
    "voluson_aet": "VOLUSON",
    "orthanc_allow_find": "1",
    "orthanc_allow_find_worklist": "1",
    "ollama_url": "http://localhost:11434/api/generate",
    "ollama_model": "llama3.1:8b",
    "ollama_model_mode": "auto",
    "ai_provider": "auto",
    "hardware_auto": "1",
    "media_ram_cache_gb": "auto",
    "media_ram_cache_max_file_mb": "auto",
    "ram_reserve_gb": "auto",
    "program_ram_cache_mb": "auto",
    "program_ram_cache_prewarm": "1",
    "gpu_auto": "1",
    "gpu_profile": "auto",
    "ollama_ctx_limit": "3072",
    "ollama_num_batch": "256",
    "ollama_num_gpu": "auto",
    "ollama_num_parallel": "1",
    "ollama_keep_alive": "10m",
    "whisper_model": "small",
    "whisper_device": "auto",
    "whisper_compute_type": "auto",
    "comfyui_gpu_args": "--lowvram --fp16",
    "openai_api_key": "",
    "openai_model": "gpt-5.4-mini",
    "openai_base_url": "https://api.openai.com/v1/responses",
    "openai_timeout": "60",
    "terminal_token": "",
    "server_url": "https://192.168.1.50:5443",
    "https_url": "https://192.168.1.50:5443",
    "smart_assistant": "1",
    "smart_assistant_quiet": "1",
    "bulutklinik_portal_url": "https://app.bulutklinik.com/App/My/favorites.gg",
    "enabiz_doctor_portal_url": "https://enabiz.gov.tr/DoktorErisim/home/KisiDogrula",
}

ENV_MAP = {
    "web_port": "YAZKLINIK_WEB_PORT",
    "https_port": "YAZKLINIK_HTTPS_PORT",
    "enable_https": "YAZKLINIK_ENABLE_HTTPS",
    "https_hosts": "YAZKLINIK_HTTPS_HOSTS",
    "server_engine": "YAZKLINIK_SERVER_ENGINE",
    "waitress_threads": "YAZKLINIK_WAITRESS_THREADS",
    "nas_root": "YAZKLINIK_NAS_ROOT",
    "data_root": "YAZKLINIK_DATA_ROOT",
    "db_root": "YAZKLINIK_DB_ROOT",
    "db_path": "YAZKLINIK_DB_PATH",
    "multimedia_root": "YAZKLINIK_MULTIMEDIA_ROOT",
    "temp_dir": "YAZKLINIK_TEMP_DIR",
    "export_root": "YAZKLINIK_EXPORT_ROOT",
    "backup_root": "YAZKLINIK_BACKUP_ROOT",
    "orthanc_host": "YAZKLINIK_ORTHANC_HOST",
    "orthanc_port": "YAZKLINIK_ORTHANC_PORT",
    "orthanc_url": "YAZKLINIK_ORTHANC_URL",
    "orthanc_user": "YAZKLINIK_ORTHANC_USER",
    "orthanc_pass": "YAZKLINIK_ORTHANC_PASS",
    "orthanc_dicom_port": "YAZKLINIK_ORTHANC_DICOM_PORT",
    "orthanc_aet": "YAZKLINIK_ORTHANC_AET",
    "voluson_aet": "YAZKLINIK_VOLUSON_AET",
    "orthanc_allow_find": "YAZKLINIK_ORTHANC_ALLOW_FIND",
    "orthanc_allow_find_worklist": "YAZKLINIK_ORTHANC_ALLOW_FIND_WORKLIST",
    "ollama_url": "YAZKLINIK_OLLAMA_URL",
    "ollama_model": "YAZKLINIK_OLLAMA_MODEL",
    "ollama_model_mode": "YAZKLINIK_OLLAMA_MODEL_MODE",
    "ai_provider": "YAZKLINIK_AI_PROVIDER",
    "hardware_auto": "YAZKLINIK_HARDWARE_AUTO",
    "media_ram_cache_gb": "YAZKLINIK_MEDIA_RAM_CACHE_GB",
    "media_ram_cache_max_file_mb": "YAZKLINIK_MEDIA_RAM_CACHE_MAX_FILE_MB",
    "ram_reserve_gb": "YAZKLINIK_RAM_RESERVE_GB",
    "program_ram_cache_mb": "YAZKLINIK_PROGRAM_RAM_CACHE_MB",
    "program_ram_cache_prewarm": "YAZKLINIK_PROGRAM_RAM_CACHE_PREWARM_ON_REQUEST",
    "gpu_auto": "YAZKLINIK_GPU_AUTO",
    "gpu_profile": "YAZKLINIK_GPU_PROFILE",
    "ollama_ctx_limit": "YAZKLINIK_OLLAMA_CTX_LIMIT",
    "ollama_num_batch": "YAZKLINIK_OLLAMA_NUM_BATCH",
    "ollama_num_gpu": "YAZKLINIK_OLLAMA_NUM_GPU",
    "ollama_num_parallel": "YAZKLINIK_OLLAMA_NUM_PARALLEL",
    "ollama_keep_alive": "YAZKLINIK_OLLAMA_KEEP_ALIVE",
    "whisper_model": "YAZKLINIK_WHISPER_MODEL",
    "whisper_device": "YAZKLINIK_WHISPER_DEVICE",
    "whisper_compute_type": "YAZKLINIK_WHISPER_COMPUTE_TYPE",
    "comfyui_gpu_args": "YAZKLINIK_COMFYUI_GPU_ARGS",
    "openai_api_key": "OPENAI_API_KEY",
    "openai_model": "YAZKLINIK_OPENAI_MODEL",
    "openai_base_url": "YAZKLINIK_OPENAI_BASE_URL",
    "openai_timeout": "YAZKLINIK_OPENAI_TIMEOUT",
    "terminal_token": "YAZKLINIK_TERMINAL_TOKEN",
    "server_url": "YAZKLINIK_SERVER_URL",
    "https_url": "YAZKLINIK_HTTPS_URL",
    "smart_assistant": "YAZKLINIK_SMART_ASSISTANT",
    "smart_assistant_quiet": "YAZKLINIK_SMART_ASSISTANT_QUIET",
    "bulutklinik_portal_url": "YAZKLINIK_BULUTKLINIK_PORTAL_URL",
    "enabiz_doctor_portal_url": "YAZKLINIK_ENABIZ_DOCTOR_PORTAL_URL",
}


def default_config_path(base_dir=None):
    base = Path(base_dir) if base_dir else Path(__file__).resolve().parent
    return base / DEFAULT_CONFIG_NAME


def normalize_config(data=None):
    cfg = dict(DEFAULT_CONFIG)
    if isinstance(data, dict):
        for key, value in data.items():
            if value is not None:
                cfg[str(key)] = str(value)
    if cfg.get("web_port") and not cfg.get("server_url", "").endswith(f":{cfg['web_port']}"):
        host = cfg.get("server_host") or cfg.get("orthanc_host") or "127.0.0.1"
        cfg["server_url"] = f"http://{host}:{cfg['web_port']}"
    return cfg


def load_config(path=None):
    cfg_path = Path(path) if path else default_config_path()
    if not cfg_path.exists():
        return normalize_config({})
    try:
        return normalize_config(json.loads(cfg_path.read_text(encoding="utf-8")))
    except Exception:
        return normalize_config({})


def save_config(config, path=None):
    cfg_path = Path(path) if path else default_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    cfg = normalize_config(config)
    cfg_path.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return cfg_path


def apply_config_to_environment(config=None, path=None, override=False):
    cfg = normalize_config(config if config is not None else load_config(path))
    for key, env_name in ENV_MAP.items():
        value = str(cfg.get(key) or "").strip()
        if not value:
            continue
        if override or not os.environ.get(env_name):
            os.environ[env_name] = value
    if cfg.get("server_url"):
        for env_name in ("YAZKLINIK_WEB_URL", "YAZKLINIK_DEFAULT_SERVER_URL"):
            if override or not os.environ.get(env_name):
                os.environ[env_name] = cfg["server_url"]
    return cfg


def env_batch_lines(config=None):
    cfg = normalize_config(config)
    lines = [
        "@echo off",
        'set "PYTHONUTF8=1"',
        'set "PYTHONIOENCODING=utf-8"',
        'set "PYTHONOPTIMIZE=1"',
    ]
    for key, env_name in ENV_MAP.items():
        value = str(cfg.get(key) or "").strip()
        if value:
            lines.append(f'set "{env_name}={value}"')
    if cfg.get("server_url"):
        lines.append(f'set "YAZKLINIK_WEB_URL={cfg["server_url"]}"')
        lines.append(f'set "YAZKLINIK_DEFAULT_SERVER_URL={cfg["server_url"]}"')
    return lines
