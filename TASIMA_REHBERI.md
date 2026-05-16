# YazKlinik D300 — RTX 5090 PC'ye Taşıma Rehberi

> **5 adım** ile yeni PC'de çalışır hale gelir. Süre: ~30-45 dakika.

## ÖZET

Yeni PC'de **sıfır kurulum** yapacaksın. Şu sıra ile gideceksin:

1. **D klasörünü kopyala** (1 dakika)
2. **SETUP_RTX5090.bat çift tıkla** (30-40 dakika otomatik kurulum)
3. **Windows'u yeniden başlat** (TR TTS aktif olsun)
4. **D300_BASLAT.bat çift tıkla** (test)
5. **Claude Code'u aç → "CLAUDE_HANDOFF.md oku" de** (yeni sohbet başlayacak)

---

## ADIM 1 — Dosyaları taşı

### Bu PC'den (mevcut)

**`D:\YazKlinik_Final_D300\`** klasörünün TAMAMINI yeni PC'ye kopyala.

Kopyalama yolları (hangisini istersen):

- **USB harici disk** (en hızlı, ~5-10 GB) — direkt kopyala-yapıştır
- **Ağ paylaşımı** — eski PC'de `D:\YazKlinik_Final_D300\` paylaş, yeni PC'den eş
- **OneDrive / Google Drive** — yükle, indir
- **WinSCP / robocopy** — yapıştırma sırasında bozulma yapmaz

### KOPYALAMADAN ÖNCE bu klasörleri **TEMİZLE** (yer kazanma — boyutu küçültür)

```
D:\YazKlinik_Final_D300\.venv\           ← yeni PC'de yeniden oluşacak (SETUP yapar)
D:\YazKlinik_Final_D300\temp\            ← geçici dosyalar
D:\YazKlinik_Final_D300\dicom_cache\     ← cache, gerek yok (NAS'tan yeniden gelir)
D:\YazKlinik_Final_D300\D300_server.log
D:\YazKlinik_Final_D300\D300_server_HATA.log
D:\YazKlinik_Final_D300\D300_whisper_service.log
```

### KOPYALANMASI ŞART olan dosyalar

```
D:\YazKlinik_Final_D300\
├── yazklinik_web.py                    ← ana uygulama
├── yazklinik_whisper_service.py
├── yazklinik_v68.py                    ← dokunulmaz eski sürüm
├── yazklinik_feature_sync.py
├── yazklinik_common.py
├── *.py (kalan modüller)
├── *.bat (D300_BASLAT, START_WHISPER, SETUP_RTX5090)
├── *.ps1 (SETUP_RTX5090, INSTALL_TURKISH_TTS)
├── requirements.txt
├── config.env                          ← AYAR DOSYASI (önemli)
├── config.rtx5090.env                  ← RTX profili şablon
├── CLAUDE.md
├── CLAUDE_HANDOFF.md                   ← Yeni Claude için
├── TASIMA_REHBERI.md                   ← BU DOSYA
├── certs\                              ← SSL sertifikası
├── local_db\yazklinik_v68.sqlite3      ← VERİTABANI (kritik!)
├── auto_backups\                       ← önceki DB yedekleri
└── static\, templates\, vb. klasörler
```

### Çift kontrol et (yeni PC'de kopyalama sonrası)

```powershell
# Yeni PC'de PowerShell'de
cd D:\YazKlinik_Final_D300
Get-ChildItem yazklinik_web.py, requirements.txt, SETUP_RTX5090.bat, config.env, local_db
```

Hepsi gözükmeli. Gözükmüyorsa kopyalama eksik.

---

## ADIM 2 — Setup'u çalıştır

### Hazırlık

Yeni PC'de **internet bağlantısı** olmalı (paketler, Whisper modelleri indirilecek).

NVIDIA driver'ın son sürüm olduğundan emin ol:
- https://www.nvidia.com/Download/index.aspx
- RTX 5090 için en güncel driver yüklü olsun

### Setup başlat

1. `D:\YazKlinik_Final_D300\SETUP_RTX5090.bat`'a **çift tıkla**
2. Açılan pencerede bir tuşa bas (Enter)
3. UAC penceresi açılır → **Evet** tıkla
4. Yönetici PowerShell penceresi açılır — orada yapılanları izle

### Setup ne yapar (30-40 dakika)

1. ✅ Python 3.12 yükler (yoksa winget ile)
2. ✅ `.venv` sanal ortamı oluşturur
3. ✅ `requirements.txt`'teki tüm paketleri yükler
4. ✅ CUDA cuBLAS + cuDNN yükler (RTX 5090 için)
5. ✅ Whisper modelleri indirir (small ~500MB + large-v3 ~1.5GB)
6. ✅ Klasör yapısını oluşturur (local_db, auto_backups, vb.)
7. ✅ HTTPS sertifikası oluşturur (yoksa)
8. ⚠ Ollama yüklü mü kontrol eder (yoksa manuel yükle linki verir)
9. ✅ Windows Türkçe TTS yükler (Tolga/Sedef sesleri)
10. ✅ `config.env`'i RTX 5090 profili ile yerleştirir

### Hata olursa

PowerShell penceresinde **kırmızı [HATA]** satırları varsa:
- Ekran görüntüsü al
- Setup'u tekrar başlat (kaldığı yerden devam etmeye çalışır)
- Hâlâ olmazsa Claude'a göster

---

## ADIM 3 — Windows'u yeniden başlat

Türkçe TTS seslerinin aktif olması için Windows yeniden başlatılmalı.

**Başlat → Güç → Yeniden Başlat**

---

## ADIM 4 — İlk test

### NAS bağlantısı (varsa)

`\\asustor\Voluson` paylaşımına eski PC'den nasıl bağlanıyorsan aynı yöntemle bağlan.

NAS gerek yoksa veya farklı yolu varsa `config.env` içinde `YAZKLINIK_NAS_ROOT=` satırını güncelle:

```
YAZKLINIK_NAS_ROOT=D:\Voluson_local
```

### Sunucuyu başlat

`D:\YazKlinik_Final_D300\D300_BASLAT.bat`'a **çift tıkla**.

Beklenen çıktı:
```
[+] config.env okuniyor... OK
[+] Hazir venv: D:\YazKlinik_Final_D300\.venv
[+] Whisper mikroservisi (port 9000)... Whisper service baslatildi
Server BASLIYOR
Adres: https://127.0.0.1:5443
[BASARI] Server hazir! WebShell aciliyor...
```

Tarayıcı otomatik açılır → **doktor / 1234** ile giriş yap.

### Alex test

1. **Ses ve Alex** sayfasına git
2. **Alex'i başlat** butonuna tıkla
3. Sağ-alt köşede **🔊 Sesi aç (Emel)** butonu çıkarsa **tıkla**
4. "Merhaba" de → 1 sn bekle → Emel sesle cevap gelmeli (1 saniyenin altında!)

RTX 5090'da:
- Whisper STT: ~0.3 sn
- Edge TTS: ~0.5 sn
- Toplam (konuş → cevap): **~1 sn**

---

## ADIM 5 — Claude Code'u aç

Yeni PC'de Claude Code başlattığında, ilk komutta şunu yaz:

```
D:\YazKlinik_Final_D300\CLAUDE_HANDOFF.md dosyasini oku ve buradan devam et
```

Claude bu dosyayı okuyacak, projeyi anlayacak, kaldığı yerden devam edebilecek.

---

## SIK SORULAR

### "Whisper large-v3 model çok yer kaplıyor"

`config.env`'de `YAZKLINIK_WHISPER_MODEL=small` yapabilirsin. RTX 5090'da small bile çok hızlı.

### "Ollama da kuracak mıyım?"

Opsiyonel. LLM (akıllı cevap, GPT alternatifi) için. Cloud (OpenAI) zaten kullanılıyor — Ollama olmasa da Alex çalışır.

Kurarsan: https://ollama.com/download/windows → yükle → `ollama pull llama3.1:8b` veya `ollama pull qwen2.5:14b`

### "NAS bağlantısı yok / farklı"

`config.env` içinde `YAZKLINIK_NAS_ROOT=` boş veya farklı yola yönlendirebilirsin. Sistem NAS olmadan da çalışır (hasta klasörleri sadece görünmez).

### "Eski PC'deki veritabanını taşımak istiyorum"

`local_db\yazklinik_v68.sqlite3` dosyasını kopyaladıysan zaten var. Tüm hasta kayıtları, randevular, notlar geldi.

### "Mevcut PC'yi de yedek olarak tutmak istiyorum"

Önemli not — **her iki PC'yi AYNI ANDA çalıştırma** çünkü:
- DB'ler bağımsız oluyor (lokal sqlite)
- NAS'a iki PC aynı anda yazarsa karışıklık olur

Birini "üretim" diğerini "yedek/test" olarak tut, gerekirse manuel DB sync yap.

---

## DESTEK

Hata olursa Claude'a göster:
- `D300_server.log` (son 50 satır)
- `D300_server_HATA.log` (son 30 satır)
- `D300_whisper_service.log` (son 30 satır)
- Ekran görüntüsü

İyi taşımalar.
