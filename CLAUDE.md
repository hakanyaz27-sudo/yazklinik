# Claude Code Brief - YazKlinik Final D300

## Gorev

Bu proje Op. Dr. Hakan YAZ icin lokal klinik yonetim sistemidir.
Stack: Python, Flask, waitress, sqlite3, Windows WebShell.

## Nereden basla?

1. `D:\YazKlinik_Final_D300` klasorunu ac.
2. `CLAUDE_BASLA_BURADAN.md` dosyasini oku.
3. Sonra `AGENTS.md` ve `D300_HANDOFF.md` dosyalarini oku.
4. Ilk dogrulama:

```powershell
Set-Location "D:\YazKlinik_Final_D300"
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" CODEX_QUICK_CHECK.py
```

## Baslatma

```powershell
D:\YazKlinik_Final_D300\D300_BASLAT.bat
```

Adres: `https://127.0.0.1:5443`
Giris: `doktor / 1234`

## En onemli dosyalar

- `yazklinik_web.py` - ana Flask uygulamasi
- `yazklinik_feature_sync.py` - menu/route manifesti
- `YazKlinik_BrowserShell_Windows.ps1` - hizli browser WebShell launcher
- `YazKlinik_WebShell_Windows.bat` - Windows WebShell baslatici
- `D300_BASLAT.bat` - server + WebShell tek tik baslatma
- `config.env` - NAS, DB, port ve WebShell ayarlari
- `CODEX_QUICK_CHECK.py` - sistem dogrulama

## Dikkat

- `yazklinik_v68.py` dosyasina dokunma.
- Hasta verisi ve NAS dosyasi silme.
- Kodda eski mojibake var; tum dosyayi formatlama.
- Kucuk hedefli patch yap, sonra test calistir.



