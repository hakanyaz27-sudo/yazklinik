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
import os
import traceback
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, render_template_string, request, session, send_file, abort


agents_bp = Blueprint("agents", __name__)

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
        "instagram": instagram_mod is not None,
        "ceviri": ceviri_mod is not None,
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
