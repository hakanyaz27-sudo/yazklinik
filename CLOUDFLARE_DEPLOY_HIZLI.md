# Cloudflare Hızlı Deploy (D700)

Bu proje Free plan icin bakim yonlendirmesini Worker ile yapar.

## 1) Tokeni ekle

`D:\YazKlinik_Final_D700\config.env` icine su satiri ac:

```env
CF_API_TOKEN=BURAYA_CLOUDFLARE_TOKEN
```

Gerekli izinler:

- `Account > Workers Scripts : Edit`
- `Zone > Workers Routes : Edit`
- `Zone > Zone : Read`

## 2) Worker + route deploy

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\YazKlinik_Final_D700\CLOUDFLARE_WORKER_KUR.ps1
```

Alternatif (tek komut, tum akisi calistirir):

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\YazKlinik_Final_D700\CLOUDFLARE_TAM_KUR.ps1
```

## 3) Opsiyonel 500 custom page denemesi

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File D:\YazKlinik_Final_D700\CLOUDFLARE_BAKIM_KUR.ps1
```

Not: Free plan bazen custom page'i reddeder; bu durumda Worker route zaten yeterlidir.
