"""Flask Blueprint - 10 klinik ajan icin tek web wire dosyasi.

yazklinik_web.py'a sadece 2 satir eklenir:
    from yazklinik_agents_routes import agents_bp
    app.register_blueprint(agents_bp)

Endpointler:
    GET  /ajanlar                        -> dashboard sayfasi (HTML)
    GET  /api/agents                     -> manifest (registry + saglik)
    POST /api/agents/telesekreter/run    -> CallRecord -> TriagedCall
    POST /api/agents/sesli_onay/run      -> ConfirmationRequest -> ConfirmationResult
    POST /api/agents/usg_rapor/run       -> USGInput -> USGReportDraft
    POST /api/agents/geri_cagirma/run    -> PatientCandidate[] -> ReminderJob[]
    POST /api/agents/bk_sync_bekci/run   -> SyncProbe -> HealthReport
    POST /api/agents/nas_yedek_izleyici/run -> {nas_root, backup_subdir} -> NASHealthReport
    POST /api/agents/recete_hazirlayici/run -> DraftRequest -> RecipeDraft
    POST /api/agents/gunluk_ozet/run     -> SummaryInput -> DailySummary
    POST /api/agents/mojibake_bekci/run  -> {root} -> ScanResult
    POST /api/agents/pr_reviewer/run     -> {diff_text} -> ReviewResult

Yetki kontrolu: session['user'] / session['username'] var mi diye bakar.
Bu Blueprint o decorator'i import etmez; basit session check yapar.
Tum cikti web layer audit'ine 'agents:*' aksiyonu olarak yansir.
"""

from __future__ import annotations

import copy
import json
import os
import time
import traceback
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote, urlsplit, urlunsplit

from yazklinik_db_adapter import agent_connection as _pgconn  # PG-primary aware (cutover)

from flask import (
    Blueprint,
    jsonify,
    render_template_string,
    request,
    session,
    send_file,
    abort,
    redirect,
    url_for,
)


agents_bp = Blueprint("agents", __name__)
_CRON_TOKEN = os.environ.get("YAZKLINIK_CRON_TOKEN", "").strip()


def _cron_auth_ok() -> bool:
    return bool(_CRON_TOKEN and request.headers.get("X-Cron-Token") == _CRON_TOKEN)


def _portal_public_base_url() -> str:
    """Hasta portal linklerinde dis/public alan adini zorlar."""
    raw = (
        os.environ.get("YAZKLINIK_PATIENT_PORTAL_BASE_URL")
        or os.environ.get("YAZKLINIK_PUBLIC_BASE_URL")
        or os.environ.get("YAZKLINIK_EXTERNAL_BASE_URL")
        or os.environ.get("YAZKLINIK_CANONICAL_HOST")
        or "https://yazhakan.com.tr"
    )
    text = str(raw or "").strip()
    if not text:
        return "https://yazhakan.com.tr"
    if not text.startswith(("http://", "https://")):
        text = "https://" + text.lstrip("/")
    try:
        parts = urlsplit(text)
        host = str(parts.hostname or "").strip().lower()
        if not host:
            return "https://yazhakan.com.tr"
        if host in {"localhost", "127.0.0.1"}:
            return "https://yazhakan.com.tr"
        if host.endswith(".ts.net"):
            return "https://yazhakan.com.tr"
        try:
            import ipaddress
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or str(ip).startswith("100."):
                return "https://yazhakan.com.tr"
        except Exception:
            pass
        scheme = (parts.scheme or "https").lower()
        netloc = parts.netloc or host
        return urlunsplit((scheme, netloc, "", "", "")).rstrip("/")
    except Exception:
        return "https://yazhakan.com.tr"


@agents_bp.after_request
def _agents_medical_theme(response):
    """Ajan sayfalarini ana D700 medikal tema ve kisa gecislerle goster."""
    try:
        if response.mimetype != "text/html" or response.direct_passthrough:
            return response
        portal_path = (request.path or "").startswith("/hasta-portal")
        html = response.get_data(as_text=True)
        if not html:
            return response
        if "yk-medical-theme-css" not in html:
            link = (
                '<link rel="stylesheet" '
                'href="/static/yk-medical-theme.css?v=d700-medical-2026-05-17-ui3" '
                'id="yk-medical-theme-css">'
            )
            if "</head>" in html:
                html = html.replace("</head>", link + "</head>", 1)
            else:
                html = link + html
        if "yk-agent-shortcuts" not in html and not portal_path:
            style = (
                '<style id="yk-agent-shortcuts-css">'
                '.yk-agent-shortcuts{position:fixed;right:18px;top:14px;z-index:40;'
                'display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end}'
                '.yk-agent-shortcuts a{background:#fff;border:1px solid #bfd7ea;'
                'color:#14324a;text-decoration:none;border-radius:8px;padding:8px 10px;'
                'font-weight:800;font-size:12px;box-shadow:0 8px 22px rgba(15,35,55,.10)}'
                '@media(max-width:760px){.yk-agent-shortcuts{position:static;margin:10px 12px;'
                'justify-content:flex-start}.yk-agent-shortcuts a{font-size:11px;padding:7px 8px}}'
                '</style>'
            )
            nav = (
                '<nav id="yk-agent-shortcuts" class="yk-agent-shortcuts">'
                '<a href="/">Ana ekran</a>'
                '<a href="/ajanlar">Klinik ajanlari</a>'
                '<a href="/yz-konsultasyon">YZ hekim</a>'
                '<a href="/hasta-portal" style="background:#0a8a76;color:#fff">Hasta Portal</a>'
                '<a href="/ceviri-merkezi">Tibbi ceviri</a>'
                '<a href="/instagram-hazirla">Instagram</a>'
                '</nav>'
            )
            if "</head>" in html:
                html = html.replace("</head>", style + "</head>", 1)
            else:
                html = style + html
            body_idx = html.lower().find("<body")
            if body_idx >= 0:
                body_end = html.find(">", body_idx)
                if body_end >= 0:
                    html = html[:body_end + 1] + nav + html[body_end + 1:]
                else:
                    html = nav + html
            else:
                html = nav + html
        response.set_data(html)
    except Exception:
        pass
    return response

# Instagram icin varsayilan yollar (config.env'den okumayi web layer yapar)
_DEFAULT_VOLUSON_ROOT = os.environ.get("YAZKLINIK_NAS_ROOT") or r"\\asustor\Voluson"
_DEFAULT_IG_DRAFT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "instagram_drafts"
)


# --- Agent imports - hata olursa modul yine yuklensin ---
_AGENT_IMPORT_ERRORS: Dict[str, str] = {}


def _safe_import(name: str):
    try:
        return __import__(name)
    except Exception as exc:  # noqa: BLE001
        _AGENT_IMPORT_ERRORS[name] = f"{type(exc).__name__}: {exc}"
        return None


telesekreter_mod = _safe_import("yazklinik_telesekreter_agent")
sesli_onay_mod = _safe_import("yazklinik_sesli_onay_agent")
usg_rapor_mod = _safe_import("yazklinik_usg_rapor_agent")
geri_cagirma_mod = _safe_import("yazklinik_geri_cagirma_agent")
bk_sync_mod = _safe_import("yazklinik_bk_sync_bekci_agent")
nas_mod = _safe_import("yazklinik_nas_yedek_izleyici_agent")
recete_mod = _safe_import("yazklinik_recete_hazirlayici_agent")
ozet_mod = _safe_import("yazklinik_gunluk_ozet_agent")
mojibake_mod = _safe_import("yazklinik_mojibake_bekci_agent")
pr_mod = _safe_import("yazklinik_pr_reviewer_agent")
instagram_mod = _safe_import("yazklinik_instagram_agent")
ceviri_mod = _safe_import("yazklinik_ceviri_agent")
konsult_mod = _safe_import("yazklinik_konsult_agent")
medgemma_mod = _safe_import("yazklinik_medgemma_agent")

# --- Session 7: 29 yeni ajan ---
vision_mod = _safe_import("yazklinik_vision_usg_agent")
soap_mod = _safe_import("yazklinik_soap_agent")
icd10_mod = _safe_import("yazklinik_icd10_agent")
gebelik_mod = _safe_import("yazklinik_gebelik_takvim_agent")
risk_mod = _safe_import("yazklinik_risk_skor_agent")
ddi_mod = _safe_import("yazklinik_ddi_agent")
voice_cmd_mod = _safe_import("yazklinik_voice_command_agent")
burnout_mod = _safe_import("yazklinik_anti_burnout_agent")
hatira_mod = _safe_import("yazklinik_hatira_usg_agent")
orchestrator_mod = _safe_import("yazklinik_orchestrator_agent")
portal_mod = _safe_import("yazklinik_hasta_portal_agent")
twofa_mod = _safe_import("yazklinik_2fa_agent")
phq9_mod = _safe_import("yazklinik_phq9_agent")
stok_mod = _safe_import("yazklinik_stok_agent")
konsey_mod = _safe_import("yazklinik_konsey_agent")
payment_mod = _safe_import("yazklinik_payment_agent")
enabiz_mod = _safe_import("yazklinik_enabiz_kts_agent")
mhrs_mod = _safe_import("yazklinik_mhrs_agent")
medula_mod = _safe_import("yazklinik_medula_agent")
lab_duzen_mod = _safe_import("yazklinik_lab_duzen_agent")
iot_mod = _safe_import("yazklinik_iot_bluetooth_agent")
plugin_mod = _safe_import("yazklinik_plugin_loader")
smear_mod = _safe_import("yazklinik_smear_hpv_agent")
memnuniyet_mod = _safe_import("yazklinik_memnuniyet_agent")
pubmed_cron_mod = _safe_import("yazklinik_pubmed_cron_agent")
compliance_mod = _safe_import("yazklinik_compliance_agent")
status_mod = _safe_import("yazklinik_status_page_agent")
celery_mod = _safe_import("yazklinik_celery_worker")
sentry_mod = _safe_import("yazklinik_sentry_init")

# Registry (opsiyonel)
try:
    from yazklinik_integration_agents import get_integration_agents as _get_registry
except Exception:  # noqa: BLE001
    _get_registry = None


def _agent_module_health_rows():
    return [
        ("yazklinik_telesekreter_agent", telesekreter_mod),
        ("yazklinik_sesli_onay_agent", sesli_onay_mod),
        ("yazklinik_usg_rapor_agent", usg_rapor_mod),
        ("yazklinik_geri_cagirma_agent", geri_cagirma_mod),
        ("yazklinik_bk_sync_bekci_agent", bk_sync_mod),
        ("yazklinik_nas_yedek_izleyici_agent", nas_mod),
        ("yazklinik_recete_hazirlayici_agent", recete_mod),
        ("yazklinik_gunluk_ozet_agent", ozet_mod),
        ("yazklinik_mojibake_bekci_agent", mojibake_mod),
        ("yazklinik_pr_reviewer_agent", pr_mod),
        ("yazklinik_instagram_agent", instagram_mod),
        ("yazklinik_ceviri_agent", ceviri_mod),
        ("yazklinik_konsult_agent", konsult_mod),
        ("yazklinik_medgemma_agent", medgemma_mod),
        ("yazklinik_vision_usg_agent", vision_mod),
        ("yazklinik_soap_agent", soap_mod),
        ("yazklinik_icd10_agent", icd10_mod),
        ("yazklinik_gebelik_takvim_agent", gebelik_mod),
        ("yazklinik_risk_skor_agent", risk_mod),
        ("yazklinik_ddi_agent", ddi_mod),
        ("yazklinik_voice_command_agent", voice_cmd_mod),
        ("yazklinik_anti_burnout_agent", burnout_mod),
        ("yazklinik_hatira_usg_agent", hatira_mod),
        ("yazklinik_orchestrator_agent", orchestrator_mod),
        ("yazklinik_hasta_portal_agent", portal_mod),
        ("yazklinik_2fa_agent", twofa_mod),
        ("yazklinik_phq9_agent", phq9_mod),
        ("yazklinik_stok_agent", stok_mod),
        ("yazklinik_konsey_agent", konsey_mod),
        ("yazklinik_payment_agent", payment_mod),
        ("yazklinik_enabiz_kts_agent", enabiz_mod),
        ("yazklinik_mhrs_agent", mhrs_mod),
        ("yazklinik_medula_agent", medula_mod),
        ("yazklinik_lab_duzen_agent", lab_duzen_mod),
        ("yazklinik_iot_bluetooth_agent", iot_mod),
        ("yazklinik_plugin_loader", plugin_mod),
        ("yazklinik_smear_hpv_agent", smear_mod),
        ("yazklinik_memnuniyet_agent", memnuniyet_mod),
        ("yazklinik_pubmed_cron_agent", pubmed_cron_mod),
        ("yazklinik_compliance_agent", compliance_mod),
        ("yazklinik_status_page_agent", status_mod),
        ("yazklinik_celery_worker", celery_mod),
        ("yazklinik_sentry_init", sentry_mod),
    ]


_AGENT_HEALTH_CACHE: Dict[str, Any] = {"ts": 0.0, "payload": None}


def _agent_health_cache_ttl() -> int:
    try:
        return max(1, int(os.environ.get("YAZKLINIK_AGENT_HEALTH_TTL_SEC", "20")))
    except Exception:
        return 20


def _agent_registry_focus_index() -> tuple[Dict[str, Dict[str, Any]], Dict[str, Any]]:
    """Map registry modules to task/guardrail metadata."""
    summary: Dict[str, Any] = {
        "available": bool(_get_registry),
        "total": 0,
        "guardrails_ok": 0,
        "needs_attention": [],
        "error": "",
    }
    index: Dict[str, Dict[str, Any]] = {}
    if not _get_registry:
        summary["error"] = "registry_unavailable"
        return index, summary
    try:
        registry = _get_registry()
        agents = registry.get("agents") if isinstance(registry, dict) else []
        for agent in agents or []:
            if not isinstance(agent, dict):
                continue
            aid = str(agent.get("id") or "").strip()
            module_name = str(agent.get("module") or "").strip()
            guardrails_ok = all([
                bool(agent.get("safe_methods")),
                bool(agent.get("blocked_methods")),
                bool(agent.get("doctor_actions")),
            ])
            summary["total"] += 1
            if guardrails_ok:
                summary["guardrails_ok"] += 1
            else:
                summary["needs_attention"].append(aid or module_name or "unknown")
            if module_name:
                index[module_name] = {
                    "agent_id": aid,
                    "name": str(agent.get("name") or "").strip(),
                    "status": str(agent.get("status") or "").strip(),
                    "entry_function": str(agent.get("entry_function") or "").strip(),
                    "guardrails_ok": guardrails_ok,
                }
    except Exception as exc:  # noqa: BLE001
        summary["error"] = f"{type(exc).__name__}: {exc}"
    return index, summary


def _agent_public_callables(module_obj: Any, limit: int = 8) -> List[str]:
    if module_obj is None:
        return []
    names: List[str] = []
    for name in dir(module_obj):
        if name.startswith("_"):
            continue
        value = getattr(module_obj, name, None)
        if callable(value):
            names.append(name)
            if len(names) >= limit:
                break
    return names


def _module_focus_payload(
    module_name: str,
    module_obj: Any,
    registry_index: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    loaded = module_obj is not None
    focus_meta = registry_index.get(module_name) or {}
    entry_function = str(focus_meta.get("entry_function") or "").strip()
    has_health_check = bool(loaded and callable(getattr(module_obj, "health_check", None)))
    entry_function_ok = bool(
        loaded and entry_function and callable(getattr(module_obj, entry_function, None))
    )
    public_callables = _agent_public_callables(module_obj)
    doc_summary = ""
    if loaded:
        doc_summary = str(getattr(module_obj, "__doc__", "") or "").strip().splitlines()[0:1]
        doc_summary = doc_summary[0].strip() if doc_summary else ""
    registered = bool(focus_meta)
    if not loaded:
        focus_ok = False
        focus_source = "import_failed"
    elif registered:
        focus_ok = bool(focus_meta.get("guardrails_ok")) and (
            entry_function_ok or not entry_function
        )
        focus_source = "registry_guardrails"
    elif has_health_check:
        focus_ok = True
        focus_source = "health_check"
    elif public_callables:
        focus_ok = True
        focus_source = "callable_api"
    else:
        focus_ok = False
        focus_source = "import_only"
    return {
        "registered": registered,
        "agent_id": focus_meta.get("agent_id", ""),
        "agent_name": focus_meta.get("name", ""),
        "agent_status": focus_meta.get("status", ""),
        "entry_function": entry_function,
        "entry_function_ok": entry_function_ok,
        "guardrails_ok": bool(focus_meta.get("guardrails_ok")) if registered else None,
        "has_health_check": has_health_check,
        "public_callables": public_callables,
        "doc_summary": doc_summary,
        "focus_ok": focus_ok,
        "focus_source": focus_source,
        "needs_attention": not focus_ok,
    }


def get_agent_module_health(force: bool = False) -> Dict[str, Any]:
    """Import edilen ajan modullerinin saglik ozetini verir (read-only)."""
    now = time.time()
    ttl = _agent_health_cache_ttl()
    cached = _AGENT_HEALTH_CACHE.get("payload")
    if not force and isinstance(cached, dict) and now - float(_AGENT_HEALTH_CACHE.get("ts") or 0) <= ttl:
        payload = copy.deepcopy(cached)
        payload["cached"] = True
        payload["cache_ttl_sec"] = ttl
        return payload
    module_health: Dict[str, Dict[str, Any]] = {}
    ok_count = 0
    fail_count = 0
    focus_ok_count = 0
    focus_attention: List[str] = []
    registry_index, registry_summary = _agent_registry_focus_index()
    for module_name, module_obj in _agent_module_health_rows():
        loaded = module_obj is not None
        if loaded:
            ok_count += 1
        else:
            fail_count += 1
        focus_payload = _module_focus_payload(module_name, module_obj, registry_index)
        if focus_payload.get("focus_ok"):
            focus_ok_count += 1
        else:
            focus_attention.append(module_name)
        module_health[module_name] = {
            "loaded": loaded,
            "error": _AGENT_IMPORT_ERRORS.get(module_name, ""),
            **focus_payload,
        }
    payload = {
        "ok": True,
        "generated_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        "total": len(module_health),
        "loaded": ok_count,
        "failed": fail_count,
        "focus_ok": focus_ok_count,
        "focus_needs_attention": focus_attention,
        "registry_focus": registry_summary,
        "cached": False,
        "cache_ttl_sec": ttl,
        "module_health": module_health,
    }
    _AGENT_HEALTH_CACHE["ts"] = now
    _AGENT_HEALTH_CACHE["payload"] = copy.deepcopy(payload)
    return payload


# --- Helper'lar ---

def _require_session():
    """Web.py'in genel session kuralina hafif bagli kontrol.
    Doktor/asistan/sekreter girisi yoksa:
      - JSON istek (XHR / Accept: application/json / /api/*) icin 401 JSON
      - HTML sayfa istegi icin /giris'e redirect (kullanici dostu)
    """
    # YazKlinik ana login'i session["user"] yazar. Eski notlarda
    # session["username"] geciyordu; iki anahtari da kabul et.
    user = (session.get("user") or session.get("username")) if hasattr(session, "get") else None
    if user:
        return None
    is_json_req = (
        request.path.startswith("/api/")
        or "application/json" in (request.headers.get("Accept", "") or "")
        or request.headers.get("X-Requested-With") == "XMLHttpRequest"
    )
    if is_json_req:
        return jsonify({"ok": False, "error": "auth_required"}), 401
    try:
        from flask import redirect as _flask_redirect
        next_url = request.path + (("?" + request.query_string.decode())
                                     if request.query_string else "")
        return _flask_redirect("/giris?next=" + next_url)
    except Exception:
        return jsonify({"ok": False, "error": "auth_required"}), 401


def _require_session_or_cron():
    if _cron_auth_ok():
        return None
    return _require_session()


def _to_jsonable(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    return value


def _safe_audit(action: str, payload: Dict[str, Any]) -> None:
    """web_audit_log fonksiyonu varsa cagir; yoksa sessizce gec."""
    try:
        import sys
        web_audit_log = None
        for module_name in ("__main__", "yazklinik_web"):
            module = sys.modules.get(module_name)
            candidate = getattr(module, "web_audit_log", None) if module else None
            if callable(candidate):
                web_audit_log = candidate
                break
        if web_audit_log is None:
            return
        try:
            web_audit_log(action=action, payload=payload)
        except TypeError:
            web_audit_log(action, payload)
    except Exception:
        pass


def _payload() -> Dict[str, Any]:
    if request.is_json:
        return request.get_json(silent=True) or {}
    return request.form.to_dict(flat=True) or {}


def _resolve_active_patient_key(raw_key: str) -> str:
    key = str(raw_key or "").strip()
    if key.lower() not in {"aktif", "active", "secili", "selected"}:
        return key
    try:
        from yazklinik_common import get_active_patient
        active = get_active_patient() or {}
        return str(active.get("patient_key") or "").strip()
    except Exception:
        return ""


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if not text:
        return default
    return text in ("1", "true", "yes", "y", "on", "evet")


_MEDGEMMA_BIND_SESSION_KEY = "medgemma_binding_v1"
_MEDGEMMA_TASKS = {
    "clinical_note",
    "usg_pdf",
    "lab_triage",
    "red_flags",
    "patient_summary",
}


def _clip_text(value: Any, max_len: int) -> str:
    text = str(value or "").strip()
    return text[:max_len]


def _normalize_task_model_overrides(overrides_raw: Any) -> Dict[str, str]:
    out: Dict[str, str] = {}
    if not isinstance(overrides_raw, dict):
        return out
    for key, value in overrides_raw.items():
        task = str(key or "").strip()
        model_id = _clip_text(value, 120)
        if task in _MEDGEMMA_TASKS and model_id:
            out[task] = model_id
    return out


def _medgemma_binding_default() -> Dict[str, Any]:
    return {
        "task": "clinical_note",
        "patient_context": "",
        "yz_definition": "",
        "assignment": "",
        "prefer_model": "",
        "task_model_overrides": {},
        "preview_only": True,
        "sticky_context": True,
    }


def _medgemma_binding_read() -> Dict[str, Any]:
    base = _medgemma_binding_default()
    raw = session.get(_MEDGEMMA_BIND_SESSION_KEY)
    if isinstance(raw, dict):
        base["task"] = str(raw.get("task") or base["task"]).strip() or base["task"]
        base["patient_context"] = _clip_text(raw.get("patient_context"), 8000)
        base["yz_definition"] = _clip_text(raw.get("yz_definition"), 4000)
        base["assignment"] = _clip_text(raw.get("assignment"), 4000)
        base["prefer_model"] = _clip_text(raw.get("prefer_model"), 120)
        base["task_model_overrides"] = _normalize_task_model_overrides(raw.get("task_model_overrides"))
        base["preview_only"] = _as_bool(raw.get("preview_only"), True)
        base["sticky_context"] = _as_bool(raw.get("sticky_context"), True)
    if base["task"] not in _MEDGEMMA_TASKS:
        base["task"] = "clinical_note"
    return base


def _medgemma_binding_write(data: Dict[str, Any]) -> Dict[str, Any]:
    out = _medgemma_binding_default()
    out["task"] = str(data.get("task") or out["task"]).strip() or out["task"]
    out["patient_context"] = _clip_text(data.get("patient_context"), 8000)
    out["yz_definition"] = _clip_text(data.get("yz_definition"), 4000)
    out["assignment"] = _clip_text(data.get("assignment"), 4000)
    out["prefer_model"] = _clip_text(data.get("prefer_model"), 120)
    out["task_model_overrides"] = _normalize_task_model_overrides(data.get("task_model_overrides"))
    out["preview_only"] = _as_bool(data.get("preview_only"), True)
    out["sticky_context"] = _as_bool(data.get("sticky_context"), True)
    if out["task"] not in _MEDGEMMA_TASKS:
        out["task"] = "clinical_note"
    session[_MEDGEMMA_BIND_SESSION_KEY] = out
    session.modified = True
    return out


def _medgemma_binding_clear() -> Dict[str, Any]:
    session.pop(_MEDGEMMA_BIND_SESSION_KEY, None)
    session.modified = True
    return _medgemma_binding_default()


def _medgemma_task_recommendations() -> Dict[str, Dict[str, str]]:
    fallback = {
        "clinical_note": {"model": "google/medgemma-4b-it", "note": "Dengeli kalite ve hiz."},
        "usg_pdf": {"model": "google/medgemma-27b-text-it", "note": "Uzun metin/PDF yorumunda daha guclu kalite."},
        "lab_triage": {"model": "google/medgemma-27b-text-it", "note": "Tetkik triyajinda daha derin analiz."},
        "red_flags": {"model": "google/medgemma-4b-it", "note": "Acil risk taramasinda hizli ve net."},
        "patient_summary": {"model": "google/medgemma-27b-text-it", "note": "Detayli dosya ozetinde daha yuksek kalite."},
        "__image_default__": {"model": "google/medgemma-27b-it", "note": "Goruntu+metin talepleri icin oncelikli onerilen model."},
    }
    try:
        if medgemma_mod and hasattr(medgemma_mod, "task_model_recommendations"):
            data = medgemma_mod.task_model_recommendations()
            if isinstance(data, dict) and data:
                return data
    except Exception:
        pass
    return fallback


def _medgemma_recommended_model(task: str, has_image: bool = False) -> str:
    try:
        if medgemma_mod and hasattr(medgemma_mod, "recommended_model_for_task"):
            model_id = str(medgemma_mod.recommended_model_for_task(task=task, has_image=has_image) or "").strip()
            if model_id:
                return model_id
    except Exception:
        pass
    table = _medgemma_task_recommendations()
    if has_image and isinstance(table.get("__image_default__"), dict):
        return str(table["__image_default__"].get("model") or "google/medgemma-27b-it")
    row = table.get(str(task or "").strip())
    if isinstance(row, dict):
        return str(row.get("model") or "google/medgemma-4b-it")
    return "google/medgemma-4b-it"


def _medgemma_task_assignment_recommendations() -> Dict[str, Dict[str, str]]:
    fallback = {
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
    try:
        if medgemma_mod and hasattr(medgemma_mod, "task_assignment_recommendations"):
            data = medgemma_mod.task_assignment_recommendations()
            if isinstance(data, dict) and data:
                return data
    except Exception:
        pass
    return fallback


_ROOT_CONFIG_CACHE: Optional[Dict[str, str]] = None


def _root_config_env() -> Dict[str, str]:
    """Read config.env once so optional agents obey the same mode as web.py."""
    global _ROOT_CONFIG_CACHE
    if _ROOT_CONFIG_CACHE is not None:
        return _ROOT_CONFIG_CACHE
    out: Dict[str, str] = {}
    try:
        cfg_path = Path(__file__).resolve().parent / "config.env"
        if cfg_path.exists():
            for line in cfg_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                out[key.strip()] = value.strip()
    except Exception:
        out = {}
    _ROOT_CONFIG_CACHE = out
    return out


def _config_or_env(key: str, default: str = "") -> str:
    cfg = _root_config_env()
    val = cfg.get(key)
    if val not in (None, ""):
        return str(val)
    return os.environ.get(key, default)


def _postgres_feature_enabled() -> bool:
    dialect_raw = _config_or_env("YAZKLINIK_DB_DIALECT", "")
    dialect = (dialect_raw or "sqlite").strip().lower()
    enabled = _as_bool(_config_or_env("YAZKLINIK_ENABLE_POSTGRES", "0"), False)
    pg_url = _config_or_env("YAZKLINIK_DATABASE_URL", "").strip()
    if dialect in {"postgres", "postgresql"} or enabled:
        return True
    return bool(pg_url and not dialect_raw)


def _mask_pg_dsn_value(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
        if not parsed.scheme.startswith("postgres") or not parsed.username:
            return text
        host = parsed.hostname or ""
        if parsed.port:
            host = f"{host}:{parsed.port}"
        auth = f"{parsed.username}:***@{host}"
        return urlunsplit((parsed.scheme, auth, parsed.path, parsed.query, parsed.fragment))
    except Exception:
        if "@" in text and ":" in text:
            return "postgresql://***:***@***"
        return text


def _agent_or_503(mod, name: str):
    if mod is None:
        return jsonify({
            "ok": False, "agent": name, "error": "module_import_failed",
            "detail": _AGENT_IMPORT_ERRORS.get(f"yazklinik_{name}_agent", "unknown"),
        }), 503
    return None


def _wrap_call(name: str, callable_fn, kwargs: Dict[str, Any]):
    try:
        result = callable_fn(**kwargs)
    except TypeError as exc:
        return jsonify({"ok": False, "agent": name, "error": "bad_request", "detail": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "agent": name, "error": "agent_failure",
                         "detail": f"{type(exc).__name__}: {exc}",
                         "trace": traceback.format_exc(limit=4)}), 500

    serialized = _to_jsonable(result)
    _safe_audit(f"agents:{name}", {"input_keys": list(kwargs.keys())})
    return jsonify({"ok": True, "agent": name, "result": serialized})


def _agent_preview(name: str, message: str, result: Dict[str, Any]):
    _safe_audit(f"agents:{name}:preview", {"result_keys": list(result.keys())})
    return jsonify({
        "ok": True,
        "agent": name,
        "preview": True,
        "message": message,
        "result": _to_jsonable(result),
    })


def _quick_step(step: str, fn, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    started = datetime.now()
    item: Dict[str, Any] = {"step": step, "ok": False, "summary": "", "duration_ms": 0}
    try:
        out = fn(**kwargs)
        payload = _to_jsonable(out)
        item["ok"] = True
        item["payload"] = payload
        if isinstance(payload, dict):
            item["summary"] = str(payload.get("summary") or payload.get("message") or step)[:180]
        else:
            item["summary"] = str(payload)[:180]
    except Exception as exc:  # noqa: BLE001
        item["error"] = f"{type(exc).__name__}: {exc}"
        item["summary"] = item["error"]
    item["duration_ms"] = int((datetime.now() - started).total_seconds() * 1000)
    return item


# --- Manifest + dashboard ---

_AGENT_SCREEN_ROUTES = {
    "bulutklinik": "/bulutklinik",
    "enabiz": "/enabiz",
    "doktortakvimi": "/randevular",
    "dokortakvimi": "/randevular",
    "randevu_sohbet": "/sohbet-merkezi",
    "kvkk_denetimevi": "/uyumluluk",
    "kvkk_denetimi": "/uyumluluk",
    "eslestirme": "/hasta-birlestir",
    "telesekreter": "/yz-telefon-diyalog",
    "sesli_onay": "/randevu-onay",
    "usg_rapor": "/hasta/aktif/usg-rapor-taslak",
    "geri_cagirma": "/toplu-hatirlatma",
    "bk_sync_bekci": "/bulutklinik-merkez",
    "nas_yedek_izleyici": "/yedekleme-merkezi",
    "recete_hazirlayici": "/recete-gunluk-kontrol",
    "gunluk_ozet": "/gun-plani",
    "mojibake_bekci": "/sistem-durumu",
    "pr_reviewer": "/calisan-isler",
    "instagram": "/instagram-hazirla",
    "konsult": "/yz-konsultasyon",
    "ceviri": "/ceviri-merkezi",
    "medgemma": "/medgemma-klinik-yz",
}

_AGENT_SCREEN_LABELS = {
    "doktortakvimi": "Randevulari ac",
    "dokortakvimi": "Randevulari ac",
    "randevu_sohbet": "Sohbet merkezini ac",
    "kvkk_denetimevi": "Uyumluluk panosunu ac",
    "kvkk_denetimi": "Uyumluluk panosunu ac",
    "eslestirme": "Hasta birlestirmeyi ac",
    "telesekreter": "Telefon diyalog ekranini ac",
    "sesli_onay": "Randevu onay ekranini ac",
    "usg_rapor": "Hasta secip USG taslagi ac",
    "geri_cagirma": "Hatirlatma ekranini ac",
    "bk_sync_bekci": "BulutKlinik merkezini ac",
    "nas_yedek_izleyici": "Yedekleme merkezini ac",
    "recete_hazirlayici": "Recete kontrolunu ac",
    "gunluk_ozet": "Gun planini ac",
    "mojibake_bekci": "Sistem durumunu ac",
    "pr_reviewer": "Calisan isleri ac",
    "medgemma": "MedGemma panelini ac",
}


def _agent_screen_route(agent_id: str, current: str = "") -> str:
    aid = str(agent_id or "").strip()
    route = str(current or "").strip()
    return route or _AGENT_SCREEN_ROUTES.get(aid, "")


def _agent_screen_label(agent_id: str) -> str:
    return _AGENT_SCREEN_LABELS.get(str(agent_id or "").strip(), "Bagli ekrana git")

@agents_bp.route("/api/agents", methods=["GET"])
def api_agents_manifest():
    auth = _require_session()
    if auth:
        return auth
    payload: Dict[str, Any] = {"ok": True, "import_errors": dict(_AGENT_IMPORT_ERRORS)}
    if _get_registry:
        try:
            registry = _get_registry()
            if isinstance(registry, dict):
                for agent in registry.get("agents") or []:
                    if not isinstance(agent, dict):
                        continue
                    aid = str(agent.get("id") or "").strip()
                    route = _agent_screen_route(aid, str(agent.get("panel_route") or ""))
                    if route:
                        agent["panel_route"] = route
                        agent["screen_label"] = _agent_screen_label(aid)
                payload["registry"] = registry
            else:
                payload["registry"] = registry
        except Exception as exc:  # noqa: BLE001
            payload["registry_error"] = f"{type(exc).__name__}: {exc}"
    payload["modules"] = {
        "telesekreter": telesekreter_mod is not None,
        "sesli_onay": sesli_onay_mod is not None,
        "usg_rapor": usg_rapor_mod is not None,
        "geri_cagirma": geri_cagirma_mod is not None,
        "bk_sync_bekci": bk_sync_mod is not None,
        "nas_yedek_izleyici": nas_mod is not None,
        "recete_hazirlayici": recete_mod is not None,
        "gunluk_ozet": ozet_mod is not None,
        "mojibake_bekci": mojibake_mod is not None,
        "pr_reviewer": pr_mod is not None,
        "instagram": instagram_mod is not None,
        "ceviri": ceviri_mod is not None,
        "konsult": konsult_mod is not None,
        "medgemma": medgemma_mod is not None,
        "vision_usg": vision_mod is not None,
        "soap": soap_mod is not None,
        "icd10": icd10_mod is not None,
        "gebelik_takvim": gebelik_mod is not None,
        "risk_skor": risk_mod is not None,
        "ddi": ddi_mod is not None,
        "smear_hpv": smear_mod is not None,
        "phq9": phq9_mod is not None,
        "konsey": konsey_mod is not None,
        "hatira_usg": hatira_mod is not None,
        "voice_command": voice_cmd_mod is not None,
        "anti_burnout": burnout_mod is not None,
        "orchestrator": orchestrator_mod is not None,
        "hasta_portal": portal_mod is not None,
        "2fa": twofa_mod is not None,
        "stok": stok_mod is not None,
        "plugin_loader": plugin_mod is not None,
        "compliance": compliance_mod is not None,
        "status_page": status_mod is not None,
        "celery_worker": celery_mod is not None,
        "sentry": sentry_mod is not None,
        "memnuniyet": memnuniyet_mod is not None,
        "pubmed_cron": pubmed_cron_mod is not None,
        "payment": payment_mod is not None,
        "enabiz_kts": enabiz_mod is not None,
        "mhrs": mhrs_mod is not None,
        "medula": medula_mod is not None,
        "lab_duzen": lab_duzen_mod is not None,
        "iot_bluetooth": iot_mod is not None,
    }
    payload["focus_health"] = get_agent_module_health(
        force=str(request.args.get("force") or "").strip() in {"1", "true", "yes"}
    )
    return jsonify(payload)


_AGENTS_PAGE = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>Klinik AjanlarÃ„Â± - YazKlinik</title>
<style>
  :root { --yk-ink:#172f49; --yk-muted:#58708a; --yk-line:#c9deed; --yk-surface:#ffffff; --yk-soft:#eef8fb; --yk-accent:#0b79b7; }
  body { font-family: -apple-system, Segoe UI, Arial, sans-serif; background: linear-gradient(135deg,#f4fbff 0%,#e9f7f5 100%); color: var(--yk-ink); margin: 0; padding: 24px; }
  h1 { margin: 0 0 16px; font-size: 24px; color:#102b45; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
  .card { background: var(--yk-surface); border: 1px solid var(--yk-line); border-radius: 10px; padding: 15px; box-shadow:0 10px 28px rgba(22,62,94,.08); }
  .card-link { display:block; color:inherit; text-decoration:none; cursor:pointer; transition:transform .14s ease, border-color .14s ease, box-shadow .14s ease; }
  .card-link:hover { transform:translateY(-2px); border-color:#0b79b7; box-shadow:0 16px 34px rgba(22,62,94,.14); }
  .card-link:focus-visible { outline:3px solid rgba(11,121,183,.24); outline-offset:2px; }
  .card h3 { margin: 0 0 6px; font-size: 15px; color: #075c92; }
  .card p { margin: 0 0 8px; font-size: 13px; color: #314c68; line-height: 1.5; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; }
  .pill.ok { background: #16824a; color: #ffffff; }
  .pill.fail { background: #b42318; color: #ffffff; }
  .pill.warn { background: #b7791f; color: #ffffff; }
  code { background: #e8f2fa; color:#183650; padding: 1px 5px; border-radius: 4px; font-size: 11px; }
  .meta { font-size: 11px; color: var(--yk-muted); margin-top: 8px; }
  .row { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
  .card-action { margin-top:12px; display:flex; align-items:center; justify-content:space-between; gap:10px; color:#075c92; font-size:12px; font-weight:900; }
  .card-action small { color:#58708a; font-weight:700; }
  .card-arrow { font-size:16px; line-height:1; }
  .btn { display: inline-block; padding: 7px 11px; background: #ffffff; border: 1px solid #a9c9df;
         border-radius: 8px; color: #15324d; text-decoration: none; font-size: 12px; cursor: pointer; font-weight:800; }
  .btn:hover { background: #eaf5fc; }
  pre { background: #f6fbff; color:#17324a; border:1px solid #cde0ee; padding: 10px; border-radius: 8px; font-size: 11px; max-height: 260px; overflow: auto; }
</style></head>
<body>
  <h1>Klinik AjanlarÃ„Â±</h1>
  <p style="color:#58708a;font-size:13px;">TÃƒÂ¼m ajanlar saf iÃ…Å¸ mantÃ„Â±Ã„Å¸Ã„Â± sunar; sonuÃƒÂ§lar onay kuyruÃ„Å¸unda doktoru bekler.
     <code>GET /api/agents</code> ile manifest, <code>POST /api/agents/&lt;id&gt;/run</code> ile calistir.</p>
  <div id="status"></div>
  <div class="grid" id="grid"></div>
  <h2 style="margin-top: 28px; font-size: 16px;">Manifest</h2>
  <pre id="raw">yukleniyor...</pre>

<script>
function ykAgentEsc(v) {
  return String(v == null ? '' : v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function ykAgentAttr(v) {
  return ykAgentEsc(v).replace(/`/g, '&#96;');
}
async function load() {
  const r = await fetch('/api/agents', {credentials: 'same-origin'});
  if (!r.ok) {
    document.getElementById('status').innerHTML =
      '<p style="color:#f5d2d2">Yetki/baglanti hatasi: ' + r.status + '</p>';
    return;
  }
  const data = await r.json();
  document.getElementById('raw').textContent = JSON.stringify(data, null, 2);
  const reg = (data.registry && data.registry.agents) || [];
  const grid = document.getElementById('grid');
  grid.innerHTML = reg.map(a => {
    const enabled = data.modules && a.module ? data.modules[a.id] : null;
    let pill = '<span class="pill warn">no module</span>';
    if (enabled === true)  pill = '<span class="pill ok">aktif</span>';
    if (enabled === false) pill = '<span class="pill fail">import hatasi</span>';
    const href = a.panel_route || '/ajanlar?agent=' + encodeURIComponent(a.id || '');
    const label = a.screen_label || 'Bagli ekrana git';
    return `
      <a class="card card-link" href="${ykAgentAttr(href)}" data-agent-id="${ykAgentAttr(a.id || '')}">
        <div class="row"><h3>${ykAgentEsc(a.name)}</h3>${pill}</div>
        <p>${ykAgentEsc(a.short || '')}</p>
        <div class="meta">id: <code>${ykAgentEsc(a.id)}</code> | risk: ${ykAgentEsc(a.risk || '-')} | durum: ${ykAgentEsc(a.status || '-')}</div>
        <div class="card-action"><small>${ykAgentEsc(label)}</small><span class="card-arrow" aria-hidden="true">&gt;</span></div>
      </a>
    `;
  }).join('');
}
load();
</script>
</body></html>
"""

_SESSION7_AGENT_CARDS = [
    {"cat": "Klinik AI", "icon": "MED", "name": "MedGemma Klinik YZ", "desc": "Google MedGemma tabanli medikal uzman ajan: USG/PDF/lab/not icin doktor onayli taslak uretir.", "method": "POST", "url": "/api/agents/medgemma/analyze", "payload": {"task": "clinical_note", "note": "28 yas, gebelik kontrolu. Sikayet yok. Tansiyon 110/70.", "patient_context": "Obstetrik rutin kontrol", "preview_only": True}},
    {"cat": "Klinik AI", "icon": "USG", "name": "USG Vision", "desc": "USG goruntusunu lokal vision model ile yorumlar.", "method": "POST", "url": "/api/agents/vision-usg/analyze", "payload": {"demo": True, "image_path": ""}},
    {"cat": "Klinik AI", "icon": "SOAP", "name": "SOAP Not", "desc": "Kisa klinik notu hizli SOAP taslagina cevirir.", "method": "POST", "url": "/api/agents/soap/expand", "payload": {"note": "Gebelik kontrolu, tansiyon normal, sikayet yok.", "prefer": "skip"}},
    {"cat": "Klinik AI", "icon": "ICD", "name": "ICD-10 Oneri", "desc": "Klinik nottan uygun ICD-10 kodlarini hizli onerir.", "method": "POST", "url": "/api/agents/icd10/suggest", "payload": {"note": "Gebelikte hipertansiyon takibi", "top_k": 5, "prefer": "skip"}},
    {"cat": "Klinik AI", "icon": "DDI", "name": "Ilac Etkilesim", "desc": "Ilac etkilesimi ve gebelik uyarilarini tarar.", "method": "POST", "url": "/api/agents/ddi/check", "payload": {"drugs": ["warfarin", "aspirin"], "is_pregnant": False}},
    {"cat": "Klinik AI", "icon": "HPV", "name": "Smear/HPV Takip", "desc": "Smear ve HPV sonucuna gore takip plani uretir.", "method": "POST", "url": "/api/agents/smear-hpv/followup", "payload": {"patient_id": "demo", "age": 35, "smear_result": "ASCUS", "hpv_result": "positive"}},
    {"cat": "Klinik AI", "icon": "PHQ", "name": "PHQ-9 Skor", "desc": "9 cevapla depresyon tarama skorunu hesaplar.", "method": "POST", "url": "/api/agents/phq9/score", "payload": {"patient_id": "demo", "answers": [2, 2, 2, 2, 2, 2, 2, 1, 1]}},
    {"cat": "Klinik AI", "icon": "KNS", "name": "Konsey Sunum", "desc": "Olgu icin konsey sunumu taslagi hazirlar.", "method": "POST", "url": "/api/agents/konsey/build", "payload": {"patient_id": "demo", "patient_initials": "D.H.", "age": 35, "diagnosis": "Infertilite", "clinical_summary": "Primer infertilite degerlendirme", "questions": ["Tedavi plani?"]}},
    {"cat": "Klinik AI", "icon": "HAT", "name": "Hatira USG", "desc": "USG hatira gorseli ve WhatsApp taslagi hazirlar.", "method": "POST", "url": "/api/agents/hatira-usg/prepare", "payload": {"patient_id": "demo", "patient_name": "Demo Hasta", "usg_pdf_or_image": "", "consent_acknowledged": True}},
    {"cat": "Klinik AI", "icon": "PRE", "name": "Preeklampsi Risk", "desc": "Tansiyon ve klinik bulgularla risk skoru verir.", "method": "POST", "url": "/api/agents/risk/preeklampsi", "payload": {"systolic": 145, "diastolic": 95, "proteinuria": "+"}},
    {"cat": "Klinik AI", "icon": "HEL", "name": "HELLP Risk", "desc": "Trombosit, AST, ALT ve LDH ile HELLP riskini hesaplar.", "method": "POST", "url": "/api/agents/risk/hellp", "payload": {"thrombocyte": 95000, "ast": 80, "alt": 75, "ldh": 650, "bilirubin": 1.4}},
    {"cat": "Klinik AI", "icon": "BIS", "name": "Bishop Skor", "desc": "Dogum indiksiyonu icin Bishop skorunu hesaplar.", "method": "POST", "url": "/api/agents/risk/bishop", "payload": {"dilation_cm": 2, "effacement_pct": 50, "station": -2, "consistency": "medium", "position": "mid"}},
    {"cat": "Klinik AI", "icon": "VTE", "name": "VTE Padua", "desc": "VTE profilaksi ihtiyaci icin Padua skorunu hesaplar.", "method": "POST", "url": "/api/agents/risk/vte", "payload": {"age_60_plus": True, "reduced_mobility": True}},
    {"cat": "Sistem", "icon": "SES", "name": "Ses Komut Parse", "desc": "Konusulan komutu olcum, not veya navigasyona cevirir.", "method": "POST", "url": "/api/agents/voice-command/parse", "payload": {"text": "BPD 85"}},
    {"cat": "Sistem", "icon": "DR", "name": "Anti Burnout", "desc": "Gunluk tempo ve klinik yuk icin rapor uretir.", "method": "GET", "url": "/api/agents/burnout/report", "payload": {}},
    {"cat": "Sistem", "icon": "VIS", "name": "Tam Muayene Orkestrator", "desc": "Klinik vaka metninden zincir calisma baslatir.", "method": "POST", "url": "/api/agents/orchestrator/full-visit", "payload": {"case_text": "28 yas, gebelik kontrolu, sikayet yok.", "prefer": "skip", "quick": True}},
    {"cat": "Sistem", "icon": "PUB", "name": "PubMed Paket", "desc": "PubMed arastirma paketi ve ozet zinciri olusturur.", "method": "POST", "url": "/api/agents/orchestrator/pubmed-pack", "payload": {"query": "preeclampsia 2025 review", "max_articles": 1, "quick": True}},
    {"cat": "Sistem", "icon": "PIPE", "name": "USG Pipeline", "desc": "USG goruntu analizi ve hasta dosyasi zinciri icin hazir.", "method": "POST", "url": "/api/agents/orchestrator/usg-pipeline", "payload": {"demo": True, "image_path": "", "patient_key": "demo"}},
    {"cat": "Sistem", "icon": "PRT", "name": "Hasta Portal Link", "desc": "Hasta icin sureli magic-link uretir.", "method": "POST", "url": "/api/agents/portal/issue-link", "payload": {"patient_id": "demo", "phone": "05550000000"}},
    {"cat": "Sistem", "icon": "2FA", "name": "2FA Kurulum API", "desc": "Doktor kullanicisi icin TOTP kurulumu baslatir.", "method": "POST", "url": "/api/agents/2fa/setup", "payload": {}},
    {"cat": "Sistem", "icon": "STK", "name": "Stok Rapor", "desc": "Azalan ve miadi yaklasan stoklari listeler.", "method": "GET", "url": "/api/agents/stok/report", "payload": {}},
    {"cat": "Sistem", "icon": "PLG", "name": "Plugin Listesi", "desc": "Yerel plugin klasorlerini tarar ve listeler.", "method": "GET", "url": "/api/agents/plugins/list", "payload": {}},
    {"cat": "Compliance + Status", "icon": "KVK", "name": "Uyumluluk Kontrolu", "desc": "ISO/KVKK kontrol listesini ve notunu hesaplar.", "method": "GET", "url": "/api/agents/compliance/run", "payload": {}},
    {"cat": "Compliance + Status", "icon": "STS", "name": "Public Status", "desc": "Klinik servis durumunu JSON olarak verir.", "method": "GET", "url": "/api/status", "payload": {}},
    {"cat": "Compliance + Status", "icon": "PWA", "name": "Manifest", "desc": "PWA manifest dosyasini kontrol eder.", "method": "GET", "url": "/manifest.webmanifest", "payload": {}},
    {"cat": "Compliance + Status", "icon": "SW", "name": "Service Worker", "desc": "PWA service worker dosyasini kontrol eder.", "method": "GET", "url": "/sw.js", "payload": {}},
    {"cat": "Cron + Stub", "icon": "ANK", "name": "Memnuniyet Anketi", "desc": "Dunku hastalar icin anket gorevini baslatir.", "method": "POST", "url": "/api/agents/memnuniyet/survey-yesterday", "payload": {"dry_run": True}},
    {"cat": "Cron + Stub", "icon": "BD", "name": "Dogum Gunu Tebrik", "desc": "Bugunku dogum gunu mesajlarini hazirlar.", "method": "POST", "url": "/api/agents/memnuniyet/birthday-today", "payload": {"dry_run": True}},
    {"cat": "Cron + Stub", "icon": "PM", "name": "PubMed Cron", "desc": "Planli PubMed taramasini calistirir.", "method": "POST", "url": "/api/agents/pubmed-cron/scan", "payload": {"queries": ["preeclampsia"], "max_per_query": 1}},
    {"cat": "Cron + Stub", "icon": "PAY", "name": "Odeme Baslat", "desc": "Odeme saglayici stub akisina test istegi atar.", "method": "POST", "url": "/api/agents/payment/initiate", "payload": {"patient_id": "demo", "amount_try": 100, "description": "Demo islem"}},
    {"cat": "Cron + Stub", "icon": "ENB", "name": "e-Nabiz Health", "desc": "e-Nabiz/KTS entegrasyon durumunu okur.", "method": "GET", "url": "/api/agents/enabiz/health", "payload": {}},
    {"cat": "Cron + Stub", "icon": "MHR", "name": "MHRS Health", "desc": "MHRS entegrasyon saglik bilgisini okur.", "method": "GET", "url": "/api/agents/mhrs/health", "payload": {}},
    {"cat": "Cron + Stub", "icon": "MED", "name": "Medula Provizyon", "desc": "SGK provizyon stub sorgusunu calistirir.", "method": "POST", "url": "/api/agents/medula/provizyon", "payload": {"tc": "11111111110"}},
    {"cat": "Cron + Stub", "icon": "LAB", "name": "Lab Duzen", "desc": "Laboratuvar entegrasyon stub sonucunu getirir.", "method": "POST", "url": "/api/agents/lab-duzen/fetch", "payload": {"patient_tc": "11111111110"}},
    {"cat": "Cron + Stub", "icon": "IOT", "name": "IoT Bluetooth", "desc": "Bluetooth cihaz tarama stub akisina istek atar.", "method": "POST", "url": "/api/agents/iot/scan", "payload": {"timeout_sec": 2}},
]

_CORE_AGENT_CARDS = [
    {
        "cat": "Klinik Ajanlar",
        "icon": "TEL",
        "name": "YZ Telesekreter",
        "desc": "Telefon metnini randevu, iptal, bilgi veya acil sinifina ayirir.",
        "method": "POST",
        "url": "/api/agents/telesekreter/run",
        "payload": {
            "caller_phone": "+905550000000",
            "caller_name": "Demo Hasta",
            "transcript": "Adim Ayse. Yarin saat on bir icin randevu almak istiyorum.",
            "received_at": "2026-05-19 10:30",
            "duration_sec": 24,
        },
    },
    {
        "cat": "Klinik Ajanlar",
        "icon": "ON",
        "name": "Sesli Randevu Onayi",
        "desc": "Hastanin evet, hayir veya erteleme cevabini guven skoru ile siniflandirir.",
        "method": "POST",
        "url": "/api/agents/sesli_onay/run",
        "payload": {
            "appointment_id": "demo-apt-1",
            "patient_phone": "+905550000000",
            "patient_name": "Demo Hasta",
            "appointment_at": "2026-05-20 11:00",
            "spoken_response": "Evet onayliyorum, yarin saat on birde gelecegim.",
        },
    },
    {
        "cat": "Klinik Ajanlar",
        "icon": "USG",
        "name": "USG Rapor Taslak",
        "desc": "Olcumlerden Hadlock EFW ve standart USG rapor taslagi uretir.",
        "method": "POST",
        "url": "/api/agents/usg_rapor/run",
        "payload": {
            "patient_id": "demo",
            "patient_name": "Demo Hasta",
            "exam_date": "2026-05-19",
            "lmp": "2025-11-04",
            "report_type": "second_trimester",
            "measurements": [
                {"name": "BPD", "value_mm": 53},
                {"name": "HC", "value_mm": 195},
                {"name": "AC", "value_mm": 172},
                {"name": "FL", "value_mm": 37},
            ],
        },
    },
    {
        "cat": "Klinik Ajanlar",
        "icon": "ARA",
        "name": "Geri Cagirma",
        "desc": "Takip zamani gelen hastalar icin onayli hatirlatma taslagi uretir.",
        "method": "POST",
        "url": "/api/agents/geri_cagirma/run",
        "payload": {
            "channel": "whatsapp",
            "candidates": [
                {
                    "patient_id": "demo",
                    "name": "Demo Hasta",
                    "phone": "+905550000000",
                    "last_visit": "2026-04-01",
                    "next_due": "2026-05-21",
                    "reason": "Kontrol randevusu",
                    "consent_messaging": True,
                    "sent_this_month": 0,
                    "blocked": False,
                }
            ],
        },
    },
    {
        "cat": "Klinik Ajanlar",
        "icon": "BK",
        "name": "BK Sync Bekci",
        "desc": "BulutKlinik senkron durumunu, token ve hata riskini raporlar.",
        "method": "POST",
        "url": "/api/agents/bk_sync_bekci/run",
        "payload": {
            "last_success_at": "2026-05-19 09:40",
            "last_attempt_at": "2026-05-19 10:00",
            "consecutive_failures": 0,
            "auth_mode": "oauth",
            "reachable": True,
        },
    },
    {
        "cat": "Klinik Ajanlar",
        "icon": "NAS",
        "name": "NAS Yedek Izleyici",
        "desc": "Yedek klasoru ve dosya sagligini okuma modunda kontrol eder.",
        "method": "POST",
        "url": "/api/agents/nas_yedek_izleyici/run",
        "payload": {
            "nas_root": ".",
            "backup_subdir": "auto_backups",
        },
    },
    {
        "cat": "Klinik Ajanlar",
        "icon": "RX",
        "name": "Recete Hazirlayici",
        "desc": "Gecmis ilaclar ve alerjilere gore recete adaylarini guvenle taslaklar.",
        "method": "POST",
        "url": "/api/agents/recete_hazirlayici/run",
        "payload": {
            "patient_id": "demo",
            "patient_name": "Demo Hasta",
            "patient_allergies": ["penisilin"],
            "chronic_conditions": ["gebelik"],
            "visit_reason": "bulanti",
            "past_medications": [
                {
                    "name": "Folik asit",
                    "dose": "1x1",
                    "duration_days": 30,
                    "prescribed_at": "2026-04-15",
                }
            ],
            "doctor_preferred_combos": [["Folik asit"]],
            "max_suggestions": 3,
        },
    },
    {
        "cat": "Klinik Ajanlar",
        "icon": "GUN",
        "name": "Gunluk Ozet",
        "desc": "Gun kapanisi, kuyruk ve yarin hazirligi icin ozet metin uretir.",
        "method": "POST",
        "url": "/api/agents/gunluk_ozet/run",
        "payload": {
            "for_date": "2026-05-19",
            "today": {
                "seen_count": 12,
                "walkin_count": 2,
                "cancelled_count": 1,
                "no_show_count": 0,
                "appointment_total": 15,
            },
            "today_finance": {
                "cash_try": 1000,
                "card_try": 4000,
                "sgk_try": 0,
                "private_insurance_try": 0,
                "refunds_try": 0,
            },
            "queues": {
                "enabiz_pending": 1,
                "bk_pending": 0,
                "usg_drafts_pending": 2,
                "voice_triage_pending": 1,
                "voice_confirm_pending": 0,
            },
            "tomorrow": [
                {
                    "time_str": "09:30",
                    "patient_initials": "D.H.",
                    "appointment_type": "Kontrol",
                    "notes": "USG hazirligi",
                }
            ],
        },
    },
    {
        "cat": "Klinik Ajanlar",
        "icon": "TXT",
        "name": "Mojibake Bekci",
        "desc": "Kaynakta bozuk karakter sinyallerini raporlar; dosya silmez veya duzeltmez.",
        "method": "POST",
        "url": "/api/agents/mojibake_bekci/run",
        "payload": {"root": "static"},
    },
    {
        "cat": "Klinik Ajanlar",
        "icon": "PR",
        "name": "PR Reviewer",
        "desc": "Diff metnindeki riskli degisiklikleri kisa kod incelemesi olarak cikarir.",
        "method": "POST",
        "url": "/api/agents/pr_reviewer/run",
        "payload": {"diff_text": "diff --git a/demo.py b/demo.py\n+print('demo')\n"},
    },
]

_SESSION7_AGENT_ADDON = """
<style id="session7-agent-cards-css">
  .s7-head { margin: 26px 0 12px; display:flex; justify-content:space-between; gap:12px; align-items:end; flex-wrap:wrap; }
  .s7-head h2 { margin:0; font-size:18px; color:#102b45; }
  .s7-tabs { display:flex; gap:8px; flex-wrap:wrap; margin: 8px 0 16px; }
  .s7-tab { border:1px solid #bfd8e9; background:#ffffff; color:#17324a; border-radius:999px; padding:7px 11px; cursor:pointer; font-size:12px; font-weight:800; }
  .s7-tab.active { background:#0b79b7; border-color:#0b79b7; color:white; }
  .session7-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:14px; }
  .agent-card { background:#ffffff; border:1px solid #c9deed; border-radius:10px; padding:14px; box-shadow:0 12px 28px rgba(20,68,103,.08); cursor:pointer; transition:transform .14s ease, border-color .14s ease, box-shadow .14s ease; }
  .agent-card:hover { transform:translateY(-2px); border-color:#0b79b7; box-shadow:0 16px 34px rgba(20,68,103,.14); }
  .agent-card:focus-visible { outline:3px solid rgba(11,121,183,.24); outline-offset:2px; }
  .agent-card h3 { margin:0; font-size:15px; color:#075c92; }
  .agent-card p { min-height:36px; }
  .agent-ico { min-width:42px; height:32px; border-radius:9px; display:inline-flex; align-items:center; justify-content:center; background:#0b79b7; color:#fff; font-size:11px; font-weight:900; letter-spacing:.02em; }
  .agent-card-top { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
  .agent-card-actions { display:flex; gap:8px; align-items:center; margin-top:10px; }
  .agent-screen { padding:7px 11px; background:#0b79b7; color:white; border:0; border-radius:8px; cursor:pointer; font-weight:800; font-size:12px; }
  .agent-run { padding:7px 11px; background:#16824a; color:white; border:0; border-radius:8px; cursor:pointer; font-weight:800; font-size:12px; }
  .agent-copy { padding:7px 9px; background:#f5fbff; color:#17324a; border:1px solid #bfd8e9; border-radius:8px; cursor:pointer; font-size:12px; }
  .agent-result { margin-top:10px; background:#f6fbff; border:1px solid #c9deed; border-radius:8px; padding:9px; min-height:42px; max-height:220px; overflow:auto; white-space:pre-wrap; font-size:11px; color:#17324a; }
  .agent-result.ok { border-color:#16824a; }
  .agent-result.fail { border-color:#b42318; color:#8a1f15; background:#fff7f6; }
  .agent-result.runner { max-height:320px; }
  .agent-card.selected { border-color:#16824a; box-shadow:0 16px 34px rgba(22,130,74,.14); }
  .s7-runner { background:#ffffff; border:1px solid #b9d3e6; border-radius:10px; padding:14px; margin:0 0 16px; box-shadow:0 14px 32px rgba(20,68,103,.10); }
  .s7-runner-head { display:grid; grid-template-columns:minmax(220px,340px) 1fr auto; gap:12px; align-items:end; }
  .s7-runner h3 { margin:0 0 6px; font-size:14px; color:#075c92; }
  .s7-runner label { display:block; font-size:12px; color:#58708a; font-weight:800; margin:0 0 4px; }
  .s7-runner select, .s7-runner input, .s7-runner textarea { width:100%; box-sizing:border-box; border:1px solid #bfd8e9; border-radius:8px; padding:8px 10px; font:13px -apple-system, Segoe UI, Arial, sans-serif; color:#17324a; background:#f8fcff; }
  .s7-runner textarea { min-height:72px; resize:vertical; }
  .s7-form-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(220px,1fr)); gap:10px; margin-top:12px; }
  .s7-form-field.wide { grid-column:1 / -1; }
  .s7-actions { display:flex; gap:8px; align-items:center; flex-wrap:wrap; }
  .s7-hint { color:#58708a; font-size:12px; margin-top:8px; }
  .s7-status-pill { display:inline-flex; align-items:center; gap:5px; border-radius:999px; padding:3px 8px; font-size:11px; font-weight:900; white-space:nowrap; }
  .s7-status-pill.ok { background:#e6f6ee; color:#116b3d; }
  .s7-status-pill.fail { background:#fff0ee; color:#9a2117; }
  .s7-status-pill.warn { background:#fff8dd; color:#815c07; }
  @media(max-width:860px){ .s7-runner-head { grid-template-columns:1fr; } }
</style>
<section id="session7-agents">
  <div class="s7-head">
    <div>
      <h2>Calistirilabilir ajanlar</h2>
      <p style="margin:4px 0 0;color:#58708a;font-size:13px;">Eski klinik ajanlar ve yeni moduller burada tek panelden calisir.</p>
    </div>
    <a class="btn" href="/uyumluluk">Uyumluluk panosu</a>
  </div>
  <div class="s7-tabs" id="s7Tabs"></div>
  <div class="s7-runner" id="s7Runner">
    <div class="s7-runner-head">
      <div>
        <label for="s7AgentSelect">Ajan</label>
        <select id="s7AgentSelect" onchange="s7SelectAgent(Number(this.value), false)"></select>
      </div>
      <div>
        <h3 id="s7RunnerTitle">Ajan hazirlaniyor</h3>
        <div class="s7-hint" id="s7RunnerDesc">Liste yukleniyor.</div>
      </div>
      <div class="s7-actions">
        <button class="agent-run" onclick="s7RunSelected()">Calistir</button>
        <button class="agent-copy" onclick="s7LoadExample()">Ornek yukle</button>
        <button class="agent-screen" onclick="s7GoScreen(s7SelectedIdx)">Ekrana git</button>
      </div>
    </div>
    <div id="s7Form" class="s7-form-grid"></div>
    <pre class="agent-result runner" id="s7RunnerResult">(sonuc burada gorunecek)</pre>
  </div>
  <div class="session7-grid" id="session7Grid"></div>
</section>
<script id="session7-agent-cards-js">
const SESSION7_AGENT_CARDS = __SESSION7_CARDS__;
function s7Slug(v) {
  return String(v || '').toLowerCase().replace(/[^a-z0-9_]+/g, '_');
}
let s7SelectedIdx = 0;
try {
  const asked = new URLSearchParams(window.location.search).get('agent');
  if (asked) {
    const token = s7Slug(asked);
    const found = SESSION7_AGENT_CARDS.findIndex(c =>
      s7Slug(c.url).includes(token) || s7Slug(c.name).includes(token));
    if (found >= 0) s7SelectedIdx = found;
  }
} catch(e) {}
let s7ActiveCat = (SESSION7_AGENT_CARDS[s7SelectedIdx] && SESSION7_AGENT_CARDS[s7SelectedIdx].cat) || 'Klinik Ajanlar';
let s7Modules = {};
function s7Escape(v) {
  return String(v == null ? '' : v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function s7RenderTabs() {
  const cats = [...new Set(SESSION7_AGENT_CARDS.map(c => c.cat))];
  document.getElementById('s7Tabs').innerHTML = cats.map(cat =>
    '<button class="s7-tab '+(cat===s7ActiveCat?'active':'')+'" onclick="s7ActiveCat=\\''+cat+'\\';s7RenderTabs();s7RenderCards();">'+cat+'</button>'
  ).join('');
}
function s7RenderCards() {
  const cards = SESSION7_AGENT_CARDS.filter(c => c.cat === s7ActiveCat);
  document.getElementById('session7Grid').innerHTML = cards.map((c, i) => `
    <div class="agent-card" data-cat="${s7Escape(c.cat)}" data-screen="${s7Escape(c.screen_url || c.url || '')}" tabindex="0" role="link" onclick="s7GoScreen(${SESSION7_AGENT_CARDS.indexOf(c)})" onkeydown="s7KeyOpen(event, ${SESSION7_AGENT_CARDS.indexOf(c)})">
      <div class="agent-card-top"><span class="agent-ico">${s7Escape(c.icon)}</span><h3>${s7Escape(c.name)}</h3></div>
      <p>${s7Escape(c.desc)}</p>
      <div class="meta"><code>${s7Escape(c.method)}</code> <code>${s7Escape(c.url)}</code></div>
      <div class="agent-card-actions">
        <button class="agent-screen" onclick="event.stopPropagation();s7GoScreen(${SESSION7_AGENT_CARDS.indexOf(c)})">${s7Escape(c.screen_label || 'Ekrana git')}</button>
        <button class="agent-run" onclick="event.stopPropagation();s7RunCard(${SESSION7_AGENT_CARDS.indexOf(c)})">Calistir</button>
        <button class="agent-copy" onclick="event.stopPropagation();navigator.clipboard && navigator.clipboard.writeText(JSON.stringify(SESSION7_AGENT_CARDS[${SESSION7_AGENT_CARDS.indexOf(c)}].payload,null,2))">Payload kopyala</button>
      </div>
      <pre class="agent-result" id="s7res-${SESSION7_AGENT_CARDS.indexOf(c)}">(bekliyor)</pre>
    </div>`).join('');
}
function s7GoScreen(idx) {
  const c = SESSION7_AGENT_CARDS[idx] || {};
  const url = c.screen_url || c.url || '/ajanlar';
  window.location.href = url;
}
function s7KeyOpen(ev, idx) {
  if (ev.key === 'Enter' || ev.key === ' ') {
    ev.preventDefault();
    s7GoScreen(idx);
  }
}
async function s7RunCard(idx) {
  const c = SESSION7_AGENT_CARDS[idx];
  const out = document.getElementById('s7res-' + idx);
  out.className = 'agent-result';
  out.textContent = 'Calisiyor...';
  try {
    const opt = {credentials:'same-origin', headers:{'Accept':'application/json'}};
    if (c.method !== 'GET') {
      opt.method = c.method;
      opt.headers['Content-Type'] = 'application/json';
      opt.body = JSON.stringify(c.payload || {});
    }
    const r = await fetch(c.url, opt);
    const text = await r.text();
    let data;
    try { data = JSON.parse(text); }
    catch (_) { data = {status:r.status, body:text.slice(0,1600)}; }
    out.classList.add(r.ok ? 'ok' : 'fail');
    out.textContent = JSON.stringify(data, null, 2);
  } catch(e) {
    out.classList.add('fail');
    out.textContent = 'Hata: ' + e.message;
  }
}
function s7ModuleKey(c) {
  const u = String((c && c.url) || '');
  if (u.includes('/telesekreter/')) return 'telesekreter';
  if (u.includes('/sesli_onay/')) return 'sesli_onay';
  if (u.includes('/usg_rapor/')) return 'usg_rapor';
  if (u.includes('/geri_cagirma/')) return 'geri_cagirma';
  if (u.includes('/bk_sync_bekci/')) return 'bk_sync_bekci';
  if (u.includes('/nas_yedek_izleyici/')) return 'nas_yedek_izleyici';
  if (u.includes('/recete_hazirlayici/')) return 'recete_hazirlayici';
  if (u.includes('/gunluk_ozet/')) return 'gunluk_ozet';
  if (u.includes('/mojibake_bekci/')) return 'mojibake_bekci';
  if (u.includes('/pr_reviewer/')) return 'pr_reviewer';
  if (u.includes('/medgemma/')) return 'medgemma';
  if (u.includes('vision-usg')) return 'vision_usg';
  if (u.includes('/soap/')) return 'soap';
  if (u.includes('/icd10/')) return 'icd10';
  if (u.includes('/ddi/')) return 'ddi';
  if (u.includes('/smear-hpv/')) return 'smear_hpv';
  if (u.includes('/phq9/')) return 'phq9';
  if (u.includes('/konsey/')) return 'konsey';
  if (u.includes('/hatira-usg/')) return 'hatira_usg';
  if (u.includes('/risk/')) return 'risk_skor';
  if (u.includes('/voice-command/')) return 'voice_command';
  if (u.includes('/burnout/')) return 'anti_burnout';
  if (u.includes('/orchestrator/')) return 'orchestrator';
  if (u.includes('/portal/')) return 'hasta_portal';
  if (u.includes('/2fa/')) return '2fa';
  if (u.includes('/stok/')) return 'stok';
  if (u.includes('/plugins/')) return 'plugin_loader';
  if (u.includes('/memnuniyet/')) return 'memnuniyet';
  if (u.includes('/pubmed-cron/')) return 'pubmed_cron';
  if (u.includes('/payment/')) return 'payment';
  if (u.includes('/enabiz/')) return 'enabiz_kts';
  if (u.includes('/mhrs/')) return 'mhrs';
  if (u.includes('/medula/')) return 'medula';
  if (u.includes('/lab-duzen/')) return 'lab_duzen';
  if (u.includes('/iot/')) return 'iot_bluetooth';
  if (u.includes('/compliance/')) return 'compliance';
  return '';
}
function s7StatusHtml(c) {
  const key = s7ModuleKey(c);
  if (!key) return '<span class="s7-status-pill warn">api</span>';
  if (s7Modules[key] === true) return '<span class="s7-status-pill ok">aktif</span>';
  if (s7Modules[key] === false) return '<span class="s7-status-pill fail">modul yok</span>';
  return '<span class="s7-status-pill warn">kontrol</span>';
}
function s7RenderSelect() {
  const sel = document.getElementById('s7AgentSelect');
  if (!sel) return;
  sel.innerHTML = SESSION7_AGENT_CARDS.map((c, i) =>
    '<option value="'+i+'">'+s7Escape(c.cat + ' - ' + c.name)+'</option>'
  ).join('');
  sel.value = String(s7SelectedIdx);
}
function s7FieldLabel(key) {
  return String(key || '').replace(/_/g, ' ').replace(/\\b\\w/g, m => m.toUpperCase());
}
function s7FieldInput(key, value) {
  const id = 's7fld_' + String(key).replace(/[^a-zA-Z0-9_]/g, '_');
  const label = s7FieldLabel(key);
  const wideKeys = /note|text|case|summary|questions|drugs|answers|payload|diff|query|path|image/i;
  const wide = wideKeys.test(key) || typeof value === 'object';
  if (typeof value === 'boolean') {
    return '<div class="s7-form-field"><label><input id="'+id+'" data-key="'+s7Escape(key)+'" data-type="bool" type="checkbox" '+(value?'checked':'')+'> '+s7Escape(label)+'</label></div>';
  }
  if (typeof value === 'number') {
    return '<div class="s7-form-field"><label for="'+id+'">'+s7Escape(label)+'</label><input id="'+id+'" data-key="'+s7Escape(key)+'" data-type="number" type="number" step="any" value="'+s7Escape(value)+'"></div>';
  }
  if (Array.isArray(value) || (value && typeof value === 'object')) {
    return '<div class="s7-form-field wide"><label for="'+id+'">'+s7Escape(label)+' JSON</label><textarea id="'+id+'" data-key="'+s7Escape(key)+'" data-type="json">'+s7Escape(JSON.stringify(value, null, 2))+'</textarea></div>';
  }
  if (wide) {
    return '<div class="s7-form-field wide"><label for="'+id+'">'+s7Escape(label)+'</label><textarea id="'+id+'" data-key="'+s7Escape(key)+'" data-type="text">'+s7Escape(value)+'</textarea></div>';
  }
  return '<div class="s7-form-field"><label for="'+id+'">'+s7Escape(label)+'</label><input id="'+id+'" data-key="'+s7Escape(key)+'" data-type="text" type="text" value="'+s7Escape(value)+'"></div>';
}
function s7RenderForm() {
  const c = SESSION7_AGENT_CARDS[s7SelectedIdx] || SESSION7_AGENT_CARDS[0] || {};
  const title = document.getElementById('s7RunnerTitle');
  const desc = document.getElementById('s7RunnerDesc');
  const form = document.getElementById('s7Form');
  if (!title || !desc || !form) return;
  title.innerHTML = '<span class="agent-ico" style="margin-right:8px;vertical-align:middle">'+s7Escape(c.icon || 'AI')+'</span>' + s7Escape(c.name || 'Ajan') + ' ' + s7StatusHtml(c);
  desc.textContent = (c.desc || '') + ' | ' + (c.method || 'GET') + ' ' + (c.url || '');
  const payload = c.payload || {};
  const keys = Object.keys(payload);
  form.innerHTML = keys.length
    ? keys.map(k => s7FieldInput(k, payload[k])).join('')
    : '<div class="s7-hint">Bu ajan ek bilgi istemeden calisir.</div>';
  const sel = document.getElementById('s7AgentSelect');
  if (sel) sel.value = String(s7SelectedIdx);
  document.querySelectorAll('.agent-card').forEach(el => {
    el.classList.toggle('selected', Number(el.dataset.idx) === s7SelectedIdx);
  });
}
function s7CollectPayload() {
  const out = {};
  document.querySelectorAll('#s7Form [data-key]').forEach(el => {
    const key = el.getAttribute('data-key');
    const type = el.getAttribute('data-type');
    if (type === 'bool') out[key] = !!el.checked;
    else if (type === 'number') out[key] = Number(el.value || 0);
    else if (type === 'json') {
      try { out[key] = JSON.parse(el.value || 'null'); }
      catch(e) { throw new Error(key + ' JSON hatali: ' + e.message); }
    } else {
      out[key] = el.value;
    }
  });
  return out;
}
function s7SelectAgent(idx, scrollIt) {
  if (!Number.isFinite(idx) || !SESSION7_AGENT_CARDS[idx]) idx = 0;
  s7SelectedIdx = idx;
  s7ActiveCat = SESSION7_AGENT_CARDS[idx].cat || s7ActiveCat;
  s7RenderTabs();
  s7RenderCards();
  s7RenderForm();
  if (scrollIt !== false) {
    document.getElementById('s7Runner').scrollIntoView({behavior:'smooth', block:'start'});
  }
}
function s7LoadExample() {
  s7RenderForm();
  const out = document.getElementById('s7RunnerResult');
  out.className = 'agent-result runner';
  out.textContent = 'Ornek degerler yuklendi.';
}
function s7RenderCards() {
  const cards = SESSION7_AGENT_CARDS.filter(c => c.cat === s7ActiveCat);
  document.getElementById('session7Grid').innerHTML = cards.map((c) => {
    const idx = SESSION7_AGENT_CARDS.indexOf(c);
    return `
    <div class="agent-card ${idx===s7SelectedIdx?'selected':''}" data-idx="${idx}" data-cat="${s7Escape(c.cat)}" tabindex="0" role="button" onclick="s7SelectAgent(${idx})" onkeydown="s7KeyOpen(event, ${idx})">
      <div class="agent-card-top"><span class="agent-ico">${s7Escape(c.icon)}</span><h3>${s7Escape(c.name)}</h3>${s7StatusHtml(c)}</div>
      <p>${s7Escape(c.desc)}</p>
      <div class="meta"><code>${s7Escape(c.method)}</code> <code>${s7Escape(c.url)}</code></div>
      <div class="agent-card-actions">
        <button class="agent-run" onclick="event.stopPropagation();s7SelectAgent(${idx})">Kullan</button>
        <button class="agent-run" onclick="event.stopPropagation();s7RunCard(${idx})">Ornekle calistir</button>
        <button class="agent-screen" onclick="event.stopPropagation();s7GoScreen(${idx})">${s7Escape(c.screen_label || 'Ekrana git')}</button>
        <button class="agent-copy" onclick="event.stopPropagation();navigator.clipboard && navigator.clipboard.writeText(JSON.stringify(SESSION7_AGENT_CARDS[${idx}].payload,null,2))">JSON kopyala</button>
      </div>
      <pre class="agent-result" id="s7res-${idx}">(bekliyor)</pre>
    </div>`;
  }).join('');
}
function s7KeyOpen(ev, idx) {
  if (ev.key === 'Enter' || ev.key === ' ') {
    ev.preventDefault();
    s7SelectAgent(idx);
  }
}
async function s7CallAgent(c, payload) {
  const opt = {credentials:'same-origin', headers:{'Accept':'application/json'}};
  if (c.method !== 'GET') {
    opt.method = c.method;
    opt.headers['Content-Type'] = 'application/json';
    opt.body = JSON.stringify(payload || {});
  }
  const r = await fetch(c.url, opt);
  const text = await r.text();
  let data;
  try { data = JSON.parse(text); }
  catch (_) { data = {status:r.status, body:text.slice(0,1600)}; }
  return {ok:r.ok, data:data};
}
async function s7RunCard(idx) {
  const c = SESSION7_AGENT_CARDS[idx];
  const out = document.getElementById('s7res-' + idx);
  out.className = 'agent-result';
  out.textContent = 'Calisiyor...';
  try {
    const res = await s7CallAgent(c, c.payload || {});
    out.classList.add(res.ok ? 'ok' : 'fail');
    out.textContent = JSON.stringify(res.data, null, 2);
  } catch(e) {
    out.classList.add('fail');
    out.textContent = 'Hata: ' + e.message;
  }
}
async function s7RunSelected() {
  const c = SESSION7_AGENT_CARDS[s7SelectedIdx];
  const out = document.getElementById('s7RunnerResult');
  out.className = 'agent-result runner';
  out.textContent = 'Calisiyor...';
  try {
    const payload = s7CollectPayload();
    const res = await s7CallAgent(c, payload);
    out.classList.add(res.ok ? 'ok' : 'fail');
    out.textContent = JSON.stringify(res.data, null, 2);
    const cardOut = document.getElementById('s7res-' + s7SelectedIdx);
    if (cardOut) {
      cardOut.className = 'agent-result ' + (res.ok ? 'ok' : 'fail');
      cardOut.textContent = JSON.stringify(res.data, null, 2);
    }
  } catch(e) {
    out.classList.add('fail');
    out.textContent = 'Hata: ' + e.message;
  }
}
async function s7LoadManifestStatus() {
  try {
    const r = await fetch('/api/agents', {credentials:'same-origin'});
    const d = await r.json();
    s7Modules = (d && d.modules) || {};
    s7RenderCards();
    s7RenderForm();
  } catch(e) {}
}
s7RenderSelect();
s7RenderTabs();
s7RenderCards();
s7RenderForm();
s7LoadManifestStatus();
</script>
"""

_SESSION7_SCREEN_ROUTES = {
    "YZ Telesekreter": "/yz-telefon-diyalog",
    "Sesli Randevu Onayi": "/randevular",
    "USG Rapor Taslak": "/hasta/aktif/usg-rapor-taslak",
    "Geri Cagirma": "/toplu-hatirlatma",
    "BK Sync Bekci": "/bulutklinik-merkez",
    "NAS Yedek Izleyici": "/yedekleme-merkezi",
    "Recete Hazirlayici": "/recete-gunluk-kontrol",
    "Gunluk Ozet": "/gun-plani",
    "Mojibake Bekci": "/sistem-durumu",
    "PR Reviewer": "/calisan-isler",
    "MedGemma Klinik YZ": "/medgemma-klinik-yz",
    "USG Vision": "/hastalar",
    "SOAP Not": "/yz-konsultasyon",
    "ICD-10 Oneri": "/yz-konsultasyon",
    "Ilac Etkilesim": "/ilac-guvenlik",
    "Smear/HPV Takip": "/hastalar",
    "PHQ-9 Skor": "/hastalar",
    "Konsey Sunum": "/yz-konsultasyon",
    "Hatira USG": "/hasta-portal",
    "Preeklampsi Risk": "/riskli-gebelik",
    "HELLP Risk": "/riskli-gebelik",
    "Bishop Skor": "/riskli-gebelik",
    "VTE Padua": "/riskli-gebelik",
    "Ses Komut Parse": "/akilli-dialog",
    "Anti Burnout": "/gun-plani",
    "Tam Muayene Orkestrator": "/yz-konsultasyon",
    "PubMed Paket": "/pubmed-tarama",
    "USG Pipeline": "/hastalar",
    "Hasta Portal Link": "/hasta-portal",
    "2FA Kurulum API": "/2fa-setup",
    "Stok Rapor": "/stok",
    "Plugin Listesi": "/ajanlar",
    "Uyumluluk Kontrolu": "/uyumluluk",
    "Public Status": "/status",
    "Manifest": "/manifest.webmanifest",
    "Service Worker": "/sw.js",
    "Memnuniyet Anketi": "/calisan-isler",
    "Dogum Gunu Tebrik": "/calisan-isler",
    "PubMed Cron": "/pubmed-tarama",
    "Odeme Baslat": "/calisan-isler",
    "e-Nabiz Health": "/enabiz",
    "MHRS Health": "/randevular",
    "Medula Provizyon": "/calisan-isler",
    "Lab Duzen": "/enabiz",
    "IoT Bluetooth": "/sistem-durumu",
}


def _session7_dashboard_cards() -> List[Dict[str, Any]]:
    cards: List[Dict[str, Any]] = []
    for card in (_CORE_AGENT_CARDS + _SESSION7_AGENT_CARDS):
        item = dict(card)
        screen_url = _SESSION7_SCREEN_ROUTES.get(str(item.get("name") or "").strip())
        if screen_url:
            item["screen_url"] = screen_url
            item["screen_label"] = "Ekrana git"
        else:
            item["screen_url"] = str(item.get("url") or "/ajanlar")
            item["screen_label"] = "API ac"
        cards.append(item)
    return cards


_AGENTS_PAGE = _AGENTS_PAGE.replace(
    '<h2 style="margin-top: 28px; font-size: 16px;">Manifest</h2>',
    _SESSION7_AGENT_ADDON.replace(
        "__SESSION7_CARDS__",
        json.dumps(_session7_dashboard_cards(), ensure_ascii=True)
    ) + '<h2 style="margin-top: 28px; font-size: 16px;">Manifest</h2>'
)


@agents_bp.route("/ajanlar/", methods=["GET"])
@agents_bp.route("/ajanlar", methods=["GET"])
def ajanlar_dashboard():
    auth = _require_session()
    if auth:
        return auth
    return render_template_string(_AGENTS_PAGE)


# --- 10 ajan endpointleri ---

@agents_bp.route("/api/agents/telesekreter/run", methods=["POST"])
def run_telesekreter():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(telesekreter_mod, "telesekreter")
    if err:
        return err
    p = _payload()
    call = telesekreter_mod.CallRecord(
        caller_phone=str(p.get("caller_phone") or ""),
        transcript=str(p.get("transcript") or ""),
        received_at=str(p.get("received_at") or ""),
        duration_sec=int(p.get("duration_sec") or 0),
        caller_name=p.get("caller_name"),
    )
    return _wrap_call("telesekreter", telesekreter_mod.parse_call, {"call": call})


@agents_bp.route("/api/agents/sesli_onay/run", methods=["POST"])
def run_sesli_onay():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(sesli_onay_mod, "sesli_onay")
    if err:
        return err
    p = _payload()
    req = sesli_onay_mod.ConfirmationRequest(
        appointment_id=str(p.get("appointment_id") or ""),
        patient_phone=str(p.get("patient_phone") or ""),
        patient_name=str(p.get("patient_name") or ""),
        appointment_at=str(p.get("appointment_at") or ""),
        spoken_response=str(p.get("spoken_response") or ""),
    )
    return _wrap_call("sesli_onay", sesli_onay_mod.decide, {"request": req})


@agents_bp.route("/api/agents/usg_rapor/run", methods=["POST"])
def run_usg_rapor():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(usg_rapor_mod, "usg_rapor")
    if err:
        return err
    p = _payload()
    measurements_raw = p.get("measurements") or []
    measurements = []
    for m in measurements_raw:
        if isinstance(m, dict):
            measurements.append(usg_rapor_mod.Measurement(
                name=str(m.get("name") or ""),
                value_mm=float(m.get("value_mm") or 0),
                notes=str(m.get("notes") or ""),
            ))
    data = usg_rapor_mod.USGInput(
        patient_id=str(p.get("patient_id") or ""),
        patient_name=str(p.get("patient_name") or ""),
        exam_date=str(p.get("exam_date") or ""),
        lmp=p.get("lmp"),
        measurements=measurements,
        report_type=str(p.get("report_type") or "second_trimester"),
        operator=str(p.get("operator") or "Op. Dr. Hakan YAZ"),
        device=str(p.get("device") or "GE Voluson"),
    )
    return _wrap_call("usg_rapor", usg_rapor_mod.build_draft, {"data": data})


@agents_bp.route("/api/agents/geri_cagirma/run", methods=["POST"])
def run_geri_cagirma():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(geri_cagirma_mod, "geri_cagirma")
    if err:
        return err
    p = _payload()
    candidates_raw = p.get("candidates") or []
    candidates = []
    for c in candidates_raw:
        if not isinstance(c, dict):
            continue
        candidates.append(geri_cagirma_mod.PatientCandidate(
            patient_id=str(c.get("patient_id") or ""),
            name=str(c.get("name") or ""),
            phone=str(c.get("phone") or ""),
            last_visit=c.get("last_visit"),
            next_due=c.get("next_due"),
            reason=str(c.get("reason") or ""),
            consent_messaging=bool(c.get("consent_messaging") or False),
            sent_this_month=int(c.get("sent_this_month") or 0),
            blocked=bool(c.get("blocked") or False),
        ))
    channel = str(p.get("channel") or "whatsapp")
    return _wrap_call("geri_cagirma", geri_cagirma_mod.bulk_schedule,
                       {"candidates": candidates, "channel": channel})


@agents_bp.route("/api/agents/bk_sync_bekci/run", methods=["POST"])
def run_bk_sync():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(bk_sync_mod, "bk_sync_bekci")
    if err:
        return err
    p = _payload()
    probe = bk_sync_mod.SyncProbe(
        last_success_at=p.get("last_success_at"),
        last_attempt_at=p.get("last_attempt_at"),
        consecutive_failures=int(p.get("consecutive_failures") or 0),
        auth_mode=str(p.get("auth_mode") or "oauth"),
        last_error=p.get("last_error"),
        token_expires_at=p.get("token_expires_at"),
        reachable=bool(p.get("reachable", True)),
    )
    return _wrap_call("bk_sync_bekci", bk_sync_mod.check_status, {"probe": probe})


@agents_bp.route("/api/agents/nas_yedek_izleyici/run", methods=["POST"])
def run_nas_izleyici():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(nas_mod, "nas_yedek_izleyici")
    if err:
        return err
    p = _payload()
    return _wrap_call("nas_yedek_izleyici", nas_mod.check_health, {
        "nas_root": str(p.get("nas_root") or ""),
        "backup_subdir": str(p.get("backup_subdir") or "auto_backups"),
    })


@agents_bp.route("/api/agents/recete_hazirlayici/run", methods=["POST"])
def run_recete():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(recete_mod, "recete_hazirlayici")
    if err:
        return err
    p = _payload()
    past_raw = p.get("past_medications") or []
    past = []
    for m in past_raw:
        if not isinstance(m, dict):
            continue
        past.append(recete_mod.PastMedication(
            name=str(m.get("name") or ""),
            dose=str(m.get("dose") or ""),
            duration_days=int(m.get("duration_days") or 0),
            prescribed_at=str(m.get("prescribed_at") or ""),
        ))
    req = recete_mod.DraftRequest(
        patient_id=str(p.get("patient_id") or ""),
        patient_name=str(p.get("patient_name") or ""),
        patient_allergies=[str(a) for a in (p.get("patient_allergies") or [])],
        chronic_conditions=[str(c) for c in (p.get("chronic_conditions") or [])],
        past_medications=past,
        visit_reason=str(p.get("visit_reason") or ""),
        doctor_preferred_combos=[
            [str(x) for x in combo] for combo in (p.get("doctor_preferred_combos") or [])
            if isinstance(combo, list)
        ],
        max_suggestions=int(p.get("max_suggestions") or 5),
    )
    return _wrap_call("recete_hazirlayici", recete_mod.build_draft, {"req": req})


@agents_bp.route("/api/agents/gunluk_ozet/run", methods=["POST"])
def run_gunluk_ozet():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(ozet_mod, "gunluk_ozet")
    if err:
        return err
    p = _payload()
    today = p.get("today") or {}
    yest = p.get("yesterday")
    fin = p.get("today_finance") or {}
    q = p.get("queues") or {}
    tomorrow_raw = p.get("tomorrow") or []
    tomorrow = []
    for s in tomorrow_raw:
        if not isinstance(s, dict):
            continue
        tomorrow.append(ozet_mod.TomorrowSlot(
            time_str=str(s.get("time_str") or ""),
            patient_initials=str(s.get("patient_initials") or ""),
            appointment_type=str(s.get("appointment_type") or ""),
            notes=str(s.get("notes") or ""),
        ))
    data = ozet_mod.SummaryInput(
        for_date=str(p.get("for_date") or ""),
        today=ozet_mod.DailyStats(**{k: int(today.get(k) or 0) for k in (
            "seen_count", "walkin_count", "cancelled_count", "no_show_count", "appointment_total")}),
        yesterday=(ozet_mod.DailyStats(**{k: int(yest.get(k) or 0) for k in (
            "seen_count", "walkin_count", "cancelled_count", "no_show_count", "appointment_total")})
                   if isinstance(yest, dict) else None),
        today_finance=ozet_mod.FinanceSnapshot(**{k: float(fin.get(k) or 0) for k in (
            "cash_try", "card_try", "sgk_try", "private_insurance_try", "refunds_try")}),
        queues=ozet_mod.PendingQueues(**{k: int(q.get(k) or 0) for k in (
            "enabiz_pending", "bk_pending", "usg_drafts_pending",
            "voice_triage_pending", "voice_confirm_pending")}),
        tomorrow=tomorrow,
    )
    return _wrap_call("gunluk_ozet", ozet_mod.build_summary, {"data": data})


@agents_bp.route("/api/agents/mojibake_bekci/run", methods=["POST"])
def run_mojibake():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(mojibake_mod, "mojibake_bekci")
    if err:
        return err
    p = _payload()
    root = str(p.get("root") or ".")
    return _wrap_call("mojibake_bekci", mojibake_mod.scan_tree, {"root": root})


@agents_bp.route("/api/agents/pr_reviewer/run", methods=["POST"])
def run_pr_reviewer():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(pr_mod, "pr_reviewer")
    if err:
        return err
    p = _payload()
    diff_text = str(p.get("diff_text") or "")
    return _wrap_call("pr_reviewer", pr_mod.review_diff, {"diff_text": diff_text})


# === MedGemma Klinik YZ ===================================================

_MEDGEMMA_BACKEND_ALLOWED = {"auto", "transformers", "endpoint", "openai_compat", "ollama"}


def _medgemma_clean_line_value(value: Any, max_len: int = 240) -> str:
    text = str(value or "").strip().replace("\r", " ").replace("\n", " ")
    return text[:max_len]


def _medgemma_bool_env(value: Any, default: bool = False) -> str:
    return "1" if _as_bool(value, default) else "0"


def _medgemma_settings_payload() -> Dict[str, Any]:
    cfg: Dict[str, Any] = {}
    try:
        if medgemma_mod and hasattr(medgemma_mod, "medgemma_config"):
            raw_cfg = medgemma_mod.medgemma_config()
            if isinstance(raw_cfg, dict):
                cfg = dict(raw_cfg)
    except Exception:
        cfg = {}
    return {
        "enabled": bool(cfg.get("enabled")) if cfg else _as_bool(_config_or_env("YAZKLINIK_MEDGEMMA_ENABLED", "0")),
        "backend": str(cfg.get("backend") or _config_or_env("YAZKLINIK_MEDGEMMA_BACKEND", "auto")),
        "model": str(cfg.get("model") or _config_or_env("YAZKLINIK_MEDGEMMA_MODEL", "google/medgemma-4b-it")),
        "text_model": str(cfg.get("text_model") or _config_or_env("YAZKLINIK_MEDGEMMA_TEXT_MODEL", "google/medgemma-27b-text-it")),
        "newer_fast_model": str(cfg.get("newer_fast_model") or _config_or_env("YAZKLINIK_MEDGEMMA_FAST_MODEL", "google/medgemma-1.5-4b-it")),
        "endpoint": str(cfg.get("endpoint") or _config_or_env("YAZKLINIK_MEDGEMMA_ENDPOINT", "")),
        "remote_allowed": bool(cfg.get("remote_allowed")) if cfg else _as_bool(_config_or_env("YAZKLINIK_MEDGEMMA_ALLOW_REMOTE", "0")),
        "device": str(cfg.get("device") or _config_or_env("YAZKLINIK_MEDGEMMA_DEVICE", "auto")),
        "dtype": str(cfg.get("dtype") or _config_or_env("YAZKLINIK_MEDGEMMA_DTYPE", "auto")),
        "max_new_tokens": int(cfg.get("max_new_tokens") or int(_config_or_env("YAZKLINIK_MEDGEMMA_MAX_NEW_TOKENS", "512") or "512")),
        "load_on_demand": bool(cfg.get("load_on_demand")) if cfg else _as_bool(_config_or_env("YAZKLINIK_MEDGEMMA_LOAD_ON_DEMAND", "1"), True),
    }


def _medgemma_save_env_updates(updates: Dict[str, str]) -> None:
    if not updates:
        return
    cfg_path = Path(__file__).resolve().parent / "config.env"
    lines: List[str] = []
    try:
        if cfg_path.exists():
            lines = cfg_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        lines = []
    replaced: Dict[str, bool] = {k: False for k in updates.keys()}
    out: List[str] = []
    for raw in lines:
        line = str(raw)
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in line:
            key = line.split("=", 1)[0].strip()
            if key in updates:
                out.append(f"{key}={updates[key]}")
                replaced[key] = True
                continue
        out.append(line)
    missing = [k for k, done in replaced.items() if not done]
    if missing:
        out.append("")
        out.append("# MedGemma panel ayarlari")
        for key in missing:
            out.append(f"{key}={updates[key]}")
    cfg_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def _medgemma_apply_runtime_updates(updates: Dict[str, str]) -> None:
    global _ROOT_CONFIG_CACHE
    _ROOT_CONFIG_CACHE = None
    for key, value in updates.items():
        os.environ[str(key)] = str(value)
    try:
        if medgemma_mod is not None and hasattr(medgemma_mod, "_CONFIG_CACHE"):
            setattr(medgemma_mod, "_CONFIG_CACHE", None)
    except Exception:
        pass


@agents_bp.route("/api/agents/medgemma/health", methods=["GET"])
def medgemma_health():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(medgemma_mod, "medgemma")
    if err:
        return err
    try:
        result = medgemma_mod.health_check()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "agent": "medgemma", "error": str(exc)}), 500
    result["task_model_recommendations"] = _medgemma_task_recommendations()
    result["task_assignment_recommendations"] = _medgemma_task_assignment_recommendations()
    result["binding"] = _medgemma_binding_read()
    return jsonify({"ok": True, "agent": "medgemma", "result": result})


@agents_bp.route("/api/agents/medgemma/settings", methods=["GET", "POST"])
def medgemma_settings():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(medgemma_mod, "medgemma")
    if err:
        return err
    if request.method == "GET":
        return jsonify({"ok": True, "agent": "medgemma", "settings": _medgemma_settings_payload()})

    p = _payload()
    updates: Dict[str, str] = {}
    if "enabled" in p:
        updates["YAZKLINIK_MEDGEMMA_ENABLED"] = _medgemma_bool_env(p.get("enabled"), False)
    if "backend" in p:
        backend = _medgemma_clean_line_value(p.get("backend"), 40).lower()
        if backend not in _MEDGEMMA_BACKEND_ALLOWED:
            return jsonify({
                "ok": False,
                "agent": "medgemma",
                "error": "invalid_backend",
                "allowed": sorted(_MEDGEMMA_BACKEND_ALLOWED),
            }), 400
        updates["YAZKLINIK_MEDGEMMA_BACKEND"] = backend
    if "model" in p:
        updates["YAZKLINIK_MEDGEMMA_MODEL"] = _medgemma_clean_line_value(p.get("model"), 180)
    if "text_model" in p:
        updates["YAZKLINIK_MEDGEMMA_TEXT_MODEL"] = _medgemma_clean_line_value(p.get("text_model"), 180)
    if "newer_fast_model" in p:
        updates["YAZKLINIK_MEDGEMMA_FAST_MODEL"] = _medgemma_clean_line_value(p.get("newer_fast_model"), 180)
    if "endpoint" in p:
        endpoint = _medgemma_clean_line_value(p.get("endpoint"), 500)
        if endpoint and not (endpoint.startswith("http://") or endpoint.startswith("https://")):
            return jsonify({"ok": False, "agent": "medgemma", "error": "invalid_endpoint"}), 400
        updates["YAZKLINIK_MEDGEMMA_ENDPOINT"] = endpoint
    if "remote_allowed" in p:
        updates["YAZKLINIK_MEDGEMMA_ALLOW_REMOTE"] = _medgemma_bool_env(p.get("remote_allowed"), False)
    if "device" in p:
        updates["YAZKLINIK_MEDGEMMA_DEVICE"] = _medgemma_clean_line_value(p.get("device"), 80)
    if "dtype" in p:
        updates["YAZKLINIK_MEDGEMMA_DTYPE"] = _medgemma_clean_line_value(p.get("dtype"), 80)
    if "max_new_tokens" in p:
        try:
            tokens = int(str(p.get("max_new_tokens") or "512").strip())
        except Exception:
            return jsonify({"ok": False, "agent": "medgemma", "error": "invalid_max_new_tokens"}), 400
        tokens = max(64, min(tokens, 8192))
        updates["YAZKLINIK_MEDGEMMA_MAX_NEW_TOKENS"] = str(tokens)
    if "load_on_demand" in p:
        updates["YAZKLINIK_MEDGEMMA_LOAD_ON_DEMAND"] = _medgemma_bool_env(p.get("load_on_demand"), True)

    if not updates:
        return jsonify({"ok": True, "agent": "medgemma", "updated": [], "settings": _medgemma_settings_payload()})

    try:
        _medgemma_save_env_updates(updates)
        _medgemma_apply_runtime_updates(updates)
        _safe_audit("agents:medgemma_settings_update", {"updated_keys": sorted(updates.keys())})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "agent": "medgemma", "error": f"{type(exc).__name__}: {exc}"}), 500

    return jsonify({
        "ok": True,
        "agent": "medgemma",
        "updated": sorted(updates.keys()),
        "settings": _medgemma_settings_payload(),
        "restart_recommended": True,
        "message": "Ayarlar kaydedildi. Tum servislerde kesin uygulama icin D700 yeniden baslatma onerilir.",
    })


@agents_bp.route("/api/agents/medgemma/context", methods=["GET", "POST", "DELETE"])
def medgemma_context():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(medgemma_mod, "medgemma")
    if err:
        return err
    if request.method == "GET":
        return jsonify({
            "ok": True,
            "agent": "medgemma",
            "result": _medgemma_binding_read(),
            "task_model_recommendations": _medgemma_task_recommendations(),
            "task_assignment_recommendations": _medgemma_task_assignment_recommendations(),
        })
    if request.method == "DELETE":
        out = _medgemma_binding_clear()
        _safe_audit("agents:medgemma_context_clear", {})
        return jsonify({
            "ok": True,
            "agent": "medgemma",
            "result": out,
            "task_model_recommendations": _medgemma_task_recommendations(),
            "task_assignment_recommendations": _medgemma_task_assignment_recommendations(),
        })
    p = _payload()
    current = _medgemma_binding_read()
    if "task" in p and str(p.get("task") or "").strip():
        current["task"] = str(p.get("task") or "").strip()
    if "patient_context" in p:
        current["patient_context"] = str(p.get("patient_context") or "")
    if "yz_definition" in p:
        current["yz_definition"] = str(p.get("yz_definition") or "")
    if "assignment" in p:
        current["assignment"] = str(p.get("assignment") or "")
    if "prefer_model" in p:
        current["prefer_model"] = str(p.get("prefer_model") or "")
    if "task_model_overrides" in p:
        current["task_model_overrides"] = _normalize_task_model_overrides(p.get("task_model_overrides"))
    if "use_recommended_model" in p:
        task_key = str(current.get("task") or "clinical_note").strip()
        overrides = dict(current.get("task_model_overrides") or {})
        if _as_bool(p.get("use_recommended_model"), False):
            overrides.pop(task_key, None)
            current["prefer_model"] = ""
        else:
            model_text = str(current.get("prefer_model") or "").strip()
            if model_text:
                overrides[task_key] = model_text
        current["task_model_overrides"] = overrides
    if "preview_only" in p:
        current["preview_only"] = _as_bool(p.get("preview_only"), current.get("preview_only", True))
    if "sticky_context" in p:
        current["sticky_context"] = _as_bool(p.get("sticky_context"), current.get("sticky_context", True))
    saved = _medgemma_binding_write(current)
    _safe_audit("agents:medgemma_context_save", {"task": saved.get("task"), "sticky_context": bool(saved.get("sticky_context"))})
    return jsonify({
        "ok": True,
        "agent": "medgemma",
        "result": saved,
        "task_model_recommendations": _medgemma_task_recommendations(),
        "task_assignment_recommendations": _medgemma_task_assignment_recommendations(),
    })


@agents_bp.route("/api/agents/medgemma/analyze", methods=["POST"])
def medgemma_analyze():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(medgemma_mod, "medgemma")
    if err:
        return err
    p = _payload()
    if _as_bool(p.get("clear_context"), False):
        _medgemma_binding_clear()
    binding = _medgemma_binding_read()
    sticky_context = _as_bool(p.get("sticky_context"), bool(binding.get("sticky_context", True)))

    task_raw = str(p.get("task") or "").strip()
    task = task_raw or str(binding.get("task") or "clinical_note")
    note = str(p.get("note") or "")
    patient_context_raw = str(p.get("patient_context") or "").strip()
    yz_definition_raw = str(p.get("yz_definition") or "").strip()
    assignment_raw = str(p.get("assignment") or "").strip()
    prefer_model_raw = str(p.get("prefer_model") or "").strip()
    use_recommended_model = _as_bool(p.get("use_recommended_model"), False)
    task_model_overrides = dict(binding.get("task_model_overrides") or {})
    if "task_model_overrides" in p:
        task_model_overrides = _normalize_task_model_overrides(p.get("task_model_overrides"))
    preview_only = _as_bool(p.get("preview_only"), bool(binding.get("preview_only", True)))
    image_path = str(p.get("image_path") or "")

    active_patient_context = patient_context_raw or str(binding.get("patient_context") or "")
    active_yz_definition = yz_definition_raw or str(binding.get("yz_definition") or "")
    active_assignment = assignment_raw or str(binding.get("assignment") or "")
    task_override_model = str(task_model_overrides.get(task) or "").strip()
    global_bound_model = str(binding.get("prefer_model") or "").strip()
    if use_recommended_model:
        task_model_overrides.pop(task, None)
    if prefer_model_raw and not use_recommended_model:
        task_model_overrides[task] = prefer_model_raw
    active_prefer_model = ""
    if not use_recommended_model:
        active_prefer_model = prefer_model_raw or task_override_model or global_bound_model

    merged_context_parts: List[str] = []
    if active_yz_definition:
        merged_context_parts.append(f"YZ tanimi:\n{active_yz_definition}")
    if active_assignment:
        merged_context_parts.append(f"Gorevlendirme:\n{active_assignment}")
    if active_patient_context:
        merged_context_parts.append(f"Hasta baglami:\n{active_patient_context}")
    merged_context = "\n\n".join(merged_context_parts).strip()

    try:
        req = medgemma_mod.MedGemmaRequest(
            task=task,
            note=note,
            patient_context=merged_context,
            image_path=image_path,
            prefer_model=active_prefer_model,
            preview_only=preview_only,
        )
        result = medgemma_mod.analyze(req)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "agent": "medgemma", "error": str(exc)}), 500
    if sticky_context:
        binding = _medgemma_binding_write({
            "task": task,
            "patient_context": active_patient_context,
            "yz_definition": active_yz_definition,
            "assignment": active_assignment,
            "prefer_model": active_prefer_model,
            "task_model_overrides": task_model_overrides,
            "preview_only": preview_only,
            "sticky_context": sticky_context,
        })
    result["binding"] = {
        "sticky_context": sticky_context,
        "use_recommended_model": bool(use_recommended_model),
        "active": binding,
        "task_model_recommendations": _medgemma_task_recommendations(),
        "task_assignment_recommendations": _medgemma_task_assignment_recommendations(),
        "recommended_model_for_task": _medgemma_recommended_model(task=task, has_image=bool(image_path)),
        "merged_context_used": merged_context[:4000],
    }
    _safe_audit("agents:medgemma_analyze", {
        "task": task,
        "preview_only": bool(preview_only),
        "chars": len(note),
        "sticky_context": bool(sticky_context),
    })
    return jsonify({"ok": bool(result.get("ok")), "agent": "medgemma", "result": result})


@agents_bp.route("/medgemma-klinik-yz", methods=["GET"])
def medgemma_page():
    auth = _require_session()
    if auth:
        return auth
    return render_template_string(_MEDGEMMA_PAGE)


@agents_bp.route("/medgemma-modul", methods=["GET"])
def medgemma_module_page():
    return medgemma_page()


_MEDGEMMA_PAGE = r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>MedGemma Klinik YZ - YazKlinik</title>
<style>
  :root{--ink:#13263d;--muted:#5d7084;--line:#c7dceb;--blue:#1268a8;--teal:#0c8b7b;--bg:#eef7f8;--surface:#fff;--warn:#b47600;--err:#b42318;--ok:#16824a}
  body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;margin:0;padding:24px;background:linear-gradient(135deg,#f6fbff,#eaf7f3);color:var(--ink)}
  .shell{max-width:1180px;margin:0 auto}
  .hero{display:grid;grid-template-columns:1.2fr .8fr;gap:16px;align-items:stretch;margin-bottom:16px}
  .panel{background:var(--surface);border:1px solid var(--line);border-radius:12px;box-shadow:0 18px 44px rgba(15,55,85,.10);padding:18px}
  h1{font-size:26px;margin:0 0 8px;color:#0f2b45}
  h2{font-size:15px;margin:0 0 10px;color:#0f5f93;text-transform:uppercase;letter-spacing:.04em}
  p{font-size:13px;line-height:1.55;color:var(--muted);margin:0 0 10px}
  label{display:block;font-size:12px;font-weight:800;color:#3d5872;margin:10px 0 4px}
  textarea,input,select{width:100%;box-sizing:border-box;border:1px solid var(--line);border-radius:9px;padding:10px 11px;background:#fbfdff;color:var(--ink);font:14px inherit}
  textarea{min-height:130px;resize:vertical}
  .grid{display:grid;grid-template-columns:330px 1fr;gap:16px;align-items:start}
  .row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
  button,.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;border:0;border-radius:9px;padding:10px 14px;font-weight:900;font-size:13px;cursor:pointer;text-decoration:none}
  .primary{background:linear-gradient(135deg,var(--blue),var(--teal));color:white}
  .ghost{background:#f5fbff;border:1px solid var(--line);color:#17324a}
  .pill{display:inline-flex;border-radius:999px;padding:5px 9px;font-size:12px;font-weight:900}
  .pill.ok{background:#e6f6ee;color:var(--ok)}.pill.warn{background:#fff6dd;color:var(--warn)}.pill.err{background:#fff0ee;color:var(--err)}
  .settings-grid{display:grid;grid-template-columns:repeat(3,minmax(220px,1fr));gap:10px}
  .switchline{display:flex;align-items:center;gap:8px;font-size:12px;font-weight:700;color:#355066}
  .switchline input{width:auto}
  pre{white-space:pre-wrap;word-break:break-word;background:#081523;color:#d8ecff;border-radius:10px;padding:14px;min-height:260px;max-height:520px;overflow:auto;font-size:13px;line-height:1.5}
  code{background:#e9f3fa;border:1px solid #cce0ee;border-radius:6px;padding:1px 5px;color:#17324a}
  .small{font-size:12px;color:var(--muted)}
  @media(max-width:900px){body{padding:12px}.hero,.grid,.settings-grid{grid-template-columns:1fr}}
</style></head><body>
<main class="shell">
  <section class="hero">
    <div class="panel">
      <h1>MedGemma Klinik YZ</h1>
      <p>Medikal not, USG/PDF metni, laboratuvar ve kirmizi alarm taramasi icin lokal/ozel endpoint destekli uzman ajan. Cikti daima doktor onayli taslaktir.</p>
      <div class="row">
        <a class="btn ghost" href="/ajanlar">Ajan merkezi</a>
        <a class="btn ghost" href="/medgemma-modul">MedGemma modul</a>
        <a class="btn ghost" href="/yz-konsultasyon">YZ konsultasyon</a>
        <a class="btn ghost" href="/yz-sihirbazi">YZ sihirbazi</a>
      </div>
    </div>
    <div class="panel">
      <h2>Durum</h2>
      <div id="statusPill" class="pill warn">kontrol ediliyor</div>
      <p id="statusText" style="margin-top:10px">MedGemma durumu okunuyor.</p>
      <div class="small" id="modelText"></div>
    </div>
  </section>

  <section class="panel" style="margin-bottom:16px">
    <h2>Modul ayarlari</h2>
    <div class="settings-grid">
      <div>
        <label>Backend</label>
        <select id="mgBackend">
          <option value="auto">auto</option>
          <option value="ollama">ollama</option>
          <option value="transformers">transformers</option>
          <option value="endpoint">endpoint</option>
          <option value="openai_compat">openai_compat</option>
        </select>
      </div>
      <div>
        <label>Ana model</label>
        <input id="mgModel" placeholder="google/medgemma-4b-it">
      </div>
      <div>
        <label>Text model</label>
        <input id="mgTextModel" placeholder="google/medgemma-27b-text-it">
      </div>
      <div>
        <label>Fast model</label>
        <input id="mgFastModel" placeholder="google/medgemma-1.5-4b-it">
      </div>
      <div>
        <label>Endpoint (opsiyonel)</label>
        <input id="mgEndpoint" placeholder="http://127.0.0.1:8000/v1/chat/completions">
      </div>
      <div>
        <label>Max yeni token</label>
        <input id="mgMaxTokens" type="number" min="64" max="8192" step="1" value="512">
      </div>
      <div>
        <label>Cihaz</label>
        <input id="mgDevice" placeholder="auto / cuda / cpu">
      </div>
      <div>
        <label>Dtype</label>
        <input id="mgDtype" placeholder="auto / bfloat16 / float16">
      </div>
      <div style="display:flex;flex-direction:column;gap:6px;justify-content:flex-end">
        <label class="switchline"><input id="mgEnabled" type="checkbox"> MedGemma etkin</label>
        <label class="switchline"><input id="mgAllowRemote" type="checkbox"> Uzak endpoint'e izin ver</label>
        <label class="switchline"><input id="mgLoadOnDemand" type="checkbox"> Modeli ihtiyac halinde yukle</label>
      </div>
    </div>
    <div class="row" style="margin-top:10px">
      <button class="primary" type="button" onclick="saveMedGemmaSettings()">Ayarlari kaydet</button>
      <button class="ghost" type="button" onclick="loadMedGemmaSettings()">Ayarlari yeniden oku</button>
      <span id="settingsStatus" class="small"></span>
    </div>
  </section>

  <section class="grid">
    <div class="panel">
      <h2>Girdi</h2>
      <label>Gorev</label>
      <select id="task">
        <option value="clinical_note">Klinik not duzenle</option>
        <option value="usg_pdf">USG/PDF oku</option>
        <option value="lab_triage">Lab/tetkik triyaj</option>
        <option value="red_flags">Kirmizi alarm tara</option>
        <option value="patient_summary">Hasta ozet taslagi</option>
      </select>
      <div class="small" id="taskModelHint">Gorev bazli onerilen model yukleniyor...</div>
      <label>Onerilen gorevlendirme profili</label>
      <div class="row">
        <select id="assignmentPreset" style="flex:1 1 240px"></select>
        <button class="ghost" type="button" onclick="applySelectedPreset()">Profili uygula</button>
      </div>
      <div class="small" id="assignmentPresetHint">Goreve uygun profile gecmek icin listeden secip uygula.</div>
      <label>Hasta baglami</label>
      <textarea id="patientContext" placeholder="Orn: 28 yas, G2P1, 24 hafta, rutin kontrol..."></textarea>
      <label>YZ tanimi (sabit rol/kurallar)</label>
      <textarea id="yzDefinition" placeholder="Orn: Kadin dogum klinik karar destek asistani. Yanitlar kisa, acik, doktor onayli olsun."></textarea>
      <label>Gorevlendirme (bu panelin ana isi)</label>
      <textarea id="assignment" placeholder="Orn: SAT bilinmiyorsa son USG/PDF'den GA hesapla ve takip taslagi ver."></textarea>
      <label>Not / PDF metni / tetkik bilgisi</label>
      <textarea id="note" placeholder="Buraya klinik metni yapistir...">28 yas, gebelik kontrolu. Sikayet yok. Tansiyon 110/70.</textarea>
      <label>Model etiketi (bos birakilirsa otomatik)</label>
      <input id="preferModel" list="medgemmaModelList" placeholder="google/medgemma-4b-it">
      <datalist id="medgemmaModelList">
        <option value="google/medgemma-1.5-4b-it"></option>
        <option value="google/medgemma-4b-it"></option>
        <option value="google/medgemma-4b-pt"></option>
        <option value="google/medgemma-27b-text-it"></option>
        <option value="google/medgemma-27b-it"></option>
      </datalist>
      <label><input id="useRecommendedModel" type="checkbox" checked style="width:auto"> Bu gorevde onerilen varsayilan LLM'i kullan</label>
      <label><input id="stickyContext" type="checkbox" checked style="width:auto"> Baglama yapis (YZ tanimi + gorevlendirme + hasta baglami)</label>
      <label><input id="previewOnly" type="checkbox" checked style="width:auto"> Once prompt onizleme modu</label>
      <div class="row" style="margin-top:12px">
        <button class="primary" onclick="runMedGemma()">Calistir</button>
        <button class="ghost" onclick="loadExample()">Ornek yukle</button>
        <button class="ghost" onclick="saveBinding()">Baglami kaydet</button>
        <button class="ghost" onclick="clearBinding()">Baglami temizle</button>
        <button class="ghost" onclick="copyOut()">Sonucu kopyala</button>
      </div>
      <p class="small">Ilk kurulumda onizleme acik gelir; model hazir olmadan uygulama takilmaz.</p>
    </div>
    <div class="panel">
      <h2>Sonuc</h2>
      <pre id="out">(bekliyor)</pre>
    </div>
  </section>
</main>
<script>
function esc(v){return String(v==null?'':v)}
let taskModelRecommendations = {};
let taskModelOverrides = {};
function setSettingsStatus(text, good){
  const el=document.getElementById('settingsStatus');
  if(!el) return;
  el.textContent=String(text||'');
  el.style.color = good ? '#11784a' : '#5d7084';
}
function applyMedGemmaSettingsUi(cfg){
  if(!cfg || typeof cfg!=='object') return;
  document.getElementById('mgEnabled').checked=!!cfg.enabled;
  document.getElementById('mgBackend').value=String(cfg.backend||'auto');
  document.getElementById('mgModel').value=String(cfg.model||'');
  document.getElementById('mgTextModel').value=String(cfg.text_model||'');
  document.getElementById('mgFastModel').value=String(cfg.newer_fast_model||'');
  document.getElementById('mgEndpoint').value=String(cfg.endpoint||'');
  document.getElementById('mgAllowRemote').checked=!!cfg.remote_allowed;
  document.getElementById('mgDevice').value=String(cfg.device||'auto');
  document.getElementById('mgDtype').value=String(cfg.dtype||'auto');
  document.getElementById('mgMaxTokens').value=String(cfg.max_new_tokens||512);
  document.getElementById('mgLoadOnDemand').checked=!!cfg.load_on_demand;
}
function setMedGemmaModelOptions(candidates){
  const dl=document.getElementById('medgemmaModelList');
  if(!dl) return;
  const seen={};
  const ordered=[];
  (candidates||[]).forEach(function(v){
    const text=String(v||'').trim();
    if(!text) return;
    const k=text.toLowerCase();
    if(seen[k]) return;
    seen[k]=1;
    ordered.push(text);
  });
  dl.innerHTML='';
  ordered.forEach(function(v){
    const opt=document.createElement('option');
    opt.value=v;
    dl.appendChild(opt);
  });
}
function refreshModelOptionsFromHealth(h){
  const list=[
    'google/medgemma-1.5-4b-it',
    'google/medgemma-4b-it',
    'google/medgemma-4b-pt',
    'google/medgemma-27b-text-it',
    'google/medgemma-27b-it',
    'medgemma:27b',
    'medgemma:4b'
  ];
  try{
    const mc=(h&&h.model_cache&&typeof h.model_cache==='object') ? h.model_cache : {};
    Object.keys(mc).forEach(function(k){ if(mc[k]) list.push(k); });
  }catch(_){}
  try{
    const ollama=((h&&h.ollama)||{});
    (ollama.models||[]).forEach(function(m){ list.push(m); });
    (ollama.medgemma_models||[]).forEach(function(m){ list.push(m); });
  }catch(_){}
  setMedGemmaModelOptions(list);
}
async function loadMedGemmaSettings(){
  try{
    const r=await fetch('/api/agents/medgemma/settings',{credentials:'same-origin'});
    const d=await r.json();
    if(!r.ok || !d.ok) throw new Error((d&&d.error)||('HTTP '+r.status));
    applyMedGemmaSettingsUi(d.settings||{});
    setSettingsStatus('Ayarlar yuklendi.', true);
  }catch(e){
    setSettingsStatus('Ayarlar okunamadi: '+(e&&e.message?e.message:e), false);
  }
}
async function saveMedGemmaSettings(){
  const body={
    enabled:document.getElementById('mgEnabled').checked,
    backend:document.getElementById('mgBackend').value,
    model:document.getElementById('mgModel').value,
    text_model:document.getElementById('mgTextModel').value,
    newer_fast_model:document.getElementById('mgFastModel').value,
    endpoint:document.getElementById('mgEndpoint').value,
    remote_allowed:document.getElementById('mgAllowRemote').checked,
    device:document.getElementById('mgDevice').value,
    dtype:document.getElementById('mgDtype').value,
    max_new_tokens:document.getElementById('mgMaxTokens').value,
    load_on_demand:document.getElementById('mgLoadOnDemand').checked
  };
  try{
    setSettingsStatus('Ayarlar kaydediliyor...', false);
    const r=await fetch('/api/agents/medgemma/settings',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    if(!r.ok || !d.ok) throw new Error((d&&d.error)||('HTTP '+r.status));
    applyMedGemmaSettingsUi(d.settings||{});
    setSettingsStatus((d.message||'Ayarlar kaydedildi.') + ' Gerekirse D700 yeniden baslat.', true);
    health();
  }catch(e){
    setSettingsStatus('Kayit hatasi: '+(e&&e.message?e.message:e), false);
  }
}
const DEFAULT_TASK_ASSIGNMENT_PROFILES = {
  clinical_note: {
    title: 'Klinik not duzenleme',
    note: 'Muayene notunu kisa, okunur ve doktor onayli taslaga cevirir.',
    yz_definition: 'Kadin dogum klinigi karar destek asistani. Kisa, net, doktor onayli yaz.',
    assignment: 'Klinik notu sorun listesi, takip plani ve doktor notu taslagi olarak duzenle.',
    patient_context: 'Rutin kontrol hastasi. Acil bulgu yoksa net sekilde belirt.'
  },
  usg_pdf: {
    title: 'USG/PDF analiz',
    note: 'USG/PDF metninden GA/EDD ve takip ihtiyacini ayiklar.',
    yz_definition: 'Obstetrik USG raporlarinda olcum odakli karar destek asistani.',
    assignment: 'SAT bilinmiyorsa son USG/PDF olcumlerini referans alip GA/EDD taslagi ver; eksik veriyi listele.',
    patient_context: 'Gebelik takibi. Son rapor onceliklidir.'
  },
  lab_triage: {
    title: 'Lab/tetkik triyaj',
    note: 'Tetkikleri oncelik seviyesine gore ayirir.',
    yz_definition: 'Laboratuvar triyajinda kirmizi bayraklari one cikar.',
    assignment: 'Anormal degerleri yuksek/orta/dusuk oncelik olarak sinifla ve takip adimi taslagi yaz.',
    patient_context: 'Tetkikler karisik gelebilir; acil riskleri ilk satira yaz.'
  },
  red_flags: {
    title: 'Kirmizi alarm tarama',
    note: 'Acil obstetrik riskleri hizla yakalar.',
    yz_definition: 'Acil bulgu tarama asistani. Risk varsa ilk satirda net bildir.',
    assignment: 'Metindeki acil riskleri ayikla; acil yonlendirme gereken durumlari ustte yaz.',
    patient_context: 'Gebelik/obstetrik semptom taramasi.'
  },
  patient_summary: {
    title: 'Hasta ozet taslagi',
    note: 'Dosya verisini hekim okumasina uygun tek ozete toplar.',
    yz_definition: 'Hasta dosyasi ozetleme asistani. Gereksiz tekrar yapma.',
    assignment: 'Hastanin gelislerini, kritik bulgularini ve planini kisa ozet halinde derle.',
    patient_context: 'Coklu gelis ve dosya icerigi olabilir.'
  }
};
let taskAssignmentProfiles = {};
function getTaskRecommendation(task){
  const key=String(task||'').trim();
  const row=taskModelRecommendations[key];
  if(row&&typeof row==='object') return row;
  return {model:'google/medgemma-4b-it', note:'Varsayilan dengeli model.'};
}
function getTaskProfile(task){
  const key=String(task||'').trim();
  const row=taskAssignmentProfiles[key];
  if(row&&typeof row==='object') return row;
  const fallback=DEFAULT_TASK_ASSIGNMENT_PROFILES[key];
  if(fallback&&typeof fallback==='object') return fallback;
  return {title:'', note:'', yz_definition:'', assignment:'', patient_context:''};
}
function updateRecommendationsFromResponse(d){
  if(!d||typeof d!=='object') return;
  if(d.task_model_recommendations && typeof d.task_model_recommendations==='object'){
    taskModelRecommendations=d.task_model_recommendations;
  }
  if(d.task_assignment_recommendations && typeof d.task_assignment_recommendations==='object'){
    taskAssignmentProfiles=d.task_assignment_recommendations;
  }
  rebuildAssignmentPresetList(document.getElementById('task').value);
  refreshTaskModelHint();
  refreshAssignmentPresetHint();
}
function rebuildAssignmentPresetList(preferredTask){
  const select=document.getElementById('assignmentPreset');
  const taskSel=document.getElementById('task');
  if(!select || !taskSel) return;
  const old=String(preferredTask || select.value || taskSel.value || '').trim();
  const options=Array.from(taskSel.options || []).map(function(opt){
    return {value:String(opt.value||''), text:String(opt.textContent||opt.value||'')};
  }).filter(function(row){ return !!row.value; });
  select.innerHTML='';
  options.forEach(function(row){
    const profile=getTaskProfile(row.value);
    const opt=document.createElement('option');
    opt.value=row.value;
    opt.textContent=row.text + (profile.title ? (' - ' + profile.title) : '');
    select.appendChild(opt);
  });
  const hasOld=Array.from(select.options || []).some(function(opt){ return opt.value===old; });
  if(hasOld){
    select.value=old;
  }else if(select.options.length){
    select.value=taskSel.value || select.options[0].value;
  }
}
function refreshAssignmentPresetHint(){
  const taskSel=document.getElementById('task');
  const presetSel=document.getElementById('assignmentPreset');
  const hint=document.getElementById('assignmentPresetHint');
  if(!taskSel || !presetSel || !hint) return;
  const selectedTask=String(presetSel.value || taskSel.value || '').trim();
  const profile=getTaskProfile(selectedTask);
  let text='';
  if(profile.title) text += profile.title;
  if(profile.note) text += (text ? ' | ' : '') + profile.note;
  hint.textContent = text || 'Goreve uygun profile gecmek icin listeden secip uygula.';
}
function applyAssignmentProfile(task, overwriteAll){
  const taskKey=String(task || document.getElementById('task').value || '').trim();
  if(!taskKey) return;
  const taskSel=document.getElementById('task');
  if(taskSel) taskSel.value=taskKey;
  const profile=getTaskProfile(taskKey);
  const yz=document.getElementById('yzDefinition');
  const assignment=document.getElementById('assignment');
  const patientContext=document.getElementById('patientContext');
  const force=!!overwriteAll;
  if(yz && profile.yz_definition && (force || !String(yz.value||'').trim())){
    yz.value=String(profile.yz_definition);
  }
  if(assignment && profile.assignment && (force || !String(assignment.value||'').trim())){
    assignment.value=String(profile.assignment);
  }
  if(patientContext && profile.patient_context && (force || !String(patientContext.value||'').trim())){
    patientContext.value=String(profile.patient_context);
  }
  const preset=document.getElementById('assignmentPreset');
  if(preset) preset.value=taskKey;
  refreshAssignmentPresetHint();
  onTaskChanged();
}
function applySelectedPreset(){
  const preset=document.getElementById('assignmentPreset');
  const task=String((preset&&preset.value) || document.getElementById('task').value || '').trim();
  applyAssignmentProfile(task, true);
}
function refreshTaskModelHint(){
  const task=document.getElementById('task').value;
  const rec=getTaskRecommendation(task);
  const useRecommended=!!document.getElementById('useRecommendedModel').checked;
  const override=String(taskModelOverrides[task]||'').trim();
  let text='Onerilen model: '+String(rec.model||'-');
  if(rec.note) text+=' | '+String(rec.note);
  if(!useRecommended&&override) text+=' | Ozel secim: '+override;
  document.getElementById('taskModelHint').textContent=text;
}
function applyRecommendedModelForTask(force){
  const task=document.getElementById('task').value;
  const rec=getTaskRecommendation(task);
  const inp=document.getElementById('preferModel');
  const useRecommended=!!document.getElementById('useRecommendedModel').checked;
  if(force || useRecommended || !String(inp.value||'').trim()){
    if(rec.model) inp.value=String(rec.model);
  }
  refreshTaskModelHint();
}
function syncTaskOverrideFromUi(){
  const task=document.getElementById('task').value;
  const useRecommended=!!document.getElementById('useRecommendedModel').checked;
  const modelText=String(document.getElementById('preferModel').value||'').trim();
  if(useRecommended){
    delete taskModelOverrides[task];
  }else if(modelText){
    taskModelOverrides[task]=modelText;
  }else{
    delete taskModelOverrides[task];
  }
}
function onTaskChanged(){
  const task=document.getElementById('task').value;
  const preset=document.getElementById('assignmentPreset');
  if(preset) preset.value=task;
  const override=String(taskModelOverrides[task]||'').trim();
  if(override){
    document.getElementById('useRecommendedModel').checked=false;
    document.getElementById('preferModel').value=override;
  }else{
    document.getElementById('useRecommendedModel').checked=true;
    applyRecommendedModelForTask(true);
  }
  refreshTaskModelHint();
  refreshAssignmentPresetHint();
}
function onUseRecommendedModelChanged(){
  const useRecommended=!!document.getElementById('useRecommendedModel').checked;
  const task=document.getElementById('task').value;
  if(useRecommended){
    delete taskModelOverrides[task];
    applyRecommendedModelForTask(true);
  }else{
    const modelText=String(document.getElementById('preferModel').value||'').trim();
    if(modelText) taskModelOverrides[task]=modelText;
  }
  refreshTaskModelHint();
}
function applyBinding(b){
  if(!b||typeof b!=='object') return;
  if(b.task) document.getElementById('task').value=String(b.task);
  if('patient_context' in b) document.getElementById('patientContext').value=String(b.patient_context||'');
  if('yz_definition' in b) document.getElementById('yzDefinition').value=String(b.yz_definition||'');
  if('assignment' in b) document.getElementById('assignment').value=String(b.assignment||'');
  if('prefer_model' in b) document.getElementById('preferModel').value=String(b.prefer_model||'');
  if('task_model_overrides' in b && b.task_model_overrides && typeof b.task_model_overrides==='object'){
    taskModelOverrides=Object.assign({}, b.task_model_overrides);
  }
  if('preview_only' in b) document.getElementById('previewOnly').checked=!!b.preview_only;
  if('sticky_context' in b) document.getElementById('stickyContext').checked=!!b.sticky_context;
  onTaskChanged();
}
async function loadBinding(){
  try{
    const r=await fetch('/api/agents/medgemma/context',{credentials:'same-origin'});
    const d=await r.json();
    updateRecommendationsFromResponse(d);
    applyBinding(d.result||{});
    refreshAssignmentPresetHint();
  }catch(e){}
}
async function saveBinding(){
  const out=document.getElementById('out');
  syncTaskOverrideFromUi();
  const body={
    task:document.getElementById('task').value,
    patient_context:document.getElementById('patientContext').value,
    yz_definition:document.getElementById('yzDefinition').value,
    assignment:document.getElementById('assignment').value,
    prefer_model:document.getElementById('preferModel').value,
    task_model_overrides:taskModelOverrides,
    use_recommended_model:document.getElementById('useRecommendedModel').checked,
    preview_only:document.getElementById('previewOnly').checked,
    sticky_context:document.getElementById('stickyContext').checked
  };
  try{
    const r=await fetch('/api/agents/medgemma/context',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    updateRecommendationsFromResponse(d);
    applyBinding(d.result||{});
    out.textContent='Baglam kaydedildi. Sonraki cagrilarda bu profil kullanilacak.';
  }catch(e){out.textContent='Hata: '+e.message}
}
async function clearBinding(){
  const out=document.getElementById('out');
  try{
    const r=await fetch('/api/agents/medgemma/context',{method:'DELETE',credentials:'same-origin'});
    const d=await r.json();
    updateRecommendationsFromResponse(d);
    taskModelOverrides={};
    applyBinding(d.result||{});
    out.textContent='Baglam temizlendi. MedGemma varsayilan profile dondu.';
  }catch(e){out.textContent='Hata: '+e.message}
}
async function health(){
  try{
    const r=await fetch('/api/agents/medgemma/health',{credentials:'same-origin'});
    const d=await r.json();
    const h=d.result||{};
    const pill=document.getElementById('statusPill');
    const ready=!!h.ready;
    pill.className='pill '+(ready?'ok':(h.config&&h.config.enabled?'warn':'err'));
    pill.textContent=ready?'hazir':(h.config&&h.config.enabled?'kurulum bekliyor':'kapali');
    updateRecommendationsFromResponse(h);
    refreshModelOptionsFromHealth(h);
    document.getElementById('statusText').textContent=(h.blockers&&h.blockers.length)?('Bekleyen: '+h.blockers.join(', ')):'MedGemma kullanima hazir.';
    const ollamaModels=((h.ollama||{}).medgemma_models||[]);
    document.getElementById('modelText').innerHTML='Backend: <code>'+esc((h.config||{}).backend)+'</code><br>Model: <code>'+esc((h.config||{}).model)+'</code><br>Text: <code>'+esc((h.config||{}).text_model)+'</code><br>Ollama MedGemma: <code>'+esc(ollamaModels.join(', ') || '-')+'</code><br>GPU: '+esc(((h.gpu||{}).name)||'kontrol yok');
    refreshTaskModelHint();
  }catch(e){
    document.getElementById('statusPill').className='pill err';
    document.getElementById('statusPill').textContent='hata';
    document.getElementById('statusText').textContent=e.message;
  }
}
function loadExample(){
  document.getElementById('task').value='usg_pdf';
  document.getElementById('patientContext').value='Hasta: gebelik takibi. SAT bilinmiyor. Son USG PDF oncelikli.';
  document.getElementById('yzDefinition').value='Kadin dogum klinigi icin karar destek asistani. Kisa, acik, doktor onayli taslak ver.';
  document.getElementById('assignment').value='SAT bilinmiyorsa son USG/PDF olcumlerini referans al, GA/EDD taslagi olustur ve eksik veriyi belirt.';
  document.getElementById('note').value='USG: CRL 9.80 mm, GA 7w0d, FHR pozitif. Rapor tarihi 2026-05-20.';
  document.getElementById('useRecommendedModel').checked=true;
  onTaskChanged();
}
async function runMedGemma(){
  const out=document.getElementById('out');
  out.textContent='Calisiyor...';
  syncTaskOverrideFromUi();
  const body={
    task:document.getElementById('task').value,
    patient_context:document.getElementById('patientContext').value,
    yz_definition:document.getElementById('yzDefinition').value,
    assignment:document.getElementById('assignment').value,
    note:document.getElementById('note').value,
    prefer_model:document.getElementById('preferModel').value,
    task_model_overrides:taskModelOverrides,
    use_recommended_model:document.getElementById('useRecommendedModel').checked,
    preview_only:document.getElementById('previewOnly').checked,
    sticky_context:document.getElementById('stickyContext').checked
  };
  try{
    const r=await fetch('/api/agents/medgemma/analyze',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    const res=d.result||d;
    updateRecommendationsFromResponse(res);
    if(res.binding && typeof res.binding==='object'){
      updateRecommendationsFromResponse(res.binding);
    }
    out.textContent=res.answer || res.prompt || JSON.stringify(res,null,2);
  }catch(e){out.textContent='Hata: '+e.message}
}
function copyOut(){navigator.clipboard&&navigator.clipboard.writeText(document.getElementById('out').textContent||'')}
document.getElementById('task').addEventListener('change', onTaskChanged);
document.getElementById('assignmentPreset').addEventListener('change', refreshAssignmentPresetHint);
document.getElementById('useRecommendedModel').addEventListener('change', onUseRecommendedModelChanged);
document.getElementById('preferModel').addEventListener('input', function(){
  if(!document.getElementById('useRecommendedModel').checked){
    syncTaskOverrideFromUi();
  }
  refreshTaskModelHint();
});
rebuildAssignmentPresetList('clinical_note');
refreshAssignmentPresetHint();
loadMedGemmaSettings();
health();
loadBinding();
</script>
</body></html>"""


# === Instagram Hazirlik Ajani ============================================
# Path traversal koruma: sadece allowed_roots altindaki dosyalar okunabilir.

def _allowed_image_root(path_str: str) -> Optional[Path]:
    """Path izinli koklerden birinin altindaysa Path dondurur, degilse None."""
    candidates = [
        _DEFAULT_VOLUSON_ROOT,
        os.environ.get("YAZKLINIK_NAS_ROOT"),
        os.path.dirname(os.path.abspath(__file__)),  # proje kokunden tarama
    ]
    for root in candidates:
        if not root:
            continue
        try:
            root_p = Path(root).resolve()
            target = Path(path_str).resolve()
            target.relative_to(root_p)
            return target
        except Exception:
            continue
    return None


# D700 v17 2026-05-17: bg-job helpers paylasilan modulden geliyor
# Boylece NAS sync (yazklinik_web.py), PubMed scan, RAG reindex de ayni
# pattern'i kullanabilir.
from yazklinik_bg_jobs import (
    bg_start_job as _bg_start_job,
    bg_get_job as _bg_get_job,
    bg_get_last_job as _bg_get_last_job,
    bg_list_jobs as _bg_list_jobs,
)
# Compatibility shim: eski kod _bg_lock() ve _BACKGROUND_JOBS bekliyor
import threading as _bg_threading_mod
_BG_LOCK = _bg_threading_mod.Lock()
def _bg_lock():
    return _BG_LOCK
# _BACKGROUND_JOBS - eski endpoint'lerin (history) erisimi icin proxy
from yazklinik_bg_jobs import _BACKGROUND_JOBS


_IG_SEEN_PATHS = {}  # user_key -> set of paths (server-side persist)


def _ig_seen_get(user_key: str) -> list:
    with _bg_lock():
        return list(_IG_SEEN_PATHS.get(user_key) or set())


def _ig_seen_add(user_key: str, paths: list):
    with _bg_lock():
        s = _IG_SEEN_PATHS.setdefault(user_key, set())
        for p in paths or []:
            if p:
                s.add(str(p))


def _ig_seen_clear(user_key: str):
    with _bg_lock():
        _IG_SEEN_PATHS.pop(user_key, None)


@agents_bp.route("/api/agents/instagram/scan", methods=["POST"])
def ig_scan():
    """Arka planda Instagram scan baslat. Donus: job_id (anlik).

    Mode'lar:
      - mode='new' (default): onceden gorulen pathleri DISLAR
      - mode='all': hicbir seyi dislamaz (reset)

    Onceki tum result candidate pathleri "seen" olarak isaretlenir.
    Boylelikle 'Tara' dedikce yeni resimler gelir.
    """
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(instagram_mod, "instagram")
    if err:
        return err
    p = _payload()
    root = str(p.get("root") or _DEFAULT_VOLUSON_ROOT)
    try:
        max_candidates = max(1, min(300, int(p.get("max_candidates") or 60)))
    except Exception:
        max_candidates = 60
    include_pdf = _as_bool(p.get("include_pdf"), True)
    try:
        min_score = float(p.get("min_score") or 0.30)
    except Exception:
        min_score = 0.30
    raw_mode = p.get("mode") or "new"
    if isinstance(raw_mode, dict):
        raw_mode = raw_mode.get("value") or raw_mode.get("mode") or "new"
    mode = str(raw_mode or "new").strip().lower()
    user_key = str(session.get("user") or session.get("username") or "doktor")

    # Onceki scan sonuclarini "seen" kaydet (kullanici simdi yeni istiyor)
    if mode == "new":
        prev = _bg_get_last_job(user_key, "ig_scan")
        if prev and prev.get("status") == "done" and prev.get("result"):
            try:
                prev_cands = (prev["result"] or {}).get("candidates", [])
                _ig_seen_add(user_key, [c.get("path") for c in prev_cands])
            except Exception:
                pass
        exclude_paths = _ig_seen_get(user_key)
    elif mode == "all":
        # Tum seen sifirla
        _ig_seen_clear(user_key)
        exclude_paths = []
    else:
        exclude_paths = []

    job_id = _bg_start_job(
        "ig_scan",
        instagram_mod.scan_archive,
        user_key=user_key,
        root=root, max_candidates=max_candidates,
        include_pdf=include_pdf, min_score=min_score,
        exclude_paths=exclude_paths,
    )
    _safe_audit("agents:instagram_scan_start",
                 {"root": root, "job_id": job_id, "mode": mode,
                  "exclude_count": len(exclude_paths)})
    return jsonify({"ok": True, "job_id": job_id, "status": "started",
                     "mode": mode, "excluded_count": len(exclude_paths)})


@agents_bp.route("/api/agents/instagram/seen-reset", methods=["POST"])
def ig_seen_reset():
    """Kullanicinin seen path setini temizle (hepsini tekrar gosterebilir)."""
    auth = _require_session()
    if auth:
        return auth
    user_key = str(session.get("user") or session.get("username") or "doktor")
    _ig_seen_clear(user_key)
    return jsonify({"ok": True, "message": "Hafiza sifirlandi - Tara'ya bastiginda hepsi gozukur"})


@agents_bp.route("/api/agents/instagram/history", methods=["GET"])
def ig_history():
    """Kullanicinin son IG scan jobs listesi (sondan ilkine)."""
    auth = _require_session()
    if auth:
        return auth
    user_key = str(session.get("user") or session.get("username") or "doktor")
    out = []
    with _bg_lock():
        for jid, j in list(_BACKGROUND_JOBS.items()):
            if not isinstance(j, dict):
                continue
            if j.get("type") != "ig_scan" or j.get("user_key") != user_key:
                continue
            r = j.get("result") or {}
            out.append({
                "job_id": jid,
                "status": j.get("status"),
                "started_at": j.get("started_at"),
                "completed_at": j.get("completed_at"),
                "count": len((r.get("candidates") or [])),
                "scanned": r.get("scanned_count", 0),
            })
    out.sort(key=lambda x: -(x["started_at"] or 0))
    return jsonify({"ok": True, "history": out[:20],
                     "seen_count": len(_ig_seen_get(user_key))})


@agents_bp.route("/api/agents/instagram/scan-status", methods=["GET"])
def ig_scan_status():
    """Job status sorgu. Query: ?job_id=X (yoksa son job)."""
    auth = _require_session()
    if auth:
        return auth
    job_id = request.args.get("job_id", "").strip()
    user_key = str(session.get("user") or session.get("username") or "doktor")
    if not job_id:
        # Kullanicinin son scan job'u
        job = _bg_get_last_job(user_key, "ig_scan")
    else:
        job = _bg_get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "job yok", "has_previous": False})
    return jsonify({
        "ok": True,
        "job_id": job["id"], "status": job["status"],
        "progress": job.get("progress", 0),
        "result": job.get("result"), "error": job.get("error"),
        "started_at": job.get("started_at"),
        "completed_at": job.get("completed_at"),
        "elapsed_sec": int((job.get("completed_at") or __import__("time").time()) - job["started_at"]),
    })


@agents_bp.route("/api/agents/instagram/thumbnail", methods=["GET"])
def ig_thumbnail():
    """Path traversal-korumali thumbnail server.

    Sadece izinli koklerin altindaki goruntu/PDF'lerden 320px thumbnail uretir.
    """
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(instagram_mod, "instagram")
    if err:
        return err
    raw_path = request.args.get("path") or ""
    target = _allowed_image_root(raw_path)
    if not target or not target.is_file():
        return abort(404)
    try:
        img = instagram_mod._open_image(target)  # type: ignore[attr-defined]
        if img is None:
            return abort(404)
        max_dim = int(request.args.get("size") or 320)
        max_dim = max(64, min(1024, max_dim))
        w, h = img.size
        if w > h:
            new_w = max_dim
            new_h = int(h * (max_dim / w))
        else:
            new_h = max_dim
            new_w = int(w * (max_dim / h))
        from PIL import Image
        thumb = img.resize((new_w, new_h), Image.LANCZOS)
        from io import BytesIO
        buf = BytesIO()
        thumb.save(buf, "JPEG", quality=80)
        buf.seek(0)
        return send_file(buf, mimetype="image/jpeg", download_name="thumb.jpg",
                          max_age=300)
    except Exception:
        return abort(500)


@agents_bp.route("/api/agents/instagram/enhance", methods=["POST"])
def ig_enhance():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(instagram_mod, "instagram")
    if err:
        return err
    p = _payload()
    raw_path = str(p.get("source_path") or "").strip()
    if not raw_path:
        return jsonify({
            "ok": False,
            "agent": "instagram",
            "error": "bad_request",
            "detail": "source_path gerekli.",
        }), 400
    target = _allowed_image_root(raw_path)
    if not target:
        return jsonify({"ok": False, "agent": "instagram", "error": "path_not_allowed",
                         "detail": "Goruntu izinli root disinda."}), 403
    if not target.is_file():
        return jsonify({
            "ok": False,
            "agent": "instagram",
            "error": "bad_request",
            "detail": "source_path gecerli bir dosya olmali.",
        }), 400

    output_dir = str(p.get("output_dir") or _DEFAULT_IG_DRAFT_DIR)
    try:
        opts = instagram_mod.EnhanceOptions(
            header_crop_ratio=float(p.get("header_crop_ratio", instagram_mod.DEFAULT_HEADER_CROP_RATIO)),
            side_crop_ratio=float(p.get("side_crop_ratio", instagram_mod.DEFAULT_SIDE_CROP_RATIO)),
            sharpen=float(p.get("sharpen", 1.2)),
            contrast=float(p.get("contrast", 1.10)),
            brightness=float(p.get("brightness", 1.05)),
            saturation=float(p.get("saturation", 1.05)),
            add_watermark=bool(p.get("add_watermark", True)),
            watermark_text=str(p.get("watermark_text") or "(c) Op. Dr. Hakan Yaz"),
            output_format=str(p.get("output_format") or "portrait"),
            blur_corners=bool(p.get("blur_corners", False)),
            output_quality=int(p.get("output_quality") or 92),
        )
    except (TypeError, ValueError) as exc:
        return jsonify({
            "ok": False,
            "agent": "instagram",
            "error": "bad_request",
            "detail": f"gecersiz enhance parametresi: {exc}",
        }), 400

    try:
        result = instagram_mod.enhance_image(
            source_path=str(target),
            output_dir=output_dir,
            opts=opts,
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "agent": "instagram", "error": "enhance_failure",
                         "detail": f"{type(exc).__name__}: {exc}",
                         "trace": traceback.format_exc(limit=3)}), 500
    _safe_audit("agents:instagram_enhance", {"source": str(target), "draft": result.draft_path})
    return jsonify({"ok": True, "agent": "instagram", "result": asdict(result)})


@agents_bp.route("/api/agents/instagram/caption", methods=["POST"])
def ig_caption():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(instagram_mod, "instagram")
    if err:
        return err
    p = _payload()
    theme = str(p.get("theme") or "egitim_3d_4d")
    hashtag_groups = p.get("hashtag_groups") or ["core_tr", "brand"]
    if not isinstance(hashtag_groups, list):
        hashtag_groups = ["core_tr", "brand"]
    custom_intro = str(p.get("custom_intro") or "")
    try:
        suggestions = instagram_mod.caption_suggestions(
            theme=theme, hashtag_groups=hashtag_groups, custom_intro=custom_intro,
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "agent": "instagram", "error": "caption_failure",
                         "detail": f"{type(exc).__name__}: {exc}"}), 500
    return jsonify({
        "ok": True,
        "agent": "instagram",
        "result": {
            "suggestions": [asdict(s) for s in suggestions],
            "available_themes": list(instagram_mod.CAPTION_TEMPLATES.keys()),
            "available_hashtag_groups": list(instagram_mod.HASHTAG_GROUPS.keys()),
            "kvkk_checklist": list(instagram_mod.KVKK_CHECKLIST),
        }
    })


@agents_bp.route("/api/agents/instagram/draft-download", methods=["GET"])
def ig_draft_download():
    """Draft klasorundeki bir resmi indir."""
    auth = _require_session()
    if auth:
        return auth
    raw = request.args.get("file") or ""
    draft_dir = Path(_DEFAULT_IG_DRAFT_DIR).resolve()
    try:
        target = (draft_dir / raw).resolve()
        target.relative_to(draft_dir)
        if not target.is_file():
            return abort(404)
        return send_file(str(target), as_attachment=True)
    except Exception:
        return abort(404)


@agents_bp.route("/instagram-hazirla", methods=["GET"])
def instagram_page():
    auth = _require_session()
    if auth:
        return auth
    return render_template_string(_INSTAGRAM_PAGE,
                                  default_root=_DEFAULT_VOLUSON_ROOT,
                                  default_draft=_DEFAULT_IG_DRAFT_DIR)


_INSTAGRAM_PAGE = r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>Instagram Hazirlik Ajani - YazKlinik</title>
<style>
  :root { --med-blue: #1769aa; --med-teal: #0c7488; --med-rose: #c2185b;
          --med-green: #16815f; --med-amber: #b8821f; --med-red: #b3261e;
          --ink: #122236; --muted: #5e7185; --line: rgba(94,113,133,0.18);
          --surface: #ffffff; --bg: #f5f8fb; }
  body { font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
         background: var(--bg); color: var(--ink); margin: 0; padding: 18px; }
  h1 { margin: 0 0 4px; font-size: 22px; }
  .lead { color: var(--muted); font-size: 12px; margin: 0 0 16px; }
  .kvkk { background: #fff8e1; border: 1px solid #f0c14b; padding: 10px 14px;
          border-radius: 10px; color: #7a5612; font-size: 12px; margin-bottom: 14px; }
  .layout { display: grid; grid-template-columns: 280px 1fr 320px; gap: 14px; }
  @media (max-width: 1100px) { .layout { grid-template-columns: 1fr; } }
  .panel { background: var(--surface); border: 1px solid var(--line);
           border-radius: 12px; padding: 14px; }
  .panel h3 { margin: 0 0 10px; font-size: 13px; color: var(--med-blue);
              text-transform: uppercase; letter-spacing: 0.6px; }
  label { display: block; font-size: 12px; color: var(--muted); margin: 8px 0 3px; }
  input[type=text], input[type=number], select, textarea {
    width: 100%; padding: 7px 10px; border: 1px solid var(--line);
    border-radius: 8px; background: #fafbfd; color: var(--ink); font-size: 13px;
    box-sizing: border-box;
  }
  input[type=range] { width: 100%; }
  button { display: inline-flex; align-items: center; gap: 6px;
           padding: 7px 14px; border: 0; border-radius: 8px; cursor: pointer;
           font-size: 13px; font-weight: 600; }
  .btn-primary { background: linear-gradient(135deg, var(--med-blue), var(--med-teal));
                 color: #fff; }
  .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(23,105,170,0.25); }
  .btn-ghost { background: transparent; border: 1px solid var(--line); color: var(--ink); }
  .btn-ghost:hover { background: rgba(23,105,170,0.08); color: var(--med-blue); }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(150px, 1fr)); gap: 10px; }
  .card { background: #fff; border: 2px solid transparent; border-radius: 10px;
          overflow: hidden; cursor: pointer; transition: transform 160ms ease, border-color 160ms ease; }
  .card:hover { transform: translateY(-2px); border-color: rgba(23,105,170,0.32); }
  .card.selected { border-color: var(--med-blue); box-shadow: 0 4px 16px rgba(23,105,170,0.22); }
  .card img { width: 100%; aspect-ratio: 1/1; object-fit: cover; background: #eef2f7; display: block; }
  .card .meta { padding: 6px 8px; font-size: 11px; }
  .card .score { color: var(--med-teal); font-weight: 700; font-size: 12px; }
  .card .name { color: var(--ink); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .card .badge-pdf { display: inline-block; background: var(--med-rose); color: #fff;
                     border-radius: 4px; padding: 1px 5px; font-size: 9px; margin-left: 4px; }
  pre, .json { background: #0d1117; color: #c9d1d9; padding: 10px; border-radius: 8px;
               font-size: 11px; max-height: 240px; overflow: auto; }
  .preview { aspect-ratio: 1/1; background: #eef2f7; border-radius: 10px;
             display: flex; align-items: center; justify-content: center; color: var(--muted);
             margin-bottom: 8px; overflow: hidden; }
  .preview img { max-width: 100%; max-height: 100%; }
  .row { display: flex; gap: 6px; flex-wrap: wrap; }
  .pill { background: rgba(23,105,170,0.10); color: var(--med-blue);
          padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }
  .status { font-size: 12px; color: var(--muted); margin-top: 6px; }
  .status.ok { color: var(--med-green); }
  .status.fail { color: var(--med-red); }
  .draft-list { font-size: 12px; color: var(--ink); }
  .draft-list a { color: var(--med-blue); display: block; padding: 4px 0;
                  text-decoration: none; word-break: break-all; }
  .draft-list a:hover { color: var(--med-teal); text-decoration: underline; }
</style></head>
<body>
  <h1>Instagram Hazirlik Ajani</h1>
  <p class="lead">USG arsivinizden Instagram icin uygun goruntuleri secer, anonimlestirir, iyilestirir ve draft klasorune kaydeder.
     <span class="pill">DOKTOR ONAYLI</span> <span class="pill">KVKK GUVENLI</span></p>

  <div class="kvkk">
    <strong>KVKK uyarisi:</strong> USG goruntulerinde hasta adi, TC kimlik, tarih ve cihaz seri numarasi
    BURNED-IN olabilir. Anonimlestirmeden Instagram'a yuklemeyin. Hasta yazili onayi olmadan
    egitim/farkindalik amacli da paylasilamaz. Otomatik kirpma yetmeyebilir; her bir resmi gozle son kontrol edin.
  </div>

  <div class="layout">

    <!-- SOL: scan parametreleri + draft listesi -->
    <div class="panel">
      <h3>1. Tarama</h3>
      <label>Klasor yolu</label>
      <input type="text" id="rootInput" value="{{ default_root }}">
      <label>Maks aday</label>
      <input type="number" id="maxCandidates" value="40" min="1" max="200">
      <label>Min skor (0..1)</label>
      <input type="number" id="minScore" value="0.30" min="0" max="1" step="0.05">
      <label><input type="checkbox" id="includePdf" checked> PDF'leri de tara</label>
      <div style="display:flex;gap:6px;margin-top:10px;flex-wrap:wrap">
        <button class="btn-primary" id="scanBtn" onclick="scan('new')" style="flex:1">ÄŸÅ¸â€ â€¢ Yeni Tara</button>
        <button class="btn-ghost" onclick="scan('all')" title="TÃƒÂ¼m hafiza sifirla + bastan tara">ÄŸÅ¸â€â€ Hepsini Tara</button>
      </div>
      <div class="status" id="scanStatus"></div>
      <div id="seenInfo" style="font-size:11px;color:var(--muted);margin-top:4px"></div>

      <h3 style="margin-top:18px;">ÄŸÅ¸â€œâ€¹ Ãƒâ€“nceki Taramalar</h3>
      <div id="historyList" style="font-size:12px"></div>

      <h3 style="margin-top:18px;">Draft klasoru</h3>
      <div class="status">{{ default_draft }}</div>
      <div class="draft-list" id="draftList"></div>
    </div>

    <!-- ORTA: aday grid -->
    <div class="panel">
      <h3>2. Adaylar</h3>
      <div class="grid" id="candidateGrid"></div>
      <div class="status" id="candStatus">Henuz tarama yapilmadi.</div>
    </div>

    <!-- SAG: secili karta iyilestirme + caption -->
    <div class="panel">
      <h3>3. Iyilestirme</h3>
      <div class="preview" id="preview">Sol/orta panelden bir resim secin</div>
      <label>Format
        <select id="outFormat">
          <option value="portrait">Portre 1080x1350 (4:5)</option>
          <option value="square">Kare 1080x1080 (1:1)</option>
          <option value="story">Story 1080x1920 (9:16)</option>
          <option value="landscape">Yatay 1080x566 (1.91:1)</option>
          <option value="original">Orijinal</option>
        </select>
      </label>
      <label>Ust strip kirp (varsayilan 0.13 = %13)
        <input type="range" id="headerCrop" min="0" max="0.40" step="0.01" value="0.13">
        <span id="headerCropV">0.13</span>
      </label>
      <label>Netlik
        <input type="range" id="sharpen" min="0" max="3" step="0.1" value="1.2">
        <span id="sharpenV">1.2</span>
      </label>
      <label>Kontrast
        <input type="range" id="contrast" min="0.6" max="1.6" step="0.05" value="1.10">
        <span id="contrastV">1.10</span>
      </label>
      <label>Parlaklik
        <input type="range" id="brightness" min="0.6" max="1.6" step="0.05" value="1.05">
        <span id="brightnessV">1.05</span>
      </label>
      <label>Doygunluk
        <input type="range" id="saturation" min="0.0" max="1.6" step="0.05" value="1.05">
        <span id="saturationV">1.05</span>
      </label>
      <label><input type="checkbox" id="blurCorners"> Alt koseleri bulaniklastir (ek anonimleme)</label>
      <label><input type="checkbox" id="addWatermark" checked> Watermark "(c) Op. Dr. Hakan Yaz"</label>
      <button class="btn-primary" id="enhanceBtn" style="margin-top:10px;">Drafta Kaydet</button>
      <div class="status" id="enhanceStatus"></div>

      <h3 style="margin-top:18px;">4. Caption</h3>
      <label>Tema
        <select id="captionTheme">
          <option value="egitim_3d_4d">Egitim - 3D/4D</option>
          <option value="gebelik_takip">Gebelik takibi</option>
          <option value="kontrol_hatirlatma">Kontrol hatirlatma</option>
          <option value="farkindalik">Farkindalik</option>
        </select>
      </label>
      <label>Hashtag gruplari</label>
      <select id="hashGroups" multiple size="5" style="height:auto;">
        <option value="core_tr" selected>Turkce core</option>
        <option value="obgyn_intl">OB-GYN uluslararasi</option>
        <option value="specialty_3d4d">3D/4D bransi</option>
        <option value="ivf_ovulasyon">IVF/ovulasyon</option>
        <option value="brand" selected>Brand</option>
      </select>
      <button class="btn-ghost" id="captionBtn" style="margin-top:8px;">Caption Uret</button>
      <pre id="captionOut" style="margin-top:8px;">Tema sec ve "Caption Uret" tikla...</pre>
    </div>
  </div>

<script>
const state = { candidates: [], selectedIdx: -1, scanRoot: '' };

['headerCrop','sharpen','contrast','brightness','saturation'].forEach(id => {
  const el = document.getElementById(id);
  const out = document.getElementById(id + 'V');
  el.addEventListener('input', () => { out.textContent = el.value; });
});

// D700: Background job + polling - sayfayi terketsen bile devam eder
// + Mode'lar: 'new' (gorulen disla) / 'all' (hepsini tekrar getir)
let pollTimer = null;
let currentJobId = null;

async function scan(mode) {
  mode = mode || 'new';
  const status = document.getElementById('scanStatus');
  status.textContent = 'Ã¢ÂÂ³ Arka planda baslatiliyor (' + mode + ')...';
  status.className = 'status';
  if(pollTimer) clearInterval(pollTimer);
  try {
    const res = await fetch('/api/agents/instagram/scan', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      credentials: 'same-origin',
      body: JSON.stringify({
        root: document.getElementById('rootInput').value,
        max_candidates: parseInt(document.getElementById('maxCandidates').value),
        min_score: parseFloat(document.getElementById('minScore').value),
        include_pdf: document.getElementById('includePdf').checked,
        mode: mode,  // 'new' = onceki gorulenleri DISLA, 'all' = hepsini tekrar
      })
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || res.status);
    currentJobId = data.job_id;
    try { localStorage.setItem('yk_ig_last_job', data.job_id); } catch(e) {}
    const excl = data.excluded_count || 0;
    status.textContent = 'ÄŸÅ¸â€â€ Arka planda taraniyor' +
      (excl > 0 ? ' (' + excl + ' onceden gorulmus disli)' : '') +
      '... Sayfadan cikabilirsin.';
    pollStatus();
    pollTimer = setInterval(pollStatus, 3000);
  } catch (e) {
    status.textContent = 'Hata: ' + e.message;
    status.classList.add('fail');
  }
}

async function loadHistory() {
  try {
    const res = await fetch('/api/agents/instagram/history', {credentials:'same-origin'});
    const d = await res.json();
    if (!d.ok) return;
    const hl = document.getElementById('historyList');
    const seenInfo = document.getElementById('seenInfo');
    if (seenInfo) {
      seenInfo.innerHTML = d.seen_count > 0 ?
        'ÄŸÅ¸Â§Â  ' + d.seen_count + ' dosya hatirda (yeni taramada gozukmez) ' +
        '<a href="#" onclick="resetSeen();return false">[Sifirla]</a>' :
        'ÄŸÅ¸Â§Â  Hicbir dosya hatirda degil';
    }
    if (!d.history || d.history.length === 0) {
      hl.innerHTML = '<i style="color:#5e7185">HiÃƒÂ§ tarama yok</i>';
      return;
    }
    hl.innerHTML = d.history.map(h => {
      const dt = h.completed_at ? new Date(h.completed_at*1000).toLocaleTimeString('tr-TR') : 'devam ediyor';
      const stIcon = h.status === 'done' ? 'Ã¢Å“â€œ' :
                     h.status === 'failed' ? 'Ã¢Å“â€”' :
                     h.status === 'running' ? 'ÄŸÅ¸â€â€' : 'Ã¢ÂÂ³';
      return '<div onclick="loadJob(\'' + h.job_id + '\')" ' +
             'style="padding:6px 8px;border-bottom:1px solid #eef3f8;cursor:pointer;' +
             'touch-action:manipulation" onmouseover="this.style.background=\'#eff5fb\'" ' +
             'onmouseout="this.style.background=\'\'">' +
             stIcon + ' <b>' + dt + '</b> - ' + h.count + ' aday ' +
             '<small style="color:#5e7185">(' + h.scanned + ' tarandi)</small></div>';
    }).join('');
  } catch(e) { console.warn('[IG] history:', e); }
}

async function loadJob(jobId) {
  try {
    const res = await fetch('/api/agents/instagram/scan-status?job_id=' +
      encodeURIComponent(jobId), {credentials:'same-origin'});
    const d = await res.json();
    if (!d.ok || !d.result) return;
    state.candidates = d.result.candidates || [];
    state.scanRoot = d.result.root || '';
    renderCandidates();
    const status = document.getElementById('scanStatus');
    status.textContent = 'ÄŸÅ¸â€œâ€¹ Eski tarama yuklendi: ' + state.candidates.length + ' aday';
    status.className = 'status ok';
  } catch(e) { console.warn('[IG] loadJob:', e); }
}

async function resetSeen() {
  if (!confirm('Hafizayi sifirlamak istiyor musun?\nSonraki taramada TUM resimler tekrar gozukur.')) return;
  try {
    await fetch('/api/agents/instagram/seen-reset', {
      method:'POST', credentials:'same-origin'});
    alert('Sifirlandi. Yeni Tara butona basinca hepsi gozukur.');
    loadHistory();
  } catch(e) { alert('Hata: ' + e.message); }
}

async function pollStatus() {
  if(!currentJobId) return;
  try {
    const res = await fetch('/api/agents/instagram/scan-status?job_id=' +
      encodeURIComponent(currentJobId), {credentials: 'same-origin'});
    const data = await res.json();
    if (!data.ok) return;
    const status = document.getElementById('scanStatus');
    if (data.status === 'done') {
      clearInterval(pollTimer); pollTimer = null;
      const result = data.result || {};
      state.candidates = result.candidates || [];
      state.scanRoot = result.root || '';
      renderCandidates();
      status.textContent = 'Ã¢Å“â€œ ' + (result.scanned_count || 0) + ' dosya tarandi, ' +
        state.candidates.length + ' aday bulundu (' + data.elapsed_sec + 's)';
      status.className = 'status ok';
    } else if (data.status === 'failed') {
      clearInterval(pollTimer); pollTimer = null;
      status.textContent = 'Ã¢Å“â€” Hata: ' + (data.error || 'bilinmiyor');
      status.className = 'status fail';
    } else if (data.status === 'running' || data.status === 'pending') {
      status.textContent = 'ÄŸÅ¸â€â€ Devam ediyor... (' + data.elapsed_sec + 's)';
    }
  } catch(e) {
    console.warn('[IG] poll hatasi:', e);
  }
}

// SAYFA ACILDIGINDA: en son tarama varsa otomatik geri yukle
async function restoreLastScan() {
  const status = document.getElementById('scanStatus');
  try {
    const res = await fetch('/api/agents/instagram/scan-status',
      {credentials: 'same-origin'});
    const data = await res.json();
    if (!data.ok) return;
    currentJobId = data.job_id;
    if (data.status === 'done' && data.result) {
      // Hazir sonuclar var - direkt goster
      const result = data.result || {};
      state.candidates = result.candidates || [];
      state.scanRoot = result.root || '';
      renderCandidates();
      const ago = Math.round((Date.now()/1000 - (data.completed_at || 0)) / 60);
      status.textContent = 'ÄŸÅ¸â€œâ€¹ Onceki tarama yuklendi: ' + state.candidates.length +
        ' aday (' + ago + ' dk once tamamlandi)';
      status.className = 'status ok';
    } else if (data.status === 'running' || data.status === 'pending') {
      // Hala calisior - polling baslat
      status.textContent = 'ÄŸÅ¸â€â€ Onceki tarama hala devam ediyor (' + data.elapsed_sec + 's)...';
      status.className = 'status';
      pollStatus();
      pollTimer = setInterval(pollStatus, 3000);
    }
  } catch(e) {
    console.warn('[IG] restore:', e);
  }
}
// Sayfa yuklenince otomatik restore
window.addEventListener('DOMContentLoaded', restoreLastScan);

function renderCandidates() {
  const grid = document.getElementById('candidateGrid');
  const stat = document.getElementById('candStatus');
  if (!state.candidates.length) {
    grid.innerHTML = '';
    stat.textContent = 'Bu klasorde aday yok.';
    return;
  }
  grid.innerHTML = state.candidates.map((c, i) => {
    const thumbUrl = '/api/agents/instagram/thumbnail?path=' + encodeURIComponent(c.path) + '&size=240';
    const isPdf = c.is_pdf ? '<span class="badge-pdf">PDF</span>' : '';
    const score = (c.final_score * 100).toFixed(0);
    return `
      <div class="card" data-i="${i}" onclick="selectCandidate(${i})">
        <img src="${thumbUrl}" loading="lazy" alt="">
        <div class="meta">
          <div class="score">${score}/100 ${isPdf}</div>
          <div class="name" title="${c.filename}">${c.filename}</div>
        </div>
      </div>`;
  }).join('');
  stat.textContent = state.candidates.length + ' aday gosteriliyor.';
}

function selectCandidate(i) {
  state.selectedIdx = i;
  document.querySelectorAll('#candidateGrid .card').forEach((el, j) => {
    el.classList.toggle('selected', i === j);
  });
  const c = state.candidates[i];
  const preview = document.getElementById('preview');
  preview.innerHTML = '<img src="/api/agents/instagram/thumbnail?path='
    + encodeURIComponent(c.path) + '&size=600" alt="preview">';
}

async function enhance() {
  if (state.selectedIdx < 0) {
    alert('Once orta panelden bir resim secin.');
    return;
  }
  const c = state.candidates[state.selectedIdx];
  const status = document.getElementById('enhanceStatus');
  status.textContent = 'Iyilestiriliyor...';
  status.className = 'status';
  try {
    const res = await fetch('/api/agents/instagram/enhance', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      credentials: 'same-origin',
      body: JSON.stringify({
        source_path: c.path,
        output_format: document.getElementById('outFormat').value,
        header_crop_ratio: parseFloat(document.getElementById('headerCrop').value),
        sharpen: parseFloat(document.getElementById('sharpen').value),
        contrast: parseFloat(document.getElementById('contrast').value),
        brightness: parseFloat(document.getElementById('brightness').value),
        saturation: parseFloat(document.getElementById('saturation').value),
        blur_corners: document.getElementById('blurCorners').checked,
        add_watermark: document.getElementById('addWatermark').checked,
      })
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || res.status);
    const r = data.result;
    status.innerHTML = '<span class="status ok">Hazir:</span> ' + r.draft_path
      + ' (' + r.width + 'x' + r.height + ', ' + Math.round(r.size_bytes/1024) + ' KB)';
    addDraft(r.draft_path);
  } catch (e) {
    status.textContent = 'Hata: ' + e.message;
    status.classList.add('fail');
  }
}

function addDraft(path) {
  const list = document.getElementById('draftList');
  const fname = path.split(/[\\\\/]/).pop();
  const a = document.createElement('a');
  a.href = '/api/agents/instagram/draft-download?file=' + encodeURIComponent(fname);
  a.textContent = fname;
  a.title = path;
  a.download = fname;
  list.prepend(a);
}

async function captionGen() {
  const theme = document.getElementById('captionTheme').value;
  const groups = Array.from(document.getElementById('hashGroups').selectedOptions).map(o => o.value);
  const out = document.getElementById('captionOut');
  out.textContent = 'Uretiliyor...';
  try {
    const res = await fetch('/api/agents/instagram/caption', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      credentials: 'same-origin',
      body: JSON.stringify({theme, hashtag_groups: groups})
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || res.status);
    const ss = data.result.suggestions || [];
    out.textContent = ss.map((s, i) =>
      '--- Oneri ' + (i+1) + ' (' + s.char_count + ' karakter) ---\n' +
      s.text + '\n\n' + s.hashtags.join(' ')
    ).join('\n\n');
  } catch (e) {
    out.textContent = 'Hata: ' + e.message;
  }
}

document.getElementById('scanBtn').addEventListener('click', scan);
document.getElementById('enhanceBtn').addEventListener('click', enhance);
document.getElementById('captionBtn').addEventListener('click', captionGen);
</script>
</body></html>
"""


# === Tibbi Ceviri Ajani (PubMed + Ollama/OpenAI) ==========================

@agents_bp.route("/api/agents/ceviri/health", methods=["GET"])
def ceviri_health():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(ceviri_mod, "ceviri")
    if err:
        return err
    try:
        h = ceviri_mod.health_check()
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "agent": "ceviri", "error": str(exc)}), 500
    return jsonify({"ok": True, "agent": "ceviri", "result": h})


@agents_bp.route("/api/agents/ceviri/pubmed-search", methods=["POST"])
def ceviri_pubmed_search():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(ceviri_mod, "ceviri")
    if err:
        return err
    p = _payload()
    query = str(p.get("query") or "").strip()
    max_results = int(p.get("max_results") or 20)
    if not query:
        return jsonify({"ok": False, "agent": "ceviri", "error": "query gerekli"}), 400
    try:
        out = ceviri_mod.search_pubmed(query, max_results=max_results)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "agent": "ceviri", "error": str(exc)}), 500
    _safe_audit("agents:ceviri_search", {"query": query, "count": len(out.get("hits", []))})
    return jsonify({"ok": True, "agent": "ceviri", "result": out})


@agents_bp.route("/api/agents/ceviri/pubmed-fetch", methods=["POST"])
def ceviri_pubmed_fetch():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(ceviri_mod, "ceviri")
    if err:
        return err
    p = _payload()
    pmid = str(p.get("pmid") or "").strip()
    if not pmid:
        return jsonify({"ok": False, "agent": "ceviri", "error": "pmid gerekli"}), 400
    try:
        art = ceviri_mod.fetch_pubmed_pmid(pmid)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "agent": "ceviri", "error": str(exc)}), 500
    _safe_audit("agents:ceviri_fetch", {"pmid": pmid})
    return jsonify({"ok": True, "agent": "ceviri", "result": asdict(art)})


@agents_bp.route("/api/agents/ceviri/translate", methods=["POST"])
def ceviri_translate():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(ceviri_mod, "ceviri")
    if err:
        return err
    p = _payload()
    text = str(p.get("text") or "").strip()
    prefer = str(p.get("prefer") or "ollama")
    if not text:
        return jsonify({"ok": False, "agent": "ceviri", "error": "text gerekli"}), 400
    try:
        res = ceviri_mod.translate_smart(
            text, prefer=prefer,
            ollama_model=p.get("ollama_model"),
            openai_model=p.get("openai_model") or "gpt-4o-mini",
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "agent": "ceviri", "error": str(exc)}), 500
    _safe_audit("agents:ceviri_translate", {"method": res.method, "chars": len(text)})
    return jsonify({"ok": True, "agent": "ceviri", "result": asdict(res)})


@agents_bp.route("/api/agents/ceviri/summarize", methods=["POST"])
def ceviri_summarize():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(ceviri_mod, "ceviri")
    if err:
        return err
    p = _payload()
    text = str(p.get("text") or "").strip()
    prefer = str(p.get("prefer") or "ollama")
    if not text:
        return jsonify({"ok": False, "agent": "ceviri", "error": "text gerekli"}), 400
    try:
        res = ceviri_mod.summarize_smart(text, prefer=prefer,
                                          ollama_model=p.get("ollama_model"))
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "agent": "ceviri", "error": str(exc)}), 500
    return jsonify({"ok": True, "agent": "ceviri", "result": asdict(res)})


@agents_bp.route("/api/agents/ceviri/translate-pubmed", methods=["POST"])
def ceviri_translate_pubmed():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(ceviri_mod, "ceviri")
    if err:
        return err
    p = _payload()
    pmid = str(p.get("pmid") or "").strip()
    prefer = str(p.get("prefer") or "ollama")
    include_summary = bool(p.get("include_summary", True))
    if not pmid:
        return jsonify({"ok": False, "agent": "ceviri", "error": "pmid gerekli"}), 400
    try:
        full = ceviri_mod.translate_pubmed_article(pmid, prefer=prefer,
                                                     include_summary=include_summary)
        md = ceviri_mod.format_as_markdown(full)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "agent": "ceviri", "error": str(exc)}), 500
    _safe_audit("agents:ceviri_translate_pubmed", {"pmid": pmid, "method": full.method})
    payload = asdict(full)
    payload["markdown"] = md
    return jsonify({"ok": True, "agent": "ceviri", "result": payload})


@agents_bp.route("/api/agents/ceviri/prompt", methods=["POST"])
def ceviri_prompt_only():
    """LLM cagrisi yapmadan sadece prompt'u dondur (ChatGPT'ye yapistir)."""
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(ceviri_mod, "ceviri")
    if err:
        return err
    p = _payload()
    text = str(p.get("text") or "").strip()
    mode = str(p.get("mode") or "translate")  # 'translate' | 'summary'
    if not text:
        return jsonify({"ok": False, "agent": "ceviri", "error": "text gerekli"}), 400
    if mode == "summary":
        prompt = ceviri_mod.build_summary_prompt(text)
    else:
        prompt = ceviri_mod.build_translation_prompt(text)
    return jsonify({"ok": True, "agent": "ceviri", "result": {
        "prompt": prompt, "mode": mode, "char_count": len(prompt),
    }})


@agents_bp.route("/ceviri-merkezi", methods=["GET"])
def ceviri_page():
    auth = _require_session()
    if auth:
        return auth
    return render_template_string(_CEVIRI_PAGE)


_CEVIRI_PAGE = r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>Tibbi Ceviri Merkezi - YazKlinik</title>
<style>
  :root { --med-blue: #1769aa; --med-teal: #0c7488; --ink: #122236;
          --muted: #5e7185; --line: rgba(94,113,133,0.18);
          --surface: #ffffff; --bg: #f5f8fb; --ok: #16815f; --warn: #b8821f; --err: #b3261e; }
  body { font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
         background: var(--bg); color: var(--ink); margin: 0; padding: 18px; }
  h1 { margin: 0 0 4px; font-size: 22px; }
  .lead { color: var(--muted); font-size: 12px; margin: 0 0 14px; }
  .layout { display: grid; grid-template-columns: 320px 1fr; gap: 14px; align-items: start; }
  @media (max-width: 1000px) { .layout { grid-template-columns: 1fr; } }
  .panel { background: var(--surface); border: 1px solid var(--line);
           border-radius: 12px; padding: 14px; }
  .panel h3 { margin: 0 0 10px; font-size: 13px; color: var(--med-blue);
              text-transform: uppercase; letter-spacing: 0.6px; }
  label { display: block; font-size: 12px; color: var(--muted); margin: 8px 0 3px; }
  input[type=text], input[type=number], select, textarea {
    width: 100%; padding: 7px 10px; border: 1px solid var(--line);
    border-radius: 8px; background: #fafbfd; color: var(--ink); font-size: 13px;
    box-sizing: border-box; font-family: inherit;
  }
  textarea { resize: vertical; min-height: 100px; }
  button { display: inline-flex; align-items: center; gap: 6px;
           padding: 7px 14px; border: 0; border-radius: 8px; cursor: pointer;
           font-size: 13px; font-weight: 600; margin-top: 4px; }
  .btn-primary { background: linear-gradient(135deg, var(--med-blue), var(--med-teal)); color: #fff; }
  .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(23,105,170,0.25); }
  .btn-ghost { background: transparent; border: 1px solid var(--line); color: var(--ink); }
  .btn-ghost:hover { background: rgba(23,105,170,0.08); color: var(--med-blue); }
  .status { font-size: 12px; color: var(--muted); margin-top: 6px; }
  .status.ok { color: var(--ok); }
  .status.fail { color: var(--err); }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }
  .badge.ok { background: #e2f3eb; color: var(--ok); }
  .badge.warn { background: #fdf2db; color: var(--warn); }
  .badge.err { background: #fbe6e4; color: var(--err); }
  .results { margin-top: 8px; }
  .res-item { padding: 9px 10px; border: 1px solid var(--line); border-radius: 8px;
              margin-bottom: 6px; cursor: pointer; background: #fafbfd;
              transition: border-color 140ms ease, background 140ms ease; }
  .res-item:hover { border-color: var(--med-blue); background: #fff; }
  .res-item.sel { border-color: var(--med-teal); background: #e1f1f4; }
  .res-item .title { font-weight: 600; color: var(--ink); font-size: 13px; }
  .res-item .meta { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .twocol { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
  @media (max-width: 800px) { .twocol { grid-template-columns: 1fr; } }
  pre { background: #0d1117; color: #c9d1d9; padding: 10px; border-radius: 8px;
        font-size: 12px; max-height: 380px; overflow: auto; white-space: pre-wrap;
        font-family: ui-monospace, "Cascadia Mono", "Consolas", monospace; }
  .actions { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
  .copy-ok { color: var(--ok) !important; }
</style></head>
<body>
  <h1>Tibbi Ceviri Merkezi</h1>
  <p class="lead">PubMed makalesi cek + Turkce ceviri + ozet. Mevcut Ollama (qwen2.5:32b) yerel calisir; yoksa OpenAI'a duser, o da yoksa ChatGPT prompt'u verir.
     <span id="healthPill" class="badge warn">saglik kontrol ediliyor...</span></p>

  <div class="layout">

    <!-- SOL -->
    <div class="panel">
      <h3>1. Kaynak</h3>
      <label>PubMed sorgusu (ornek: "preeclampsia 2025 review")</label>
      <input type="text" id="pmQuery" placeholder="anahtar kelimeler...">
      <button class="btn-primary" id="searchBtn">PubMed Ara</button>
      <div class="results" id="searchResults"></div>
      <div class="status" id="searchStatus"></div>

      <label style="margin-top:14px;">Veya dogrudan PMID</label>
      <input type="text" id="pmidInput" placeholder="40123456">
      <button class="btn-primary" id="fetchBtn">PMID Getir + Ceviri</button>
      <div class="status" id="fetchStatus"></div>

      <h3 style="margin-top:18px;">2. Ya da serbest metin</h3>
      <textarea id="freeText" placeholder="Ingilizce metin yapistir..."></textarea>
      <div class="actions">
        <button class="btn-primary" id="freeTranslateBtn">Ceviri (oto)</button>
        <button class="btn-ghost" id="freeSummaryBtn">Ozet (TR)</button>
        <button class="btn-ghost" id="freePromptBtn">ChatGPT promptu</button>
      </div>
      <div class="status" id="freeStatus"></div>

      <h3 style="margin-top:18px;">Tercih</h3>
      <label>LLM oncelik
        <select id="prefer">
          <option value="ollama">Ollama (yerel)</option>
          <option value="openai">OpenAI</option>
          <option value="prompt_only">Sadece prompt</option>
        </select>
      </label>
      <label><input type="checkbox" id="incSummary" checked> Ozet de uret</label>
    </div>

    <!-- SAG -->
    <div class="panel">
      <h3>Sonuc</h3>
      <div id="articleHead"></div>
      <div class="twocol">
        <div>
          <label style="font-weight:600;color:var(--ink);">English</label>
          <pre id="enOut">(bekleniyor)</pre>
        </div>
        <div>
          <label style="font-weight:600;color:var(--ink);">Turkce</label>
          <pre id="trOut">(bekleniyor)</pre>
        </div>
      </div>
      <label style="font-weight:600;color:var(--ink);">Ozet (TR)</label>
      <pre id="sumOut">(bekleniyor)</pre>

      <div class="actions">
        <button class="btn-ghost" id="copyTrBtn">TR ceviriyi kopyala</button>
        <button class="btn-ghost" id="copyMdBtn">Tum markdown kopyala</button>
        <button class="btn-ghost" id="downloadMdBtn">Markdown indir</button>
        <button class="btn-ghost" id="sendAlexBtn">Alex'e gonder</button>
      </div>
      <div class="status" id="mainStatus"></div>
    </div>
  </div>

<script>
const S = { results: [], selectedPmid: null, currentMarkdown: '', currentArticle: null };

async function checkHealth() {
  try {
    const r = await fetch('/api/agents/ceviri/health', {credentials: 'same-origin'});
    const d = await r.json();
    if (!d.ok) throw 0;
    const h = d.result;
    const ollama = h.ollama_available ? 'Ollama OK (' + (h.ollama_model||'?') + ')' : 'Ollama yok';
    const oa = h.openai_available ? 'OpenAI OK' : 'OpenAI yok';
    const pm = h.pubmed_reachable ? 'PubMed OK' : 'PubMed yok';
    const pill = document.getElementById('healthPill');
    pill.textContent = ollama + ' | ' + oa + ' | ' + pm;
    pill.className = 'badge ' + (h.ollama_available || h.openai_available ? 'ok' : 'warn');
  } catch (e) {
    document.getElementById('healthPill').textContent = 'saglik kontrol hatasi';
  }
}

async function pmSearch() {
  const q = document.getElementById('pmQuery').value.trim();
  const status = document.getElementById('searchStatus');
  status.textContent = 'aranÃ„Â±yor...'; status.className = 'status';
  try {
    const r = await fetch('/api/agents/ceviri/pubmed-search', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      credentials: 'same-origin',
      body: JSON.stringify({query: q, max_results: 20}),
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || r.status);
    S.results = d.result.hits || [];
    renderResults();
    status.textContent = S.results.length + ' sonuc.';
    status.className = 'status ok';
  } catch (e) {
    status.textContent = 'Hata: ' + e.message; status.className = 'status fail';
  }
}

function renderResults() {
  const box = document.getElementById('searchResults');
  if (!S.results.length) { box.innerHTML = ''; return; }
  box.innerHTML = S.results.map(h => `
    <div class="res-item" data-pmid="${h.pmid}" onclick="selectHit('${h.pmid}')">
      <div class="title">${escapeHtml(h.title)}</div>
      <div class="meta">${h.year} Ã‚Â· ${escapeHtml(h.journal)} Ã‚Â· PMID ${h.pmid}</div>
    </div>
  `).join('');
}

function escapeHtml(s) { return String(s||'').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]); }

function selectHit(pmid) {
  S.selectedPmid = pmid;
  document.querySelectorAll('#searchResults .res-item').forEach(el => {
    el.classList.toggle('sel', el.dataset.pmid === pmid);
  });
  document.getElementById('pmidInput').value = pmid;
  fetchAndTranslate();
}

async function fetchAndTranslate() {
  const pmid = (document.getElementById('pmidInput').value || S.selectedPmid || '').trim();
  if (!pmid) { alert('PMID lazim'); return; }
  const status = document.getElementById('fetchStatus');
  const mainStatus = document.getElementById('mainStatus');
  status.textContent = 'PMID ' + pmid + ' getiriliyor + cevriliyor...';
  status.className = 'status';
  mainStatus.textContent = '';
  document.getElementById('enOut').textContent = 'cekiliyor...';
  document.getElementById('trOut').textContent = 'cevriliyor...';
  document.getElementById('sumOut').textContent = '';

  try {
    const prefer = document.getElementById('prefer').value;
    const inc = document.getElementById('incSummary').checked;
    const r = await fetch('/api/agents/ceviri/translate-pubmed', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      credentials: 'same-origin',
      body: JSON.stringify({pmid: pmid, prefer: prefer, include_summary: inc}),
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || r.status);
    const res = d.result;
    S.currentMarkdown = res.markdown || '';
    S.currentArticle = res;
    const a = res.article || {};
    document.getElementById('articleHead').innerHTML = `
      <div style="margin-bottom:8px;">
        <div style="font-weight:700;font-size:14px;">${escapeHtml(a.title || '(baslik yok)')}</div>
        ${res.title_tr ? '<div style="color:var(--med-teal);font-size:13px;margin-top:2px;">TR: ' + escapeHtml(res.title_tr) + '</div>' : ''}
        <div style="font-size:11px;color:var(--muted);margin-top:4px;">
          ${escapeHtml((a.authors||[]).slice(0,4).join(', '))} Ã‚Â· ${escapeHtml(a.journal||'')} Ã‚Â· ${a.year||''} Ã‚Â· PMID ${a.pmid}
          ${a.doi ? ' Ã‚Â· <a href="https://doi.org/' + a.doi + '" target="_blank">DOI</a>' : ''}
          Ã‚Â· <a href="${a.pubmed_url}" target="_blank">PubMed</a>
        </div>
      </div>`;
    document.getElementById('enOut').textContent = a.abstract || '(abstract bos)';
    document.getElementById('trOut').textContent = res.abstract_tr || '(ceviri bos)';
    document.getElementById('sumOut').textContent = res.summary_tr || '(ozet yok)';
    const chain = (res.fallback_chain||[]).join(' -> ');
    status.textContent = 'tamamlandi (' + chain + ')';
    status.className = 'status ok';
    if (res.error) {
      mainStatus.textContent = 'Uyari: ' + res.error;
      mainStatus.className = 'status fail';
    }
  } catch (e) {
    status.textContent = 'Hata: ' + e.message;
    status.className = 'status fail';
  }
}

async function freeTranslate(mode) {
  const text = document.getElementById('freeText').value.trim();
  if (!text) { alert('Once metin yapistir'); return; }
  const status = document.getElementById('freeStatus');
  status.textContent = mode + ' isleniyor...'; status.className = 'status';
  document.getElementById('enOut').textContent = text;
  document.getElementById('trOut').textContent = mode === 'prompt' ? '' : 'cevriliyor...';
  document.getElementById('sumOut').textContent = '';
  try {
    let url = '/api/agents/ceviri/translate';
    let body = {text, prefer: document.getElementById('prefer').value};
    if (mode === 'summary') url = '/api/agents/ceviri/summarize';
    if (mode === 'prompt') { url = '/api/agents/ceviri/prompt'; body = {text, mode: 'translate'}; }
    const r = await fetch(url, {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      credentials: 'same-origin', body: JSON.stringify(body),
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || r.status);
    if (mode === 'prompt') {
      document.getElementById('trOut').textContent = d.result.prompt;
      status.textContent = 'Prompt hazir - kopyalayip ChatGPT\\'ye yapistirin.';
    } else if (mode === 'summary') {
      document.getElementById('sumOut').textContent = d.result.translated_text;
      status.textContent = 'Ozet hazir.';
    } else {
      document.getElementById('trOut').textContent = d.result.translated_text;
      status.textContent = 'Ceviri hazir (' + d.result.method + ').';
    }
    status.classList.add('ok');
  } catch (e) {
    status.textContent = 'Hata: ' + e.message; status.classList.add('fail');
  }
}

function copyToClipboard(text, btn) {
  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = 'Ã¢Å“â€œ kopyalandi';
    btn.classList.add('copy-ok');
    setTimeout(() => { btn.textContent = orig; btn.classList.remove('copy-ok'); }, 1400);
  });
}

document.getElementById('searchBtn').addEventListener('click', pmSearch);
document.getElementById('fetchBtn').addEventListener('click', fetchAndTranslate);
document.getElementById('freeTranslateBtn').addEventListener('click', () => freeTranslate('translate'));
document.getElementById('freeSummaryBtn').addEventListener('click', () => freeTranslate('summary'));
document.getElementById('freePromptBtn').addEventListener('click', () => freeTranslate('prompt'));

document.getElementById('copyTrBtn').addEventListener('click', (e) => {
  copyToClipboard(document.getElementById('trOut').textContent, e.target);
});
document.getElementById('copyMdBtn').addEventListener('click', (e) => {
  copyToClipboard(S.currentMarkdown || document.getElementById('trOut').textContent, e.target);
});
document.getElementById('downloadMdBtn').addEventListener('click', () => {
  const md = S.currentMarkdown || document.getElementById('trOut').textContent;
  if (!md) return;
  const blob = new Blob([md], {type: 'text/markdown;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  const pmid = S.selectedPmid || 'metin';
  a.download = 'ceviri_' + pmid + '_' + Date.now() + '.md';
  a.click();
});
document.getElementById('sendAlexBtn').addEventListener('click', () => {
  const tr = document.getElementById('trOut').textContent || '';
  const inp = document.getElementById('ykVoiceQuickText');
  if (inp) {
    inp.value = 'Bu makaleye dair kisa yorumun nedir?\\n' + tr.slice(0, 1500);
    inp.focus();
    document.getElementById('mainStatus').textContent = 'Alex inputuna yazildi.';
    document.getElementById('mainStatus').className = 'status ok';
  } else {
    document.getElementById('mainStatus').textContent = 'Alex bar bu sayfada degil.';
    document.getElementById('mainStatus').className = 'status fail';
  }
});

checkHealth();
</script>
</body></html>
"""


# === YZ Konsultasyon Ajani ================================================

@agents_bp.route("/api/agents/konsult/health", methods=["GET"])
def konsult_health():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(konsult_mod, "konsult")
    if err:
        return err
    try:
        return jsonify({"ok": True, "agent": "konsult", "result": konsult_mod.health_check()})
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "agent": "konsult", "error": str(e)}), 500


@agents_bp.route("/api/agents/konsult/extract", methods=["POST"])
def konsult_extract():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(konsult_mod, "konsult")
    if err:
        return err
    p = _payload()
    text = str(p.get("text") or "").strip()
    if not text:
        return jsonify({"ok": False, "agent": "konsult", "error": "text gerekli"}), 400
    try:
        case, trace = konsult_mod.extract_case(text, prefer=str(p.get("prefer") or "ollama"))
    except Exception as e:  # noqa: BLE001
        return jsonify({"ok": False, "agent": "konsult", "error": str(e)}), 500
    return jsonify({"ok": True, "agent": "konsult",
                     "result": {"case": asdict(case), "trace": trace}})


@agents_bp.route("/api/agents/konsult/full", methods=["POST"])
def konsult_full():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(konsult_mod, "konsult")
    if err:
        return err
    p = _payload()
    text = str(p.get("text") or "").strip()
    prefer = str(p.get("prefer") or "ollama")
    skip = p.get("skip_steps") or []
    if not isinstance(skip, list):
        skip = []
    if not text:
        return jsonify({"ok": False, "agent": "konsult", "error": "text gerekli"}), 400
    try:
        res = konsult_mod.full_consultation(text, prefer=prefer, skip_steps=[str(s) for s in skip])
        md = konsult_mod.format_as_markdown(res, include_trace=bool(p.get("include_trace")))
    except Exception as e:  # noqa: BLE001
        import traceback as _tb
        return jsonify({"ok": False, "agent": "konsult", "error": str(e),
                         "trace": _tb.format_exc(limit=3)}), 500
    _safe_audit("agents:konsult_full", {"chars": len(text), "confidence": res.confidence,
                                          "ddx_count": len(res.differentials)})
    payload = asdict(res)
    payload["markdown"] = md
    return jsonify({"ok": True, "agent": "konsult", "result": payload})


@agents_bp.route("/yz-konsultasyon", methods=["GET"])
def konsult_page():
    auth = _require_session()
    if auth:
        return auth
    return render_template_string(_KONSULT_PAGE)


_KONSULT_PAGE = r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>YZ Konsultasyon - YazKlinik</title>
<style>
  :root { --med-blue: #1769aa; --med-teal: #0c7488; --med-rose: #c2185b;
          --med-green: #16815f; --med-amber: #b8821f; --med-red: #b3261e;
          --med-violet: #6f4cb8;
          --ink: #122236; --muted: #5e7185; --line: rgba(94,113,133,0.18);
          --surface: #ffffff; --bg: #f5f8fb; }
  body { font-family: -apple-system, "Segoe UI", system-ui, sans-serif;
         background: var(--bg); color: var(--ink); margin: 0; padding: 18px; }
  h1 { margin: 0 0 4px; font-size: 22px; }
  .lead { color: var(--muted); font-size: 12px; margin: 0 0 12px; }
  .warn { background: #fff8e1; border: 1px solid #f0c14b; padding: 8px 12px;
          border-radius: 8px; color: #7a5612; font-size: 12px; margin-bottom: 14px; }
  .layout { display: grid; grid-template-columns: 380px 1fr; gap: 14px; align-items: start; }
  @media (max-width: 1100px) { .layout { grid-template-columns: 1fr; } }
  .panel { background: var(--surface); border: 1px solid var(--line);
           border-radius: 12px; padding: 14px; }
  .panel h3 { margin: 0 0 10px; font-size: 13px; color: var(--med-blue);
              text-transform: uppercase; letter-spacing: 0.6px; }
  label { display: block; font-size: 12px; color: var(--muted); margin: 8px 0 3px; }
  textarea, input[type=text], select { width: 100%; padding: 8px 10px;
    border: 1px solid var(--line); border-radius: 8px; background: #fafbfd;
    color: var(--ink); font-size: 13px; box-sizing: border-box; font-family: inherit; }
  textarea { resize: vertical; min-height: 180px; }
  button { display: inline-flex; align-items: center; gap: 6px;
    padding: 8px 16px; border: 0; border-radius: 8px; cursor: pointer;
    font-size: 13px; font-weight: 600; }
  .btn-primary { background: linear-gradient(135deg, var(--med-blue), var(--med-teal)); color: #fff; }
  .btn-primary:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(23,105,170,0.25); }
  .btn-ghost { background: transparent; border: 1px solid var(--line); color: var(--ink); }
  .btn-ghost:hover { background: rgba(23,105,170,0.08); color: var(--med-blue); }
  .status { font-size: 12px; color: var(--muted); margin-top: 8px; }
  .status.ok { color: var(--med-green); } .status.fail { color: var(--med-red); }
  .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; font-weight: 600; }
  .b-high { background: #fbe6e4; color: var(--med-red); }
  .b-med  { background: #fdf2db; color: var(--med-amber); }
  .b-low  { background: #e2f3eb; color: var(--med-green); }
  .b-urg  { background: var(--med-red); color: #fff; }
  .b-pri  { background: var(--med-amber); color: #fff; }
  .b-rou  { background: var(--med-teal); color: #fff; }
  .b-cat  { background: rgba(111,76,184,0.16); color: var(--med-violet); }
  .red-flag-box { background: #fbe6e4; border-left: 4px solid var(--med-red);
    padding: 10px 14px; border-radius: 8px; margin-bottom: 12px; }
  .red-flag-box h4 { margin: 0 0 6px; color: var(--med-red); font-size: 13px; }
  .ddx-card { background: #fff; border: 1px solid var(--line); border-radius: 10px;
    padding: 12px 14px; margin-bottom: 10px; }
  .ddx-card h4 { margin: 0; font-size: 14px; display: flex;
    align-items: center; justify-content: space-between; gap: 8px; }
  .ddx-card .reasoning { margin-top: 8px; font-size: 12px; color: var(--ink); }
  .ddx-card ul { margin: 4px 0; padding-left: 20px; font-size: 12px; }
  .ddx-card .meta { font-size: 11px; color: var(--muted); margin-top: 4px; }
  .workup-item, .tx-item, .fu-item { padding: 8px 12px; border-left: 3px solid var(--line);
    background: #fafbfd; border-radius: 6px; margin-bottom: 6px; font-size: 13px; }
  .workup-item.urgent { border-left-color: var(--med-red); }
  .workup-item.priority { border-left-color: var(--med-amber); }
  .workup-item .extra { font-size: 11px; color: var(--muted); margin-top: 2px; }
  .tx-item { border-left-color: var(--med-teal); }
  .tx-item .dose { color: var(--med-blue); font-weight: 600; }
  .case-card { background: #f4f8fc; border-radius: 8px; padding: 10px 12px;
    font-size: 12px; margin-bottom: 10px; }
  .case-card div { margin: 2px 0; }
  .actions { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 12px; }
  pre.md-export { background: #0d1117; color: #c9d1d9; padding: 12px; border-radius: 8px;
    font-size: 11px; max-height: 300px; overflow: auto; white-space: pre-wrap;
    font-family: ui-monospace, "Cascadia Mono", "Consolas", monospace; }
  .skeleton { background: #e2eaf2; height: 14px; border-radius: 4px; margin: 4px 0;
    animation: pulse 1.4s ease-in-out infinite; }
  @keyframes pulse { 0%,100% { opacity: 0.5; } 50% { opacity: 1; } }
  .examples { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 6px; }
  .examples button { font-size: 11px; padding: 4px 8px; background: #eef4fa;
    color: var(--med-blue); border: 0; border-radius: 999px; cursor: pointer; }
  .examples button:hover { background: rgba(23,105,170,0.18); }
  details { background: #fafbfd; border: 1px solid var(--line); border-radius: 8px;
    padding: 8px 12px; margin-top: 12px; font-size: 12px; }
  details summary { cursor: pointer; font-weight: 600; color: var(--med-blue); }
</style></head>
<body>
  <h1>YZ Konsultasyon (Multi-Step OB-GYN)</h1>
  <p class="lead">5 adimli akilli zincir: vaka ayriklastir Ã¢â€ â€™ kirmizi alarm + DDx Ã¢â€ â€™ tetkik Ã¢â€ â€™ tedavi Ã¢â€ â€™ takip. Yerel Ollama (qwen2.5:32b) yi kullanir; OpenAI varsa fallback.
     <span id="healthPill" class="badge b-med">saglik kontrol...</span></p>
  <div class="warn"><strong>UYARI:</strong> Bu sistemin ciktilari klinik karar destek niteligindedir; KESINLIKLE klinik karar yerine gecmez. Tum oneriler yetkili hekim tarafindan dogrulanmadan uygulanmamalidir.</div>

  <div class="layout">
    <!-- SOL: Vaka girisi -->
    <div class="panel">
      <h3>Vaka</h3>
      <label>Vaka tarifi (serbest metin, hasta adi/TC YAZMAYIN)</label>
      <textarea id="caseText" placeholder="Ornek: 32 yas, G2P1, 34 hafta gebe. 2 gundur basagrisi, gorme bulaniklasti. TA 158/102, idrar testinde ++ proteinuri. Onceki gebelikte gestasyonel diyabet vardi."></textarea>
      <div class="examples">
        <button onclick="loadExample(1)">Preeklampsi suphesi</button>
        <button onclick="loadExample(2)">Acil PPH</button>
        <button onclick="loadExample(3)">PCOS infertilite</button>
        <button onclick="loadExample(4)">PID</button>
      </div>
      <label style="margin-top:10px;">LLM tercih</label>
      <select id="prefer">
        <option value="ollama">Ollama (yerel, qwen2.5:32b)</option>
        <option value="openai">OpenAI</option>
      </select>
      <div class="actions">
        <button class="btn-primary" id="runFullBtn">Tam Konsultasyon</button>
        <button class="btn-ghost" id="runExtractBtn">Sadece Vaka Yapilandir</button>
      </div>
      <div class="status" id="runStatus"></div>
    </div>

    <!-- SAG: Sonuc -->
    <div class="panel" id="resultPanel">
      <h3>Sonuc</h3>
      <div id="resultArea" style="font-size:13px;color:var(--muted);">
        Sol panele vaka yazip "Tam Konsultasyon" tikla.
      </div>
    </div>
  </div>

<script>
const EXAMPLES = {
  1: '32 yas, G2P1, 34 hafta gebe. Son 2 gundur frontal basagrisi var, bugun gorme bulaniklasti. TA: 158/102, nabiz 92, ates 36.8. Spot idrar +++ protein. Bacaklarda 2+ odem. Onceki gebelikte gestasyonel diyabet vardi.',
  2: '28 yas, G1P1, normal vaginal dogum yapali 30 dakika oldu. Dogum sonrasi devam eden parlak kirmizi vajinal kanama, su ana kadar 800 cc. TA 100/60, nabiz 110, uterus gevsek hissediliyor. Plasenta cikti.',
  3: '26 yas, evli 3 yildir cocuk yok. Adetler duzensiz (40-90 gun arasi), kilo problemi var (BMI 32). Yuzde tuylenme, akne. Onceki HSG normal, esinin spermiyogrami normal. AMH yuksek.',
  4: '24 yas, cinsel aktif, 2 partner. Son 5 gundur alt karin agrisi, kotu kokulu vajinal akinti, ates 38.4. Adet gecikmesi yok, son adet 10 gun once. Servikal hareket hassasiyeti var.'
};

function loadExample(i) {
  document.getElementById('caseText').value = EXAMPLES[i] || '';
}

async function checkHealth() {
  try {
    const r = await fetch('/api/agents/konsult/health', {credentials: 'same-origin'});
    const d = await r.json();
    const h = d.result || {};
    const llm = (h.llm || {});
    const pill = document.getElementById('healthPill');
    if (llm.ollama_available) {
      pill.textContent = 'Ollama OK (' + (llm.ollama_model || '?') + ')';
      pill.className = 'badge b-low';
    } else if (llm.openai_available) {
      pill.textContent = 'OpenAI OK';
      pill.className = 'badge b-low';
    } else {
      pill.textContent = 'LLM erisilemez';
      pill.className = 'badge b-high';
    }
  } catch (e) {
    document.getElementById('healthPill').textContent = 'saglik bilinmiyor';
  }
}

function escapeHtml(s) {
  return String(s||'').replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]);
}

function probBadge(p) {
  if (p === 'high') return '<span class="badge b-high">yuksek</span>';
  if (p === 'low') return '<span class="badge b-low">dusuk</span>';
  return '<span class="badge b-med">orta</span>';
}
function priBadge(p) {
  if (p === 'urgent') return '<span class="badge b-urg">acil</span>';
  if (p === 'priority') return '<span class="badge b-pri">oncelikli</span>';
  return '<span class="badge b-rou">rutin</span>';
}

async function runFull() {
  const text = document.getElementById('caseText').value.trim();
  if (!text) { alert('Once vaka yaz'); return; }
  const prefer = document.getElementById('prefer').value;
  const status = document.getElementById('runStatus');
  const out = document.getElementById('resultArea');
  status.textContent = 'YZ dusunuyor (10-30 sn surebilir)...';
  status.className = 'status';
  out.innerHTML = '<div class="skeleton" style="width:60%"></div><div class="skeleton" style="width:90%"></div><div class="skeleton" style="width:75%"></div><div class="skeleton" style="width:85%"></div>';
  try {
    const r = await fetch('/api/agents/konsult/full', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      credentials: 'same-origin',
      body: JSON.stringify({text, prefer, include_trace: false}),
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || r.status);
    renderResult(d.result);
    status.textContent = 'Tamamlandi. Guven: ' + d.result.confidence
      + ' | yontem: ' + (d.result.used_methods||[]).join(', ');
    status.className = 'status ok';
  } catch (e) {
    status.textContent = 'Hata: ' + e.message;
    status.className = 'status fail';
    out.innerHTML = '<div style="color:var(--med-red);font-size:12px;">' + escapeHtml(e.message) + '</div>';
  }
}

async function runExtract() {
  const text = document.getElementById('caseText').value.trim();
  if (!text) { alert('Once vaka yaz'); return; }
  const status = document.getElementById('runStatus');
  status.textContent = 'Vaka yapilandiriliyor...';
  try {
    const r = await fetch('/api/agents/konsult/extract', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      credentials: 'same-origin',
      body: JSON.stringify({text, prefer: document.getElementById('prefer').value}),
    });
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || r.status);
    const c = d.result.case;
    document.getElementById('resultArea').innerHTML = `
      <h3 style="font-size:14px;color:var(--med-blue);margin:0 0 8px;">Yapilandirilmis Vaka</h3>
      <div class="case-card">
        ${c.yas ? '<div>Yas: <b>' + c.yas + '</b></div>' : ''}
        ${c.gravide ? '<div>Gravide: <b>' + c.gravide + '</b></div>' : ''}
        ${c.parite ? '<div>Parite: <b>' + escapeHtml(c.parite) + '</b></div>' : ''}
        ${c.gebelik_haftasi ? '<div>Gebelik haftasi: <b>' + c.gebelik_haftasi + '</b></div>' : ''}
        ${c.presenting_complaint ? '<div>Sikayet: <b>' + escapeHtml(c.presenting_complaint) + '</b></div>' : ''}
        ${(c.associated_symptoms||[]).length ? '<div>Eslik eden: ' + c.associated_symptoms.map(escapeHtml).join(', ') + '</div>' : ''}
        ${Object.keys(c.vitals||{}).length ? '<div>Vitaller: ' + Object.entries(c.vitals).map(([k,v]) => k+': '+v).join(' | ') + '</div>' : ''}
        ${(c.risk_factors||[]).length ? '<div>Risk: ' + c.risk_factors.map(escapeHtml).join(', ') + '</div>' : ''}
      </div>
      ${(c.missing_critical_info||[]).length ? `
        <div class="red-flag-box"><h4>Eksik Kritik Bilgi</h4>
          <ul style="margin:0;padding-left:20px;">
            ${c.missing_critical_info.map(m => '<li>' + escapeHtml(m) + '</li>').join('')}
          </ul>
        </div>` : ''}`;
    status.textContent = 'Yapilandirma tamam'; status.className = 'status ok';
  } catch (e) {
    status.textContent = 'Hata: ' + e.message; status.className = 'status fail';
  }
}

function renderResult(r) {
  const c = r.case || {};
  const html = [];

  // Kirmizi alarm
  if ((r.red_flags||[]).length) {
    html.push(`<div class="red-flag-box"><h4>KIRMIZI ALARMLAR (${r.red_flags.length})</h4>
      <ul style="margin:0;padding-left:20px;">
        ${r.red_flags.map(x => '<li>' + escapeHtml(x) + '</li>').join('')}
      </ul></div>`);
  }

  // Vaka ozeti
  html.push('<h3 style="font-size:14px;color:var(--med-blue);margin:14px 0 6px;">Yapilandirilmis Vaka</h3>');
  const meta = [];
  if (c.yas) meta.push('Yas: <b>'+c.yas+'</b>');
  if (c.gravide) meta.push('G: <b>'+c.gravide+'</b>');
  if (c.parite) meta.push('Parite: <b>'+escapeHtml(c.parite)+'</b>');
  if (c.gebelik_haftasi) meta.push('Gebelik: <b>'+c.gebelik_haftasi+'h</b>');
  html.push('<div class="case-card">' + meta.join(' Ã‚Â· '));
  if (c.presenting_complaint) html.push('<div>Sikayet: '+escapeHtml(c.presenting_complaint)+'</div>');
  if ((c.risk_factors||[]).length) html.push('<div>Risk: '+c.risk_factors.map(escapeHtml).join(', ')+'</div>');
  html.push('</div>');

  // Most likely
  if (r.most_likely) {
    html.push('<div style="font-size:13px;margin:10px 0;">En muhtemel: <b style="color:var(--med-violet);">'+escapeHtml(r.most_likely)+'</b></div>');
  }

  // DDx
  if ((r.differentials||[]).length) {
    html.push('<h3 style="font-size:14px;color:var(--med-blue);margin:14px 0 6px;">Ayirici Tanilar ('+r.differentials.length+')</h3>');
    r.differentials.forEach((d, i) => {
      const sup = (d.supporting_findings||[]).map(escapeHtml);
      const ag  = (d.against_findings||[]).map(escapeHtml);
      const urgPill = d.severity === 'urgent' ? ' <span class="badge b-urg">ACIL</span>' : '';
      html.push(`<div class="ddx-card">
        <h4><span>${i+1}. ${escapeHtml(d.diagnosis)} ${urgPill}</span>${probBadge(d.probability)}</h4>
        <div class="meta">${d.icd10 ? 'ICD-10: <code>'+escapeHtml(d.icd10)+'</code> Ã‚Â· ' : ''}${d.next_step_to_confirm ? 'Dogrulamak icin: '+escapeHtml(d.next_step_to_confirm) : ''}</div>
        ${sup.length ? '<div class="reasoning">Lehine:<ul>'+sup.map(x=>'<li>'+x+'</li>').join('')+'</ul></div>' : ''}
        ${ag.length ? '<div class="reasoning">Aleyhine:<ul>'+ag.map(x=>'<li>'+x+'</li>').join('')+'</ul></div>' : ''}
        ${d.notes ? '<div class="meta">Not: '+escapeHtml(d.notes)+'</div>' : ''}
      </div>`);
    });
  }

  // Workup
  if ((r.workup||[]).length) {
    html.push('<h3 style="font-size:14px;color:var(--med-blue);margin:14px 0 6px;">Onerilen Tetkik (' + r.workup.length + ')</h3>');
    const order = {'urgent':0,'priority':1,'routine':2};
    const sorted = r.workup.slice().sort((a,b) => (order[a.priority]||9) - (order[b.priority]||9));
    sorted.forEach(w => {
      html.push(`<div class="workup-item ${w.priority||'routine'}">
        ${priBadge(w.priority)} <b>${escapeHtml(w.name)}</b> <span class="badge b-cat">${escapeHtml(w.category)}</span>
        ${w.rationale ? '<div class="extra">Sebep: '+escapeHtml(w.rationale)+'</div>' : ''}
        ${w.expected_finding ? '<div class="extra">Beklenen: '+escapeHtml(w.expected_finding)+'</div>' : ''}
      </div>`);
    });
  }

  // Treatment
  if ((r.treatment||[]).length) {
    html.push('<h3 style="font-size:14px;color:var(--med-blue);margin:14px 0 6px;">Tedavi Plani ('+r.treatment.length+')</h3>');
    r.treatment.forEach(tx => {
      const preg = tx.pregnancy_category ? ' <span class="badge b-cat">Gebe kat: '+escapeHtml(tx.pregnancy_category)+'</span>' : '';
      html.push(`<div class="tx-item">
        <b>${escapeHtml(tx.line || '')} - ${escapeHtml(tx.name)}</b> ${preg}
        ${tx.dose ? '<div class="dose">'+escapeHtml(tx.dose)+'</div>' : ''}
        ${tx.duration ? '<div class="extra">Sure: '+escapeHtml(tx.duration)+'</div>' : ''}
        ${(tx.contraindications||[]).length ? '<div class="extra" style="color:var(--med-red);">Kontrendike: '+tx.contraindications.map(escapeHtml).join(', ')+'</div>' : ''}
        ${tx.notes ? '<div class="extra">Not: '+escapeHtml(tx.notes)+'</div>' : ''}
      </div>`);
    });
  }

  // Follow-up
  const fu = r.follow_up || {};
  if (fu.interval || (fu.what_to_watch||[]).length || (fu.patient_counseling||[]).length) {
    html.push('<h3 style="font-size:14px;color:var(--med-blue);margin:14px 0 6px;">Takip Plani</h3>');
    if (fu.interval) html.push('<div class="fu-item"><b>Aralik:</b> '+escapeHtml(fu.interval)+'</div>');
    if ((fu.what_to_watch||[]).length) html.push('<div class="fu-item"><b>Izlenecek:</b> '+fu.what_to_watch.map(escapeHtml).join(', ')+'</div>');
    if ((fu.red_flags_to_return||[]).length) html.push('<div class="fu-item" style="border-left-color:var(--med-red);"><b>Acilen donmesi gereken durumlar:</b><ul style="margin:4px 0;padding-left:20px;">'+fu.red_flags_to_return.map(x => '<li>'+escapeHtml(x)+'</li>').join('')+'</ul></div>');
    if ((fu.patient_counseling||[]).length) html.push('<div class="fu-item"><b>Hasta egitimi:</b><ul style="margin:4px 0;padding-left:20px;">'+fu.patient_counseling.map(x => '<li>'+escapeHtml(x)+'</li>').join('')+'</ul></div>');
  }

  if (r.patient_summary_tr) {
    html.push('<details open><summary>Hastaya soylenecek (taslak)</summary><p style="margin:8px 0 0;">'+escapeHtml(r.patient_summary_tr)+'</p></details>');
  }

  // Aksiyonlar
  html.push(`<div class="actions">
    <button class="btn-ghost" onclick="copyMarkdown()">Markdown Kopyala</button>
    <button class="btn-ghost" onclick="downloadMd()">Markdown Indir</button>
    <button class="btn-ghost" onclick="sendToAlex()">Alex'e Gonder</button>
    <button class="btn-ghost" onclick="document.getElementById('mdBox').classList.toggle('hidden')">Markdown Goster</button>
  </div>`);
  html.push('<pre class="md-export hidden" id="mdBox">' + escapeHtml(r.markdown || '') + '</pre>');

  if (r.confidence === 'low' || (r.errors||[]).length) {
    html.push('<div class="warn" style="margin-top:12px;">Guven dusuk veya LLM hatasi var. Sonuclari ekstra dikkatle gozden gecirin. ' + (r.errors||[]).map(escapeHtml).join(' | ') + '</div>');
  }

  document.getElementById('resultArea').innerHTML = html.join('\n');
  document.getElementById('mdBox').classList.add('hidden');
  window._lastResult = r;
}

function copyMarkdown() {
  const md = (window._lastResult && window._lastResult.markdown) || '';
  if (md) navigator.clipboard.writeText(md);
}
function downloadMd() {
  const md = (window._lastResult && window._lastResult.markdown) || '';
  if (!md) return;
  const blob = new Blob([md], {type: 'text/markdown;charset=utf-8'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'konsult_' + Date.now() + '.md';
  a.click();
}
function sendToAlex() {
  const r = window._lastResult; if (!r) return;
  const inp = document.getElementById('ykVoiceQuickText');
  if (inp) {
    inp.value = 'Bu konsultasyon raporu hakkinda yorumun nedir?\\n\\n' + (r.most_likely || '') + '\\n\\n' + (r.markdown || '').slice(0, 2000);
    inp.focus();
  } else {
    alert('Alex bar bu sayfada bulunamadi.');
  }
}

document.getElementById('runFullBtn').addEventListener('click', runFull);
document.getElementById('runExtractBtn').addEventListener('click', runExtract);

const style = document.createElement('style');
style.textContent = '.hidden { display: none !important; }';
document.head.appendChild(style);

checkHealth();
</script>
</body></html>
"""


# === D700 2026-05-17: Konsultasyon -> hasta dosyasina ekle + USG taslak sayfasi ===

@agents_bp.route("/api/agents/konsult/save-to-visit", methods=["POST"])
def konsult_save_to_visit():
    auth = _require_session()
    if auth:
        return auth
    p = _payload()
    patient_key = _resolve_active_patient_key(p.get("patient_key"))
    markdown = str(p.get("markdown") or "").strip()
    most_likely = str(p.get("most_likely") or "")
    if not patient_key or not markdown:
        return jsonify({"ok": False, "error": "patient_key ve markdown gerekli"}), 400
    try:
        import sqlite3
        db_path = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")
        con = _pgconn(sqlite_path=db_path)
        try:
            from datetime import datetime as _dt
            now = _dt.now().strftime("%Y-%m-%d %H:%M:%S")
            cols = [r[1] for r in con.execute("PRAGMA table_info(visits)").fetchall()]
            insert_cols = ["patient_folder_key", "visit_date", "notes", "created_at"]
            insert_vals = [patient_key, now,
                           f"YZ Konsultasyon: {most_likely}\n\n{markdown}", now]
            if "visit_type" in cols:
                insert_cols.append("visit_type"); insert_vals.append("konsult")
            if "examination" in cols:
                insert_cols.append("examination")
                insert_vals.append(f"YZ Konsultasyon: {most_likely}")
            if "source" in cols:
                insert_cols.append("source"); insert_vals.append("konsult:agent")
            ph = ",".join("?" * len(insert_vals))
            cur = con.execute(
                f"INSERT INTO visits ({','.join(insert_cols)}) VALUES ({ph})",
                insert_vals)
            con.commit()
            visit_id = cur.lastrowid
        finally:
            con.close()
        _safe_audit("agents:konsult_save", {"patient_key": patient_key, "visit_id": visit_id})
        return jsonify({"ok": True, "agent": "konsult",
                         "result": {"visit_id": visit_id, "patient_key": patient_key}})
    except Exception as e:
        return jsonify({"ok": False, "agent": "konsult", "error": str(e)}), 500


@agents_bp.route("/hasta/<path:patient_key>/usg-rapor-taslak", methods=["GET"])
def usg_rapor_taslak_page(patient_key):
    auth = _require_session()
    if auth:
        return auth
    resolved_key = _resolve_active_patient_key(patient_key)
    if not resolved_key:
        patients = []
        try:
            import sqlite3
            db_path = (os.environ.get("YAZKLINIK_DB_PATH")
                       or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")
            con = _pgconn(sqlite_path=db_path)
            con.row_factory = sqlite3.Row
            try:
                patients = [dict(r) for r in con.execute("""
                    SELECT p.folder_key AS patient_key,
                           COALESCE(NULLIF(p.display_name, ''), p.folder_key) AS display_name,
                           COALESCE(pp.protocol_no, '') AS protocol_no
                    FROM patients p
                    LEFT JOIN patient_protocols pp ON pp.patient_key = p.folder_key
                    WHERE COALESCE(p.archived_at, '') = ''
                    ORDER BY COALESCE(p.updated_at, p.created_at, p.folder_key) DESC
                    LIMIT 80
                """).fetchall()]
            finally:
                con.close()
        except Exception:
            patients = []
        return render_template_string(r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>USG Rapor Taslagi - Hasta Sec</title>
<style>
  body{font-family:-apple-system,"Segoe UI",system-ui,sans-serif;background:#eef6fb;color:#13243a;margin:0;padding:24px}
  .wrap{max-width:980px;margin:0 auto}
  .hero{background:#fff;border:1px solid #c8dceb;border-radius:14px;padding:18px;box-shadow:0 14px 34px rgba(19,36,58,.08)}
  .search{width:100%;padding:13px 14px;border:1px solid #b7cfdf;border-radius:10px;margin:14px 0;font-size:16px}
  .grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:10px}
  .card{background:#fff;border:1px solid #c8dceb;border-radius:12px;padding:13px;text-decoration:none;color:#13243a;font-weight:800}
  .card small{display:block;color:#66788a;font-weight:700;margin-top:5px}
</style></head><body><main class="wrap">
  <section class="hero">
    <h1>USG Rapor Taslagi icin hasta sec</h1>
    <p>Bu ajan artik hasta menusune bos dusmez. Once hastayi sec, sonra taslak ekrani acilir.</p>
    <input class="search" id="q" placeholder="Hasta adi, protokol veya dosya anahtari ara">
  </section>
  <section class="grid" id="list">
    {% for p in patients %}
      <a class="card" href="/hasta/{{ p.patient_key|urlencode }}/usg-rapor-taslak"
         data-search="{{ (p.display_name ~ ' ' ~ p.protocol_no ~ ' ' ~ p.patient_key)|lower }}">
        {{ p.display_name }}
        <small>{{ p.protocol_no or p.patient_key }}</small>
      </a>
    {% else %}
      <div class="card">Hasta listesi okunamadi.</div>
    {% endfor %}
  </section>
<script>
document.getElementById('q').addEventListener('input', function(){
  var n=this.value.toLocaleLowerCase('tr-TR');
  document.querySelectorAll('#list .card').forEach(function(a){
    a.style.display = !n || (a.dataset.search||'').toLocaleLowerCase('tr-TR').indexOf(n)>=0 ? '' : 'none';
  });
});
</script></main></body></html>""", patients=patients)
    if str(patient_key or "").strip() != resolved_key:
        q_patient = quote(str(resolved_key), safe="")
        return redirect(f"/hasta/{q_patient}/usg-rapor-taslak")
    return render_template_string(_USG_RAPOR_TASLAK_PAGE, patient_key=resolved_key)


_USG_RAPOR_TASLAK_PAGE = r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>USG Rapor Taslagi</title>
<style>
  :root { --med-blue:#1769aa; --med-teal:#0c7488; --ink:#122236;
          --muted:#5e7185; --line:rgba(94,113,133,0.18); --bg:#f5f8fb; }
  body { font-family:-apple-system,"Segoe UI",system-ui,sans-serif;
         background:var(--bg); color:var(--ink); margin:0; padding:18px; }
  h1 { margin:0 0 4px; font-size:22px; }
  .lead { color:var(--muted); font-size:12px; margin:0 0 14px; }
  .layout { display:grid; grid-template-columns:1fr 1.4fr; gap:14px; }
  @media (max-width:1000px) { .layout { grid-template-columns:1fr; } }
  .panel { background:#fff; border:1px solid var(--line); border-radius:12px; padding:14px; }
  .panel h3 { margin:0 0 10px; font-size:13px; color:var(--med-blue);
              text-transform:uppercase; letter-spacing:0.6px; }
  label { display:block; font-size:12px; color:var(--muted); margin:8px 0 3px; }
  input,select { width:100%; padding:7px 10px; border:1px solid var(--line);
                 border-radius:8px; background:#fafbfd; color:var(--ink);
                 font-size:13px; box-sizing:border-box; }
  .grid2 { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
  button { padding:8px 16px; border:0; border-radius:8px; cursor:pointer;
           font-size:13px; font-weight:600; }
  .btn-primary { background:linear-gradient(135deg,var(--med-blue),var(--med-teal)); color:#fff; }
  .btn-ghost { background:transparent; border:1px solid var(--line); color:var(--ink); }
  .status { font-size:12px; color:var(--muted); margin-top:6px; }
  pre.preview { background:#0d1117; color:#c9d1d9; padding:12px; border-radius:8px;
                font-size:12px; max-height:520px; overflow:auto; white-space:pre-wrap; }
</style></head>
<body>
  <h1>USG Rapor Taslagi</h1>
  <p class="lead">Hasta: <b>{{ patient_key }}</b> - Olcumleri gir, sag tarafta canli Hadlock EFW + sablon olusur. Begenirsen "Hasta Dosyasina Ekle" tikla.</p>
  <div class="layout">
    <div class="panel">
      <h3>1. Olcumler</h3>
      <label>Muayene tarihi<input type="date" id="examDate"></label>
      <label>SAT (LMP, opsiyonel)<input type="date" id="lmp"></label>
      <label>Rapor tipi
        <select id="reportType">
          <option value="second_trimester">2. trimester</option>
          <option value="first_trimester">1. trimester</option>
          <option value="third_trimester">3. trimester</option>
          <option value="morphology">Morfolojik tarama</option>
          <option value="free">Serbest</option>
        </select>
      </label>
      <h3 style="margin-top:14px;">Biyometri (mm)</h3>
      <div class="grid2">
        <label>BPD<input type="number" id="bpd" step="0.1"></label>
        <label>HC<input type="number" id="hc" step="0.1"></label>
        <label>AC<input type="number" id="ac" step="0.1"></label>
        <label>FL<input type="number" id="fl" step="0.1"></label>
      </div>
      <button class="btn-primary" id="goBtn" style="margin-top:12px;">Taslak Olustur</button>
      <button class="btn-ghost" id="saveBtn" style="margin-top:8px;" disabled>Hasta Dosyasina Ekle</button>
      <div class="status" id="status"></div>
    </div>
    <div class="panel">
      <h3>2. Onizleme</h3>
      <pre class="preview" id="preview">Sol panelden olcumleri girip "Taslak Olustur" tikla.</pre>
    </div>
  </div>
<script>
const PATIENT = {{ patient_key|tojson }};
document.getElementById('examDate').valueAsDate = new Date();
let lastDraft = null;
document.getElementById('goBtn').addEventListener('click', async () => {
  const body = {
    patient_id: PATIENT, patient_name: PATIENT,
    exam_date: document.getElementById('examDate').value,
    lmp: document.getElementById('lmp').value || null,
    report_type: document.getElementById('reportType').value,
    measurements: ['bpd','hc','ac','fl'].map(k => ({
      name: k.toUpperCase(),
      value_mm: parseFloat(document.getElementById(k).value) || 0
    })).filter(m => m.value_mm > 0)
  };
  document.getElementById('preview').textContent = 'isleniyor...';
  try {
    const r = await fetch('/api/agents/usg_rapor/run', {
      method:'POST', headers:{'Content-Type':'application/json'},
      credentials:'same-origin', body: JSON.stringify(body)});
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || r.status);
    lastDraft = d.result;
    document.getElementById('preview').textContent = d.result.raw_body || '(bos)';
    document.getElementById('saveBtn').disabled = false;
    document.getElementById('status').textContent =
      'OK - EFW: ' + (d.result.efw_grams || '-') + ' g, ' + d.result.ga_text;
  } catch(e) { document.getElementById('preview').textContent = 'Hata: ' + e.message; }
});
document.getElementById('saveBtn').addEventListener('click', async () => {
  if (!lastDraft) return;
  if (!confirm('USG taslagi hasta dosyasina visit olarak eklensin mi?')) return;
  try {
    const r = await fetch('/api/agents/konsult/save-to-visit', {
      method:'POST', headers:{'Content-Type':'application/json'},
      credentials:'same-origin',
      body: JSON.stringify({patient_key: PATIENT, markdown: lastDraft.raw_body,
                             most_likely: 'USG ' + (lastDraft.ga_text || '')})});
    const d = await r.json();
    if (!d.ok) throw new Error(d.error || r.status);
    document.getElementById('status').textContent = 'Hasta dosyasina eklendi (visit_id ' + d.result.visit_id + ')';
    document.getElementById('saveBtn').disabled = true;
  } catch(e) { document.getElementById('status').textContent = 'Hata: ' + e.message; }
});
</script>
</body></html>
"""


# === D700 2026-05-17: VeriDB endpointleri (Postgres + Redis + MeiliSearch) ===

postgres_mod = _safe_import("yazklinik_postgres_agent")
redis_mod = _safe_import("yazklinik_redis_agent")
meili_mod = _safe_import("yazklinik_meilisearch_agent")
_PG_HEALTH_CACHE: Dict[str, Any] = {"ts": 0.0, "payload": None}


def _pg_health_cache_ttl() -> int:
    try:
        return max(
            10,
            min(
                int(
                    os.environ.get(
                        "YAZKLINIK_PG_HEALTH_CACHE_TTL_SEC",
                        "600")),
                900))
    except Exception:
        return 600


def _pg_health_cache_path() -> Path:
    return (
        Path(__file__).resolve().parent
        / "runtime_state"
        / "postgres_health"
        / "last_report.json"
    )


def _pg_health_cache_read(force: bool = False) -> Optional[Dict[str, Any]]:
    if force:
        return None
    now = time.time()
    ttl = _pg_health_cache_ttl()
    cached = _PG_HEALTH_CACHE.get("payload")
    try:
        age = now - float(_PG_HEALTH_CACHE.get("ts") or 0.0)
    except Exception:
        age = ttl + 1
    if isinstance(cached, dict) and age <= ttl:
        return copy.deepcopy(cached)
    try:
        path = _pg_health_cache_path()
        if path.is_file() and now - float(path.stat().st_mtime) <= ttl:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict):
                _PG_HEALTH_CACHE["ts"] = now
                _PG_HEALTH_CACHE["payload"] = copy.deepcopy(payload)
                return payload
    except Exception:
        pass
    return None


def _pg_health_cache_write(payload: Dict[str, Any]) -> None:
    if not isinstance(payload, dict):
        return
    now = time.time()
    _PG_HEALTH_CACHE["ts"] = now
    _PG_HEALTH_CACHE["payload"] = copy.deepcopy(payload)
    try:
        path = _pg_health_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2),
            encoding="utf-8")
    except Exception:
        pass


@agents_bp.route("/api/db/postgres/health", methods=["GET"])
def api_pg_health():
    auth = _require_session()
    if auth: return auth
    force = str(request.args.get("force") or "").strip() == "1"
    if not _postgres_feature_enabled():
        return jsonify({
            "ok": True,
            "agent": "postgres",
            "result": {
                "ok": True,
                "enabled": False,
                "skipped": True,
                "message": "PostgreSQL kapali; sistem SQLite modunda calisiyor.",
            },
        })
    err = _agent_or_503(postgres_mod, "postgres")
    if err: return err
    cached = _pg_health_cache_read(force=force)
    if isinstance(cached, dict):
        return jsonify(cached)
    result = postgres_mod.health_check()
    if isinstance(result, dict) and "dsn" in result:
        result["dsn"] = _mask_pg_dsn_value(str(result.get("dsn") or ""))
    payload = {"ok": True, "agent": "postgres", "result": result}
    _pg_health_cache_write(payload)
    return jsonify(payload)


@agents_bp.route("/api/db/postgres/migrate", methods=["POST"])
def api_pg_migrate():
    """Sadece doktor. Default dry_run=True."""
    auth = _require_session()
    if auth: return auth
    if session.get("role") != "doktor":
        return jsonify({"ok": False, "error": "Sadece doktor"}), 403
    err = _agent_or_503(postgres_mod, "postgres")
    if err: return err
    p = _payload()
    dry_run = bool(p.get("dry_run", True))
    tables = p.get("tables") or ["patients", "visits"]
    try:
        return jsonify({"ok": True, "agent": "postgres",
                         "result": postgres_mod.migrate_from_sqlite(
                             tables=tables, dry_run=dry_run)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@agents_bp.route("/api/cache/health", methods=["GET"])
def api_cache_health():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(redis_mod, "redis")
    if err: return err
    return jsonify({"ok": True, "agent": "redis",
                     "result": redis_mod.health_check()})


@agents_bp.route("/api/cache/get", methods=["POST"])
def api_cache_get():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(redis_mod, "redis")
    if err: return err
    p = _payload()
    k = str(p.get("key") or "")
    if not k:
        return jsonify({"ok": False, "error": "key gerekli"}), 400
    return jsonify({"ok": True, "result": redis_mod.cache_get(k)})


@agents_bp.route("/api/queue/stats", methods=["GET"])
def api_queue_stats():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(redis_mod, "redis")
    if err: return err
    queues = ["voice_confirm", "geri_cagirma", "telesekreter_triyaj",
              "instagram_drafts"]
    stats = {}
    for q in queues:
        stats[q] = {"length": redis_mod.queue_length(q),
                    "preview": redis_mod.queue_peek(q, limit=3)}
    return jsonify({"ok": True, "result": stats})


@agents_bp.route("/api/search/full-text", methods=["POST"])
def api_search_full_text():
    """MeiliSearch - typo tolerant, anlik. ChromaDB semantic disinda KEYWORD."""
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(meili_mod, "meilisearch")
    if err: return err
    p = _payload()
    q = str(p.get("query") or "").strip()
    index_uid = str(p.get("index") or "yk_patients")
    limit = int(p.get("limit") or 20)
    filters = p.get("filters")
    if not q:
        return jsonify({"ok": False, "error": "query gerekli"}), 400
    return jsonify({"ok": True, "agent": "meilisearch",
                     "result": meili_mod.search(q, index_uid=index_uid,
                                                  limit=limit, filters=filters)})


@agents_bp.route("/api/search/health", methods=["GET"])
def api_search_health():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(meili_mod, "meilisearch")
    if err: return err
    return jsonify({"ok": True, "agent": "meilisearch",
                     "result": meili_mod.health_check()})


@agents_bp.route("/api/search/sync", methods=["POST"])
def api_search_sync():
    """SQLite -> MeiliSearch sync. Doktor only."""
    auth = _require_session()
    if auth: return auth
    if session.get("role") != "doktor":
        return jsonify({"ok": False, "error": "Sadece doktor"}), 403
    err = _agent_or_503(meili_mod, "meilisearch")
    if err: return err
    p = _payload()
    dry_run = bool(p.get("dry_run", False))
    try:
        return jsonify({"ok": True, "agent": "meilisearch",
                         "result": meili_mod.sync_all_from_sqlite(dry_run=dry_run)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@agents_bp.route("/veridb-merkezi", methods=["GET"])
def veridb_merkezi_page():
    """VeriDB Dashboard: Postgres + Redis + MeiliSearch tek panelden gor."""
    auth = _require_session()
    if auth: return auth
    return render_template_string(_VERIDB_PAGE)


_VERIDB_PAGE = r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>VeriDB Merkezi - YazKlinik</title>
<style>
  :root { --med-blue:#1769aa; --med-teal:#0c7488; --med-green:#16815f;
          --med-red:#b3261e; --ink:#122236; --muted:#5e7185;
          --line:rgba(94,113,133,0.18); --bg:#f5f8fb; }
  body { font-family:-apple-system,"Segoe UI",sans-serif; background:var(--bg);
         color:var(--ink); margin:0; padding:18px; }
  h1 { margin:0 0 10px; font-size:22px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); gap:14px; }
  .card { background:#fff; border:1px solid var(--line); border-radius:12px; padding:14px; }
  .card h3 { margin:0 0 8px; font-size:14px; color:var(--med-blue);
              display:flex; align-items:center; justify-content:space-between; }
  .badge { padding:2px 8px; border-radius:999px; font-size:11px; font-weight:600; }
  .b-ok { background:#e2f3eb; color:var(--med-green); }
  .b-fail { background:#fbe6e4; color:var(--med-red); }
  pre { background:#0d1117; color:#c9d1d9; padding:10px; border-radius:8px;
        font-size:11px; max-height:200px; overflow:auto; }
  .search-box { display:flex; gap:6px; margin:8px 0; }
  .search-box input, .search-box select { flex:1; padding:6px 10px;
        border:1px solid var(--line); border-radius:6px; }
  .search-box button { padding:6px 12px; background:var(--med-blue);
        color:#fff; border:0; border-radius:6px; cursor:pointer; }
  .hit { padding:8px; border:1px solid var(--line); border-radius:8px;
         margin-top:6px; font-size:12px; }
  .hit em { background:yellow; font-style:normal; }
</style></head>
<body>
  <h1>VeriDB Merkezi</h1>
  <p style="color:var(--muted);font-size:12px;">PostgreSQL (buyuk olcek) + Redis (cache+queue) + MeiliSearch (anlik arama)</p>

  <div class="grid">
    <div class="card">
      <h3>PostgreSQL <span id="pgStatus" class="badge">...</span></h3>
      <pre id="pgInfo">yukleniyor</pre>
    </div>
    <div class="card">
      <h3>Redis <span id="rdStatus" class="badge">...</span></h3>
      <pre id="rdInfo">yukleniyor</pre>
    </div>
    <div class="card">
      <h3>MeiliSearch <span id="msStatus" class="badge">...</span></h3>
      <pre id="msInfo">yukleniyor</pre>
    </div>
    <div class="card">
      <h3>Queue Sayilari</h3>
      <pre id="qStats">yukleniyor</pre>
    </div>
  </div>

  <div class="card" style="margin-top:14px;">
    <h3>Anlik Tam Metin Arama (MeiliSearch)</h3>
    <div class="search-box">
      <input id="searchQuery" placeholder="orn: Kilic Seval, preeklampsi, 2026-04">
      <select id="searchIndex">
        <option value="yk_patients">Hastalar</option>
        <option value="yk_visits">Gelisler</option>
        <option value="yk_rx">Receteler</option>
      </select>
      <button onclick="doSearch()">Ara</button>
    </div>
    <div id="searchResults"></div>
  </div>

<script>
function esc(s) { return String(s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[c]); }
function statusBadge(elId, ok) {
  const el = document.getElementById(elId);
  el.textContent = ok ? 'OK' : 'FAIL';
  el.className = 'badge ' + (ok ? 'b-ok' : 'b-fail');
}

async function load() {
  for (const [url, statusEl, infoEl] of [
    ['/api/db/postgres/health', 'pgStatus', 'pgInfo'],
    ['/api/cache/health', 'rdStatus', 'rdInfo'],
    ['/api/search/health', 'msStatus', 'msInfo'],
  ]) {
    try {
      const r = await fetch(url, {credentials:'same-origin'});
      const d = await r.json();
      const res = d.result || d;
      statusBadge(statusEl, res.ok);
      document.getElementById(infoEl).textContent = JSON.stringify(res, null, 2);
    } catch(e) {
      statusBadge(statusEl, false);
      document.getElementById(infoEl).textContent = e.message;
    }
  }
  try {
    const r = await fetch('/api/queue/stats', {credentials:'same-origin'});
    const d = await r.json();
    document.getElementById('qStats').textContent = JSON.stringify(d.result, null, 2);
  } catch(e) {
    document.getElementById('qStats').textContent = e.message;
  }
}

async function doSearch() {
  const q = document.getElementById('searchQuery').value.trim();
  const idx = document.getElementById('searchIndex').value;
  if (!q) return;
  const box = document.getElementById('searchResults');
  box.innerHTML = '<i>aranÃ„Â±yor...</i>';
  try {
    const r = await fetch('/api/search/full-text', {
      method:'POST', headers:{'Content-Type':'application/json'},
      credentials:'same-origin',
      body: JSON.stringify({query: q, index: idx, limit: 15})});
    const d = await r.json();
    const res = d.result || {};
    box.innerHTML = '<b>'+res.total+' sonuc</b> ('+res.processing_time_ms+' ms)';
    for (const h of (res.hits || [])) {
      const f = h._formatted || h;
      box.innerHTML += '<div class="hit"><b>' +
        (f.display_name || f.patient_folder_key || f.id || '?') +
        '</b><br><small>' +
        Object.entries(f).filter(([k,v])=>k!=='_formatted'&&v).map(([k,v])=>k+': '+v).join(' | ').substring(0,300) +
        '</small></div>';
    }
  } catch(e) {
    box.innerHTML = '<span style="color:red">'+esc(e.message)+'</span>';
  }
}

load();
document.getElementById('searchQuery').addEventListener('keydown', e => { if (e.key==='Enter') doSearch(); });
</script>
</body></html>
"""


# ============================================================================
# Session 7: 29 yeni ajan endpointleri (Mayis 2026)
# ============================================================================

# --- Vision USG (llama3.2-vision) ---
@agents_bp.route("/api/agents/vision-usg/analyze", methods=["POST"])
def api_vision_usg_analyze():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(vision_mod, "vision_usg")
    if err: return err
    p = _payload()
    image_path = p.get("image_path") or ""
    if not image_path or _as_bool(p.get("demo")):
        return _agent_preview("vision_usg",
                              "USG Vision hazir. Gercek analiz icin USG/PDF gorseli secin.",
                              {
                                  "mode": "image_required",
                                  "next_screen": "/hastalar",
                                  "required_input": "image_path",
                                  "doctor_review_required": True,
                                  "sample_steps": [
                                      "USG gorselini hasta dosyasindan sec",
                                      "Vision analizi olcum ve kalite bulgularini cikarir",
                                      "Rapor taslagi hekim onayina duser",
                                  ],
                              })
    return _wrap_call("vision_usg", vision_mod.analyze_image,
                       {"image_path": image_path})


# --- SOAP genisletici ---
@agents_bp.route("/api/agents/soap/expand", methods=["POST"])
def api_soap_expand():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(soap_mod, "soap")
    if err: return err
    p = _payload()
    note = (p.get("note") or p.get("text") or "").strip()
    if not note:
        return jsonify({"ok": False, "error": "note gerekli"}), 400
    return _wrap_call("soap", soap_mod.expand_to_soap,
                       {"short_note": note, "prefer": p.get("prefer", "ollama")})


# --- ICD-10 oner ---
@agents_bp.route("/api/agents/icd10/suggest", methods=["POST"])
def api_icd10_suggest():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(icd10_mod, "icd10")
    if err: return err
    p = _payload()
    note = (p.get("note") or p.get("text") or "").strip()
    return _wrap_call("icd10", icd10_mod.suggest_codes,
                       {"note": note, "top_k": int(p.get("top_k", 5)),
                        "prefer": p.get("prefer", "ollama")})


# --- Gebelik takvimi ---
@agents_bp.route("/api/agents/gebelik/plan", methods=["POST"])
def api_gebelik_plan():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(gebelik_mod, "gebelik_takvim")
    if err: return err
    p = _payload()
    lmp = p.get("lmp") or ""
    if not lmp:
        return jsonify({"ok": False, "error": "lmp (YYYY-MM-DD) gerekli"}), 400
    return _wrap_call("gebelik_takvim", gebelik_mod.compute_plan,
                       {"lmp_iso": lmp})


# --- Risk skorlari (preeklampsi/HELLP/Bishop) ---
@agents_bp.route("/api/agents/risk/preeklampsi", methods=["POST"])
def api_risk_preeklampsi():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(risk_mod, "risk_skor")
    if err: return err
    return _wrap_call("risk_preeklampsi", risk_mod.preeklampsi_risk, _payload())


@agents_bp.route("/api/agents/risk/hellp", methods=["POST"])
def api_risk_hellp():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(risk_mod, "risk_skor")
    if err: return err
    return _wrap_call("risk_hellp", risk_mod.hellp_risk, _payload())


@agents_bp.route("/api/agents/risk/bishop", methods=["POST"])
def api_risk_bishop():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(risk_mod, "risk_skor")
    if err: return err
    return _wrap_call("risk_bishop", risk_mod.bishop_score, _payload())


@agents_bp.route("/api/agents/risk/vte", methods=["POST"])
def api_risk_vte():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(risk_mod, "risk_skor")
    if err: return err
    return _wrap_call("risk_vte", risk_mod.vte_padua_score, _payload())


# --- DDI Drug interaction ---
@agents_bp.route("/api/agents/ddi/check", methods=["POST"])
def api_ddi_check():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(ddi_mod, "ddi")
    if err: return err
    p = _payload()
    drugs = p.get("drugs") or []
    if isinstance(drugs, str):
        drugs = [d.strip() for d in drugs.split(",") if d.strip()]
    return _wrap_call("ddi", ddi_mod.check_interactions, {
        "drugs": drugs,
        "is_pregnant": bool(p.get("is_pregnant", False)),
        "trimester": p.get("trimester")})


# --- Voice command ---
@agents_bp.route("/api/agents/voice-command/parse", methods=["POST"])
def api_voice_command_parse():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(voice_cmd_mod, "voice_command")
    if err: return err
    p = _payload()
    text = p.get("text") or p.get("spoken_text") or ""
    return _wrap_call("voice_command", voice_cmd_mod.parse, {"spoken_text": text})


# --- Anti-burnout dashboard ---
@agents_bp.route("/api/agents/burnout/report", methods=["GET", "POST"])
def api_burnout_report():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(burnout_mod, "anti_burnout")
    if err: return err
    return _wrap_call("anti_burnout", burnout_mod.compute_report, {})


# --- Hatira USG WhatsApp ---
@agents_bp.route("/api/agents/hatira-usg/prepare", methods=["POST"])
def api_hatira_prepare():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(hatira_mod, "hatira_usg")
    if err: return err
    p = _payload()
    return _wrap_call("hatira_prepare", hatira_mod.prepare, {
        "patient_id": p.get("patient_id", ""),
        "patient_name": p.get("patient_name", ""),
        "patient_phone": p.get("patient_phone", ""),
        "usg_pdf_or_image": p.get("usg_pdf_or_image", ""),
        "ga_text": p.get("ga_text", ""),
        "template_index": int(p.get("template_index", 0)),
        "consent_acknowledged": bool(p.get("consent_acknowledged", False))})


@agents_bp.route("/api/agents/hatira-usg/send", methods=["POST"])
def api_hatira_send():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(hatira_mod, "hatira_usg")
    if err: return err
    p = _payload()
    if not p.get("consent_acknowledged"):
        return jsonify({"ok": False, "error": "consent zorunlu"}), 400
    # Onceden prepare() ile uretilen job dict'i kabul et
    try:
        from yazklinik_hatira_usg_agent import HatiraJob
        job = HatiraJob(**{k: v for k, v in p.items()
                            if k in HatiraJob.__dataclass_fields__})
        out = hatira_mod.send(job)
        return jsonify({"ok": True, "result": asdict(out)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


# --- Orchestrator (chain) ---
@agents_bp.route("/api/agents/orchestrator/full-visit", methods=["POST"])
def api_orch_full_visit():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(orchestrator_mod, "orchestrator")
    if err: return err
    p = _payload()
    case = p.get("case_text") or ""
    if not case:
        return jsonify({"ok": False, "error": "case_text gerekli"}), 400
    if _as_bool(p.get("quick")) or str(p.get("prefer") or "").lower() == "skip":
        steps: List[Dict[str, Any]] = []
        if icd10_mod is not None:
            steps.append(_quick_step("icd10", icd10_mod.suggest_codes,
                                     {"note": case, "top_k": 5, "prefer": "skip"}))
        if soap_mod is not None:
            steps.append(_quick_step("soap", soap_mod.expand_to_soap,
                                     {"short_note": case, "prefer": "skip"}))
        if ddi_mod is not None:
            drugs = p.get("drugs") or []
            if isinstance(drugs, str):
                drugs = [d.strip() for d in drugs.split(",") if d.strip()]
            steps.append(_quick_step("ddi", ddi_mod.check_interactions,
                                     {"drugs": drugs, "is_pregnant": _as_bool(p.get("is_pregnant")),
                                      "trimester": p.get("trimester")}))
        return _agent_preview("orchestrator_full_visit",
                              "Tam muayene zinciri hizli modda hazir; agir LLM konsultasyon icin ekrandan calistirin.",
                              {
                                  "flow_name": "full_visit_quick",
                                  "case_text": case,
                                  "overall_ok": all(bool(s.get("ok")) for s in steps) if steps else True,
                                  "summary": f"{len([s for s in steps if s.get('ok')])}/{len(steps)} hizli adim OK",
                                  "steps": steps,
                                  "real_flow": "full_visit",
                              })
    return _wrap_call("orchestrator_full_visit", orchestrator_mod.full_visit,
                       {"case_text": case, "prefer": p.get("prefer", "ollama")})


@agents_bp.route("/api/agents/orchestrator/pubmed-pack", methods=["POST"])
def api_orch_pubmed_pack():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(orchestrator_mod, "orchestrator")
    if err: return err
    p = _payload()
    q = p.get("query") or ""
    if not q:
        return jsonify({"ok": False, "error": "query gerekli"}), 400
    if _as_bool(p.get("quick")) or _as_bool(p.get("demo")):
        return _agent_preview("orchestrator_pubmed_pack",
                              "PubMed paketi hazir. Uzun tarama arka plan PubMed ekranindan baslatilir.",
                              {
                                  "flow_name": "pubmed_pack_quick",
                                  "query": q,
                                  "max_articles": int(p.get("max_articles", 1)),
                                  "next_screen": "/pubmed-tarama",
                                  "sample_steps": [
                                      "PubMed arama",
                                      "Makale secimi",
                                      "Turkce ozet ve RAG indeks",
                                  ],
                              })
    return _wrap_call("orchestrator_pubmed_pack", orchestrator_mod.pubmed_research_pack,
                       {"query": q, "max_articles": int(p.get("max_articles", 3))})


@agents_bp.route("/api/agents/orchestrator/usg-pipeline", methods=["POST"])
def api_orch_usg_pipeline():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(orchestrator_mod, "orchestrator")
    if err: return err
    p = _payload()
    image = p.get("image_path") or ""
    if not image or _as_bool(p.get("demo")):
        return _agent_preview("orchestrator_usg_pipeline",
                              "USG pipeline hazir. Hasta dosyasindan USG gorseli/PDF secilince zincir calisir.",
                              {
                                  "flow_name": "usg_pipeline_ready",
                                  "patient_key": p.get("patient_key", ""),
                                  "required_input": "image_path",
                                  "next_screen": "/hastalar",
                                  "sample_steps": [
                                      "Vision USG analiz",
                                      "Biyometri olcumlerini ayikla",
                                      "USG rapor taslagi uret",
                                      "Hekim onayindan sonra hasta dosyasina isle",
                                  ],
                              })
    return _wrap_call("orchestrator_usg_pipeline", orchestrator_mod.usg_full_pipeline,
                       {"image_path": image, "patient_key": p.get("patient_key", ""),
                        "lmp": p.get("lmp")})


# --- Hasta Portal ---
def _tr_fold(s: str) -> str:
    """Turkce harfleri ASCII'ye + lowercase. Arama icin diacritic-insensitive."""
    if not s:
        return ""
    s = str(s).lower()
    # Turkce harf -> ASCII (Turk'e ozel I/i kuralina dikkat)
    table = str.maketrans({'\xe7': 'c', '\u011f': 'g', '\u0131': 'i', '\xf6': 'o', '\u015f': 's', '\xfc': 'u', '\xc7': 'C', '\u011e': 'G', '\u0130': 'I', '\xd6': 'O', '\u015e': 'S', '\xdc': 'U', '\xe2': 'a', '\xc2': 'a', '\xee': 'i', '\xce': 'i', '\xfb': 'u', '\xdb': 'u'})
    return s.translate(table)


@agents_bp.route("/sw-kill", methods=["GET"])
def sw_kill_switch():
    """Eski Service Worker'i tamamen oldur + cache temizle + ana sayfaya yonlendir.

    KULLANIM: Kullanici browser'inda eski SW takildi ise bu URL'i ac.
    JS unregister + cache clear + 2sn sonra /hasta-portal'a redirect.
    """
    return """<!doctype html><html><head><meta charset='utf-8'>
<title>Service Worker temizleniyor...</title>
<style>body{font-family:sans-serif;text-align:center;padding:60px;background:#0d4f8b;color:#fff}
.spin{display:inline-block;width:40px;height:40px;border:4px solid #fff;border-top-color:#ffd166;
border-radius:50%;animation:s 1s linear infinite}
@keyframes s{to{transform:rotate(360deg)}}</style></head><body>
<div class='spin'></div>
<h2>Eski cache temizleniyor...</h2>
<p id='msg'>Lutfen bekleyin</p>
<script>
(async function(){
  const msg = document.getElementById('msg');
  try {
    if('serviceWorker' in navigator){
      const regs = await navigator.serviceWorker.getRegistrations();
      msg.textContent = regs.length + ' eski SW siliniyor...';
      for(const r of regs) await r.unregister();
    }
    if('caches' in window){
      const ks = await caches.keys();
      msg.textContent = 'Tum cache temizleniyor: ' + ks.length;
      for(const k of ks) await caches.delete(k);
    }
    msg.textContent = 'Ã¢Å“â€œ Temizlik tamam. Yonlendiriliyor...';
    setTimeout(() => location.href = '/hasta-portal?admin=1&fresh=' + Date.now(), 1500);
  } catch(e){
    msg.textContent = 'Hata: ' + e.message + ' - manuel /hasta-portal acin';
  }
})();
</script></body></html>"""


@agents_bp.route("/api/agents/portal/search-patients", methods=["GET"])
def api_portal_search_patients():
    """Hasta arama - diacritic + case insensitive Turkish search.

    Query: ?q=<arama_metni> (en az 2 char)
    Donus: [{key, name, phone, age}, ...] - max 12 sonuc

    Strateji:
      1. Sorgu kelimelerini ASCII-fold (Ebru ErdoÃ„Å¸an -> ebru erdogan)
      2. DB'den genis cevre cek (ilk kelime LIKE)
      3. Python'da her satirin display_name'ini ASCII-fold edip
         TUM kelimeleri AND ile kontrol et
      4. Ranking: ad basinda eslesen once
    """
    auth = _require_session()
    if auth: return auth
    q = (request.args.get("q") or "").strip()
    if len(q) < 2:
        return jsonify({"ok": True, "result": []})

    import sqlite3, os
    dbp = (os.environ.get("YAZKLINIK_DB_PATH")
            or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")
    if not os.path.exists(dbp):
        return jsonify({"ok": False, "error": "db yok"}), 503

    q_fold = _tr_fold(q)
    words = [w for w in q_fold.split() if w]
    if not words:
        return jsonify({"ok": True, "result": []})

    # DB'den genis cevre cek - her kelime icin OR (asagida Python AND filtreler)
    first_word = words[0]
    like_pat = f"%{first_word}%"
    # Geni cek (telefon/tc'ye de bak)
    sql = ("SELECT p.folder_key AS key, p.display_name AS name, "
           "  COALESCE(pd.phone, pt.phone, '') AS phone, "
           "  COALESCE(pd.age, pt.age, 0) AS age, "
           "  COALESCE(pd.tc_no, '') AS tc "
           "FROM patients p "
           "LEFT JOIN patient_demographics pd ON pd.patient_key = p.folder_key "
           "LEFT JOIN patient_type pt ON pt.patient_key = p.folder_key "
           "WHERE (LOWER(p.display_name) LIKE LOWER(?) "
           "    OR LOWER(p.folder_key) LIKE LOWER(?) "
           "    OR pd.phone LIKE ? "
           "    OR pd.tc_no LIKE ?) "
           "  AND p.archived_at IS NULL "
           "LIMIT 200")  # genis - Python filtreyecek
    con = _pgconn(sqlite_path=dbp)
    con.row_factory = sqlite3.Row
    try:
        rows = con.execute(sql, (like_pat, like_pat, like_pat, like_pat)).fetchall()

        # Python-filtre: TUM kelimeler eslesmel (AND), diacritic-insensitive
        matches = []
        for r in rows:
            name_fold = _tr_fold(r["name"] or "")
            key_fold = _tr_fold(r["key"] or "")
            phone = (r["phone"] or "").lower()
            tc = (r["tc"] or "").lower()
            haystack = f"{name_fold} {key_fold} {phone} {tc}"
            if all(w in haystack for w in words):
                # Ranking: ad basinda eslesen +10, ad iceren +5, key/phone +1
                score = 0
                if name_fold.startswith(words[0]):
                    score += 10
                if words[0] in name_fold:
                    score += 5
                if len(words) > 1 and all(w in name_fold for w in words):
                    score += 8
                matches.append((score, dict(r)))

        # Skora gore sirala, top 12
        matches.sort(key=lambda x: -x[0])
        results = [m[1] for m in matches[:12]]
        # tc'yi disari verme (KVKK)
        for r in results:
            r.pop("tc", None)
        return jsonify({"ok": True, "result": results, "query_folded": q_fold,
                         "raw_hit_count": len(rows), "match_count": len(matches)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
    finally:
        con.close()


@agents_bp.route("/api/agents/portal/share-options", methods=["GET"])
def api_portal_share_options():
    """Doktorun SELECTOR formu icin - bir hasta hakkinda paylasilabilir
    tum item'lari listele (visits, pdfs, meds, labs)."""
    auth = _require_session()
    if auth: return auth
    pid = request.args.get("patient_id", "").strip()
    if not pid:
        return jsonify({"ok": False, "error": "patient_id gerek"}), 400
    if not portal_mod:
        return jsonify({"ok": False, "error": "portal_mod yok"}), 503

    out = {"visits": [], "pdfs": [], "meds": [], "labs": []}
    try:
        # Tum ziyaretler (selector icin daha cok)
        try:
            out["visits"] = portal_mod.list_visit_summaries(pid, limit=15)
        except Exception:
            pass
        try:
            out["pdfs"] = portal_mod.list_my_pdfs(pid)
        except Exception:
            pass
        try:
            out["meds"] = portal_mod.list_my_meds(pid)
        except Exception:
            pass
        try:
            out["labs"] = portal_mod.list_my_labs(pid)
        except Exception:
            pass
        return jsonify({"ok": True, "result": out})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@agents_bp.route("/api/agents/portal/issue-link", methods=["POST"])
def api_portal_issue_link():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(portal_mod, "hasta_portal")
    if err: return err
    p = _payload()
    # share_config: doktorun SELECTOR ile sectiklerini iceren JSON
    share_config = p.get("share_config")
    if share_config and not isinstance(share_config, dict):
        try:
            import json as _json
            share_config = _json.loads(share_config)
        except Exception:
            share_config = None
    # base_url: Funnel veya local
    base_url = (p.get("base_url") or _portal_public_base_url())
    return _wrap_call("portal_issue", portal_mod.issue_magic_link, {
        "patient_id": p.get("patient_id", ""),
        "phone": p.get("phone", ""),
        "base_url": base_url,
        "ttl_hours": int(p.get("ttl_hours", 24)),
        "share_config": share_config,
        "tc_last4": str(p.get("tc_last4") or "").strip(),
        "birth_year": int(p.get("birth_year") or 0) or None})


@agents_bp.route("/hasta-portal/uret", methods=["POST"])
def hasta_portal_uret_form():
    """FORM submit ile magic link uret - XHR bypass (Funnel/Werkzeug stuck cozumu).

    Browser native form post -> server response HTML olarak donduÃ„Å¸unde
    browser sayfasini direkt acar, XHR buffer sorunu YOK.
    """
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(portal_mod, "hasta_portal")
    if err: return err

    pid = (request.form.get("patient_id") or "").strip()
    phone = (request.form.get("phone") or "").strip()
    ttl = int(request.form.get("ttl_hours") or 168)
    tc_last4 = (request.form.get("tc_last4") or "").strip()
    birth_year_str = (request.form.get("birth_year") or "").strip()
    birth_year = int(birth_year_str) if birth_year_str.isdigit() else None
    custom_message = (request.form.get("custom_message") or "").strip()
    show_pdfs = request.form.get("opt_pdfs") == "1"
    show_meds = request.form.get("opt_meds") == "1"
    show_labs = request.form.get("opt_labs") == "1"
    # Visit secimi (multi)
    selected_visits = request.form.getlist("visit_keys")
    do_whatsapp = request.form.get("do_whatsapp") == "1"

    if not pid:
        return "Hasta ID gerek", 400

    share_config = {
        "visits": selected_visits if selected_visits else None,
        "show_pdfs": show_pdfs, "show_meds": show_meds, "show_labs": show_labs,
        "custom_message": custom_message,
    }
    base_url = _portal_public_base_url()

    res = portal_mod.issue_magic_link(
        patient_id=pid, phone=phone, base_url=base_url,
        ttl_hours=ttl, share_config=share_config,
        tc_last4=tc_last4, birth_year=birth_year)

    if not res.ok or not res.magic_link:
        return f"Hata: link uretilemedi", 500

    link = res.magic_link
    # WhatsApp URL hazirla
    wa_phone = "".join(c for c in (phone or "") if c.isdigit())
    if wa_phone.startswith("0"):
        wa_phone = "90" + wa_phone[1:]
    elif not wa_phone.startswith("90") and len(wa_phone) == 10:
        wa_phone = "90" + wa_phone
    import urllib.parse as _up
    wa_msg = _up.quote(
        f"Sayin hastamiz,\n\n"
        f"Kendi dosyaniza erisim icin asagidaki linke tikkayabilirsiniz:\n"
        f"{link}\n\n"
        f"Link {ttl} saat gecerlidir.\n\n"
        f"- Op. Dr. Hakan Yaz Klinigi")
    wa_url = f"https://wa.me/{wa_phone}?text={wa_msg}" if wa_phone else ""

    # Direkt yonlendirme - WhatsApp veya geri portal
    if do_whatsapp and wa_url:
        return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Link Uretildi</title>
<meta http-equiv="refresh" content="3;url={wa_url}">
<style>body{{font-family:sans-serif;text-align:center;padding:50px;background:#0a8a76;color:#fff}}
.box{{background:#fff;color:#122236;padding:30px;border-radius:14px;max-width:500px;margin:0 auto;
box-shadow:0 8px 24px rgba(0,0,0,.2)}}h2{{color:#0a8a76}}a.btn{{display:inline-block;background:#25d366;
color:#fff;padding:14px 24px;border-radius:10px;text-decoration:none;font-weight:700;margin:10px}}
.link{{background:#eff5fb;padding:12px;border-radius:6px;font-size:12px;word-break:break-all;margin:14px 0}}</style>
</head><body><div class="box">
<h2>Ã¢Å“â€œ Magic Link Uretildi</h2>
<p>WhatsApp 3 saniyede otomatik acilir...</p>
<div class="link">{link}</div>
<a class="btn" href="{wa_url}">ÄŸÅ¸â€œÂ± WhatsApp Ã…Âimdi AÃƒÂ§</a>
<a class="btn" href="/hasta-portal" style="background:#5e7185">Ã¢â€ Â Portal Geri DÃƒÂ¶n</a>
</div></body></html>"""
    else:
        return f"""<!doctype html><html><head><meta charset="utf-8">
<title>Link Uretildi</title>
<style>body{{font-family:sans-serif;text-align:center;padding:50px;background:#0d4f8b;color:#fff}}
.box{{background:#fff;color:#122236;padding:30px;border-radius:14px;max-width:600px;margin:0 auto;
box-shadow:0 8px 24px rgba(0,0,0,.2)}}h2{{color:#16815f}}a.btn{{display:inline-block;
padding:14px 24px;border-radius:10px;text-decoration:none;font-weight:700;margin:8px}}
.link{{background:#eff5fb;padding:14px;border-radius:8px;font-size:13px;word-break:break-all;margin:16px 0;
border:1px solid #cdd9e3}}</style>
</head><body><div class="box">
<h2>Ã¢Å“â€œ Magic Link Uretildi ({ttl} saat gecerli)</h2>
<div class="link">{link}</div>
<a class="btn" href="{link}" target="_blank" style="background:#1769aa;color:#fff">ÄŸÅ¸â€˜Â Onizle (Yeni Sekme)</a>
<a class="btn" href="{wa_url}" target="_blank" style="background:#25d366;color:#fff">ÄŸÅ¸â€œÂ± WhatsApp AÃƒÂ§</a>
<a class="btn" href="/hasta-portal" style="background:#5e7185;color:#fff">Ã¢â€ Â Portal Geri DÃƒÂ¶n</a>
<p style="font-size:12px;color:#5e7185;margin-top:20px">Linki kopyalayip elle gonderebilirsin de.</p>
</div></body></html>"""


@agents_bp.route("/api/agents/portal/revoke", methods=["POST"])
def api_portal_revoke():
    """Token iptal et - hasta artik linke giremez."""
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(portal_mod, "hasta_portal")
    if err: return err
    p = _payload()
    token = (p.get("token") or "").strip()
    if not token:
        return jsonify({"ok": False, "error": "token gerek"}), 400
    ok = portal_mod.revoke_token(token)
    return jsonify({"ok": True, "result": {"revoked": ok}})


@agents_bp.route("/api/agents/portal/delete-revoked", methods=["POST"])
def api_portal_delete_revoked():
    """Iptal edilmis tek token kaydini sil."""
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(portal_mod, "hasta_portal")
    if err: return err
    p = _payload()
    token = (p.get("token") or "").strip()
    if not token:
        return jsonify({"ok": False, "error": "token gerek"}), 400
    deleted = portal_mod.delete_revoked_token(token)
    return jsonify({"ok": True, "result": {"deleted": bool(deleted)}})


@agents_bp.route("/api/agents/portal/cleanup-revoked", methods=["POST"])
def api_portal_cleanup_revoked():
    """Iptal edilmis tum token kayitlarini temizle."""
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(portal_mod, "hasta_portal")
    if err: return err
    deleted_count = int(portal_mod.cleanup_revoked_tokens())
    return jsonify({"ok": True, "result": {"deleted_count": deleted_count}})


@agents_bp.route("/hasta-portal/giris", methods=["GET", "POST"])
def hasta_portal_giris():
    err = _agent_or_503(portal_mod, "hasta_portal")
    if err: return err
    token = request.args.get("token", "")
    sig = request.args.get("sig", "")
    if not token:
        return "Token eksik", 400

    # POST: TC + dogum yili dogrulama formu submit
    if request.method == "POST":
        tc = (request.form.get("tc_last4") or "").strip()
        by = (request.form.get("birth_year") or "").strip()
        if not portal_mod.verify_tc_birth(token, tc, by):
            return render_template_string(_PORTAL_TC_FORM,
                token=token, sig=sig, error="Bilgiler hatalÃ„Â± - tekrar deneyin")
        # Dogrulama OK - session set
        res = portal_mod.verify_token(token, mark_used=True)
        if res.ok:
            session["portal_patient_id"] = res.session.patient_id
            session["portal_token"] = token
            return _flask_redirect_obj("/hasta-portal?patient=1")
        return f"Hata: {res.error}", 403

    # GET: ilk acilis - token dogrula, TC gerekiyorsa form goster
    res = portal_mod.verify_token(token, mark_used=False)
    if not res.ok:
        return render_template_string(_PORTAL_ERROR_PAGE, error=res.error), 403
    # Sig dogrula
    try:
        import hashlib as _hl, hmac as _hmac
        expected_sig = _hmac.new(
            portal_mod.PORTAL_SECRET.encode(),
            f"{res.session.patient_id}|{token}".encode(),
            _hl.sha256).hexdigest()[:16]
        if sig and not _hmac.compare_digest(sig, expected_sig):
            return render_template_string(_PORTAL_ERROR_PAGE,
                error="GeÃƒÂ§ersiz imza - link tamam deÃ„Å¸il"), 403
    except Exception:
        pass

    # TC dogrulama gerekiyor mu?
    if res.magic_link == "NEEDS_TC_VERIFY":
        return render_template_string(_PORTAL_TC_FORM, token=token, sig=sig, error=None)

    # Direkt giris (TC ayarlanmamis)
    res2 = portal_mod.verify_token(token, mark_used=True)
    if res2.ok:
        session["portal_patient_id"] = res2.session.patient_id
        session["portal_token"] = token
        return _flask_redirect_obj("/hasta-portal?patient=1")
    return f"Hata: {res2.error}", 403


def _flask_redirect_obj(url):
    from flask import redirect as _redir
    return _redir(url)


_PORTAL_TC_FORM = r"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<title>DoÃ„Å¸rulama - Hasta Portal</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0d4f8b">
<link rel="apple-touch-icon" sizes="180x180" href="/static/icons/apple-touch-icon-180.png">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"Segoe UI",sans-serif;background:linear-gradient(135deg,#0d4f8b,#0a8a76);
color:#fff;padding:30px;min-height:100vh;min-height:100dvh;
display:flex;align-items:center;justify-content:center}
.card{background:#fff;color:#122236;border-radius:16px;padding:30px;max-width:420px;width:100%;
box-shadow:0 10px 40px rgba(0,0,0,0.25)}
h1{color:#0d4f8b;font-size:22px;margin-bottom:8px}
p{color:#5e7185;line-height:1.5;margin-bottom:18px;font-size:14px}
label{display:block;color:#0d4f8b;font-weight:600;font-size:13px;margin-bottom:6px;margin-top:14px}
input{width:100%;padding:14px 16px;font-size:16px;border:2px solid #cdd9e3;border-radius:10px;
-webkit-appearance:none;letter-spacing:1px}
input:focus{border-color:#1769aa;outline:none}
button{width:100%;background:#1769aa;color:#fff;border:0;padding:16px;border-radius:10px;
font-weight:700;font-size:15px;margin-top:20px;cursor:pointer;min-height:50px;
touch-action:manipulation;-webkit-appearance:none}
button:active{background:#0d4f8b}
.err{background:#fde7e9;color:#b3261e;padding:10px;border-radius:8px;font-size:13px;margin-top:12px}
.info{background:#e6f4ea;color:#0a8a76;padding:10px;border-radius:8px;font-size:12px;margin-top:12px}
</style></head><body>
<div class="card">
<h1>ÄŸÅ¸â€Â Kimlik DoÃ„Å¸rulama</h1>
<p>SayÃ„Â±n hastamÃ„Â±z, kiÃ…Å¸isel saÃ„Å¸lÃ„Â±k verilerinize eriÃ…Å¸im iÃƒÂ§in aÃ…Å¸aÃ„Å¸Ã„Â±daki bilgileri girin:</p>
<form method="POST" action="/hasta-portal/giris?token={{token|urlencode}}&sig={{sig|urlencode}}">
  <label>TC Kimlik No (son 4 hane)</label>
  <input type="tel" name="tc_last4" maxlength="4" pattern="[0-9]{4}" required
         placeholder="****" inputmode="numeric" autocomplete="off">
  <label>DoÃ„Å¸um YÃ„Â±lÃ„Â±</label>
  <input type="tel" name="birth_year" maxlength="4" pattern="[0-9]{4}" required
         placeholder="YYYY" inputmode="numeric" autocomplete="off">
  {% if error %}<div class="err">Ã¢Å¡Â  {{error}}</div>{% endif %}
  <button type="submit">Devam Et Ã¢â€ â€™</button>
</form>
<div class="info">ÄŸÅ¸â€â€™ Bu bilgiler sadece kimliÃ„Å¸inizi doÃ„Å¸rulamak iÃƒÂ§in kullanÃ„Â±lÃ„Â±r. Saklanmaz, paylaÃ…Å¸Ã„Â±lmaz.</div>
</div>
</body></html>"""


_PORTAL_ERROR_PAGE = r"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<title>Hata - Hasta Portal</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:-apple-system,sans-serif;background:linear-gradient(135deg,#b3261e,#5e7185);
color:#fff;padding:40px;text-align:center;min-height:100vh}
.card{background:#fff;color:#122236;border-radius:16px;padding:30px;max-width:400px;margin:0 auto;
box-shadow:0 10px 40px rgba(0,0,0,0.2)}
h1{color:#b3261e;font-size:20px;margin-bottom:12px}
p{color:#5e7185;line-height:1.5}
</style></head><body>
<div class="card">
<h1>Ã¢ÂÅ’ EriÃ…Å¸im SaÃ„Å¸lanamadÃ„Â±</h1>
<p>{{error}}</p>
<p style="margin-top:14px;font-size:13px">LÃƒÂ¼tfen klinikten yeni link talep edin.</p>
</div>
</body></html>"""


def _validate_patient_path(pid: str, abs_path: str):
    """Path traversal koruma - abs_path hasta klasorunun ICINDE mi?

    Donus: (rp_str, error_str) - error None ise OK.
    """
    if not abs_path:
        return None, "path yok"
    try:
        import sqlite3 as _sq, os as _os
        dbp = (os.environ.get("YAZKLINIK_DB_PATH")
                or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")
        con = _sq.connect(dbp)
        try:
            row = con.execute(
                "SELECT full_path FROM patients WHERE folder_key = ?", (pid,)
            ).fetchone()
            patient_root = row[0] if row else ""
        finally:
            con.close()
        if not patient_root:
            return None, "hasta klasoru yok"
        rp = _os.path.realpath(abs_path)
        pr = _os.path.realpath(patient_root)
        if not rp.startswith(pr):
            return None, "yetkisiz path"
        return rp, None
    except Exception as e:
        return None, f"hata: {e}"


def _portal_patient_root(pid: str) -> str:
    try:
        import sqlite3 as _sq
        dbp = (os.environ.get("YAZKLINIK_DB_PATH")
                or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")
        con = _sq.connect(dbp)
        try:
            row = con.execute(
                "SELECT full_path FROM patients WHERE folder_key = ?",
                (pid,)).fetchone()
        finally:
            con.close()
        return str(row[0] or "").strip() if row else ""
    except Exception:
        return ""


def _portal_list_diet_pdfs(pid: str, limit: int = 20) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        import sqlite3
        dbp = (os.environ.get("YAZKLINIK_DB_PATH")
                or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")
        con = _pgconn(sqlite_path=dbp)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT id, file_name, created_at, LENGTH(pdf_blob) AS pdf_size "
                "FROM patient_diet_documents "
                "WHERE patient_key=? AND COALESCE(deleted_at,'')='' "
                "ORDER BY created_at DESC, id DESC LIMIT ?",
                (pid, int(limit))).fetchall()
        finally:
            con.close()
        for row in rows:
            d = dict(row)
            doc_id = int(d.get("id") or 0)
            if doc_id < 1:
                continue
            out.append({
                "id": doc_id,
                "name": str(d.get("file_name") or f"YZ_Diyet_{doc_id}.pdf"),
                "created_at": str(d.get("created_at") or ""),
                "size": int(d.get("pdf_size") or 0),
            })
    except Exception:
        pass
    return out


def _portal_list_pregnancy_plan_pdfs(pid: str, limit: int = 10) -> List[Dict[str, Any]]:
    """Hasta klasorunde gebelik takip plani benzeri PDF'leri bul."""
    out: List[Dict[str, Any]] = []
    seen = set()
    keywords = ("gebelik", "takip", "plan", "preg")
    try:
        import sqlite3
        dbp = (os.environ.get("YAZKLINIK_DB_PATH")
                or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")
        con = _pgconn(sqlite_path=dbp)
        con.row_factory = sqlite3.Row
        try:
            rows = con.execute(
                "SELECT file_name, full_path, mtime "
                "FROM files "
                "WHERE patient_folder_key = ? "
                "  AND COALESCE(file_kind,'') = 'pdf' "
                "  AND (archived_at IS NULL OR archived_at = '') "
                "ORDER BY COALESCE(mtime,0) DESC",
                (pid,)).fetchall()
        finally:
            con.close()
        for row in rows:
            name = str(row["file_name"] or "").strip()
            path = str(row["full_path"] or "").strip()
            if not name or not path:
                continue
            low = name.lower()
            if not any(k in low for k in keywords):
                continue
            key = path.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append({
                "name": name,
                "abs_path": path,
                "mtime": int(row["mtime"] or 0),
            })
            if len(out) >= int(limit):
                break
    except Exception:
        pass
    out.sort(key=lambda x: int(x.get("mtime") or 0), reverse=True)
    return out[:max(1, int(limit))]


@agents_bp.route("/hasta-portal/cikis", methods=["GET"])
def hasta_portal_cikis():
    """Hasta session'unu temizle (doktor magic-link uretirken hasta gozune
    yanlislikla geciyse bunu cozer)."""
    session.pop("portal_patient_id", None)
    session.pop("portal_token", None)
    from flask import redirect as _redir
    return _redir("/hasta-portal?admin=1")


@agents_bp.route("/hasta-portal/media", methods=["GET"])
def hasta_portal_media():
    """Hasta sadece KENDI klasorundeki resim/PDF'lere erisebilir.

    Query:
      ?path=<abs_path>      - dosya yolu (zorunlu)
      &download=1           - opsiyonel - Content-Disposition: attachment
    """
    pid = session.get("portal_patient_id")
    if not pid:
        return "Yetki YOK", 401
    abs_path = request.args.get("path", "")
    download = request.args.get("download") in ("1", "true", "yes")
    rp, err = _validate_patient_path(pid, abs_path)
    if err:
        return err, 403 if err != "path yok" else 400
    import os as _os
    if not _os.path.isfile(rp):
        return "dosya yok", 404
    ext = rp.lower().rsplit(".", 1)[-1]
    if ext not in ("jpg", "jpeg", "png", "pdf", "mp4", "mov", "avi", "m4v", "webm"):
        return "izin verilmeyen tip", 403
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "pdf": "application/pdf",
            "mp4": "video/mp4", "mov": "video/quicktime",
            "avi": "video/x-msvideo", "m4v": "video/mp4",
            "webm": "video/webm"}[ext]
    fname = _os.path.basename(rp)
    return send_file(rp, mimetype=mime,
                      as_attachment=download,
                      download_name=fname)


@agents_bp.route("/hasta-portal/diyet/<int:doc_id>/pdf", methods=["GET"])
def hasta_portal_diet_pdf(doc_id: int):
    """Portal oturumundaki hastanin YZ diyet PDF kaydini sun."""
    pid = session.get("portal_patient_id")
    if not pid:
        return "Yetki YOK", 401
    try:
        import sqlite3
        from io import BytesIO
        dbp = (os.environ.get("YAZKLINIK_DB_PATH")
                or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")
        con = _pgconn(sqlite_path=dbp)
        con.row_factory = sqlite3.Row
        try:
            row = con.execute(
                "SELECT file_name, pdf_blob "
                "FROM patient_diet_documents "
                "WHERE id=? AND patient_key=? AND COALESCE(deleted_at,'')='' "
                "LIMIT 1",
                (int(doc_id), str(pid))).fetchone()
        finally:
            con.close()
        if not row:
            return "Diyet PDF bulunamadi", 404
        blob = bytes(row["pdf_blob"] or b"")
        if not blob:
            return "Diyet PDF icerigi bos", 404
        download = request.args.get("download") in ("1", "true", "yes")
        name = str(row["file_name"] or f"YZ_Diyet_{int(doc_id)}.pdf")
        return send_file(
            BytesIO(blob),
            mimetype="application/pdf",
            download_name=name,
            as_attachment=download,
            max_age=0,
        )
    except Exception as ex:
        return f"diyet pdf hata: {ex}", 500


@agents_bp.route("/hasta-portal/gebelik-takip-plani/pdf", methods=["GET"])
def hasta_portal_pregnancy_plan_pdf():
    """Portal oturumundaki hasta icin gebelik takip plani PDF blob uretir."""
    pid = session.get("portal_patient_id")
    if not pid:
        return "Yetki YOK", 401
    include_past = request.args.get("liste") == "tum"
    try:
        from io import BytesIO
        import yazklinik_web as _ykweb
        fn = getattr(_ykweb, "_preg_plan_pdf_blob_v1000", None)
        if not callable(fn):
            return "Gebelik plan PDF motoru hazir degil", 503
        blob = fn(str(pid), include_past=bool(include_past))
        if not blob:
            return "Gebelik takip plani PDF olusturulamadi", 404
        suffix = "tum" if include_past else "guncel"
        return send_file(
            BytesIO(blob),
            mimetype="application/pdf",
            download_name=f"Gebelik_Takip_Plani_{suffix}.pdf",
            as_attachment=False,
            max_age=0,
        )
    except Exception as ex:
        return f"gebelik plan pdf hata: {ex}", 500


@agents_bp.route("/hasta-portal/visit-zip", methods=["GET"])
def hasta_portal_visit_zip():
    """Ziyaret klasorunu ZIP olarak indir.

    Query: ?path=<visit_folder_path>
    Donus: zip file streaming, dosya adi: <visit_klasor>_dosyalar.zip
    """
    pid = session.get("portal_patient_id")
    if not pid:
        return "Yetki YOK", 401
    abs_path = request.args.get("path", "")
    rp, err = _validate_patient_path(pid, abs_path)
    if err:
        return err, 403 if err != "path yok" else 400
    import os as _os, io as _io, zipfile as _zip
    if not _os.path.isdir(rp):
        return "klasor yok", 404
    # Sadece izin verilen dosya tipleri (resim + PDF)
    allowed_ext = {".jpg", ".jpeg", ".png", ".pdf", ".mp4", ".mov", ".avi", ".m4v", ".webm"}
    folder_name = _os.path.basename(rp.rstrip("\\/"))
    buf = _io.BytesIO()
    file_count = 0
    try:
        with _zip.ZipFile(buf, "w", _zip.ZIP_DEFLATED) as zf:
            for f in sorted(_os.listdir(rp)):
                full = _os.path.join(rp, f)
                if not _os.path.isfile(full):
                    continue
                lo = f.lower()
                if not any(lo.endswith(e) for e in allowed_ext):
                    continue
                try:
                    zf.write(full, arcname=f)
                    file_count += 1
                except Exception:
                    pass
    except Exception as e:
        return f"zip uretilemedi: {e}", 500
    if file_count == 0:
        return "klasorde indirilebilir dosya yok", 404
    buf.seek(0)
    from flask import Response as _Resp
    resp = _Resp(buf.getvalue(), mimetype="application/zip")
    resp.headers["Content-Disposition"] = (
        f'attachment; filename="{folder_name}_dosyalar.zip"')
    return resp


@agents_bp.route("/hasta-portal", methods=["GET"])
@agents_bp.route("/op-dr-hakan-yaz", methods=["GET"])
def hasta_portal_home():
    """Dual-mode portal:
      - DOKTOR session varsa: yonetim paneli (link uret + son linkler)
      - HASTA portal session varsa: kendi ziyaret/recete listesi
      - Hicbiri yoksa: aciklama + giris linkleri
    """
    portal_pid = session.get("portal_patient_id")
    doktor_user = (session.get("user") or session.get("username"))

    # D700 2026-05-18: Magic-link ile gelen hasta oturumu klinik oturumundan
    # once gelir. Aksi halde doktorun/terminalin acik kaldigi tarayicida
    # hasta linki yonetim panelini gosterebilir.
    admin_view = request.args.get("admin") in ("1", "true", "yes")
    patient_view = request.args.get("patient") in ("1", "true", "yes")
    if (request.path or "").rstrip("/").lower() == "/op-dr-hakan-yaz":
        patient_view = True
    if doktor_user and (not portal_pid) and (not patient_view):
        # Doktor oturumu icin tek yonetim girisi: yeni admin paneli.
        return _flask_redirect_obj("/hasta-portal-admin")
    if admin_view and doktor_user:
        session.pop("portal_patient_id", None)
        session.pop("portal_token", None)
        # D700 yeni yonetim paneli: tokenli hasta portal + A5 QR ekrani.
        return _flask_redirect_obj("/hasta-portal-admin")
    elif portal_pid and doktor_user and not patient_view:
        portal_pid = None

    # MOD 1: Hasta magic-link ile gelmis; portal ekraninda menuler gosterilmez.
    if portal_pid:
        # Hasta URL'i legacy yapida kalsin: /hasta-portal?patient=1
        curr_path = (request.path or "").rstrip("/").lower()
        if curr_path == "/op-dr-hakan-yaz":
            return _flask_redirect_obj("/hasta-portal?patient=1")
        if curr_path == "/hasta-portal" and not patient_view:
            return _flask_redirect_obj("/hasta-portal?patient=1")

        visits = []
        pdfs = []
        meds = []
        labs = []
        diet_pdfs = []
        pregnancy_plan_pdfs = []
        custom_message = ""
        # Scopes oku - doktor sectiklerini filter et
        scopes = {"all": True}
        try:
            token_used = session.get("portal_token", "")
            if portal_mod and token_used:
                scopes = portal_mod.get_token_scopes(token_used)
        except Exception:
            pass
        custom_message = scopes.get("custom_message", "") or ""
        allowed_visits = scopes.get("visits")  # None = hepsi
        strict_visits = bool(scopes.get("strict_visits", False))
        show_pdfs = scopes.get("show_pdfs", scopes.get("all", True))
        show_meds = scopes.get("show_meds", scopes.get("all", True))
        show_labs = scopes.get("show_labs", scopes.get("all", True))

        if portal_mod:
            try:
                all_visits = portal_mod.list_my_visits(portal_pid)
                # Filter by allowed visit keys (doktor secimi varsa)
                if strict_visits and isinstance(allowed_visits, list) and allowed_visits:
                    visits = []
                    for v in all_visits:
                        vk = str(v.get("visit_key") or "")
                        fp = str(v.get("full_path") or "")
                        vd = str(v.get("visit_date") or "")
                        if vk in allowed_visits or fp in allowed_visits or vd in allowed_visits:
                            visits.append(v)
                else:
                    visits = all_visits
                media_map = {}
                try:
                    media_map = portal_mod.list_visit_media_map(
                        portal_pid, visits, max_imgs=12)
                except Exception:
                    media_map = {}
                for v in visits:
                    v["examination_clean"] = ""
                    v["control_note_clean"] = ""
                    v["notes_clean"] = ""
                    fp = v.get("full_path") or ""
                    try:
                        vk = str(v.get("visit_key") or "")
                        media = media_map.get(vk) if vk else None
                        if not media:
                            media = portal_mod.list_visit_images(
                                fp,
                                max_imgs=12,
                                patient_id=portal_pid,
                                visit_key=vk,
                                visit_date=v.get("visit_date") or "",
                            )
                        v["visit_images"] = media.get("images", [])
                        v["visit_videos"] = media.get("videos", [])
                        v["visit_pdfs"] = media.get("pdfs", [])
                        # Hasta portalinda doktor notu gosterilmez.
                        v["examination_clean"] = ""
                        v["control_note_clean"] = ""
                        v["notes_clean"] = ""
                    except Exception:
                        v["visit_images"] = []
                        v["visit_videos"] = []
                        v["visit_pdfs"] = []
            except Exception:
                pass
            # Hasta ekraninda toplu/tekrar PDF listesi gizli:
            # PDF sadece ziyaret kartinda tek rapor olarak gosterilir.
            pdfs = []
            if show_meds:
                try: meds = portal_mod.list_my_meds(portal_pid)
                except Exception: pass
            if show_labs:
                try: labs = portal_mod.list_my_labs(portal_pid)
                except Exception: pass
            try:
                diet_pdfs = _portal_list_diet_pdfs(portal_pid, limit=20)
            except Exception:
                diet_pdfs = []
            try:
                pregnancy_plan_pdfs = _portal_list_pregnancy_plan_pdfs(
                    portal_pid, limit=12)
            except Exception:
                pregnancy_plan_pdfs = []
        # D700 v17 2026-05-17: Hasta adini al - "Hos geldiniz X" diye selamla
        patient_name = ""
        try:
            import sqlite3 as _sql3, os as _os
            dbp = (_os.environ.get("YAZKLINIK_DB_PATH")
                    or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")
            con_pn = _sql3.connect(dbp)
            try:
                row_pn = con_pn.execute(
                    "SELECT display_name FROM patients WHERE folder_key=?",
                    (portal_pid,)).fetchone()
                if row_pn and row_pn[0]:
                    patient_name = str(row_pn[0]).strip()
            finally:
                con_pn.close()
        except Exception:
            pass
        return render_template_string(_PORTAL_HASTA_PAGE,
                                       visits=visits, pdfs=pdfs, meds=meds,
                                       labs=labs, custom_message=custom_message,
                                       pid=portal_pid, patient_name=patient_name,
                                       diet_pdfs=diet_pdfs,
                                       pregnancy_plan_pdfs=pregnancy_plan_pdfs)

    # MOD 2: Doktor login - yonetim paneli
    if doktor_user:
        # Son uretilen 20 token + hasta listesi
        recent_tokens = []
        all_patients = []
        try:
            import sqlite3, os, json as _json
            dbp = (os.environ.get("YAZKLINIK_DB_PATH")
                    or r"D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3")
            con = _pgconn(sqlite_path=dbp)
            con.row_factory = sqlite3.Row
            try:
                rows = con.execute(
                    "SELECT token, patient_id, phone, issued_at, expires_at, "
                    "  consumed_at, revoked_at, last_used_at, use_count "
                    "FROM patient_portal_tokens "
                    "ORDER BY COALESCE(last_used_at, issued_at) DESC LIMIT 30"
                ).fetchall()
                recent_tokens = [dict(r) for r in rows]
            except Exception:
                # Yeni kolon yoksa (eski sema) - en azindan eski sema ile dene
                try:
                    rows = con.execute(
                        "SELECT token, patient_id, phone, issued_at, expires_at, consumed_at "
                        "FROM patient_portal_tokens ORDER BY issued_at DESC LIMIT 30"
                    ).fetchall()
                    recent_tokens = [dict(r) for r in rows]
                except Exception:
                    pass
            # D700: TUM hastalari sayfaya gomerek arama client-side yapilacak
            # API stuck oluyor (Funnel/Werkzeug), bu yontem sifir network
            try:
                rows2 = con.execute(
                    "SELECT p.folder_key AS k, p.display_name AS n, "
                    "  COALESCE(pd.phone, pt.phone, '') AS p, "
                    "  COALESCE(pd.age, pt.age, 0) AS a "
                    "FROM patients p "
                    "LEFT JOIN patient_demographics pd ON pd.patient_key = p.folder_key "
                    "LEFT JOIN patient_type pt ON pt.patient_key = p.folder_key "
                    "WHERE p.archived_at IS NULL "
                    "ORDER BY p.updated_at DESC "
                    "LIMIT 5000"
                ).fetchall()
                all_patients = [dict(r) for r in rows2]
            except Exception:
                pass
            con.close()
        except Exception:
            pass
        return render_template_string(_PORTAL_DOKTOR_PAGE,
                                       doktor=doktor_user, tokens=recent_tokens,
                                       all_patients_json=_json.dumps(all_patients, ensure_ascii=False))

    # MOD 3: Hicbir session yok -> public aciklama sayfasi (login zorlamasi yok)
    return render_template_string(_PORTAL_LANDING_PAGE), 200


_PORTAL_HASTA_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Op. Dr. Hakan YAZ | YAZ Klinik</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0d4f8b">
<link rel="apple-touch-icon" sizes="180x180" href="/static/icons/apple-touch-icon-180.png">
<link rel="stylesheet" href="/static/yk-ios-mobile.css?v=d700-ios-2026-05-17">
<style>
:root{--safe-top:env(safe-area-inset-top,0px);--safe-bottom:env(safe-area-inset-bottom,0px)}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"Segoe UI",sans-serif;background:#f5f8fb;color:#122236;
padding:calc(20px+var(--safe-top)) 16px calc(20px+var(--safe-bottom));max-width:760px;margin:0 auto;
min-height:100vh;min-height:100dvh}
.hdr{background:linear-gradient(135deg,#0d4f8b 0%,#0a8a76 100%);color:#fff;
padding:20px;border-radius:14px;margin-bottom:18px}
.hdr h1{font-size:22px;margin-bottom:4px}
.hdr p{opacity:.85;font-size:14px}
.portal-brand{display:flex;align-items:center;gap:12px;margin-bottom:10px}
.portal-brand img{width:44px;height:44px;border-radius:12px;background:#fff;padding:4px;object-fit:contain}
.portal-brand-top{font-size:12px;letter-spacing:.7px;text-transform:uppercase;opacity:.92}
.portal-brand-sub{font-size:14px;font-weight:700}
.card{background:#fff;border:1px solid #cdd9e3;border-radius:10px;padding:14px;margin-bottom:10px;
box-shadow:0 1px 3px rgba(0,0,0,.06)}
.card b{color:#0d4f8b;font-size:15px}
.card .meta{font-size:12px;color:#5e7185;margin-top:4px}
.empty{text-align:center;padding:40px;color:#5e7185}
.foot{text-align:center;margin-top:20px;font-size:12px;color:#5e7185}
.portal-gallery-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(90px,1fr));gap:6px}
.portal-thumb-wrap{position:relative}
.portal-preview-link{display:block;aspect-ratio:1;background:#000;border-radius:6px;overflow:hidden}
.portal-preview-link img{width:100%;height:100%;object-fit:cover}
.portal-video-tile{display:block;aspect-ratio:1;background:#030b14;border-radius:6px;overflow:hidden}
.portal-video-tile video{width:100%;height:100%;object-fit:cover}
.portal-download-btn{position:absolute;bottom:4px;right:4px;background:rgba(13,79,139,0.92);
color:#fff;width:24px;height:24px;border-radius:50%;display:flex;align-items:center;justify-content:center;
text-decoration:none;font-size:12px;font-weight:700;box-shadow:0 2px 4px rgba(0,0,0,0.3)}
.portal-preview-modal{position:fixed;inset:0;background:rgba(8,18,30,0.86);z-index:9999;display:none;
align-items:center;justify-content:center;padding:10px}
.portal-preview-modal.open{display:flex}
.portal-preview-shell{width:min(100%,820px);max-height:calc(100dvh - 18px);background:#0e2034;border:1px solid #2a4667;
border-radius:14px;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 45px rgba(0,0,0,0.45)}
.portal-preview-top{display:flex;align-items:center;gap:8px;padding:10px;background:#132941;color:#dceeff}
.portal-preview-title{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1}
.portal-preview-count{font-size:12px;color:#a7bfd9}
.portal-preview-btn{border:0;background:#17395a;color:#fff;min-width:36px;height:36px;border-radius:9px;
font-size:16px;font-weight:700;cursor:pointer}
.portal-preview-btn:active{transform:scale(0.96)}
.portal-preview-stage{position:relative;background:#060f19;display:flex;align-items:center;justify-content:center;
min-height:42dvh;overflow:hidden;touch-action:pan-y}
.portal-preview-img{max-width:100%;max-height:58dvh;transform-origin:center center;transition:transform .15s ease}
.portal-preview-nav{position:absolute;top:50%;transform:translateY(-50%);width:42px;height:42px;border:0;
border-radius:50%;background:rgba(13,37,61,0.85);color:#fff;font-size:20px;font-weight:700;cursor:pointer}
.portal-preview-nav.prev{left:10px}
.portal-preview-nav.next{right:10px}
.portal-preview-tools{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px;padding:10px;background:#10253c}
.portal-preview-tools button{background:#204567;color:#fff;border:0;border-radius:9px;height:36px;font-weight:700;cursor:pointer}
.portal-preview-sliders{display:grid;grid-template-columns:1fr 1fr;gap:8px;padding:0 10px 10px;background:#10253c}
.portal-preview-slider-box{background:#17324f;border-radius:9px;padding:8px 10px;color:#dceeff;font-size:11px}
.portal-preview-slider-box input{width:100%;margin-top:6px}
@media(max-width:680px){
  .portal-preview-tools{grid-template-columns:repeat(2,minmax(0,1fr))}
  .portal-preview-sliders{grid-template-columns:1fr}
}
</style></head><body>
<div class="hdr">
  <div class="portal-brand">
    <img src="/static/brand_logo.png" alt="YAZ Klinik">
    <div>
      <div class="portal-brand-top">Op. Dr. Hakan YAZ</div>
      <div class="portal-brand-sub">YAZ Klinik Hasta Portali</div>
    </div>
  </div>
  {% if patient_name %}
    <div style="font-size:12px;opacity:.85;letter-spacing:1px;text-transform:uppercase;margin-bottom:6px">HoÃ…Å¸ Geldiniz</div>
    <h1 style="font-size:24px;margin-bottom:6px">{{patient_name}}</h1>
    <p>Hasta dosyanÃ„Â±z - son ziyaretler ve raporlar</p>
  {% else %}
    <h1>HoÃ…Å¸ Geldiniz</h1>
    <p>Hasta dosyanÃ„Â±z - son ziyaretler ve raporlar</p>
  {% endif %}
</div>
{% if custom_message %}
  <div style="background:linear-gradient(135deg,#fff8e1,#fff3c4);border-left:4px solid #f0b400;
              padding:14px 16px;border-radius:0 8px 8px 0;margin-bottom:14px">
    <div style="font-size:12px;font-weight:700;color:#b87333;margin-bottom:4px">ÄŸÅ¸â€™Â¬ DOKTORDAN MESAJ</div>
    <div style="font-size:14px;color:#7a5a00;white-space:pre-line">{{custom_message}}</div>
  </div>
{% endif %}

{% if visits %}
  <div style="background:#d9f4ec;color:#0a8a76;padding:10px 14px;border-radius:8px;
              margin:14px 0 8px;font-size:12px;display:flex;align-items:center;gap:8px">
    <span style="font-size:16px">ÄŸÅ¸â€â€</span>
    <span>Bu sayfa <b>her aÃƒÂ§Ã„Â±lÃ„Â±Ã…Å¸ta otomatik gÃƒÂ¼ncellenir</b> - sonraki ziyaretleriniz buraya eklenir.
    Linkinizi saklayÃ„Â±n, tekrar tekrar aÃƒÂ§abilirsiniz.</span>
  </div>
  <h3 style="color:#0d4f8b;font-size:16px;margin:14px 0 8px;display:flex;justify-content:space-between;align-items:center">
    <span>ÄŸÅ¸â€œâ€¹ Ziyaretleriniz ({{visits|length}})</span>
    {% if visits[0].visit_date %}
      <small style="color:#5e7185;font-size:11px;font-weight:400">Son: {{visits[0].visit_date}}</small>
    {% endif %}
  </h3>
  {% for v in visits %}
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <b style="font-size:15px">ÄŸÅ¸â€œâ€¦ {{v.visit_date or '-'}}</b>
      <span style="font-size:11px;color:#5e7185;background:#eff5fb;padding:2px 8px;border-radius:10px">{{v.visit_type or 'Muayene'}}</span>
    </div>
    {% if v.visit_images %}
    <div style="margin-top:10px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <div style="font-size:12px;color:#0d4f8b;font-weight:600">ÄŸÅ¸â€“Â¼ USG GÃƒÂ¶rÃƒÂ¼ntÃƒÂ¼leri ({{v.visit_images|length}}{% if v.image_count and v.image_count > v.visit_images|length %} / toplam {{v.image_count}}{% endif %})</div>
        {% if v.full_path %}
        <a href="/hasta-portal/visit-zip?path={{v.full_path|urlencode}}"
           style="background:#1769aa;color:#fff;padding:6px 10px;border-radius:6px;
                  text-decoration:none;font-size:11px;font-weight:700;white-space:nowrap">
          ÄŸÅ¸â€œÂ¦ Hepsini Ã„Â°ndir (ZIP)
        </a>
        {% endif %}
      </div>
      {% set visit_idx = loop.index0 %}
      <div class="portal-gallery-grid">
        {% for img in v.visit_images %}
        <div class="portal-thumb-wrap">
          <a href="/hasta-portal/media?path={{img.abs_path|urlencode}}" target="_blank"
             class="portal-preview-link"
             data-gallery="visit-{{visit_idx}}"
             data-title="{{v.visit_date or 'Ziyaret'}} - {{img.name or ('USG ' ~ loop.index)}}">
            <img src="/hasta-portal/media?path={{img.abs_path|urlencode}}" loading="lazy" alt="USG">
          </a>
          <a href="/hasta-portal/media?path={{img.abs_path|urlencode}}&download=1"
             title="Indir"
             class="portal-download-btn">&#x2B07;</a>
        </div>
        {% endfor %}
      </div>
    </div>
    {% endif %}

    {% if v.visit_videos %}
    <div style="margin-top:10px">
      <div style="font-size:12px;color:#1769aa;font-weight:600;margin-bottom:6px">Video Onizleme ({{v.visit_videos|length}})</div>
      <div class="portal-gallery-grid">
        {% for vid in v.visit_videos %}
        <div class="portal-thumb-wrap">
          <a class="portal-video-tile" href="/hasta-portal/media?path={{vid.abs_path|urlencode}}" target="_blank" rel="noopener">
            <video controls preload="metadata" playsinline>
              <source src="/hasta-portal/media?path={{vid.abs_path|urlencode}}" type="video/mp4">
            </video>
          </a>
          <a href="/hasta-portal/media?path={{vid.abs_path|urlencode}}&download=1"
             title="Video indir"
             class="portal-download-btn">&#x2B07;</a>
        </div>
        {% endfor %}
      </div>
    </div>
    {% endif %}

    {% if v.visit_pdfs %}
    <div style="margin-top:10px">
      <div style="font-size:12px;color:#0a8a76;font-weight:600;margin-bottom:6px">ÄŸÅ¸â€œâ€ Rapor / PDF</div>
      {% set pdf = v.visit_pdfs[0] %}
      <div style="display:inline-flex;gap:0;margin:2px;border-radius:8px;overflow:hidden">
        <a href="/hasta-portal/media?path={{pdf.abs_path|urlencode}}" target="_blank"
           style="background:#d9f4ec;color:#0a8a76;padding:8px 12px;
                  text-decoration:none;font-size:13px;font-weight:600">
          ÄŸÅ¸â€œâ€ {{pdf.name}}
        </a>
        <a href="/hasta-portal/media?path={{pdf.abs_path|urlencode}}&download=1"
           title="PDF Indir"
                   style="background:#0a8a76;color:#fff;padding:8px 12px;
                          text-decoration:none;font-size:13px;font-weight:700">
                  Ã¢Â¬â€¡ Ã„Â°ndir
        </a>
      </div>
    </div>
    {% endif %}

    {% if v.full_path and (v.visit_images or v.visit_videos or v.visit_pdfs) %}
    <div style="margin-top:10px;padding-top:8px;border-top:1px solid #eef3f8;text-align:center">
      <a href="/hasta-portal/visit-zip?path={{v.full_path|urlencode}}"
         style="display:inline-block;background:linear-gradient(135deg,#0d4f8b,#0a8a76);
                color:#fff;padding:10px 20px;border-radius:10px;text-decoration:none;
                font-weight:700;font-size:13px;box-shadow:0 3px 8px rgba(0,0,0,0.15)">
        ÄŸÅ¸â€œÂ¦ Bu ziyaretin TÃƒÅ“M dosyalarÃ„Â±nÃ„Â± ZIP olarak indir
      </a>
    </div>
    {% endif %}
  </div>
  {% endfor %}
{% endif %}

{% if pdfs %}
  <h3 style="color:#0a8a76;font-size:16px;margin:14px 0 8px">ÄŸÅ¸â€œâ€ Raporlar / PDF'ler ({{pdfs|length}})</h3>
  {% for p in pdfs %}
  <div class="card">
    <b>{{p.file_name}}</b>
    {% if p.report_type %}<span style="font-size:11px;color:#5e7185;float:right">{{p.report_type}}</span>{% endif %}
    <div class="meta">ÄŸÅ¸â€œâ€¦ {{p.created_at[:10] if p.created_at else '-'}} Ã¢â‚¬Â¢ {{p.source or 'klinik'}}</div>
  </div>
  {% endfor %}
{% endif %}

  <h3 style="color:#7a4dc8;font-size:16px;margin:14px 0 8px">YZ Diyet Listesi PDF{% if diet_pdfs %} ({{diet_pdfs|length}}){% endif %}</h3>
{% if diet_pdfs %}
  {% for d in diet_pdfs %}
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
      <div>
        <b>{{d.name}}</b>
        <div class="meta">{{d.created_at[:16] if d.created_at else '-'}}</div>
      </div>
      <a href="/hasta-portal/diyet/{{d.id}}/pdf" target="_blank" rel="noopener"
         style="background:#7a4dc8;color:#fff;padding:8px 12px;border-radius:8px;text-decoration:none;font-weight:700">
        PDF Ac
      </a>
    </div>
  </div>
  {% endfor %}
{% else %}
  <div class="card">
    <div class="meta" style="font-size:13px;color:#294860">
      Henuz YZ diyet PDF kaydi bulunmuyor.
    </div>
  </div>
{% endif %}

<h3 style="color:#1c6b9d;font-size:16px;margin:14px 0 8px">Gebelik Takip Plani PDF</h3>
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
    <div class="meta" style="font-size:13px;color:#294860">Guncel gebelik takip plani PDF onizleme</div>
    <a href="/hasta-portal/gebelik-takip-plani/pdf" target="_blank" rel="noopener"
       style="background:#1c6b9d;color:#fff;padding:8px 12px;border-radius:8px;text-decoration:none;font-weight:700">
      PDF Ac
    </a>
  </div>
</div>

{% if pregnancy_plan_pdfs %}
  <h3 style="color:#1c6b9d;font-size:16px;margin:14px 0 8px">Kayitli Gebelik Plan Dosyalari</h3>
  {% for p in pregnancy_plan_pdfs %}
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap">
      <b>{{p.name}}</b>
      <a href="/hasta-portal/media?path={{p.abs_path|urlencode}}" target="_blank" rel="noopener"
         style="background:#1769aa;color:#fff;padding:8px 12px;border-radius:8px;text-decoration:none;font-weight:700">
        Onizle
      </a>
    </div>
  </div>
  {% endfor %}
{% endif %}

{% if meds %}
  <h3 style="color:#b87333;font-size:16px;margin:14px 0 8px">ÄŸÅ¸â€™Å  Aktif Ã„Â°laÃƒÂ§lar ({{meds|length}})</h3>
  {% for m in meds %}
  <div class="card">
    <b>{{m.drug_name}}</b> {% if m.dose %}- {{m.dose}}{% endif %}
    {% if m.frequency %}<div class="meta">Ã¢ÂÂ° {{m.frequency}}</div>{% endif %}
    {% if m.indication %}<div class="meta">ÄŸÅ¸â€™Â¡ {{m.indication}}</div>{% endif %}
  </div>
  {% endfor %}
{% endif %}

{% if labs %}
  <h3 style="color:#a01e7e;font-size:16px;margin:14px 0 8px">ÄŸÅ¸Â§Âª Laboratuvar SonuÃƒÂ§larÃ„Â± ({{labs|length}})</h3>
  {% for l in labs %}
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <b>{{l.test_name or l.test_code}}</b>
      <span style="font-weight:700;color:{% if l.flag == 'H' or l.flag == 'critical' %}#b3261e{% elif l.flag == 'L' %}#b87333{% else %}#16815f{% endif %}">{{l.value}} {{l.unit or ''}}</span>
    </div>
    {% if l.reference_range %}<div class="meta">Referans: {{l.reference_range}}</div>{% endif %}
    {% if l.sample_date or l.report_date %}
      <div class="meta">ÄŸÅ¸â€œâ€¦ {{l.report_date or l.sample_date}}</div>
    {% endif %}
  </div>
  {% endfor %}
{% endif %}

{% if not visits and not pdfs and not meds and not labs and not custom_message %}
  <div class="card empty">
    HenÃƒÂ¼z kayÃ„Â±t bulunmamaktadÃ„Â±r.<br>
    Klinik ekibimiz veri girdikten sonra burada gÃƒÂ¶rÃƒÂ¼necektir.
  </div>
{% endif %}
<p class="foot">
  Op. Dr. Hakan Yaz KliniÃ„Å¸i<br>
  SorularÃ„Â±nÃ„Â±z iÃƒÂ§in klinik ile iletiÃ…Å¸ime geÃƒÂ§in.
</p>
<div id="portal-preview-modal" class="portal-preview-modal" aria-hidden="true">
  <div class="portal-preview-shell" role="dialog" aria-modal="true" aria-label="USG onizleme">
    <div class="portal-preview-top">
      <button type="button" class="portal-preview-btn" id="portal-preview-close-top" aria-label="Kapat">x</button>
      <div id="portal-preview-title" class="portal-preview-title">USG goruntusu</div>
      <div id="portal-preview-count" class="portal-preview-count">1/1</div>
    </div>
    <div id="portal-preview-stage" class="portal-preview-stage">
      <button type="button" class="portal-preview-nav prev" id="portal-preview-prev" aria-label="Onceki">&lt;</button>
      <img id="portal-preview-img" class="portal-preview-img" src="" alt="USG onizleme">
      <button type="button" class="portal-preview-nav next" id="portal-preview-next" aria-label="Sonraki">&gt;</button>
    </div>
    <div class="portal-preview-tools">
      <button type="button" id="portal-tool-zoomout">Zoom -</button>
      <button type="button" id="portal-tool-zoomin">Zoom +</button>
      <button type="button" id="portal-tool-rotate">Dondur</button>
      <button type="button" id="portal-tool-reset">Sifirla</button>
      <button type="button" id="portal-tool-next">Gorsel Degistir</button>
      <button type="button" id="portal-preview-close-bottom">Kapat</button>
    </div>
    <div class="portal-preview-sliders">
      <label class="portal-preview-slider-box">Parlaklik
        <input id="portal-tool-brightness" type="range" min="60" max="160" step="5" value="100">
      </label>
      <label class="portal-preview-slider-box">Kontrast
        <input id="portal-tool-contrast" type="range" min="60" max="160" step="5" value="100">
      </label>
    </div>
  </div>
</div>
<script>
(function(){
  const links = Array.from(document.querySelectorAll('.portal-preview-link'));
  if (!links.length) return;

  const modal = document.getElementById('portal-preview-modal');
  const image = document.getElementById('portal-preview-img');
  const titleEl = document.getElementById('portal-preview-title');
  const countEl = document.getElementById('portal-preview-count');
  const stage = document.getElementById('portal-preview-stage');
  const prevBtn = document.getElementById('portal-preview-prev');
  const nextBtn = document.getElementById('portal-preview-next');
  const closeTopBtn = document.getElementById('portal-preview-close-top');
  const closeBottomBtn = document.getElementById('portal-preview-close-bottom');
  const zoomInBtn = document.getElementById('portal-tool-zoomin');
  const zoomOutBtn = document.getElementById('portal-tool-zoomout');
  const rotateBtn = document.getElementById('portal-tool-rotate');
  const resetBtn = document.getElementById('portal-tool-reset');
  const nextToolBtn = document.getElementById('portal-tool-next');
  const brightnessSlider = document.getElementById('portal-tool-brightness');
  const contrastSlider = document.getElementById('portal-tool-contrast');

  const galleries = Object.create(null);
  links.forEach((link) => {
    const galleryId = link.dataset.gallery || 'default';
    if (!galleries[galleryId]) galleries[galleryId] = [];
    galleries[galleryId].push({
      src: link.getAttribute('href'),
      title: link.dataset.title || 'USG goruntusu'
    });
    link.dataset.galleryIndex = String(galleries[galleryId].length - 1);
    link.addEventListener('click', (ev) => {
      ev.preventDefault();
      openPreview(galleryId, Number(link.dataset.galleryIndex || '0'));
    });
  });

  let activeGallery = [];
  let activeIndex = 0;
  let zoom = 1;
  let rotate = 0;
  let brightness = 100;
  let contrast = 100;
  let isOpen = false;
  let touchStartX = 0;
  let touchActive = false;

  function applyImageAdjustments(){
    image.style.transform = 'scale(' + zoom + ') rotate(' + rotate + 'deg)';
    image.style.filter = 'brightness(' + brightness + '%) contrast(' + contrast + '%)';
  }

  function resetVisualState(){
    zoom = 1;
    rotate = 0;
    brightness = 100;
    contrast = 100;
    brightnessSlider.value = '100';
    contrastSlider.value = '100';
    applyImageAdjustments();
  }

  function renderCurrent(){
    const item = activeGallery[activeIndex];
    if (!item) return;
    image.src = item.src;
    titleEl.textContent = item.title || 'USG goruntusu';
    countEl.textContent = String(activeIndex + 1) + '/' + String(activeGallery.length || 1);
    prevBtn.style.display = activeGallery.length > 1 ? 'block' : 'none';
    nextBtn.style.display = activeGallery.length > 1 ? 'block' : 'none';
    applyImageAdjustments();
  }

  function nextImage(step){
    if (!activeGallery.length) return;
    activeIndex = (activeIndex + step + activeGallery.length) % activeGallery.length;
    renderCurrent();
  }

  function openPreview(galleryId, startIndex){
    activeGallery = galleries[galleryId] || [];
    if (!activeGallery.length) return;
    activeIndex = Math.max(0, Math.min(startIndex || 0, activeGallery.length - 1));
    resetVisualState();
    renderCurrent();
    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.style.overflow = 'hidden';
    isOpen = true;
  }

  function closePreview(){
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.style.overflow = '';
    isOpen = false;
  }

  prevBtn.addEventListener('click', () => nextImage(-1));
  nextBtn.addEventListener('click', () => nextImage(1));
  nextToolBtn.addEventListener('click', () => nextImage(1));
  closeTopBtn.addEventListener('click', closePreview);
  closeBottomBtn.addEventListener('click', closePreview);
  zoomInBtn.addEventListener('click', () => { zoom = Math.min(4, zoom + 0.2); applyImageAdjustments(); });
  zoomOutBtn.addEventListener('click', () => { zoom = Math.max(0.6, zoom - 0.2); applyImageAdjustments(); });
  rotateBtn.addEventListener('click', () => { rotate = (rotate + 90) % 360; applyImageAdjustments(); });
  resetBtn.addEventListener('click', resetVisualState);
  brightnessSlider.addEventListener('input', () => { brightness = Number(brightnessSlider.value || '100'); applyImageAdjustments(); });
  contrastSlider.addEventListener('input', () => { contrast = Number(contrastSlider.value || '100'); applyImageAdjustments(); });

  modal.addEventListener('click', (ev) => {
    if (ev.target === modal) closePreview();
  });

  window.addEventListener('keydown', (ev) => {
    if (!isOpen) return;
    if (ev.key === 'Escape') closePreview();
    if (ev.key === 'ArrowLeft') nextImage(-1);
    if (ev.key === 'ArrowRight') nextImage(1);
  });

  stage.addEventListener('touchstart', (ev) => {
    if (!isOpen || !ev.touches || ev.touches.length !== 1) return;
    touchStartX = ev.touches[0].clientX;
    touchActive = true;
  }, { passive: true });
  stage.addEventListener('touchend', (ev) => {
    if (!touchActive || !isOpen || !ev.changedTouches || !ev.changedTouches.length) return;
    const deltaX = ev.changedTouches[0].clientX - touchStartX;
    touchActive = false;
    if (Math.abs(deltaX) < 45) return;
    if (deltaX > 0) nextImage(-1);
    else nextImage(1);
  }, { passive: true });
})();
</script>
</body></html>"""


_PORTAL_DOKTOR_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Hasta Portal YÃƒÂ¶netimi</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1769aa">
<link rel="apple-touch-icon" sizes="180x180" href="/static/icons/apple-touch-icon-180.png">
<link rel="stylesheet" href="/static/yk-ios-mobile.css?v=d700-ios-2026-05-17">
<style>
:root{--safe-top:env(safe-area-inset-top,0px);--safe-bottom:env(safe-area-inset-bottom,0px)}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"Segoe UI",sans-serif;background:#f5f8fb;color:#122236;
padding:calc(20px+var(--safe-top)) 18px calc(20px+var(--safe-bottom));max-width:980px;margin:0 auto;
min-height:100vh;min-height:100dvh}
h1{color:#0d4f8b;font-size:24px;margin-bottom:6px}
.sub{color:#5e7185;font-size:14px;margin-bottom:24px}
.section{background:#fff;border:1px solid #cdd9e3;border-radius:12px;padding:18px;margin-bottom:18px}
.section h2{color:#1769aa;font-size:16px;margin-bottom:14px;display:flex;align-items:center;gap:8px}
.section h2 .num{background:#1769aa;color:#fff;width:24px;height:24px;border-radius:50%;
display:inline-flex;align-items:center;justify-content:center;font-size:12px;font-weight:700}
.form-row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:12px}
.form-row > *{flex:1;min-width:200px}
input,select{padding:12px 14px;border:1px solid #cdd9e3;border-radius:8px;font-size:16px;width:100%;
-webkit-appearance:none;background:#fff}
button{background:#1769aa;color:#fff;border:0;padding:12px 22px;border-radius:8px;
cursor:pointer;font-weight:700;font-size:14px;min-height:44px;touch-action:manipulation;-webkit-appearance:none}
button:active{transform:scale(0.97)}
button.btn-wa{background:#25d366}
button.btn-secondary{background:#5e7185}
.result{margin-top:12px;padding:14px;background:#eff5fb;border-radius:8px;font-family:monospace;
font-size:13px;word-break:break-all;display:none}
.result.show{display:block}
.result a{color:#1769aa;font-weight:700}
table{width:100%;border-collapse:collapse;display:block;overflow-x:auto}
th,td{padding:10px 8px;text-align:left;border-bottom:1px solid #eef3f8;font-size:13px;white-space:nowrap}
th{background:#eff5fb;color:#0d4f8b;font-size:11px;text-transform:uppercase;font-weight:700}
.status-active{color:#16815f;font-weight:700}
.status-used{color:#5e7185}
.status-expired{color:#b3261e}
.tip{background:#fff8e1;border-left:4px solid #f0b400;padding:12px 14px;border-radius:0 6px 6px 0;
font-size:13px;margin-bottom:18px;color:#7a5a00}
@media(max-width:600px){
  body{padding-left:12px;padding-right:12px}
  .form-row{flex-direction:column}
  .form-row > *{min-width:auto}
}
</style></head><body>
<h1>Hasta Portal YÃƒÂ¶netimi</h1>
<div class="sub">Doktor: <b>{{doktor}}</b> - Hastalara magic-link ÃƒÂ¼ret, WhatsApp ile gÃƒÂ¶nder, son linkleri takip et</div>

<div class="tip">
  <b>NasÃ„Â±l ÃƒÂ§alÃ„Â±Ã…Å¸Ã„Â±r:</b> Hasta iÃƒÂ§in magic-link ÃƒÂ¼retin, link WhatsApp ile hastaya gider, hasta 24 saat iÃƒÂ§inde tÃ„Â±klarsa ziyaret/reÃƒÂ§ete/USG bilgilerini gÃƒÂ¶rÃƒÂ¼r. Link tek kullanÃ„Â±mlÃ„Â±ktÃ„Â±r.
</div>

<div class="section">
  <h2><span class="num">1</span> Yeni Magic-Link ÃƒÅ“ret</h2>
  <input type="search" id="patient-search" placeholder="ÄŸÅ¸â€Â Hasta ara (ad, telefon, TC, dosya no)..."
         autocomplete="off" inputmode="search"
         style="width:100%;padding:14px 16px;font-size:16px;border:2px solid #1769aa;border-radius:10px;-webkit-appearance:none;margin-bottom:8px">
  <div id="search-status" style="font-size:12px;color:#5e7185;margin-bottom:8px;min-height:14px"></div>
  <div id="patient-results" style="background:#fff;border:2px solid #cdd9e3;
       border-radius:10px;max-height:380px;overflow-y:auto;
       display:none;margin-bottom:12px;box-shadow:0 4px 16px rgba(0,0,0,0.1)"></div>
  <div id="selected-patient" style="display:none;background:#e6f4ea;border:1px solid #16815f;
       border-radius:10px;padding:14px;margin-bottom:12px">
    <b style="color:#16815f">Ã¢Å“â€œ SeÃƒÂ§ili hasta:</b>
    <div id="selected-info" style="margin-top:6px;font-size:14px"></div>
  </div>

  <!-- SELECTOR WIZARD: hasta secince acilir -->
  <div id="share-wizard" style="display:none;background:#f5f8fb;border:1px solid #cdd9e3;
       border-radius:10px;padding:14px;margin-bottom:12px">
    <div style="background:linear-gradient(135deg,#e2eef7,#d9f4ec);border-left:4px solid #1769aa;
                padding:10px 14px;border-radius:0 6px 6px 0;margin-bottom:12px;font-size:13px;color:#0d4f8b">
      ÄŸÅ¸â€â€” <b>KALICI HASTA LÃ„Â°NKÃ„Â°:</b> Bu link hastanÃ„Â±n <b>tek eriÃ…Å¸im noktasÃ„Â±</b> olur.
      Hasta her aÃƒÂ§tÃ„Â±Ã„Å¸Ã„Â±nda en gÃƒÂ¼ncel verileri gÃƒÂ¶rÃƒÂ¼r - <u>sonradan eklenen ziyaretler otomatik gÃƒÂ¶zÃƒÂ¼kÃƒÂ¼r</u>.
      Belirli ziyaretleri kilitlemek istersen aÃ…Å¸aÃ„Å¸Ã„Â±dan seÃƒÂ§.
    </div>
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
      <b style="color:#0d4f8b;font-size:14px">ÄŸÅ¸â€œÂ¤ Hasta Ne GÃƒÂ¶rsÃƒÂ¼n?</b>
      <button type="button" onclick="loadShareOptions()" style="background:#5e7185;font-size:12px;padding:6px 10px">ÄŸÅ¸â€â€ Yenile</button>
    </div>

    <!-- Custom message -->
    <div style="margin-bottom:10px">
      <label style="font-size:12px;color:#0d4f8b;font-weight:600;display:block;margin-bottom:4px">ÄŸÅ¸â€™Â¬ Hasta iÃƒÂ§in ÃƒÂ¶zel mesaj (ÃƒÂ¼st kÃ„Â±sÃ„Â±mda gÃƒÂ¶rÃƒÂ¼nÃƒÂ¼r):</label>
      <textarea id="custom-message" rows="3" placeholder="Ãƒâ€“rn: SayÃ„Â±n AyÃ…Å¸e, sonuÃƒÂ§lar normal. 2 hafta sonra kontrol iÃƒÂ§in bekliyorum. - Dr. Hakan Yaz"
                style="width:100%;padding:10px;font-size:14px;border:1px solid #cdd9e3;border-radius:6px;resize:vertical;-webkit-appearance:none"></textarea>
    </div>

    <!-- Quick toggles -->
    <div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:10px;font-size:14px">
      <label style="display:inline-flex;align-items:center;gap:8px;cursor:pointer;padding:8px 12px;background:#fff;border:1px solid #cdd9e3;border-radius:8px">
        <input type="checkbox" id="opt-pdfs" checked
               style="width:20px;height:20px;accent-color:#1769aa;cursor:pointer;-webkit-appearance:checkbox !important;appearance:checkbox !important">
        ÄŸÅ¸â€œâ€ PDF/Rapor ArÃ…Å¸ivi
      </label>
      <label style="display:inline-flex;align-items:center;gap:8px;cursor:pointer;padding:8px 12px;background:#fff;border:1px solid #cdd9e3;border-radius:8px">
        <input type="checkbox" id="opt-meds" checked
               style="width:20px;height:20px;accent-color:#1769aa;cursor:pointer;-webkit-appearance:checkbox !important;appearance:checkbox !important">
        ÄŸÅ¸â€™Å  Ã„Â°laÃƒÂ§ Listesi
      </label>
      <label style="display:inline-flex;align-items:center;gap:8px;cursor:pointer;padding:8px 12px;background:#fff;border:1px solid #cdd9e3;border-radius:8px">
        <input type="checkbox" id="opt-labs" checked
               style="width:20px;height:20px;accent-color:#1769aa;cursor:pointer;-webkit-appearance:checkbox !important;appearance:checkbox !important">
        ÄŸÅ¸Â§Âª Lab SonuÃƒÂ§larÃ„Â±
      </label>
    </div>

    <!-- Visit selector (OPSIYONEL - kilitlemek istersen) -->
    <div id="visit-list-wrapper" style="display:none;margin-bottom:8px">
      <div style="font-size:12px;color:#0d4f8b;font-weight:600;margin-bottom:6px;display:flex;justify-content:space-between">
        <span>ÄŸÅ¸â€œâ€¹ Belirli ziyaretleri kilitle (boÃ…Å¸ bÃ„Â±rak = HEPSÃ„Â° + sonradan eklenenler)</span>
        <span>
          <a href="#" onclick="toggleAllVisits(true);return false" style="font-size:11px;margin-right:8px">Hepsi seÃƒÂ§</a>
          <a href="#" onclick="toggleAllVisits(false);return false" style="font-size:11px">HiÃƒÂ§biri</a>
        </span>
      </div>
      <div id="visit-list" style="max-height:200px;overflow-y:auto;background:#fff;padding:8px;border-radius:6px;border:1px solid #cdd9e3"></div>
    </div>

    <div style="font-size:11px;color:#5e7185;margin-top:6px;background:#fff;padding:8px;border-radius:6px;border:1px dashed #cdd9e3">
      Ã¢â€Â¹Ã¯Â¸Â <b>VarsayÃ„Â±lan</b> (hiÃƒÂ§bir ziyaret seÃƒÂ§ilmezse): Hasta tÃƒÂ¼m geÃƒÂ§miÃ…Å¸ + sonraki ziyaretleri gÃƒÂ¶rÃƒÂ¼r (otomatik gÃƒÂ¼ncel).<br>
      ÄŸÅ¸â€â€™ <b>Belirli seÃƒÂ§im</b>: Sadece seÃƒÂ§ilen ziyaretler gÃƒÂ¶zÃƒÂ¼kÃƒÂ¼r, sonradan eklenenler GÃƒâ€“ZÃƒÅ“KMEZ.
    </div>
  </div>

  <!-- KIMLIK DOGRULAMA: Hasta linke tikladiginda TC + dogum yili sorulur -->
  <div id="verify-wrapper" style="display:none;background:#fde7f5;border:1px solid #a01e7e;
       border-radius:10px;padding:14px;margin-bottom:12px">
    <div style="font-size:13px;color:#a01e7e;font-weight:700;margin-bottom:8px">
      ÄŸÅ¸â€Â Hasta Kimlik DoÃ„Å¸rulamasÃ„Â± (Ãƒâ€“nerilen - extra gÃƒÂ¼venlik)
    </div>
    <div style="font-size:12px;color:#5e7185;margin-bottom:8px">
      Hasta linke tÃ„Â±kladÃ„Â±Ã„Å¸Ã„Â±nda TC son 4 hane + doÃ„Å¸um yÃ„Â±lÃ„Â± sorulur (link ÃƒÂ§alÃ„Â±nsa da girilemez)
    </div>
    <div class="form-row">
      <input type="tel" id="tc_last4" placeholder="TC son 4 hane (opsiyonel)" maxlength="4"
             pattern="[0-9]{4}" inputmode="numeric" autocomplete="off">
      <input type="tel" id="birth_year" placeholder="DoÃ„Å¸um yÃ„Â±lÃ„Â± (opsiyonel) ÃƒÂ¶rn 1985" maxlength="4"
             pattern="[0-9]{4}" inputmode="numeric" autocomplete="off">
    </div>
    <div style="font-size:11px;color:#5e7185;margin-top:4px">
      Ã¢â€Â¹Ã¯Â¸Â Her ikisi de boÃ…Å¸ bÃ„Â±rakÃ„Â±lÃ„Â±rsa link doÃ„Å¸rudan aÃƒÂ§Ã„Â±lÃ„Â±r (gÃƒÂ¼venlik yok)
    </div>
  </div>

  <div class="form-row">
    <input type="text" id="pid" placeholder="Hasta ID (yukaridan secince doluyor)" autocomplete="off" readonly
           style="background:#f5f8fb">
    <input type="tel" id="phone" placeholder="Telefon (5XXX...)" inputmode="tel" autocomplete="off">
    <select id="ttl" style="max-width:240px;padding:14px 12px;font-size:16px;border:1px solid #cdd9e3;border-radius:8px;background:#fff">
      <option value="24">24 saat (tek seferlik)</option>
      <option value="72">3 gÃƒÂ¼n</option>
      <option value="168">1 hafta</option>
      <option value="720">1 ay</option>
      <option value="2160">3 ay</option>
      <option value="8760" selected>1 yÃ„Â±l (ÃƒÂ¶nerilen - kalÃ„Â±cÃ„Â± link)</option>
      <option value="87600">10 yÃ„Â±l (sÃƒÂ¼resiz)</option>
    </select>
  </div>
  <!-- FORM SUBMIT (XHR yerine - Funnel stuck bypass) -->
  <form id="link-form" method="POST" action="/hasta-portal/uret" target="_self">
    <input type="hidden" name="patient_id" id="form-pid">
    <input type="hidden" name="phone" id="form-phone">
    <input type="hidden" name="ttl_hours" id="form-ttl">
    <input type="hidden" name="tc_last4" id="form-tc">
    <input type="hidden" name="birth_year" id="form-by">
    <input type="hidden" name="custom_message" id="form-msg">
    <input type="hidden" name="opt_pdfs" id="form-opt-pdfs" value="1">
    <input type="hidden" name="opt_meds" id="form-opt-meds" value="1">
    <input type="hidden" name="opt_labs" id="form-opt-labs" value="1">
    <input type="hidden" name="do_whatsapp" id="form-wa" value="0">
    <div id="form-visits-hidden"></div>
    <div class="form-row">
      <button type="button" onclick="submitForm(false)">ÄŸÅ¸â€â€” Link ÃƒÅ“ret</button>
      <button type="button" class="btn-wa" onclick="submitForm(true)">ÄŸÅ¸â€œÂ± ÃƒÅ“ret + WhatsApp GÃƒÂ¶nder</button>
      <button type="button" class="btn-secondary" onclick="clearAll()">Temizle</button>
    </div>
  </form>
  <div class="result" id="result"></div>
</div>

<div class="section">
  <h2><span class="num">2</span> Son ÃƒÅ“retilen Linkler (20)</h2>
  <div style="display:flex;justify-content:flex-end;margin:-4px 0 10px 0">
    <button type="button" class="btn-secondary"
            onclick="cleanupRevokedTokens()"
            style="padding:8px 12px;font-size:12px;min-height:34px">
      Iptal edilenleri temizle
    </button>
  </div>
  <table>
    <thead><tr><th>Hasta ID</th><th>Tel</th><th>Uretildi</th><th>Sona Erer</th><th>Kullanim</th><th>Durum</th><th>Islem</th></tr></thead>
    <tbody>
    {% for t in tokens %}
    <tr>
      <td><small>{{t.patient_id[:25]}}{% if t.patient_id|length > 25 %}...{% endif %}</small></td>
      <td><small>{{t.phone or '-'}}</small></td>
      <td><small>{{t.issued_at[:16] if t.issued_at else '-'}}</small></td>
      <td><small>{{t.expires_at[:16] if t.expires_at else '-'}}</small></td>
      <td style="text-align:center">
        {% if t.use_count and t.use_count > 0 %}
          <span style="color:#16815f">{{t.use_count}}x</span>
          {% if t.last_used_at %}<br><small style="color:#5e7185">{{t.last_used_at[5:16]}}</small>{% endif %}
        {% else %}
          <span style="color:#5e7185">-</span>
        {% endif %}
      </td>
      <td>
      {% if t.revoked_at %}<span style="color:#b3261e;font-weight:700">Ã„Â°PTAL</span>
      {% elif t.use_count and t.use_count > 0 %}<span class="status-active">Aktif (kullaniliyor)</span>
      {% else %}<span class="status-active">HazÃ„Â±r</span>
      {% endif %}
      </td>
      <td>
        {% if not t.revoked_at %}
          <button onclick="revokeToken('{{t.token}}', '{{t.patient_id[:20]}}')"
                  style="background:#b3261e;padding:4px 8px;font-size:11px;min-height:28px">Iptal</button>
        {% else %}
          <button onclick="deleteRevokedToken('{{t.token}}', '{{t.patient_id[:20]}}')"
                  style="background:#5e7185;padding:4px 8px;font-size:11px;min-height:28px">Sil</button>
        {% endif %}
      </td>
    </tr>
    {% else %}
    <tr><td colspan="7" style="text-align:center;color:#5e7185;padding:20px">HenÃƒÂ¼z hiÃƒÂ§ link ÃƒÂ¼retilmemiÃ…Å¸</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>

<div class="section">
  <h2><span class="num">3</span> Test Ãƒâ€“nizleme (Kendi Magic-Linkin)</h2>
  <p style="color:#5e7185;font-size:13px;margin-bottom:12px">
    ÃƒÅ“retilen linki buraya yapÃ„Â±Ã…Å¸tÃ„Â±rÃ„Â±p ÃƒÂ¶nizleyebilirsin (hasta nasÃ„Â±l gÃƒÂ¶rÃƒÂ¼r?):
  </p>
  <div class="form-row">
    <input type="text" id="preview-url" placeholder="https://.../hasta-portal/giris?token=...&sig=...">
    <button onclick="previewLink()">ÄŸÅ¸â€˜Â Ãƒâ€“nizle</button>
  </div>
</div>

<script>
// --- D700 v5: TUM HASTALAR SAYFADA GOMULU + 100% CLIENT-SIDE ARAMA ---
// (Onceki XHR/Fetch versiyonlari Funnel/SW katmaninda stuck oluyordu)
// SW temizligi defansif:
(async function nukeSW(){
  try {
    if('serviceWorker' in navigator){
      const regs = await navigator.serviceWorker.getRegistrations();
      for(const reg of regs){ await reg.unregister(); }
    }
    if('caches' in window){
      const keys = await caches.keys();
      for(const k of keys){ await caches.delete(k); }
    }
  } catch(e) {}
})();

// SUNUCU GOMULU HASTA LISTESI (3500 hasta, ~300KB)
const ALL_PATIENTS = {{all_patients_json|safe}};
console.log('[YK-PORTAL] ' + ALL_PATIENTS.length + ' hasta sayfa yuklendi (client-side arama)');

// Turkce ASCII fold (DB'deki ile ayni mantik)
function trFold(s){
  return String(s||'').toLowerCase()
    .replace(/[Ã„Å¸Ã„Â]/g, 'g')
    .replace(/[ÃƒÂ¼ÃƒÅ“]/g, 'u')
    .replace(/[Ã…Å¸Ã…Â]/g, 's')
    .replace(/[Ã„Â±Ã„Â°iI]/g, 'i')
    .replace(/[ÃƒÂ¶Ãƒâ€“]/g, 'o')
    .replace(/[ÃƒÂ§Ãƒâ€¡]/g, 'c')
    .replace(/[ÃƒÂ¢Ãƒâ€š]/g, 'a')
    .replace(/[ÃƒÂ®ÃƒÂ]/g, 'i')
    .replace(/[ÃƒÂ»Ãƒâ€º]/g, 'u');
}

// Tum hastalarin search index'i (haystack pre-compute)
const SEARCH_INDEX = ALL_PATIENTS.map(p => ({
  k: p.k, n: p.n || '', ph: p.p || '', a: p.a || 0,
  h: trFold((p.n||'') + ' ' + (p.k||'') + ' ' + (p.p||''))
}));

let searchTimer = null;
const searchInput = document.getElementById('patient-search');
const resultsBox = document.getElementById('patient-results');
const statusBox = document.getElementById('search-status');

if(!searchInput) console.error('[YK-PORTAL] patient-search input bulunamadi!');
if(!resultsBox) console.error('[YK-PORTAL] patient-results div bulunamadi!');

if(searchInput){
  searchInput.addEventListener('input', (e) => {
    const q = e.target.value.trim();
    if(q.length < 2){
      resultsBox.style.display = 'none';
      statusBox.textContent = '(2 harf yaz - lokal arama, ' + ALL_PATIENTS.length + ' hasta)';
      return;
    }
    // ANLIK client-side arama (network gerek YOK)
    doSearch(q);
  });
}

function doSearch(q){
  // 100% client-side - sifir network, sifir gecikme
  const t0 = performance.now();
  const qFold = trFold(q);
  const words = qFold.split(/\s+/).filter(Boolean);
  if(words.length === 0){
    resultsBox.style.display = 'none';
    return;
  }
  // Filter + rank
  const matches = [];
  for(const p of SEARCH_INDEX){
    let allMatch = true;
    for(const w of words){
      if(!p.h.includes(w)){ allMatch = false; break; }
    }
    if(allMatch){
      const nameFold = trFold(p.n);
      let score = 1;
      if(nameFold.startsWith(words[0])) score += 10;
      if(nameFold.includes(words[0])) score += 5;
      if(words.every(w => nameFold.includes(w))) score += 8;
      matches.push({s: score, p: p});
      if(matches.length > 100) break; // cok genis arama korumasi
    }
  }
  matches.sort((a, b) => b.s - a.s);
  const items = matches.slice(0, 15).map(m => ({
    key: m.p.k, name: m.p.n, phone: m.p.ph, age: m.p.a
  }));
  const dt = Math.round(performance.now() - t0);
  console.log('[YK-PORTAL] Local search "' + q + '" -> ' + items.length + ' in ' + dt + 'ms');
  statusBox.style.color = '#5e7185';
  statusBox.textContent = items.length + ' sonuc (' + dt + 'ms lokal)';
  handleSearchResult({result: items}, q);
}

function handleSearchResult(d, q){
  try {
    const items = (d.result || []);
    statusBox.style.color = '#5e7185';
    statusBox.textContent = items.length + ' sonuc bulundu';

    if(items.length === 0){
      resultsBox.innerHTML = '<div style="padding:18px;text-align:center;color:#5e7185">Hasta bulunamadi: "' + escapeHtml(q) + '"</div>';
      resultsBox.style.display = 'block';
      return;
    }
    resultsBox.innerHTML = items.map(p =>
      '<div class="patient-item" data-key="' + escapeHtml(p.key || '') +
      '" data-name="' + escapeHtml(p.name || '') +
      '" data-phone="' + escapeHtml(p.phone || '') + '" ' +
      'style="padding:14px 16px;border-bottom:1px solid #eef3f8;cursor:pointer;' +
      'touch-action:manipulation;transition:background 0.15s">' +
      '<div style="font-weight:700;color:#0d4f8b;font-size:15px">' +
        escapeHtml(p.name || p.key || '?') + '</div>' +
      '<div style="font-size:12px;color:#5e7185;margin-top:4px">' +
        (p.phone ? 'ÄŸÅ¸â€œÂ± ' + escapeHtml(p.phone) + ' &nbsp;|&nbsp; ' : '') +
        'ÄŸÅ¸â€œÂ ' + escapeHtml((p.key || '').substring(0, 40)) +
        (p.age ? ' &nbsp;|&nbsp; ' + p.age + ' yas' : '') +
      '</div></div>'
    ).join('');
    resultsBox.style.display = 'block';
    console.log('[YK-PORTAL] Rendered', items.length, 'items');

    // Click + hover handlers
    resultsBox.querySelectorAll('.patient-item').forEach(el => {
      el.addEventListener('click', () => {
        console.log('[YK-PORTAL] Selected:', el.dataset);
        selectPatient({
          key: el.dataset.key,
          name: el.dataset.name,
          phone: el.dataset.phone
        });
      });
      el.addEventListener('mouseenter', () => el.style.background = '#eff5fb');
      el.addEventListener('mouseleave', () => el.style.background = '#fff');
    });
  } catch(err) {
    console.error('[YK-PORTAL] Fetch hatasi:', err);
    statusBox.style.color = '#b3261e';
    statusBox.textContent = 'Hata: ' + err.message;
    resultsBox.innerHTML = '<div style="padding:14px;color:#b3261e">Arama hatasi: ' + escapeHtml(err.message) + '</div>';
    resultsBox.style.display = 'block';
  }
}

function selectPatient(p){
  document.getElementById('pid').value = p.key;
  document.getElementById('phone').value = p.phone || '';
  document.getElementById('selected-info').innerHTML =
    '<b>' + escapeHtml(p.name) + '</b><br>' +
    '<small>Dosya: ' + escapeHtml(p.key) + '</small>' +
    (p.phone ? '<br><small>Tel: ' + escapeHtml(p.phone) + '</small>' :
      '<br><small style="color:#b87333">Ã¢Å¡Â  Telefon kayitli degil - elle gir</small>');
  document.getElementById('selected-patient').style.display = 'block';
  document.getElementById('share-wizard').style.display = 'block';
  document.getElementById('verify-wrapper').style.display = 'block';
  resultsBox.style.display = 'none';
  searchInput.value = p.name || p.key;
  // Visit listesini yukle (selector icin)
  loadShareOptions();
  if(!p.phone) document.getElementById('phone').focus();
}

function loadShareOptions(){
  const pid = document.getElementById('pid').value.trim();
  if(!pid) return;
  const wrapper = document.getElementById('visit-list-wrapper');
  const list = document.getElementById('visit-list');
  list.innerHTML = '<i style="color:#5e7185">Yukleniyor...</i>';
  wrapper.style.display = 'block';

  const xhr = new XMLHttpRequest();
  xhr.open('GET', '/api/agents/portal/share-options?patient_id=' +
          encodeURIComponent(pid) + '&_t=' + Date.now(), true);
  xhr.withCredentials = true;
  xhr.timeout = 10000;
  xhr.ontimeout = function(){ list.innerHTML = '<span style="color:#b3261e">Timeout</span>'; };
  xhr.onerror = function(){ list.innerHTML = '<span style="color:#b3261e">Hata</span>'; };
  xhr.onload = function(){
    try {
      const d = JSON.parse(xhr.responseText);
      if(!d.ok){ list.innerHTML = '<span style="color:#b3261e">' + d.error + '</span>'; return; }
      const visits = (d.result && d.result.visits) || [];
      const pdfs = (d.result && d.result.pdfs) || [];
      const meds = (d.result && d.result.meds) || [];
      const labs = (d.result && d.result.labs) || [];
      if(visits.length === 0){
        list.innerHTML = '<i style="color:#5e7185">Bu hastanin ziyaret kaydi YOK</i>';
      } else {
        list.innerHTML = visits.map((v, i) => {
          const hasMedia = (v.image_count > 0 || v.pdf_count > 0);
          const label = (v.visit_date || '-') + ' | ' + (v.visit_type || 'muayene');
          const media = hasMedia ? '<span style="color:#0a8a76;font-size:11px"> ÄŸÅ¸â€“Â¼ ' +
                       (v.image_count||0) + ' resim, ÄŸÅ¸â€œâ€ ' + (v.pdf_count||0) + ' pdf</span>' :
                       '<span style="color:#b87333;font-size:11px"> Ã¢Å¡Â  dosyasiz</span>';
          // Default: ilk 5 secili (dosyali olanlar)
          const checked = '';  // KALICI LINK: default HEPSI bos (auto-update)
          return '<label style="display:flex;align-items:center;gap:8px;padding:8px 4px;border-bottom:1px solid #eef3f8;cursor:pointer;font-size:13px">' +
            '<input type="checkbox" class="visit-cb" data-key="' + escapeHtml(v.full_path || v.visit_key || '') + '" ' + checked +
            ' style="width:18px;height:18px;accent-color:#1769aa;-webkit-appearance:checkbox !important;appearance:checkbox !important;flex-shrink:0"> ' +
            '<span><b>' + escapeHtml(label) + '</b>' + media + '</span></label>';
        }).join('');
      }
      // Pdfs / labs counts info
      let info = [];
      if(pdfs.length) info.push('ÄŸÅ¸â€œâ€ ' + pdfs.length + ' arÃ…Å¸iv PDF');
      if(meds.length) info.push('ÄŸÅ¸â€™Å  ' + meds.length + ' aktif ilaÃƒÂ§');
      if(labs.length) info.push('ÄŸÅ¸Â§Âª ' + labs.length + ' lab sonuÃƒÂ§');
      if(info.length){
        list.insertAdjacentHTML('beforeend',
          '<div style="font-size:11px;color:#5e7185;margin-top:8px;padding-top:6px;border-top:1px solid #eef3f8">Mevcut: ' + info.join(' | ') + '</div>');
      }
    } catch(e){
      list.innerHTML = '<span style="color:#b3261e">Parse hatasi: ' + e.message + '</span>';
    }
  };
  xhr.send();
}

function toggleAllVisits(state){
  document.querySelectorAll('.visit-cb').forEach(cb => { cb.checked = state; });
}

function collectShareConfig(){
  const selected = [];
  document.querySelectorAll('.visit-cb:checked').forEach(cb => {
    if(cb.dataset.key) selected.push(cb.dataset.key);
  });
  return {
    visits: selected.length > 0 ? selected : null,  // null = hepsi default
    show_pdfs: document.getElementById('opt-pdfs').checked,
    show_meds: document.getElementById('opt-meds').checked,
    show_labs: document.getElementById('opt-labs').checked,
    custom_message: document.getElementById('custom-message').value.trim()
  };
}

function clearAll(){
  searchInput.value = '';
  document.getElementById('pid').value = '';
  document.getElementById('phone').value = '';
  document.getElementById('selected-patient').style.display = 'none';
  document.getElementById('share-wizard').style.display = 'none';
  document.getElementById('custom-message').value = '';
  document.getElementById('result').classList.remove('show');
  resultsBox.style.display = 'none';
}

function escapeHtml(s){
  return String(s||'').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}

function revokeToken(token, patientId){
  if(!confirm('Bu link iptal edilsin mi?\n\nHasta: ' + patientId + '\n\nIptal sonrasi hasta bu link ile artik giremez.')) return;
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/agents/portal/revoke?_t=' + Date.now(), true);
  xhr.withCredentials = true;
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.timeout = 8000;
  xhr.onload = function(){
    if(xhr.status === 200){
      alert('Link iptal edildi.');
      location.reload();
    } else {
      alert('Hata: ' + xhr.status + ' - ' + xhr.responseText.substring(0, 200));
    }
  };
  xhr.onerror = function(){ alert('Ag hatasi'); };
  xhr.ontimeout = function(){ alert('Timeout'); };
  xhr.send(JSON.stringify({token: token}));
}

function deleteRevokedToken(token, patientId){
  if(!confirm('Iptal edilmis link kaydi silinsin mi?\n\nHasta: ' + patientId + '\n\nBu islem geri alinmaz.')) return;
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/agents/portal/delete-revoked?_t=' + Date.now(), true);
  xhr.withCredentials = true;
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.timeout = 8000;
  xhr.onload = function(){
    if(xhr.status === 200){
      try {
        const data = JSON.parse(xhr.responseText || '{}');
        if(data && data.result && data.result.deleted){
          alert('Kayit silindi.');
        } else {
          alert('Kayit silinemedi (iptal edilmis olmayabilir).');
        }
      } catch(e) {
        alert('Kayit silindi.');
      }
      location.reload();
    } else {
      alert('Hata: ' + xhr.status + ' - ' + xhr.responseText.substring(0, 200));
    }
  };
  xhr.onerror = function(){ alert('Ag hatasi'); };
  xhr.ontimeout = function(){ alert('Timeout'); };
  xhr.send(JSON.stringify({token: token}));
}

function cleanupRevokedTokens(){
  if(!confirm('Iptal edilen tum link kayitlari temizlensin mi?\n\nBu islem geri alinmaz.')) return;
  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/agents/portal/cleanup-revoked?_t=' + Date.now(), true);
  xhr.withCredentials = true;
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.timeout = 10000;
  xhr.onload = function(){
    if(xhr.status === 200){
      let deletedCount = 0;
      try {
        const data = JSON.parse(xhr.responseText || '{}');
        deletedCount = Number((data && data.result && data.result.deleted_count) || 0);
      } catch(e) {}
      alert(deletedCount + ' adet iptal edilmis link kaydi temizlendi.');
      location.reload();
    } else {
      alert('Hata: ' + xhr.status + ' - ' + xhr.responseText.substring(0, 200));
    }
  };
  xhr.onerror = function(){ alert('Ag hatasi'); };
  xhr.ontimeout = function(){ alert('Timeout'); };
  xhr.send('{}');
}

// --- D700 v6: FORM SUBMIT (browser native, Funnel/Werkzeug stuck bypass) ---
function submitForm(doWhatsApp){
  const pid = document.getElementById('pid').value.trim();
  if(!pid){
    alert('Once yukaridan hasta sec (arama kutusu)');
    searchInput.focus();
    return;
  }
  // Form alanlarini doldur
  document.getElementById('form-pid').value = pid;
  document.getElementById('form-phone').value = document.getElementById('phone').value.trim();
  document.getElementById('form-ttl').value = document.getElementById('ttl').value;
  document.getElementById('form-tc').value = (document.getElementById('tc_last4') || {}).value || '';
  document.getElementById('form-by').value = (document.getElementById('birth_year') || {}).value || '';
  document.getElementById('form-msg').value = (document.getElementById('custom-message') || {}).value || '';
  document.getElementById('form-opt-pdfs').value = document.getElementById('opt-pdfs').checked ? '1' : '0';
  document.getElementById('form-opt-meds').value = document.getElementById('opt-meds').checked ? '1' : '0';
  document.getElementById('form-opt-labs').value = document.getElementById('opt-labs').checked ? '1' : '0';
  document.getElementById('form-wa').value = doWhatsApp ? '1' : '0';
  // Secilen ziyaretleri hidden input olarak ekle
  const hiddenWrapper = document.getElementById('form-visits-hidden');
  hiddenWrapper.innerHTML = '';
  document.querySelectorAll('.visit-cb:checked').forEach(cb => {
    if(cb.dataset.key){
      const inp = document.createElement('input');
      inp.type = 'hidden';
      inp.name = 'visit_keys';
      inp.value = cb.dataset.key;
      hiddenWrapper.appendChild(inp);
    }
  });
  console.log('[YK-PORTAL] FORM SUBMIT pid=' + pid + ' wa=' + doWhatsApp);
  document.getElementById('link-form').submit();
}

// LEGACY (artik kullanilmiyor - FORM submit'e cevrildi)
function issueLink(callback){
  const pid = document.getElementById('pid').value.trim();
  const phone = document.getElementById('phone').value.trim();
  const ttl = parseInt(document.getElementById('ttl').value || '24');
  if(!pid){
    alert('Once yukaridan hasta sec (arama kutusu)');
    searchInput.focus();
    if(callback) callback(null);
    return;
  }
  const result = document.getElementById('result');
  result.classList.add('show');
  result.innerHTML = '<i>Link uretiliyor...</i>';
  console.log('[YK-PORTAL] issueLink START pid=' + pid + ' phone=' + phone);

  const xhr = new XMLHttpRequest();
  xhr.open('POST', '/api/agents/portal/issue-link?_t=' + Date.now(), true);
  xhr.withCredentials = true;
  xhr.setRequestHeader('Content-Type', 'application/json');
  xhr.setRequestHeader('Cache-Control', 'no-cache');
  xhr.setRequestHeader('X-Requested-With', 'XMLHttpRequest');
  xhr.timeout = 15000;
  xhr.ontimeout = function(){
    console.warn('[YK-PORTAL] issueLink TIMEOUT 15s');
    result.innerHTML = '<b style="color:#b3261e">Ã¢Å¡Â  Sunucu cevap vermedi (15s)</b>';
    if(callback) callback(null);
  };
  xhr.onerror = function(){
    console.error('[YK-PORTAL] issueLink ERROR');
    result.innerHTML = '<b style="color:#b3261e">Ã¢Å¡Â  Ag hatasi - tekrar dene</b>';
    if(callback) callback(null);
  };
  xhr.onload = function(){
    console.log('[YK-PORTAL] issueLink DONE status:', xhr.status);
    if(xhr.status === 401){
      result.innerHTML = '<b style="color:#b3261e">Ã¢Å¡Â  Yetki YOK - tekrar login</b>';
      if(callback) callback(null); return;
    }
    if(xhr.status !== 200){
      result.innerHTML = '<b style="color:#b3261e">Ã¢Å¡Â  HTTP ' + xhr.status + '</b><br>' +
        '<small>' + escapeHtml(xhr.responseText.substring(0, 200)) + '</small>';
      if(callback) callback(null); return;
    }
    let d;
    try { d = JSON.parse(xhr.responseText); }
    catch(e){
      result.innerHTML = '<b style="color:#b3261e">JSON parse hatasi</b>';
      if(callback) callback(null); return;
    }
    if(d.ok && d.result && d.result.magic_link){
      const link = d.result.magic_link;
      result.innerHTML = '<b style="color:#16815f">Ã¢Å“â€œ Magic Link uretildi (' + ttl + ' saat gecerli):</b><br><br>' +
        '<div style="background:#fff;padding:10px;border-radius:6px;border:1px solid #cdd9e3;word-break:break-all">' +
        '<a href="' + link + '" target="_blank">' + link + '</a></div><br>' +
        '<button id="btnCopy" style="background:#5e7185">ÄŸÅ¸â€œâ€¹ Kopyala</button> ' +
        '<button id="btnPreview" style="background:#1769aa">ÄŸÅ¸â€˜Â Onizle</button>';
      // Event listenerlari ekle (inline onclick yerine)
      document.getElementById('btnCopy').addEventListener('click', () => copyLink(link));
      document.getElementById('btnPreview').addEventListener('click', () => window.open(link, '_blank'));
      if(callback) callback(d);
    } else {
      result.innerHTML = '<b style="color:#b3261e">Hata:</b> ' +
        escapeHtml(d.error || JSON.stringify(d));
      if(callback) callback(null);
    }
  };
  const shareConfig = collectShareConfig();
  const tcLast4 = (document.getElementById('tc_last4') || {}).value || '';
  const birthYear = (document.getElementById('birth_year') || {}).value || '';
  console.log('[YK-PORTAL] share_config:', shareConfig, 'tc:', tcLast4, 'birth:', birthYear);
  xhr.send(JSON.stringify({
    patient_id: pid, phone: phone, ttl_hours: ttl,
    share_config: shareConfig,
    tc_last4: tcLast4,
    birth_year: birthYear
  }));
}

function issueAndWhatsApp(){
  const phone = document.getElementById('phone').value.trim();
  if(!phone){
    alert('Telefon gerekli - hasta secince otomatik dolar veya elle gir');
    return;
  }
  issueLink((d) => {
    if(!d || !d.ok || !d.result || !d.result.magic_link) return;
    const cleanPhone = phone.replace(/\D/g, '');
    let waPhone = cleanPhone;
    if(waPhone.startsWith('0')) waPhone = '90' + waPhone.substring(1);
    else if(!waPhone.startsWith('90') && waPhone.length === 10) waPhone = '90' + waPhone;
    const msg = encodeURIComponent(
      'Sayin hastamiz,\n\n' +
      'Kendi dosyaniza erisim icin asagidaki linke tikkayabilirsiniz:\n' +
      d.result.magic_link + '\n\n' +
      'Link 24 saat gecerlidir, tek kullanimliktir.\n\n' +
      '- Op. Dr. Hakan Yaz Klinigi'
    );
    window.open('https://wa.me/' + waPhone + '?text=' + msg, '_blank');
  });
}

function copyLink(text){
  navigator.clipboard.writeText(text).then(
    () => alert('Ã¢Å“â€œ Link kopyalandi'),
    () => alert('Kopyalanamadi - elle sec ve kopyala')
  );
}

function previewLink(){
  const url = document.getElementById('preview-url').value.trim();
  if(url) window.open(url, '_blank');
}
</script>
</body></html>"""


_PORTAL_LANDING_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Hasta Portal - GiriÃ…Å¸</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0d4f8b">
<link rel="apple-touch-icon" sizes="180x180" href="/static/icons/apple-touch-icon-180.png">
<link rel="stylesheet" href="/static/yk-ios-mobile.css?v=d700-ios-2026-05-17">
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,"Segoe UI",sans-serif;background:linear-gradient(135deg,#0d4f8b 0%,#0a8a76 100%);color:#fff;
padding:24px;min-height:100vh;min-height:100dvh;display:flex;align-items:center;justify-content:center}
.card{background:#fff;color:#122236;border-radius:16px;padding:30px;max-width:480px;width:100%;
box-shadow:0 10px 40px rgba(0,0,0,0.2)}
h1{color:#0d4f8b;font-size:22px;margin-bottom:8px}
p{color:#5e7185;line-height:1.6;margin-bottom:16px}
.btn{display:block;background:#1769aa;color:#fff;padding:14px;border-radius:10px;
text-align:center;text-decoration:none;font-weight:700;margin-top:12px;min-height:44px;
display:flex;align-items:center;justify-content:center;touch-action:manipulation}
.btn.btn-secondary{background:#5e7185}
.info{background:#eff5fb;padding:14px;border-radius:8px;font-size:13px;color:#0d4f8b;margin-bottom:16px}
</style></head><body>
<div class="card">
<h1>Hasta Portal</h1>
<p>Bu sayfa kiÃ…Å¸iye ÃƒÂ¶zel hasta eriÃ…Å¸imi iÃƒÂ§indir. Klinikten size gelen <b>magic-link</b> mesajÃ„Â±na tÃ„Â±klamanÃ„Â±z gerekir.</p>
<div class="info">
<b>HastaysanÃ„Â±z:</b> Klinikten size WhatsApp ile gelen linke tÃ„Â±klayÃ„Â±n.<br>
<b>Klinik personeliyseniz:</b> Doktor hesabÃ„Â± ile giriÃ…Å¸ yapÃ„Â±n.
</div>
<a href="/giris?next=/hasta-portal" class="btn">Doktor / Personel GiriÃ…Å¸i</a>
<a href="/" class="btn btn-secondary">Ana Sayfaya DÃƒÂ¶n</a>
</div>
</body></html>"""


# --- 2FA TOTP ---
@agents_bp.route("/api/agents/2fa/setup", methods=["POST"])
def api_2fa_setup():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(twofa_mod, "2fa")
    if err: return err
    user = (session.get("user") or session.get("username") or "doktor")
    return _wrap_call("2fa_setup", twofa_mod.setup, {"user": user})


@agents_bp.route("/api/agents/2fa/enable", methods=["POST"])
def api_2fa_enable():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(twofa_mod, "2fa")
    if err: return err
    p = _payload()
    user = (session.get("user") or session.get("username") or "doktor")
    ok = twofa_mod.enable(user, p.get("code", ""))
    return jsonify({"ok": True, "result": {"enabled": ok}})


@agents_bp.route("/api/agents/2fa/verify", methods=["POST"])
def api_2fa_verify():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(twofa_mod, "2fa")
    if err: return err
    p = _payload()
    user = (session.get("user") or session.get("username") or "doktor")
    ok = twofa_mod.verify(user, p.get("code", ""))
    return jsonify({"ok": True, "result": {"verified": ok}})


@agents_bp.route("/api/agents/2fa/reset", methods=["POST"])
def api_2fa_reset():
    """Mevcut 2FA'yi mevcut TOTP kodu ile sifirla. Sonra setup tekrar cagrilabilir."""
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(twofa_mod, "2fa")
    if err: return err
    p = _payload()
    user = (session.get("user") or session.get("username") or "doktor")
    ok = twofa_mod.reset(user, p.get("code", ""))
    return jsonify({"ok": True, "result": {"reset": ok}})


@agents_bp.route("/2fa-setup", methods=["GET"])
def two_fa_setup_page():
    auth = _require_session()
    if auth:
        return auth
    return render_template_string(r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>2FA Kurulum - YazKlinik</title>
<style>
body{font-family:-apple-system,Segoe UI,Arial,sans-serif;background:#eef5fb;color:#16243a;margin:0;padding:24px}
.shell{max-width:980px;margin:0 auto}.top{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}
.steps{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:14px;margin-top:18px}
.card{background:#fff;border:1px solid #cbddeb;border-radius:12px;padding:18px;box-shadow:0 14px 32px rgba(21,69,105,.08)}
h1{margin:0;color:#15395c}h2{font-size:17px;margin:0 0 10px}.muted{color:#63758a;font-size:13px;line-height:1.45}
button,.btn{border:0;background:#1769aa;color:white;border-radius:9px;padding:10px 14px;font-weight:800;cursor:pointer;text-decoration:none;display:inline-flex;gap:8px;align-items:center}
button.secondary{background:#eef4fa;color:#17324a;border:1px solid #c4d7e8}input,textarea{width:100%;box-sizing:border-box;border:1px solid #bfd0df;border-radius:9px;padding:10px;font:inherit}
textarea{min-height:84px;font-family:Consolas,monospace;font-size:12px}.qrbox{background:#f6fbff;border:1px dashed #9ab9d4;border-radius:12px;padding:12px;word-break:break-all;font-family:Consolas,monospace;font-size:12px}
.ok{color:#15803d;font-weight:800}.fail{color:#b42318;font-weight:800}.codes{display:grid;grid-template-columns:repeat(2,1fr);gap:6px;margin-top:8px}.code{background:#f2f6fb;border-radius:8px;padding:7px;text-align:center;font-family:Consolas,monospace}
</style></head><body><main class="shell">
<div class="top"><div><h1>2FA Kurulum</h1><p class="muted">Doktor hesabi icin TOTP/Authenticator kurulumu.</p></div><a class="btn" href="/ajanlar">Ajanlara don</a></div>
<div class="steps">
<section class="card"><h2>1. Kurulumu baslat</h2><p class="muted">Secret uretilir, QR yerine otpauth URL kopyalanabilir.</p><button onclick="startSetup()">Setup baslat</button><div id="setupStatus" class="muted" style="margin-top:10px"></div></section>
<section class="card"><h2>2. Authenticator'a ekle</h2><p class="muted">Google/Microsoft Authenticator'da manuel anahtar veya otpauth URL ile ekleyin.</p><label>Secret</label><input id="secret" readonly><label style="margin-top:8px;display:block">otpauth URL</label><textarea id="otpauth" readonly></textarea><button class="secondary" onclick="copyOtp()">URL kopyala</button></section>
<section class="card"><h2>3. 6 hane kodu dogrula</h2><p class="muted">Uygulamadaki 6 haneli kodu yazin ve 2FA'yi aktif edin.</p><input id="code" inputmode="numeric" maxlength="6" placeholder="123456"><button style="margin-top:10px" onclick="enable2fa()">Aktif et</button><div id="verifyStatus" style="margin-top:10px"></div><h2 style="margin-top:18px">Backup kodlari</h2><div id="codes" class="codes"></div><button class="secondary" style="margin-top:10px" onclick="downloadCodes()">Backup kodlarini indir</button></section>
</div>
</main><script>
let setupData=null;
async function postJson(url, body){const r=await fetch(url,{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},body:JSON.stringify(body||{})}); const d=await r.json(); if(!r.ok||!d.ok) throw new Error((d&&d.error)||r.status); return d.result||d;}
async function startSetup(){const st=document.getElementById('setupStatus'); st.textContent='Hazirlaniyor...'; try{setupData=await postJson('/api/agents/2fa/setup',{}); document.getElementById('secret').value=setupData.secret_b32||''; document.getElementById('otpauth').value=setupData.qr_url||''; document.getElementById('codes').innerHTML=(setupData.backup_codes||[]).map(c=>'<div class="code">'+c+'</div>').join(''); st.innerHTML='<span class="ok">Setup hazir.</span>'; }catch(e){st.innerHTML='<span class="fail">'+e.message+'</span>';}}
async function enable2fa(){const box=document.getElementById('verifyStatus'); box.textContent='Kontrol ediliyor...'; try{const res=await postJson('/api/agents/2fa/enable',{code:document.getElementById('code').value}); box.innerHTML=res.enabled?'<span class="ok">2FA aktif edildi.</span>':'<span class="fail">Kod gecersiz.</span>'; }catch(e){box.innerHTML='<span class="fail">'+e.message+'</span>';}}
function copyOtp(){const t=document.getElementById('otpauth'); t.select(); document.execCommand('copy');}
function downloadCodes(){const codes=(setupData&&setupData.backup_codes)||[]; const blob=new Blob([codes.join('\\n')],{type:'text/plain'}); const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='yazklinik-2fa-backup-codes.txt'; a.click(); setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
</script></body></html>""")


# --- PHQ-9 ---
@agents_bp.route("/api/agents/phq9/score", methods=["POST"])
def api_phq9_score():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(phq9_mod, "phq9")
    if err: return err
    p = _payload()
    answers = p.get("answers") or []
    if isinstance(answers, str):
        answers = [int(x) for x in answers.replace(",", " ").split()]
    return _wrap_call("phq9_score", phq9_mod.score,
                       {"patient_id": p.get("patient_id", ""), "answers": answers})


@agents_bp.route("/api/agents/phq9/questionnaire", methods=["GET"])
def api_phq9_questionnaire():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(phq9_mod, "phq9")
    if err: return err
    return jsonify({"ok": True, "result": phq9_mod.get_questionnaire()})


# --- Stok ---
@agents_bp.route("/api/agents/stok/report", methods=["GET"])
def api_stok_report():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(stok_mod, "stok")
    if err: return err
    return _wrap_call("stok_report", stok_mod.generate_report, {})


@agents_bp.route("/api/agents/stok/upsert", methods=["POST"])
def api_stok_upsert():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(stok_mod, "stok")
    if err: return err
    p = _payload()
    try:
        from yazklinik_stok_agent import StockItem
        item = StockItem(**{k: v for k, v in p.items()
                             if k in StockItem.__dataclass_fields__})
        ok = stok_mod.upsert_item(item)
        return jsonify({"ok": True, "result": {"upserted": ok}})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@agents_bp.route("/api/agents/stok/movement", methods=["POST"])
def api_stok_movement():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(stok_mod, "stok")
    if err: return err
    p = _payload()
    ok = stok_mod.record_movement(
        code=p.get("code", ""), direction=p.get("direction", "out"),
        quantity=int(p.get("quantity", 1)), note=p.get("note", ""))
    return jsonify({"ok": True, "result": {"recorded": ok}})


@agents_bp.route("/stok", methods=["GET"])
def stok_page():
    auth = _require_session()
    if auth:
        return auth
    return render_template_string(r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Stok - YazKlinik</title>
<style>
body{font-family:-apple-system,Segoe UI,Arial,sans-serif;background:#eef5fb;color:#13243a;margin:0;padding:22px}
.shell{max-width:1180px;margin:0 auto}.top{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
h1{margin:0;color:#15395c}.grid{display:grid;grid-template-columns:1.2fr .8fr;gap:14px;margin-top:16px}.card{background:#fff;border:1px solid #cbddeb;border-radius:12px;padding:16px;box-shadow:0 14px 32px rgba(21,69,105,.08)}
@media(max-width:900px){.grid{grid-template-columns:1fr}}label{display:block;font-size:12px;font-weight:800;color:#415873;margin-top:8px}
input,select{width:100%;box-sizing:border-box;border:1px solid #bfd0df;border-radius:9px;padding:9px;font:inherit}button,.btn{border:0;background:#1769aa;color:white;border-radius:9px;padding:9px 12px;font-weight:800;cursor:pointer;text-decoration:none}
button.secondary{background:#edf4fa;color:#17324a;border:1px solid #c4d7e8}table{width:100%;border-collapse:collapse;margin-top:10px}th,td{padding:9px;border-bottom:1px solid #e6eef5;text-align:left;font-size:13px}th{background:#f3f8fc}
.alerts{display:grid;gap:8px}.alert{border-radius:9px;padding:10px;background:#fff7ed;border:1px solid #fed7aa}.critical{background:#fef2f2;border-color:#fecaca}.muted{color:#66788c;font-size:13px}.ok{color:#15803d}.fail{color:#b42318}
.row{display:grid;grid-template-columns:1fr 1fr;gap:8px}.chart{display:grid;gap:6px;margin-top:10px}.bar{display:grid;grid-template-columns:120px 1fr 42px;gap:8px;align-items:center}.bar span:nth-child(2){height:10px;background:#dbeafe;border-radius:999px;overflow:hidden}.bar i{display:block;height:10px;background:#1769aa}
</style></head><body><main class="shell">
<div class="top"><div><h1>Stok Yonetimi</h1><p class="muted">Ilac ve sarf stoklari, miat ve azalan uyarilari.</p></div><a class="btn" href="/ajanlar">Ajanlara don</a></div>
<div class="grid">
<section class="card"><h2>Stok raporu</h2><div id="summary" class="muted">Yukleniyor...</div><div id="alerts" class="alerts"></div><table><thead><tr><th>Kod</th><th>Ad</th><th>Kategori</th><th>Adet</th><th>Esik</th><th>Miat</th></tr></thead><tbody id="items"></tbody></table><h3>Aylik tuketim</h3><div id="chart" class="chart"></div></section>
<section class="card"><h2>Yeni urun / guncelle</h2><label>Kod</label><input id="code" value="OXY-10IU"><label>Ad</label><input id="name" value="Oxytocin 10IU ampul"><div class="row"><div><label>Kategori</label><select id="category"><option>ilac</option><option>sarf</option><option>cihaz</option><option>egitim</option></select></div><div><label>Adet</label><input id="qty" type="number" value="4"></div></div><div class="row"><div><label>Esik</label><input id="threshold" type="number" value="5"></div><div><label>Miat</label><input id="expiry" type="date"></div></div><label>Tedarikci</label><input id="supplier" value="Klinik tedarikci"><label>Birim maliyet</label><input id="cost" type="number" step="0.01" value="45"><button style="margin-top:12px" onclick="saveItem()">Urunu kaydet</button><hr><h2>Hareket kaydet</h2><div class="row"><div><label>Yon</label><select id="direction"><option value="out">Cikis</option><option value="in">Giris</option></select></div><div><label>Adet</label><input id="moveQty" type="number" value="1"></div></div><label>Not</label><input id="note" value="Muayene kullanimi"><button class="secondary" style="margin-top:12px" onclick="saveMovement()">Hareket kaydet</button><div id="msg" class="muted" style="margin-top:10px"></div></section>
</div></main><script>
function esc(s){return String(s==null?'':s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
async function api(url, body){const opt={credentials:'same-origin',headers:{'Accept':'application/json'}}; if(body!==undefined){opt.method='POST';opt.headers['Content-Type']='application/json';opt.body=JSON.stringify(body);} const r=await fetch(url,opt); const d=await r.json(); if(!r.ok||!d.ok) throw new Error((d&&d.error)||r.status); return d.result||d;}
async function loadReport(){try{const r=await api('/api/agents/stok/report'); document.getElementById('summary').textContent='Kalem: '+r.total_items+' | Deger: '+r.total_value_try+' TRY | '+r.generated_at; document.getElementById('alerts').innerHTML=(r.alerts||[]).map(a=>'<div class="alert '+(a.severity==='critical'?'critical':'')+'"><b>'+esc(a.item_name)+'</b><br>'+esc(a.message)+'<br><small>'+esc(a.suggested_action)+'</small></div>').join('') || '<p class="ok">Aktif stok uyarisi yok.</p>'; document.getElementById('items').innerHTML=(r.items||[]).map(i=>'<tr><td>'+esc(i.code)+'</td><td>'+esc(i.name)+'</td><td>'+esc(i.category)+'</td><td>'+esc(i.quantity_on_hand)+'</td><td>'+esc(i.reorder_threshold)+'</td><td>'+esc(i.expiry_date)+'</td></tr>').join('') || '<tr><td colspan="6" class="muted">Kayitli stok yok.</td></tr>'; const cons=r.monthly_consumption_estimate||{}; const max=Math.max(1,...Object.values(cons)); document.getElementById('chart').innerHTML=Object.entries(cons).map(([k,v])=>'<div class="bar"><b>'+esc(k)+'</b><span><i style="width:'+(v/max*100)+'%"></i></span><em>'+v+'</em></div>').join('') || '<p class="muted">Son 30 gunde cikis yok.</p>'; }catch(e){document.getElementById('summary').innerHTML='<span class="fail">'+e.message+'</span>';}}
function formItem(){return {code:code.value,name:name.value,category:category.value,quantity_on_hand:Number(qty.value||0),reorder_threshold:Number(threshold.value||0),expiry_date:expiry.value,supplier:supplier.value,cost_per_unit:Number(cost.value||0)}}
async function saveItem(){const m=document.getElementById('msg'); try{await api('/api/agents/stok/upsert',formItem()); m.innerHTML='<span class="ok">Urun kaydedildi.</span>'; loadReport();}catch(e){m.innerHTML='<span class="fail">'+e.message+'</span>';}}
async function saveMovement(){const m=document.getElementById('msg'); try{await api('/api/agents/stok/movement',{code:code.value,direction:direction.value,quantity:Number(moveQty.value||1),note:note.value}); m.innerHTML='<span class="ok">Hareket kaydedildi.</span>'; loadReport();}catch(e){m.innerHTML='<span class="fail">'+e.message+'</span>';}}
(function(){const d=new Date(); d.setDate(d.getDate()+20); expiry.value=d.toISOString().slice(0,10); loadReport();})();
</script></body></html>""")


# --- Konsey vaka sunum ---
@agents_bp.route("/api/agents/konsey/build", methods=["POST"])
def api_konsey_build():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(konsey_mod, "konsey")
    if err: return err
    p = _payload()
    try:
        from yazklinik_konsey_agent import ConseyVakaInput
        case = ConseyVakaInput(**{k: v for k, v in p.items()
                                   if k in ConseyVakaInput.__dataclass_fields__})
        sunum = konsey_mod.build_presentation(case, use_rag=bool(p.get("use_rag", True)))
        return jsonify({"ok": True, "result": asdict(sunum)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


# --- Payment ---
@agents_bp.route("/api/agents/payment/initiate", methods=["POST"])
def api_payment_initiate():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(payment_mod, "payment")
    if err: return err
    p = _payload()
    try:
        from yazklinik_payment_agent import PaymentRequest
        req = PaymentRequest(**{k: v for k, v in p.items()
                                 if k in PaymentRequest.__dataclass_fields__})
        out = payment_mod.initiate(req)
        return jsonify({"ok": True, "result": asdict(out)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@agents_bp.route("/api/agents/payment/webhook/<provider>", methods=["POST"])
def api_payment_webhook(provider):
    err = _agent_or_503(payment_mod, "payment")
    if err: return err
    # GUVENLIK: raw_body imza dogrulamasi icin gerekli (iyzico/stripe HMAC)
    raw_body = request.get_data() or b""
    sig = (request.headers.get("X-Signature")
            or request.headers.get("X-Iyzico-Signature")
            or request.headers.get("Stripe-Signature", ""))
    result = payment_mod.confirm_webhook(
        provider, request.get_json(silent=True) or {},
        signature=sig, raw_body=raw_body)
    if not result.get("ok"):
        return jsonify(result), 401
    return jsonify({"ok": True, "result": result})


@agents_bp.route("/api/agents/payment/recent", methods=["GET"])
def api_payment_recent():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(payment_mod, "payment")
    if err: return err
    return jsonify({"ok": True, "result": payment_mod.list_recent(limit=50)})


# --- Health/info for stubs (e-Nabiz, MHRS, Medula, Duzen, IoT) ---
@agents_bp.route("/api/agents/enabiz/health", methods=["GET"])
def api_enabiz_health():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(enabiz_mod, "enabiz")
    if err: return err
    return jsonify({"ok": True, "result": enabiz_mod.health_check()})


@agents_bp.route("/api/agents/mhrs/health", methods=["GET"])
def api_mhrs_health():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(mhrs_mod, "mhrs")
    if err: return err
    return jsonify({"ok": True, "result": mhrs_mod.health_check()})


@agents_bp.route("/api/agents/medula/health", methods=["GET"])
def api_medula_health():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(medula_mod, "medula")
    if err: return err
    return jsonify({"ok": True, "result": medula_mod.health_check()})


@agents_bp.route("/api/agents/medula/provizyon", methods=["POST"])
def api_medula_provizyon():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(medula_mod, "medula")
    if err: return err
    p = _payload()
    out = medula_mod.query_provizyon(p.get("tc", ""))
    return jsonify({"ok": True, "result": asdict(out)})


@agents_bp.route("/api/agents/lab-duzen/health", methods=["GET"])
def api_lab_duzen_health():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(lab_duzen_mod, "lab_duzen")
    if err: return err
    return jsonify({"ok": True, "result": lab_duzen_mod.health_check()})


@agents_bp.route("/api/agents/lab-duzen/fetch", methods=["POST"])
def api_lab_duzen_fetch():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(lab_duzen_mod, "lab_duzen")
    if err: return err
    p = _payload()
    out = lab_duzen_mod.fetch_results(p.get("patient_tc", ""))
    return jsonify({"ok": True, "result": asdict(out)})


@agents_bp.route("/api/agents/iot/scan", methods=["POST"])
def api_iot_scan():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(iot_mod, "iot_bluetooth")
    if err: return err
    p = _payload()
    out = iot_mod.scan_for_devices(int(p.get("timeout_sec", 5)))
    return jsonify({"ok": True, "result": asdict(out)})


# --- Plugin loader ---
@agents_bp.route("/api/agents/plugins/list", methods=["GET"])
def api_plugins_list():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(plugin_mod, "plugin_loader")
    if err: return err
    plugin_mod.scan_and_load()
    return jsonify({"ok": True, "result": plugin_mod.list_plugins()})


@agents_bp.route("/api/agents/plugins/call", methods=["POST"])
def api_plugins_call():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(plugin_mod, "plugin_loader")
    if err: return err
    p = _payload()
    return jsonify({"ok": True,
                     "result": plugin_mod.call_plugin(
                         p.get("plugin", ""), p.get("func", ""),
                         *p.get("args", []), **p.get("kwargs", {}))})


# --- Smear/HPV takip ---
@agents_bp.route("/api/agents/smear-hpv/followup", methods=["POST"])
def api_smear_followup():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(smear_mod, "smear_hpv")
    if err: return err
    p = _payload()
    try:
        from datetime import date as _date
        from yazklinik_smear_hpv_agent import SmearRecord
        payload = {k: v for k, v in p.items() if k in SmearRecord.__dataclass_fields__}
        if not payload.get("smear_date"):
            payload["smear_date"] = _date.today().isoformat()
        if not payload.get("hpv_test") and p.get("hpv_result"):
            payload["hpv_test"] = p.get("hpv_result")
        if "smear_result" in payload and payload.get("smear_result") is not None:
            payload["smear_result"] = str(payload.get("smear_result") or "").strip()
        if not payload.get("smear_result"):
            return jsonify({"ok": False, "error": "smear_result gerekli"}), 400
        rec = SmearRecord(**payload)
        plan = smear_mod.compute_followup(rec)
        return jsonify({"ok": True, "result": asdict(plan)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 400


# --- Memnuniyet + dogum gunu ---
@agents_bp.route("/api/agents/memnuniyet/survey-yesterday", methods=["POST"])
def api_memnuniyet_survey():
    auth = _require_session_or_cron()
    if auth: return auth
    err = _agent_or_503(memnuniyet_mod, "memnuniyet")
    if err: return err
    p = _payload()
    return _wrap_call("memnuniyet_survey", memnuniyet_mod.send_survey_for_yesterday,
                      {"dry_run": _as_bool(p.get("dry_run"))})


@agents_bp.route("/api/agents/memnuniyet/birthday-today", methods=["POST"])
def api_birthday_today():
    auth = _require_session_or_cron()
    if auth: return auth
    err = _agent_or_503(memnuniyet_mod, "memnuniyet")
    if err: return err
    p = _payload()
    return _wrap_call("birthday_today", memnuniyet_mod.send_birthday_today,
                      {"dry_run": _as_bool(p.get("dry_run"))})


# --- PubMed cron tarama (BG-JOB: sayfa terkedilse de devam eder) ---
@agents_bp.route("/api/agents/pubmed-cron/scan", methods=["POST"])
def api_pubmed_cron_scan():
    auth = _require_session_or_cron()
    if auth: return auth
    err = _agent_or_503(pubmed_cron_mod, "pubmed_cron")
    if err: return err
    p = _payload()
    user_key = str(session.get("user") or session.get("username") or "doktor")
    kwargs = {
        "queries": p.get("queries"),
        "max_per_query": int(p.get("max_per_query", 3)),
        "send_to_doctor": bool(p.get("send_to_doctor", True)),
    }
    # Sync modu istenirse (cron'dan vb): legacy davranis
    if str(p.get("sync") or "").lower() in ("1", "true", "yes"):
        return _wrap_call("pubmed_cron_scan", pubmed_cron_mod.scan, kwargs)
    # Default: bg-job
    job_id = _bg_start_job("pubmed_scan", pubmed_cron_mod.scan,
                           user_key=user_key, **kwargs)
    return jsonify({"ok": True, "job_id": job_id, "status": "started",
                    "message": "PubMed scan arka planda - sayfa terkedilebilir"})


@agents_bp.route("/api/agents/pubmed-cron/status", methods=["GET"])
def api_pubmed_cron_status():
    auth = _require_session()
    if auth: return auth
    job_id = (request.args.get("job_id") or "").strip()
    if not job_id:
        return jsonify({"ok": False, "error": "job_id missing"}), 400
    job = _bg_get_job(job_id)
    if not job:
        return jsonify({"ok": False, "error": "job not found"}), 404
    return jsonify({"ok": True, "job": job})


@agents_bp.route("/api/agents/pubmed-cron/last", methods=["GET"])
def api_pubmed_cron_last():
    auth = _require_session()
    if auth: return auth
    user_key = str(session.get("user") or session.get("username") or "doktor")
    job = _bg_get_last_job(user_key, "pubmed_scan")
    return jsonify({"ok": True, "job": job})


@agents_bp.route("/pubmed-tarama", methods=["GET"])
def pubmed_tarama_page():
    """PubMed scan UI - arka planda calisir, sayfa terkedilebilir."""
    auth = _require_session()
    if auth: return auth
    return render_template_string(_PUBMED_TARAMA_PAGE)


# --- Tum BG-JOBS canli durum (her sayfada gosterilebilir) ---
_BG_JOB_TYPES = {
    "ig_scan":      {"label": "Instagram tarama",   "url": "/instagram-hazirla", "icon": "IG"},
    "nas_sync":     {"label": "NAS senkronizasyon", "url": "/nas-senkronizasyon", "icon": "NAS"},
    "rag_reindex":  {"label": "RAG reindex",        "url": "/alex-rag-merkezi",   "icon": "RAG"},
    "pubmed_scan":  {"label": "PubMed tarama",      "url": "/pubmed-tarama",       "icon": "PMD"},
}


@agents_bp.route("/api/bg-jobs/active", methods=["GET"])
def api_bg_jobs_active():
    """Tum aktif (running/pending) joblari listele - global widget icin."""
    auth = _require_session()
    if auth: return auth
    user_key = str(session.get("user") or session.get("username") or "doktor")
    out = []
    with _bg_lock():
        for jid, j in list(_BACKGROUND_JOBS.items()):
            if not isinstance(j, dict):
                continue
            if j.get("user_key") != user_key:
                continue
            if j.get("status") not in ("running", "pending"):
                continue
            jt = j.get("type", "")
            meta = _BG_JOB_TYPES.get(jt, {"label": jt, "url": "#", "icon": "?"})
            out.append({
                "id": jid, "type": jt,
                "status": j.get("status"),
                "label": meta["label"], "url": meta["url"], "icon": meta["icon"],
                "started_at": j.get("started_at"),
                "progress": j.get("progress", 0),
            })
    out.sort(key=lambda x: x.get("started_at") or 0, reverse=True)
    return jsonify({"ok": True, "active": out, "count": len(out)})


@agents_bp.route("/api/bg-jobs/all", methods=["GET"])
def api_bg_jobs_all():
    """Tum joblari (running + done + failed) listele - calisan-isler sayfasi icin."""
    auth = _require_session()
    if auth: return auth
    user_key = str(session.get("user") or session.get("username") or "doktor")
    out = []
    with _bg_lock():
        for jid, j in list(_BACKGROUND_JOBS.items()):
            if not isinstance(j, dict):
                continue
            if j.get("user_key") != user_key:
                continue
            jt = j.get("type", "")
            meta = _BG_JOB_TYPES.get(jt, {"label": jt, "url": "#", "icon": "?"})
            out.append({
                "id": jid, "type": jt,
                "status": j.get("status"),
                "label": meta["label"], "url": meta["url"], "icon": meta["icon"],
                "started_at": j.get("started_at"),
                "completed_at": j.get("completed_at"),
                "error": j.get("error"),
            })
    out.sort(key=lambda x: x.get("started_at") or 0, reverse=True)
    return jsonify({"ok": True, "jobs": out[:50], "count": len(out)})


@agents_bp.route("/calisan-isler", methods=["GET"])
def calisan_isler_page():
    """Tum BG-jobs canli panel - aktif + tamamlanan + hata listesi."""
    auth = _require_session()
    if auth: return auth
    return render_template_string(_CALISAN_ISLER_PAGE)


_CALISAN_ISLER_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Calisan Isler (BG-Jobs)</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:900px;margin:0 auto;padding:18px;background:#f5f8fb;color:#122236}
h1{color:#0d4f8b;margin-bottom:6px}
.sub{color:#5e7185;margin-bottom:18px;font-size:14px}
.card{background:#fff;border:1px solid #cdd9e3;border-radius:12px;padding:14px;margin-bottom:10px;box-shadow:0 2px 8px rgba(0,0,0,0.04);display:flex;align-items:center;gap:12px}
.icon{width:48px;height:48px;border-radius:12px;background:linear-gradient(135deg,#1769aa,#0a8a76);color:#fff;display:flex;align-items:center;justify-content:center;font-weight:800;font-size:13px}
.info{flex:1;min-width:0}
.title{font-weight:700;color:#0d4f8b}
.meta{font-size:12px;color:#5e7185;margin-top:2px}
.status{padding:4px 10px;border-radius:12px;font-size:12px;font-weight:700;white-space:nowrap}
.s-running{background:#fef3c7;color:#92400e}
.s-pending{background:#fef3c7;color:#92400e}
.s-done{background:#dcfce7;color:#166534}
.s-failed{background:#fee2e2;color:#b3261e}
.btn{background:#1769aa;color:#fff;padding:8px 14px;border-radius:6px;text-decoration:none;font-size:13px;font-weight:600;display:inline-block}
.empty{text-align:center;color:#5e7185;padding:40px;background:#fff;border-radius:12px;border:1px dashed #cdd9e3}
.spinner{display:inline-block;width:12px;height:12px;border:2px solid #f0a92b;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;margin-right:4px;vertical-align:middle}
@keyframes spin{to{transform:rotate(360deg)}}
</style></head><body>
<h1>Calisan Isler (BG-Jobs)</h1>
<div class="sub">Arka planda calisan tum islerin canli durumu. Sayfa otomatik yenilenir (5sn).</div>

<div style="margin-bottom:14px;font-size:13px">
  <a href="/" class="btn" style="background:#5e7185">&lt;- Ana sayfa</a>
  <span id="lastUpdate" style="color:#5e7185;margin-left:10px"></span>
</div>

<h3 style="margin-top:18px;color:#0d4f8b">Aktif (calisiyor)</h3>
<div id="activeList"></div>

<h3 style="margin-top:24px;color:#0d4f8b">Son Tamamlananlar / Hatalar</h3>
<div id="doneList"></div>

<p style="margin-top:24px;font-size:12px;color:#5e7185">
  Joblar 1 saat sonra otomatik silinir. Sunucu restart edilirse de silinir (in-memory).
</p>

<script>
function esc(s){return String(s||'').replace(/[<>&"]/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;",'"':"&quot;"})[c]);}
function fmtTime(ts) {
  if (!ts) return '-';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('tr-TR', {hour:'2-digit', minute:'2-digit', second:'2-digit'}) +
    ' (' + d.toLocaleDateString('tr-TR') + ')';
}
function fmtDur(start, end) {
  if (!start) return '-';
  const e = end || (Date.now()/1000);
  const sec = Math.round(e - start);
  if (sec < 60) return sec + ' sn';
  if (sec < 3600) return Math.floor(sec/60) + ' dk ' + (sec%60) + ' sn';
  return Math.floor(sec/3600) + ' sa ' + Math.floor((sec%3600)/60) + ' dk';
}
function renderJob(j) {
  const statusClass = 's-' + j.status;
  const isActive = (j.status === 'running' || j.status === 'pending');
  return '<div class="card">' +
    '<div class="icon">' + esc(j.icon) + '</div>' +
    '<div class="info">' +
      '<div class="title">' + esc(j.label) + '</div>' +
      '<div class="meta">' +
        'Basladi: ' + fmtTime(j.started_at) + ' &middot; Sure: ' + fmtDur(j.started_at, j.completed_at) +
        (j.error ? '<br><span style="color:#b3261e">Hata: ' + esc(j.error) + '</span>' : '') +
      '</div>' +
    '</div>' +
    '<span class="status ' + statusClass + '">' +
      (isActive ? '<span class="spinner"></span>' : '') + esc(j.status.toUpperCase()) +
    '</span>' +
    '<a href="' + esc(j.url) + '" class="btn">Sayfaya Git</a>' +
  '</div>';
}
async function refresh() {
  try {
    const r = await fetch('/api/bg-jobs/all?_t=' + Date.now(), {credentials:'same-origin'});
    const j = await r.json();
    if (!j.ok) return;
    const active = (j.jobs || []).filter(x => x.status === 'running' || x.status === 'pending');
    const done = (j.jobs || []).filter(x => x.status === 'done' || x.status === 'failed').slice(0, 20);
    const activeBox = document.getElementById('activeList');
    const doneBox = document.getElementById('doneList');
    activeBox.innerHTML = active.length ?
      active.map(renderJob).join('') :
      '<div class="empty">Su anda aktif is yok</div>';
    doneBox.innerHTML = done.length ?
      done.map(renderJob).join('') :
      '<div class="empty">Henuz tamamlanan is yok</div>';
    document.getElementById('lastUpdate').textContent = 'Son guncel: ' + new Date().toLocaleTimeString('tr-TR');
  } catch(e) { console.warn(e); }
}
refresh();
setInterval(refresh, 5000);
</script></body></html>
"""


_PUBMED_TARAMA_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>PubMed Tarama</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{font-family:-apple-system,Segoe UI,sans-serif;max-width:900px;margin:0 auto;padding:18px;background:#f5f8fb;color:#122236}
h1{color:#0d4f8b;margin-bottom:6px}
.sub{color:#5e7185;margin-bottom:18px;font-size:14px}
.card{background:#fff;border:1px solid #cdd9e3;border-radius:12px;padding:18px;margin-bottom:14px;box-shadow:0 2px 8px rgba(0,0,0,0.04)}
.btn{background:#1769aa;color:#fff;border:none;padding:12px 22px;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer}
.btn:disabled{background:#94a3b8;cursor:not-allowed}
.btn-secondary{background:#5e7185}
input,select,textarea{padding:10px 12px;border:1px solid #cdd9e3;border-radius:6px;font-size:14px;width:100%;font-family:inherit}
label{display:block;font-size:12px;font-weight:600;color:#0d4f8b;margin-bottom:4px}
.row{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:10px}
.row > *{flex:1;min-width:200px}
.tip{background:#e2eef7;border-left:4px solid #1769aa;padding:10px 14px;border-radius:0 6px 6px 0;font-size:13px;color:#0d4f8b;margin-bottom:14px}
.banner-run{background:#fef3c7;border:1px solid #f0a92b;padding:14px;border-radius:10px;font-size:14px;margin-bottom:14px;display:none}
.banner-done{background:#dcfce7;border:1px solid #16815f;padding:14px;border-radius:10px;font-size:14px;margin-bottom:14px;display:none}
.banner-fail{background:#fee2e2;border:1px solid #b3261e;padding:14px;border-radius:10px;font-size:14px;margin-bottom:14px;display:none}
small{color:#5e7185}
.spinner{display:inline-block;width:14px;height:14px;border:2px solid #1769aa;border-top-color:transparent;border-radius:50%;animation:spin 0.8s linear infinite;margin-right:6px;vertical-align:middle}
@keyframes spin{to{transform:rotate(360deg)}}
</style></head><body>
<h1>PubMed Tarama</h1>
<div class="sub">Yeni makaleleri bul + Turkce ozet + RAG indekse ekle. <b>Arka planda calisir</b> - sayfayi terkedebilirsin, geri donunce sonuc burada bekler.</div>

<div class="tip">
  <b>Nasil calisir:</b> Tikla -> PubMed'e 8 hazir sorgu gonderilir (gebelik, jinekoloji, USG vb.). En son 24 saat makaleleri ceker, Ollama ile Turkce ozetler, RAG vektor DB'sine indeksler. 1-3 dakika surer.
</div>

<div id="banner-run" class="banner-run">
  <span class="spinner"></span><b>Arka planda calisiyor...</b> Sayfayi terkedebilirsin, geri donunce sonuc burada gozukur.
</div>
<div id="banner-done" class="banner-done"></div>
<div id="banner-fail" class="banner-fail"></div>

<div class="card">
  <h3 style="margin-top:0">Ayarlar</h3>
  <div class="row">
    <div>
      <label>Sorgu basina max makale</label>
      <input type="number" id="maxPer" value="3" min="1" max="20">
    </div>
    <div>
      <label>Doktora gonder</label>
      <select id="sendDoc">
        <option value="1" selected>Evet (WhatsApp ozeti)</option>
        <option value="0">Hayir (sadece indeksle)</option>
      </select>
    </div>
  </div>
  <div style="margin-top:8px">
    <label>Sorgular (bos = varsayilan 8 sorgu)</label>
    <textarea id="queries" rows="3" placeholder="Her satira bir sorgu (orn: preeclampsia 2026). Bos birakirsan default klinik sorgular kullanilir."></textarea>
  </div>
  <div style="margin-top:14px">
    <button class="btn" id="btnRun">PubMed Taramayi Baslat</button>
    <button class="btn btn-secondary" onclick="location.reload()">Sayfayi Yenile</button>
  </div>
</div>

<div class="card">
  <h3 style="margin-top:0">Sonuc</h3>
  <div id="result"><small>Henuz tarama yok</small></div>
</div>

<p style="margin-top:14px"><a href="/ajanlar">&lt;- Klinik Ajanlari</a> &middot; <a href="/calisan-isler">Tum Calisan Isler</a></p>

<script>
const btnRun = document.getElementById('btnRun');
const banRun = document.getElementById('banner-run');
const banDone = document.getElementById('banner-done');
const banFail = document.getElementById('banner-fail');
const resBox = document.getElementById('result');
let pollTimer = null;
function esc(s){return String(s||'').replace(/[<>&"]/g, c => ({"<":"&lt;",">":"&gt;","&":"&amp;",'"':"&quot;"})[c]);}
function showResult(r) {
  if (!r) { resBox.innerHTML = '<small>Sonuc bos</small>'; return; }
  let h = '<div style="font-size:13px">';
  if (r.scanned_count) h += '<b>Taranan:</b> ' + r.scanned_count + ' makale<br>';
  if (r.added_count) h += '<b>Eklenen:</b> ' + r.added_count + ' yeni<br>';
  if (r.queries) {
    h += '<b>Sorgular:</b><ul style="margin:6px 0 0 18px">';
    for (const q of (r.queries || [])) {
      h += '<li>' + esc(q.query || q) + ' (' + (q.count || 0) + ')</li>';
    }
    h += '</ul>';
  }
  if (r.errors && r.errors.length) {
    h += '<b style="color:#b3261e">Hatalar:</b><ul style="margin:6px 0 0 18px;color:#b3261e">';
    for (const e of r.errors) h += '<li>' + esc(e) + '</li>';
    h += '</ul>';
  }
  h += '</div>';
  resBox.innerHTML = h;
}
async function pollStatus(jobId) {
  try {
    const r = await fetch('/api/agents/pubmed-cron/status?job_id=' + encodeURIComponent(jobId) + '&_t=' + Date.now(),
      {credentials:'same-origin'});
    const j = await r.json();
    if (!j.ok || !j.job) return;
    if (j.job.status === 'done') {
      clearInterval(pollTimer);
      banRun.style.display = 'none';
      banDone.style.display = 'block';
      banDone.innerHTML = '<b>Tamamlandi.</b> Sonuclar asagida.';
      showResult(j.job.result);
      btnRun.disabled = false;
    } else if (j.job.status === 'failed') {
      clearInterval(pollTimer);
      banRun.style.display = 'none';
      banFail.style.display = 'block';
      banFail.innerHTML = '<b>Hata:</b> ' + esc(j.job.error || 'unknown');
      btnRun.disabled = false;
    }
  } catch(e) { console.warn('[PubMed] poll:', e); }
}
// Sayfaya geldiginde son jobu kontrol et
(async function checkLast() {
  try {
    const r = await fetch('/api/agents/pubmed-cron/last?_t=' + Date.now(), {credentials:'same-origin'});
    const j = await r.json();
    if (j.ok && j.job) {
      if (j.job.status === 'running' || j.job.status === 'pending') {
        banRun.style.display = 'block';
        btnRun.disabled = true;
        pollTimer = setInterval(() => pollStatus(j.job.id), 3000);
      } else if (j.job.status === 'done') {
        banDone.style.display = 'block';
        banDone.innerHTML = '<b>Son tamamlanan tarama.</b>';
        showResult(j.job.result);
      } else if (j.job.status === 'failed') {
        banFail.style.display = 'block';
        banFail.innerHTML = '<b>Son tarama hata verdi:</b> ' + esc(j.job.error || 'unknown');
      }
    }
  } catch(e) {}
})();
btnRun.addEventListener('click', async () => {
  banDone.style.display = 'none';
  banFail.style.display = 'none';
  banRun.style.display = 'block';
  btnRun.disabled = true;
  resBox.innerHTML = '<small><span class="spinner"></span>Tarama baslatiliyor...</small>';
  try {
    const queries = (document.getElementById('queries').value || '').trim()
      .split('\n').map(s => s.trim()).filter(Boolean);
    const payload = {
      max_per_query: parseInt(document.getElementById('maxPer').value) || 3,
      send_to_doctor: document.getElementById('sendDoc').value === '1',
    };
    if (queries.length) payload.queries = queries;
    const r = await fetch('/api/agents/pubmed-cron/scan', {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload)
    });
    const j = await r.json();
    if (j.ok && j.job_id) {
      if (pollTimer) clearInterval(pollTimer);
      pollTimer = setInterval(() => pollStatus(j.job_id), 3000);
    } else {
      banRun.style.display = 'none';
      banFail.style.display = 'block';
      banFail.innerHTML = '<b>Hata:</b> ' + esc(j.error || 'baslatilamadi');
      btnRun.disabled = false;
    }
  } catch(e) {
    banRun.style.display = 'none';
    banFail.style.display = 'block';
    banFail.innerHTML = '<b>Hata:</b> ' + esc(e.message);
    btnRun.disabled = false;
  }
});
</script></body></html>
"""


# --- Compliance dashboard ---
@agents_bp.route("/api/agents/compliance/run", methods=["GET", "POST"])
def api_compliance_run():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(compliance_mod, "compliance")
    if err: return err
    return _wrap_call("compliance", compliance_mod.run_checks, {})


@agents_bp.route("/api/agents/compliance/readiness", methods=["GET", "POST"])
def api_compliance_readiness():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(compliance_mod, "compliance")
    if err:
        return err
    payload = _payload()
    db_path = (payload.get("db_path") or os.environ.get("YAZKLINIK_DB_PATH") or None)
    try:
        result = compliance_mod.run_readiness(db_path=db_path)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "agent": "compliance",
            "error": "readiness_failure",
            "detail": f"{type(exc).__name__}: {exc}",
        }), 500
    return jsonify({"ok": True, "agent": "compliance", "result": result})


@agents_bp.route("/uyumluluk", methods=["GET"])
def uyumluluk_page():
    auth = _require_session()
    if auth: return auth
    return render_template_string(_COMPLIANCE_PAGE)


@agents_bp.route("/mobil", methods=["GET"])
def mobil_dashboard():
    """iPhone 17 Pro Max / 6.9-inch ekran icin ozel dashboard.

    Tasarim:
        - 2x2 buyuk kart grid (ana islemler)
        - Bugunun ozeti band
        - Hizli komut: voice + arama
        - Alex bar altta sabit (zaten global)
    """
    auth = _require_session()
    if auth: return auth
    return render_template_string(_MOBIL_DASHBOARD_PAGE)


_MOBIL_DASHBOARD_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8">
<title>YazKlinik Mobil</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<meta name="theme-color" content="#0d4f8b">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="YazKlinik">
<link rel="apple-touch-icon" sizes="180x180" href="/static/icons/apple-touch-icon-180.png">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="stylesheet" href="/static/yk-ios-mobile.css?v=d700-ios-2026-05-17">
<style>
:root{
  --safe-top:env(safe-area-inset-top,0px);
  --safe-bottom:env(safe-area-inset-bottom,0px);
  --bg:#0d4f8b;
  --bg2:#0a8a76;
  --card:#ffffff;
  --ink:#122236;
  --muted:#5e7185;
  --accent:#ffd166;
}
*{box-sizing:border-box;margin:0;padding:0}
html,body{
  -webkit-text-size-adjust:100%;
  -webkit-tap-highlight-color:transparent;
  overscroll-behavior-y:contain;
}
body{
  font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif;
  background:linear-gradient(135deg,#0d4f8b 0%,#0a8a76 100%);
  color:#fff;
  min-height:100vh;min-height:100dvh;
  padding:calc(20px + var(--safe-top)) 16px calc(96px + var(--safe-bottom));
  display:flex;flex-direction:column;
}

/* Header */
.hdr{
  display:flex;align-items:center;justify-content:space-between;
  margin-bottom:16px;
}
.hdr-title{font-size:13px;opacity:.85;letter-spacing:1px;text-transform:uppercase}
.hdr-doctor{font-size:18px;font-weight:700;margin-top:2px}
.hdr-time{font-size:13px;opacity:.85;font-variant-numeric:tabular-nums}

/* Today stats - 3 column */
.stats3{
  display:grid;grid-template-columns:repeat(3,1fr);gap:8px;
  background:rgba(255,255,255,0.1);
  padding:14px;border-radius:14px;margin-bottom:18px;
  backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);
}
.s-n{font-size:24px;font-weight:800;line-height:1}
.s-l{font-size:11px;opacity:.8;margin-top:4px;text-transform:uppercase;letter-spacing:.5px}
.s-it{text-align:center}

/* Search bar */
.search{
  background:#fff;color:var(--ink);
  border-radius:14px;padding:14px 16px;font-size:16px;
  border:none;width:100%;margin-bottom:18px;
  box-shadow:0 4px 16px rgba(0,0,0,0.1);
  -webkit-appearance:none;
}
.search::placeholder{color:var(--muted)}

/* 2x2 action grid */
.grid2{
  display:grid;grid-template-columns:repeat(2,1fr);gap:12px;
  margin-bottom:18px;
}
.card{
  background:var(--card);color:var(--ink);
  border-radius:16px;padding:16px 14px;
  min-height:108px;
  display:flex;flex-direction:column;justify-content:space-between;
  text-decoration:none;
  box-shadow:0 4px 14px rgba(0,0,0,0.08);
  touch-action:manipulation;
  -webkit-user-select:none;user-select:none;
  transition:transform 0.15s ease;
}
.card:active{transform:scale(0.97)}
.card-ico{
  width:36px;height:36px;border-radius:10px;
  display:flex;align-items:center;justify-content:center;
  font-size:20px;font-weight:700;
}
.card-ttl{font-weight:700;font-size:15px;margin-top:8px}
.card-sub{font-size:11px;color:var(--muted);margin-top:2px}

/* Renkli card varyant */
.c-yeni .card-ico{background:#e2eef7;color:#0d4f8b}
.c-rand .card-ico{background:#d9f4ec;color:#0a8a76}
.c-recete .card-ico{background:#fde7f5;color:#a01e7e}
.c-usg .card-ico{background:#fff3c4;color:#b87300}
.c-konsult .card-ico{background:#e6e7ff;color:#4b1ea0}
.c-stok .card-ico{background:#ffe4e1;color:#b3261e}

/* Quick links footer */
.qlinks{
  display:flex;gap:8px;flex-wrap:wrap;
  margin-top:auto;
}
.qlink{
  flex:1;min-width:0;
  background:rgba(255,255,255,0.12);color:#fff;
  padding:10px 8px;border-radius:10px;text-align:center;
  text-decoration:none;font-size:12px;font-weight:600;
  backdrop-filter:blur(10px);-webkit-backdrop-filter:blur(10px);
  touch-action:manipulation;
}
.qlink:active{background:rgba(255,255,255,0.2)}

/* Voice button - prominent FAB */
.voice-fab{
  position:fixed;
  bottom:calc(20px + var(--safe-bottom));
  right:16px;
  width:60px;height:60px;border-radius:50%;
  background:linear-gradient(135deg,#ffd166 0%,#f39c12 100%);
  border:none;cursor:pointer;
  box-shadow:0 6px 20px rgba(255,209,102,0.4);
  display:flex;align-items:center;justify-content:center;
  font-size:24px;
  z-index:1000;
  touch-action:manipulation;
}
.voice-fab:active{transform:scale(0.92)}

/* iPhone 17 Pro Max 6.9" - 2 col bile genis, 3-col mumkun */
@media (min-device-width: 430px) {
  .grid2{gap:14px}
  .card{min-height:120px;padding:18px 16px}
  .card-ttl{font-size:16px}
}

/* iPad - 4 column */
@media (min-width: 768px) {
  body{padding:24px 28px;max-width:760px;margin:0 auto}
  .grid2{grid-template-columns:repeat(3,1fr)}
  .voice-fab{bottom:30px;right:30px;width:70px;height:70px}
}

/* Dynamic Island reserve top */
@media (display-mode: standalone) {
  body{padding-top:max(var(--safe-top),50px)}
}
</style></head><body>
<div class="hdr">
  <div>
    <div class="hdr-title">YazKlinik</div>
    <div class="hdr-doctor">Op. Dr. Hakan Yaz</div>
  </div>
  <div class="hdr-time" id="clock">--:--</div>
</div>

<div class="stats3">
  <div class="s-it"><div class="s-n" id="today-patients">-</div><div class="s-l">BugÃƒÂ¼n</div></div>
  <div class="s-it"><div class="s-n" id="upcoming">-</div><div class="s-l">SÃ„Â±radaki</div></div>
  <div class="s-it"><div class="s-n" id="msgs">-</div><div class="s-l">Mesaj</div></div>
</div>

<input class="search" type="search" inputmode="search"
       placeholder="Hasta ara (ad, telefon, dosya no)..."
       id="searchInput" autocomplete="off">

<div class="grid2">
  <a href="/yeni-hasta" class="card c-yeni">
    <div class="card-ico">+</div>
    <div>
      <div class="card-ttl">Yeni Hasta</div>
      <div class="card-sub">HÃ„Â±zlÃ„Â± kayÃ„Â±t</div>
    </div>
  </a>
  <a href="/randevular" class="card c-rand">
    <div class="card-ico">Ã¢â€”Â·</div>
    <div>
      <div class="card-ttl">Randevular</div>
      <div class="card-sub">BugÃƒÂ¼n ve yarÃ„Â±n</div>
    </div>
  </a>
  <a href="/yz-konsultasyon" class="card c-konsult">
    <div class="card-ico">Ã¢Ëœâ€¦</div>
    <div>
      <div class="card-ttl">YZ KonsÃƒÂ¼lt</div>
      <div class="card-sub">5 adÃ„Â±m analiz</div>
    </div>
  </a>
  <a href="/hasta/aktif/usg-rapor-taslak" class="card c-usg">
    <div class="card-ico">Ã¢â€”â€°</div>
    <div>
      <div class="card-ttl">USG Rapor</div>
      <div class="card-sub">Taslak + AI</div>
    </div>
  </a>
  <a href="/stok" class="card c-stok">
    <div class="card-ico">Ã¢â€“Â¤</div>
    <div>
      <div class="card-ttl">Stok</div>
      <div class="card-sub">Ã„Â°laÃƒÂ§ + miat</div>
    </div>
  </a>
  <a href="/ajanlar" class="card c-recete">
    <div class="card-ico">Ã¢Å¡Â¡</div>
    <div>
      <div class="card-ttl">TÃƒÂ¼m Ajanlar</div>
      <div class="card-sub">31 modÃƒÂ¼l</div>
    </div>
  </a>
</div>

<div class="qlinks">
  <a class="qlink" href="/dashboard">Panel</a>
  <a class="qlink" href="/uyumluluk">Uyumluluk</a>
  <a class="qlink" href="/status">Durum</a>
  <a class="qlink" href="/ceviri-merkezi">Ãƒâ€¡eviri</a>
</div>

<button class="voice-fab" id="voiceBtn" aria-label="Sesli komut">ÄŸÅ¸ÂÂ¤</button>

<script>
// Clock
function updateClock(){
  const now = new Date();
  document.getElementById('clock').textContent =
    String(now.getHours()).padStart(2,'0')+':'+String(now.getMinutes()).padStart(2,'0');
}
updateClock(); setInterval(updateClock, 30000);

// Today stats - fetch from API
async function loadStats(){
  try {
    const r = await fetch('/api/status', {credentials:'same-origin'});
    const d = await r.json();
    if (d.result) {
      document.getElementById('today-patients').textContent = d.result.db_visits_today || 0;
    }
  } catch(e) {}
}
loadStats();

// Search - enter ile randevulara git
document.getElementById('searchInput').addEventListener('keydown', e => {
  if (e.key === 'Enter') {
    const q = e.target.value.trim();
    if (q) window.location.href = '/hastalar?q=' + encodeURIComponent(q);
  }
});

// Voice button - Alex'i tetikle
document.getElementById('voiceBtn').addEventListener('click', () => {
  // Eger Alex global API varsa onu kullan
  if (window.ykVoiceAgent) {
    window.ykVoiceAgent.start({voice:true, focus:true});
  } else {
    // Yoksa Web Speech API
    if ('webkitSpeechRecognition' in window || 'SpeechRecognition' in window) {
      const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
      const rec = new SR();
      rec.lang = 'tr-TR';
      rec.start();
      rec.onresult = (ev) => {
        const text = ev.results[0][0].transcript;
        // Voice command'a yonlendir
        fetch('/api/agents/voice-command/parse', {
          method:'POST', headers:{'Content-Type':'application/json'},
          credentials:'same-origin',
          body: JSON.stringify({text: text})
        }).then(r=>r.json()).then(d=>{
          if (d.result && d.result.target && d.result.intent === 'navigate') {
            window.location.href = d.result.target;
          } else {
            alert('Anlasildi: ' + text);
          }
        });
      };
    } else {
      alert('Sesli komut bu tarayicida desteklenmiyor');
    }
  }
});

// PWA install hint (iOS)
if (window.matchMedia('(display-mode: standalone)').matches) {
  console.log('[YazKlinik] PWA mode aktif - tam ekran');
} else if (/iPhone|iPad|iPod/.test(navigator.userAgent)) {
  // Show "Add to Home Screen" hint after 5sec
  setTimeout(() => {
    if (!sessionStorage.getItem('yk_pwa_hint_shown')) {
      sessionStorage.setItem('yk_pwa_hint_shown', '1');
      // Subtle bottom toast olabilir; simdilik console
      console.log('[YazKlinik] Tip: Safari Paylas > Ana Ekrana Ekle');
    }
  }, 5000);
}
</script>
</body></html>"""


_COMPLIANCE_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8">
<title>ISO 27001 / KVKK Uyumluluk - YazKlinik</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1769aa">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="Uyumluluk">
<link rel="apple-touch-icon" sizes="180x180" href="/static/icons/apple-touch-icon-180.png">
<link rel="manifest" href="/manifest.webmanifest">
<link rel="stylesheet" href="/static/yk-ios-mobile.css?v=d700-ios-2026-05-17">
<style>
:root{--safe-top:env(safe-area-inset-top,0px);--safe-bottom:env(safe-area-inset-bottom,0px)}
*{box-sizing:border-box}
html,body{-webkit-text-size-adjust:100%;-webkit-tap-highlight-color:transparent;margin:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f8fb;color:#122236;
padding:calc(20px + var(--safe-top)) 18px calc(20px + var(--safe-bottom));max-width:1100px;margin:0 auto;
min-height:100vh;min-height:100dvh}
h1{margin:0 0 14px;color:#0f4c81;font-size:22px}
.banner{background:#fff;border:1px solid #cdd9e3;border-radius:14px;padding:18px;
margin-bottom:18px;display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.banner > div:first-child{min-width:120px}
.score-big{font-size:42px;font-weight:900;line-height:1}
.grade-A{color:#166534}.grade-B{color:#0f4c81}.grade-C{color:#92400e}
.grade-D,.grade-F{color:#991b1b}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #cdd9e3;
border-radius:10px;overflow:hidden;display:block;overflow-x:auto;-webkit-overflow-scrolling:touch}
th,td{padding:11px 10px;text-align:left;border-bottom:1px solid #eef3f8;font-size:13px;white-space:nowrap}
th{background:#eff5fb;font-weight:700;color:#0d4f8b;text-transform:uppercase;letter-spacing:.3px;font-size:11px}
.s-pass{color:#166534;font-weight:700}.s-fail{color:#991b1b;font-weight:700}
.s-warn{color:#92400e;font-weight:700}.s-unknown{color:#475569}
.recs{margin-top:18px;background:#fffbe5;border-left:4px solid #f0b400;padding:14px;border-radius:0 8px 8px 0}
button{background:#0f4c81;color:#fff;border:0;padding:12px 20px;border-radius:8px;
cursor:pointer;font-weight:700;min-height:44px;font-size:14px;touch-action:manipulation;-webkit-appearance:none}
button:active{background:#0d4f8b}
@media(max-width:600px){
  body{padding-left:12px;padding-right:12px}
  .banner{padding:14px;gap:12px}
  .score-big{font-size:36px}
  th,td{padding:9px 7px;font-size:12px}
  th{font-size:10px}
}
@media(display-mode:standalone){body{padding-top:calc(40px + var(--safe-top))}}
</style></head><body>
<h1>ISO 27001 + KVKK Uyumluluk Panosu</h1>
<div class="banner">
<div><div class="score-big" id="grade">?</div><div id="scoretxt">YÃƒÂ¼kleniyor...</div></div>
<div style="flex:1"><div id="criticalbox" style="font-size:14px;color:#b3261e"></div></div>
<button onclick="runCheck()">Yeniden Ãƒâ€¡alÃ„Â±Ã…Å¸tÃ„Â±r</button>
</div>
<table><thead><tr><th>Kod</th><th>Kontrol</th><th>Standart</th><th>Durum</th><th>Detay</th></tr></thead>
<tbody id="checks"></tbody></table>
<div class="recs" id="recs" style="display:none"></div>
<script>
async function runCheck(){
  const r = await fetch('/api/agents/compliance/run',{credentials:'same-origin'});
  const d = await r.json(); const res = d.result || d;
  document.getElementById('grade').textContent = res.grade;
  document.getElementById('grade').className = 'score-big grade-' + (res.grade||'?').replace('+','');
  document.getElementById('scoretxt').textContent =
    res.score + '/' + res.max_score + ' (' + res.pct + '%)';
  document.getElementById('criticalbox').textContent =
    res.critical_failures>0 ? ('KRÃ„Â°TÃ„Â°K: '+res.critical_failures+' ÃƒÂ¶nemli eksik') : 'Kritik eksik yok';
  const tb = document.getElementById('checks'); tb.innerHTML='';
  for(const c of res.checks){
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>'+c.code+'</td><td>'+c.title+'</td><td>'+c.standard+'</td>'+
      '<td class="s-'+c.status+'">'+c.status.toUpperCase()+'</td><td>'+c.detail+'</td>';
    tb.appendChild(tr);
  }
  if(res.recommendations_top && res.recommendations_top.length){
    document.getElementById('recs').style.display='block';
    document.getElementById('recs').innerHTML = '<b>Ã„Â°lk Ãƒâ€“neriler:</b><ul>'+
      res.recommendations_top.map(r=>'<li>'+r+'</li>').join('')+'</ul>';
  }
}
runCheck();
</script></body></html>"""


# --- Status page (PUBLIC - auth gerek YOK) ---
@agents_bp.route("/api/status", methods=["GET"])
def api_status_public():
    """PUBLIC - hastalar gorebilir."""
    if status_mod is None:
        return jsonify({"ok": False, "error": "status modul yuk olamadi"}), 503
    rpt = status_mod.build_report()
    return jsonify({"ok": True, "result": asdict(rpt)})


@agents_bp.route("/status", methods=["GET"])
def status_public_page():
    """PUBLIC HTML status sayfasi."""
    if status_mod is None:
        return "Status modul yuk olamadi", 503
    rpt = status_mod.build_report()
    return status_mod.render_html(rpt), 200, {"Content-Type": "text/html; charset=utf-8"}


# --- PWA: manifest + service worker (no auth) ---
@agents_bp.route("/manifest.webmanifest", methods=["GET"])
def pwa_manifest():
    return send_file(
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "static", "manifest.json"),
        mimetype="application/manifest+json")


@agents_bp.route("/sw.js", methods=["GET"])
def pwa_sw():
    """Service Worker - no-cache header sart, browser her zaman yeni versiyonu kontrol etsin."""
    resp = send_file(
        os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "static", "sw.js"),
        mimetype="application/javascript")
    # SW dosyasi browser tarafinda CACHE'lenmemeli (Chrome 24 saat ozel kural)
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    resp.headers["Service-Worker-Allowed"] = "/"
    return resp




