# YazKlinik D700 - Claude Handoff (Guncel)

Bu dosya Claude oturumunun D700'u dogru anlamasi icindir.

## Proje kimligi

- Proje: YazKlinik Final D700
- Klasor: `D:\YazKlinik_Final_D700`
- Stack: Python 3.10+, Flask, waitress, sqlite3
- Baslatma: `D700_BASLAT.bat`
- Ilk kurulum: `D700_ILK_KURULUM.bat`

## Hemen calisacak kontrol

```powershell
Set-Location "D:\YazKlinik_Final_D700"
& ".venv\Scripts\python.exe" CODEX_QUICK_CHECK.py
```

Beklenen satir: `CODEX_D700_QUICK_CHECK_OK`

## Kritik dosyalar

1. `yazklinik_web.py` - ana Flask uygulamasi
2. `yazklinik_feature_sync.py` - menu/route manifesti
3. `config.env` - DB/NAS/port/AI ayarlari
4. `CODEX_QUICK_CHECK.py` - sistem dogrulama
5. `D700_BASLAT.bat` - normal acilis

## D700 kurallari (kirmama listesi)

- `yazklinik_v68.py` dosyasini buyuk degistirme.
- Hasta verisi silme yapma; arsiv mantigi kullan.
- NAS klasorunde silme yapma.
- Kodda mojibake olabilecek bolumleri genis capta formatlama.
- Kucuk hedefli patch + test ile ilerle.

## MedGemma/Ollama (D700)

- Iki modlu kurulum menusu:
  - `MEDGEMMA_KURULUM_SECENEKLI.bat`
- Online:
  - `MEDGEMMA_ONLINE_KUR.bat`
- Offline:
  - `MEDGEMMA_OFFLINE_KUR.bat`

## Yeni PC icin paketler

J surucusunde hazirlanan paketler:

- Core kurulum:
  - `J:\YazKlinik_D700_CORE_SETUP_20260525_222848\KURULUM_CORE_BASLAT.bat`
- Tum Ollama model paketi (MedGemma dahil):
  - `J:\YazKlinik_D700_OLLAMA_MODELS_PACK_20260525_222848\KURULUM_OLLAMA_OFFLINE_PAKET.bat`

## Kullanici ile iletisim stili

- Turkce, kisa, direkt.
- "Yap" denince teori degil uygulama + test + net sonuc ver.
- "Calismiyor" denince once canli durum kontrolu yap (port, process, route).
