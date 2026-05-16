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

Yetki kontrolu: session['username'] var mi diye bakar (zaten web.py decorator).
Bu Blueprint o decorator'i import etmez; basit session check yapar.
Tum cikti web layer audit'ine 'agents:*' aksiyonu olarak yansir.
"""

from __future__ import annotations

import json
import traceback
from dataclasses import asdict, is_dataclass
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, render_template_string, request, session


agents_bp = Blueprint("agents", __name__)


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

# Registry (opsiyonel)
try:
    from yazklinik_integration_agents import get_integration_agents as _get_registry
except Exception:  # noqa: BLE001
    _get_registry = None


# --- Helper'lar ---

def _require_session():
    """Web.py'in genel session kuralina hafif bagli kontrol.
    Doktor/asistan/sekreter girisi yoksa 401 dondur.
    """
    user = session.get("username") if hasattr(session, "get") else None
    if not user:
        return jsonify({"ok": False, "error": "auth_required"}), 401
    return None


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
    }
    return jsonify(payload)


_AGENTS_PAGE = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<title>Klinik Ajanlari - YazKlinik</title>
<style>
  body { font-family: -apple-system, Segoe UI, sans-serif; background: #0e1117; color: #e6e6e6; margin: 0; padding: 24px; }
  h1 { margin: 0 0 16px; font-size: 22px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 14px; }
  .card h3 { margin: 0 0 6px; font-size: 15px; color: #58a6ff; }
  .card p { margin: 0 0 8px; font-size: 12px; color: #c9d1d9; line-height: 1.45; }
  .pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-size: 11px; }
  .pill.ok { background: #1f6f43; color: #d2f5da; }
  .pill.fail { background: #6f1f1f; color: #f5d2d2; }
  .pill.warn { background: #6f5f1f; color: #f5ecb1; }
  code { background: #0d1117; padding: 1px 5px; border-radius: 4px; font-size: 11px; }
  .meta { font-size: 11px; color: #8b949e; margin-top: 8px; }
  .row { display: flex; justify-content: space-between; gap: 8px; align-items: center; }
  .btn { display: inline-block; padding: 5px 10px; background: #21262d; border: 1px solid #30363d;
         border-radius: 6px; color: #e6e6e6; text-decoration: none; font-size: 11px; cursor: pointer; }
  .btn:hover { background: #30363d; }
  pre { background: #010409; padding: 10px; border-radius: 6px; font-size: 11px; max-height: 260px; overflow: auto; }
</style></head>
<body>
  <h1>Klinik Ajanlari (10)</h1>
  <p style="color:#8b949e;font-size:12px;">Tum ajanlar saf is mantigi sunar; sonuclar onay kuyrugunda doktoru bekler.
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
