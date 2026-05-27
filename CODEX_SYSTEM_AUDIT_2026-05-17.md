# CODEX SYSTEM AUDIT - 2026-05-17

## Yapilan Duzeltmeler

- D700 servis runner'a tekil calisma kilidi eklendi; ayni SIP/ASR/TTS/web servisinin cift baslamasi engellendi.
- D500_BASLAT icin baslatma kilidi eklendi; art arda cift tiklamada birden fazla launcher akisi acilmayacak.
- Health Monitor restartlari D500_SERVICE_RUNNER uzerinden calisacak sekilde duzeltildi.
- Alex web ve SIP ses profili robotik/aksanli Piper/Ahmet yerine dogal Turkce Emel profile cekildi.
- Kayitli telefon/Alex metinleri aktif DB ayarlarinda temiz Turkce olarak guncellendi.
- Alex kisa sohbetlerde artik zorla `llama3.1:8b` kullanmiyor; secili `qwen2.5:32b` modeliyle cevap veriyor.
- Alex ses kesilmesi icin TTS watchdog 22 saniyeye uzatildi, otomatik barge-in esigi daha guvenli hale getirildi.
- SIP TTS metin normalizasyonu `Dr`, `Op. Dr.`, `Uzm. Dr.`, `Prof. Dr.` kisaltmalarini telefonda `Doktor` seklinde okutacak sekilde genisletildi.
- Ajanlar sayfasi koyu/okunmaz kartlardan acik medikal tema kartlara tasindi.
- Service worker cache listesi var olmayan CSS yerine gercek manifest/tema/icon dosyalarina cekildi.
- Compliance ajani auto_backups klasorunu okuyacak sekilde duzeltildi; bugunku yedegi goruyor.
- Alex web TTS icin Piper/DFKI artik serbest profil metninde bile Emel Neural'a yonleniyor; Piper sadece `YAZKLINIK_ALEX_ALLOW_PIPER_TTS=1` ile acilabilir.
- Alex web/telefon TTS akisi Edge Emel/Ahmet oncelikli hale getirildi; XTTS artik varsayilan degil, sadece `YAZKLINIK_ALEX_ALLOW_XTTS_TTS=1` veya tarayicida `ykAlexAllowXttsTts=1` ile kullanilir.
- Alex otomatik barge-in yerel depolama bayragiyla kendiliginden acilmiyor; yankiyla kendi sesini kesmemesi icin varsayilan kapali, manuel `Alex'i kes` butonu korunuyor.
- SIP TTS normalizasyonundaki `Doktor Doktor` tekrari temizlendi (`Dr. Hakan YAZ` -> `Doktor`, `Op.Dr. Hakan Yaz` -> `Operator Doktor`).
- Alex tarayici mikrofon VAD ayarlari daha sabirli hale getirildi: kayit 9 sn, aktif komut 8 sn, wake kaydi 5.5 sn, sessizlik kesme 1.5 sn.
- Alex bozuk/garland STT duydugunda 100 ms icinde tekrar tekrar donguye girmesi engellendi; bos/bozuk duyma artik kademeli geri bekleme yapiyor.
- Alex voice-turn icin debug ses kaydi eklendi: sadece `no-speech`, `stt-error`, `garland-skip` durumlari `runtime_state/alex_voice_debug` altinda saklaniyor.
- Alex sesli LLM cevabina Cyrillic/Rusca veya tool-artigi parcalar sizarsa TTS'e gitmeden ve hafizaya yazilmadan temizleniyor.
- Codex testinden kalan bozuk Rusca Alex test hafizasi `alex_memory`, `alex_training_data`, `alex_facts`, `alex_learned_summaries` tablolarindan temizlendi.
- Claude/Git Bash tarafindan acilan `nohup python.exe yazklinik_web.py` sureci 5443 portunu ele gecirdigi icin kapatildi; port tekrar D500_SERVICE_RUNNER altindaki yonetimli web surecine verildi.
- Health Monitor artik 5443'u sadece HTTP cevap olarak degil, surec sahibi olarak da denetliyor; `D500_SERVICE_RUNNER.py` disinda calisan direkt `yazklinik_web.py` surecini kapatip D700 yonetimli web'i yeniden baslatir.
- SIP Alex'e uzun sessizlik kapanis kuralÄ± eklendi: 20 saniye ses/STT gelmezse "Gorusmeyi kapatiyorum, iyi gunler/iyi aksamlar" diyerek SIP BYE ile telefonu kapatir.

## Canli Dogrulama

- Portlar acik: 5443 web, 9000 Whisper, 9001 Piper, 9002 XTTS, 9019 SIP Alex.
- `/api/agents`: 42 modul aktif, import hatasi yok.
- `/api/agents/compliance/run`: grade B, pct 79.6, kritik eksik 0.
- `/api/sip-alex/status`: registered true, Edge voice tr-TR-EmelNeural.
- `/api/phone/voice-turn-text`: SSE chunk + audio uretti; son canli testte engine `edge_tts:tr-TR-EmelNeural`, model `qwen2.5:32b`.
- 3 kez arka arkaya `/api/phone/voice-turn-text` canli test edildi; hata 0, ses motoru hep `edge_tts:tr-TR-EmelNeural`.
- SIP kontrol servisi `9019/status`: registered true, extension 19, Edge Emel, legacy fallback false.
- SIP `--tts-test`: Edge Emel WAV uretti, `runtime_state\sip_test_current.wav`, 8.21 sn, fallback false.
- `/api/phone/voice-turn`: TTS ile uretilen Turkce WAV yeniden STT+LLM+TTS zincirinden gecirildi; STT 175 ms, model `qwen2.5:32b`, Cyrillic/Rusca cikti yok.
- `/api/phone/voice-turn`: sessiz WAV testi `no-speech` dondurdu ve debug kaydi `runtime_state\alex_voice_debug` altina yazildi.
- `CODEX_QUICK_CHECK.py`: `CODEX_D500_QUICK_CHECK_OK`.
- 5443 port sahibi dogrulandi: `D500_SERVICE_RUNNER.py -> yazklinik_web.py`, direkt/Claude web sureci sayisi 0.
- `/api/phone/tts`: engine `edge_tts:tr-TR-EmelNeural`, content-type `audio/mpeg`.
- `/api/phone/voice-turn-text`: SSE chunk + audio uretti, engine `edge_tts:tr-TR-EmelNeural`.
- `/api/phone/voice-turn`: Edge Emel TTS ile uretilen MP3 tekrar STT+LLM+TTS zincirinden gecirildi; STT 441 ms, engine `edge_tts:tr-TR-EmelNeural`, Cyrillic/Rusca cikti yok.
- Canli Alex testlerinin yazdigi gecici hafiza kayitlari temizlendi (`alex_memory` ids 519-522).
- SIP status yeni kuralÄ± gosteriyor: `silence_hangup_seconds=20.0`, REGISTER OK 200.

## Kalan Bilinen Riskler

- Compliance B seviyesinde; A icin Tailscale/Caddy TLS kaniti, KVKK talep UI, egitim kaydi ve disk sifreleme kaniti gerekir.
- `yazklinik_web.py` icinde eski mojibake yorum/metin bloklari halen var; aktif DB metinleri temizlendi, ama kaynak genel mojibake temizligi ayri kontrollu is olarak kalmali.

