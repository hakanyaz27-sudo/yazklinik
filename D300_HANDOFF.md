# YazKlinik Final D300 - Handoff

## Ne bu?

Bu klasor D250 son calisan surumunden uretilen D300 calisma kopyasidir.
Amac: Codex ve Claude Code acildiginda projeyi hizli anlamasi, calistirmasi ve
guvenli sekilde devam ettirmesi.

## Klasor

`D:\YazKlinik_Final_D300`

## Baslatma

Windows:

```powershell
D:\YazKlinik_Final_D300\D300_BASLAT.bat
```

Manuel:

```powershell
Set-Location "D:\YazKlinik_Final_D300"
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" -u yazklinik_web.py
```

Adres:

```text
https://127.0.0.1:5443
doktor / 1234
```

## D300 ile gelen son durum

- WebShell artik Chrome/Edge app-mode hizli kabuk olarak aciliyor.
- WebShell istegi `yk_webshell=1` ve `YazKlinikWebShell/1.0` user-agent ile hizli moda giriyor.
- BrowserShell cache, GPU raster, no-proxy, arka plan yavaslatma kapali ve AboveNormal oncelik ayarli.
- Ust menudeki Uzman/Basit mod secimi native select katmani ile calisir hale getirildi.
- Tema butonu native select katmani ile calisir hale getirildi.
- D300 config yollari `D:\YazKlinik_Final_D300` klasorune ayarlandi.
- Lokal SQLite DB, calisan D250 DB uzerinden SQLite backup ile guvenli kopyalandi.

## Ilk okunacak dosyalar

- `AGENTS.md` - Codex/OpenAI agent kurallari
- `CLAUDE.md` - Claude Code proje brifi
- `CLAUDE_BASLA_BURADAN.md` - Claude icin ilk adim
- `CODEX_BASLA_BURADAN.md` - Codex icin ilk adim
- `CODEX_COMMANDS.md` - sik komutlar
- `CODEX_FILE_MAP.md` - dosya sorumluluklari
- `CODEX_API_ENDPOINTS.md` - route listesi

## Test

```powershell
Set-Location "D:\YazKlinik_Final_D300"
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" -m py_compile yazklinik_web.py yazklinik_v68.py yazklinik_feature_sync.py D300_TERMINAL_SYNC.py
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" CODEX_QUICK_CHECK.py
```

Beklenen son satir:

```text
CODEX_D300_QUICK_CHECK_OK
```

## Kritik kurallar

- `yazklinik_v68.py` dosyasina dokunma; legacy ve kirilgan.
- Hasta verisi silme; gerekiyorsa arsiv alanlari kullan.
- NAS klasoru altindaki hasta dosyalarini Python ile silme.
- Buyuk otomatik formatlama yapma; kaynakta mojibake bloklari var.
- Degisiklikten sonra compile ve `CODEX_QUICK_CHECK.py` calistir.



