# AGENTS.md - YazKlinik Final D700 (Codex / OpenAI Agent Brief)

> Bu dosya Codex CLI ve OpenAI Agent SDK'lari icin **otomatik okunan** kontekst dosyasidir.
> Ilk acilista mutlaka oku, sonra `CODEX_QUICK_CHECK.py` ile dogrulama yap.
>
> **YENI:** Daha kapsamli master reference icin `CODEX_PROJECT.md` oku.
> O dosya tum projeyi tek seferde anlatir: dosya yapisi, konvansiyonlar,
> son seans degisiklikleri, troubleshooting, ornek code patterns.

## TL;DR

- **Ne**: Klinik yonetim sistemi - Op. Dr. Hakan YAZ (Kadin Dogum / OB-GYN)
- **Dil**: Python 3.10+ (Flask + waitress + sqlite3)
- **Klasor**: `D:\YazKlinik_Final_D700\`
- **Server**: `https://192.168.1.50:5443` (HTTPS: 5443)
- **Giris**: `doktor / users.json guncel sifre` (bu PC: 1133, TAM YETKI), `asistan / 1234`, `sekreter / 1234`
- **Baslat**: `D700_BASLAT.bat` cift tikla
- **Hizli kontrol**: `python CODEX_QUICK_CHECK.py`
- **Versiyon**: D700 (2026-05-18) - temiz Asustor NAS + lokal DB + menu/tema bakimi

## D700 Devam Notu

- Bu klasor D700 son halinden uretilmis D700 calisma kopyasidir.
- WebShell varsayilan olarak Chrome/Edge app-mode hizli kabukla acilir.
- Ust menude Uzman/Basit mod secimi ve tema secimi native select katmani ile calisir.
- Claude icin once `CLAUDE_BASLA_BURADAN.md`, Codex icin once `CODEX_BASLA_BURADAN.md` oku.
- Handoff ozeti (son seans): `CODEX_HANDOFF_2026-05-26.md`.
- 2026-05-18: Yeni klinik araclar/ajanlar/sistem sayfalari menude gorunur; tema fallback ve D700 surum bilgisi hizalandi.

## Iletisim Stili (kullanici tercihi)

- **Turkce yaz** (klinik dili)
- **Kisa yaz** - 3-5 cumle yeter
- "Yap" deyince: **calisan kod + 1 test + 1 cumle teslim** formatinda bitir
- Uzun teori verme. Onaysiz buyuk degisiklik yapma.
- "Yapildim / su dosyalar / su test" formatinda kapat.

## Kritik Kurallar

1. **`yazklinik_v68.py` dosyasina dokunma** - 8000+ satirlik legacy monolit, kirilgan. Mecbur kalirsan kucuk hedefli patch.
2. **Hasta verisi silme** - `patients`, `visits`, `files`, `usg_measurements` tablolarinda kayit silme. Sadece `archived_at` set et.
3. **NAS klasoru silme** - `\\asustor\Voluson\Hastalar\` icindekileri Python'dan silme. Sadece okuma.
4. **`git reset --hard`, `git checkout --` yapma** - veri kaybi riski.
5. **Inline HTML/JS bloklari** - Python f-string icindeyse CSS/JS brace icin `{{` `}}`. Triple string icindeyse normal `{` `}`.
6. **Mojibake bloklari** - Source'ta `ÃƒÆ’`, `Ãƒâ€š`, `Ãƒâ€` gibi karakterler var (eski Win-1252 Ã¢â€ â€™ UTF-8 cift encode). Otomatik formatlama yapma. Yeni kod yazarken **ASCII guvenli** ol.
7. **Compile + restart sonrasi smoke test** - degisiklik yaptiktan sonra mutlaka `CODEX_QUICK_CHECK.py` calistir.

## Operasyonel Tuzaklar - OKUMADAN PRODA DOKUNMA (2026-05-26)

Sahada ogrenilen tuzaklar. Aksi halde "edit yaptim ama canliya gecmedi / Alex coktu" gibi yanlis teshislere takilirsin.

### 1. waitress HOT-RELOAD YOK -> edit canli olmasi icin PROCESS restart sart
- `yazklinik_web.py`'yi editlemek YETMEZ. Calisan waitress eski kodu servis etmeye devam eder.
- Fix disk'te olabilir, compile temiz olabilir, cache-bust'lu olabilir; yine de doktor eski/bozuk davranisi gorur ("geri bozuldu" der). Cunku hic canliya gecmemistir.
- TESPIT: port 5052 sahibi proc'un CreationDate < dosya LastWriteTime ise -> CANLI BAYAT -> restart gerekli.
  ```powershell
  $p=(Get-NetTCPConnection -LocalPort 5052 -State Listen).OwningProcess
  (Get-CimInstance Win32_Process -Filter "ProcessId=$p").CreationDate   # proc start
  (Get-Item D:\YazKlinik_Final_D700\yazklinik_web.py).LastWriteTime      # dosya mtime
  ```
- Route'un HTTP 200 donmesi fix'in canli oldugunu KANITLAMAZ (bozuk inline JS'li sayfa da 200 doner).
- ISTISNA: `render()` icinde sayfa HTML'ine enjekte edilen `<style>`/`<script>` no-cache -> reload'da aninda gecerli; ama Python kodu degistigi icin yine de proc restart sart.

### 2. Restart proseduru (web-only)
- Mimari: her servis `D700_SERVICE_RUNNER.py <modul>` (pythonw) altinda calisir; ayri bir `D700_HEALTH_MONITOR.py` proc'u dusen servisi ~30sn'de bir respawn eder (min-restart guard var).
- Web-only restart: port 5052 sahibi PID'i kill et, Health Monitor respawn etsin. Manuel relaunch monitorle YARISIR (cift proc) - yapma.
  ```powershell
  $pid5052=(Get-NetTCPConnection -LocalPort 5052 -State Listen).OwningProcess; Stop-Process -Id $pid5052 -Force
  ```
- BOOT YAVAS: 13.6 MB dosya re-import + preflight yuzunden listener, proc start'tan ~2.5-5 DK SONRA gelir. O sirada 5052/5443 no-listen, `curl` 000 doner. Erken "coktu" deme; 2+ ardisik `http://127.0.0.1:5052/giris` 200 gorene kadar yokla.
- Restart sonrasi tazelik: yeni proc CreationDate > dosya mtime olmali.
- Temiz tam restart: `D700_BASLAT.bat` (TUM stack: whisper/xtts/piper/comfyui/SIP dahil - hasta telefon hattini kisa sure dusurur; web-only kod degisikligi icin doktora zamanlamayi sor). Web-only hafif: `D700_ADMIN_WEB_RESTART.bat` (UAC).
- `D700_BASLAT.bat`'i YAKALANMIS/PIPE'LI cikti ile baslatma (`& bat 2>&1 | ...`, run_in_background) -> stdin redirect olur, bat'in `timeout /t` cagrilari "Input redirection is not supported" ile oler, server DOWN kalir. Detached, kendi konsoluyla baslat:
  ```powershell
  Start-Process cmd.exe -ArgumentList '/c','"D:\YazKlinik_Final_D700\D700_BASLAT.bat"' -WorkingDirectory 'D:\YazKlinik_Final_D700'
  ```

### 3. Core asset cache-busting (BASE_HTML inline JS/CSS editi)
- `yk-core.js`, `yk-premium.css`, `yk-pro-v3.css` -> `Cache-Control: immutable` + STATIK `?v=...` ile servis edilir. `yk-core.js` BASE_HTML icindeki inline `<script>`'ten runtime'da cikarilir.
- BASE_HTML inline JS/CSS editlersen cache'li tarayici/WebShell ESKI asset'i servis eder (reload'da bile) -> fix client'a ulasmaz.
- Cozum: asset referansindaki `?v=` string'ini BUMP et, ya da WebShell disk cache temizle (`%LOCALAPPDATA%\YazKlinik\BrowserShellCache`). Sayfa HTML'i no-cache oldugu icin govdedeki inline edit reload'da gecer; sadece extract edilen DIS asset'ler tuzaktir.

### 4. WebShell restart sonrasi BAYAT
- Web restart edince doktorun acik WebShell'i (Chrome `--app`) bayatlar: Alex/SSE/canli paneller olu gorunur ama server saglikli. Coz: sayfayi reload et / WebShell yeniden ac. "Alex coktu" diye yanlis teshis koyma.
- Self-kill gotcha: `YazKlinik_WebShell_Windows.bat` cmdline'i `*BrowserShell*` veya `*WebShell\main.py*` eslesen HER proc'u oldurur (proc-name filtresi yok). WebShell proc'u oldururken Name filtresi kullan (kendi shell'ini oldurme).

### 5. Client-side JS debug
- Tarayici Claude'a bagli degil ama `.venv`'de Playwright + system Chrome var (`channel="chrome"`, `ignore_https_errors=True`). `pageerror`/`console`/`requestfailed` yakala. Syntax hatasi icin rendered script'lere `node --check` (Node: `C:\Program Files\nodejs`).

### 6. Login / smoke / port
- Smoke kimligi: user `doktor`, sifre `users.json`'dan (env `YAZKLINIK_SMOKE_PASSWORD` override). `CODEX_QUICK_CHECK` bunu otomatik kullanir. **Localhost auth muafiyeti YOK.**
- HTTPS 5443 werkzeug -> PowerShell .NET TLS handshake'i yanlis fail edebilir; 5443'u `curl -k` ile dogrula, `Invoke-WebRequest` ile DEGIL. Saglik/smoke kontrolu icin plain HTTP **5052** kullan.

### 7. CF Access remote lockout = sahte "sifre hatali"
- `YAZKLINIK_CF_ACCESS_ENFORCE=1` iken uzaktan login sonrasi kritik admin ekranlari (`/hizmet-ajanlari`,`/sistem-ayarlari`,`/entegrasyonlar`,`/ajanlar`) `/giris`'e geri atar (cf-access-* header gelmedigi icin). Doktor "giris olmuyor" der ama sifre dogru; localhost hep calisir. Coz: `ENFORCE=0` + restart.

### 8. Cloudflare bakim sayfasi
- `yazhakan.com.tr` FREE plan -> 5xx Custom Pages KAPALI (err 1219). Bakim sayfasi icin Cloudflare WORKER kullan (Custom Pages degil). Sayfa hazir: `cloudflare_bakim_sayfasi.html` + `/bakim` route.

> Bu seansin (2026-05-26) ayrintili devir notu: **CODEX_HANDOFF_2026-05-26.md**.

## Dosya Yapisi

```
D:\YazKlinik_Final_D700\
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_web.py              ana Flask uygulamasi (~6.8 MB tek dosya)
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_v68.py              legacy monolit - DOKUNMA
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_feature_sync.py     route manifesti (sidebar)
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_desktop_v1000.py    Windows hybrid desktop shell
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_textfix.py          mojibake fix helper
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_config.py           config dosyasi load/save
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_common.py           ortak yardimci
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_db_onar.py          DB onarim aracI
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_dicom_private.py    DICOM private tag
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_enabiz_agent.py     E-Nabiz entegre
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_integration_agents.py  YZ integration
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_nas_watcher.py      NAS klasor degisiklik dinleyici
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_open_folder_helper.py  Windows klasor ac
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_pdf_patient_extract.py  PDF -> hasta data
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_photo_print_helper.py   foto print
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_runtime_cleanup.py  runtime temizlik
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_updater.py          guncelleyici
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_whatsapp_local_helper.py  WhatsApp helper
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik\                    Python paketi (icinde sub-moduller)
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ static\                       UI varlik (CSS/JS/img)
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ tools\                        yan araclar (PDF/OCR vs)
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ local_db\
Ã¢â€â€š   Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_v68.sqlite3     LOKAL DB (server PC'de, NAS'ta degil)
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ auto_backups\                 24 saatte bir DB yedek
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ config.env                    Ã¢Ëœâ€¦ Tum ayarlar burada (NAS, DB, port)
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ D700_BASLAT.bat               Ã¢Ëœâ€¦ Tek tikla baslat
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ README_D700.md                tam dokumantasyon
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ CODEX_QUICK_CHECK.py          sistem dogrulama
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ CODEX_FILE_MAP.md             dosya sorumluluklari (detayli)
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ CODEX_COMMANDS.md             yaygin gorevler + komutlar
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ CODEX_API_ENDPOINTS.md        Flask route listesi
Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ AGENTS.md                     bu dosya
```

## Konfigurasyon (`config.env`)

```bash
YAZKLINIK_NAS_ROOT=\\asustor\Voluson\Hastalar
YAZKLINIK_DB_PATH=D:\YazKlinik_Final_D700\local_db\yazklinik_v68.sqlite3
YAZKLINIK_WEB_PORT=5052
YAZKLINIK_HTTPS_PORT=5443
YAZKLINIK_ENABLE_HTTPS=1
YAZKLINIK_WAITRESS_THREADS=12
YAZKLINIK_BACKUP_ROOT=D:\YazKlinik_Final_D700\auto_backups
YAZKLINIK_VOLUSON_AUTO_PREFIX=F137230
PYTHONUTF8=1
```

Web UI'den degistir: `https://192.168.1.50:5443/sistem-ayarlari`
Manuel: `D:\YazKlinik_Final_D700\config.env` editle, restart.

## Sunucu Calistirma

```powershell
# Kolay - launcher script (config.env okur)
D:\YazKlinik_Final_D700\D700_BASLAT.bat

# Manuel
Set-Location "D:\YazKlinik_Final_D700"
$env:YAZKLINIK_DB_PATH="D:\YazKlinik_Final_D700\local_db\yazklinik_v68.sqlite3"
$env:YAZKLINIK_NAS_ROOT="\\asustor\Voluson\Hastalar"
$env:YAZKLINIK_WEB_PORT="5052"
& "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" -u yazklinik_web.py
```

## Calisan Surec Nasil Bulunur

```powershell
# Port 5443 sahibi
Get-NetTCPConnection -LocalPort 5443 | Select OwningProcess, State

# Tum python procs
Get-Process python | Select Id, WorkingSet64
```

## DB Yapisi (SQLite)

- **DB yolu**: `D:\YazKlinik_Final_D700\local_db\yazklinik_v68.sqlite3`
- **Boyut**: ~3.7 MB (lokal kopya, gercek veri NAS DB ile sync olur)
- **Ana tablolar** (73 tane):
  - `patients` (folder_key PK) - 179 hasta (2026-05-26)
  - `patient_protocols` (patient_key FK)
  - `patient_demographics` (patient_key FK) - lmp_override, data_json
  - `visits` (patient_folder_key FK)
  - `files` (patient_folder_key FK) - PDF/JPG dosya kayit
  - `usg_measurements` (patient_key FK) - GA/BPD/HC/AC/FL/EFW
  - `prescriptions` (patient_key FK)
  - `web_audit_log` (patient_key) - islem audit

- **52 tablo** patient_key/folder_key icerir (merge icin _MERGE_FK_TABLES'da liste)

## Onemli Route'lar

```
/                          dashboard (giris sonrasi)
/giris                     login
/hastalar                  hasta listesi (lazy GA chip)
/yeni-hasta                yeni hasta kayit
/hasta/<key>               hasta dosyasi
/hasta/<key>/sil           sil (POST)
/hasta-birlestir           D128 SUPER: 2 hasta merge
/akilli-dialog             Alex AI chat (wake word "alex")
/tedavi-planla             Tedavi Planlayici (D128 SUPER)
/tedavi-planla/recete-cikti  A5 profesyonel recete
/sistem-ayarlari           Ã¢Ëœâ€¦ D700 NAS/DB/port ayar UI
/obgyn-rehber              klinik rehber 11 kategori
/diyet-rehberi             8 senaryo diyet
/ivf-konsult               IVF protokol
/api/sistem-durumu         JSON sistem health
```

Tum route listesi: `CODEX_API_ENDPOINTS.md`

## Hizli Test

```powershell
# 1) Compile check
& "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" -m py_compile yazklinik_web.py yazklinik_v68.py yazklinik_feature_sync.py

# 2) Sistem dogrulama
& "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" CODEX_QUICK_CHECK.py
```

Beklenen son satir: `CODEX_D700_QUICK_CHECK_OK`

## D700 Son Seans Degisiklikleri (2026-05-12)

### ReÃƒÂ§ete (e-ReÃƒÂ§ete 5 sÃƒÂ¼tun)
- `drug_fields`: `["name","route","dose","daily","box"]` lock'lu (`sysparam_rx_print_d700_erecete_locked=1`)
- Routes: AGIZDAN / VAJINAL / INTRAMUSKULER / SUBKUTAN / **REKTAL** (yeni)
- `_rx_build_medications_text()` artik route+period+daily korur
- Hasta recete sayfasinda **Gor / Bas / Duzenle / Sil** butonlari
- `/hasta/<key>/recete/goruntule/<rx_id>` (+ `?print=1` auto-print)
- `/hasta/<key>/recete/sil/<rx_id>` (POST + confirm + hard delete)

### Onam (D700)
- 6 kategori: Gebelik / Infertilite / Jinekoloji / **Jinekolojik Estetik** / **Medikal Estetik** / Paylasim Izinleri
- `/onam-sablonlari` sayfasinda yeÃ…Å¸il **"Toplu Onam Import"** karti
- `_onam_classify_bulk()` otomatik kategorize (anahtar kelime + PDF iceriÃ„Å¸i)
- Sort: her kategori icinde en cok kullanilan ustte + ÄŸÅ¸Ââ€  rozet + use badge
- `/onam/yazdir/<id>` PDF iframe + auto window.print()

### Tema Sistemi (palette-reactive, geniÃ…Å¸ ÃƒÂ§aplÃ„Â±)
- `yk-premium.css` + `yk-pro-v3.css`: `--pro-accent/bg/surface/header` palette-reactive
- 12 palet icin EXPLICIT override (body/header/sidebar/card hepsi degisir)
- Emergency theme modal (`<head>` script `yk-theme-emergency-modal`)
- Floating fallback buton sag ust kose her sayfada (44px ÄŸÅ¸ÂÂ¨)

### WebShell Modu (kritik fix)
- `_yk_webshell_slim_html()` voice-agent strip KALDIRILDI
- `yk-stability.js` + `yk-safari-compat.js` artik WebShell'de de inject
- Alex bar + tema + butonlar WebShell'de calisir

### Hasta Listesi
- `_patient_name_looks_like_filename_only()` filter (yazklinik_web.py L14297)
- `F137230-26-05-07-3__` gibi dosya-adi tipi kayitlar `_load_patient_listing()` icinde gizleniyor
- Cache key: `terminal_patients_v3`

### Performance
- `_clean_patient_display_name` module-level cached import
- Mojibake middleware fast bytes pre-check (0xC2/0xC3 yoksa skip)
- CSS cache versiyon: `?v=d700-25-bar-simple`

### Alex Bar / Voice Panel
- Tum quickbar + panel butonlarina inline onclick fallback
- Emergency capture handler (`<head>` script `yk-alex-bar-emergency`)
- Document-level capture phase tÃƒÂ¼m ykVoice* ID'leri yakalar

### IVF Konsult
- "Hizli Klinik Bilgi Sorgu" 10 chip artik Alex'e gitmiyor
- Inline bilgi paneli (`#yk-quickinfo-panel`) acar

## D128 -> D700 Yenilikler

- **Lokal DB** server PC'sinde (eski: NAS bagimliydi)
- **NAS yolu** `\\asustor\Voluson` (eski: `\\Sam\usg`)
- **config.env** + `/sistem-ayarlari` web UI ile yollar editlenebilir
- D128'in tum SUPER ozellikleri devam:
  - Tedavi Planlayici + DDI etkilesim + A5 recete + QR
  - Hasta autocomplete + SAT/USG bazli gebelik haftasi
  - Hasta listesi GA chip (sari SAT / mavi USG / yesil PDF)
  - Hasta Birlestir (46 tablo bulk transfer)
  - Wake word "Alex" arka plan dinleyici
  - DB performans tuning (connect timeout 10s, busy 5s, retry x3)

## Acik Isler / Bilinen Sorunlar

1. **Mojibake** source code'da bazi yerlerde var (Win-1252 cift encode). Dokunma, kucuk hedefli fix yap.
2. **`yazklinik_v68.py` v68 surumu legacy** - cogu DB schema migration burada. Ayrintili degisiklik onayli olarak.
3. **`yazklinik_web.py` ~13.6 MB** - tek dosya, parcalama riskli. Ekleme yaparken yer planli (yakin route'larin yanina).
4. **Cache** - `_PERF_CACHE` modul-level dict, restart'ta sifirlanir. TTL 60s-30dk arasi.

## Kullaniciya Cevap Stili (ornek)

```
Yaptim.

**Dosyalar:**
- yazklinik_web.py - X eklendi (line 12345)
- D700_BASLAT.bat - Y env var eklendi

**Test:**
- COMPILE_OK
- 17/17 route smoke OK, ortalama 232ms

Server `https://192.168.1.50:5443/yeni-route` aktif.
```

## Troubleshooting

| Sorun | Cozum |
|---|---|
| `unable to open database file` | `config.env`'de `YAZKLINIK_DB_PATH` mevcut path mi? |
| `\\asustor\Voluson erisilmiyor` | Map drive (Asustor IP/user/pass) veya `/sistem-ayarlari`'dan farkli path |
| Port 5443 dolu | `D700_BASLAT.bat` otomatik kill; manuel: `taskkill /F /IM python.exe` |
| 500 Internal Server Error | server log: `D700_server_HATA.log`; before_request DB check soft-fail |
| Mojibake | UTF-8 BOM mu (config dosyasinda olmamali); source'ta var ise dokunma |

## Codex Kurallari

1. **Once oku, sonra yaz.** Kullanici "yap" demeden buyuk degisiklik yapma.
2. **Mevcut pattern'i takip et.** Yeni route eklerken yakindaki route'larin pattern'ini kopyala.
3. **Compile her zaman, smoke test her zaman.** `python -m py_compile` + `CODEX_QUICK_CHECK.py`.
4. **D700_BASLAT.bat'i kirma.** Launcher script'i degisirken once Read sonra Edit (small).
5. **config.env'e eklerken duzenli ol.** Yorumlu, gruplu, KEY=VALUE format.
6. **Test session ile route check** (yardimci PowerShell):
   ```powershell
   $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
   Invoke-WebRequest -Uri "https://127.0.0.1:5443/giris" -Method POST -Body @{username="doktor"; password="1133"} -WebSession $session
   Invoke-WebRequest -Uri "https://127.0.0.1:5443/<route>" -WebSession $session
   ```

## Yardimci Dosyalar

- `CODEX_QUICK_CHECK.py` - hizli durum dogrulama (compile + DB + route + NAS)
- `CODEX_FILE_MAP.md` - dosya sorumluluklari (her yazklinik_*.py ne yapar)
- `CODEX_COMMANDS.md` - yaygin gorevler (server start/stop, DB query, log oku)
- `CODEX_API_ENDPOINTS.md` - tum Flask route'lari + ne yaptiklari

---
**Versiyon**: D700 (2026-05-18) | **Yazar**: Op. Dr. Hakan YAZ | **Stack**: Python 3.10 + Flask + waitress + sqlite3




