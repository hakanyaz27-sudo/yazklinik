# CODEX HANDOFF â€” Session 4 (2026-05-17) - Akillilik Paketi

**Branch:** `d700-safe-initial` (Claude tarafindan fast-forward push edildi)
**Onceki:** [SESSION3](CODEX_HANDOFF_2026-05-16_SESSION3.md) -> [SESSION2](CODEX_HANDOFF_2026-05-16_SESSION2.md) -> [AJANLAR](CODEX_HANDOFF_2026-05-16_AJANLAR.md)

Bu seansta YazKlinik'in **AI omurgasi** tamamen yukseltildi:
- RAG: BGE-M3 + reranker (eski mpnet'ten 2x dogru)
- Konsultasyon: meditron:70b (Stanford tibbi LLM) klinik adimlarda otomatik secilir
- Arayuz: htmx + Alpine.js + Chart.js CDN inject
- Yeni Docker stack: Vaultwarden + Uptime Kuma + n8n + Open WebUI
- Tek tikla kurulum + dogrulama scriptleri

---

## YENI DOSYALAR

| Dosya | Konu |
|---|---|
| `akillilik/docker-compose.yml` | 4-servis stack (Vaultwarden 18443, Uptime Kuma 13001, n8n 15678, Open WebUI 13000) |
| `akillilik/INSTALL_AKILLILIK_PAKETI.ps1` | Master kurulum scripti (winget + pip + ollama + docker), default DryRun |
| `akillilik/VERIFY_AKILLILIK.ps1` | 6 kategoride 20+ test, yesil/kirmizi rapor |
| `akillilik/KLINIK_AKILLILIK_REHBERI.md` | Doktor rehberi: ne kazandin, kullanim ornekleri |
| `CODEX_HANDOFF_2026-05-17_SESSION4.md` | Bu dosya |

---

## DEGISTIRILEN DOSYALAR

### `yazklinik_rag.py`
- `EMBED_MODEL` default: `BAAI/bge-m3` (eskiden mpnet)
- Yeni: `RERANKER_MODEL = BAAI/bge-reranker-v2-m3`
- Yeni `_get_reranker()` lazy loader (paket yoksa None doner, sessiz)
- Yeni `rerank_results(query, results, top_k)` fonksiyonu
- `search()` yeni parametre: `use_reranker`, `fetch_k` (varsayilan 15)
- 2-asama: retrieve (gevsek threshold) -> rerank (sert siralama)
- ENV ile ezilebilir: `ALEX_EMBED_MODEL`, `ALEX_RERANKER_MODEL`, `ALEX_USE_RERANKER=0`, `ALEX_RAG_THRESHOLD`, `ALEX_RAG_TOP_K`, `ALEX_RAG_RERANK_FETCH_K`

### `yazklinik_konsult_agent.py`
- VERSION -> `2026.05.17-konsult-v2`
- Yeni: `PREFERRED_MODELS_BY_STEP` sozlugu
  - extract: qwen2.5:32b, qwen2.5:72b, qwen3-coder:30b
  - ddx/workup/treatment: meditron:70b, qwen2.5:72b, qwen2.5:32b
  - followup: qwen2.5:32b, meditron:70b
- Yeni `_list_ollama_models()` cache (5 dk)
- Yeni `_pick_model_for_step(step)` mevcut modellerden ilk uygun olani secer
- `_llm_call(prompt, ..., step=...)` ek param
- Tum 5 step fonksiyonu (extract/ddx/workup/treatment/followup) step kimligini geciyor

### `yazklinik_web.py`
- Mevcut medikal-theme + alex-positioner inject'lerinden sonra:
  ```python
  # D700 2026-05-17: htmx + Alpine.js + Chart.js CDN
  if "yk-smart-ui-bundle" not in html:
      inject = ('<script id="yk-smart-ui-bundle">window.__ykSmartUI=1;</script>'
                '<script src="https://unpkg.com/htmx.org@1.9.12" defer></script>'
                '<script defer src="https://unpkg.com/alpinejs@3.13.10/dist/cdn.min.js"></script>'
                '<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js" defer></script>')
  ```
- 11 satir net ekleme, mevcut sayfalar etkilenmiyor

---

## DOCKER STACK ICERIGI

```
akillilik/
  docker-compose.yml         # 4 servis tek dosyada
  INSTALL_AKILLILIK_PAKETI.ps1  # winget + pip + ollama + docker bundle
  VERIFY_AKILLILIK.ps1       # 20+ test
  KLINIK_AKILLILIK_REHBERI.md
  data/                      # gitignore, container volume mount
    vaultwarden/
    uptime-kuma/
    n8n/
    open-webui/
  .env                       # install script tarafinda generate (admin token)
```

**Servisler:**
| Container | Port | Image | Volume |
|---|---|---|---|
| yk-vaultwarden | 18443 | vaultwarden/server:latest | ./data/vaultwarden |
| yk-uptime-kuma | 13001 | louislam/uptime-kuma:1 | ./data/uptime-kuma |
| yk-n8n | 15678 | docker.n8n.io/n8nio/n8n:latest | ./data/n8n |
| yk-open-webui | 13000 | ghcr.io/open-webui/open-webui:main | ./data/open-webui |

Open WebUI -> host.docker.internal:11434 ile Ollama'ya baglanir.

---

## NASIL CALISTIRMA

```powershell
cd D:\YazKlinik_Final_D500\akillilik

# 1. Once dry-run gor:
.\INSTALL_AKILLILIK_PAKETI.ps1
# Ne yapilacagini gosterir, hicbir sey kurmaz.

# 2. Gercekten kur:
.\INSTALL_AKILLILIK_PAKETI.ps1 -Run
# 30-60 dk: winget app, pip pkg, ollama pull (medgemma 17 GB), docker stack up.

# 3. Belli bolumleri atla:
.\INSTALL_AKILLILIK_PAKETI.ps1 -Run -SkipOllama
.\INSTALL_AKILLILIK_PAKETI.ps1 -Run -SkipDocker -SkipWinget

# 4. Dogrula:
.\VERIFY_AKILLILIK.ps1
# 6 kategoride 20+ test, OK/XX raporu, sonunda yesil cikti.
```

---

## YENI ENV DEGISKENLERI (opsiyonel)

```powershell
# RAG
$env:ALEX_EMBED_MODEL = "BAAI/bge-m3"               # default
$env:ALEX_RERANKER_MODEL = "BAAI/bge-reranker-v2-m3"
$env:ALEX_USE_RERANKER = "1"                         # 0=kapali
$env:ALEX_RAG_THRESHOLD = "0.7"                      # gevsek retrieve
$env:ALEX_RAG_TOP_K = "5"                            # son cikti
$env:ALEX_RAG_RERANK_FETCH_K = "15"                  # ilk asama N

# YazKlinik server restart sonrasi geceriz olur.
```

---

## VERIFY KOMUTLARI (Codex icin)

```powershell
# Hizli kontrol
python -c "import yazklinik_rag as r; print('RAG:', r.EMBED_MODEL, '/ reranker:', r.USE_RERANKER)"
# Beklenen: RAG: BAAI/bge-m3 / reranker: True

python -c "import yazklinik_konsult_agent as k; print(k.AGENT_VERSION); print(k._pick_model_for_step('ddx'))"
# Beklenen: 2026.05.17-konsult-v2 / meditron:70b

# Docker stack
docker compose -f akillilik/docker-compose.yml ps
# Beklenen: 4 container yk-vaultwarden / yk-uptime-kuma / yk-n8n / yk-open-webui

# Full verify
.\akillilik\VERIFY_AKILLILIK.ps1
```

---

## ETKI / METRIKLER

| Metrik | Once | Sonra |
|---|---|---|
| RAG embed model | paraphrase-mpnet (2 yillik) | BGE-M3 (SOTA) |
| RAG threshold | tek asama | 2-asama (retrieve + rerank) |
| Konsultasyon model | qwen2.5:32b (genel) | meditron:70b (tibbi) klinik adimlarda |
| Sifre yonetimi | doktor/1234 | Vaultwarden self-host (random) |
| Servis monitoring | yok | Uptime Kuma dashboard |
| Workflow otomasyon | yok | n8n (400+ entegrasyon) |
| Ollama UI | yok | Open WebUI (ChatGPT-vari) |
| Arayuz reactive | bos | htmx + Alpine.js + Chart.js |

---

## CODEX ICIN NEXT-STEPS (siralanmis)

1. **n8n ilk workflow** (P1)
   "Yeni randevu -> 24h sonra WhatsApp hatirlatma" workflow'unu n8n'de kur
   (YazKlinik webhook + Twilio/WhatsApp Business node)

2. **Open WebUI'da custom prompt** (P1)
   Open WebUI'da "Klinik konsultasyon" promptu olustur (system message =
   yazklinik_konsult_agent.PERSONA), favori model meditron:70b

3. **Uptime Kuma watch list** (P1)
   YazKlinik 5443, Ollama 11434, Whisper 9000, Public Funnel watch ekle,
   Discord/Telegram push bildirim ayarla

4. **RAG: alex_facts -> Vaultwarden notes** (P2)
   Doktorun ezberlettigi facts'ler Vaultwarden secure notes'a yedeklesin

5. **n8n + SIP bridge** (P2)
   `yazklinik_sip_alex_client.py` webhook'u n8n'e bagla, n8n trigger ile
   telesekreter_agent'i cagir, sonra n8n WhatsApp/SMS yaniti

6. **Restic backup baslat** (P2)
   Restic ile `rag_data/`, `local_db/`, `akillilik/data/` yedek hattini kur
   (gunluk artimli, sifreli)

7. **Open WebUI -> RAG entegre** (P3)
   Open WebUI'nin built-in RAG'i var; YazKlinik ChromaDB'sini ona bagla
   (paylasilan collection)

---

## COMMIT'LER (kronolojik, son 5)

(Push edilince burayi guncelle)
```
xxxxxxx  Session 4: Akillilik paketi (BGE-M3 + meditron + docker stack)
f827383  Session 3 handoff: uzaktan erisim + SIP bridge entegrasyon notu
671ead4  Merge Codex (Session 3): Alex SIP bridge + bg silencing
98f1888  Uzaktan erisim altyapisi: ProxyFix + Tailscale Funnel rehberi
5daf58a  Add Alex SIP phone bridge (Codex)
```

---

## RISKLER / DIKKAT EDILECEKLER

- **BGE-M3 ilk yuklemede 570 MB download** - normal, sonra cache
- **meditron:70b 42 GB VRAM**: RTX 5090 (32 GB) icin gpu_layers ile bolunur, ilk istek yavas (~15 sn warmup)
- **Open WebUI WEBUI_AUTH=true**: ilk admin hesabini kuruncaya kadar sign-up'a kapali. Kur, sonra `ENABLE_SIGNUP=false` yap
- **n8n credentials**: ilk owner hesabi olusturulur, 2FA opsiyonel onerilir
- **Vaultwarden SIGNUPS_ALLOWED=true** ilk hesap icin; doktor giris yaptiktan sonra `false` yapilmali (admin panelinden)
- **Docker stack data klasoru** `gitignore` listesinde olmali (su an gitignore yok)

---

## OZET

Bu seansta:
- 5 yeni dosya (docker-compose + 2 ps1 + 2 md)
- 3 mevcut dosya yukseltildi (rag, konsult, web)
- Hicbir bozma yok, hicbir mevcut feature etkilenmedi
- Docker stack tek komutla 4 servis ayaga kalkar
- Verify scripti her sey saglikli mi kontrol eder

Doktor icin: `cd akillilik; .\INSTALL_AKILLILIK_PAKETI.ps1 -Run` ile ~1 saatte premium klinik AI platformuna donusur.

---

*Hazirlayan: Claude. Op. Dr. Hakan Yaz icin 2026-05-17.*


