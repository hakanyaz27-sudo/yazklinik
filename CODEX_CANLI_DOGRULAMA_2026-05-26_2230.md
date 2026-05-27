# Codex Canli Dogrulama - 2026-05-26

Tarih: 2026-05-26 22:32:05 (Europe/Istanbul)
Klasor: D:\YazKlinik_Final_D700

## Sonuc Ozeti
- CODEX_QUICK_CHECK: CODEX_D700_QUICK_CHECK_OK
- Hata: 0
- Uyari: 0
- Route smoke: 18/18 OK

## Surec Tazeligi
- Web PID (5052): 47216
- ProcessStart: 2026-05-26 22:19:50
- yazklinik_web.py LastWriteTime: 2026-05-26 21:58:32
- Tazelik: Fresh=True (process start > file mtime)

## Port Durumu (listen)
- 5052 (web http): acik
- 5443 (web https): acik
- 8042 (Orthanc): acik
- 8188 (ComfyUI): acik
- 9000 (Whisper): acik
- 9001 (Piper): acik
- 9019 (SIP Alex): acik
- 11434 (Ollama): acik

## 90sn Soak Test (18x, 5sn aralik)
- http://127.0.0.1:5052/api/terminal/ping-fast -> OK 18 / Fail 0
- https://127.0.0.1:5443/api/terminal/ping-fast -> OK 18 / Fail 0
- http://127.0.0.1:9000/health -> OK 18 / Fail 0
- http://127.0.0.1:9001/health -> OK 18 / Fail 0
- http://127.0.0.1:9019/status -> OK 18 / Fail 0
- http://127.0.0.1:8188/system_stats -> OK 18 / Fail 0

## Not
Bu snapshot anlik stabilite kanitidir; web kod degisikligi sonrasi waitress hot-reload olmadigi icin restart + yeniden quick check zorunludur.
