# Claude Devir - Sol Menu Geri Donus (2026-05-18)

## Calisan aktif proje
- Bu PC'de aktif 5443 sunucusu: `D:\YazKlinik_Final_D500\yazklinik_web.py`
- D700 degil, D700 canli calisiyor.

## Yapilan degisiklik
- Dosya: `D:\YazKlinik_Final_D500\yazklinik_web.py`
- `yk-d700-final-polish.css` ve `yk-d700-sidebar-premium.js` enjeksiyonu kosula baglandi.
- Sabit: `_YK_ENABLE_D500_SIDEBAR_PREMIUM = False`
- Sonuc: Sol menude istemeyen premium/kartli gorunum kapandi, sade menuye dondu.

## Dogrulama
- `python -m py_compile yazklinik_web.py` -> OK
- `python CODEX_QUICK_CHECK.py` -> `CODEX_D500_QUICK_CHECK_OK`
- `/hastalar` HTML kontrolu:
  - `yk-d700-final-polish.css` yok
  - `yk-d700-sidebar-premium.js` yok

## Claude'a not
- Sol menuyu tekrar tasarlamak istenirse once `yazklinik_web.py` icindeki tema enjeksiyon bloklarini koruyup
  gorunumu `static/yk-core.css` uzerinden sade/okunur olarak revize et.
- Bu premium bloklar tekrar acilacaksa yalnizca su bayragi `True` yap:
  - `_YK_ENABLE_D500_SIDEBAR_PREMIUM`



