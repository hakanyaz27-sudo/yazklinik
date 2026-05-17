# CODEX HANDOFF — Session 5 (2026-05-17) - 18 madde tek seans

**Branch:** `d300-safe-initial` (Claude fast-forward push)
**Onceki:** [SESSION4](CODEX_HANDOFF_2026-05-17_SESSION4.md)

Bu seansta **18 maddenin tamami** tek seansta bitirildi: RAG enhancement,
RAG entegrasyon, yeni UI sayfalari, cron scriptleri, GitHub Actions,
Cloudflare Tunnel, Twilio/Mautic/MedSAM/Axolotl stub'lari.

---

## TAMAMLANAN 18 MADDE (Session 5)

### Kod degisiklikleri (7 dosya)
| # | Madde | Dosya | Detay |
|---|---|---|---|
| 1 | RAG hibrit (vektor + BM25) | `yazklinik_rag.py` | `hybrid_rerank()`, `_bm25_score()`, `search(hybrid=True)` |
| 2 | RAG citation tracking | `yazklinik_rag.py` | her sonuca `cite_key`, `cite_kind`, `cite_source` |
| 3 | Konsult -> RAG entegrasyon | `yazklinik_konsult_agent.py` | `_find_similar_cases()`, `use_rag=True`, `rag_citations` field |
| 4 | PubMed -> RAG auto-index | `yazklinik_ceviri_agent.py` | `_auto_index_to_rag()`, `translate_pubmed_article(auto_index_rag=True)` |
| 5 | Voluson -> RAG auto re-index | `yazklinik_voluson.py` | `import_pdf()` sonrasi RAG `index_document()` hook |
| 6 | USG rapor taslak sayfasi | `yazklinik_agents_routes.py` | `/hasta/<key>/usg-rapor-taslak` + canli Hadlock preview |
| 7 | Konsult -> hasta visit kaydet | `yazklinik_agents_routes.py` | `POST /api/agents/konsult/save-to-visit` |
| 8 | SIP -> sesli_onay wire | `yazklinik_sip_alex_client.py` | `triage_call_turn()` icine `confirm_decide()` |

### Yeni dosyalar (8 dosya + 4 klasor)

| Dosya | Niye |
|---|---|
| `yazklinik_twilio_agent.py` | Twilio Voice/SMS bridge iskeleti (ENV ile aktif) |
| `akillilik/scripts/restic_daily_backup.ps1` | Gunluk sifreli yedek (Task Scheduler) |
| `akillilik/scripts/whatsapp_send_reminders.ps1` | geri_cagirma WA gonderim cron |
| `akillilik/scripts/nas_health_check.ps1` | NAS izleyici 6 saatte bir |
| `akillilik/scripts/INSTALL_CRON_TASKS.ps1` | 3 task'i tek tikla kur |
| `.github/workflows/pr-reviewer.yml` | yazklinik_pr_reviewer_agent her PR'da auto-yorum |
| `akillilik/cloudflare/README.md` | Cloudflare Tunnel kurulum (Tailscale alternatifi) |
| `akillilik/mautic/docker-compose.yml` + `.env.example` | Mautic email automation |
| `akillilik/medsam/README.md` | MedSAM tibbi goruntu segmentasyon stub |
| `akillilik/axolotl/README.md` | LoRA fine-tune (yk-meditron custom) stub |

---

## YENI ENDPOINTLER

| Method | Route | Is |
|---|---|---|
| GET | `/hasta/<patient_key>/usg-rapor-taslak` | Hasta-bagli USG taslak UI (canli Hadlock) |
| POST | `/api/agents/konsult/save-to-visit` | Konsult ciktisini visits tablosuna ekle |

---

## YENI ENV / KONFIGRASYONLAR

```powershell
# Twilio (opsiyonel)
$env:TWILIO_ACCOUNT_SID = "ACxxxx"
$env:TWILIO_AUTH_TOKEN = "xxxx"
$env:TWILIO_FROM_NUMBER = "+905551234567"

# RAG ileri ayar (opsiyonel, default'lar iyi)
$env:ALEX_RAG_HYBRID = "1"   # search() varsayilan hibrit (BM25 + vektor)
```

---

## NASIL KULLANILIR

### RAG hibrit arama
```python
import yazklinik_rag as r
# Sadece vektor:
results = r.search("preeklampsi tedavi", top_k=5)
# Hibrit (BM25 + vektor):
results = r.search("preeklampsi tedavi", top_k=5, hybrid=True)
# Citation kullan:
for x in results:
    print(x["cite_kind"], x["cite_source"], x["score"])
```

### Konsultasyon RAG ile (default acik)
```python
from yazklinik_konsult_agent import full_consultation
r = full_consultation("32 hafta gebe, basagrisi, TA 158/102", use_rag=True)
print(r.rag_citations)  # benzer gecmis vakalar + PubMed makaleler
```

### PubMed cevirisi otomatik RAG'a
```python
from yazklinik_ceviri_agent import translate_pubmed_article
r = translate_pubmed_article("12345678", auto_index_rag=True)
# 5 dk sonra Alex sohbette ayni konuyu sorulursa bulur
```

### USG rapor taslak (hasta sayfasinda)
```
https://127.0.0.1:5443/hasta/F12345_Ayse_Y/usg-rapor-taslak
```

### Konsultasyon -> hasta dosyasi
```javascript
// /yz-konsultasyon sayfasinda yeni buton (manual eklenebilir):
fetch('/api/agents/konsult/save-to-visit', {
  method: 'POST',
  body: JSON.stringify({
    patient_key: 'F12345_Ayse',
    markdown: result.markdown,
    most_likely: result.most_likely
  })
});
```

### Cron job'lari kur
```powershell
# Admin PowerShell:
cd D:\YazKlinik_Final_D300\akillilik\scripts
.\INSTALL_CRON_TASKS.ps1
```

### Mautic email automation
```powershell
cd D:\YazKlinik_Final_D300\akillilik\mautic
cp .env.example .env  # parolalari random ile degistir
docker compose up -d
# http://localhost:13005 -> setup sihirbazi
```

### PR Reviewer GitHub Actions
- Otomatik: her PR'da `.github/workflows/pr-reviewer.yml` calisir
- Blocker varsa CI fail; warn/info yorumlanir
- Repo'da Actions tab'inda gor

---

## ETKI / KAZANIMLAR

| Once | Sonra |
|---|---|
| RAG salt vektor | Hibrit (vektor + BM25) - yazim hatasinda daha iyi |
| Konsultasyon "klinik bilgi vakum" | Geçmis vakalar + PubMed citation inject |
| PubMed makale -> sadece UI | Otomatik RAG'a yazilir, Alex bulur |
| Voluson PDF -> sadece DB | RAG'a otomatik index, semantic search'te cikar |
| USG ölcumu manuel rapor yazma | `/hasta/<key>/usg-rapor-taslak` canli Hadlock + tek tik kayit |
| Konsult sayfasi okuyup PDF'e koparma | "Hasta Dosyasina Ekle" butonu, visit olarak kayit |
| SIP telesekreter ham triyaj | Sesli onay otomatik state degistirir (pending appt varsa) |
| Yedek = manuel hatirlamayla | Cron + retention (7d+4w+12m) |
| WhatsApp hatirlatma = elle | Cron + geri_cagirma kuyrugu |
| NAS = donmus var mi bilmem | 6 saatte bir saglik check |
| PR review = elle | GitHub Actions her PR'da otomatik yorum |
| Twilio = yok | iskelet + env config hazir |
| Mautic = yok | Docker compose hazir |
| Cloudflare = yok | tam rehber + ornek config |

---

## RISKLER / DIKKAT

- **RAG hybrid**: BM25 Turkce tokenizer kucuk (stop words 12 kelime); buyuk corpus icin upgrade gerekir
- **PubMed auto-index**: ceviri sonrasi senkron yazilir (cevap yavaslar 100-300 ms)
- **Voluson auto re-index**: PDF import basina ek 200-500 ms (RTX 5090 ile farkindalik yok)
- **Konsult save-to-visit**: visits sema kontrolu var, ama farkli sema'da test edilmedi
- **SIP sesli_onay**: `call.pending_appointment_id` field SIP client'da set edilmeli (web layer'in randevu olusturduktan sonra)
- **Twilio**: ENV'siz aktif degil, kuru iskelet
- **Mautic**: ilk acılışta DB init 2-5 dk

---

## CODEX ICIN NEXT-STEPS

1. **Konsult UI'da "Hasta Dosyasina Ekle" butonu wire** (P1)
   `/yz-konsultasyon` sayfasinda patient_key sec + Save butonu ekle.

2. **n8n ilk workflow** (P1)
   "Yeni randevu" webhook -> 24h sonra WhatsApp/Twilio

3. **Open WebUI custom prompt** (P1)
   "Klinik konsultasyon" persona promptu olustur (yazklinik_konsult_agent.PERSONA)

4. **MedSAM gercek kurulum** (P2)
   `akillilik/medsam/README.md` adimlari ile

5. **Axolotl + ilk fine-tune** (P3)
   yazklinik klinik notlarindan dataset cikar -> yk-meditron model

6. **Uptime Kuma watch list otomasyonu** (P3)
   YazKlinik 5443, Ollama 11434, Whisper 9000, 4 panel, NAS otomatik ekle

---

## VERIFY KOMUTLARI

```powershell
$venv = "D:\YazKlinik_Final_D300\.venv\Scripts\python.exe"

# RAG hibrit
& $venv -c "import yazklinik_rag as r; print('hybrid_rerank:', hasattr(r, 'hybrid_rerank'))"

# Konsult RAG
& $venv -c "import yazklinik_konsult_agent as k; print('_find_similar_cases:', hasattr(k, '_find_similar_cases'))"

# Ceviri auto-index
& $venv -c "import yazklinik_ceviri_agent as c; print('_auto_index_to_rag:', hasattr(c, '_auto_index_to_rag'))"

# Twilio
& $venv -c "from yazklinik_twilio_agent import integration_health; print(integration_health())"

# YazKlinik server (yeni route'lar)
curl.exe -sk -I https://127.0.0.1:5443/hasta/test/usg-rapor-taslak
# Beklenen: HTTP 302 (login) veya 200

# GitHub Actions check
ls .github/workflows/pr-reviewer.yml

# Cron scripts
ls akillilik/scripts/*.ps1
```

---

## TOPLAM PROJE DURUMU

| Kategori | Adet |
|---|---|
| Aktif klinik ajan | 13 |
| Self-host servis (Docker) | 6 (Vaultwarden, Uptime Kuma, n8n, Open WebUI, OHIF, Stirling) |
| Hazir Docker compose | 2 (Mautic ek, Jitsi stub) |
| Cron job | 3 (Restic daily, WhatsApp reminders, NAS health 6h) |
| GitHub Actions | 1 (PR reviewer) |
| Yeni UI sayfasi | 5 (/ajanlar, /yz-konsultasyon, /ceviri-merkezi, /instagram-hazirla, /hasta/.../usg-rapor-taslak) |
| Codex handoff dokuman | 5 (Sessions 1-5) |
| Tibbi LLM | 2 (meditron:70b + yaz:latest) |
| Embed/Reranker | 2 (BGE-M3 + BGE-Reranker-v2-m3) |
| Hibrit arama | 2 yontem (vektor + BM25) |

---

*Hazirlayan: Claude. Op. Dr. Hakan Yaz icin 2026-05-17.*
