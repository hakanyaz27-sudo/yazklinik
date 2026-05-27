# WebUI Araç Kurulum Dosyasi (D700)

## 1) Figma
- **Kurulum**: Windows'ta otomatik olarak yuklenir. Yoksa:
  - https://www.figma.com/downloads/

## 2) Postman
- **Kurulum**: bu scriptle `Postman.Postman` kullaniliyor.

## 3) Playwright
- Bu klasördeki `WEBUI_TOOLS_SETUP.ps1` ile paketler yuklenir.
- `playwright_smoke.mjs` dosyasi `/giris` login + `/hastalar` sayfasi smoke testi icin hazir.

## 4) Lighthouse
- Komutlar:
  - `npm run lighthouse_login`
  - `npm run lighthouse_dashboard`
- Sonuclar: `lighthouse-giris.html`, `lighthouse-dashboard.html`

## 5) WAVE ve Axe
- Tarayicida acik sayfa olarak kurulacak eklenti linkleri:
  - WAVE: https://wave.webaim.org/extension
  - Axe (Chrome/Edge): https://www.deque.com/axe/devtools/extension/chrome

## Calisma
PowerShell:
```powershell
Set-Location "D:\YazKlinik_Final_D500\webui_tools"
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force
.\WEBUI_TOOLS_SETUP.ps1
```

Smoke test ciktilarini her degisiklikten sonra alabilirsin.

