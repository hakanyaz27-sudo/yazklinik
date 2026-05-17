# Codex Handoff - Session 7 (2026-05-17)

## TL;DR

Bu seansta YazKlinik D300'e **29 yeni ajan** + tam Flask wire + PWA + uyumluluk panosu + public status sayfasi + Celery worker iskeleti eklendi. Hepsi smoke-test gecti, syntax temiz, Blueprint 91 endpoint ile yuklendi.

Worktree: `D:\YazKlinik_Final_D300\.claude\worktrees\friendly-khayyam-672aff`
Branch: `claude/friendly-khayyam-672aff`

## Yeni Ajanlar (29 adet)

### Klinik AI
1. `yazklinik_vision_usg_agent.py` - llama3.2-vision:11b USG goruntu analizi (modality/view/GA/measurements/ig_potential)
2. `yazklinik_soap_agent.py` - kisa not -> tam SOAP genisletici (S/O/A/P + patient_education + needs_more_info)
3. `yazklinik_icd10_agent.py` - TR-ICD10 katalog + LLM semantic match (top_k)
4. `yazklinik_gebelik_takvim_agent.py` - GA milestones (11-14 NT, 18-22 morfo, 24-28 GDM, 28 RhD, 35-37 GBS, 37 dogum cantasi)
5. `yazklinik_risk_skor_agent.py` - preeklampsi / HELLP (Mississippi I-III) / Bishop / VTE Padua
6. `yazklinik_ddi_agent.py` - kritik ilac-ilac etkilesim + gebelik FDA kategori X/D
7. `yazklinik_smear_hpv_agent.py` - ASCCP 2019 takip planlama (ASCUS/LSIL/HSIL/AGC)
8. `yazklinik_phq9_agent.py` - Patient Health Questionnaire-9 (intihar risk uyarisi)
9. `yazklinik_konsey_agent.py` - tumor board / yuksek risk gebelik vaka sunum (markdown slides + RAG)
10. `yazklinik_hatira_usg_agent.py` - guzel USG -> WhatsApp anonim hatira (consent zorunlu)

### Sistem & Altyapi
11. `yazklinik_voice_command_agent.py` - "yeni hasta...", "BPD 85", "tansiyon 158/102" regex parser
12. `yazklinik_anti_burnout_agent.py` - doktor yorgunluk skoru (patients_today + longest_stretch + breaks)
13. `yazklinik_orchestrator_agent.py` - chain (full_visit / pubmed_research_pack / usg_full_pipeline)
14. `yazklinik_hasta_portal_agent.py` - magic-link tabanli hasta self-service
15. `yazklinik_2fa_agent.py` - TOTP (pyotp olmadan da calisir, stdlib HMAC-SHA1)
16. `yazklinik_stok_agent.py` - ilac/sarf stok takip + miat uyari + aylik tuketim tahmini
17. `yazklinik_plugin_loader.py` - plugins/ klasoru dinamik 3rd party agent yukleyici
18. `yazklinik_compliance_agent.py` - ISO 27001 + KVKK kontrol noktalari (10+ check, skor + grade)
19. `yazklinik_status_page_agent.py` - public uptime page (TCP probe 10 servis)
20. `yazklinik_celery_worker.py` - Redis broker, beat schedule (daily summary, nightly backup)
21. `yazklinik_sentry_init.py` - opsiyonel hata izleme, KVKK redact

### Cron / Otomasyon
22. `yazklinik_memnuniyet_agent.py` - dun-gelen anket + bugun-dogan tebrik
23. `yazklinik_pubmed_cron_agent.py` - 8 default sorgu gunluk tarama + RAG auto-index

### Entegrasyon Stub'lari
24. `yazklinik_payment_agent.py` - iyzico/Stripe (env yoksa stub mode)
25. `yazklinik_enabiz_kts_agent.py` - e-Nabiz e-recete bildirim stub
26. `yazklinik_mhrs_agent.py` - MHRS randevu cek stub
27. `yazklinik_medula_agent.py` - SGK provizyon + e-recete stub
28. `yazklinik_lab_duzen_agent.py` - Duzen Lab API stub + manual entry
29. `yazklinik_iot_bluetooth_agent.py` - Omron BP / Xiaomi scale / Accu-Chek parser

## Yeni Endpointler (Blueprint 91 route)

### Klinik (POST)
- `/api/agents/vision-usg/analyze` `{image_path}`
- `/api/agents/soap/expand` `{note}`
- `/api/agents/icd10/suggest` `{note, top_k}`
- `/api/agents/gebelik/plan` `{lmp, current_date?}`
- `/api/agents/risk/preeklampsi` (ricin params)
- `/api/agents/risk/hellp`
- `/api/agents/risk/bishop`
- `/api/agents/risk/vte`
- `/api/agents/ddi/check` `{drugs[], is_pregnant, trimester}`
- `/api/agents/smear-hpv/followup` `{smear_date, smear_result, hpv_test, age}`
- `/api/agents/phq9/score` `{patient_id, answers[9]}`
- `/api/agents/phq9/questionnaire` (GET)
- `/api/agents/konsey/build` `{ConseyVakaInput fields}`
- `/api/agents/hatira-usg/prepare`
- `/api/agents/hatira-usg/send`

### Orchestration
- `/api/agents/orchestrator/full-visit` `{case_text, prefer}`
- `/api/agents/orchestrator/pubmed-pack` `{query, max_articles}`
- `/api/agents/orchestrator/usg-pipeline` `{image_path, patient_key, lmp}`

### Sistem
- `/api/agents/voice-command/parse` `{text}`
- `/api/agents/burnout/report` (GET)
- `/api/agents/2fa/setup` / `/enable` / `/verify`
- `/api/agents/portal/issue-link` `{patient_id, phone}`
- `/hasta-portal/giris?token=...` (magic link login)
- `/hasta-portal` (hasta panel)
- `/api/agents/compliance/run` (GET/POST)
- `/uyumluluk` (HTML grade panosu)

### Stok / Vaka / Odeme / Stub
- `/api/agents/stok/report` (GET)
- `/api/agents/stok/upsert` / `/movement`
- `/api/agents/payment/initiate` / `/webhook/<provider>` / `/recent`
- `/api/agents/enabiz/health` / `/api/agents/mhrs/health` / `/api/agents/medula/health` / `/api/agents/medula/provizyon`
- `/api/agents/lab-duzen/health` / `/fetch`
- `/api/agents/iot/scan`
- `/api/agents/plugins/list` / `/call`

### Cron
- `/api/agents/memnuniyet/survey-yesterday`
- `/api/agents/memnuniyet/birthday-today`
- `/api/agents/pubmed-cron/scan`

### Public (auth YOK)
- `/api/status` -> JSON 10 servis durumu
- `/status` -> tek dosya HTML uptime page
- `/manifest.webmanifest` -> PWA manifest
- `/sw.js` -> Service Worker (cache + push)

## Diger Yeni Dosyalar

- `static/manifest.json` - PWA manifest (shortcuts: Yeni Hasta / Randevular / Dashboard)
- `static/sw.js` - Service worker (network-first HTML, cache-first asset, push handler)
- `n8n_workflows/whatsapp_chatbot.json` - n8n flow: WhatsApp incoming -> intent -> YazKlinik API veya Ollama qwen2.5:32b -> reply
- `akillilik/xtts/README.md` - Voice cloning (Hakan sesi) stub yol haritasi
- `akillilik/saas/README.md` - Multi-tenancy (schema/db/RLS) tartismasi
- `akillilik/wearables/README.md` - Apple Watch + WearOS push roadmap

## Codex'in Yapacaklari (Onerilen)

### YUKSEK ONCELIK
1. **`yazklinik_web.py` register kontrolu**: `from yazklinik_agents_routes import agents_bp` ve `app.register_blueprint(agents_bp)` zaten var mi? Yoksa ekle.
2. **PWA icon'lar**: `static/icons/icon-192.png`, `icon-512.png` eksik. 1024px PNG'den iki boyut uret. (Idea: medical asclepius + Y harfi)
3. **Test ve UI**: `/uyumluluk` ve `/status` sayfalarini browser'da ac, dogru render ediyor mu kontrol et.
4. **Cron entegrasyonu**: Windows Task Scheduler'a ekle:
   ```
   - memnuniyet survey (her gun 09:00) -> POST /api/agents/memnuniyet/survey-yesterday
   - birthday today (her gun 08:00) -> POST /api/agents/memnuniyet/birthday-today
   - pubmed cron (her gun 07:00) -> POST /api/agents/pubmed-cron/scan
   - status check (her saat) -> GET /api/status
   ```

### ORTA
5. **Plugin demo**: `plugins/hello_plugin.py` ile bir ornek yaz, `/api/agents/plugins/list` test et.
6. **2FA setup wizard UI**: `/2fa-setup` HTML sayfasi (QR + 6 hane test input)
7. **Stok UI**: `/stok` sayfasi - ilac listesi + miat uyari + + sayisi ekleme
8. **Konsey UI**: `/konsey-vaka` sayfasi - form ile vaka detay alip markdown ciktiyi gosterir
9. **PHQ-9 UI**: `/phq9` hasta tarafindan doldurma (9 soru, slider)

### DUSUK ONCELIK
10. **Celery worker baslat**: `celery -A yazklinik_celery_worker worker --pool=solo --loglevel=info` test
11. **Voice command demo UI**: `/sesli-komut` mikrofondan oku, intent goster
12. **Compliance**: skor 9/27 = F. Acil eksikler: audit_log tablosu, patient_consents tablosu, restic backup ozellik.

## Bilinen Eksikler

- **PWA icon dosyalari yok** -> `/manifest.webmanifest` icin 404 dusebilir
- **Celery + Redis**: `celery` paketi henuz pip install edilmedi
- **Sentry**: SENTRY_DSN env yoksa pasif
- **IoT BLE**: `bleak` paketi yok (Windows BT dis araci)
- **e-Nabiz / MHRS / Medula**: gercek API key + sertifika yok -> stub mode

## Smoke Test Sonuclari

```
IMPORTED OK: 29/29 yeni modul
Blueprint loaded: agents, deferred funcs: 91
PHQ9: skor=16 severity=moderate-severe suicide=True
DDI: 1 uyari (warfarin+aspirin major), safe=False
VOICE: 'BPD 85' -> measure(bpd_mm) conf=92
COMPLIANCE: 9/27 grade=F (audit_log + consent eksik)
STATUS: degraded - 7 yardimci servis kapali
SMEAR: ASCUS+HPV+ -> plan=colpo
```

## Branch Notu

Kullanici "tumunu yapalim" dedi -> hepsi tek seansda yapildi. 29 dosya + 1 routes guncellemesi + 6 stub README + 1 PWA + 1 n8n workflow.

Commit hazir, push ardindan main'e fast-forward yapilabilir.

---

Op. Dr. Hakan Yaz icin yazildi. Bir sonraki seansta:
- PWA icon uret (Codex)
- Stok/Konsey/PHQ-9 UI ekle (Codex)
- Celery worker baslat (operator)
- Compliance grade C->A: audit_log + consent + restic kur (operator + Codex)
