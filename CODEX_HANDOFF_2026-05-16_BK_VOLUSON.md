# CODEX HANDOFF — BulutKlinik ↔ Voluson Entegrasyon (2026-05-16)

**Bağlam:** Op. Dr. Hakan Yaz (OB-GYN) için YazKlinik D300 lokal Flask/SQLite app + BulutKlinik bulut SaaS + Voluson NAS USG dosyaları arasında köprü.

**Server:** `https://127.0.0.1:5443` (waitress, HTTPS). Restart: `D300_BASLAT.bat` veya `Stop-Process` + lock dosyası sil (`$env:LOCALAPPDATA\Temp\YazKlinik\locks\web_5443.lock`) + `python -u yazklinik_web.py`.

---

## ÖZET — Bu session'da ne yapıldı

1. **BulutKlinik veri çekme** — son 90 gün protokol + tüm hastalar + obstetri xlsx + tahsilatlar import (3 mode: `since` / `missing` / `all`)
2. **Voluson eşleştirme** — TR-normalize ad/soyad → folder_key match (auto + manuel onay, gebe filtre)
3. **Hasta detay sayfası** — kimlik, iletişim, medikal, protokoller, obstetri USG tablosu, tahsilatlar
4. **Çift yön sync** (her ikisi de yerel + manuel akış):
   - Voluson ⇒ BK (yerel düzeltme + clipboard manuel paste)
   - BK ⇒ Voluson (patient_demographics'e yazma)
5. **Alex iyileştirmeleri**: Whisper hallüsinasyon filtresi, llama3.1:8b → qwen2.5:32b (Türkçe), "Hakan Yaz" Rus aksanı düzeltme
6. **Diğer UI**: `/bk-hastalar` liste (DataTables yerine vanilla JS), `/bk-hastalar/<no>` detay, `/bk-voluson-match` eşleştirme sayfası

---

## YENİ DOSYALAR

| Dosya | Amaç |
|---|---|
| `yazklinik_bulutklinik_import.py` | BK hasta/protokol/obstetri/tahsilat CSV+XLSX import (3 mode: since/all/missing). CLI: `python yazklinik_bulutklinik_import.py --mode missing --dry-run` |

---

## DEĞİŞTİRİLEN DOSYALAR

### `yazklinik_web.py` (Flask ana uygulama)
- **Line ~26447** — `_OLLAMA_RECOMMENDED_TASK_PREFS["phone"]` → `qwen2.5:32b` ilk sıra (Türkçe için, RTX 5090'da ~30 t/s)
- **Line ~49609** — `_alex_is_meaningful_input(text)` — Whisper hallüsinasyon filtresi (tek-kelime block + takvim isimleri + tekrar ≥2)
- **Line ~55369 ve ~55994** — Alex sistem prompt (2 voice endpoint): kural 12 (gramer: olucam→olacağım), kural 13 (TTS Rus aksanı: "Hakan Yaz" → "Doktor/Hocam")
- **Line ~123516+** — `/bulutklinik-merkez` sayfası: yeni "Local Database" tile + 3 import butonu (Son 90 gün / Eksik hastalar / Tümünü) + "Voluson Eslestir" link
- **Line ~124277+** — Hasta liste / detay sayfaları ve API endpoint'leri (aşağıda)

### `yazklinik_bulutklinik_cookie_client.py`
- Önceki session'da eklenmişti: `EXPORT_CATEGORIES` dict (8 kategori), `export_category()`, `export_all()`, Calendar API (today/tomorrow/last_week/next_week), `calendar_search_patient`

---

## YENİ DB TABLOLARI (SQLite, `local_db/yazklinik_v68.sqlite3`)

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

-- Voluson ↔ BK eşleştirme (manuel + auto)
bk_voluson_links (bk_hasta_no PK, folder_key, match_kind, confidence,
                  matched_at, matched_by, note)

-- Yerel edit audit log + BK sync durumu
bk_patient_changes (id PK, bk_hasta_no, field, old_value, new_value,
                    changed_at, changed_by, synced_to_bk DEFAULT 0,
                    synced_at, sync_method)
```

**Mevcut Voluson tabloları kullanılıyor:**
- `patients (folder_key, display_name, full_path, archived_at, ...)`
- `patient_demographics (patient_key, tc_no, phone, birth_date, blood_type,
                         allergies, chronic_conditions, dicom_patient_id, ...)`

---

## YENİ API ENDPOINT'LERİ

### Import
- `POST /api/bk-hastalar/import-run?mode=since|all|missing` — BulutKlinik'ten import çalıştır

### Liste / Detay
- `GET /bk-hastalar` — vanilla JS liste (arama + sıralama + sayfalama, jQuery yok)
- `GET /api/bk-hastalar/list` — JSON liste
- `GET /bk-hastalar/<bk_no>` — hasta detay sayfası

### Yerel düzenleme (BK ile manuel sync)
- `POST /api/bk-hastalar/<bk_no>/update` — bk_patients güncelle + bk_patient_changes log
- `GET /api/bk-hastalar/<bk_no>/changes` — pending değişimler (synced=0)
- `POST /api/bk-hastalar/<bk_no>/mark-synced` — manuel BK aktarma sonrası işaretle

### Voluson ⇒ BK çekme (Voluson'dan BK'ya öner)
- `GET /api/bk-hastalar/<bk_no>/voluson-suggest`
- `POST /api/bk-hastalar/<bk_no>/voluson-apply` — onaylananları bk_patients'a yaz

### BK ⇒ Voluson aktarma (BK'dan Voluson'a yaz)
- `GET /api/bk-hastalar/<bk_no>/voluson-export-suggest`
- `POST /api/bk-hastalar/<bk_no>/voluson-export-apply` — patient_demographics'e yaz

### Voluson eşleştirme
- `GET /bk-voluson-match` — eşleştirme sayfası (dropdown: 30/60/90/180/365/Hepsi gün filtresi, default 90)
- `GET /api/bk-voluson/match-candidates?days=90` — JSON
- `POST /api/bk-voluson/link` — manuel bağla
- `POST /api/bk-voluson/unlink` — sil
- `POST /api/bk-voluson/auto-confirm?days=90` — tüm exact (score=1.0) bağla

### Var olan (cookie tabanlı)
- `GET /api/bulutklinik/cookie/events?range=today|tomorrow|...`
- `GET /api/bulutklinik/cookie/patient-search?q=AYŞEGÜL`
- `GET /api/bulutklinik/cookie/export/<int:cid>` (0-7)
- `GET /api/bulutklinik/cookie/export-all` — ZIP

---

## ÖNEMLİ KARARLAR / BULGULAR

### BulutKlinik portal yapısı
- **SPA** (Single Page Application, JS-driven). REST endpoint'leri JS bundle içinde, deeplink yok.
- **Çalışan endpoint'ler** (cookie ile POST/GET):
  - `/App/My/favorites.gg` (anasayfa)
  - `/Protocol/<no>` (protokol detay — kullanıcı paylaştı)
  - `/MyPatients` (hasta listesi sayfası, form ile search)
  - `/Med/Medical/my_patients_list_v2` (DataTables AJAX, POST)
  - `/Pat/Patient/search` (POST, HTML döner)
  - `/Pat/Patient/del_patient` (POST)
  - **`/Pat/Patient/update_patient`** (POST, 500 dönüyor — field schema bilinmiyor)
  - `/Sec/Security/export_data/<id>` (CSV/XLSX download)
- **404 dönen pattern'ler** (denenmiş): `/Cln/Hasta/*`, `/App/Hasta/*`, `/Pat/Patient/edit/*`, `/Pat/Patient/save_patient`, vb.

### Otomatik POST yapılamadı çünkü:
- `update_patient` empty POST → 500, body boş, field schema gizli
- Tüm form field name varyasyonları 404
- CSRF token gerekli olabilir (XSRF/Yii framework)
- Playwright ile DOM probe yapıldı: tablo satır click event SPA tarafından yenmiş, modal/panel açılmadı (DOM selector belirsiz)

### Mevcut çözüm: **manuel kopya-yapıştır**
- "BK'ya Aktar" butonu modal açar
- Her değişim için ayrı `[Kopyala]` buton
- "BK Portal Aç" linki + TC kimlik kopya
- Doktor BK'da yapıştır + kaydet → YazKlinik'te "Aktarıldı - İşaretle"
- `bk_patient_changes.synced_to_bk = 1` olarak işaretlenir

### Voluson tarafı
- 80 aktif hasta (patients tablosu, archived_at NULL)
- 23 hasta otomatik exact match ile bağlandı (test sonucu) — TR normalize: ı→i, ş→s, ğ→g, ü→u, ö→o, ç→c, sort tokens (sıra bağımsız)
- 135 hasta Voluson'da yok — çoğu jinekoloji/kontrol, normal (Voluson sadece gebe USG)
- **Gebe filtre**: `bk_obstetri_index`'te kayıtlı olan hastalar gebe sayılır → "GEBE+Voluson YOK (Acil)" filtre kritik liste

### Encoding notu
- BulutKlinik CSV exportları **UTF-8** (BOM'lu). Türkçe karakterler doğru. Terminal cp1252 göstermez ama DB'de temizdir.
- Stdout için: `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')` — **sadece `if __name__ == "__main__"`** içinde olmalı (module reload bug var, bkz. yazklinik_bulutklinik_import.py)

---

## YAPILACAKLAR (TODO — codex'e devir)

### Acil
1. **TUBA KURT (#3387) gerçek test**: yerel "Düzenle" + "BK'ya Aktar" akışını sen test et (kullanıcı son saatte hata aldı, fix sonrası restart gerekti). Eğer `con.description → cursor.description` fix sonrası hala bir sorun varsa logla.
2. **`/bk-hastalar` 166 hastadan 3269'a çık**: Kullanıcı `/bulutklinik-merkez` → **"Eksik hastalar"** veya **"TUMUNU CEK"** tıklayacak → 3269 yeni hasta + obstetri xlsx + tahsilatlar import. Doğrulama: `SELECT COUNT(*) FROM bk_patients` (166 → ~3435 olmalı).

### Otomatik POST (kullanıcı 2. seçeneği seçmişti)
Kullanıcı için Network'ten kopya-yapıştır pratik olmadı ("anlamadım sen yap"). 3 alternatif:

**A) Playwright tam otomasyon** (orta zor)
- Cookie inject + headful Chromium aç
- `/MyPatients` → search input doldur (`med_name_surname`) → submit
- DataTables satır click handler'ı bul (DOM olay listener inspect)
- "Düzenle" buton bul + tıkla → form HTML yakala
- Form field name'lerini extract et + Kaydet → network POST yakala
- Risk: BK UI değişince patlar
- Yer: yeni dosya `bulutklinik_playwright_writer.py` öneririm

**B) API key (en sağlam, sen alacaksın)**
- BK panel → Ayarlar → API Erisim → 4 alan: Client ID, Secret Key, User (eposta), Password
- `/bulutklinik` ayarlar sayfasında gir
- Resmi REST API ile yazma/okuma
- Cookie bağımlılığı sıfır

**C) Browser extension** (son çare)
- Userscript / Tampermonkey: BulutKlinik portal'inde otomatik POST yakalayan + YazKlinik API'ye gönderen
- Kullanıcı bir kere kurar, her hasta düzenlemede otomatik

### Diğer eklenebilecekler
- **Cron incremental sync** — her 30 dk arka planda `/api/bk-hastalar/import-run?mode=missing` çağır (cookie geçerliyse)
- **Birleşik hasta sayfası** — `/hasta/<folder>` sayfasında sağ panele BK detayları (zaten 2 ayrı sayfa var, JOIN'lemek)
- **Birleşik arama** — sidebar single search: hem `patients` (Voluson) hem `bk_patients` JOIN
- **NAS yazma** — Voluson'da yeni klasör oluştur (BK'da gebe ama henüz USG yok → skeleton folder + demographics dosyası)
- **Alex RAG** — bk_patients'ı ChromaDB'ye index'le ("ŞİRİN ASLI'nın son protokolleri" sorgusu)
- **`/bk-hastalar/<no>/edit-history`** — bk_patient_changes audit log sayfası (kim ne değiştirdi)

---

## BİLİNEN SORUNLAR / DİKKAT

1. **Server restart gerekir** — Flask waitress auto-reload yapmaz. Her kod değişikliğinden sonra:
   ```powershell
   $pid_n = (Get-NetTCPConnection -State Listen -LocalPort 5443).OwningProcess
   Stop-Process -Id $pid_n -Force
   Remove-Item "$env:LOCALAPPDATA\Temp\YazKlinik\locks\web_5443.lock" -ErrorAction SilentlyContinue
   # Sonra: D300_BASLAT.bat veya python -u yazklinik_web.py
   ```

2. **Cookie expire** — BulutKlinik cookie 24-72 saat geçerli. Bittiğinde:
   ```
   D:\YazKlinik_Final_D300\.venv\Scripts\python.exe D:\YazKlinik_Final_D300\bulutklinik_cookie_cdp.py
   ```

3. **Replace_all bug**: `print(` → `_safe_print(` yaparken **fonksiyon gövdesindeki print'i de** etkiledi, recursion. Düzeltme: `_safe_print` içinde `builtins.print` kullan (zaten yapıldı).

4. **F-string + tek tırnaklı string**: `'BulutKlinik\\'e'` Python parse hatası verir. Çift tırnaklı string + escape kullan: `"BulutKlinik'e"`.

5. **`con.description` HATAS!** — sqlite3 Connection objesinde `description` yok, Cursor'da var:
   ```python
   cur = con.execute("SELECT ...")  # Cursor!
   row = cur.fetchone()
   cols = [d[0] for d in cur.description]  # cur, not con
   ```

6. **Detay sayfasında JS f-string** — `{repr(bk_no)}` kullanılıyor, single quote escape sorunsuz.

7. **DataTables yok** — yazklinik_web.py'da jQuery yüklü değil, sadece `jquery.dataTables.min.js` koy → patlar. Vanilla JS kullan veya jQuery CDN ekle.

---

## DOSYA REFERANSLARI

| Dosya | Önemli line'lar |
|---|---|
| `yazklinik_web.py` | 26447 (model prefs), 49609 (Whisper filtre), 55369+55994 (Alex prompt), 123516+ (bulutklinik-merkez), 124277+ (BK route'ları) |
| `yazklinik_bulutklinik_import.py` | tüm dosya (~500 satır) |
| `yazklinik_bulutklinik_cookie_client.py` | EXPORT_CATEGORIES, export_category, calendar_* |
| `bulutklinik_cookie_cdp.py` | Cookie yenileme scripti (Chrome --remote-debugging-port + Playwright CDP) |
| `local_db/yazklinik_v68.sqlite3` | DB (WAL mode) |

---

## TEST KOMUTLARI

```powershell
# Sistem doğrulama
& "D:\YazKlinik_Final_D300\.venv\Scripts\python.exe" D:\YazKlinik_Final_D300\CODEX_QUICK_CHECK.py

# Syntax check
& "D:\YazKlinik_Final_D300\.venv\Scripts\python.exe" -c "import py_compile; py_compile.compile(r'D:\YazKlinik_Final_D300\yazklinik_web.py', doraise=True); print('OK')"

# CLI import dry-run
D:\YazKlinik_Final_D300\.venv\Scripts\python.exe D:\YazKlinik_Final_D300\yazklinik_bulutklinik_import.py --mode missing --dry-run

# DB hızlı durum
D:/YazKlinik_Final_D300/.venv/Scripts/python.exe -c "import sqlite3; c=sqlite3.connect(r'D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3'); [print(t,c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0]) for t in ('bk_patients','bk_protocols','bk_obstetri_index','bk_obstetri_visits','bk_payments','bk_voluson_links','bk_patient_changes')]"
```

---

## SESSION BOYUNCA KARARLAR (özet)

- **Voluson eşleştirme** sadece "son N gün protokollü" hastalar için (default 90 gün) — eski 3000+ hasta listeyi şişirmez
- **CDN bağımlılığı yok** — `/bk-hastalar` sayfası DataTables yerine vanilla JS (offline çalışsın)
- **Phone model qwen2.5:32b** — llama3.1:8b Türkçe'de "olucam/yardımcılmak" gibi uydurma kelimeler üretiyordu
- **Manuel sync default** — otomatik POST keşfedilemediği için clipboard rehberi, audit log ile
- **NAS yazma yok (şimdilik)** — sadece DB write (patient_demographics). Yeni Voluson klasörü oluşturma sonraya bırakıldı

---

## KULLANICI ŞİKAYETLERİ VE NE YAPILDI

| Şikayet | Çözüm |
|---|---|
| "Alex saçmalıyor" | Whisper hallüsinasyon filtresi v1 + v2 (tek-kelime block, takvim isimleri, repeat detection). Memory clean (18 sahte konuşma silindi). |
| "Daha çok Ruslar gibi konuşuyor" | llama3.1:8b → qwen2.5:32b (model değişimi). Sistem prompt kural 12 (Türkçe gramer kuralları). |
| "Hakan Yaz Rusça aksana dönüyor" | Sistem prompt kural 13: "Hakan Yaz" / "Yaz" söyleme, "Doktor/Hocam" de. |
| "Yeni hastaları çekemiyor" | Import 3 mode: since (mevcut), missing (DB'de olmayan), all (3000+). Sebep: BK CSV'de "Geliş Tarihi" boş, protokol bazlı filter eksik hastaları kaçırıyordu. |
| "BK aktar BK'ya gitmedi" | Manuel kopya-yapıştır rehberi olduğunu netleştirdik. Modal yeniden tasarım: 3 net adım + her field için ayrı [Kopyala] buton. Otomatik POST keşfedilemedi (`/Pat/Patient/update_patient` var ama 500 + field schema gizli). |
| "Voluson'da yapılan düzeltmeleri BK'ya yüklemek" | `bk_patient_changes` audit log + pending banner + "BK'ya Aktar" modal (yerel düzelt → manuel BK paste → işaretle). |
| "BK hastasının bilgilerini Voluson'a çek" | `/api/bk-hastalar/<no>/voluson-suggest` (Voluson klasör adı + PDF/DICOM'dan ad/soyad/doğum/TC öner) + onay tablosu + apply → bk_patients update + audit log |
| "BK'dan Voluson'a aktar" | `/api/bk-hastalar/<no>/voluson-export-suggest` + apply → patient_demographics tablosuna yaz (TC, telefon, doğum, kan grubu, alerjiler, özgeçmiş). 6 izinli field, allowlist güvenlik. |
| "Bu 2 programı içiçe kullanmak mümkün mü?" | 3 seviye tartışıldı: 1) İframe (BK X-Frame-Options engelliyor — imkansız), 2) Cookie sync (mevcut, kırılgan), 3) API key (sağlam, kullanıcı alacak). Mevcut: read-only cookie + manuel write paste. |

---

**Son commit hash:** (henüz commit yok, hepsi unstaged)
**Server son durum:** PID 26648 (16:18:54 başladı), restart sonrası yeni PID
**DB son sayım** (öncesi/sonrası import bekliyor):
- bk_patients: 166
- bk_protocols: 414
- bk_obstetri_index/visits: 0 (kullanıcı "Eksik hastalar" tıklayınca dolacak)
- bk_payments: 0
- bk_voluson_links: 0 (otomatik onay henüz tetiklenmedi)
- bk_patient_changes: 0+ (test edildikçe artar)
