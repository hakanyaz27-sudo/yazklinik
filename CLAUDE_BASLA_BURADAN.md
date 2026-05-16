# Claude - Basla Buradan

Sen YazKlinik Final D300 klasorundesin:

```text
D:\YazKlinik_Final_D300
```

Kullanici Turkce, kisa ve sonuc odakli cevap ister. "Yap" derse plan uzatma:
calisan kod, bir test ve kisa teslim bekler.

## Ilk kontrol

```powershell
Set-Location "D:\YazKlinik_Final_D300"
& "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" CODEX_QUICK_CHECK.py
```

## Calistirma

```powershell
D:\YazKlinik_Final_D300\D300_BASLAT.bat
```

## Son bilinen durum

- D300, D200 son halinden ayrilmis yeni calisma kopyasidir.
- WebShell hizlandirildi ve Chrome/Edge app-mode olarak acilir.
- Uzman/Basit mod secimi ve tema secimi ust menude tekrar calisir.
- Config, DB ve backup yollari D300 klasorune ayarlandi.

## Guvenli calisma kurallari

- `yazklinik_v68.py` dosyasina dokunma.
- Hasta kaydi/dosyasi silme; arsiv kullan.
- NAS icindeki dosyalari silme.
- Degisiklikten sonra compile + `CODEX_QUICK_CHECK.py` calistir.


