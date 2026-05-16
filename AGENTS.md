# AGENTS.md - YazKlinik Final D300 (Codex / OpenAI Agent Brief)

> Bu dosya Codex CLI ve OpenAI Agent SDK'lari icin **otomatik okunan** kontekst dosyasidir.
> Ilk acilista mutlaka oku, sonra `CODEX_QUICK_CHECK.py` ile dogrulama yap.
>
> **YENI:** Daha kapsamli master reference icin `CODEX_PROJECT.md` oku.
> O dosya tum projeyi tek seferde anlatir: dosya yapisi, konvansiyonlar,
> son seans degisiklikleri, troubleshooting, ornek code patterns.

## TL;DR

- **Ne**: Klinik yonetim sistemi - Op. Dr. Hakan YAZ (Kadin Dogum / OB-GYN)
- **Dil**: Python 3.10+ (Flask + waitress + sqlite3)
- **Klasor**: `D:\YazKlinik_Final_D300\`
- **Server**: `https://127.0.0.1:5443` (HTTPS: 5443)
- **Giris**: `doktor / 1234` (TAM YETKI), `asistan / 1234`, `sekreter / 1234`
- **Baslat**: `D300_BASLAT.bat` cift tikla
- **Hizli kontrol**: `python CODEX_QUICK_CHECK.py`
- **Versiyon**: D300 (2026-05-11) - temiz Asustor NAS + lokal DB

## D300 Devam Notu

- Bu klasor D250 son halinden uretilmis D300 calisma kopyasidir.
- WebShell varsayilan olarak Chrome/Edge app-mode hizli kabukla acilir.
- Ust menude Uzman/Basit mod secimi ve tema secimi native select katmani ile calisir.
- Claude icin once `CLAUDE_BASLA_BURADAN.md`, Codex icin once `CODEX_BASLA_BURADAN.md` oku.
- Handoff ozeti: `D300_HANDOFF.md`.

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
6. **Mojibake bloklari** - Source'ta `Ãƒ`, `Ã‚`, `Ã„` gibi karakterler var (eski Win-1252 â†’ UTF-8 cift encode). Otomatik formatlama yapma. Yeni kod yazarken **ASCII guvenli** ol.
7. **Compile + restart sonrasi smoke test** - degisiklik yaptiktan sonra mutlaka `CODEX_QUICK_CHECK.py` calistir.

## Dosya Yapisi

```
D:\YazKlinik_Final_D300\
â”œâ”€â”€ yazklinik_web.py              ana Flask uygulamasi (~6.8 MB tek dosya)
â”œâ”€â”€ yazklinik_v68.py              legacy monolit - DOKUNMA
â”œâ”€â”€ yazklinik_feature_sync.py     route manifesti (sidebar)
â”œâ”€â”€ yazklinik_desktop_v1000.py    Windows hybrid desktop shell
â”œâ”€â”€ yazklinik_textfix.py          mojibake fix helper
â”œâ”€â”€ yazklinik_config.py           config dosyasi load/save
â”œâ”€â”€ yazklinik_common.py           ortak yardimci
â”œâ”€â”€ yazklinik_db_onar.py          DB onarim aracI
â”œâ”€â”€ yazklinik_dicom_private.py    DICOM private tag
â”œâ”€â”€ yazklinik_enabiz_agent.py     E-Nabiz entegre
â”œâ”€â”€ yazklinik_integration_agents.py  YZ integration
â”œâ”€â”€ yazklinik_nas_watcher.py      NAS klasor degisiklik dinleyici
â”œâ”€â”€ yazklinik_open_folder_helper.py  Windows klasor ac
â”œâ”€â”€ yazklinik_pdf_patient_extract.py  PDF -> hasta data
â”œâ”€â”€ yazklinik_photo_print_helper.py   foto print
â”œâ”€â”€ yazklinik_runtime_cleanup.py  runtime temizlik
â”œâ”€â”€ yazklinik_updater.py          guncelleyici
â”œâ”€â”€ yazklinik_whatsapp_local_helper.py  WhatsApp helper
â”œâ”€â”€ yazklinik\                    Python paketi (icinde sub-moduller)
â”œâ”€â”€ static\                       UI varlik (CSS/JS/img)
â”œâ”€â”€ tools\                        yan araclar (PDF/OCR vs)
â”œâ”€â”€ local_db\
â”‚   â””â”€â”€ yazklinik_v68.sqlite3     LOKAL DB (server PC'de, NAS'ta degil)
â”œâ”€â”€ auto_backups\                 24 saatte bir DB yedek
â”œâ”€â”€ config.env                    â˜… Tum ayarlar burada (NAS, DB, port)
â”œâ”€â”€ D300_BASLAT.bat               â˜… Tek tikla baslat
â”œâ”€â”€ README_D300.md                tam dokumantasyon
â”œâ”€â”€ CODEX_QUICK_CHECK.py          sistem dogrulama
â”œâ”€â”€ CODEX_FILE_MAP.md             dosya sorumluluklari (detayli)
â”œâ”€â”€ CODEX_COMMANDS.md             yaygin gorevler + komutlar
â”œâ”€â”€ CODEX_API_ENDPOINTS.md        Flask route listesi
â””â”€â”€ AGENTS.md                     bu dosya
```

## Konfigurasyon (`config.env`)

```bash
YAZKLINIK_NAS_ROOT=\\asustor\Voluson\Hastalar
YAZKLINIK_DB_PATH=D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3
YAZKLINIK_WEB_PORT=5443
YAZKLINIK_HTTPS_PORT=5443
YAZKLINIK_ENABLE_HTTPS=1
YAZKLINIK_WAITRESS_THREADS=12
YAZKLINIK_BACKUP_ROOT=D:\YazKlinik_Final_D300\auto_backups
YAZKLINIK_VOLUSON_AUTO_PREFIX=F137230
PYTHONUTF8=1
```

Web UI'den degistir: `https://127.0.0.1:5443/sistem-ayarlari`
Manuel: `D:\YazKlinik_Final_D300\config.env` editle, restart.

## Sunucu Calistirma

```powershell
# Kolay - launcher script (config.env okur)
D:\YazKlinik_Final_D300\D300_BASLAT.bat

# Manuel
Set-Location "D:\YazKlinik_Final_D300"
$env:YAZKLINIK_DB_PATH="D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3"
$env:YAZKLINIK_NAS_ROOT="\\asustor\Voluson\Hastalar"
$env:YAZKLINIK_WEB_PORT="5443"
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" -u yazklinik_web.py
```

## Calisan Surec Nasil Bulunur

```powershell
# Port 5443 sahibi
Get-NetTCPConnection -LocalPort 5443 | Select OwningProcess, State

# Tum python procs
Get-Process python | Select Id, WorkingSet64
```

## DB Yapisi (SQLite)

- **DB yolu**: `D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3`
- **Boyut**: ~3.7 MB (lokal kopya, gercek veri NAS DB ile sync olur)
- **Ana tablolar** (73 tane):
  - `patients` (folder_key PK) - 85 hasta
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
/sistem-ayarlari           â˜… D300 NAS/DB/port ayar UI
/obgyn-rehber              klinik rehber 11 kategori
/diyet-rehberi             8 senaryo diyet
/ivf-konsult               IVF protokol
/api/sistem-durumu         JSON sistem health
```

Tum route listesi: `CODEX_API_ENDPOINTS.md`

## Hizli Test

```powershell
# 1) Compile check
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" -m py_compile yazklinik_web.py yazklinik_v68.py yazklinik_feature_sync.py

# 2) Sistem dogrulama
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" CODEX_QUICK_CHECK.py
```

Beklenen son satir: `CODEX_D300_QUICK_CHECK_OK`

## D300 Son Seans Degisiklikleri (2026-05-12)

### ReÃ§ete (e-ReÃ§ete 5 sÃ¼tun)
- `drug_fields`: `["name","route","dose","daily","box"]` lock'lu (`sysparam_rx_print_d250_erecete_locked=1`)
- Routes: AGIZDAN / VAJINAL / INTRAMUSKULER / SUBKUTAN / **REKTAL** (yeni)
- `_rx_build_medications_text()` artik route+period+daily korur
- Hasta recete sayfasinda **Gor / Bas / Duzenle / Sil** butonlari
- `/hasta/<key>/recete/goruntule/<rx_id>` (+ `?print=1` auto-print)
- `/hasta/<key>/recete/sil/<rx_id>` (POST + confirm + hard delete)

### Onam (D300)
- 6 kategori: Gebelik / Infertilite / Jinekoloji / **Jinekolojik Estetik** / **Medikal Estetik** / Paylasim Izinleri
- `/onam-sablonlari` sayfasinda yeÅŸil **"Toplu Onam Import"** karti
- `_onam_classify_bulk()` otomatik kategorize (anahtar kelime + PDF iceriÄŸi)
- Sort: her kategori icinde en cok kullanilan ustte + ğŸ† rozet + use badge
- `/onam/yazdir/<id>` PDF iframe + auto window.print()

### Tema Sistemi (palette-reactive, geniÅŸ Ã§aplÄ±)
- `yk-premium.css` + `yk-pro-v3.css`: `--pro-accent/bg/surface/header` palette-reactive
- 12 palet icin EXPLICIT override (body/header/sidebar/card hepsi degisir)
- Emergency theme modal (`<head>` script `yk-theme-emergency-modal`)
- Floating fallback buton sag ust kose her sayfada (44px ğŸ¨)

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
- CSS cache versiyon: `?v=d250-25-bar-simple`

### Alex Bar / Voice Panel
- Tum quickbar + panel butonlarina inline onclick fallback
- Emergency capture handler (`<head>` script `yk-alex-bar-emergency`)
- Document-level capture phase tÃ¼m ykVoice* ID'leri yakalar

### IVF Konsult
- "Hizli Klinik Bilgi Sorgu" 10 chip artik Alex'e gitmiyor
- Inline bilgi paneli (`#yk-quickinfo-panel`) acar

## D128 -> D200 Yenilikler

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
3. **`yazklinik_web.py` ~6.8 MB** - tek dosya, parcalama riskli. Ekleme yaparken yer planli (yakin route'larin yanina).
4. **Cache** - `_PERF_CACHE` modul-level dict, restart'ta sifirlanir. TTL 60s-30dk arasi.

## Kullaniciya Cevap Stili (ornek)

```
Yaptim.

**Dosyalar:**
- yazklinik_web.py - X eklendi (line 12345)
- D300_BASLAT.bat - Y env var eklendi

**Test:**
- COMPILE_OK
- 17/17 route smoke OK, ortalama 232ms

Server `https://127.0.0.1:5443/yeni-route` aktif.
```

## Troubleshooting

| Sorun | Cozum |
|---|---|
| `unable to open database file` | `config.env`'de `YAZKLINIK_DB_PATH` mevcut path mi? |
| `\\asustor\Voluson erisilmiyor` | Map drive (Asustor IP/user/pass) veya `/sistem-ayarlari`'dan farkli path |
| Port 5443 dolu | `D300_BASLAT.bat` otomatik kill; manuel: `taskkill /F /IM python.exe` |
| 500 Internal Server Error | server log: `D300_server_HATA.log`; before_request DB check soft-fail |
| Mojibake | UTF-8 BOM mu (config dosyasinda olmamali); source'ta var ise dokunma |

## Codex Kurallari

1. **Once oku, sonra yaz.** Kullanici "yap" demeden buyuk degisiklik yapma.
2. **Mevcut pattern'i takip et.** Yeni route eklerken yakindaki route'larin pattern'ini kopyala.
3. **Compile her zaman, smoke test her zaman.** `python -m py_compile` + `CODEX_QUICK_CHECK.py`.
4. **D300_BASLAT.bat'i kirma.** Launcher script'i degisirken once Read sonra Edit (small).
5. **config.env'e eklerken duzenli ol.** Yorumlu, gruplu, KEY=VALUE format.
6. **Test session ile route check** (yardimci PowerShell):
   ```powershell
   $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
   Invoke-WebRequest -Uri "https://127.0.0.1:5443/giris" -Method POST -Body @{username="doktor"; password="1234"} -WebSession $session
   Invoke-WebRequest -Uri "https://127.0.0.1:5443/<route>" -WebSession $session
   ```

## Yardimci Dosyalar

- `CODEX_QUICK_CHECK.py` - hizli durum dogrulama (compile + DB + route + NAS)
- `CODEX_FILE_MAP.md` - dosya sorumluluklari (her yazklinik_*.py ne yapar)
- `CODEX_COMMANDS.md` - yaygin gorevler (server start/stop, DB query, log oku)
- `CODEX_API_ENDPOINTS.md` - tum Flask route'lari + ne yaptiklari

---
**Versiyon**: D300 (2026-05-11) | **Yazar**: Op. Dr. Hakan YAZ | **Stack**: Python 3.10 + Flask + waitress + sqlite3


