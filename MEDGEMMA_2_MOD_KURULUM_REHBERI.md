# MedGemma 2 Mod Kurulum Rehberi (D700)

Bu altyapi iki farkli kurulum verir:

1. `ONLINE` kurulum  
2. `OFFLINE` kurulum

## 1) Tek ekran secim

```bat
D:\YazKlinik_Final_D700\MEDGEMMA_KURULUM_SECENEKLI.bat
```

## 2) Direkt online

```bat
D:\YazKlinik_Final_D700\MEDGEMMA_ONLINE_KUR.bat
```

Yaptigi:
- Ollama kurulu degilse kurmayi dener (`winget`)
- Ollama API (`11434`) ayaga kalkar
- `medgemma:27b` pull edilir
- HF MedGemma modelleri indirilir:
  - `google/medgemma-4b-it`
  - `google/medgemma-1.5-4b-it`
- `config.env` icinde MedGemma aktiflenir (`YAZKLINIK_MEDGEMMA_ENABLED=1`)

## 3) Direkt offline

```bat
D:\YazKlinik_Final_D700\MEDGEMMA_OFFLINE_KUR.bat
```

Yaptigi:
- `MEDGEMMA_OLLAMA_PACK` icindeki `ollama-runtime` kopyalanir
- Pack icindeki HF MedGemma dosyalari proje `models` klasorune kopyalanir
- Pack icindeki Ollama `manifests+blobs` hedef `~\.ollama\models` altina kopyalanir
- Ollama API ayaga kalkar
- `config.env` icinde MedGemma aktiflenir

## 4) Offline pack uretme/guncelleme

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\YazKlinik_Final_D700\MAKE_MEDGEMMA_OLLAMA_PACK.ps1 -EnsureOllamaModels
```

Not:
- Script MedGemma HF dosyalarini ve Ollama tarafinda istenen MedGemma tag'larinin
  `manifest+blob` artefaktlarini pakete koyar.
- Varsayilan tag: `medgemma:27b`

## 5) Rapor dosyalari

- Online rapor: `runtime_state\MEDGEMMA_ONLINE_INSTALL_REPORT_*.json`
- Offline rapor: `runtime_state\MEDGEMMA_OFFLINE_INSTALL_REPORT_*.json`
- Pack raporu: `MEDGEMMA_OLLAMA_PACK\PACK_REPORT.json`
