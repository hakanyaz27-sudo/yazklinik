# Codex - Basla Buradan

Klasor:

```text
D:\YazKlinik_Final_D500
```

Bu D700 surumu, D700 son calisan halinden uretilmis yeni calisma kopyasidir.
Ilk is olarak `AGENTS.md` ve `D500_HANDOFF.md` oku.

## Komutlar

Baslat:

```powershell
D:\YazKlinik_Final_D500\D500_BASLAT.bat
```

Test:

```powershell
Set-Location "D:\YazKlinik_Final_D500"
& "D:\YazKlinik_Final_D500\.venv\Scripts\python.exe" -m py_compile yazklinik_web.py yazklinik_v68.py yazklinik_feature_sync.py D500_TERMINAL_SYNC.py
& "D:\YazKlinik_Final_D500\.venv\Scripts\python.exe" CODEX_QUICK_CHECK.py
```

Beklenen:

```text
CODEX_D500_QUICK_CHECK_OK
```

## Son degisiklikler

- **2026-05-17 (Session 7 SUPER PUSH):** 31 yeni ajan + Flask wire (93 endpoint) + PWA + uyumluluk panosu + status sayfasi + Codex 7 gorev tamam. Detay: **`CODEX_HANDOFF_2026-05-17_SESSION7.md`** + **`CODEX_GOREV_2026-05-17.md`**.
    - **Claude klinik AI (10):** vision_usg (llama3.2-vision), soap, icd10, gebelik_takvim, risk_skor (preeklampsi/HELLP/Bishop/VTE), ddi, smear_hpv, phq9, konsey, hatira_usg
    - **Claude sistem (11):** voice_command, anti_burnout, orchestrator (chain), hasta_portal (magic-link), 2fa (TOTP stdlib), stok, plugin_loader, compliance (ISO27001+KVKK), status_page, celery_worker, sentry_init
    - **Claude cron (2):** memnuniyet+birthday, pubmed_cron
    - **Claude stub (6):** payment (iyzico/Stripe), enabiz, mhrs, medula, lab_duzen, iot_bluetooth
    - **Claude sistem altyapisi (2):** db_migrate (11 idempotent tablo), backup_verify (restic+sqlite)
    - **Codex tamamlananlar:** /ajanlar dashboard kartlari + audit_log/consent migration + PWA ikonlari (192/512/1024) + /2fa-setup HTML + /stok HTML + INSTALL_CRON_TASKS_SESSION7.ps1 + X-Cron-Token endpoint korumasi
    - Public yeni: `/status` + `/api/status` + `/uyumluluk` + `/hasta-portal/giris?token=...` + `/manifest.webmanifest` + `/sw.js`
    - SAYISAL: 93 Blueprint endpoint, 31/31 modul import OK, Compliance F (33%) -> C (64.8%)
- **2026-05-17 (Session 6 - VeriDB):** PostgreSQL + Redis + MeiliSearch eklendi. Detay: **`CODEX_HANDOFF_2026-05-17_SESSION6.md`**.
    - 3 yeni Docker servis: yk-postgres (15432), yk-redis (16379), yk-meilisearch (17700)
    - 3 yeni Python agent + 9 yeni endpoint + `/veridb-merkezi` UI dashboard
    - MeiliSearch canli: 2964 hasta + 12790 gelis + 182 recete (typo tolerant arama)
    - PostgreSQL ready: schema kuruldu, migration helper (dry-run default)
    - Redis cache + 4 standart kuyruk (voice_confirm, geri_cagirma, telesekreter_triyaj, instagram_drafts)
    - VERIFY: 40/43 OK = %93
- **2026-05-17 (Session 5):** 18 madde tek seans. Detay: **`CODEX_HANDOFF_2026-05-17_SESSION5.md`**.
    - RAG hibrit (vektor + BM25) + citation tracking
    - Konsultasyon -> RAG (gecmis vakalar + PubMed inject)
    - PubMed ceviri otomatik RAG'a yazar; Voluson import RAG'a re-index
    - Yeni sayfa: `/hasta/<key>/usg-rapor-taslak` (canli Hadlock + hasta dosyasina ekle)
    - SIP cagri -> sesli_onay otomatik state degisir
    - 3 cron job (Restic daily, WhatsApp reminders, NAS health 6h) + INSTALL_CRON_TASKS.ps1
    - GitHub Actions PR reviewer + Cloudflare Tunnel rehberi
    - Mautic Docker, MedSAM/Axolotl stub, Twilio iskelet
- **2026-05-17 (Session 4):** **Akillilik Paketi** - AI omurgasi yukseltildi. Detayli handoff: **`CODEX_HANDOFF_2026-05-17_SESSION4.md`**.
    - RAG: `BAAI/bge-m3` + `BAAI/bge-reranker-v2-m3` (2-asama retrieve+rerank, eski mpnet'ten 2x dogru)
    - Konsultasyon: `meditron:70b` (Stanford tibbi LLM) klinik adimlarda otomatik secilir
    - Arayuz: htmx + Alpine.js + Chart.js CDN inject (mevcut sayfalar etkilenmiyor)
    - Docker stack: `akillilik/` altinda Vaultwarden + Uptime Kuma + n8n + Open WebUI
    - Tek tikla kurulum: `cd akillilik; .\INSTALL_AKILLILIK_PAKETI.ps1 -Run`
    - Dogrulama: `.\VERIFY_AKILLILIK.ps1` (20+ test)
    - Doktor rehberi: `akillilik/KLINIK_AKILLILIK_REHBERI.md`
- **2026-05-16 (aksam):** Uzaktan erisim altyapisi + Alex SIP bridge entegre edildi. Detayli handoff: **`CODEX_HANDOFF_2026-05-16_SESSION3.md`**.
    - Claude: `yazklinik_remote_access.py` (ProxyFix + audit) + `TAILSCALE_UZAKTAN_ERISIM.md` (kurulum rehberi). Public IP 176.236.92.142:65187 / Tailscale Funnel ikinci PC'den koprulenir.
    - Codex: `yazklinik_sip_alex_client.py` (SIP bridge), `D500_SERVICE_RUNNER.py`, `D500_SIP_ALEX_BASLAT.bat` (sessiz baslatma).
    - **P0 DONE:** `doktor/1234` artik gecersiz; yeni lokal parola `users.json` + `runtime_state/D500_DOKTOR_YENI_SIFRE_*.txt` icinde, git'e alinmaz.
    - **P1 DONE:** SIP bridge gelen cagri STT metnini `yazklinik_telesekreter_agent.parse_call()` ile triyaj eder.
- **2026-05-16 (ogleden sonra):** 3 yeni ajan + 1 buyuk fix + 2 UX iyilestirme. Detayli handoff: **`CODEX_HANDOFF_2026-05-16_SESSION2.md`**.
    - YZ Konsultasyon ajani (`/yz-konsultasyon`) - 5-step OB-GYN klinik karar destek
    - Tibbi Ceviri ajani (`/ceviri-merkezi`) - PubMed + qwen2.5:32b yerel
    - Instagram Hazirlik ajani (`/instagram-hazirla`) - USG arsivinden KVKK-anonim draft
    - **fix(voluson):** USG PDF importu artik yas/kilo/boy/TA/LMP de visits + patient_demographics'a yazar
    - Medikal tema CSS overlay (additive)
    - Alex bar suruklenebilir + 9 preset + Alt+A/M/C kisayollari
    - MANIFEST_VERSION -> 2026.05.18-D700-MENU-AGENTS-CLINICAL
- **2026-05-16 (sabah):** 10 klinik ajan eklendi (telesekreter / sesli onay / USG rapor / geri cagirma / BK sync bekci / NAS izleyici / recete / gunluk ozet / mojibake bekci / PR reviewer). `/ajanlar` dashboard + `/api/agents/*` Blueprint. Detayli handoff: **`CODEX_HANDOFF_2026-05-16_AJANLAR.md`**. v68 ve mevcut route'lar dokunulmadi.
- WebShell hizli Chrome/Edge app-mode kabuga tasindi.
- WebShell fast-mode algilamasi user-agent ve `yk_webshell=1` ile garanti edildi.
- Mod secimi ve tema secimi ust menude tekrar calisir.
- D700 config, DB ve backup yollari ayrildi.




