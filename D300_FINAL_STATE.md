# YazKlinik D300 — Final Sürüm Durumu (16 Mayıs 2026)

> RTX 5090 PC için tam optimize edilmiş profesyonel durum.
> Önceki: `CLAUDE_HANDOFF.md`. Bu dosya **şimdiki final yapılandırma**yı özetler.

## Kullanıcı

**Op. Dr. Hakan Yaz** — Kadın Hastalıkları ve Doğum (OB-GYN) uzmanı. Tek doktorlu kişisel klinik.

## Donanım profili

- **GPU:** NVIDIA RTX 5090 (32 GB VRAM, Blackwell sm_120)
- **RAM:** 192 GB DDR5
- **Disk:** D:\ 1.9 TB (boş ~1.1 TB)
- **Driver:** NVIDIA 576.88, CUDA 12.8

## Tek tık başlatma

```
D:\YazKlinik_Final_D300\D300_BASLAT.bat
```

Tek tıkla başlatılan **5 process** (hepsi HIGH priority):
1. **Whisper microservice** (port 9000) — large-v3-turbo CUDA fp16
2. **XTTS-v2 microservice** (port 9002) — Emel + Ahmet dual voice
3. **Piper microservice** (port 9001) — yedek lokal TTS
4. **Health Monitor** — her 30 saniyede servis check + auto-restart
5. **Web server** (port 5443) — Flask + Waitress 64 thread
   + **WebShell** Chromium app-mode

URL: `https://127.0.0.1:5443` — Giriş: `doktor / 1234`

## Aktif AI Pipeline (Siri-mode akıcı muhabbet)

```
Sen konuş → VAD 1.2sn sessizlik bekle (cümle bitişi)
   ↓
Whisper turbo STT (~135 ms / 3sn audio) — RTX 5090
   ↓
Ollama gpt-oss:20b LLM streaming (~327 ms / 40 token, ilk token <100ms)
   ↓ cümle bittiğinde
XTTS-v2 voice clone (~1.2 sn / cümle, Emel veya Ahmet) — RTX 5090
   ↓
Browser audio queue → otomatik akıcı çalar
   ↓ Alex konuşurken
**Barge-in:** kırmızı "Alex'i kes" butonu + yüksek sesle "DUR" → anında susar
   ↓ Audio bitince
Mic 100ms sonra otomatik açılır (continuous loop)
```

## Optimizasyon profili (D300_RTX5090_OPTIMAL_20260515)

### Ollama (LLM)
- `OLLAMA_FLASH_ATTENTION=1` — RTX 5090 flash attention (~30% hız)
- `OLLAMA_MAX_LOADED_MODELS=3` — 3 model paralel VRAM'da
- `OLLAMA_NUM_PARALLEL=4` — aynı modele 4 paralel istek
- `OLLAMA_KEEP_ALIVE=8h` — sürekli VRAM'da hazır
- `OLLAMA_KV_CACHE_TYPE=q8_0` — KV cache quantize, 2x context
- `OLLAMA_NUM_THREAD=16`

### Task model atamaları (`/yz-gorev-modelleri`)
| Görev | Model | VRAM | Niçin |
|---|---|---|---|
| **Telefon/Sohbet (Alex)** | **gpt-oss:20b** | 14 GB | MoE 116B, hızlı + akıllı |
| Klinik karar | qwen2.5:32b | 20 GB | En akıllı Türkçe |
| Reçete | qwen2.5:32b | 20 GB | Detay için kalite |
| Vision (USG/DICOM) | qwen3-vl:30b | 19.5 GB | Yeni nesil vision |
| Özet/Rapor | gpt-oss:20b | 14 GB | MoE hızlı |
| Hızlı komut | llama3.1:8b | 5 GB | Sub-saniye |
| Genel asistan | gpt-oss:20b | 14 GB | Dengeli |

### TTS (`/ses-profilleri`)
- **Emel** (Edge TTS Emel referansı, XTTS-v2 clone) — varsayılan kadın sesi
- **Ahmet** (Edge TTS Ahmet referansı, XTTS-v2 clone) — erkek sesi
- Kullanıcının `/ses-profilleri` sayfasında seçtiği profil **DB'den otomatik okunur**

### Whisper STT
- Model: **large-v3-turbo** (lokal indirilmiş, `D:\YazKlinik_Final_D300\models\whisper\large-v3-turbo`)
- Device: cuda, compute: float16
- Iç Silero VAD: 500ms silence, 400ms pad, threshold 0.4
- HF_HUB_OFFLINE=1 (model cache'den)

### System & Cache
- Waitress: **64 thread** (eski 32)
- Media RAM cache: **128 GB** (eski 48 GB)
- Program cache: **16 GB** (eski 4 GB)
- SQLite: 256 MB cache, **2 GB mmap**, 8 KB page, WAL + NORMAL sync
- Process priority: **HIGH** (tüm Python servisleri)

## Akıcı muhabbet özellikleri (tamamlandı)

- **Streaming endpoint** `/api/phone/voice-turn-text` — text → SSE stream
- **Per-sentence parallel TTS** (thread'ler aynı anda XTTS yapar)
- **Sentence grouping** (ilk cümle anında, sonraki kısa cümleler 60+ char grupla)
- **VAD sabırlı** 1.2 sn sessizlik (doğal duraksamada kesilmez)
- **Barge-in** otomatik (RMS > 0.05) + manuel "Alex'i kes" kırmızı buton
- **Continuous loop** cevap biter → 100ms sonra mic açılır
- **Echo cancellation** strict (Alex'in sesi mic'e dönmez)
- **Cache no-store** HTML response (browser daima fresh sayfa)
- **TTS text normalize** ("Op. Dr." → "Operatör Doktor", "HAKAN YAZ" → "Hakan Yaz")
- **System prompt geniş**: klinik + genel bilgi + kısaltma yasağı

## Servis portları & sağlık

| Port | Servis | Health URL | Kontrol |
|---|---|---|---|
| 5443 | Web (HTTPS) | `https://127.0.0.1:5443/giris` | `curl -k …` 200/302 |
| 9000 | Whisper | `http://127.0.0.1:9000/health` | JSON `{ok:true}` |
| 9001 | Piper | `http://127.0.0.1:9001/health` | JSON `{ok:true}` |
| 9002 | XTTS | `http://127.0.0.1:9002/health` | JSON `{ok:true, voices:[emel,ahmet]}` |
| 11434 | Ollama | `http://127.0.0.1:11434/api/version` | JSON `{version:…}` |

Health Monitor (`D300_HEALTH_MONITOR.py`) bunları her 30sn check eder, düşen servisi auto-restart.

## Benchmark sonuçları (16 May 2026)

| Test | Süre | Hardware |
|---|---|---|
| Whisper STT (3sn audio) | **135 ms** (RTF 0.045) | RTX 5090 |
| XTTS Emel (4-5sn audio) | **1.32 sn** | RTX 5090 |
| XTTS Ahmet (3-4sn audio) | **1.18 sn** | RTX 5090 |
| Ollama gpt-oss:20b (40 token) | **327 ms** | RTX 5090 |
| VRAM kullanım | 14.5 / 32 GB | %45 doluluk |
| **End-to-end (kullanıcı sustu → ses başlar)** | **~700-1000 ms** | Siri Voice Mode hızı |

## Dizinler

```
D:\YazKlinik_Final_D300\
├── yazklinik_web.py              # Ana Flask app (7.3 MB)
├── yazklinik_v68.py              # Legacy monolit (DOKUNMA)
├── yazklinik_whisper_service.py  # Port 9000
├── yazklinik_xtts_service.py     # Port 9002
├── yazklinik_piper_service.py    # Port 9001
├── D300_HEALTH_MONITOR.py        # Auto-restart watchdog
├── D300_BASLAT.bat               # Tek tık başlatıcı (HIGH priority)
├── config.env                    # RTX 5090 profili (128 GB cache, vb.)
├── models/
│   ├── whisper/large-v3-turbo/   # Local Whisper model
│   ├── xtts/emel_reference.wav   # Emel voice clone reference
│   ├── xtts/ahmet_reference.wav  # Ahmet voice clone reference
│   ├── piper/tr_TR-dfki-medium.* # Piper yedek
│   └── ffmpeg/extracted/.../bin/ # FFmpeg shared DLLs (torchcodec)
├── certs/                        # HTTPS sertifika
├── local_db/yazklinik_v68.sqlite3 # 18.89 MB, 92 hasta, 78 tablo
└── auto_backups/                 # 24sn DB backup
```

## Kritik kurallar (hâlâ geçerli)

1. `yazklinik_v68.py` (48 MB legacy) — **DOKUNMA**
2. Hasta verisi **SİLME** — `archived_at` set et
3. NAS klasör altındaki dosyaları **silme**
4. PowerShell `Get-Content -Raw` + `Set-Content -Encoding UTF8` **YASAK** — TR mojibake
5. `git reset --hard`, `git checkout --` **YAPMA**
6. Otomatik formatlama (black, autopep8) **YAPMA** — source'ta mojibake var
7. Python f-string içinde JS `\n` yerine **`\\n`** kullan (string literal kırılmaması için)

## Pending / opsiyonel iyileştirmeler

- [ ] Voice profile UI sayfada hızlı seçici (zaten `/ses-profilleri` var, 1-tık değil)
- [ ] YZ Telesekreter (UCM6300A Asterisk AMI) — kullanıcı IP/AMI bilgisi vermedi
- [ ] Vision model warmup (Ollama'ya `qwen3-vl:30b` ön-yükle)
- [ ] Log rotation (logrotate veya tarih bazlı dosya)
- [ ] DB auto-backup verify (24sn backup gerçekten çalışıyor mu test)

## Hızlı problem giderme

| Sorun | Çözüm |
|---|---|
| Servis cevap vermiyor | Health Monitor 30sn içinde auto-restart eder. Manuel: `D300_BASLAT.bat` |
| Ses gelmiyor | Tarayıcı **Ctrl+Shift+R** + sayfaya bir kez tıkla (autoplay unlock) |
| Yanlış anlama | Mikrofon level kontrol (Windows Ses Ayarları) |
| Barge-in tetiklenmiyor | F12 → Console → `window._ykBargeThreshold = 0.03` |
| Alex çift cevap | Bir önceki turn iptal edilmemiş → tarayıcı yenile |

---

**Versiyon:** D300_RTX5090_OPTIMAL_20260515 + 20260516 final polish
**Stack:** Python 3.12 + PyTorch nightly cu128 + Coqui-TTS + faster-whisper + Ollama + Flask
