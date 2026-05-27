# CODEX HANDOFF â€” BulutKlinik â†” Voluson Entegrasyon (2026-05-16)

**BaÄŸlam:** Op. Dr. Hakan Yaz (OB-GYN) iÃ§in YazKlinik D700 lokal Flask/SQLite app + BulutKlinik bulut SaaS + Voluson NAS USG dosyalarÄ± arasÄ±nda kÃ¶prÃ¼.

**Server:** `https://127.0.0.1:5443` (waitress, HTTPS). Restart: `D500_BASLAT.bat` veya `Stop-Process` + lock dosyasÄ± sil (`$env:LOCALAPPDATA\Temp\YazKlinik\locks\web_5443.lock`) + `python -u yazklinik_web.py`.

---

## Ã–ZET â€” Bu session'da ne yapÄ±ldÄ±

1. **BulutKlinik veri Ã§ekme** â€” son 90 gÃ¼n protokol + tÃ¼m hastalar + obstetri xlsx + tahsilatlar import (3 mode: `since` / `missing` / `all`)
2. **Voluson eÅŸleÅŸtirme** â€” TR-normalize ad/soyad â†’ folder_key match (auto + manuel onay, gebe filtre)
3. **Hasta detay sayfasÄ±** â€” kimlik, iletiÅŸim, medikal, protokoller, obstetri USG tablosu, tahsilatlar
4. **Ã‡ift yÃ¶n sync** (her ikisi de yerel + manuel akÄ±ÅŸ):
   - Voluson â‡’ BK (yerel dÃ¼zeltme + clipboard manuel paste)
   - BK â‡’ Voluson (patient_demographics'e yazma)
5. **Alex iyileÅŸtirmeleri**: Whisper hallÃ¼sinasyon filtresi, llama3.1:8b â†’ qwen2.5:32b (TÃ¼rkÃ§e), "Hakan Yaz" Rus aksanÄ± dÃ¼zeltme
6. **DiÄŸer UI**: `/bk-hastalar` liste (DataTables yerine vanilla JS), `/bk-hastalar/<no>` detay, `/bk-voluson-match` eÅŸleÅŸtirme sayfasÄ±

---

## YENÄ° DOSYALAR

| Dosya | AmaÃ§ |
|---|---|
| `yazklinik_bulutklinik_import.py` | BK hasta/protokol/obstetri/tahsilat CSV+XLSX import (3 mode: since/all/missing). CLI: `python yazklinik_bulutklinik_import.py --mode missing --dry-run` |

---

## DEÄÄ°ÅTÄ°RÄ°LEN DOSYALAR

### `yazklinik_web.py` (Flask ana uygulama)
- **Line ~26447** â€” `_OLLAMA_RECOMMENDED_TASK_PREFS["phone"]` â†’ `qwen2.5:32b` ilk sÄ±ra (TÃ¼rkÃ§e iÃ§in, RTX 5090'da ~30 t/s)
- **Line ~49609** â€” `_alex_is_meaningful_input(text)` â€” Whisper hallÃ¼sinasyon filtresi (tek-kelime block + takvim isimleri + tekrar â‰¥2)
- **Line ~55369 ve ~55994** â€” Alex sistem prompt (2 voice endpoint): kural 12 (gramer: olucamâ†’olacaÄŸÄ±m), kural 13 (TTS Rus aksanÄ±: "Hakan Yaz" â†’ "Doktor/Hocam")
- **Line ~123516+** â€” `/bulutklinik-merkez` sayfasÄ±: yeni "Local Database" tile + 3 import butonu (Son 90 gÃ¼n / Eksik hastalar / TÃ¼mÃ¼nÃ¼) + "Voluson Eslestir" link
- **Line ~124277+** â€” Hasta liste / detay sayfalarÄ± ve API endpoint'leri (aÅŸaÄŸÄ±da)

### `yazklinik_bulutklinik_cookie_client.py`
- Ã–nceki session'da eklenmiÅŸti: `EXPORT_CATEGORIES` dict (8 kategori), `export_category()`, `export_all()`, Calendar API (today/tomorrow/last_week/next_week), `calendar_search_patient`

---

## YENÄ° DB TABLOLARI (SQLite, `local_db/yazklinik_v68.sqlite3`)

```sql
-- BK hasta + protokol ana kopya
bk_patients (bk_hasta_no PK, tc_kimlik, ad, soyad, cinsiyet, uyruk,
             telefon, eposta, adres, dogum_tarihi, dogum_yeri, medeni_hali,
             kan_grubu, baba_adi, anne_adi, alerjiler, ozgecmis, soygecmis,
             gelis_nedeni, not_text, anlasmali_kurum, ...)
bk_protocols (protokol_no PK, bk_hasta_no FK, isim, soyisim, brans,
              doktor, protokol_tarihi, protokol_tipi, gelis_nedeni, ...)

-- Obstetri (xlsx'ten)
bk_obstetri_index (bk_hasta_no PK, visit_count, last_visit, first_visit, updated_at)
bk_obstetri_visits (bk_hasta_no, takip_no, tarih, usg_age, efw, amnion,
                    plasenta, serviks, hb, hct, mcv, plt, tit, diger, kilo,
                    ta, sikayet, olusturulma, guncelleme, row_hash PK)

-- Tahsilatlar (csv'den)
bk_payments (payment_id PK, protokol_no, bk_hasta_no, hasta_ad, hasta_soyad,
             odenen, cinsi, tarih, row_hash UNIQUE, imported_at)

-- Voluson â†” BK eÅŸleÅŸtirme (manuel + auto)
bk_voluson_links (bk_hasta_no PK, folder_key, match_kind, confidence,
                  matched_at, matched_by, note)

-- Yerel edit audit log + BK sync durumu
bk_patient_changes (id PK, bk_hasta_no, field, old_value, new_value,
                    changed_at, changed_by, synced_to_bk DEFAULT 0,
                    synced_at, sync_method)
```

**Mevcut Voluson tablolarÄ± kullanÄ±lÄ±yor:**
- `patients (folder_key, display_name, full_path, archived_at, ...)`
- `patient_demographics (patient_key, tc_no, phone, birth_date, blood_type,
                         allergies, chronic_conditions, dicom_patient_id, ...)`

---

## YENÄ° API ENDPOINT'LERÄ°

### Import
- `POST /api/bk-hastalar/import-run?mode=since|all|missing` â€” BulutKlinik'ten import Ã§alÄ±ÅŸtÄ±r

### Liste / Detay
- `GET /bk-hastalar` â€” vanilla JS liste (arama + sÄ±ralama + sayfalama, jQuery yok)
- `GET /api/bk-hastalar/list` â€” JSON liste
- `GET /bk-hastalar/<bk_no>` â€” hasta detay sayfasÄ±

### Yerel dÃ¼zenleme (BK ile manuel sync)
- `POST /api/bk-hastalar/<bk_no>/update` â€” bk_patients gÃ¼ncelle + bk_patient_changes log
- `GET /api/bk-hastalar/<bk_no>/changes` â€” pending deÄŸiÅŸimler (synced=0)
- `POST /api/bk-hastalar/<bk_no>/mark-synced` â€” manuel BK aktarma sonrasÄ± iÅŸaretle

### Voluson â‡’ BK Ã§ekme (Voluson'dan BK'ya Ã¶ner)
- `GET /api/bk-hastalar/<bk_no>/voluson-suggest`
- `POST /api/bk-hastalar/<bk_no>/voluson-apply` â€” onaylananlarÄ± bk_patients'a yaz

### BK â‡’ Voluson aktarma (BK'dan Voluson'a yaz)
- `GET /api/bk-hastalar/<bk_no>/voluson-export-suggest`
- `POST /api/bk-hastalar/<bk_no>/voluson-export-apply` â€” patient_demographics'e yaz

### Voluson eÅŸleÅŸtirme
- `GET /bk-voluson-match` â€” eÅŸleÅŸtirme sayfasÄ± (dropdown: 30/60/90/180/365/Hepsi gÃ¼n filtresi, default 90)
- `GET /api/bk-voluson/match-candidates?days=90` â€” JSON
- `POST /api/bk-voluson/link` â€” manuel baÄŸla
- `POST /api/bk-voluson/unlink` â€” sil
- `POST /api/bk-voluson/auto-confirm?days=90` â€” tÃ¼m exact (score=1.0) baÄŸla

### Var olan (cookie tabanlÄ±)
- `GET /api/bulutklinik/cookie/events?range=today|tomorrow|...`
- `GET /api/bulutklinik/cookie/patient-search?q=AYÅEGÃœL`
- `GET /api/bulutklinik/cookie/export/<int:cid>` (0-7)
- `GET /api/bulutklinik/cookie/export-all` â€” ZIP

---

## Ã–NEMLÄ° KARARLAR / BULGULAR

### BulutKlinik portal yapÄ±sÄ±
- **SPA** (Single Page Application, JS-driven). REST endpoint'leri JS bundle iÃ§inde, deeplink yok.
- **Ã‡alÄ±ÅŸan endpoint'ler** (cookie ile POST/GET):
  - `/App/My/favorites.gg` (anasayfa)
  - `/Protocol/<no>` (protokol detay â€” kullanÄ±cÄ± paylaÅŸtÄ±)
  - `/MyPatients` (hasta listesi sayfasÄ±, form ile search)
  - `/Med/Medical/my_patients_list_v2` (DataTables AJAX, POST)
  - `/Pat/Patient/search` (POST, HTML dÃ¶ner)
  - `/Pat/Patient/del_patient` (POST)
  - **`/Pat/Patient/update_patient`** (POST, 500 dÃ¶nÃ¼yor â€” field schema bilinmiyor)
  - `/Sec/Security/export_data/<id>` (CSV/XLSX download)
- **404 dÃ¶nen pattern'ler** (denenmiÅŸ): `/Cln/Hasta/*`, `/App/Hasta/*`, `/Pat/Patient/edit/*`, `/Pat/Patient/save_patient`, vb.

### Otomatik POST yapÄ±lamadÄ± Ã§Ã¼nkÃ¼:
- `update_patient` empty POST â†’ 500, body boÅŸ, field schema gizli
- TÃ¼m form field name varyasyonlarÄ± 404
- CSRF token gerekli olabilir (XSRF/Yii framework)
- Playwright ile DOM probe yapÄ±ldÄ±: tablo satÄ±r click event SPA tarafÄ±ndan yenmiÅŸ, modal/panel aÃ§Ä±lmadÄ± (DOM selector belirsiz)

### Mevcut Ã§Ã¶zÃ¼m: **manuel kopya-yapÄ±ÅŸtÄ±r**
- "BK'ya Aktar" butonu modal aÃ§ar
- Her deÄŸiÅŸim iÃ§in ayrÄ± `[Kopyala]` buton
- "BK Portal AÃ§" linki + TC kimlik kopya
- Doktor BK'da yapÄ±ÅŸtÄ±r + kaydet â†’ YazKlinik'te "AktarÄ±ldÄ± - Ä°ÅŸaretle"
- `bk_patient_changes.synced_to_bk = 1` olarak iÅŸaretlenir

### Voluson tarafÄ±
- 80 aktif hasta (patients tablosu, archived_at NULL)
- 23 hasta otomatik exact match ile baÄŸlandÄ± (test sonucu) â€” TR normalize: Ä±â†’i, ÅŸâ†’s, ÄŸâ†’g, Ã¼â†’u, Ã¶â†’o, Ã§â†’c, sort tokens (sÄ±ra baÄŸÄ±msÄ±z)
- 135 hasta Voluson'da yok â€” Ã§oÄŸu jinekoloji/kontrol, normal (Voluson sadece gebe USG)
- **Gebe filtre**: `bk_obstetri_index`'te kayÄ±tlÄ± olan hastalar gebe sayÄ±lÄ±r â†’ "GEBE+Voluson YOK (Acil)" filtre kritik liste

### Encoding notu
- BulutKlinik CSV exportlarÄ± **UTF-8** (BOM'lu). TÃ¼rkÃ§e karakterler doÄŸru. Terminal cp1252 gÃ¶stermez ama DB'de temizdir.
- Stdout iÃ§in: `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')` â€” **sadece `if __name__ == "__main__"`** iÃ§inde olmalÄ± (module reload bug var, bkz. yazklinik_bulutklinik_import.py)

---

## YAPILACAKLAR (TODO â€” codex'e devir)

### Acil
1. **TUBA KURT (#3387) gerÃ§ek test**: yerel "DÃ¼zenle" + "BK'ya Aktar" akÄ±ÅŸÄ±nÄ± sen test et (kullanÄ±cÄ± son saatte hata aldÄ±, fix sonrasÄ± restart gerekti). EÄŸer `con.description â†’ cursor.description` fix sonrasÄ± hala bir sorun varsa logla.
2. **`/bk-hastalar` 166 hastadan 3269'a Ã§Ä±k**: KullanÄ±cÄ± `/bulutklinik-merkez` â†’ **"Eksik hastalar"** veya **"TUMUNU CEK"** tÄ±klayacak â†’ 3269 yeni hasta + obstetri xlsx + tahsilatlar import. DoÄŸrulama: `SELECT COUNT(*) FROM bk_patients` (166 â†’ ~3435 olmalÄ±).

### Otomatik POST (kullanÄ±cÄ± 2. seÃ§eneÄŸi seÃ§miÅŸti)
KullanÄ±cÄ± iÃ§in Network'ten kopya-yapÄ±ÅŸtÄ±r pratik olmadÄ± ("anlamadÄ±m sen yap"). 3 alternatif:

**A) Playwright tam otomasyon** (orta zor)
- Cookie inject + headful Chromium aÃ§
- `/MyPatients` â†’ search input doldur (`med_name_surname`) â†’ submit
- DataTables satÄ±r click handler'Ä± bul (DOM olay listener inspect)
- "DÃ¼zenle" buton bul + tÄ±kla â†’ form HTML yakala
- Form field name'lerini extract et + Kaydet â†’ network POST yakala
- Risk: BK UI deÄŸiÅŸince patlar
- Yer: yeni dosya `bulutklinik_playwright_writer.py` Ã¶neririm

**B) API key (en saÄŸlam, sen alacaksÄ±n)**
- BK panel â†’ Ayarlar â†’ API Erisim â†’ 4 alan: Client ID, Secret Key, User (eposta), Password
- `/bulutklinik` ayarlar sayfasÄ±nda gir
- Resmi REST API ile yazma/okuma
- Cookie baÄŸÄ±mlÄ±lÄ±ÄŸÄ± sÄ±fÄ±r

**C) Browser extension** (son Ã§are)
- Userscript / Tampermonkey: BulutKlinik portal'inde otomatik POST yakalayan + YazKlinik API'ye gÃ¶nderen
- KullanÄ±cÄ± bir kere kurar, her hasta dÃ¼zenlemede otomatik

### DiÄŸer eklenebilecekler
- **Cron incremental sync** â€” her 30 dk arka planda `/api/bk-hastalar/import-run?mode=missing` Ã§aÄŸÄ±r (cookie geÃ§erliyse)
- **BirleÅŸik hasta sayfasÄ±** â€” `/hasta/<folder>` sayfasÄ±nda saÄŸ panele BK detaylarÄ± (zaten 2 ayrÄ± sayfa var, JOIN'lemek)
- **BirleÅŸik arama** â€” sidebar single search: hem `patients` (Voluson) hem `bk_patients` JOIN
- **NAS yazma** â€” Voluson'da yeni klasÃ¶r oluÅŸtur (BK'da gebe ama henÃ¼z USG yok â†’ skeleton folder + demographics dosyasÄ±)
- **Alex RAG** â€” bk_patients'Ä± ChromaDB'ye index'le ("ÅÄ°RÄ°N ASLI'nÄ±n son protokolleri" sorgusu)
- **`/bk-hastalar/<no>/edit-history`** â€” bk_patient_changes audit log sayfasÄ± (kim ne deÄŸiÅŸtirdi)

---

## BÄ°LÄ°NEN SORUNLAR / DÄ°KKAT

1. **Server restart gerekir** â€” Flask waitress auto-reload yapmaz. Her kod deÄŸiÅŸikliÄŸinden sonra:
   ```powershell
   $pid_n = (Get-NetTCPConnection -State Listen -LocalPort 5443).OwningProcess
   Stop-Process -Id $pid_n -Force
   Remove-Item "$env:LOCALAPPDATA\Temp\YazKlinik\locks\web_5443.lock" -ErrorAction SilentlyContinue
   # Sonra: D500_BASLAT.bat veya python -u yazklinik_web.py
   ```

2. **Cookie expire** â€” BulutKlinik cookie 24-72 saat geÃ§erli. BittiÄŸinde:
   ```
   D:\YazKlinik_Final_D500\.venv\Scripts\python.exe D:\YazKlinik_Final_D500\bulutklinik_cookie_cdp.py
   ```

3. **Replace_all bug**: `print(` â†’ `_safe_print(` yaparken **fonksiyon gÃ¶vdesindeki print'i de** etkiledi, recursion. DÃ¼zeltme: `_safe_print` iÃ§inde `builtins.print` kullan (zaten yapÄ±ldÄ±).

4. **F-string + tek tÄ±rnaklÄ± string**: `'BulutKlinik\\'e'` Python parse hatasÄ± verir. Ã‡ift tÄ±rnaklÄ± string + escape kullan: `"BulutKlinik'e"`.

5. **`con.description` HATAS!** â€” sqlite3 Connection objesinde `description` yok, Cursor'da var:
   ```python
   cur = con.execute("SELECT ...")  # Cursor!
   row = cur.fetchone()
   cols = [d[0] for d in cur.description]  # cur, not con
   ```

6. **Detay sayfasÄ±nda JS f-string** â€” `{repr(bk_no)}` kullanÄ±lÄ±yor, single quote escape sorunsuz.

7. **DataTables yok** â€” yazklinik_web.py'da jQuery yÃ¼klÃ¼ deÄŸil, sadece `jquery.dataTables.min.js` koy â†’ patlar. Vanilla JS kullan veya jQuery CDN ekle.

---

## DOSYA REFERANSLARI

| Dosya | Ã–nemli line'lar |
|---|---|
| `yazklinik_web.py` | 26447 (model prefs), 49609 (Whisper filtre), 55369+55994 (Alex prompt), 123516+ (bulutklinik-merkez), 124277+ (BK route'larÄ±) |
| `yazklinik_bulutklinik_import.py` | tÃ¼m dosya (~500 satÄ±r) |
| `yazklinik_bulutklinik_cookie_client.py` | EXPORT_CATEGORIES, export_category, calendar_* |
| `bulutklinik_cookie_cdp.py` | Cookie yenileme scripti (Chrome --remote-debugging-port + Playwright CDP) |
| `local_db/yazklinik_v68.sqlite3` | DB (WAL mode) |

---

## TEST KOMUTLARI

```powershell
# Sistem doÄŸrulama
& "D:\YazKlinik_Final_D500\.venv\Scripts\python.exe" D:\YazKlinik_Final_D500\CODEX_QUICK_CHECK.py

# Syntax check
& "D:\YazKlinik_Final_D500\.venv\Scripts\python.exe" -c "import py_compile; py_compile.compile(r'D:\YazKlinik_Final_D500\yazklinik_web.py', doraise=True); print('OK')"

# CLI import dry-run
D:\YazKlinik_Final_D500\.venv\Scripts\python.exe D:\YazKlinik_Final_D500\yazklinik_bulutklinik_import.py --mode missing --dry-run

# DB hÄ±zlÄ± durum
D:/YazKlinik_Final_D500/.venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect(r'D:\YazKlinik_Final_D500\local_db\yazklinik_v68.sqlite3'); [print(t,c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in ('bk_patients','bk_protocols','bk_obstetri_index','bk_obstetri_visits','bk_payments','bk_voluson_links','bk_patient_changes')]"
```

---

## SESSION BOYUNCA KARARLAR (Ã¶zet)

- **Voluson eÅŸleÅŸtirme** sadece "son N gÃ¼n protokollÃ¼" hastalar iÃ§in (default 90 gÃ¼n) â€” eski 3000+ hasta listeyi ÅŸiÅŸirmez
- **CDN baÄŸÄ±mlÄ±lÄ±ÄŸÄ± yok** â€” `/bk-hastalar` sayfasÄ± DataTables yerine vanilla JS (offline Ã§alÄ±ÅŸsÄ±n)
- **Phone model qwen2.5:32b** â€” llama3.1:8b TÃ¼rkÃ§e'de "olucam/yardÄ±mcÄ±lmak" gibi uydurma kelimeler Ã¼retiyordu
- **Manuel sync default** â€” otomatik POST keÅŸfedilemediÄŸi iÃ§in clipboard rehberi, audit log ile
- **NAS yazma yok (ÅŸimdilik)** â€” sadece DB write (patient_demographics). Yeni Voluson klasÃ¶rÃ¼ oluÅŸturma sonraya bÄ±rakÄ±ldÄ±

---

## KULLANICI ÅÄ°KAYETLERÄ° VE NE YAPILDI

| Åikayet | Ã‡Ã¶zÃ¼m |
|---|---|
| "Alex saÃ§malÄ±yor" | Whisper hallÃ¼sinasyon filtresi v1 + v2 (tek-kelime block, takvim isimleri, repeat detection). Memory clean (18 sahte konuÅŸma silindi). |
| "Daha Ã§ok Ruslar gibi konuÅŸuyor" | llama3.1:8b â†’ qwen2.5:32b (model deÄŸiÅŸimi). Sistem prompt kural 12 (TÃ¼rkÃ§e gramer kurallarÄ±). |
| "Hakan Yaz RusÃ§a aksana dÃ¶nÃ¼yor" | Sistem prompt kural 13: "Hakan Yaz" / "Yaz" sÃ¶yleme, "Doktor/Hocam" de. |
| "Yeni hastalarÄ± Ã§ekemiyor" | Import 3 mode: since (mevcut), missing (DB'de olmayan), all (3000+). Sebep: BK CSV'de "GeliÅŸ Tarihi" boÅŸ, protokol bazlÄ± filter eksik hastalarÄ± kaÃ§Ä±rÄ±yordu. |
| "BK aktar BK'ya gitmedi" | Manuel kopya-yapÄ±ÅŸtÄ±r rehberi olduÄŸunu netleÅŸtirdik. Modal yeniden tasarÄ±m: 3 net adÄ±m + her field iÃ§in ayrÄ± [Kopyala] buton. Otomatik POST keÅŸfedilemedi (`/Pat/Patient/update_patient` var ama 500 + field schema gizli). |
| "Voluson'da yapÄ±lan dÃ¼zeltmeleri BK'ya yÃ¼klemek" | `bk_patient_changes` audit log + pending banner + "BK'ya Aktar" modal (yerel dÃ¼zelt â†’ manuel BK paste â†’ iÅŸaretle). |
| "BK hastasÄ±nÄ±n bilgilerini Voluson'a Ã§ek" | `/api/bk-hastalar/<no>/voluson-suggest` (Voluson klasÃ¶r adÄ± + PDF/DICOM'dan ad/soyad/doÄŸum/TC Ã¶ner) + onay tablosu + apply â†’ bk_patients update + audit log |
| "BK'dan Voluson'a aktar" | `/api/bk-hastalar/<no>/voluson-export-suggest` + apply â†’ patient_demographics tablosuna yaz (TC, telefon, doÄŸum, kan grubu, alerjiler, Ã¶zgeÃ§miÅŸ). 6 izinli field, allowlist gÃ¼venlik. |
| "Bu 2 programÄ± iÃ§iÃ§e kullanmak mÃ¼mkÃ¼n mÃ¼?" | 3 seviye tartÄ±ÅŸÄ±ldÄ±: 1) Ä°frame (BK X-Frame-Options engelliyor â€” imkansÄ±z), 2) Cookie sync (mevcut, kÄ±rÄ±lgan), 3) API key (saÄŸlam, kullanÄ±cÄ± alacak). Mevcut: read-only cookie + manuel write paste. |

---

**Son commit hash:** (henÃ¼z commit yok, hepsi unstaged)
**Server son durum:** PID 26648 (16:18:54 baÅŸladÄ±), restart sonrasÄ± yeni PID
**DB son sayÄ±m** (Ã¶ncesi/sonrasÄ± import bekliyor):
- bk_patients: 166
- bk_protocols: 414
- bk_obstetri_index/visits: 0 (kullanÄ±cÄ± "Eksik hastalar" tÄ±klayÄ±nca dolacak)
- bk_payments: 0
- bk_voluson_links: 0 (otomatik onay henÃ¼z tetiklenmedi)
- bk_patient_changes: 0+ (test edildikÃ§e artar)

