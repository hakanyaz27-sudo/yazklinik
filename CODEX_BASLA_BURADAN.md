# Codex - Basla Buradan

Klasor:

```text
D:\YazKlinik_Final_D300
```

Bu D300 surumu, D200 son calisan halinden uretilmis yeni calisma kopyasidir.
Ilk is olarak `AGENTS.md` ve `D300_HANDOFF.md` oku.

## Komutlar

Baslat:

```powershell
D:\YazKlinik_Final_D300\D300_BASLAT.bat
```

Test:

```powershell
Set-Location "D:\YazKlinik_Final_D300"
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" -m py_compile yazklinik_web.py yazklinik_v68.py yazklinik_feature_sync.py D300_TERMINAL_SYNC.py
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" CODEX_QUICK_CHECK.py
```

Beklenen:

```text
CODEX_D300_QUICK_CHECK_OK
```

## Son degisiklikler

- **2026-05-16:** 10 klinik ajan eklendi (telesekreter / sesli onay / USG rapor / geri cagirma / BK sync bekci / NAS izleyici / recete / gunluk ozet / mojibake bekci / PR reviewer). `/ajanlar` dashboard + `/api/agents/*` Blueprint. Detayli handoff: **`CODEX_HANDOFF_2026-05-16_AJANLAR.md`**. v68 ve mevcut route'lar dokunulmadi.
- WebShell hizli Chrome/Edge app-mode kabuga tasindi.
- WebShell fast-mode algilamasi user-agent ve `yk_webshell=1` ile garanti edildi.
- Mod secimi ve tema secimi ust menude tekrar calisir.
- D300 config, DB ve backup yollari ayrildi.


