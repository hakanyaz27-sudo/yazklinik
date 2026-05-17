# Alex Ses Kalitesi - Russian Aksanini Sokme (2026-05-17 Fix)

## Sorun

Kullanici raporu: "Alex turkcesi rus aksani hic guzel degil"

Tespit:
- `edge_tts` Python paketi **kurulu degildi**
- `piper` Python paketi **kurulu degildi**
- Default ses profili `tr_lokal_piper` (Piper DFKI - **robotik/aksanli**)
- Tum bu sebepler birlestiginde browser SpeechSynthesis fallback'i tetikleniyordu
- Windows'ta `Microsoft Tolga Desktop` sesi geri donuyordu (eski, **Russian-aksanli**)

## Cozum (Bu commit)

### 1. edge_tts kuruldu (v7.2.8)
```powershell
python -m pip install edge-tts
```
Bu paket Microsoft Edge Neural cloud seslerine FREE erisim verir.
En kaliteli Turkce TTS: `tr-TR-EmelNeural` (kadin) ve `tr-TR-AhmetNeural` (erkek).

### 2. Default ses profili degisti
`yazklinik_web.py`:
```python
# ESKI:
or "tr_lokal_piper"      # robotik/aksanli

# YENI:
or "tr_premium_kadin"    # Emel Neural - dogal Turkce
```

### 3. Legacy profile map guncellendi
"lokal/yerel/aksansiz/turkce net" -> art-k Emel Neural'a yonleniyor
(eski hali Piper'a gidiyordu).

### 4. Browser-side voice picker iyilestirildi
Eski: TR-lang ilk bulunan voice'u seciyordu (genelde Tolga = kotu)

Yeni: Voice puanlanir, en iyi secilir:
- `Online/Natural/Neural` keywords: +100 puan
- `emel`: +50, `ahmet`: +45
- `filiz`: +30
- `google`: +20
- `tolga`: **-50 puan** (eski/robotik, son tercih)

### 5. DB'de voice profile guncel
```sql
UPDATE app_settings SET value='tr_premium_kadin'
  WHERE key='ai_phone_voice_profile';
```

## Test

```python
import asyncio, edge_tts
async def main():
    com = edge_tts.Communicate(
        "Merhaba, ben Alex. Aksansiz konusuyorum.",
        "tr-TR-EmelNeural", rate="-3%", pitch="+2Hz")
    await com.save("test.mp3")
asyncio.run(main())
```

## Yedek Lokal Sesler (Eger Internet Yok ise)

Edge TTS internete ihtiyac duyar. Internet kesilirse yedek olarak Piper kullanilabilir AMA daha iyi modeller var:

### A. Piper Yeni Turkce Modeller (lokal, internet bagimsiz)

Piper'in `tr_TR-dfki-medium` modeli robotik. Yeni iyi modeller:

```powershell
# Piper kurulum
pip install piper-tts

# Yeni Turkce modeller indir (~60 MB her biri)
# Onerilen:
#   tr_TR-fettah-medium    - dogal erkek
#   tr_TR-fahrettin-medium - tok erkek
mkdir D:\YazKlinik_Final_D300\tools\piper-models
cd D:\YazKlinik_Final_D300\tools\piper-models
curl -L -O https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/fettah/medium/tr_TR-fettah-medium.onnx
curl -L -O https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/fettah/medium/tr_TR-fettah-medium.onnx.json
```

### B. Coqui XTTS v2 (voice cloning - Hakan'in sesi)

```powershell
pip install TTS
```

```python
from TTS.api import TTS
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2")
tts.tts_to_file(
    text="Bu Hakan'in sesi ile uretilmis bir mesaj.",
    speaker_wav="D:\\YazKlinik_Final_D300\\samples\\hakan_30sec.wav",
    language="tr",
    file_path="output.wav"
)
```
Hakan'dan 6-30 saniye temiz ses ornegi gerek (gurultusuz).

### C. F5-TTS (en yeni, en dogal)

```bash
pip install f5-tts
```
F5-TTS Turkce voice cloning ile **gercekten** dogal, hatta Hakan'in sesini taklit edebilir.

## Sonuc

Bu commit'le:
- **Default ses**: Emel Neural (dogal Turkce kadin)
- **Erkek alternatif**: Ahmet Neural
- **Yedek lokal**: Piper (varsa) veya browser Microsoft Online voices
- **Tolga (Russian-aksanli)**: ARTIK SON TERCIH

Kullanici hala sevmezse:
1. Web arayuzunden ses profili degistir (`/dashboard` > Ayarlar > Ses)
2. Veya XTTS ile Hakan'in kendi sesini klonla

## Test Adimi

1. `D300_BASLAT.bat` (server'i yeniden baslat)
2. Alex'i ac (Alt+A)
3. Bir sey yaz: "Hasta listesini ac"
4. Cevabi seslendirme -> Emel Neural sesi gelmeli (Russian aksan YOK)

Eger hala kotu ses geliyorsa:
- Network ayagi: Edge TTS internet bagimlidir (cloud servis)
- VPN/firewall block? Browser dev console'da `[YK-TTS] Secilen ses:` logu kontrol et
