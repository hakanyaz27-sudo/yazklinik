# CODEX HANDOFF — Session 2 (2026-05-16 - oğleden sonra)

**Branch:** `claude/friendly-khayyam-672aff` (PR: https://github.com/hakanyaz27-sudo/yazklinik/compare/d300-safe-initial...claude/friendly-khayyam-672aff)

**Onceki handoff:** [`CODEX_HANDOFF_2026-05-16_AJANLAR.md`](CODEX_HANDOFF_2026-05-16_AJANLAR.md) — ilk 10 ajan + Blueprint wire-up.

Bu handoff o donumundan sonra eklenen **6 commit**'i kapsar: Medikal tema, Alex bar positioner, Instagram ajani, Tibbi ceviri ajani, YZ Konsultasyon ajani, Voluson PDF -> hasta dosyasi fix.

---

## TL;DR — Bu session'da neler degisti

| # | Commit | Konu | Etki |
|---|---|---|---|
| 1 | `5f67c3b` | **Medikal tema CSS overlay** | Hasta listesi/kart/toolbar guzellesir; dark mod korunur |
| 2 | `8f7acf3` | **Alex bar positioner** | Bar suruklenebilir + 9 preset + Alt+A/M/C kisayollari |
| 3 | `5d4fd3d` | **Instagram Hazirlik Ajani** | USG arsivinden anonim/iyilestirilmis IG draft uretir |
| 4 | `b77fa35` | **Tibbi Ceviri Ajani** | PubMed + qwen2.5:32b yerel + ChatGPT prompt fallback |
| 5 | `dd08b5e` | **YZ Konsultasyon Ajani** | 5-step OB-GYN klinik karar destek (extract -> DDx -> tetkik -> tedavi -> takip) |
| 6 | `252eece` | **fix(voluson): USG PDF -> visits + demographics** | BPD/AC/FL disinda yas/kilo/boy/TA/LMP de gelisler sayfasinda + hasta kartinda gozukur |

**Toplam:** 3 yeni ajan modulu (`yazklinik_*_agent.py`), 1 yeni Blueprint endpoint cluster, 1 buyuk bugfix, 1 yeni static CSS, 1 yeni static JS, 3 yeni dashboard sayfasi (`/ajanlar`, `/instagram-hazirla`, `/ceviri-merkezi`, `/yz-konsultasyon`).

---

## 1) Medikal Tema CSS Overlay (`5f67c3b`)

**Dosyalar:** `static/yk-medical-theme.css` (yeni, 437 satir), `yazklinik_web.py` (+17 satir inject hook)

**Ne yapar:** `yk-executive-polish.css` ile ayni desende, mevcut sayfaya **uzerine binme** stilleri ekler:
- Hasta kartlari: brans bazli sol-kenar renkli serit (jinekoloji=rose, obstetrik=teal, gebelik=violet, dogum=green)
- Avatar dairesi: gradient + ring + glow
- "Bugun geldi" rozeti: yesil animasyonlu nabız noktasi (1.8s)
- Stat kartlar: hover lift + soft gradient
- Arama cubugu: focus'ta medikal mavi 4px halka
- Grid/Liste toggle: aktif state gradient pill
- Top header: glassmorphism (backdrop-blur)
- Tum kurallar `html:not([data-theme="dark"])` prefiksi -> dark mod KORUNUR
- `prefers-reduced-motion` + print stilleri var

**Inject:** web.py line ~41327 sonrasi 17 satirlik try/except (executive-polish ile ayni pattern). CSS yuklenemese sayfa acilir.

**Kaldirma:** `static/yk-medical-theme.css`'yi sil + `web.py`'daki inject bloğunu sil; tum sayfalar eski haline doner.

---

## 2) Alex Bar Positioner (`8f7acf3`)

**Dosyalar:** `static/yk-alex-positioner.js` (yeni, 348 satir), `yazklinik_web.py` (+18 satir inject hook)

**Ne yapar:** Mevcut `#ykVoiceAgent` (Alex alt bar) markup'ina dokunmadan DOM'a 2 dugme + drag listener ekler.

**Yeni dugmeler:**
- `⋮⋮` grip (sol bas): mouse ile suruklenir, cift tik = varsayilan konum
- `☰` menu butonu (× kapatma butonundan once): 9 preset gosterir

**Konum presetleri:** Merkez Alt (varsayilan), Merkez Ust, 4 kose, Tam Merkez, Mini (sadece FAB), Tam Gizle.

**Klavye kisayollari:** `Alt+A` goster/gizle, `Alt+M` mini moda, `Alt+C` bara odaklan.

**Hafiza:** `localStorage["ykAlexPosition"] = {preset, x, y}` — tarayici hatirlar.

**Snap:** kose/orta cizgisine yakin birakilirsa otomatik preset'e snap.

**Mobil:** `<600px` ekran -> drag kapali (mevcut sticky alt davranisi korunur).

**Public API:** `window.ykAlexPositioner.apply('preset-key')`, `.load()`, `.save()`.

---

## 3) Instagram Hazirlik Ajani (`5d4fd3d`)

**Dosyalar:** `yazklinik_instagram_agent.py` (yeni, 468 satir), `yazklinik_agents_routes.py` (+~280 satir), `yazklinik_integration_agents.py` (+1 ajan), `yazklinik_feature_sync.py` (+1 menu).

**Ne yapar:** Voluson NAS / herhangi klasoru tarar, en guzel goruntuleri 6 metrikli skorla siralar, doktor secer, anonimleştirir + iyilestirir + Instagram boyutlarinda drafta kaydeder.

**Skor formulu:**
- Sharpness (Laplacian variance) %30
- Resolution %20
- Aspect ratio fit %15
- Recency %15
- File size %10
- Filename hints %10

**Anonimlestirme (KVKK kritik):**
- Default ust strip kirpilir (%13) — USG cihazinin hasta bilgi seridi
- Slider ile daha agresif kirpma + alt kose blur opsiyonu
- Otomatik post atma YOK - sadece `instagram_drafts/` klasorune yazar
- Path-traversal koruma: `YAZKLINIK_NAS_ROOT` + proje koku disindaki istekler 403

**Endpoints:**
| Method | Route | Is |
|---|---|---|
| POST | `/api/agents/instagram/scan` | Klasor tara |
| GET | `/api/agents/instagram/thumbnail?path=...&size=320` | Guvenli thumbnail |
| POST | `/api/agents/instagram/enhance` | Iyilestir + drafta yaz |
| POST | `/api/agents/instagram/caption` | Caption + hashtag uret |
| GET | `/api/agents/instagram/draft-download?file=...` | Drafttan indir |
| GET | `/instagram-hazirla` | Tam UI |

**UI:** 3 panel - sol scan, orta aday grid (thumbnail+skor), sag iyilestirme slider + caption.

**Bagimliliklar:** Pillow 12.2, numpy 2.4, fitz (PyMuPDF) - zaten yukluler.

---

## 4) Tibbi Ceviri Ajani (`b77fa35`)

**Dosyalar:** `yazklinik_ceviri_agent.py` (yeni, 529 satir), `yazklinik_agents_routes.py` (+~488 satir), `yazklinik_integration_agents.py` (+1 ajan), `yazklinik_feature_sync.py` (+1 menu).

**Ne yapar:** Ingilizce PubMed makalesi cek + Turkce ceviri + 3-5 madde ozet.

**LLM zinciri (oto fallback):**
1. **Ollama yerel** (qwen2.5:32b varsayilan - config.env'den okur)
2. **OpenAI** (OPENAI_API_KEY env varsa)
3. **Prompt-only** mod - LLM yoksa ChatGPT'ye yapistirilacak prompt cikti

**PubMed:** NCBI E-utilities (API key gerekmez, ucretsiz). esearch + esummary + efetch.

**Glossary:** 60+ OB-GYN terimi (preeklampsi, GDM, hCG, PCOS, IUGR, vs.) ceviri promptuna otomatik eklenir.

**Endpoints:**
| Method | Route | Is |
|---|---|---|
| GET | `/api/agents/ceviri/health` | LLM durumu |
| POST | `/api/agents/ceviri/pubmed-search` | Sorgudan PMID listesi |
| POST | `/api/agents/ceviri/pubmed-fetch` | PMID -> makale |
| POST | `/api/agents/ceviri/translate` | Metin ceviri (oto fallback) |
| POST | `/api/agents/ceviri/summarize` | TR 3-5 madde ozet |
| POST | `/api/agents/ceviri/translate-pubmed` | PMID -> fetch + ceviri + ozet + markdown |
| POST | `/api/agents/ceviri/prompt` | LLM cagirma, ChatGPT icin prompt |
| GET | `/ceviri-merkezi` | Tam UI |

**UI:** Sol kaynak (PubMed sorgu/PMID/serbest metin), sag yan yana EN | TR + ozet, Markdown indir / Alex'e gonder.

**Gizlilik:** Ollama yerel = hasta verisi PC'den cikmaz (default).

---

## 5) YZ Konsultasyon Ajani (`dd08b5e`) - "cok zeki" konsultasyon

**Dosyalar:** `yazklinik_konsult_agent.py` (yeni, 583 satir), `yazklinik_agents_routes.py` (+~400 satir), `yazklinik_integration_agents.py` (+1 ajan), `yazklinik_feature_sync.py` (+1 menu).

**Ne yapar:** Doktor vaka tarifi yazar -> 5 adimli AYRI LLM cagrisi zinciri:

1. **EXTRACT**: serbest metni JSON yapilandirir (yas, gravide, gebelik haftasi, vitaller, sikayet, **eksik kritik bilgi**)
2. **DDx**: 5-8 ayirici tani + ICD-10 + olasilik (high/med/low) + lehine/aleyhine bulgular + dogrulama adimi + **kirmizi alarmlar**
3. **WORKUP**: onerilen lab/imaging/exam/history + priority (urgent/priority/routine) + beklenen sonuc
4. **TREATMENT**: 1.basamak/2.basamak/alternatif + doz + gebelik FDA kategorisi + kontrendikasyon
5. **FOLLOW-UP**: aralik + izlenecekler + acilen donulmesi gereken alarmlar + hasta egitimi

**Persona prompt:** "25 yillik OB-GYN konsultani, ACOG/RCOG/TJOD bilir, TITCK ilac katalogunu bilir, KVKK uyumlu, oneri tonu (klinik karar doktorundur)".

**Gebede X-kategori ilac:** persona promptunda **explicit yasak**.

**Guven hesabi:** errors yoksa + DDx>=3 + workup>=2 + treatment>=1 = **high**.

**Endpoints:**
| Method | Route | Is |
|---|---|---|
| GET | `/api/agents/konsult/health` | LLM durumu |
| POST | `/api/agents/konsult/extract` | Sadece vaka yapilandir (hizli, 1 LLM cagrisi) |
| POST | `/api/agents/konsult/full` | 5-step tam zincir (~20-30 saniye yerel) |
| GET | `/yz-konsultasyon` | Tam UI |

**UI ozellikleri:**
- 4 ornek vaka one-click (preeklampsi, PPH, PCOS, PID)
- Skeleton loader
- Renk kodlu rozetler: DDx (kirmizi/sari/yesil olasilik), Tetkik (acil/oncelikli/rutin), Gebelik kategorisi (mor)
- Kirmizi alarm kutusu en uste
- Markdown export + "Alex'e gonder"

**Reuse:** LLM cagrisi `yazklinik_ceviri_agent`'tan `_ollama_generate` ve `_openai_chat` import eder.

---

## 6) fix(voluson): USG PDF importu visits + demographics'a da yazar (`252eece`)

**Dosya:** `yazklinik_voluson.py` (+271 satir, sifir silme)

**Sorun:** Voluson PDF importu sadece `voluson_reports` tablosuna kayit yaziyordu. BPD/AC/FL gibi olcumler USG sayfasinda goruluyor ama hastanin **Gelisler** sayfasinda USG visit'i gozukmuyordu; demografik kartinda **yas/kilo/boy/TA bos** kaliyordu.

**Cozum:** `_sync_to_patient_records(con, data, patient_key, pdf_path)` helper'i eklendi; `import_pdf()`'in ayni transactionu icinde cagrilir.

**Visits tablosuna eklenen kayit:**
- `visit_type='usg'`, `source='voluson:auto'`
- `visit_date` = exam_date (PDF'den)
- `visit_key = "voluson-<md5(pdf_path)>"` -> IDEMPOTENT (ayni PDF tekrar import edilse duplicate yok)
- `examination` = kisa ozet: "USG (Voluson) - GA: 32w5d | EFW: 2100g | BPD: 80.5mm | ..."
- `notes` = uzun dokum: demografik+vital, gebelik, biyometri, doppler, klinik flag'ler

**patient_demographics.data_json'a merge:**
- `_set_if_empty()` ile **mevcut degerleri EZMEZ** (elle girilmis kilo varsa USG ezmez)
- Eklenenler: `age`, `birth_date`, `height/height_cm`, `weight/weight_kg`, `bmi`, `systolic_bp/diastolic_bp`, `ta` (string), `blood_pressure` (nested dict + recorded_at + source), `gravida`, `para`, `lmp`
- Farkli sayfalar farkli anahtar bekledigi icin **hem duz hem nested** yazilir.

**Defansif yaklasim:**
- `_table_exists()` + `_table_columns()` ile sema kontrolu
- Eksik kolon varsa o alan atlanir, hata firlatmaz
- Patient match yoksa sync sessizce gecer (sadece voluson_reports yazilir)
- Hata olursa con.commit() once rollback -> voluson_reports da yazilmaz

**Eski PDF'leri yeniden import:** `force=True` ile `/api/voluson/import` POST -> idempotent visit + demografik dolar.

**In-memory DB testi:**
```
Sync result: {'visit_written': True, 'demographics_updated': True, 'reason': ''}
2nd call: {'visit_written': False, 'demographics_updated': True}  (idempotent ✓)
Visit rows: 1 (1 olmali) ✓
Demografik: age=32, height=165, weight=72.5, ta=140/90, gravida=2, para=1 ✓
```

---

## TAM AJAN MANIFESTI (13 yeni / toplam 18)

Onceki seans + bu seansla birlikte registry'de 18 ajan var. Bu seansta eklenenler:

| # | id | Route | Risk | Modul |
|---|---|---|---|---|
| 11 | `instagram` | `/instagram-hazirla` | high | `yazklinik_instagram_agent` |
| 12 | `ceviri` | `/ceviri-merkezi` | low | `yazklinik_ceviri_agent` |
| 13 | `konsult` | `/yz-konsultasyon` | high | `yazklinik_konsult_agent` |

Onceki seanstaki 10: telesekreter, sesli_onay, usg_rapor, geri_cagirma, bk_sync_bekci, nas_yedek_izleyici, recete_hazirlayici, gunluk_ozet, mojibake_bekci, pr_reviewer.

Toplam 13 yeni endpoint cluster + 3 UI sayfa (`/ajanlar`, `/instagram-hazirla`, `/ceviri-merkezi`, `/yz-konsultasyon`).

**MANIFEST_VERSION:** `2026.05.16-D300-AGENTS-IG-CEVIRI-KONSULT`

---

## DEGISMEYEN / KORUNAN

- `yazklinik_v68.py` — tek bir karaktere bile dokunulmadi
- Mevcut `yazklinik_web.py` route'lari — hicbir biri silinmedi/degistirilmedi. web.py'a yalniz **3 kucuk try/except inject blok** eklendi (medical CSS, alex JS, agents blueprint register) + voluson_web.py icin **hicbir degisiklik**
- DB sema — hicbir tablo eklenmedi/duzenlenmedi. Sadece mevcut `visits` ve `patient_demographics`'a YAZIYORUZ
- Static CSS dosyalari (yk-core, yk-executive-polish, yk-premium, yk-pro-v3) — hicbiri silinmedi/duzenlenmedi
- Mevcut Alex bar JS/CSS — hic dokunulmadi

---

## CODEX ICIN NEXT-STEP ONERILERI (oncelikli)

1. **Twilio webhook -> telesekreter ajani** (P1)
   `POST /webhook/twilio/voice` -> `yazklinik_telesekreter_agent.parse_call()` -> onay kuyrugu SQLite.

2. **STT pipeline -> sesli_onay** (P1)
   `yazklinik_whisper_service.py` ile koprude `decide()` -> guven yuksekse direk randevu state degisikligi.

3. **`/hasta/<key>/usg-rapor-taslak` sayfasi** (P2)
   `usg_rapor_agent.build_draft()` ile interaktif form + canli preview.

4. **WhatsApp send pipeline -> geri_cagirma** (P2)
   `yazklinik_whatsapp_local_helper.py` cron + `ReminderJob.scheduled_for`.

5. **Voluson sync UI panel** (P2)
   `/voluson-import` sayfasinda her satira "Hasta dosyasina senkronla" butonu (mevcut PDF'ler icin force=True ile tekrar import).

6. **Konsultasyon -> hasta dosyasina ekleme** (P3)
   `/yz-konsultasyon` cikti -> `visits` tablosuna `visit_type='konsult'` olarak ekleyen buton.

7. **Cesitli ajanlar -> SQLite onay kuyrugu tablosu** (P3)
   Yeni tablo: `agent_review_queue (id, agent_id, payload_json, status, created_at, reviewed_by, action)`.
   Tum LLM-cikti ajanlari (telesekreter, sesli_onay, konsult, instagram, recete) buraya dusurur.

---

## ENTEGRASYON SECENEKLERI (Codex bu degisiklikleri nasil alir)

### Secenek A — PR Merge (en temiz)

```powershell
# 1. PR'i GitHub'da inceleyin:
# https://github.com/hakanyaz27-sudo/yazklinik/compare/d300-safe-initial...claude/friendly-khayyam-672aff
# 2. "Merge pull request" tikla (squash veya merge commit)
# 3. Codex tarafinda:
cd D:\YazKlinik_Final_D300
git checkout d300-safe-initial
git pull origin d300-safe-initial
# Restart server
D300_BASLAT.bat
```

### Secenek B — Branch'i direkt al (test icin)

```powershell
cd D:\YazKlinik_Final_D300
git fetch origin claude/friendly-khayyam-672aff
git checkout claude/friendly-khayyam-672aff
D300_BASLAT.bat
# Begenirsen merge et, begenmezsen geri don
```

### Secenek C — Cherry-pick (parca parca)

```powershell
git checkout d300-safe-initial
# Sadece Voluson fix'ini al:
git cherry-pick 252eece
# Sadece medikal temayi al:
git cherry-pick 5f67c3b
# ...
```

---

## VERIFY KOMUTLARI (her secenek sonrasi)

```powershell
# 1. Hizli kontrol
python CODEX_QUICK_CHECK.py

# 2. Manifest dogru mu
python -c "from yazklinik_feature_sync import MANIFEST_VERSION, FEATURE_GROUPS; print(MANIFEST_VERSION); print('AJANLAR:', len(dict(FEATURE_GROUPS).get('AJANLAR', ())))"
# Beklenen: "2026.05.16-D300-AGENTS-IG-CEVIRI-KONSULT"  /  "AJANLAR: 14"

# 3. Blueprint route count
python -c "from yazklinik_agents_routes import agents_bp; from flask import Flask; a=Flask('t'); a.register_blueprint(agents_bp); print(len([r for r in a.url_map.iter_rules() if r.endpoint.startswith('agents.')]))"
# Beklenen: 23+ (10 ajan x 1 endpoint + 5 IG endpoint + 7 ceviri + 3 konsult + 2 dashboard)

# 4. Yeni ajanlar import edilebilir mi
python -c "import yazklinik_instagram_agent, yazklinik_ceviri_agent, yazklinik_konsult_agent; print('OK')"

# 5. Voluson sync helper var mi
python -c "from yazklinik_voluson import _sync_to_patient_records; print('OK')"

# 6. Server baslat + sayfalari elle dene
D300_BASLAT.bat
# https://127.0.0.1:5443/ajanlar
# https://127.0.0.1:5443/yz-konsultasyon
# https://127.0.0.1:5443/ceviri-merkezi
# https://127.0.0.1:5443/instagram-hazirla
```

---

## VERSIYON BUMPLARI

| Dosya | Onceki | Yeni |
|---|---|---|
| `yazklinik_feature_sync.py` MANIFEST_VERSION | `2026.05.16-D300-AGENTS-WIRED` | `2026.05.16-D300-AGENTS-IG-CEVIRI-KONSULT` |
| `yazklinik_integration_agents.py` AGENT_VERSION | `2026.05.16-integration-agents` | `2026.05.16-integration-agents-ig-ceviri-konsult` |
| Yeni ajan modulleri | yok | hepsi `AGENT_VERSION = "2026.05.16-<id>"` |

---

## COMMIT'LER (kronolojik)

```
0a5a718  Add 10 klinik ajani (Session 1)
512eec7  Wire 10 klinik ajani: Blueprint (Session 1)
89b3b25  Codex handoff: 10 klinik ajan + Blueprint (Session 1)
5f67c3b  Medical theme CSS overlay (Session 2)
8f7acf3  Alex bar positioner (Session 2)
5d4fd3d  Instagram Hazirlik Ajani (Session 2)
b77fa35  Tibbi Ceviri Ajani (Session 2)
dd08b5e  YZ Konsultasyon Ajani (Session 2)
252eece  fix(voluson): USG PDF -> visits + demographics (Session 2)
```

---

## EKSILER / BILINEN SINIRLAR

- Konsultasyon ajaninin LLM cagrilari yerel Ollama'ya bagimli; Ollama down ise OpenAI yoksa hicbir cikti gelmez (UI prompt-only modunda calismaya devam eder ama Konsultasyon icin gercek cikti olmaz)
- Instagram ajaninin scan'i NAS uzerinde 5000+ dosya icin yavas olabilir (3-5 sn). max_files limiti `_walk_files` icinde 5000.
- Voluson fix idempotency `visit_key` kolonuna bagimli; o kolonu olmayan eski DB'lerde duplicate visit olabilir (ALTER TABLE ile kolon eklenir ama mevcut dataya retro-active uygulanmaz)
- Sayfalar mobil'de calisiyor ama Alex positioner'in drag'i 600px alti ekranlarda kapali; kucuk ekran kullanicisi konum degistiremez

---

## KVKK + ETIK UYUM

| Risk | Korunma |
|---|---|
| Hasta PII'si yabanci LLM'e | Ollama yerel default; OpenAI sadece doktor explicit secerse |
| USG goruntude hasta adi -> Instagram | Default ust strip kirpilir; UI'da buyuk KVKK uyari banneri |
| Otomatik post / otomatik recete | YOK - tum cikti "draft" / "oneri", doktor onayi gerekir |
| Hasta verisi silme | Voluson fix sadece YAZAR, hicbir kayit silinmez |
| Path traversal saldirisi | Instagram + Voluson endpoint'leri allowed root altinda |
| Klinik direktif tonu | Konsultasyon ajani persona promptunda "oneri" ifadesi zorunlu |

---

## SORU/SORUN AKARSA

- Konsultasyon ajani LLM bekleme suresi uzun -> qwen2.5:32b yerine `yaz:latest` veya kucuk model dene (UI'da LLM tercih dropdownu var)
- Instagram thumbnail'leri yuklenmiyor -> `YAZKLINIK_NAS_ROOT` env var dogru ayarlanmis mi kontrol et
- Voluson fix yeni hasta'da gozukmuyor -> `force=True` ile tekrar import et veya `match_patient()` cikti dogru mu kontrol et
- Medikal tema gozukmuyor -> `Ctrl+F5` ile tarayici cache temizle, `?v=d300-medical-2026-05-16` query string'i tarayici sevmemis olabilir

---

*Hazirlayan: Claude (Anthropic). Inceleme: Op. Dr. Hakan Yaz. Tarih: 2026-05-16.*
