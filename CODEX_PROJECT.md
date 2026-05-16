# CODEX_PROJECT.md â€” YazKlinik Final D300 (Master Reference)

> **Codex / AI agent ana baslangic dosyasi.**  
> Bu dosya tek seferde okunup tum projeyi anlatir. Detay icin yan dosyalar
> referans verilir: `AGENTS.md`, `CODEX_FILE_MAP.md`, `CODEX_COMMANDS.md`,
> `CODEX_API_ENDPOINTS.md`, `D300_HANDOFF.md`.

---

## 1. TL;DR

| Soru | Cevap |
|---|---|
| **Ne?** | Klinik yonetim sistemi (Op. Dr. Hakan YAZ, Kadin Dogum / OB-GYN) |
| **Stack** | Python 3.10 + Flask + waitress + sqlite3 + Bootstrap 5 + WebShell (Chrome/Edge `--app` mode) |
| **Klasor** | `D:\YazKlinik_Final_D300\` |
| **Server** | `https://127.0.0.1:5443` (HTTPS 5443) |
| **Giris** | `doktor / 1234` (tam yetki), `asistan/1234`, `sekreter/1234` |
| **Baslat** | `D300_BASLAT.bat` cift tikla |
| **Smoke test** | `python CODEX_QUICK_CHECK.py` â†’ `CODEX_D300_QUICK_CHECK_OK` |
| **Ana dosya** | `yazklinik_web.py` (~6.8 MB tek-dosya Flask app, ~136K satir) |
| **DB** | `local_db\yazklinik_v68.sqlite3` |
| **NAS** | `\\ASUSTOR\Voluson\Hastalar\` (PDF/USG/foto kaynak) |

---

## 2. Iletisim Stili (kullanici tercihi)

- **Turkce yaz** (klinik dili)
- **Kisa cevap** â€” 3â€“5 cumle, asiri teori verme
- "Yap" deyince: **calisan kod + 1 test + 1 cumle teslim**
- Onaysiz buyuk refactor yapma
- Kapanis formati: `Yaptim. Dosyalar: X. Test: COMPILE_OK + Y.`

---

## 3. Kritik Kurallar (kirma)

| Yasak | Sebep |
|---|---|
| `yazklinik_v68.py` duzenleme | 8000+ satir legacy monolit, kirilgan |
| Hasta verisi silme (`patients`/`visits`/`files`/`usg_measurements`) | Sadece `archived_at` set et |
| NAS `\\ASUSTOR\Voluson\Hastalar\` silme | Python'dan asla, sadece okuma |
| `git reset --hard`, `git checkout --`, force push | Veri kaybi riski |
| Buyuk otomatik formatlama | Kaynakta mojibake var, dokunma |
| Inline f-string'de `{` `}` unutmak | CSS/JS brace'leri `{{` `}}` ile escape |
| **`yk-premium.css` / `yk-pro-v3.css` ile `yk-core.css`'i ayni anda guncellemeden cache versiyon bumplama** | Tarayici eski CSS'i tutar |

**Her degisiklik sonrasi:** `python -m py_compile yazklinik_web.py` + `CODEX_QUICK_CHECK.py` + browser cache atla (Ctrl+Shift+R veya WebShell yeniden baslat).

---

## 4. Dosya Yapisi (tam)

```
D:\YazKlinik_Final_D300\
â”œâ”€â”€ yazklinik_web.py                â˜… ana Flask app (~6.8 MB, ~136K satir)
â”œâ”€â”€ yazklinik_v68.py                â˜… LEGACY monolit - DOKUNMA
â”œâ”€â”€ yazklinik_feature_sync.py       sidebar route manifesti
â”œâ”€â”€ yazklinik_desktop_v1000.py      Windows hybrid desktop shell
â”œâ”€â”€ yazklinik_textfix.py            mojibake repair (Win-1252 cift encode)
â”œâ”€â”€ yazklinik_config.py             config dosyasi load/save
â”œâ”€â”€ yazklinik_common.py             ortak yardimci (patient name temizleme)
â”œâ”€â”€ yazklinik_db_onar.py            DB onarim/migrate
â”œâ”€â”€ yazklinik_dicom_private.py      DICOM private tag
â”œâ”€â”€ yazklinik_enabiz_agent.py       E-Nabiz entegre
â”œâ”€â”€ yazklinik_integration_agents.py YZ integration
â”œâ”€â”€ yazklinik_nas_watcher.py        NAS klasor dinleyici
â”œâ”€â”€ yazklinik_open_folder_helper.py Windows klasor ac
â”œâ”€â”€ yazklinik_pdf_patient_extract.py PDF -> hasta data extract
â”œâ”€â”€ yazklinik_photo_print_helper.py foto print
â”œâ”€â”€ yazklinik_runtime_cleanup.py    runtime temizlik
â”œâ”€â”€ yazklinik_updater.py            guncelleyici
â”œâ”€â”€ yazklinik_whatsapp_local_helper.py WhatsApp helper
â”‚
â”œâ”€â”€ yazklinik\                      Python paketi (sub-modules)
â”‚
â”œâ”€â”€ static\                         UI varlik (CSS/JS/img)
â”‚   â”œâ”€â”€ yk-core.css                 â˜… ana CSS (~3 MB, BASE_HTML disindan ayri serve)
â”‚   â”œâ”€â”€ yk-premium.css              â˜… premium override (renkler, kart, sidebar)
â”‚   â”œâ”€â”€ yk-pro-v3.css               â˜… pro v3 override (palet-reaktif accent)
â”‚   â”œâ”€â”€ yk-safari-compat.js         Safari/Edge compat shim
â”‚   â”œâ”€â”€ yk-stability.js             event guard + mic permission
â”‚   â”œâ”€â”€ yk-core.js                  ana JS yardimci
â”‚   â””â”€â”€ img\                        logo + ikon
â”‚
â”œâ”€â”€ tools\                          yan araclar
â”‚   â”œâ”€â”€ onam_import.py              CLI: onam klasoru -> DB toplu import
â”‚   â””â”€â”€ (digerleri)
â”‚
â”œâ”€â”€ local_db\
â”‚   â””â”€â”€ yazklinik_v68.sqlite3       â˜… LOKAL DB (73 tablo, ~3.7 MB)
â”‚
â”œâ”€â”€ auto_backups\                   24 saatte bir DB yedek
â”‚
â”œâ”€â”€ config.env                      â˜… Tum ayarlar (NAS, DB, port, AI key)
â”œâ”€â”€ D300_BASLAT.bat                 â˜… Tek tikla baslat (server + WebShell)
â”‚
â”œâ”€â”€ README_D300.md                  tam dokumantasyon
â”œâ”€â”€ CODEX_PROJECT.md                â˜… BU DOSYA (master reference)
â”œâ”€â”€ CODEX_QUICK_CHECK.py            sistem dogrulama
â”œâ”€â”€ CODEX_FILE_MAP.md               dosya sorumluluklari (detayli)
â”œâ”€â”€ CODEX_COMMANDS.md               yaygin gorevler + komutlar
â”œâ”€â”€ CODEX_API_ENDPOINTS.md          Flask route listesi
â”œâ”€â”€ AGENTS.md                       Codex/agent rules ozet
â”œâ”€â”€ CLAUDE.md                       Claude Code proje brifi
â””â”€â”€ D300_HANDOFF.md                 handoff ozeti
```

---

## 5. config.env (Tum Ayarlar)

```bash
# Veri yollari
YAZKLINIK_NAS_ROOT=\\ASUSTOR\Voluson\Hastalar
YAZKLINIK_DB_PATH=D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3
YAZKLINIK_BACKUP_ROOT=D:\YazKlinik_Final_D300\auto_backups

# Server
YAZKLINIK_WEB_PORT=5443
YAZKLINIK_HTTPS_PORT=5443
YAZKLINIK_ENABLE_HTTPS=1
YAZKLINIK_WAITRESS_THREADS=16
YAZKLINIK_SERVER_ENGINE=waitress

# Voluson USG auto-import prefix
YAZKLINIK_VOLUSON_AUTO_PREFIX=F137230

# Python
PYTHONUTF8=1

# AI (varsa)
OPENAI_API_KEY=sk-...
DEEPSEEK_API_KEY=...
ANTHROPIC_API_KEY=sk-ant-...
```

Web UI ile: `https://127.0.0.1:5443/sistem-ayarlari`

---

## 6. Server Baslatma / Durdurma

**Tek tikla:**
```powershell
D:\YazKlinik_Final_D300\D300_BASLAT.bat
```

**Manuel:**
```powershell
Set-Location "D:\YazKlinik_Final_D300"
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" -u yazklinik_web.py
```

**Port'u kim tutuyor:**
```powershell
Get-NetTCPConnection -LocalPort 5443 | Select OwningProcess, State
```

**Durdur:**
```powershell
$pids = (netstat -ano | findstr LISTENING | findstr 5443 | ForEach-Object { ($_ -split '\s+')[-1] })
foreach ($p in $pids) { Stop-Process -Id $p -Force }
```

**Cache temizle (WebShell):**
```powershell
Get-Process msedge -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\YazKlinik\BrowserShellCache" -ErrorAction SilentlyContinue
Remove-Item -Recurse -Force "$env:LOCALAPPDATA\YazKlinik\BrowserShell\Default\Cache" -ErrorAction SilentlyContinue
```

---

## 7. DB Yapisi (SQLite, 73 tablo)

**Yol:** `D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3`

**Ana tablolar:**

| Tablo | PK / FK | Aciklama |
|---|---|---|
| `patients` | `folder_key` PK | Hasta klasoru |
| `patient_protocols` | `patient_key` FK | Protokol no |
| `patient_demographics` | `patient_key` FK | yas, lmp_override, data_json |
| `visits` | `patient_folder_key` FK | gelis kaydi |
| `files` | `patient_folder_key` FK | PDF/JPG dosya |
| `usg_measurements` | `patient_key` FK | GA/BPD/HC/AC/FL/EFW |
| `prescriptions` | `patient_key` FK | Recete (D300 e-Recete 5 sutun) |
| `consent_forms` | (form_key PK) | Onam (D300 BLOB icinde) |
| `ready_prescription_templates` | (id PK) | Hazir recete sablonlari |
| `web_audit_log` | `patient_key` | islem audit |
| `settings` | `key` PK | sysparam (kullanici tercih) |

**52 tablo `patient_key` icerir** â€” merge icin `_MERGE_FK_TABLES` listesi.

**DB sorgusu:**
```powershell
& "C:\...\python.exe" -c "import sqlite3; con=sqlite3.connect(r'D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3'); print(con.execute('SELECT COUNT(*) FROM patients').fetchone())"
```

---

## 8. Onemli Route'lar (en sik kullanilan)

```
/                          dashboard
/giris                     login
/hastalar                  hasta listesi
/yeni-hasta                yeni hasta
/hasta/<key>               hasta dosyasi
/hasta/<key>/recete        bu hastanin receteleri (Gor/Bas/Sil)
/hasta/<key>/recete-hazirla yeni recete olustur
/hasta/<key>/recete/goruntule/<rx_id>  recete print HTML
/hasta/<key>/recete/sil/<rx_id>  recete sil (POST)
/hasta/<key>/onam          hastanin onamlari
/akilli-dialog             Alex AI chat (wake word "alex")
/ses-ve-alex               Ses + Alex merkezi
/recete-sablonlari         hazir recete sablon yonetimi
/onam-sablonlari           onam database + toplu import (D300)
/onam/ac/<id>              onam ac (inline)
/onam/yazdir/<id>          onam yazdir (auto-print iframe)
/onam/indir/<id>           onam indir
/tedavi-planla             Tedavi Planlayici
/ivf-konsult               IVF protokol + Hizli Klinik Bilgi (D300 inline)
/obgyn-rehber              klinik rehber 11 kategori
/diyet-rehberi             8 senaryo diyet
/sistem-ayarlari           â˜… NAS/DB/port ayar UI
/api/sistem-durumu         JSON sistem health
```

Tam liste: `CODEX_API_ENDPOINTS.md`

---

## 9. D300 Son Seans Degisiklikleri (2026-05-12)

### ReÃ§ete (e-ReÃ§ete 5 sÃ¼tun standardÄ±)

- **`drug_fields` defaults:** `["name", "route", "dose", "daily", "box"]`
- SÃ¼tunlar: Ilac Adi | Kullanim Sekli | Doz | Periyot | Adet
- **Routes:** AGIZDAN / VAJINAL / INTRAMUSKULER / SUBKUTAN / **REKTAL** (D300 ekleme)
- **Dose:** `5x1` (gunde N kez x her seferinde M tane)
- **Periyot:** `1 X GUN` / `1 X HAFTA` / `2 X AY`
- **Adet:** `DIB (Bir)` / `DIB (Iki)` (e-Recete formati)
- **DB lock migration:** `sysparam_rx_print_d250_erecete_locked` = "1"
- `_rx_build_medications_text()` artik route+period+daily korur (round-trip kayipsiz)
- `_rx_parse_medications_items()` REKTAL regex ekledi
- Hasta recete sayfasinda **Gor / Bas / Duzenle / Sil** butonlari
- `/hasta/<key>/recete/goruntule/<rx_id>` + `?print=1` auto-print
- `/hasta/<key>/recete/sil/<rx_id>` POST hard delete + confirm

### Onam Sistemi (D300)

- **6 kategori:** Gebelik / Infertilite / Jinekoloji / **Jinekolojik Estetik** / **Medikal Estetik** / Paylasim Izinleri
- **`_onam_classify_bulk()`** otomatik kategorize (anahtar kelime + PDF iceriÄŸi)
- **`/onam-sablonlari`** sayfasinda:
  - YeÅŸil **"Toplu Onam Import"** karti (sunucu klasor yolu + coklu dosya)
  - Kategori basliklarina gore gruplama + ikonlu
  - **Use score sort:** her kategori icinde en cok kullanilan ustte
  - **Rozetler:** ğŸ† #1, #2, #3 + use count badge (renkli)
- **`/onam/yazdir/<id>`** PDF iframe + window.print() auto
- Bulk import helper'lari: `_onam_bulk_import_folder()`, `_onam_bulk_import_uploads()`

### Tema Sistemi (palette-reactive, geniÅŸ Ã§aplÄ±)

- **`yk-premium.css` + `yk-pro-v3.css`:** `--pro-accent`, `--pro-bg`, `--pro-surface`, `--pro-header` artik `var(--palette-accent)` ve 12 palet icin EXPLICIT override
- **GeniÅŸ kapsam:** body, top-header, sidebar, sidebar-brand, card, btn-primary, btn-outline-primary palette-reactive
- **Emergency theme modal** (`<head>` script `yk-theme-emergency-modal`):
  - Kendi DOM'unu yaratir (`#ykThemeModalV3`)
  - Mod + Ic alan paleti (12) + Sol bar paleti (9) tek menude
  - Document-level capture handler 3 katmanli (inline onclick + addEventListener + document capture)
  - **Floating fallback buton** (`#ykFloatingThemeBtn`) sag ust kose her sayfada gorunur (44px daire ğŸ¨)
- **Mobil:** `mobile-bottom-nav`'a Tema linki eklendi

### WebShell Modu

- `_yk_webshell_slim_html()` **agresif voice-agent/smart-guide HTML strip KALDIRILDI** (sadece mobile-bottom-nav stripleniyor)
- `yk-stability.js` + `yk-safari-compat.js` artik **WebShell modunda da inject** ediliyor (onceden filtreleniyordu)
- Alex bar + tema panel + tum butonlar WebShell'de calisir

### Hasta Listesi Filtresi

- **`_patient_name_looks_like_filename_only()`** (yazklinik_web.py L14297)
- `F137230-26-05-07-3__` gibi ad/soyad icermeyen dosya-adi tipi kayitlari GIZLER
- Filter `_load_patient_listing()` icinde (kaynak fonksiyon) â€” tum listelerde aktif
- Arama yapilirsa filtre gevÅŸer (kullanici acikca ID yazdiysa goster)
- Cache key versiyon: `terminal_patients_v3`

### Performance

- `_clean_patient_display_name()` artik **module-level cached import** (onceden her cagrida modul import yapiyordu)
- Mojibake middleware **fast bytes pre-check**: 0xC2/0xC3 byte yoksa decode atla
- yk-premium.css ve yk-pro-v3.css cache versiyon: `?v=d250-25-bar-simple` (her seans bumplandi)

### Alex Bar / Voice Panel

- Tum quickbar + panel butonlarina **inline onclick fallback** eklendi (`pointer-events:auto; cursor:pointer`)
- **Emergency capture handler** (`<head>` script `yk-alex-bar-emergency`):
  - Document-level capture phase
  - TÃ¼m ykVoice* ID'lerini yakalayip URL navigate veya bar kapama
  - `[YK_ALEX] Emergency: ...` log

### IVF Konsult â€” Hizli Klinik Bilgi Sorgu

- 10 chip (Antagonist/Long agonist/PPOS/Gardner/PGT-A/Luteal/ICSI/DuoStim/OHSS/AMH) **artik Alex'e gitmiyor**, **inline bilgi paneli** acar (`#yk-quickinfo-panel`)
- Klinik ozet + kapatma butonu

---

## 10. Onemli Konvansiyonlar

### CSS Cache Busting

`yazklinik_web.py` L26754'te:
```html
<link rel="stylesheet" href="/static/yk-premium.css?v=d250-XX-aciklama">
<link rel="stylesheet" href="/static/yk-pro-v3.css?v=d250-XX-aciklama">
```

CSS edit yaptiktan sonra versiyon stringi bump et â€” yoksa tarayici eski CSS'i tutar.

### F-String Brace Escaping

```python
content = f"""
<style>
  .my-class {{       /* iki kat = literal { */
    color: red;
  }}
</style>
<script>
  if (foo === '{value}') {{ ... }}   /* iki kat brace + tek kat string */
</script>
"""
```

### Inline onclick Fallback Pattern

JS handler IIFE crash etse bile buton calissin diye:
```html
<button onclick="try{ if(typeof xFunc==='function') xFunc(event); else fallback(); }catch(e){ console.error(e); } return false;">
```

`pointer-events:none` icon icine, button uzerinde `pointer-events:auto`.

### Document-Level Capture Handler

Inline + addEventListener her ikisi de fail ederse:
```js
document.addEventListener("click", function(ev) {
  var btn = ev.target.closest("[data-yk-action]");
  if (btn) {
    ev.preventDefault();
    handleAction(btn.dataset.ykAction);
  }
}, true);  // â† capture phase
```

### Mojibake Repair

`yazklinik_textfix.fix_mojibake_text()` â€” kullanici girdisinde Win-1252 cift encode olabilir. POST handler'larda:
```python
diagnosis = fix_mojibake_text(str(request.form.get("diagnosis") or "")).strip()
```

### WebShell Detection

Server-side:
```python
def _yk_is_webshell_request():
    # User-Agent veya yk_webshell=1 query/cookie kontrol
    ...
```

Client-side:
```js
document.documentElement.hasAttribute('data-yazklinik-webshell')
```

---

## 11. Hizli Test Komutlari

```powershell
# 1) Compile check
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" -m py_compile yazklinik_web.py

# 2) Sistem dogrulama
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" CODEX_QUICK_CHECK.py

# 3) HTTP smoke (curl)
curl -s -o /dev/null -w "%{http_code}\n" https://127.0.0.1:5443/

# 4) Login + sayfa cek
curl -s -c /tmp/c.txt -L "https://127.0.0.1:5443/giris" > /dev/null
curl -s -b /tmp/c.txt -c /tmp/c.txt -X POST -d "username=doktor&password=1234" "https://127.0.0.1:5443/giris" > /dev/null
curl -s -b /tmp/c.txt "https://127.0.0.1:5443/" -o /tmp/home.html
wc -c /tmp/home.html

# 5) DB hizli sorgu
& "C:\...\python.exe" -c "import sqlite3; c=sqlite3.connect(r'D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3'); print('Patients:', c.execute('SELECT COUNT(*) FROM patients').fetchone()[0])"
```

---

## 12. Yaygin Gorevler

### Yeni route ekle
1. `yazklinik_web.py` icinde yakin route'larin yanina ekle
2. `@permission_required(...)` decorator dogru sec
3. `@app.route("/...")` URL benzersiz olsun
4. Return `render(content, title="...")` veya `jsonify({...})`
5. Compile + restart + curl test

### Yeni endpoint icin permission
Var olan: `view_patient`, `edit_patient`, `view_prescription`, `edit_prescription`, `view_consent`, `edit_consent`, `view_command_center`, `manage_command_center`...
Yeni gerekiyorsa `_DEFAULT_PERMISSIONS_BY_ROLE` dict'ine ekle.

### DB schema migration
`_ensure_X_schema(con)` pattern:
```python
def _ensure_X_schema(con=None):
    def _run(c):
        c.execute("CREATE TABLE IF NOT EXISTS X (...)")
        cols = {r[1] for r in c.execute("PRAGMA table_info(X)").fetchall()}
        if 'new_col' not in cols:
            try: c.execute("ALTER TABLE X ADD COLUMN new_col TEXT")
            except: pass
    if con: _run(con); return
    with db_conn() as c: _run(c); c.commit()
```

### Yeni CSS rule eklerken
1. `static/yk-premium.css` veya `static/yk-pro-v3.css` icine ekle
2. `yazklinik_web.py` L26754'teki cache versiyon stringi bump
3. WebShell ise tray'den cikis + Edge'i oldur + cache temizle

---

## 13. Troubleshooting

| Sorun | Cozum |
|---|---|
| `unable to open database file` | `config.env` DB path mevcut mu? klasor yazilabilir mi? |
| `\\ASUSTOR\Voluson erisilmiyor` | Map drive (Asustor IP/user/pass) veya `/sistem-ayarlari`'dan farkli path |
| Port 5443 dolu | `D300_BASLAT.bat` otomatik kill; manuel: `Stop-Process -Id <pid>` |
| 500 Internal Server Error | `D300_server_HATA.log` oku; before_request DB check soft-fail |
| Mojibake | UTF-8 BOM yok; source'ta var ise dokunma |
| WebShell buton calismiyor | Cache temizle + Edge oldur + cache klasor sil |
| Tema degismiyor | CSS cache versiyon bump; `<html data-palette="...">` set mi (F12) |
| ReÃ§ete print sutunlari kayiyor | `_rx_build_medications_text()` route+period yazÄ±yor mu? Migration `sysparam_rx_print_d250_erecete_locked`=1 mi? |

---

## 14. Codex / Agent Kurallari

1. **Once oku, sonra yaz.** Kullanici "yap" demeden buyuk degisiklik yapma.
2. **Mevcut pattern'i takip et.** Yeni route eklerken yakindaki route'larin pattern'ini kopyala.
3. **Her degisiklikten sonra:** `python -m py_compile` + restart + curl smoke test.
4. **D300_BASLAT.bat'i kirma.** Launcher script'i degisirken once Read sonra Edit (small).
5. **config.env'e eklerken duzenli ol.** Yorumlu, gruplu, KEY=VALUE format.
6. **CSS edit sonrasi cache versiyon bump** zorunlu.
7. **Inline onclick fallback** kritik UI butonlarinda standart pattern (IIFE crash icin guvence).
8. **Sleep loop kullanma** â€” `Start-Sleep -Seconds 25` blocked. Background command + notification kullan.
9. **Test session ile route check**:
   ```powershell
   $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
   Invoke-WebRequest -Uri "https://127.0.0.1:5443/giris" -Method POST -Body @{username="doktor"; password="1234"} -WebSession $session
   Invoke-WebRequest -Uri "https://127.0.0.1:5443/<route>" -WebSession $session
   ```

---

## 15. Kullaniciya Cevap Stili (ornek)

```
Yaptim.

**Dosyalar:**
- yazklinik_web.py L12345 - X eklendi (5 satir)
- static/yk-premium.css L2200 - Y CSS rule

**Test:**
- COMPILE_OK
- HTTP 200 /yeni-route

Server https://127.0.0.1:5443/yeni-route aktif. Ctrl+Shift+R ile cache atla.
```

---

## 16. Versiyon

**D300 (2026-05-12)** | **Yazar:** Op. Dr. Hakan YAZ | **Stack:** Python 3.10 + Flask + waitress + sqlite3 + Bootstrap 5 + WebShell

**Son guncellenen:** 2026-05-12 (D300 e-Recete + onam toplu import + tema palette-reactive + Alex bar fallback + filename filter)

---

**Bu dosyayi ilk ac:** `CODEX_PROJECT.md` (bu dosya)  
**Sonra detay:** `AGENTS.md`, `CODEX_FILE_MAP.md`, `CODEX_COMMANDS.md`, `CODEX_API_ENDPOINTS.md`



