# YazKlinik D700 â€” RTX 5090 PC'ye TaÅŸÄ±ma Rehberi

> **5 adÄ±m** ile yeni PC'de Ã§alÄ±ÅŸÄ±r hale gelir. SÃ¼re: ~30-45 dakika.

## Ã–ZET

Yeni PC'de **sÄ±fÄ±r kurulum** yapacaksÄ±n. Åu sÄ±ra ile gideceksin:

1. **D klasÃ¶rÃ¼nÃ¼ kopyala** (1 dakika)
2. **SETUP_RTX5090.bat Ã§ift tÄ±kla** (30-40 dakika otomatik kurulum)
3. **Windows'u yeniden baÅŸlat** (TR TTS aktif olsun)
4. **D500_BASLAT.bat Ã§ift tÄ±kla** (test)
5. **Claude Code'u aÃ§ â†’ "CLAUDE_HANDOFF.md oku" de** (yeni sohbet baÅŸlayacak)

---

## ADIM 1 â€” DosyalarÄ± taÅŸÄ±

### Bu PC'den (mevcut)

**`D:\YazKlinik_Final_D500\`** klasÃ¶rÃ¼nÃ¼n TAMAMINI yeni PC'ye kopyala.

Kopyalama yollarÄ± (hangisini istersen):

- **USB harici disk** (en hÄ±zlÄ±, ~5-10 GB) â€” direkt kopyala-yapÄ±ÅŸtÄ±r
- **AÄŸ paylaÅŸÄ±mÄ±** â€” eski PC'de `D:\YazKlinik_Final_D500\` paylaÅŸ, yeni PC'den eÅŸ
- **OneDrive / Google Drive** â€” yÃ¼kle, indir
- **WinSCP / robocopy** â€” yapÄ±ÅŸtÄ±rma sÄ±rasÄ±nda bozulma yapmaz

### KOPYALAMADAN Ã–NCE bu klasÃ¶rleri **TEMÄ°ZLE** (yer kazanma â€” boyutu kÃ¼Ã§Ã¼ltÃ¼r)

```
D:\YazKlinik_Final_D500\.venv\           â† yeni PC'de yeniden oluÅŸacak (SETUP yapar)
D:\YazKlinik_Final_D500\temp\            â† geÃ§ici dosyalar
D:\YazKlinik_Final_D500\dicom_cache\     â† cache, gerek yok (NAS'tan yeniden gelir)
D:\YazKlinik_Final_D500\D500_server.log
D:\YazKlinik_Final_D500\D500_server_HATA.log
D:\YazKlinik_Final_D500\D500_whisper_service.log
```

### KOPYALANMASI ÅART olan dosyalar

```
D:\YazKlinik_Final_D500\
â”œâ”€â”€ yazklinik_web.py                    â† ana uygulama
â”œâ”€â”€ yazklinik_whisper_service.py
â”œâ”€â”€ yazklinik_v68.py                    â† dokunulmaz eski sÃ¼rÃ¼m
â”œâ”€â”€ yazklinik_feature_sync.py
â”œâ”€â”€ yazklinik_common.py
â”œâ”€â”€ *.py (kalan modÃ¼ller)
â”œâ”€â”€ *.bat (D500_BASLAT, START_WHISPER, SETUP_RTX5090)
â”œâ”€â”€ *.ps1 (SETUP_RTX5090, INSTALL_TURKISH_TTS)
â”œâ”€â”€ requirements.txt
â”œâ”€â”€ config.env                          â† AYAR DOSYASI (Ã¶nemli)
â”œâ”€â”€ config.rtx5090.env                  â† RTX profili ÅŸablon
â”œâ”€â”€ CLAUDE.md
â”œâ”€â”€ CLAUDE_HANDOFF.md                   â† Yeni Claude iÃ§in
â”œâ”€â”€ TASIMA_REHBERI.md                   â† BU DOSYA
â”œâ”€â”€ certs\                              â† SSL sertifikasÄ±
â”œâ”€â”€ local_db\yazklinik_v68.sqlite3      â† VERÄ°TABANI (kritik!)
â”œâ”€â”€ auto_backups\                       â† Ã¶nceki DB yedekleri
â””â”€â”€ static\, templates\, vb. klasÃ¶rler
```

### Ã‡ift kontrol et (yeni PC'de kopyalama sonrasÄ±)

```powershell
# Yeni PC'de PowerShell'de
cd D:\YazKlinik_Final_D500
Get-ChildItem yazklinik_web.py, requirements.txt, SETUP_RTX5090.bat, config.env, local_db
```

Hepsi gÃ¶zÃ¼kmeli. GÃ¶zÃ¼kmÃ¼yorsa kopyalama eksik.

---

## ADIM 2 â€” Setup'u Ã§alÄ±ÅŸtÄ±r

### HazÄ±rlÄ±k

Yeni PC'de **internet baÄŸlantÄ±sÄ±** olmalÄ± (paketler, Whisper modelleri indirilecek).

NVIDIA driver'Ä±n son sÃ¼rÃ¼m olduÄŸundan emin ol:
- https://www.nvidia.com/Download/index.aspx
- RTX 5090 iÃ§in en gÃ¼ncel driver yÃ¼klÃ¼ olsun

### Setup baÅŸlat

1. `D:\YazKlinik_Final_D500\SETUP_RTX5090.bat`'a **Ã§ift tÄ±kla**
2. AÃ§Ä±lan pencerede bir tuÅŸa bas (Enter)
3. UAC penceresi aÃ§Ä±lÄ±r â†’ **Evet** tÄ±kla
4. YÃ¶netici PowerShell penceresi aÃ§Ä±lÄ±r â€” orada yapÄ±lanlarÄ± izle

### Setup ne yapar (30-40 dakika)

1. âœ… Python 3.12 yÃ¼kler (yoksa winget ile)
2. âœ… `.venv` sanal ortamÄ± oluÅŸturur
3. âœ… `requirements.txt`'teki tÃ¼m paketleri yÃ¼kler
4. âœ… CUDA cuBLAS + cuDNN yÃ¼kler (RTX 5090 iÃ§in)
5. âœ… Whisper modelleri indirir (small ~500MB + large-v3 ~1.5GB)
6. âœ… KlasÃ¶r yapÄ±sÄ±nÄ± oluÅŸturur (local_db, auto_backups, vb.)
7. âœ… HTTPS sertifikasÄ± oluÅŸturur (yoksa)
8. âš  Ollama yÃ¼klÃ¼ mÃ¼ kontrol eder (yoksa manuel yÃ¼kle linki verir)
9. âœ… Windows TÃ¼rkÃ§e TTS yÃ¼kler (Tolga/Sedef sesleri)
10. âœ… `config.env`'i RTX 5090 profili ile yerleÅŸtirir

### Hata olursa

PowerShell penceresinde **kÄ±rmÄ±zÄ± [HATA]** satÄ±rlarÄ± varsa:
- Ekran gÃ¶rÃ¼ntÃ¼sÃ¼ al
- Setup'u tekrar baÅŸlat (kaldÄ±ÄŸÄ± yerden devam etmeye Ã§alÄ±ÅŸÄ±r)
- HÃ¢lÃ¢ olmazsa Claude'a gÃ¶ster

---

## ADIM 3 â€” Windows'u yeniden baÅŸlat

TÃ¼rkÃ§e TTS seslerinin aktif olmasÄ± iÃ§in Windows yeniden baÅŸlatÄ±lmalÄ±.

**BaÅŸlat â†’ GÃ¼Ã§ â†’ Yeniden BaÅŸlat**

---

## ADIM 4 â€” Ä°lk test

### NAS baÄŸlantÄ±sÄ± (varsa)

`\\asustor\Voluson` paylaÅŸÄ±mÄ±na eski PC'den nasÄ±l baÄŸlanÄ±yorsan aynÄ± yÃ¶ntemle baÄŸlan.

NAS gerek yoksa veya farklÄ± yolu varsa `config.env` iÃ§inde `YAZKLINIK_NAS_ROOT=` satÄ±rÄ±nÄ± gÃ¼ncelle:

```
YAZKLINIK_NAS_ROOT=D:\Voluson_local
```

### Sunucuyu baÅŸlat

`D:\YazKlinik_Final_D500\D500_BASLAT.bat`'a **Ã§ift tÄ±kla**.

Beklenen Ã§Ä±ktÄ±:
```
[+] config.env okuniyor... OK
[+] Hazir venv: D:\YazKlinik_Final_D500\.venv
[+] Whisper mikroservisi (port 9000)... Whisper service baslatildi
Server BASLIYOR
Adres: https://127.0.0.1:5443
[BASARI] Server hazir! WebShell aciliyor...
```

TarayÄ±cÄ± otomatik aÃ§Ä±lÄ±r â†’ **doktor / 1234** ile giriÅŸ yap.

### Alex test

1. **Ses ve Alex** sayfasÄ±na git
2. **Alex'i baÅŸlat** butonuna tÄ±kla
3. SaÄŸ-alt kÃ¶ÅŸede **ğŸ”Š Sesi aÃ§ (Emel)** butonu Ã§Ä±karsa **tÄ±kla**
4. "Merhaba" de â†’ 1 sn bekle â†’ Emel sesle cevap gelmeli (1 saniyenin altÄ±nda!)

RTX 5090'da:
- Whisper STT: ~0.3 sn
- Edge TTS: ~0.5 sn
- Toplam (konuÅŸ â†’ cevap): **~1 sn**

---

## ADIM 5 â€” Claude Code'u aÃ§

Yeni PC'de Claude Code baÅŸlattÄ±ÄŸÄ±nda, ilk komutta ÅŸunu yaz:

```
D:\YazKlinik_Final_D500\CLAUDE_HANDOFF.md dosyasini oku ve buradan devam et
```

Claude bu dosyayÄ± okuyacak, projeyi anlayacak, kaldÄ±ÄŸÄ± yerden devam edebilecek.

---

## SIK SORULAR

### "Whisper large-v3 model Ã§ok yer kaplÄ±yor"

`config.env`'de `YAZKLINIK_WHISPER_MODEL=small` yapabilirsin. RTX 5090'da small bile Ã§ok hÄ±zlÄ±.

### "Ollama da kuracak mÄ±yÄ±m?"

Opsiyonel. LLM (akÄ±llÄ± cevap, GPT alternatifi) iÃ§in. Cloud (OpenAI) zaten kullanÄ±lÄ±yor â€” Ollama olmasa da Alex Ã§alÄ±ÅŸÄ±r.

Kurarsan: https://ollama.com/download/windows â†’ yÃ¼kle â†’ `ollama pull llama3.1:8b` veya `ollama pull qwen2.5:14b`

### "NAS baÄŸlantÄ±sÄ± yok / farklÄ±"

`config.env` iÃ§inde `YAZKLINIK_NAS_ROOT=` boÅŸ veya farklÄ± yola yÃ¶nlendirebilirsin. Sistem NAS olmadan da Ã§alÄ±ÅŸÄ±r (hasta klasÃ¶rleri sadece gÃ¶rÃ¼nmez).

### "Eski PC'deki veritabanÄ±nÄ± taÅŸÄ±mak istiyorum"

`local_db\yazklinik_v68.sqlite3` dosyasÄ±nÄ± kopyaladÄ±ysan zaten var. TÃ¼m hasta kayÄ±tlarÄ±, randevular, notlar geldi.

### "Mevcut PC'yi de yedek olarak tutmak istiyorum"

Ã–nemli not â€” **her iki PC'yi AYNI ANDA Ã§alÄ±ÅŸtÄ±rma** Ã§Ã¼nkÃ¼:
- DB'ler baÄŸÄ±msÄ±z oluyor (lokal sqlite)
- NAS'a iki PC aynÄ± anda yazarsa karÄ±ÅŸÄ±klÄ±k olur

Birini "Ã¼retim" diÄŸerini "yedek/test" olarak tut, gerekirse manuel DB sync yap.

---

## DESTEK

Hata olursa Claude'a gÃ¶ster:
- `D500_server.log` (son 50 satÄ±r)
- `D500_server_HATA.log` (son 30 satÄ±r)
- `D500_whisper_service.log` (son 30 satÄ±r)
- Ekran gÃ¶rÃ¼ntÃ¼sÃ¼

Ä°yi taÅŸÄ±malar.

