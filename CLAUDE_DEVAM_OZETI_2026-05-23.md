# CLAUDE DEVAM OZETI (D700) - 2026-05-23

Bu not, Codex tarafinda yapilan performans odakli son degisiklikleri Claude'un hizli devralmasi icin hazirlandi.

## Kapsam
- Hedef: Hasta listesi/ana sayfa gecislerindeki yavasligi azaltmak, DB pool baskisini dusurmek.
- Dosya: `D:\YazKlinik_Final_D500\yazklinik_web.py`

## Bu turda yapilan degisiklikler

1. Render context cache eklendi (tekrarli context hesaplarini azaltmak icin)
- Global cache:
  - `_YK_RENDER_CONTEXT_CACHE = {"ts": 0.0, "mode": "", "data": None}`
  - `_YK_RENDER_CONTEXT_TTL = 90.0`
- Fonksiyon:
  - `def _yk_inject_experience_mode()` icinde TTL + mode bazli cache return eklendi.

2. Ops reconciliation ve pool davranisi hafifletildi
- `_ops_db_conn()` default wait fallback:
  - `4.0` -> `1.2` saniye
- `_ops_auto_reconciliation_before_request()`:
  - auth guard (session yoksa cik)
  - interval throttle (`YAZKLINIK_OPS_RECON_MIN_INTERVAL_SEC`, clamp 60..3600, default 300)
  - lock + son calisma zamani ile gereksiz tekrarlar azaltildi.

3. Hasta liste sorgu maliyeti dusuruldu
- `_load_patient_listing()`:
  - `query_limit = ... limit * 3` -> `limit * 2`

4. Dashboard hasta cekim yukleri dusuruldu
- `home()`:
  - `fetch_limit = min(1500, max(500, per_page * (page + 3)))`
  - yeni: `fetch_limit = min(900, max(280, per_page * (page + 2)))`

5. Autocomplete payload sinirlandi
- `home()` icindeki hasta search json olusturma dongusu:
  - `for _p in (patients_all or []):`
  - yeni: `for _p in (patients_all or [])[:600]:`

6. Arka plan polling trafiÄŸi azaltildi
- JS polling blok:
  - `minGap` (normal mod): `20000` -> `90000`
  - `bgPollMs` default: `30000` -> `120000`
  - webshell fast mod default: `60000`

## Yaklasik kod referanslari (satirlar kayabilir)
- `_load_patient_listing`: ~19828
- background poll JS: ~39019, ~39100
- `home()` fetch/autocomplete: ~53269, ~53281

## Bilinen durum / notlar
- Bu turda compile veya `CODEX_QUICK_CHECK.py` calistirilmadi (kullanici izni olmadan dogrulama kosulmadi).
- Projede daha once gorulen hata: `db_pool_timeout_guard` (UI banner ve loglarda gecmis durumda).
- Ortam PG-primary ayarinda olabilir; sqlite lokalde hasta sayisi 0 gorunse bile production veri PostgreSQL tarafinda olabilir.

## Claude icin onerilen siradaki adimlar
1. Servisi kontrollu restart et ve PID/port 5443 sahipligini dogrula.
2. `CODEX_QUICK_CHECK.py` calistir.
3. Login sonrasi su endpointleri smoke et:
   - `/hastalar`
   - `/api/arka-plan-gorevleri/durum`
   - `/api/sistem-durumu`
4. `db_pool_timeout_guard` tekrarliyorsa:
   - `_ops_db_conn` semaphore davranisini ve pool metriklerini logla
   - arka plan poll intervalini configten override edecek env toggles eklemeyi degerlendir.

## Kritik kurallar (hatirlatma)
- `yazklinik_v68.py` dosyasina dokunma (zorunlu degilse).
- Hasta verilerinde hard delete yapma (archive mantigi).
- AGENTS.md pattern'ini takip et, kucuk ve hedefli patch uygula.

