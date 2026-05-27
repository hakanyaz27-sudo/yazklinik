# CODEX HANDOFF â€” 10 Klinik Ajan + /ajanlar Dashboard (2026-05-16)

**BaÄŸlam:** Op. Dr. Hakan Yaz (OB-GYN) iÃ§in YazKlinik D700'e 10 yeni klinik ajan eklendi. TÃ¼m ajanlar saf is mantigi (pure functions); web layer ile bir Flask Blueprint Ã¼zerinden baÄŸlandÄ±. v68 ve mevcut route'lar **dokunulmadÄ±**.

**Sunucu:** `https://127.0.0.1:5443` (waitress, HTTPS). Restart: `D500_BASLAT.bat` veya `Stop-Process` + lock dosyasÄ± sil + `python -u yazklinik_web.py`.

**Branch:** `claude/friendly-khayyam-672aff` (PR: https://github.com/hakanyaz27-sudo/yazklinik/pull/new/claude/friendly-khayyam-672aff)

---

## Ã–ZET â€” Bu session'da ne yapÄ±ldÄ±

1. **10 saf ajan modÃ¼lÃ¼** eklendi (`yazklinik_*_agent.py`), her biri stdlib + ASCII safe + AGENT_VERSION sabiti + dataclass + `if __name__ == "__main__"` smoke testi.
2. **yazklinik_integration_agents.py** registry'sine 10 ajan kaydedildi (AGENT_VERSION bumped: `2026.05.16-integration-agents`).
3. **yazklinik_agents_routes.py** yeni Flask Blueprint â€” 12 route (10 ajan endpoint + manifest + dashboard).
4. **yazklinik_feature_sync.py** AJANLAR menÃ¼ grubu (11 entry); MANIFEST_VERSION â†’ `2026.05.16-D700-AGENTS-WIRED`.
5. **yazklinik_web.py** sadece **10 satÄ±r** dokunma: `app.register_blueprint(agents_bp)` try/except sarmalÄ±nda â€” patlasa bile mevcut web ayakta kalÄ±r.

**Toplam:** 14 yeni dosya, 3 deÄŸiÅŸtirilen dosya, +3053 satÄ±r. SÄ±fÄ±r kod silindi.

---

## YENÄ° DOSYALAR

| Dosya | AmaÃ§ | Entry function |
|---|---|---|
| `yazklinik_telesekreter_agent.py` | Gelen aramayÄ± niyet+aciliyet triyajÄ± | `parse_call(call: CallRecord)` |
| `yazklinik_sesli_onay_agent.py` | "Evet/hayÄ±r/ertele" â†’ randevu state | `decide(request: ConfirmationRequest)` |
| `yazklinik_usg_rapor_agent.py` | BPD/HC/AC/FL â†’ Hadlock EFW + taslak | `build_draft(data: USGInput)` |
| `yazklinik_geri_cagirma_agent.py` | Kontrol/aÅŸÄ±/postop hatÄ±rlatma kuyruÄŸu | `bulk_schedule(candidates, channel)` |
| `yazklinik_bk_sync_bekci_agent.py` | BulutKlinik token/cookie saÄŸlÄ±k | `check_status(probe: SyncProbe)` |
| `yazklinik_nas_yedek_izleyici_agent.py` | NAS yedek + disk doluluk (read-only) | `check_health(nas_root, backup_subdir)` |
| `yazklinik_recete_hazirlayici_agent.py` | GeÃ§miÅŸ + alerji ile reÃ§ete taslaÄŸÄ± | `build_draft(req: DraftRequest)` |
| `yazklinik_gunluk_ozet_agent.py` | GÃ¼n sonu trafik + ciro + bekleyenler | `build_summary(data: SummaryInput)` |
| `yazklinik_mojibake_bekci_agent.py` | Encoding bozukluÄŸu (**SADECE TESPIT**) | `scan_tree(root: str)` |
| `yazklinik_pr_reviewer_agent.py` | Diff sablon kontrol (v68/DELETE/NAS) | `review_diff(diff_text: str)` |
| `yazklinik_agents_routes.py` | Flask Blueprint â€” 12 route | `agents_bp` |
| `CODEX_HANDOFF_2026-05-16_AJANLAR.md` | Bu dokÃ¼man | â€” |

---

## DEÄÄ°ÅTÄ°RÄ°LEN DOSYALAR

### `yazklinik_web.py`

**Sadece line 631 sonrasÄ± 10 satÄ±r eklendi** (line 631 = `app = Flask(__name__)`). Kalan 161.045 satÄ±ra dokunulmadÄ±.

```python
app = Flask(__name__)

# === 10 klinik ajan Blueprint - tek wire point ===
try:
    from yazklinik_agents_routes import agents_bp as _agents_bp
    app.register_blueprint(_agents_bp)
except Exception as _agents_exc:  # noqa: BLE001
    import logging as _agents_log
    _agents_log.getLogger(__name__).warning(
        "agents_bp register basarisiz: %s", _agents_exc
    )
```

### `yazklinik_feature_sync.py`

- `MANIFEST_VERSION` â†’ `"2026.05.16-D700-AGENTS-WIRED"` (line 18)
- Yeni AJANLAR grubu `FEATURE_GROUPS` sonuna eklendi (line 441 Ã¶ncesi)

### `yazklinik_integration_agents.py`

- `AGENT_VERSION` â†’ `"2026.05.16-integration-agents"` (line 15)
- `INTEGRATION_AGENTS` listesine 10 yeni ajan kaydÄ± (her biri id, name, short, status, risk, module, entry_function, safe/blocked methods, doctor_actions)

---

## YENÄ° API ENDPOINTS

| Route | Method | Body | Cevap |
|---|---|---|---|
| `/ajanlar` | GET | â€” | HTML dashboard (kart grid + manifest dump) |
| `/api/agents` | GET | â€” | JSON: `{ok, modules, registry, import_errors}` |
| `/api/agents/telesekreter/run` | POST | `{caller_phone, transcript, received_at?, duration_sec?, caller_name?}` | `{ok, agent, result: TriagedCall}` |
| `/api/agents/sesli_onay/run` | POST | `{appointment_id, patient_phone, patient_name, appointment_at, spoken_response}` | `{ok, agent, result: ConfirmationResult}` |
| `/api/agents/usg_rapor/run` | POST | `{patient_id, patient_name, exam_date, lmp?, measurements:[{name,value_mm,notes?}], report_type?}` | `{ok, agent, result: USGReportDraft}` |
| `/api/agents/geri_cagirma/run` | POST | `{candidates:[PatientCandidate], channel:"whatsapp"\|"sms"}` | `{ok, agent, result:{queued,skipped}}` |
| `/api/agents/bk_sync_bekci/run` | POST | `{last_success_at?, consecutive_failures?, auth_mode?, token_expires_at?, reachable?}` | `{ok, agent, result: HealthReport}` |
| `/api/agents/nas_yedek_izleyici/run` | POST | `{nas_root, backup_subdir?}` | `{ok, agent, result: NASHealthReport}` |
| `/api/agents/recete_hazirlayici/run` | POST | `{patient_id, patient_name, patient_allergies, chronic_conditions, past_medications:[PastMedication], doctor_preferred_combos, max_suggestions?}` | `{ok, agent, result: RecipeDraft}` |
| `/api/agents/gunluk_ozet/run` | POST | `{for_date, today, yesterday?, today_finance, queues, tomorrow:[TomorrowSlot]}` | `{ok, agent, result: DailySummary}` |
| `/api/agents/mojibake_bekci/run` | POST | `{root}` | `{ok, agent, result: ScanResult}` |
| `/api/agents/pr_reviewer/run` | POST | `{diff_text}` | `{ok, agent, result: ReviewResult}` |

**Standart cevap zarflarÄ±:**
- BaÅŸarÄ±: `{"ok": true, "agent": "<id>", "result": {...}}`
- ModÃ¼l import hatasÄ±: `503` + `{"ok": false, "agent": "<id>", "error": "module_import_failed", "detail": "..."}`
- HatalÄ± parametre: `400` + `{"ok": false, "agent": "<id>", "error": "bad_request"}`
- Ajan exception: `500` + `{"ok": false, "agent": "<id>", "error": "agent_failure", "trace": "..."}`
- Yetki yok: `401` + `{"ok": false, "error": "auth_required"}`

---

## YETKÄ° VE GÃœVENLÄ°K

- **Auth:** Her endpoint `session["username"]` ister. Web.py'nÄ±n mevcut `login_required` decorator desenine baÄŸÄ±mlÄ± deÄŸil â€” basit kontrol, kompozisyona uygun.
- **Audit:** `web_audit_log` fonksiyonu varsa `agents:<id>` aksiyonuyla cagirilir. Yoksa sessizce geÃ§er (try/except).
- **Hata izolasyonu:** Blueprint register tek try/except sarmalÄ±nda â€” yapÄ± bozulursa web.py aÃ§Ä±lmaya devam eder.
- **Memory kurallarÄ±:**
  - v68 dokunulmadÄ± âœ…
  - Hasta verisi silen kod yok âœ…
  - NAS read-only (sadece stat ve disk_usage) âœ…
  - Mojibake **sadece tespit eder**, asla auto-fix yok âœ…
  - Recete ajanÄ± alerji listesi yoksa hicbir oneri yapmaz âœ…

---

## TEST KOMUTLARI

### Standalone smoke (server gerekmez)

```powershell
$env:PYTHONIOENCODING="utf-8"
python.exe yazklinik_telesekreter_agent.py
python.exe yazklinik_sesli_onay_agent.py
python.exe yazklinik_usg_rapor_agent.py
python.exe yazklinik_geri_cagirma_agent.py
python.exe yazklinik_bk_sync_bekci_agent.py
python.exe yazklinik_recete_hazirlayici_agent.py
python.exe yazklinik_gunluk_ozet_agent.py
python.exe yazklinik_pr_reviewer_agent.py
```

### Blueprint sanity (server gerekmez)

```python
python.exe -c @"
from yazklinik_agents_routes import agents_bp
from flask import Flask
a = Flask('test'); a.register_blueprint(agents_bp)
print(sorted(r.rule for r in a.url_map.iter_rules() if r.endpoint.startswith('agents.')))
"@
```

### Server Ã¼zerinden test (login sonrasÄ±)

```powershell
# 1. Server'Ä± baslat
D500_BASLAT.bat

# 2. Tarayicida giris
# https://127.0.0.1:5443/giris  ->  doktor / 1234

# 3. Dashboard
# https://127.0.0.1:5443/ajanlar

# 4. Manifest
curl -k -b cookies.txt https://127.0.0.1:5443/api/agents | jq

# 5. Ornek call - telesekreter
curl -k -X POST -H "Content-Type: application/json" -b cookies.txt `
  -d '{"caller_phone":"05551234567","transcript":"Su geldi sancim var acil"}' `
  https://127.0.0.1:5443/api/agents/telesekreter/run | jq
```

### CODEX_QUICK_CHECK Ã§alÄ±ÅŸtÄ±r

```powershell
& "D:\YazKlinik_Final_D500\.venv\Scripts\python.exe" `
  D:\YazKlinik_Final_D500\CODEX_QUICK_CHECK.py
```

---

## SCREENSHOT / UI

`/ajanlar` sayfasÄ±:
- Ãœst banner: "Klinik Ajanlari (10)" + kullanÄ±m notu
- Grid: her ajan iÃ§in bir kart (isim, aÃ§Ä±klama, durum rozeti, id/risk/status meta)
- YeÅŸil "aktif" = modÃ¼l yÃ¼klendi
- KÄ±rmÄ±zÄ± "import hatasi" = modÃ¼l var ama import patlamÄ±ÅŸ
- SarÄ± "no module" = registry'de var ama dosya yok
- Alt: `<pre>` manifest JSON dump (debug iÃ§in)

Tema dark, vanilla CSS, dependency yok.

---

## NEXT STEPS â€” CODEX Ä°Ã‡Ä°N Ã–NERÄ°LEN Ä°ÅLER

Ã–nceliklendirilmiÅŸ:

1. **PSTN/Twilio webhook baÄŸla** (P1):
   `POST /webhook/twilio/voice` â†’ `parse_call()` â†’ onay kuyruÄŸuna SQLite'a yaz.
   Yeni tablo Ã¶neri: `agent_call_queue (id PK, agent, payload_json, status, created_at, reviewed_at, reviewed_by, action_taken)`.

2. **Sesli onay STT pipeline** (P1):
   Mevcut whisper service'i (`yazklinik_whisper_service.py`, port 9000) ile kÃ¶prÃ¼ kur.
   Outbound call sonrasÄ± STT â†’ `decide()` â†’ guven yuksekse direk randevu state degisikligi.

3. **USG rapor â†’ web.py recete-hazirla benzeri sayfa** (P2):
   `/hasta/<key>/usg-rapor-taslak` â€” sol panel form (BPD/HC/AC/FL giriÅŸi), saÄŸ panel canlÄ± taslak preview.
   `usg_rapor.build_draft()` Ã§aÄŸrÄ±, doktor dÃ¼zenler, "Hasta dosyasÄ±na yaz" butonu mevcut PDF/usg_measurements yoluna gider.

4. **Geri Ã§aÄŸÄ±rma iÃ§in sablonlanmis WhatsApp gÃ¶nderim** (P2):
   `yazklinik_whatsapp_local_helper.py` zaten var. `ReminderJob.scheduled_for` ile cron entegrasyonu.
   Doktor onay ekranÄ±: `/geri-cagirma-kuyrugu` (queue list + tek tÄ±kla onay/iptal).

5. **NAS izleyici daemon** (P3):
   `D500_HEALTH_MONITOR.py` icine `nas_yedek_izleyici.check_health()` Ã§aÄŸrÄ±sÄ±.
   Critical durumda `D500_health_monitor.log.err` yaz.

6. **PR reviewer GitHub Actions** (P3):
   `.github/workflows/pr-review.yml` â€” `pr_reviewer.review_diff()` her PR'da otomatik koÅŸar.
   Blocker varsa CI fail.

---

## BÄ°LÄ°NEN SINIRLAR

- Endpoint'ler **JSON only** (form post desteklenir ama dataclass Ã§evirisi zayÄ±f kalÄ±r).
- Audit `web_audit_log` ilk istek geldiÄŸinde import edilir; o zamana kadar log ekleme yok.
- Blueprint adÄ± `agents` â€” URL prefix yok; mevcut `/api/...` yapÄ±sÄ±yla Ã§akÄ±ÅŸan route bulunmadÄ± (kontrol edildi).
- `request.is_json` False ise `request.form.to_dict(flat=True)` kullanÄ±lÄ±r â€” listeyle gelen `measurements` gibi alanlar form Ã¼zerinden Ã§alÄ±ÅŸmaz, JSON gÃ¶nderin.
- USG ajanÄ± Hadlock IV formÃ¼lÃ¼nÃ¼ kullanÄ±r; referans tablosu basit (12-40 hafta, 4 haftada bir). Persantil tablosuna geÃ§erken `REFERENCE_MEANS` sÃ¶zlÃ¼ÄŸÃ¼ gÃ¼ncellenmeli.

---

## REGISTRY EROZYONUNU Ã–NLE

`yazklinik_integration_agents.py` artÄ±k 14 ajan iÃ§erir (4 mevcut + 10 yeni). Yeni ajan eklemek istersen:

```python
{
    "id": "yeni_ajan",
    "name": "Yeni Klinik Ajani",
    "short": "Bir cumlelik aciklama.",
    "status": "ready_internal",  # | "ready_with_credentials" | "official_export_or_api_required"
    "risk": "low",                # | "medium" | "high"
    "directions": ["YazKlinik -> X"],
    "module": "yazklinik_yeni_ajan_agent",   # entry module
    "entry_function": "main_fn",             # ana fonksiyon adi
    "safe_methods": ["..."],
    "blocked_methods": ["..."],
    "doctor_actions": ["..."],
},
```

`yazklinik_agents_routes.py`'a yeni endpoint ekle, `yazklinik_feature_sync.py` AJANLAR grubuna `_r(...)` kaydet, web.py'a dokunma â€” Blueprint zaten yÃ¼klÃ¼.

---

## VERSIONS TOUCHED

| Dosya | Eski | Yeni |
|---|---|---|
| yazklinik_integration_agents.py `AGENT_VERSION` | `2026.04.30-integration-agents` | `2026.05.16-integration-agents` |
| yazklinik_feature_sync.py `MANIFEST_VERSION` | `2026.05.16-D700-CLIENT-DEVICE` | `2026.05.16-D700-AGENTS-WIRED` |

Her yeni ajan dosyasÄ±nda `AGENT_VERSION = "2026.05.16-<id>"` sabiti var.

---

## COMMITS

```
512eec7  Wire 10 klinik ajani: /ajanlar dashboard + /api/agents/* Blueprint
0a5a718  Add 10 klinik ajani (telesekreter, sesli onay, USG rapor, geri cagirma, ...)
95c3b2a  Add terminal-safe client actions and BK Voluson panel  (onceki session)
```

PR linki ilk push'tan sonra: https://github.com/hakanyaz27-sudo/yazklinik/compare/d700-safe-initial...claude/friendly-khayyam-672aff



