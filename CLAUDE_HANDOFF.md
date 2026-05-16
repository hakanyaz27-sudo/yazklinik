# YazKlinik D300 — Claude Code Hand-off Notu (RTX 5090 PC)

> Bu dosya, RTX 5090 PC'sinde yeni başlatılacak Claude Code oturumu için yazıldı.
> Önceki oturum 15 Mayıs 2026'da bu yazıldı — buradan kaldığı yerden devam et.

## Kullanıcı

**Op. Dr. Hakan YAZ** — Kadın Hastalıkları ve Doğum (OB-GYN) uzmanı. Tek doktorlu kişisel klinik. YazKlinik yapımcısı + kullanıcısı.

**Tarz:** Türkçe, kısa, doğrudan. "Yap" deyince kod + 1 test + 1 cümle teslim. v68'e dokunma kuralı.

## Sistem özeti

**Stack:** Python 3.12 + Flask + waitress + sqlite3 + Windows 11. Tek monolith `yazklinik_web.py` (~6.5 MB).

**Giriş noktası:** `D:\YazKlinik_Final_D300\D300_BASLAT.bat` (sunucu + Whisper microservice + WebShell tek tık)

**URL:** `https://127.0.0.1:5443` (HTTPS self-signed), kullanıcı `doktor / 1234`

## RTX 5090 PC'ye özel ayarlar (önemli!)

Bu PC önceki PC'den FARKLI. Optimum performans için `config.env` zaten **RTX 5090 profili** ile geldi:

```
YAZKLINIK_WHISPER_MODEL=large-v3
YAZKLINIK_WHISPER_DEVICE=cuda
YAZKLINIK_WHISPER_COMPUTE_TYPE=float16
YAZKLINIK_OLLAMA_NUM_GPU=99
YAZKLINIK_OLLAMA_CTX_LIMIT=16384
YAZKLINIK_OLLAMA_NUM_PARALLEL=4
```

**Beklenen performans (önceki PC'ye göre):**
| İşlem | Eski PC (CPU) | RTX 5090 |
|---|---|---|
| Whisper STT (3 sn ses) | 2-4 sn | **0.2-0.4 sn** |
| Konuş → Alex cevap | ~3 sn | **~0.7-1 sn** |
| Whisper model | small | **large-v3 (daha doğru)** |

## En önemli 5 dosya

1. `yazklinik_web.py` — ana Flask uygulaması (6.5 MB monolith, **v68'e dokunma**)
2. `yazklinik_whisper_service.py` — Whisper microservice (port 9000)
3. `D300_BASLAT.bat` — sunucu + servis + WebShell tek tık
4. `START_WHISPER_SERVICE.bat` — sadece Whisper service (debug için)
5. `config.env` — NAS, DB, port, GPU profili ayarları

## Son durum (15 Mayıs 2026 sonu itibarıyla)

### ✅ Çalışıyor
- **Alex sesli asistan** karşılıklı konuşma
  - VAD: konuşma başladıktan sonra **1 sn susunca otomatik kes** (8 sn beklemiyor)
  - Browser MediaRecorder VAD'li yol öncelikli (WebShell'de bile)
  - Edge TTS Emel sesi ile cevap (`tr-TR-EmelNeural`)
  - Karşılıklı backoff 200ms (alex aktif iken)
  - Wake word zorunlu değil (alexLoop açıkken her cümle komut sayılır)
  - Barge-in: Alex konuşurken kullanıcı konuşunca anında kesilir
- **Hasta listesi** — premium glassmorphism, status dots, mini stats, son geliş özeti, grid/liste toggle, list mode grid-template-areas fix, IntersectionObserver lazy fill
- **27 tema sistemi** (Midnight Pro dahil)
- **NVR kamera** — 20 kanal seçici + layout seçici (1/2/4/6/9/16) + tek-tık tam ekran + 1/2/5/10 sn auto-refresh
- **Sesli randevu** — "yarın saat 14 randevu ver" → form prefill (`_voice_parse_appointment_intent`)
- **Smart search** — TR normalize + fuzzy, input[list] ve data-yk-smart input'larda
- **Hasta son geliş batch endpoint** (`/api/hasta-son-gelis-batch`)

### ⚠ Önceki PC'de sorunlu, RTX 5090'da çözülmesi beklenen
- **Whisper hızı** — small/int8 CPU'da 2-4 sn alıyordu. CUDA fp16'da 0.3 sn olmalı.
- **Konuş→cevap genel akıcılık** — RTX ile Siri/Alexa kadar akıcı olmalı.
- **STT doğruluğu** — small'dan large-v3'e geçince Türkçe doğruluk %95+

### ❌ Pending (kullanıcı talepleri)
- **YZ Telesekreter** UCM6300A Asterisk AMI entegrasyonu — kullanıcı IP/AMI port/user/pass/recording path bilgisi vermedi henüz
- **Sesli randevu — "evet" onay sonrası otomatik kaydet** (form prefill var, evet onayı yok)
- **Windows TR TTS yüklü değildi (eski PC)** — RTX 5090'a `SETUP_RTX5090.ps1` zaten yüklüyor

## Önemli not — TTS pipeline'ları

Önceki oturumun en kritik bulgusu: **3 farklı TTS pipeline var** (`speak`, `window.ykSpeak`, `ykPhoneSpeak`). Her birinde "TR ses yoksa İngilizce ile okuma" engeli + `play-blocked` durumunda **otomatik "🔊 Sesi aç" butonu** var (sağ-alt köşede pulse eden kırmızı-turuncu).

**Browser TTS fallback'i:** Sadece Windows'ta TR ses (Tolga/Sedef) yüklüyse aktif. Aksi takdirde sessiz kalır. Bu sayede İngilizce sesle Türkçe okuma yapmaz. RTX 5090'da setup script TR TTS'i otomatik yükledi.

## "Yap" istek tipleri (kullanıcı tarzı)

Kullanıcı genelde tek cümle ile söyler. Örnek son istekler:
- "alex çok iyi çalıştır" → STT + TTS + akıcılık paketi
- "sistem çok yavaş hızlandır" → backdrop-filter kaldır, lazy fill, smart-search lite
- "nvr 20 kanaldan 4'lü izlemek istiyorum" → kanal/layout seçici
- "temaları geri getir" → dark mode toggle kaldır, mevcut 27 tema çalışsın
- "alex 8 sn beni bekliyor" → VAD + recording duration ayarı

**Çözüm akışı:** Sorun → kök neden tanı → 2-3 spot fix → syntax test → "şu butona bas, test et" → kullanıcı dön.

## Komutlar (RTX 5090 PC'de)

```powershell
# Hızlı test
D:\YazKlinik_Final_D300\D300_BASLAT.bat

# Sadece sunucu (servis ayrı)
$env:YAZKLINIK_WEB_PORT="5443"
& "D:\YazKlinik_Final_D300\.venv\Scripts\python.exe" "D:\YazKlinik_Final_D300\yazklinik_web.py"

# Whisper service tek başına
D:\YazKlinik_Final_D300\START_WHISPER_SERVICE.bat

# Syntax check
& "D:\YazKlinik_Final_D300\.venv\Scripts\python.exe" -c "import ast; ast.parse(open('D:\\YazKlinik_Final_D300\\yazklinik_web.py','r',encoding='utf-8').read()); print('OK')"

# Hızlı dogrulama
& "D:\YazKlinik_Final_D300\.venv\Scripts\python.exe" D:\YazKlinik_Final_D300\CODEX_QUICK_CHECK.py
```

## Önemli kurallar (önceki Claude'dan dersler)

1. **PowerShell `Get-Content -Raw` + `Set-Content -Encoding UTF8` ASLA KULLANMA** — Türkçe karakterleri double-mojibake yapar. Python ile dosya yaz (`io.open(..., encoding='utf-8', newline='')`).
2. **`v68.py` dosyasına dokunma** — kullanıcı bu kurala katı.
3. **Hasta verisi + NAS dosyası SİLME** — sadece veritabanı operasyonları yap, dosya silme yapma.
4. **Eski mojibake** — kodda Türkçe yorumlarda mojibake olabilir. Bunları geri çevirmeye CALMAYÇA AGRESİF olma — sadece UI'a çıkanları düzelt (HTML, label, h2, vb.).
5. **Patch küçük olsun** — büyük refactor yapma. Hedefli 1-3 spot fix + test → kullanıcıya teslim.
6. **Test komutu hep ver** — kullanıcı "tarayıcı kapat → Ctrl+F5 → test et" şeklinde test eder.

## Devam etmek için ilk adım

1. Bu dosyayı oku (zaten okuyorsun)
2. `CLAUDE_BASLA_BURADAN.md` varsa onu da oku (proje kuralları)
3. `AGENTS.md` + `D300_HANDOFF.md` varsa kontrol et
4. Kullanıcı ne istiyor → tek cümle ile söyleyecek
5. **RTX 5090 PC'de ilk test:** D300_BASLAT.bat çalıştır, Alex'i test et — beklenen 1 sn altı cevap

## İletişim örnekleri (kullanıcı ile)

**Kötü cevap:** "Şunu, bunu ve şunu yapacağım, önce A'yı sonra B'yi..."

**İyi cevap:** "Sebep: X kapalıydı. Düzelttim. Sen şimdi: D300_BASLAT.bat aç → Ctrl+F5 → Alex'e 'merhaba' de → cevap geldi mi söyle."

## Dosya yapısı (RTX 5090 PC'de beklenen)

```
D:\YazKlinik_Final_D300\
├── yazklinik_web.py           ← ana app (6.5 MB)
├── yazklinik_whisper_service.py ← Whisper microservice
├── yazklinik_v68.py            ← ESKİ - DOKUNMA
├── yazklinik_feature_sync.py   ← menü manifesti
├── yazklinik_common.py
├── D300_BASLAT.bat
├── START_WHISPER_SERVICE.bat
├── SETUP_RTX5090.bat / .ps1    ← İLK KURULUM
├── INSTALL_TURKISH_TTS.bat / .ps1 ← TR TTS yükleyici (setup içinde de var)
├── config.env                  ← RTX 5090 profili kopyalandı
├── config.rtx5090.env          ← Profil şablonu
├── requirements.txt
├── CLAUDE.md                   ← proje kuralları
├── CLAUDE_HANDOFF.md           ← BU DOSYA
├── CLAUDE_BASLA_BURADAN.md     ← varsa ilk oku
├── AGENTS.md
├── D300_HANDOFF.md
├── certs\
│   ├── yazklinik_https.crt
│   └── yazklinik_https.key
├── local_db\
│   └── yazklinik_v68.sqlite3   ← veritabanı (taşınmalı veya temiz başlar)
├── auto_backups\
├── data\
├── exports\
├── voice_records\
└── runtime_state\
```

## Son satır

Kullanıcı sade konuşur — "merhaba" derse sistem yanıt vermeli. "Yap" derse 5 dakikada teslim et. "Çalışmıyor" derse 1 cümlede tanı + spot fix. **Detaya boğma.**

İyi iş çıkar, sevgili Claude. Op. Dr. Hakan YAZ seni bekliyor.
