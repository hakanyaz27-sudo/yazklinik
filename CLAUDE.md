# Claude Code Brief - YazKlinik Final D700

## Gorev

Bu repo Op. Dr. Hakan YAZ icin lokal klinik yonetim sistemidir.
Stack: Python 3.10+, Flask, waitress, sqlite3, Windows WebShell.

## Ilk adim

1. `D:\YazKlinik_Final_D700` klasorunde calis.
2. `CLAUDE_BASLA_BURADAN.md` oku.
3. `AGENTS.md` oku (kritik kurallar burada).
4. Ilk dogrulama:

```powershell
Set-Location "D:\YazKlinik_Final_D700"
& "D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" CODEX_QUICK_CHECK.py
```

Beklenen: `CODEX_D700_QUICK_CHECK_OK`

## Baslatma

```powershell
D:\YazKlinik_Final_D700\D700_BASLAT.bat
```

Aktif URL/port `config.env`'den okunur (bu kurulumda web portu 5052 olabilir).

## En onemli dosyalar

- `yazklinik_web.py` - ana Flask uygulamasi
- `yazklinik_feature_sync.py` - menu/route manifesti
- `D700_BASLAT.bat` - server + destek servisleri
- `D700_ILK_KURULUM.bat` - ilk kurulum/venv/pip
- `config.env` - NAS, DB, port, AI ayarlari
- `CODEX_QUICK_CHECK.py` - compile + DB + route + servis dogrulama
- `MEDGEMMA_KURULUM_SECENEKLI.bat` - MedGemma online/offline kurulum secimi

## Cok kritik kurallar

- `yazklinik_v68.py` dosyasina dokunma (zorunlu degilse).
- Hasta verisi silme; arsiv mantigi kullan.
- NAS altinda dosya silme yapma.
- Buyuk refactor yapma; kucuk hedefli patch yap.
- Degisiklikten sonra dogrulama calistir:
  - `python -m py_compile ...` (gerektiginde)
  - `CODEX_QUICK_CHECK.py`
