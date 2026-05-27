# D700 Hasta Portal Ayrimi - 2026-05-27

## Ozet

Hasta portali ana `yazklinik_web.py` process'inden ayrildi.

- Ana doktor programi: `https://yazhakan.com.tr` -> `127.0.0.1:5052` / Caddy `5443`
- Hasta portali: `https://hasta.yazhakan.com.tr` -> `127.0.0.1:5053`
- Yeni public program: `yazklinik_patient_portal_public.py`
- Tek tik baslatma: `D700_PATIENT_PORTAL_BASLAT.bat`

## Guvenlik davranisi

- Hasta portal programinda doktor login, hasta listesi, sistem ayarlari ve admin route'lari yoktur.
- `hasta.yazhakan.com.tr/giris` 404 doner.
- Ana domain uzerinden `/hasta-portal/p/<token>` gelirse `https://hasta.yazhakan.com.tr/hasta-portal/p/<token>` adresine 302 yonlenir.
- Doktor tarafinda link uretimi ana programda kalir: `/hasta-portal-admin`.
- Uretilen linkler `YAZKLINIK_PATIENT_PORTAL_BASE_URL` nedeniyle hasta subdomain'i ile baslar.

## Degisen dosyalar

- `yazklinik_patient_portal_public.py` - public hasta portal Flask app
- `config.env` - hasta portal host/port/base URL ayarlari
- `D700_BASLAT.bat` - hasta portal servis baslatma entegrasyonu
- `D700_HEALTH_MONITOR.py` - hasta portal health kontrolu
- `D700_PATIENT_PORTAL_BASLAT.bat` / `.ps1` - web'den bagimsiz portal baslatma
- `D700_PATIENT_PORTAL_SPLIT_CHECK.py` / `.bat` - hasta portali ayrimini tek komutla dogrulama
- `D700_PATIENT_PORTAL_TEK_TIK_KONTROL.bat` - quick check + portal ayrim check zinciri
- `%USERPROFILE%\.cloudflared\config.yml` - `hasta.yazhakan.com.tr -> http://127.0.0.1:5053`
- `yazklinik_web.py` - ana domain public portal isteklerini hasta subdomain'e yonlendirir

## Dogrulama

- `CODEX_QUICK_CHECK.py` -> `CODEX_D700_QUICK_CHECK_OK`
- `D700_PATIENT_PORTAL_SPLIT_CHECK.py` -> `D700_PATIENT_PORTAL_SPLIT_CHECK_OK`
- `https://hasta.yazhakan.com.tr/` -> 200
- `https://hasta.yazhakan.com.tr/giris` -> 404
- Gecici token ile `https://hasta.yazhakan.com.tr/hasta-portal/p/<token>` -> 200, iptal sonrasi 403
- Ana domain `http://127.0.0.1:5052/hasta-portal/p/<token>` -> 302 hasta subdomain

## Rutin kontrol

```powershell
cd /d D:\YazKlinik_Final_D700
D700_PATIENT_PORTAL_SPLIT_CHECK.bat
```

Bu kontrol test token'i olusturur, ana program/hasta portali/Cloudflare rotasini
dener ve test token'ini `revoked_at` ile iptal eder; hasta kaydi veya NAS dosyasi silmez.

Tam zincir kontrol:

```powershell
cd /d D:\YazKlinik_Final_D700
D700_PATIENT_PORTAL_TEK_TIK_KONTROL.bat
```

## Cloudflare

Tunnel ID: `5b2615e3-c29c-4dbf-80f2-f76e73ac73b7`

DNS route:

```powershell
cloudflared tunnel route dns 5b2615e3-c29c-4dbf-80f2-f76e73ac73b7 hasta.yazhakan.com.tr
```

Ingress kural sirasi onemli: `hasta.yazhakan.com.tr` kuralini `yazhakan.com.tr` kurallarinin ustunde tut.
