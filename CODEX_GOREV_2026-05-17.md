# CODEX GOREV - 2026-05-17 (Session 7 sonrasi)

> **Codex, bu dosyayi bastan sona oku.** Iki bolum var:
> 1. Claude'un az once yaptiklarinin ozeti (sen ne gormeli + nasil entegre)
> 2. **Sana verilen 7 gorev** (oncelik sirali, her biri kucuk + bagimsiz)

Branch: `claude/friendly-khayyam-672aff` (push edildi)
Worktree: `D:\YazKlinik_Final_D500\.claude\worktrees\friendly-khayyam-672aff`
Main: `D:\YazKlinik_Final_D500` (dosyalar zaten kopyalandi)

---

## BOLUM 1: Claude Bu Seansta Ne Yapti

### Tek satirla
29 yeni Python ajan modulu + Flask Blueprint'e 38 yeni endpoint + PWA (manifest+sw) + uyumluluk panosu (`/uyumluluk`) + public status sayfasi (`/status`) + n8n WhatsApp chatbot workflow + 3 stub README. Hepsi smoke OK.

### Eklenen 29 ajan dosyasi

| Dosya | Ana fonksiyon | LLM kullanir mi |
|---|---|---|
| `yazklinik_vision_usg_agent.py` | `analyze_image(path)` | EVET (llama3.2-vision:11b) |
| `yazklinik_soap_agent.py` | `expand_to_soap(note)` | EVET (meditron veya qwen) |
| `yazklinik_icd10_agent.py` | `suggest_codes(note, top_k)` | EVET (LLM semantic match) |
| `yazklinik_gebelik_takvim_agent.py` | `compute_plan(lmp)` | HAYIR |
| `yazklinik_risk_skor_agent.py` | `preeklampsi_risk(...)`, `hellp_risk(...)`, `bishop_score(...)`, `vte_padua_score(...)` | HAYIR |
| `yazklinik_ddi_agent.py` | `check_interactions(drugs, is_pregnant)` | HAYIR (static DB) |
| `yazklinik_smear_hpv_agent.py` | `compute_followup(SmearRecord)` | HAYIR |
| `yazklinik_phq9_agent.py` | `score(patient_id, [9 cevap])` | HAYIR |
| `yazklinik_konsey_agent.py` | `build_presentation(ConseyVakaInput)` | RAG kullanir |
| `yazklinik_hatira_usg_agent.py` | `prepare()` + `send(job)` | HAYIR (instagram_agent + WhatsApp) |
| `yazklinik_voice_command_agent.py` | `parse(spoken_text)` | HAYIR (regex) |
| `yazklinik_anti_burnout_agent.py` | `compute_report()` | HAYIR |
| `yazklinik_orchestrator_agent.py` | `full_visit()`, `pubmed_research_pack()`, `usg_full_pipeline()` | EVET (chain) |
| `yazklinik_hasta_portal_agent.py` | `issue_magic_link()`, `verify_token()`, `list_my_visits()` | HAYIR |
| `yazklinik_2fa_agent.py` | `setup(user)`, `enable()`, `verify(code)` | HAYIR (stdlib HMAC-SHA1) |
| `yazklinik_stok_agent.py` | `upsert_item()`, `record_movement()`, `generate_report()` | HAYIR |
| `yazklinik_plugin_loader.py` | `scan_and_load()`, `call_plugin()` | HAYIR |
| `yazklinik_compliance_agent.py` | `run_checks()` (10+ ISO/KVKK kontrol) | HAYIR |
| `yazklinik_status_page_agent.py` | `build_report()`, `render_html()` | HAYIR |
| `yazklinik_celery_worker.py` | Celery app + 4 task | HAYIR |
| `yazklinik_sentry_init.py` | `init_if_configured()` | HAYIR |
| `yazklinik_memnuniyet_agent.py` | `send_survey_for_yesterday()`, `send_birthday_today()` | HAYIR (WhatsApp) |
| `yazklinik_pubmed_cron_agent.py` | `scan(queries, max)` | EVET (ceviri_agent zincir) |
| `yazklinik_payment_agent.py` | `initiate()`, `confirm_webhook()`, `refund()` | HAYIR (stub) |
| `yazklinik_enabiz_kts_agent.py` | `submit_recete()` | HAYIR (stub) |
| `yazklinik_mhrs_agent.py` | `import_today()` | HAYIR (stub) |
| `yazklinik_medula_agent.py` | `query_provizyon()`, `submit_recete()` | HAYIR (stub) |
| `yazklinik_lab_duzen_agent.py` | `fetch_results()`, `upsert_manual()` | HAYIR (stub) |
| `yazklinik_iot_bluetooth_agent.py` | `scan_for_devices()`, parser fonksiyonlar | HAYIR (bleak stub) |

### Wire (Flask Blueprint)

Dosya: `yazklinik_agents_routes.py` (+~580 satir append)
- 38 yeni endpoint (asagida liste)
- Compliance HTML page (`/uyumluluk`)
- Status HTML page (`/status` PUBLIC)
- PWA serve (`/manifest.webmanifest`, `/sw.js`)
- Hasta portal (`/hasta-portal`, `/hasta-portal/giris?token=...`)

### Yeni endpoint listesi (38)

```
POST  /api/agents/vision-usg/analyze         {image_path}
POST  /api/agents/soap/expand                {note, prefer?}
POST  /api/agents/icd10/suggest              {note, top_k}
POST  /api/agents/gebelik/plan               {lmp, current_date?}
POST  /api/agents/risk/preeklampsi
POST  /api/agents/risk/hellp
POST  /api/agents/risk/bishop
POST  /api/agents/risk/vte
POST  /api/agents/ddi/check                  {drugs[], is_pregnant, trimester}
POST  /api/agents/smear-hpv/followup         {SmearRecord fields}
POST  /api/agents/phq9/score                 {patient_id, answers[9]}
GET   /api/agents/phq9/questionnaire
POST  /api/agents/konsey/build               {ConseyVakaInput fields, use_rag?}
POST  /api/agents/hatira-usg/prepare         {patient_id, patient_name, ...}
POST  /api/agents/hatira-usg/send            {HatiraJob fields}
POST  /api/agents/voice-command/parse        {text}
GET   /api/agents/burnout/report
POST  /api/agents/2fa/setup
POST  /api/agents/2fa/enable                 {code}
POST  /api/agents/2fa/verify                 {code}
POST  /api/agents/portal/issue-link          {patient_id, phone, ttl_hours?}
GET   /hasta-portal/giris?token=...&sig=...  (magic link login)
GET   /hasta-portal                          (hasta panel HTML)
POST  /api/agents/orchestrator/full-visit    {case_text, prefer?}
POST  /api/agents/orchestrator/pubmed-pack   {query, max_articles?}
POST  /api/agents/orchestrator/usg-pipeline  {image_path, patient_key, lmp?}
GET   /api/agents/stok/report
POST  /api/agents/stok/upsert                {StockItem fields}
POST  /api/agents/stok/movement              {code, direction, quantity}
POST  /api/agents/payment/initiate           {PaymentRequest fields}
POST  /api/agents/payment/webhook/<provider>
GET   /api/agents/payment/recent
GET   /api/agents/enabiz/health
GET   /api/agents/mhrs/health
GET   /api/agents/medula/health
POST  /api/agents/medula/provizyon           {tc}
GET   /api/agents/lab-duzen/health
POST  /api/agents/lab-duzen/fetch            {patient_tc}
POST  /api/agents/iot/scan
GET   /api/agents/plugins/list
POST  /api/agents/plugins/call               {plugin, func, args, kwargs}
POST  /api/agents/memnuniyet/survey-yesterday
POST  /api/agents/memnuniyet/birthday-today
POST  /api/agents/pubmed-cron/scan           {queries?, max_per_query?}
GET   /api/agents/compliance/run             (PUBLIC GET)
POST  /api/agents/compliance/run
GET   /uyumluluk                             (HTML grade panel)
GET   /api/status                            (PUBLIC JSON)
GET   /status                                (PUBLIC HTML)
GET   /manifest.webmanifest                  (PWA)
GET   /sw.js                                 (PWA service worker)
```

### Diger dosyalar

- `static/manifest.json` - PWA manifest (shortcuts + icons referansi)
- `static/sw.js` - Service Worker (network-first HTML, cache-first asset, push handler)
- `n8n_workflows/whatsapp_chatbot.json` - WhatsApp incoming -> intent -> YazKlinik API veya Ollama qwen2.5:32b
- `akillilik/xtts/README.md` - Voice cloning (Hakan sesi) yol haritasi
- `akillilik/saas/README.md` - Multi-tenancy tartismasi
- `akillilik/wearables/README.md` - Apple Watch + WearOS push roadmap
- `CODEX_HANDOFF_2026-05-17_SESSION7.md` - tam handoff
- `CODEX_BASLA_BURADAN.md` - Session 7 entry eklendi

### Smoke test sonuclari (Claude tarafindan calistirildi)

```
IMPORTED OK: 29/29 modul (Python 3.12)
Blueprint loaded: agents, deferred funcs: 91
PHQ9: skor=16 severity=moderate-severe suicide=True
DDI: 1 uyari (warfarin+aspirin major), safe=False
VOICE: 'BPD 85' -> measure(bpd_mm) conf=92
COMPLIANCE: 9/27 grade=F (audit_log + consent eksik)
STATUS: degraded - 7 yardimci servis kapali (normal, henuz baslamadi)
SMEAR: ASCUS+HPV+ -> plan=colpo
```

### Git durumu

```
Commit 4e6f00f: Session 7: 29 yeni ajan + Flask wire + PWA + uyumluluk panosu
Commit da7a7b9: docs: Session 7 entry CODEX_BASLA_BURADAN.md guncellendi
Branch: claude/friendly-khayyam-672aff (PUSH EDILDI)
Main: d700-safe-initial (8 commit geride, henuz merge edilmedi)
```

---

## BOLUM 2: Codex Sana Verilen 7 Gorev

> Her gorev bagimsiz, sirayla yapabilirsin. Her birinde net "test komutu" var.

### GOREV 1: Server restart + Blueprint register dogrula [10 dk]

**Amac**: 91 yeni endpoint canli sistemde calissin.

**Adimlar**:
1. `yazklinik_web.py`'a bak: `from yazklinik_agents_routes import agents_bp` ve `app.register_blueprint(agents_bp)` var mi? (muhtemelen var, sadece dogrula)
2. Server'i kill et:
   ```powershell
   Get-NetTCPConnection -LocalPort 5443 -ErrorAction SilentlyContinue |
     Select-Object -ExpandProperty OwningProcess -Unique |
     ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }
   ```
3. Yeniden baslat: `D:\YazKlinik_Final_D500\D500_BASLAT.bat`
4. Smoke test:
   ```powershell
   $sess = Invoke-WebRequest -Uri "https://127.0.0.1:5443/giris" -SessionVariable s -SkipCertificateCheck
   # Login at, sonra:
   curl.exe -k https://127.0.0.1:5443/api/status
   curl.exe -k https://127.0.0.1:5443/status
   curl.exe -k -X POST -H "Content-Type: application/json" `
     -d '{"text":"BPD 85"}' https://127.0.0.1:5443/api/agents/voice-command/parse
   ```

**Bekleniyor**: `/status` HTML render olur, `/api/status` JSON doner, voice-command 401 (auth gerek - bu DOGRU).

---

### GOREV 2: `/ajanlar` dashboard'a 29 yeni kart ekle [20 dk]

**Amac**: Yeni ajanlar dashboard'da gorunsun.

**Dosya**: `yazklinik_agents_routes.py` -> `_AGENT_DASHBOARD_PAGE` HTML string'i
(line ~314 civari `agents_dashboard()` fonksiyonu)

**Yapilacak**: Mevcut HTML'e 29 yeni `<div class="agent-card">` ekle. Her kart icin:
- Ikon + isim + bir cumle aciklama
- "Calistir" butonu -> ilgili endpoint'e POST
- Sonuc box (JSON pretty render)

**Onerilen kategoriler** (4 sekme):
1. Klinik AI (vision, soap, icd10, ddi, smear, phq9, konsey, hatira, risk x4)
2. Sistem (voice, burnout, orchestrator x3, portal, 2fa, stok, plugin)
3. Compliance + Status (compliance, status, manifest, sw)
4. Cron + Stub (memnuniyet, pubmed_cron, payment, enabiz, mhrs, medula, lab, iot)

**Test**: `https://127.0.0.1:5443/ajanlar` -> 29 yeni kart gorunmeli.

---

### GOREV 3: Compliance grade F -> C (audit_log + patient_consents tablo) [15 dk]

**Amac**: `yazklinik_compliance_agent.run_checks()` su an 9/27 (F) veriyor cunku `audit_log` ve `patient_consents` tablolari yok.

**Adimlar**:
1. SQLite migration:
   ```sql
   CREATE TABLE IF NOT EXISTS audit_log (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     ts TEXT NOT NULL,
     user TEXT,
     action TEXT,
     payload_json TEXT,
     ip TEXT
   );
   CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts);

   CREATE TABLE IF NOT EXISTS patient_consents (
     id INTEGER PRIMARY KEY AUTOINCREMENT,
     patient_id TEXT NOT NULL,
     consent_type TEXT NOT NULL,
     consent_given INTEGER DEFAULT 0,
     consent_text TEXT,
     given_at TEXT,
     withdrawn_at TEXT,
     signed_by TEXT
   );
   ```
2. `yazklinik_web.py`'a `web_audit_log(action, payload)` helper'i varsa kontrol et, yoksa ekle (audit_log tablosuna INSERT).
3. Migration script: `D:\YazKlinik_Final_D500\migrations\007_audit_consent.sql`
4. Test:
   ```powershell
   curl.exe -k https://127.0.0.1:5443/api/agents/compliance/run
   # grade C veya B beklenir (audit + consent ikisi de pass)
   ```

---

### GOREV 4: PWA ikon dosyalari (icon-192.png + icon-512.png) [10 dk]

**Amac**: `/manifest.webmanifest` referansi calissin (yoksa 404).

**Yapilacak**:
1. Tasarim: medical (asclepius/yilan-asa) + Y harfi, mavi-beyaz palet
2. 1024x1024 master PNG uret (DALL-E, Canva veya manuel)
3. `static/icons/` klasoru ac, iki boyut kaydet:
   - `static/icons/icon-192.png` (192x192)
   - `static/icons/icon-512.png` (512x512)
4. Browser test: `https://127.0.0.1:5443/manifest.webmanifest` -> Manifest viewer'da iconlar gorunmeli.

**Tavsiye**: ImageMagick:
```powershell
magick convert input.png -resize 192x192 static/icons/icon-192.png
magick convert input.png -resize 512x512 static/icons/icon-512.png
```

---

### GOREV 5: 2FA setup wizard UI (`/2fa-setup`) [25 dk]

**Amac**: Hekim TOTP 2FA'yi browser'dan kurabilsin.

**Dosya**: `yazklinik_agents_routes.py` icine yeni endpoint:
```python
@agents_bp.route("/2fa-setup", methods=["GET"])
def two_fa_setup_page():
    # render HTML: 1) Setup buton -> POST /api/agents/2fa/setup
    # 2) QR kod render (qrcode kutuphanesi var mi? yoksa otpauth URL kopyala butonu)
    # 3) 6 hane input -> POST /api/agents/2fa/enable
    # 4) Backup kodlari indir
```

**Adimlar**:
1. `pip install qrcode[pil]` (varsa atla)
2. HTML form: 3 step wizard (setup -> QR + scan + verify -> done)
3. Sayfa Backup codes'u dosyaya indirme link uretir
4. Test: `https://127.0.0.1:5443/2fa-setup` -> 3 step calismali, sonra `2fa.verify(...)` `True` donmeli.

---

### GOREV 6: Stok UI (`/stok`) [25 dk]

**Amac**: Hekim/asistan ilac stogunu browser'dan yonetebilsin.

**Dosya**: `yazklinik_agents_routes.py` icine yeni endpoint:
```python
@agents_bp.route("/stok", methods=["GET"])
def stok_page():
    # render HTML: 1) Liste tablo (alerts top - miat/azalan)
    # 2) "Yeni urun ekle" form (StockItem fields)
    # 3) "Hareket kaydet" form (in/out + adet)
```

**Adimlar**:
1. Tablo: GET `/api/agents/stok/report` -> render alerts + items
2. Form: POST `/api/agents/stok/upsert`
3. Hareket: POST `/api/agents/stok/movement`
4. Aylik tuketim grafik (Chart.js veya basit liste)
5. Test: `/stok` -> bir ornek ilac ekle, miat 20 gun -> alert listede gorunmeli.

---

### GOREV 7: Windows Task Scheduler 4 cron job [15 dk]

**Amac**: Otomatik gunluk gorevler calissin.

**Dosya**: `akillilik\scripts\INSTALL_CRON_TASKS_SESSION7.ps1` (yeni)

**Eklenecek 4 task**:
```powershell
# 1) Memnuniyet anket - her gun 09:00
Register-ScheduledTask -TaskName "YazKlinik_MemnuniyetSurvey" `
  -Trigger (New-ScheduledTaskTrigger -Daily -At 9:00am) `
  -Action (New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -Command `"Invoke-WebRequest -Method POST -Uri https://127.0.0.1:5443/api/agents/memnuniyet/survey-yesterday -SkipCertificateCheck`"")

# 2) Birthday tebrik - her gun 08:00
# 3) PubMed cron - her gun 07:00
# 4) Status check - her saat
```

**Onemli**: API'lar `_require_session` kullaniyor; cron icin alternatif olarak ya:
- Cron user oturum acsin (cookie file kullan)
- VEYA endpoint'lere `X-Cron-Token: <secret>` header dogrulamasi ekle (basit)

**Tavsiye**: Header secret yontemi, su sekilde:
```python
# yazklinik_agents_routes.py basina:
_CRON_TOKEN = os.environ.get("YAZKLINIK_CRON_TOKEN", "")
def _cron_auth_ok():
    return _CRON_TOKEN and request.headers.get("X-Cron-Token") == _CRON_TOKEN

# her cron endpoint'inde:
if not _cron_auth_ok():
    auth = _require_session()
    if auth: return auth
```

**Test**: Task Scheduler'da manuel "Run" et, hata oldumu kontrol.

---

## Test Komutlari (Genel)

```powershell
# 1) Module imports OK?
& "C:\Users\yazha\AppData\Local\Programs\Python\Python312\python.exe" -c "
import sys
sys.path.insert(0, r'D:\YazKlinik_Final_D500')
for m in ['yazklinik_compliance_agent', 'yazklinik_status_page_agent', 'yazklinik_phq9_agent']:
    __import__(m); print(m, 'OK')"

# 2) Server 5443 dinliyor mu?
Get-NetTCPConnection -LocalPort 5443 -ErrorAction SilentlyContinue

# 3) Public endpoints (auth yok):
curl.exe -k https://127.0.0.1:5443/api/status
curl.exe -k https://127.0.0.1:5443/status
curl.exe -k https://127.0.0.1:5443/manifest.webmanifest

# 4) Auth gerekli (401 doner - dogru):
curl.exe -k https://127.0.0.1:5443/api/agents/burnout/report
curl.exe -k -X POST https://127.0.0.1:5443/api/agents/voice-command/parse
```

---

## Sorun cikarsa

- **Import error**: `sys.path` icine `D:\YazKlinik_Final_D500` ekle
- **Flask register hatasi**: Blueprint adi `agents` cakisma yapiyor mu? `app.blueprints.keys()` ile bak
- **CRLF/LF warning**: Onemsiz, Git otomatik cevirir
- **Compliance hala F**: `audit_log` tablosu olusturuldu mu? `sqlite3 yazklinik_v68.sqlite3 ".tables"` ile bak
- **PWA install gozukmuyor**: HTTPS sart (zaten 5443 HTTPS), service worker root scope `/` olmali (zaten oyle)

---

## Bana Geri Donus

7 gorevi yaparken:
- Her gorev sonu kisa not yaz (`docs/CODEX_NOTES_2026-05-17.md` icine append)
- Eger `yazklinik_agents_routes.py`'a degisiklik yaptiysan, **commit mesaji** "codex: <gorev> tamam" formatinda olsun
- Eger conflict cikarsa, **Hakan'a sor**, otomatik resolve etme

Iyi calismalar Codex! 7 gorev = ~2 saat. Bittiginde gerekirse 8. gorev (Konsey + PHQ-9 UI) opsiyonel.

â€” Claude (Session 7 sonunda yazdi)

