# Codex - Basla Buradan

Klasor:

```text
D:\YazKlinik_Final_D300
```

Bu D300 surumu, D200 son calisan halinden uretilmis yeni calisma kopyasidir.
Ilk is olarak `AGENTS.md` ve `D300_HANDOFF.md` oku.

## Komutlar

Baslat:

```powershell
D:\YazKlinik_Final_D300\D300_BASLAT.bat
```

Test:

```powershell
Set-Location "D:\YazKlinik_Final_D300"
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" -m py_compile yazklinik_web.py yazklinik_v68.py yazklinik_feature_sync.py D300_TERMINAL_SYNC.py
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" CODEX_QUICK_CHECK.py
```

Beklenen:

```text
CODEX_D300_QUICK_CHECK_OK
```

## Son degisiklikler

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
    - Codex: `yazklinik_sip_alex_client.py` (SIP bridge), `D300_SERVICE_RUNNER.py`, `D300_SIP_ALEX_BASLAT.bat` (sessiz baslatma).
    - **P0 DONE:** `doktor/1234` artik gecersiz; yeni lokal parola `users.json` + `runtime_state/D300_DOKTOR_YENI_SIFRE_*.txt` icinde, git'e alinmaz.
    - **P1 DONE:** SIP bridge gelen cagri STT metnini `yazklinik_telesekreter_agent.parse_call()` ile triyaj eder.
- **2026-05-16 (ogleden sonra):** 3 yeni ajan + 1 buyuk fix + 2 UX iyilestirme. Detayli handoff: **`CODEX_HANDOFF_2026-05-16_SESSION2.md`**.
    - YZ Konsultasyon ajani (`/yz-konsultasyon`) - 5-step OB-GYN klinik karar destek
    - Tibbi Ceviri ajani (`/ceviri-merkezi`) - PubMed + qwen2.5:32b yerel
    - Instagram Hazirlik ajani (`/instagram-hazirla`) - USG arsivinden KVKK-anonim draft
    - **fix(voluson):** USG PDF importu artik yas/kilo/boy/TA/LMP de visits + patient_demographics'a yazar
    - Medikal tema CSS overlay (additive)
    - Alex bar suruklenebilir + 9 preset + Alt+A/M/C kisayollari
    - MANIFEST_VERSION -> 2026.05.16-D300-AGENTS-IG-CEVIRI-KONSULT
- **2026-05-16 (sabah):** 10 klinik ajan eklendi (telesekreter / sesli onay / USG rapor / geri cagirma / BK sync bekci / NAS izleyici / recete / gunluk ozet / mojibake bekci / PR reviewer). `/ajanlar` dashboard + `/api/agents/*` Blueprint. Detayli handoff: **`CODEX_HANDOFF_2026-05-16_AJANLAR.md`**. v68 ve mevcut route'lar dokunulmadi.
- WebShell hizli Chrome/Edge app-mode kabuga tasindi.
- WebShell fast-mode algilamasi user-agent ve `yk_webshell=1` ile garanti edildi.
- Mod secimi ve tema secimi ust menude tekrar calisir.
- D300 config, DB ve backup yollari ayrildi.


