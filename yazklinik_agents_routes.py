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

import json
import os
import traceback
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, render_template_string, request, session, send_file, abort


agents_bp = Blueprint("agents", __name__)
_CRON_TOKEN = os.environ.get("YAZKLINIK_CRON_TOKEN", "").strip()


def _cron_auth_ok() -> bool:
    return bool(_CRON_TOKEN and request.headers.get("X-Cron-Token") == _CRON_TOKEN)


@agents_bp.after_request
def _agents_medical_theme(response):
    """Ajan sayfalarini ana D300 medikal tema ve kisa gecislerle goster."""
    try:
        if response.mimetype != "text/html" or response.direct_passthrough:
            return response
        html = response.get_data(as_text=True)
        if not html:
            return response
        if "yk-medical-theme-css" not in html:
            link = (
                '<link rel="stylesheet" '
                'href="/static/yk-medical-theme.css?v=d300-medical-2026-05-17-ui3" '
                'id="yk-medical-theme-css">'
            )
            if "</head>" in html:
                html = html.replace("</head>", link + "</head>", 1)
            else:
                html = link + html
        if "yk-agent-shortcuts" not in html:
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
                '<a href="/hasta-portal" style="background:#0a8a76;color:#fff">🔗 Hasta Portal</a>'
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
        from yazklinik_web import web_audit_log  # type: ignore
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


# --- Manifest + dashboard ---

@agents_bp.route("/api/agents", methods=["GET"])
def api_agents_manifest():
    auth = _require_session()
    if auth:
        return auth
    payload: Dict[str, Any] = {"ok": True, "import_errors": dict(_AGENT_IMPORT_ERRORS)}
    if _get_registry:
        try:
            payload["registry"] = _get_registry()
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
    return jsonify(payload)


_AGENTS_PAGE = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>Klinik Ajanları - YazKlinik</title>
<style>
  :root { --yk-ink:#172f49; --yk-muted:#58708a; --yk-line:#c9deed; --yk-surface:#ffffff; --yk-soft:#eef8fb; --yk-accent:#0b79b7; }
  body { font-family: -apple-system, Segoe UI, Arial, sans-serif; background: linear-gradient(135deg,#f4fbff 0%,#e9f7f5 100%); color: var(--yk-ink); margin: 0; padding: 24px; }
  h1 { margin: 0 0 16px; font-size: 24px; color:#102b45; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
  .card { background: var(--yk-surface); border: 1px solid var(--yk-line); border-radius: 10px; padding: 15px; box-shadow:0 10px 28px rgba(22,62,94,.08); }
  .card h3 { margin: 0 0 6px; font-size: 15px; color: #075c92; }
  .card p { margin: 0 0 8px; font-size: 13px; color: #314c68; line-height: 1.5; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; }
  .pill.ok { background: #16824a; color: #ffffff; }
  .pill.fail { background: #b42318; color: #ffffff; }
  .pill.warn { background: #b7791f; color: #ffffff; }
  code { background: #e8f2fa; color:#183650; padding: 1px 5px; border-radius: 4px; font-size: 11px; }
  .meta { font-size: 11px; color: var(--yk-muted); margin-top: 8px; }
  .row { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
  .btn { display: inline-block; padding: 7px 11px; background: #ffffff; border: 1px solid #a9c9df;
         border-radius: 8px; color: #15324d; text-decoration: none; font-size: 12px; cursor: pointer; font-weight:800; }
  .btn:hover { background: #eaf5fc; }
  pre { background: #f6fbff; color:#17324a; border:1px solid #cde0ee; padding: 10px; border-radius: 8px; font-size: 11px; max-height: 260px; overflow: auto; }
</style></head>
<body>
  <h1>Klinik Ajanları</h1>
  <p style="color:#58708a;font-size:13px;">Tüm ajanlar saf iş mantığı sunar; sonuçlar onay kuyruğunda doktoru bekler.
     <code>GET /api/agents</code> ile manifest, <code>POST /api/agents/&lt;id&gt;/run</code> ile calistir.</p>
  <div id="status"></div>
  <div class="grid" id="grid"></div>
  <h2 style="margin-top: 28px; font-size: 16px;">Manifest</h2>
  <pre id="raw">yukleniyor...</pre>

<script>
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
    return `
      <div class="card">
        <div class="row"><h3>${a.name}</h3>${pill}</div>
        <p>${a.short || ''}</p>
        <div class="meta">id: <code>${a.id}</code> | risk: ${a.risk || '-'} | durum: ${a.status || '-'}</div>
      </div>
    `;
  }).join('');
}
load();
</script>
</body></html>
"""

_SESSION7_AGENT_CARDS = [
    {"cat": "Klinik AI", "icon": "USG", "name": "USG Vision", "desc": "USG goruntusunu lokal vision model ile yorumlar.", "method": "POST", "url": "/api/agents/vision-usg/analyze", "payload": {"image_path": ""}},
    {"cat": "Klinik AI", "icon": "SOAP", "name": "SOAP Not", "desc": "Kisa klinik notu SOAP formatina genisletir.", "method": "POST", "url": "/api/agents/soap/expand", "payload": {"note": "Gebelik kontrolu, tansiyon normal, sikayet yok."}},
    {"cat": "Klinik AI", "icon": "ICD", "name": "ICD-10 Oneri", "desc": "Klinik nottan uygun ICD-10 kodlarini onerir.", "method": "POST", "url": "/api/agents/icd10/suggest", "payload": {"note": "Gebelikte hipertansiyon takibi", "top_k": 5}},
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
    {"cat": "Sistem", "icon": "VIS", "name": "Tam Muayene Orkestrator", "desc": "Klinik vaka metninden zincir calisma baslatir.", "method": "POST", "url": "/api/agents/orchestrator/full-visit", "payload": {"case_text": "28 yas, gebelik kontrolu, sikayet yok."}},
    {"cat": "Sistem", "icon": "PUB", "name": "PubMed Paket", "desc": "PubMed arastirma paketi ve ozet zinciri olusturur.", "method": "POST", "url": "/api/agents/orchestrator/pubmed-pack", "payload": {"query": "preeclampsia 2025 review", "max_articles": 2}},
    {"cat": "Sistem", "icon": "PIPE", "name": "USG Pipeline", "desc": "USG goruntu analizi ve hasta dosyasi zinciri icin hazir.", "method": "POST", "url": "/api/agents/orchestrator/usg-pipeline", "payload": {"image_path": "", "patient_key": "demo"}},
    {"cat": "Sistem", "icon": "PRT", "name": "Hasta Portal Link", "desc": "Hasta icin sureli magic-link uretir.", "method": "POST", "url": "/api/agents/portal/issue-link", "payload": {"patient_id": "demo", "phone": "05550000000"}},
    {"cat": "Sistem", "icon": "2FA", "name": "2FA Kurulum API", "desc": "Doktor kullanicisi icin TOTP kurulumu baslatir.", "method": "POST", "url": "/api/agents/2fa/setup", "payload": {}},
    {"cat": "Sistem", "icon": "STK", "name": "Stok Rapor", "desc": "Azalan ve miadi yaklasan stoklari listeler.", "method": "GET", "url": "/api/agents/stok/report", "payload": {}},
    {"cat": "Sistem", "icon": "PLG", "name": "Plugin Listesi", "desc": "Yerel plugin klasorlerini tarar ve listeler.", "method": "GET", "url": "/api/agents/plugins/list", "payload": {}},
    {"cat": "Compliance + Status", "icon": "KVK", "name": "Uyumluluk Kontrolu", "desc": "ISO/KVKK kontrol listesini ve notunu hesaplar.", "method": "GET", "url": "/api/agents/compliance/run", "payload": {}},
    {"cat": "Compliance + Status", "icon": "STS", "name": "Public Status", "desc": "Klinik servis durumunu JSON olarak verir.", "method": "GET", "url": "/api/status", "payload": {}},
    {"cat": "Compliance + Status", "icon": "PWA", "name": "Manifest", "desc": "PWA manifest dosyasini kontrol eder.", "method": "GET", "url": "/manifest.webmanifest", "payload": {}},
    {"cat": "Compliance + Status", "icon": "SW", "name": "Service Worker", "desc": "PWA service worker dosyasini kontrol eder.", "method": "GET", "url": "/sw.js", "payload": {}},
    {"cat": "Cron + Stub", "icon": "ANK", "name": "Memnuniyet Anketi", "desc": "Dunku hastalar icin anket gorevini baslatir.", "method": "POST", "url": "/api/agents/memnuniyet/survey-yesterday", "payload": {}},
    {"cat": "Cron + Stub", "icon": "BD", "name": "Dogum Gunu Tebrik", "desc": "Bugunku dogum gunu mesajlarini hazirlar.", "method": "POST", "url": "/api/agents/memnuniyet/birthday-today", "payload": {}},
    {"cat": "Cron + Stub", "icon": "PM", "name": "PubMed Cron", "desc": "Planli PubMed taramasini calistirir.", "method": "POST", "url": "/api/agents/pubmed-cron/scan", "payload": {"queries": ["preeclampsia"], "max_per_query": 1}},
    {"cat": "Cron + Stub", "icon": "PAY", "name": "Odeme Baslat", "desc": "Odeme saglayici stub akisina test istegi atar.", "method": "POST", "url": "/api/agents/payment/initiate", "payload": {"patient_id": "demo", "amount_try": 100, "description": "Demo islem"}},
    {"cat": "Cron + Stub", "icon": "ENB", "name": "e-Nabiz Health", "desc": "e-Nabiz/KTS entegrasyon durumunu okur.", "method": "GET", "url": "/api/agents/enabiz/health", "payload": {}},
    {"cat": "Cron + Stub", "icon": "MHR", "name": "MHRS Health", "desc": "MHRS entegrasyon saglik bilgisini okur.", "method": "GET", "url": "/api/agents/mhrs/health", "payload": {}},
    {"cat": "Cron + Stub", "icon": "MED", "name": "Medula Provizyon", "desc": "SGK provizyon stub sorgusunu calistirir.", "method": "POST", "url": "/api/agents/medula/provizyon", "payload": {"tc": "11111111110"}},
    {"cat": "Cron + Stub", "icon": "LAB", "name": "Lab Duzen", "desc": "Laboratuvar entegrasyon stub sonucunu getirir.", "method": "POST", "url": "/api/agents/lab-duzen/fetch", "payload": {"patient_tc": "11111111110"}},
    {"cat": "Cron + Stub", "icon": "IOT", "name": "IoT Bluetooth", "desc": "Bluetooth cihaz tarama stub akisina istek atar.", "method": "POST", "url": "/api/agents/iot/scan", "payload": {"timeout_sec": 2}},
]

_SESSION7_AGENT_ADDON = """
<style id="session7-agent-cards-css">
  .s7-head { margin: 26px 0 12px; display:flex; justify-content:space-between; gap:12px; align-items:end; flex-wrap:wrap; }
  .s7-head h2 { margin:0; font-size:18px; color:#102b45; }
  .s7-tabs { display:flex; gap:8px; flex-wrap:wrap; margin: 8px 0 16px; }
  .s7-tab { border:1px solid #bfd8e9; background:#ffffff; color:#17324a; border-radius:999px; padding:7px 11px; cursor:pointer; font-size:12px; font-weight:800; }
  .s7-tab.active { background:#0b79b7; border-color:#0b79b7; color:white; }
  .session7-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); gap:14px; }
  .agent-card { background:#ffffff; border:1px solid #c9deed; border-radius:10px; padding:14px; box-shadow:0 12px 28px rgba(20,68,103,.08); }
  .agent-card h3 { margin:0; font-size:15px; color:#075c92; }
  .agent-card p { min-height:36px; }
  .agent-ico { min-width:42px; height:32px; border-radius:9px; display:inline-flex; align-items:center; justify-content:center; background:#0b79b7; color:#fff; font-size:11px; font-weight:900; letter-spacing:.02em; }
  .agent-card-top { display:flex; align-items:center; gap:10px; margin-bottom:8px; }
  .agent-card-actions { display:flex; gap:8px; align-items:center; margin-top:10px; }
  .agent-run { padding:7px 11px; background:#16824a; color:white; border:0; border-radius:8px; cursor:pointer; font-weight:800; font-size:12px; }
  .agent-copy { padding:7px 9px; background:#f5fbff; color:#17324a; border:1px solid #bfd8e9; border-radius:8px; cursor:pointer; font-size:12px; }
  .agent-result { margin-top:10px; background:#f6fbff; border:1px solid #c9deed; border-radius:8px; padding:9px; min-height:42px; max-height:220px; overflow:auto; white-space:pre-wrap; font-size:11px; color:#17324a; }
  .agent-result.ok { border-color:#16824a; }
  .agent-result.fail { border-color:#b42318; color:#8a1f15; background:#fff7f6; }
</style>
<section id="session7-agents">
  <div class="s7-head">
    <div>
      <h2>Session 7 ajanları</h2>
      <p style="margin:4px 0 0;color:#58708a;font-size:13px;">29 yeni modülü kapsayan çalıştırılabilir aksiyon kartları.</p>
    </div>
    <a class="btn" href="/uyumluluk">Uyumluluk panosu</a>
  </div>
  <div class="s7-tabs" id="s7Tabs"></div>
  <div class="session7-grid" id="session7Grid"></div>
</section>
<script id="session7-agent-cards-js">
const SESSION7_AGENT_CARDS = __SESSION7_CARDS__;
let s7ActiveCat = 'Klinik AI';
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
    <div class="agent-card" data-cat="${s7Escape(c.cat)}">
      <div class="agent-card-top"><span class="agent-ico">${s7Escape(c.icon)}</span><h3>${s7Escape(c.name)}</h3></div>
      <p>${s7Escape(c.desc)}</p>
      <div class="meta"><code>${s7Escape(c.method)}</code> <code>${s7Escape(c.url)}</code></div>
      <div class="agent-card-actions">
        <button class="agent-run" onclick="s7RunCard(${SESSION7_AGENT_CARDS.indexOf(c)})">Calistir</button>
        <button class="agent-copy" onclick="navigator.clipboard && navigator.clipboard.writeText(JSON.stringify(SESSION7_AGENT_CARDS[${SESSION7_AGENT_CARDS.indexOf(c)}].payload,null,2))">Payload kopyala</button>
      </div>
      <pre class="agent-result" id="s7res-${SESSION7_AGENT_CARDS.indexOf(c)}">(bekliyor)</pre>
    </div>`).join('');
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
s7RenderTabs();
s7RenderCards();
</script>
"""

_AGENTS_PAGE = _AGENTS_PAGE.replace(
    '<h2 style="margin-top: 28px; font-size: 16px;">Manifest</h2>',
    _SESSION7_AGENT_ADDON.replace(
        "__SESSION7_CARDS__",
        json.dumps(_SESSION7_AGENT_CARDS, ensure_ascii=True)
    ) + '<h2 style="margin-top: 28px; font-size: 16px;">Manifest</h2>'
)


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


@agents_bp.route("/api/agents/instagram/scan", methods=["POST"])
def ig_scan():
    auth = _require_session()
    if auth:
        return auth
    err = _agent_or_503(instagram_mod, "instagram")
    if err:
        return err
    p = _payload()
    root = str(p.get("root") or _DEFAULT_VOLUSON_ROOT)
    max_candidates = int(p.get("max_candidates") or 60)
    include_pdf = bool(p.get("include_pdf", True))
    min_score = float(p.get("min_score") or 0.30)
    try:
        result = instagram_mod.scan_archive(
            root=root, max_candidates=max_candidates,
            include_pdf=include_pdf, min_score=min_score,
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "agent": "instagram", "error": "scan_failure",
                         "detail": f"{type(exc).__name__}: {exc}"}), 500
    _safe_audit("agents:instagram_scan", {"root": root, "count": result.get("count_returned", 0)})
    return jsonify({"ok": True, "agent": "instagram", "result": result})


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
    raw_path = str(p.get("source_path") or "")
    target = _allowed_image_root(raw_path)
    if not target:
        return jsonify({"ok": False, "agent": "instagram", "error": "path_not_allowed",
                         "detail": "Goruntu izinli root disinda."}), 403

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
      <button class="btn-primary" id="scanBtn" style="margin-top:10px;">Tara</button>
      <div class="status" id="scanStatus"></div>

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

async function scan() {
  const status = document.getElementById('scanStatus');
  status.textContent = 'Taraniyor...';
  status.className = 'status';
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
      })
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || res.status);
    state.candidates = data.result.candidates || [];
    state.scanRoot = data.result.root;
    renderCandidates();
    status.textContent = data.result.scanned_count + ' dosya tarandi, '
      + state.candidates.length + ' aday bulundu.';
    status.classList.add('ok');
  } catch (e) {
    status.textContent = 'Hata: ' + e.message;
    status.classList.add('fail');
  }
}

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
  status.textContent = 'aranıyor...'; status.className = 'status';
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
      <div class="meta">${h.year} · ${escapeHtml(h.journal)} · PMID ${h.pmid}</div>
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
          ${escapeHtml((a.authors||[]).slice(0,4).join(', '))} · ${escapeHtml(a.journal||'')} · ${a.year||''} · PMID ${a.pmid}
          ${a.doi ? ' · <a href="https://doi.org/' + a.doi + '" target="_blank">DOI</a>' : ''}
          · <a href="${a.pubmed_url}" target="_blank">PubMed</a>
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
    btn.textContent = '✓ kopyalandi';
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
  <p class="lead">5 adimli akilli zincir: vaka ayriklastir → kirmizi alarm + DDx → tetkik → tedavi → takip. Yerel Ollama (qwen2.5:32b) yi kullanir; OpenAI varsa fallback.
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
  html.push('<div class="case-card">' + meta.join(' · '));
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
        <div class="meta">${d.icd10 ? 'ICD-10: <code>'+escapeHtml(d.icd10)+'</code> · ' : ''}${d.next_step_to_confirm ? 'Dogrulamak icin: '+escapeHtml(d.next_step_to_confirm) : ''}</div>
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


# === D300 2026-05-17: Konsultasyon -> hasta dosyasina ekle + USG taslak sayfasi ===

@agents_bp.route("/api/agents/konsult/save-to-visit", methods=["POST"])
def konsult_save_to_visit():
    auth = _require_session()
    if auth:
        return auth
    p = _payload()
    patient_key = str(p.get("patient_key") or "").strip()
    markdown = str(p.get("markdown") or "").strip()
    most_likely = str(p.get("most_likely") or "")
    if not patient_key or not markdown:
        return jsonify({"ok": False, "error": "patient_key ve markdown gerekli"}), 400
    try:
        import sqlite3
        db_path = (os.environ.get("YAZKLINIK_DB_PATH")
                   or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")
        con = sqlite3.connect(db_path, timeout=10)
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
    return render_template_string(_USG_RAPOR_TASLAK_PAGE, patient_key=patient_key)


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


# === D300 2026-05-17: VeriDB endpointleri (Postgres + Redis + MeiliSearch) ===

postgres_mod = _safe_import("yazklinik_postgres_agent")
redis_mod = _safe_import("yazklinik_redis_agent")
meili_mod = _safe_import("yazklinik_meilisearch_agent")


@agents_bp.route("/api/db/postgres/health", methods=["GET"])
def api_pg_health():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(postgres_mod, "postgres")
    if err: return err
    return jsonify({"ok": True, "agent": "postgres",
                     "result": postgres_mod.health_check()})


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
  box.innerHTML = '<i>aranıyor...</i>';
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
    if not image_path:
        return jsonify({"ok": False, "error": "image_path gerekli"}), 400
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
    if not image:
        return jsonify({"ok": False, "error": "image_path gerekli"}), 400
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
    table = str.maketrans({
        "ğ": "g", "Ğ": "g",
        "ü": "u", "Ü": "u",
        "ş": "s", "Ş": "s",
        "ı": "i", "İ": "i",
        "ö": "o", "Ö": "o",
        "ç": "c", "Ç": "c",
        "â": "a", "Â": "a",
        "î": "i", "Î": "i",
        "û": "u", "Û": "u",
    })
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
    msg.textContent = '✓ Temizlik tamam. Yonlendiriliyor...';
    setTimeout(() => location.href = '/hasta-portal?fresh=' + Date.now(), 1500);
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
      1. Sorgu kelimelerini ASCII-fold (Ebru Erdoğan -> ebru erdogan)
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
            or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")
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
    con = sqlite3.connect(dbp)
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
    base_url = (p.get("base_url") or
                 (request.host_url.rstrip("/") if request.host_url else
                  "https://sam.turkey-orfe.ts.net"))
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

    Browser native form post -> server response HTML olarak donduğunde
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
    base_url = request.host_url.rstrip("/") if request.host_url else "https://sam.turkey-orfe.ts.net"

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
<h2>✓ Magic Link Uretildi</h2>
<p>WhatsApp 3 saniyede otomatik acilir...</p>
<div class="link">{link}</div>
<a class="btn" href="{wa_url}">📱 WhatsApp Şimdi Aç</a>
<a class="btn" href="/hasta-portal" style="background:#5e7185">← Portal Geri Dön</a>
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
<h2>✓ Magic Link Uretildi ({ttl} saat gecerli)</h2>
<div class="link">{link}</div>
<a class="btn" href="{link}" target="_blank" style="background:#1769aa;color:#fff">👁 Onizle (Yeni Sekme)</a>
<a class="btn" href="{wa_url}" target="_blank" style="background:#25d366;color:#fff">📱 WhatsApp Aç</a>
<a class="btn" href="/hasta-portal" style="background:#5e7185;color:#fff">← Portal Geri Dön</a>
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
                token=token, sig=sig, error="Bilgiler hatalı - tekrar deneyin")
        # Dogrulama OK - session set
        res = portal_mod.verify_token(token, mark_used=True)
        if res.ok:
            session["portal_patient_id"] = res.session.patient_id
            session["portal_token"] = token
            return _flask_redirect_obj("/hasta-portal")
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
                error="Geçersiz imza - link tamam değil"), 403
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
        return _flask_redirect_obj("/hasta-portal")
    return f"Hata: {res2.error}", 403


def _flask_redirect_obj(url):
    from flask import redirect as _redir
    return _redir(url)


_PORTAL_TC_FORM = r"""<!doctype html><html lang="tr"><head><meta charset="utf-8">
<title>Doğrulama - Hasta Portal</title>
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
<h1>🔐 Kimlik Doğrulama</h1>
<p>Sayın hastamız, kişisel sağlık verilerinize erişim için aşağıdaki bilgileri girin:</p>
<form method="POST" action="/hasta-portal/giris?token={{token|urlencode}}&sig={{sig|urlencode}}">
  <label>TC Kimlik No (son 4 hane)</label>
  <input type="tel" name="tc_last4" maxlength="4" pattern="[0-9]{4}" required
         placeholder="****" inputmode="numeric" autocomplete="off">
  <label>Doğum Yılı</label>
  <input type="tel" name="birth_year" maxlength="4" pattern="[0-9]{4}" required
         placeholder="YYYY" inputmode="numeric" autocomplete="off">
  {% if error %}<div class="err">⚠ {{error}}</div>{% endif %}
  <button type="submit">Devam Et →</button>
</form>
<div class="info">🔒 Bu bilgiler sadece kimliğinizi doğrulamak için kullanılır. Saklanmaz, paylaşılmaz.</div>
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
<h1>❌ Erişim Sağlanamadı</h1>
<p>{{error}}</p>
<p style="margin-top:14px;font-size:13px">Lütfen klinikten yeni link talep edin.</p>
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
                or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")
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
    if ext not in ("jpg", "jpeg", "png", "pdf"):
        return "izin verilmeyen tip", 403
    mime = {"jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "pdf": "application/pdf"}[ext]
    fname = _os.path.basename(rp)
    return send_file(rp, mimetype=mime,
                      as_attachment=download,
                      download_name=fname)


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
    allowed_ext = {".jpg", ".jpeg", ".png", ".pdf"}
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
def hasta_portal_home():
    """Dual-mode portal:
      - DOKTOR session varsa: yonetim paneli (link uret + son linkler)
      - HASTA portal session varsa: kendi ziyaret/recete listesi
      - Hicbiri yoksa: aciklama + giris linkleri
    """
    portal_pid = session.get("portal_patient_id")
    doktor_user = (session.get("user") or session.get("username"))

    # MOD 1: Hasta gormus magic-link ile gelmis
    if portal_pid:
        visits = []
        pdfs = []
        meds = []
        labs = []
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
        show_pdfs = scopes.get("show_pdfs", scopes.get("all", True))
        show_meds = scopes.get("show_meds", scopes.get("all", True))
        show_labs = scopes.get("show_labs", scopes.get("all", True))

        if portal_mod:
            try:
                all_visits = portal_mod.list_my_visits(portal_pid)
                # Filter by allowed visit_keys (eger doktor secti ise)
                if isinstance(allowed_visits, list) and allowed_visits:
                    # visits tablo visit_key ile select edildi; ama list_my_visits visit_key dondurmuyor
                    # Bu yuzden full_path veya visit_date+pdf_count match
                    # En basit: full_path match
                    visits = []
                    for v in all_visits:
                        if v.get("full_path") in allowed_visits or v.get("visit_date") in allowed_visits:
                            visits.append(v)
                else:
                    visits = all_visits
                for v in visits:
                    fp = v.get("full_path") or ""
                    try:
                        media = portal_mod.list_visit_images(fp, max_imgs=12)
                        v["visit_images"] = media.get("images", [])
                        v["visit_pdfs"] = media.get("pdfs", [])
                    except Exception:
                        v["visit_images"] = []
                        v["visit_pdfs"] = []
            except Exception:
                pass
            if show_pdfs:
                try: pdfs = portal_mod.list_my_pdfs(portal_pid)
                except Exception: pass
            if show_meds:
                try: meds = portal_mod.list_my_meds(portal_pid)
                except Exception: pass
            if show_labs:
                try: labs = portal_mod.list_my_labs(portal_pid)
                except Exception: pass
        return render_template_string(_PORTAL_HASTA_PAGE,
                                       visits=visits, pdfs=pdfs, meds=meds,
                                       labs=labs, custom_message=custom_message,
                                       pid=portal_pid)

    # MOD 2: Doktor login - yonetim paneli
    if doktor_user:
        # Son uretilen 20 token + hasta listesi
        recent_tokens = []
        all_patients = []
        try:
            import sqlite3, os, json as _json
            dbp = (os.environ.get("YAZKLINIK_DB_PATH")
                    or r"D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3")
            con = sqlite3.connect(dbp)
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
            # D300: TUM hastalari sayfaya gomerek arama client-side yapilacak
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

    # MOD 3: Hicbir session yok
    return render_template_string(_PORTAL_LANDING_PAGE), 401


_PORTAL_HASTA_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Hasta Portal - Ziyaretleriniz</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0d4f8b">
<link rel="apple-touch-icon" sizes="180x180" href="/static/icons/apple-touch-icon-180.png">
<link rel="stylesheet" href="/static/yk-ios-mobile.css?v=d300-ios-2026-05-17">
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
.card{background:#fff;border:1px solid #cdd9e3;border-radius:10px;padding:14px;margin-bottom:10px;
box-shadow:0 1px 3px rgba(0,0,0,.06)}
.card b{color:#0d4f8b;font-size:15px}
.card .meta{font-size:12px;color:#5e7185;margin-top:4px}
.empty{text-align:center;padding:40px;color:#5e7185}
.foot{text-align:center;margin-top:20px;font-size:12px;color:#5e7185}
</style></head><body>
<div class="hdr">
  <h1>Hoş Geldiniz</h1>
  <p>Hasta dosyanız - son ziyaretler ve raporlar</p>
</div>
{% if custom_message %}
  <div style="background:linear-gradient(135deg,#fff8e1,#fff3c4);border-left:4px solid #f0b400;
              padding:14px 16px;border-radius:0 8px 8px 0;margin-bottom:14px">
    <div style="font-size:12px;font-weight:700;color:#b87333;margin-bottom:4px">💬 DOKTORDAN MESAJ</div>
    <div style="font-size:14px;color:#7a5a00;white-space:pre-line">{{custom_message}}</div>
  </div>
{% endif %}

{% if visits %}
  <h3 style="color:#0d4f8b;font-size:16px;margin:14px 0 8px">📋 Ziyaretler ({{visits|length}})</h3>
  {% for v in visits %}
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <b style="font-size:15px">📅 {{v.visit_date or '-'}}</b>
      <span style="font-size:11px;color:#5e7185;background:#eff5fb;padding:2px 8px;border-radius:10px">{{v.visit_type or 'Muayene'}}</span>
    </div>
    {% if v.examination_clean %}<div class="meta">{{v.examination_clean}}</div>{% endif %}
    {% if v.control_note_clean and not v.examination_clean %}<div class="meta">{{v.control_note_clean}}</div>{% endif %}
    {% if v.notes_clean and not v.examination_clean and not v.control_note_clean %}<div class="meta">{{v.notes_clean}}</div>{% endif %}

    {% if v.visit_images %}
    <div style="margin-top:10px">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
        <div style="font-size:12px;color:#0d4f8b;font-weight:600">🖼 USG Görüntüleri ({{v.visit_images|length}}{% if v.image_count and v.image_count > v.visit_images|length %} / toplam {{v.image_count}}{% endif %})</div>
        {% if v.full_path %}
        <a href="/hasta-portal/visit-zip?path={{v.full_path|urlencode}}"
           style="background:#1769aa;color:#fff;padding:6px 10px;border-radius:6px;
                  text-decoration:none;font-size:11px;font-weight:700;white-space:nowrap">
          📦 Hepsini İndir (ZIP)
        </a>
        {% endif %}
      </div>
      <div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(90px,1fr));gap:6px">
        {% for img in v.visit_images %}
        <div style="position:relative">
          <a href="/hasta-portal/media?path={{img.abs_path|urlencode}}" target="_blank"
             style="display:block;aspect-ratio:1;background:#000;border-radius:6px;overflow:hidden">
            <img src="/hasta-portal/media?path={{img.abs_path|urlencode}}" loading="lazy"
                 style="width:100%;height:100%;object-fit:cover">
          </a>
          <a href="/hasta-portal/media?path={{img.abs_path|urlencode}}&download=1"
             title="Indir"
             style="position:absolute;bottom:4px;right:4px;background:rgba(13,79,139,0.92);
                    color:#fff;width:24px;height:24px;border-radius:50%;
                    display:flex;align-items:center;justify-content:center;
                    text-decoration:none;font-size:12px;font-weight:700;
                    box-shadow:0 2px 4px rgba(0,0,0,0.3)">⬇</a>
        </div>
        {% endfor %}
      </div>
    </div>
    {% endif %}

    {% if v.visit_pdfs %}
    <div style="margin-top:10px">
      <div style="font-size:12px;color:#0a8a76;font-weight:600;margin-bottom:6px">📄 Rapor / PDF</div>
      {% for pdf in v.visit_pdfs %}
      <div style="display:inline-flex;gap:0;margin:2px;border-radius:8px;overflow:hidden">
        <a href="/hasta-portal/media?path={{pdf.abs_path|urlencode}}" target="_blank"
           style="background:#d9f4ec;color:#0a8a76;padding:8px 12px;
                  text-decoration:none;font-size:13px;font-weight:600">
          📄 {{pdf.name}}
        </a>
        <a href="/hasta-portal/media?path={{pdf.abs_path|urlencode}}&download=1"
           title="PDF Indir"
           style="background:#0a8a76;color:#fff;padding:8px 12px;
                  text-decoration:none;font-size:13px;font-weight:700">
          ⬇ İndir
        </a>
      </div>
      {% endfor %}
    </div>
    {% endif %}

    {% if v.full_path and (v.visit_images or v.visit_pdfs) %}
    <div style="margin-top:10px;padding-top:8px;border-top:1px solid #eef3f8;text-align:center">
      <a href="/hasta-portal/visit-zip?path={{v.full_path|urlencode}}"
         style="display:inline-block;background:linear-gradient(135deg,#0d4f8b,#0a8a76);
                color:#fff;padding:10px 20px;border-radius:10px;text-decoration:none;
                font-weight:700;font-size:13px;box-shadow:0 3px 8px rgba(0,0,0,0.15)">
        📦 Bu ziyaretin TÜM dosyalarını ZIP olarak indir
      </a>
    </div>
    {% endif %}
  </div>
  {% endfor %}
{% endif %}

{% if pdfs %}
  <h3 style="color:#0a8a76;font-size:16px;margin:14px 0 8px">📄 Raporlar / PDF'ler ({{pdfs|length}})</h3>
  {% for p in pdfs %}
  <div class="card">
    <b>{{p.file_name}}</b>
    {% if p.report_type %}<span style="font-size:11px;color:#5e7185;float:right">{{p.report_type}}</span>{% endif %}
    <div class="meta">📅 {{p.created_at[:10] if p.created_at else '-'}} • {{p.source or 'klinik'}}</div>
  </div>
  {% endfor %}
{% endif %}

{% if meds %}
  <h3 style="color:#b87333;font-size:16px;margin:14px 0 8px">💊 Aktif İlaçlar ({{meds|length}})</h3>
  {% for m in meds %}
  <div class="card">
    <b>{{m.drug_name}}</b> {% if m.dose %}- {{m.dose}}{% endif %}
    {% if m.frequency %}<div class="meta">⏰ {{m.frequency}}</div>{% endif %}
    {% if m.indication %}<div class="meta">💡 {{m.indication}}</div>{% endif %}
  </div>
  {% endfor %}
{% endif %}

{% if labs %}
  <h3 style="color:#a01e7e;font-size:16px;margin:14px 0 8px">🧪 Laboratuvar Sonuçları ({{labs|length}})</h3>
  {% for l in labs %}
  <div class="card">
    <div style="display:flex;justify-content:space-between;align-items:center">
      <b>{{l.test_name or l.test_code}}</b>
      <span style="font-weight:700;color:{% if l.flag == 'H' or l.flag == 'critical' %}#b3261e{% elif l.flag == 'L' %}#b87333{% else %}#16815f{% endif %}">{{l.value}} {{l.unit or ''}}</span>
    </div>
    {% if l.reference_range %}<div class="meta">Referans: {{l.reference_range}}</div>{% endif %}
    {% if l.sample_date or l.report_date %}
      <div class="meta">📅 {{l.report_date or l.sample_date}}</div>
    {% endif %}
  </div>
  {% endfor %}
{% endif %}

{% if not visits and not pdfs and not meds and not labs and not custom_message %}
  <div class="card empty">
    Henüz kayıt bulunmamaktadır.<br>
    Klinik ekibimiz veri girdikten sonra burada görünecektir.
  </div>
{% endif %}
<p class="foot">
  Op. Dr. Hakan Yaz Kliniği<br>
  Sorularınız için klinik ile iletişime geçin.
</p>
</body></html>"""


_PORTAL_DOKTOR_PAGE = r"""<!doctype html><html lang="tr"><head>
<meta charset="utf-8"><title>Hasta Portal Yönetimi</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#1769aa">
<link rel="apple-touch-icon" sizes="180x180" href="/static/icons/apple-touch-icon-180.png">
<link rel="stylesheet" href="/static/yk-ios-mobile.css?v=d300-ios-2026-05-17">
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
<h1>Hasta Portal Yönetimi</h1>
<div class="sub">Doktor: <b>{{doktor}}</b> - Hastalara magic-link üret, WhatsApp ile gönder, son linkleri takip et</div>

<div class="tip">
  <b>Nasıl çalışır:</b> Hasta için magic-link üretin, link WhatsApp ile hastaya gider, hasta 24 saat içinde tıklarsa ziyaret/reçete/USG bilgilerini görür. Link tek kullanımlıktır.
</div>

<div class="section">
  <h2><span class="num">1</span> Yeni Magic-Link Üret</h2>
  <input type="search" id="patient-search" placeholder="🔍 Hasta ara (ad, telefon, TC, dosya no)..."
         autocomplete="off" inputmode="search"
         style="width:100%;padding:14px 16px;font-size:16px;border:2px solid #1769aa;border-radius:10px;-webkit-appearance:none;margin-bottom:8px">
  <div id="search-status" style="font-size:12px;color:#5e7185;margin-bottom:8px;min-height:14px"></div>
  <div id="patient-results" style="background:#fff;border:2px solid #cdd9e3;
       border-radius:10px;max-height:380px;overflow-y:auto;
       display:none;margin-bottom:12px;box-shadow:0 4px 16px rgba(0,0,0,0.1)"></div>
  <div id="selected-patient" style="display:none;background:#e6f4ea;border:1px solid #16815f;
       border-radius:10px;padding:14px;margin-bottom:12px">
    <b style="color:#16815f">✓ Seçili hasta:</b>
    <div id="selected-info" style="margin-top:6px;font-size:14px"></div>
  </div>

  <!-- SELECTOR WIZARD: hasta secince acilir -->
  <div id="share-wizard" style="display:none;background:#f5f8fb;border:1px solid #cdd9e3;
       border-radius:10px;padding:14px;margin-bottom:12px">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
      <b style="color:#0d4f8b;font-size:14px">📤 Hasta Ne Görsün? (varsayılan: hepsi)</b>
      <button type="button" onclick="loadShareOptions()" style="background:#5e7185;font-size:12px;padding:6px 10px">🔄 Yenile</button>
    </div>

    <!-- Custom message -->
    <div style="margin-bottom:10px">
      <label style="font-size:12px;color:#0d4f8b;font-weight:600;display:block;margin-bottom:4px">💬 Hasta için özel mesaj (üst kısımda görünür):</label>
      <textarea id="custom-message" rows="3" placeholder="Örn: Sayın Ayşe, sonuçlar normal. 2 hafta sonra kontrol için bekliyorum. - Dr. Hakan Yaz"
                style="width:100%;padding:10px;font-size:14px;border:1px solid #cdd9e3;border-radius:6px;resize:vertical;-webkit-appearance:none"></textarea>
    </div>

    <!-- Quick toggles -->
    <div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:10px;font-size:14px">
      <label style="display:inline-flex;align-items:center;gap:8px;cursor:pointer;padding:8px 12px;background:#fff;border:1px solid #cdd9e3;border-radius:8px">
        <input type="checkbox" id="opt-pdfs" checked
               style="width:20px;height:20px;accent-color:#1769aa;cursor:pointer;-webkit-appearance:checkbox !important;appearance:checkbox !important">
        📄 PDF/Rapor Arşivi
      </label>
      <label style="display:inline-flex;align-items:center;gap:8px;cursor:pointer;padding:8px 12px;background:#fff;border:1px solid #cdd9e3;border-radius:8px">
        <input type="checkbox" id="opt-meds" checked
               style="width:20px;height:20px;accent-color:#1769aa;cursor:pointer;-webkit-appearance:checkbox !important;appearance:checkbox !important">
        💊 İlaç Listesi
      </label>
      <label style="display:inline-flex;align-items:center;gap:8px;cursor:pointer;padding:8px 12px;background:#fff;border:1px solid #cdd9e3;border-radius:8px">
        <input type="checkbox" id="opt-labs" checked
               style="width:20px;height:20px;accent-color:#1769aa;cursor:pointer;-webkit-appearance:checkbox !important;appearance:checkbox !important">
        🧪 Lab Sonuçları
      </label>
    </div>

    <!-- Visit selector -->
    <div id="visit-list-wrapper" style="display:none;margin-bottom:8px">
      <div style="font-size:12px;color:#0d4f8b;font-weight:600;margin-bottom:6px;display:flex;justify-content:space-between">
        <span>📋 Ziyaretler (seçili olanlar paylaşılır)</span>
        <span>
          <a href="#" onclick="toggleAllVisits(true);return false" style="font-size:11px;margin-right:8px">Hepsi</a>
          <a href="#" onclick="toggleAllVisits(false);return false" style="font-size:11px">Hiçbiri</a>
        </span>
      </div>
      <div id="visit-list" style="max-height:200px;overflow-y:auto;background:#fff;padding:8px;border-radius:6px;border:1px solid #cdd9e3"></div>
    </div>

    <div style="font-size:11px;color:#5e7185;margin-top:6px">
      ℹ️ Hiçbir ziyaret seçilmezse tüm ziyaretler (default 5) paylaşılır
    </div>
  </div>

  <!-- KIMLIK DOGRULAMA: Hasta linke tikladiginda TC + dogum yili sorulur -->
  <div id="verify-wrapper" style="display:none;background:#fde7f5;border:1px solid #a01e7e;
       border-radius:10px;padding:14px;margin-bottom:12px">
    <div style="font-size:13px;color:#a01e7e;font-weight:700;margin-bottom:8px">
      🔐 Hasta Kimlik Doğrulaması (Önerilen - extra güvenlik)
    </div>
    <div style="font-size:12px;color:#5e7185;margin-bottom:8px">
      Hasta linke tıkladığında TC son 4 hane + doğum yılı sorulur (link çalınsa da girilemez)
    </div>
    <div class="form-row">
      <input type="tel" id="tc_last4" placeholder="TC son 4 hane (opsiyonel)" maxlength="4"
             pattern="[0-9]{4}" inputmode="numeric" autocomplete="off">
      <input type="tel" id="birth_year" placeholder="Doğum yılı (opsiyonel) örn 1985" maxlength="4"
             pattern="[0-9]{4}" inputmode="numeric" autocomplete="off">
    </div>
    <div style="font-size:11px;color:#5e7185;margin-top:4px">
      ℹ️ Her ikisi de boş bırakılırsa link doğrudan açılır (güvenlik yok)
    </div>
  </div>

  <div class="form-row">
    <input type="text" id="pid" placeholder="Hasta ID (yukaridan secince doluyor)" autocomplete="off" readonly
           style="background:#f5f8fb">
    <input type="tel" id="phone" placeholder="Telefon (5XXX...)" inputmode="tel" autocomplete="off">
    <select id="ttl" style="max-width:200px;padding:14px 12px;font-size:16px;border:1px solid #cdd9e3;border-radius:8px;background:#fff">
      <option value="24">24 saat</option>
      <option value="72">3 gün</option>
      <option value="168" selected>1 hafta</option>
      <option value="720">1 ay</option>
      <option value="2160">3 ay</option>
      <option value="8760">1 yıl</option>
      <option value="87600">10 yıl (süresiz)</option>
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
      <button type="button" onclick="submitForm(false)">🔗 Link Üret</button>
      <button type="button" class="btn-wa" onclick="submitForm(true)">📱 Üret + WhatsApp Gönder</button>
      <button type="button" class="btn-secondary" onclick="clearAll()">Temizle</button>
    </div>
  </form>
  <div class="result" id="result"></div>
</div>

<div class="section">
  <h2><span class="num">2</span> Son Üretilen Linkler (20)</h2>
  <table>
    <thead><tr><th>Hasta ID</th><th>Tel</th><th>Uretildi</th><th>Sona Erer</th><th>Kullanim</th><th>Durum</th><th>Iptal</th></tr></thead>
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
      {% if t.revoked_at %}<span style="color:#b3261e;font-weight:700">İPTAL</span>
      {% elif t.use_count and t.use_count > 0 %}<span class="status-active">Aktif (kullaniliyor)</span>
      {% else %}<span class="status-active">Hazır</span>
      {% endif %}
      </td>
      <td>
        {% if not t.revoked_at %}
          <button onclick="revokeToken('{{t.token}}', '{{t.patient_id[:20]}}')"
                  style="background:#b3261e;padding:4px 8px;font-size:11px;min-height:28px">İptal</button>
        {% endif %}
      </td>
    </tr>
    {% else %}
    <tr><td colspan="7" style="text-align:center;color:#5e7185;padding:20px">Henüz hiç link üretilmemiş</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>

<div class="section">
  <h2><span class="num">3</span> Test Önizleme (Kendi Magic-Linkin)</h2>
  <p style="color:#5e7185;font-size:13px;margin-bottom:12px">
    Üretilen linki buraya yapıştırıp önizleyebilirsin (hasta nasıl görür?):
  </p>
  <div class="form-row">
    <input type="text" id="preview-url" placeholder="https://.../hasta-portal/giris?token=...&sig=...">
    <button onclick="previewLink()">👁 Önizle</button>
  </div>
</div>

<script>
// --- D300 v5: TUM HASTALAR SAYFADA GOMULU + 100% CLIENT-SIDE ARAMA ---
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
    .replace(/[ğĞ]/g, 'g')
    .replace(/[üÜ]/g, 'u')
    .replace(/[şŞ]/g, 's')
    .replace(/[ıİiI]/g, 'i')
    .replace(/[öÖ]/g, 'o')
    .replace(/[çÇ]/g, 'c')
    .replace(/[âÂ]/g, 'a')
    .replace(/[îÎ]/g, 'i')
    .replace(/[ûÛ]/g, 'u');
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
        (p.phone ? '📱 ' + escapeHtml(p.phone) + ' &nbsp;|&nbsp; ' : '') +
        '📁 ' + escapeHtml((p.key || '').substring(0, 40)) +
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
      '<br><small style="color:#b87333">⚠ Telefon kayitli degil - elle gir</small>');
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
          const media = hasMedia ? '<span style="color:#0a8a76;font-size:11px"> 🖼 ' +
                       (v.image_count||0) + ' resim, 📄 ' + (v.pdf_count||0) + ' pdf</span>' :
                       '<span style="color:#b87333;font-size:11px"> ⚠ dosyasiz</span>';
          // Default: ilk 5 secili (dosyali olanlar)
          const checked = (hasMedia && i < 5) ? 'checked' : '';
          return '<label style="display:flex;align-items:center;gap:8px;padding:8px 4px;border-bottom:1px solid #eef3f8;cursor:pointer;font-size:13px">' +
            '<input type="checkbox" class="visit-cb" data-key="' + escapeHtml(v.full_path || v.visit_key || '') + '" ' + checked +
            ' style="width:18px;height:18px;accent-color:#1769aa;-webkit-appearance:checkbox !important;appearance:checkbox !important;flex-shrink:0"> ' +
            '<span><b>' + escapeHtml(label) + '</b>' + media + '</span></label>';
        }).join('');
      }
      // Pdfs / labs counts info
      let info = [];
      if(pdfs.length) info.push('📄 ' + pdfs.length + ' arşiv PDF');
      if(meds.length) info.push('💊 ' + meds.length + ' aktif ilaç');
      if(labs.length) info.push('🧪 ' + labs.length + ' lab sonuç');
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

// --- D300 v6: FORM SUBMIT (browser native, Funnel/Werkzeug stuck bypass) ---
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
    result.innerHTML = '<b style="color:#b3261e">⚠ Sunucu cevap vermedi (15s)</b>';
    if(callback) callback(null);
  };
  xhr.onerror = function(){
    console.error('[YK-PORTAL] issueLink ERROR');
    result.innerHTML = '<b style="color:#b3261e">⚠ Ag hatasi - tekrar dene</b>';
    if(callback) callback(null);
  };
  xhr.onload = function(){
    console.log('[YK-PORTAL] issueLink DONE status:', xhr.status);
    if(xhr.status === 401){
      result.innerHTML = '<b style="color:#b3261e">⚠ Yetki YOK - tekrar login</b>';
      if(callback) callback(null); return;
    }
    if(xhr.status !== 200){
      result.innerHTML = '<b style="color:#b3261e">⚠ HTTP ' + xhr.status + '</b><br>' +
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
      result.innerHTML = '<b style="color:#16815f">✓ Magic Link uretildi (' + ttl + ' saat gecerli):</b><br><br>' +
        '<div style="background:#fff;padding:10px;border-radius:6px;border:1px solid #cdd9e3;word-break:break-all">' +
        '<a href="' + link + '" target="_blank">' + link + '</a></div><br>' +
        '<button id="btnCopy" style="background:#5e7185">📋 Kopyala</button> ' +
        '<button id="btnPreview" style="background:#1769aa">👁 Onizle</button>';
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
    () => alert('✓ Link kopyalandi'),
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
<meta charset="utf-8"><title>Hasta Portal - Giriş</title>
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#0d4f8b">
<link rel="apple-touch-icon" sizes="180x180" href="/static/icons/apple-touch-icon-180.png">
<link rel="stylesheet" href="/static/yk-ios-mobile.css?v=d300-ios-2026-05-17">
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
<p>Bu sayfa kişiye özel hasta erişimi içindir. Klinikten size gelen <b>magic-link</b> mesajına tıklamanız gerekir.</p>
<div class="info">
<b>Hastaysanız:</b> Klinikten size WhatsApp ile gelen linke tıklayın.<br>
<b>Klinik personeliyseniz:</b> Doktor hesabı ile giriş yapın.
</div>
<a href="/giris?next=/hasta-portal" class="btn">Doktor / Personel Girişi</a>
<a href="/" class="btn btn-secondary">Ana Sayfaya Dön</a>
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
        from yazklinik_smear_hpv_agent import SmearRecord
        rec = SmearRecord(**{k: v for k, v in p.items()
                              if k in SmearRecord.__dataclass_fields__})
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
    return _wrap_call("memnuniyet_survey", memnuniyet_mod.send_survey_for_yesterday, {})


@agents_bp.route("/api/agents/memnuniyet/birthday-today", methods=["POST"])
def api_birthday_today():
    auth = _require_session_or_cron()
    if auth: return auth
    err = _agent_or_503(memnuniyet_mod, "memnuniyet")
    if err: return err
    return _wrap_call("birthday_today", memnuniyet_mod.send_birthday_today, {})


# --- PubMed cron tarama ---
@agents_bp.route("/api/agents/pubmed-cron/scan", methods=["POST"])
def api_pubmed_cron_scan():
    auth = _require_session_or_cron()
    if auth: return auth
    err = _agent_or_503(pubmed_cron_mod, "pubmed_cron")
    if err: return err
    p = _payload()
    return _wrap_call("pubmed_cron_scan", pubmed_cron_mod.scan, {
        "queries": p.get("queries"),
        "max_per_query": int(p.get("max_per_query", 3)),
        "send_to_doctor": bool(p.get("send_to_doctor", True))})


# --- Compliance dashboard ---
@agents_bp.route("/api/agents/compliance/run", methods=["GET", "POST"])
def api_compliance_run():
    auth = _require_session()
    if auth: return auth
    err = _agent_or_503(compliance_mod, "compliance")
    if err: return err
    return _wrap_call("compliance", compliance_mod.run_checks, {})


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
<link rel="stylesheet" href="/static/yk-ios-mobile.css?v=d300-ios-2026-05-17">
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
  <div class="s-it"><div class="s-n" id="today-patients">-</div><div class="s-l">Bugün</div></div>
  <div class="s-it"><div class="s-n" id="upcoming">-</div><div class="s-l">Sıradaki</div></div>
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
      <div class="card-sub">Hızlı kayıt</div>
    </div>
  </a>
  <a href="/randevular" class="card c-rand">
    <div class="card-ico">◷</div>
    <div>
      <div class="card-ttl">Randevular</div>
      <div class="card-sub">Bugün ve yarın</div>
    </div>
  </a>
  <a href="/yz-konsultasyon" class="card c-konsult">
    <div class="card-ico">★</div>
    <div>
      <div class="card-ttl">YZ Konsült</div>
      <div class="card-sub">5 adım analiz</div>
    </div>
  </a>
  <a href="/hasta/aktif/usg-rapor-taslak" class="card c-usg">
    <div class="card-ico">◉</div>
    <div>
      <div class="card-ttl">USG Rapor</div>
      <div class="card-sub">Taslak + AI</div>
    </div>
  </a>
  <a href="/stok" class="card c-stok">
    <div class="card-ico">▤</div>
    <div>
      <div class="card-ttl">Stok</div>
      <div class="card-sub">İlaç + miat</div>
    </div>
  </a>
  <a href="/ajanlar" class="card c-recete">
    <div class="card-ico">⚡</div>
    <div>
      <div class="card-ttl">Tüm Ajanlar</div>
      <div class="card-sub">31 modül</div>
    </div>
  </a>
</div>

<div class="qlinks">
  <a class="qlink" href="/dashboard">Panel</a>
  <a class="qlink" href="/uyumluluk">Uyumluluk</a>
  <a class="qlink" href="/status">Durum</a>
  <a class="qlink" href="/ceviri-merkezi">Çeviri</a>
</div>

<button class="voice-fab" id="voiceBtn" aria-label="Sesli komut">🎤</button>

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
<link rel="stylesheet" href="/static/yk-ios-mobile.css?v=d300-ios-2026-05-17">
<style>
:root{--safe-top:env(safe-area-inset-top,0px);--safe-bottom:env(safe-area-inset-bottom,0px)}
*{box-sizing:border-box}
html,body{-webkit-text-size-adjust:100%;-webkit-tap-highlight-color:transparent;margin:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#f5f8fb;color:#122236;
padding:calc(20px + var(--safe-top)) 18px calc(20px + var(--safe-bottom));max-width:1100px;margin:0 auto;
min-height:100vh;min-height:100dvh}
h1{margin:0 0 14px;color:#1769aa;font-size:22px}
.banner{background:#fff;border:1px solid #cdd9e3;border-radius:14px;padding:18px;
margin-bottom:18px;display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.banner > div:first-child{min-width:120px}
.score-big{font-size:42px;font-weight:900;line-height:1}
.grade-A{color:#16815f}.grade-B{color:#1769aa}.grade-C{color:#b87333}
.grade-D,.grade-F{color:#b3261e}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #cdd9e3;
border-radius:10px;overflow:hidden;display:block;overflow-x:auto;-webkit-overflow-scrolling:touch}
th,td{padding:11px 10px;text-align:left;border-bottom:1px solid #eef3f8;font-size:13px;white-space:nowrap}
th{background:#eff5fb;font-weight:700;color:#0d4f8b;text-transform:uppercase;letter-spacing:.3px;font-size:11px}
.s-pass{color:#16815f;font-weight:700}.s-fail{color:#b3261e;font-weight:700}
.s-warn{color:#b87333;font-weight:700}.s-unknown{color:#888}
.recs{margin-top:18px;background:#fffbe5;border-left:4px solid #f0b400;padding:14px;border-radius:0 8px 8px 0}
button{background:#1769aa;color:#fff;border:0;padding:12px 20px;border-radius:8px;
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
<div><div class="score-big" id="grade">?</div><div id="scoretxt">Yükleniyor...</div></div>
<div style="flex:1"><div id="criticalbox" style="font-size:14px;color:#b3261e"></div></div>
<button onclick="runCheck()">Yeniden Çalıştır</button>
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
    res.critical_failures>0 ? ('KRİTİK: '+res.critical_failures+' önemli eksik') : 'Kritik eksik yok';
  const tb = document.getElementById('checks'); tb.innerHTML='';
  for(const c of res.checks){
    const tr = document.createElement('tr');
    tr.innerHTML = '<td>'+c.code+'</td><td>'+c.title+'</td><td>'+c.standard+'</td>'+
      '<td class="s-'+c.status+'">'+c.status.toUpperCase()+'</td><td>'+c.detail+'</td>';
    tb.appendChild(tr);
  }
  if(res.recommendations_top && res.recommendations_top.length){
    document.getElementById('recs').style.display='block';
    document.getElementById('recs').innerHTML = '<b>İlk Öneriler:</b><ul>'+
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

