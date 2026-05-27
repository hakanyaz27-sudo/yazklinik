# Claude - Basla Buradan (D700)

Sen `D:\YazKlinik_Final_D700` klasorundesin.

Kullanici stili:
- Turkce
- Kisa, sonuc odakli
- "Yap" dediginde calisan is + test + kisa teslim

## Ilk 5 dakika

1. `AGENTS.md` dosyasini oku.
2. `CLAUDE_HANDOFF.md` dosyasini oku.
3. Hizli dogrulama calistir:

```powershell
Set-Location "D:\YazKlinik_Final_D700"
& "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" CODEX_QUICK_CHECK.py
```

Beklenen: `CODEX_D700_QUICK_CHECK_OK`

## Calistirma

```powershell
D:\YazKlinik_Final_D700\D700_BASLAT.bat
```

Ilk kurulum gereken yeni PC:

```powershell
D:\YazKlinik_Final_D700\D700_ILK_KURULUM.bat
```

## MedGemma kurulum secenekleri

```powershell
D:\YazKlinik_Final_D700\MEDGEMMA_KURULUM_SECENEKLI.bat
```

- Secenek 1: Online kurulum (internetten indirir)
- Secenek 2: Offline kurulum (hazir pack'ten kurar)

## Asla unutma

- `yazklinik_v68.py` dosyasina dokunma (mecbur degilse).
- Hasta/NAS verisi silme.
- Buyuk refactor yerine kucuk hedefli patch.
- Is bitince dogrulama: `CODEX_QUICK_CHECK.py`.
