# XTTS Voice Cloning - Hakan Sesi (Stub)

## Amac

Doktorun kendi sesi ile hastalara WhatsApp sesli notu gonderme:
- "Sayin Ayse Hanim, kontrol sonuclariniz iyi. Lutfen onumuzdeki hafta gelin."
- "Beta-HCG sonucu pozitif, geldiginizde detaylica anlatacagim."

## Teknoloji

- **Coqui XTTS v2** (acik kaynak, ticari kullanim icin lisans gerek)
- **F5-TTS** (yeni model, daha dogal Turkce)
- **Bark** (Suno - mood + tone)

## Kurulum (henuz yapilmadi)

```bash
pip install TTS  # Coqui XTTS
# veya
pip install f5-tts
```

## Ornek Cagiri (placeholder)

```python
from TTS.api import TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
tts.tts_to_file(
    text="Sayin Ayse Hanim, kontrol sonuclariniz iyi gozukuyor.",
    speaker_wav="hakan_sample.wav",  # 6-10 saniye doktor ornegi
    language="tr",
    file_path="output.wav"
)
```

## Gizlilik

- KVKK: hastalara "yapay zeka sesi" uyarisi gosterilir
- WhatsApp template: "Sn ... , bu sesli mesaj YapayZeka ses sentezi ile uretildi"
- Voice clone modeli sadece D700 makinada calisir, NAS'ta sifreli durur
- Hastane disinda baska makine icin lisans + onay sart

## Production yol haritasi

1. Hakan'dan 30 saniye temiz sesli ornek al (gurultusuz)
2. F5-TTS / XTTS modeli ile fine-tune (opsiyonel)
3. `yazklinik_voice_clone_agent.py` yaz: text -> wav uretici
4. WhatsApp helper'a sesli not gonderme ekle
5. Hasta consent checkbox: "Sesli mesajlari sentez ile alabilirim"
6. Audit log: her sesli mesaj icin uretim + gonderim ts kaydet

## Status

**STUB - henuz kurulu degil.** Onay alindiginda 1-2 saat ile aktif edilebilir.

