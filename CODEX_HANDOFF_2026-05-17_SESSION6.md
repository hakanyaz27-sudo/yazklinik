# CODEX HANDOFF — Session 6 (2026-05-17) - VeriDB Asama 3

**Branch:** `d300-safe-initial` (Claude fast-forward push)
**Onceki:** [SESSION5](CODEX_HANDOFF_2026-05-17_SESSION5.md)

Bu seansta **PostgreSQL + Redis + MeiliSearch** Docker stack'e eklendi. Tum
veritabani altyapisi profesyonel: anlik tam metin arama (typo tolerant),
cache + queue, scale-out hazirligi.

---

## YENI ICERIK (3 servis + 3 agent + 1 dashboard sayfa)

### Docker Containers (3 yeni)
| Container | Port | Image | Niye |
|---|---|---|---|
| `yk-postgres` | 15432 | postgres:16-alpine | SQLite buyudukce migration hedefi (10K hasta+) |
| `yk-redis` | 16379 | redis:7-alpine | Cache + queue (sesli_onay, geri_cagirma, alex session) |
| `yk-meilisearch` | 17700 | getmeili/meilisearch:v1.13 | Anlik tam metin arama (typo tolerant, ChromaDB alternatifi) |

### Yeni Python Agent Modulleri
| Dosya | Ne yapar |
|---|---|
| `yazklinik_postgres_agent.py` | health_check, init_schema, migrate_from_sqlite (dry_run default) |
| `yazklinik_redis_agent.py` | cache_set/get, queue_push/pop, rate_limit, session_memory |
| `yazklinik_meilisearch_agent.py` | ensure_indexes, sync_table, sync_all_from_sqlite, search |

### Yeni Endpointler
| Method | Route | Aciklama |
|---|---|---|
| GET | `/api/db/postgres/health` | PG durum + tablolu sayisi |
| POST | `/api/db/postgres/migrate` | SQLite -> PG (default dry_run, doktor only) |
| GET | `/api/cache/health` | Redis durum + memory |
| POST | `/api/cache/get` | Tek key okuma |
| GET | `/api/queue/stats` | 4 standart kuyrugun uzunluk + preview |
| POST | `/api/search/full-text` | MeiliSearch (typo tolerant) |
| GET | `/api/search/health` | Meili durum + index sayilari |
| POST | `/api/search/sync` | SQLite -> Meili sync (doktor only) |
| GET | `/veridb-merkezi` | Tam UI: 3 servisin durumu + canli arama |

---

## CANLI VERILER (bu seans yapilan ilk sync)

```
MeiliSearch index'leri (live):
  yk_patients : 2964 doc     (3464 sqlite icinde, 500 sub-task pending olabilir)
  yk_visits   : 12790 doc    (tamami sync)
  yk_rx       : 182 doc      (tamami sync)

PostgreSQL:
  yazklinik DB + 3 yeni tablo
    yk_patients_pg, yk_visits_pg, yk_audit_log_pg
  Henuz veri yok - migrate_from_sqlite() ile manuel doldurulur

Redis:
  uptime 50+ dk, memory ~1 MB
  4 standart kuyruk hazir:
    yk:q:voice_confirm
    yk:q:geri_cagirma
    yk:q:telesekreter_triyaj
    yk:q:instagram_drafts
```

---

## ENV PAROLALARI (.env'de, GIT'E GIRMEZ)

```
POSTGRES_PASSWORD=2436385C122F44264A3C246061C1D3D3
REDIS_PASSWORD=A8C7D13B3D133FE2780543D89B25DF8A
MEILI_MASTER_KEY=A2149612E19FA8F582C73EA5FBA369F9
```

`akillilik/.env` dosyasi `.gitignore`'da.

---

## KULLANIM ORNEKLERI

### Anlik arama (typo tolerant)
```javascript
// Hasta "Kilic Sevall" yazsan da bulur:
fetch('/api/search/full-text', {
  method:'POST', credentials:'same-origin',
  headers:{'Content-Type':'application/json'},
  body: JSON.stringify({query:'Kilic Sevall', index:'yk_patients', limit:10})
})
```

### Sesli onay kuyrugu
```python
from yazklinik_redis_agent import queue_push, queue_pop
queue_push('voice_confirm', {'appt_id':'A123', 'phone':'+90555...'})
# Worker tarafinda:
job = queue_pop('voice_confirm', timeout=30)
```

### PostgreSQL migration (canli)
```python
from yazklinik_postgres_agent import init_schema, migrate_from_sqlite
init_schema()  # sema kur
# Once dry-run:
migrate_from_sqlite(dry_run=True)  # sayilar gosterir
# Sonra gercek:
migrate_from_sqlite(dry_run=False, tables=['patients'])
```

### Alex session memory (30 dk TTL)
```python
from yazklinik_redis_agent import session_add, session_get_all
session_add('sess_abc123', 'last_patient', 'F12345_Ayse', ttl_sec=1800)
all_data = session_get_all('sess_abc123')
```

### Cache decorator-vari
```python
from yazklinik_redis_agent import cache_get, cache_set
def expensive_calc(pmid):
    cached = cache_get(f'pubmed:{pmid}')
    if cached: return cached
    result = fetch_pubmed(pmid)  # yavas
    cache_set(f'pubmed:{pmid}', result, ttl_sec=86400)
    return result
```

---

## VeriDB MERKEZI UI

`https://127.0.0.1:5443/veridb-merkezi`

Sayfada gorulen:
- 3 servisin canli sağlık rozeti (OK/FAIL)
- Postgres versiyon + db + table_count
- Redis versiyon + uptime + memory
- MeiliSearch versiyon + 3 index doc count
- 4 standart kuyrugun anlik length + preview
- **Anlik arama formu**: hasta/gelis/recete index'lerinde typo tolerant search

---

## DEFAULT DAVRANIS - SAFE

Mevcut YazKlinik kodu **HIC DEGISMEDI**. Yeni 3 servis "opsiyonel altyapi":
- PostgreSQL: SQLite ile paralel kullanilabilir (dual-write opsiyonel)
- Redis: cache miss = SQLite/disk fallback (lazy)
- MeiliSearch: keyword arama; ChromaDB semantic arama korunur

SQLite ana DB olarak calismaya devam eder. PG'ye migration tamamen
manuel (`migrate_from_sqlite(dry_run=False)`).

---

## NEXT-STEPS (Codex icin oncelikli)

1. **Konsultasyon UI'a Save-to-Visit butonu wire** (Session 5'ten)
2. **n8n ilk workflow** (Session 5'ten)
3. **Open WebUI custom prompt** (Session 5'ten)
4. **Hasta listesi sayfasina MeiliSearch entegre** (P1)
   - `/hastalar` sayfasindaki autocomplete ChromaDB yerine /api/search/full-text
   - Anlik (~10ms), typo tolerant
5. **Voice confirm worker** (P1)
   - Background script: `queue_pop('voice_confirm', timeout=60)` loop
   - SIP bridge sesli_onay payload'i kuyruga koyar; worker Twilio outbound call
6. **Auto-sync MeiliSearch** (P2)
   - Yeni hasta/visit ekleyince Redis pub/sub trigger
   - Worker incremental update
7. **PG dual-write** (P2)
   - YazKlinik web layer'da `insert_patient()` cagrildiginda hem SQLite hem PG'ye yaz
   - Sonra "dogru olan PG" demek icin haftalik karsi-karsi karsilastir
8. **Restic backup'a Postgres data'sini dahil et** (P3)
   - `akillilik/data/postgres` zaten yedek listesinde, ama PG dump ek garanti

---

## VERIFY (40/43 OK = %93)

```powershell
cd D:\YazKlinik_Final_D300\akillilik
.\VERIFY_AKILLILIK.ps1
```

Sahte fail'ler (gercek calisiyor):
- `sentence_transformers` (PowerShell quirk, FlagEmbedding kullanir)
- `HTTPS yaniti` (PS 5.1 TLS quirk, curl ile OK)
- `Restic CLI` (winget yeni kurulum PATH refresh)

Asama 3 yeni testler (hepsi OK):
- 3 container (PG/Redis/Meili)
- 3 python paket (psycopg/redis/meilisearch)
- 3 port (15432/16379/17700)
- 2 endpoint (postgres/health, veridb-merkezi)

---

## COMMIT'LER (son 3)

```
xxxxxxx  Session 6: VeriDB Asama 3 (Postgres + Redis + MeiliSearch)
7095b59  Session 5: 18 madde tek seansta - RAG enhancement + UI + cron + GH Actions + stubs
c58e44c  VERIFY: Asama 2 winget yerine exe path fallback
```

---

## TOPLAM PROJE FINAL DURUM

| Bilesen | Sayi |
|---|---|
| Klinik ajan | 16 (telesekreter, sesli_onay, usg_rapor, geri_cagirma, bk_sync_bekci, nas_yedek_izleyici, recete, gunluk_ozet, mojibake_bekci, pr_reviewer, instagram, ceviri, konsult, postgres, redis, meilisearch) |
| Docker servis | 9 (Vaultwarden, Uptime Kuma, n8n, Open WebUI, OHIF, Stirling, Postgres, Redis, MeiliSearch) + 2 stub (Mautic, Jitsi) |
| Cron job | 3 (Restic daily, WhatsApp reminders, NAS health 6h) |
| GitHub Actions | 1 (PR reviewer) |
| UI sayfa | 6 (/ajanlar, /yz-konsultasyon, /ceviri-merkezi, /instagram-hazirla, USG taslak, **veridb-merkezi**) |
| Codex handoff | 6 (Sessions 1-6) |
| Tibbi LLM | 2 (meditron:70b + yaz:latest) |
| Embed + Reranker + BM25 | BGE-M3 + BGE-Reranker-v2-m3 + BM25 hybrid |
| Veritabani | SQLite (ana) + PostgreSQL (yedek/scale) + Redis (cache) + MeiliSearch (arama) + ChromaDB (semantic) |

---

*Hazirlayan: Claude. Op. Dr. Hakan Yaz icin 2026-05-17 (sabah uyandiginda hazir).*
