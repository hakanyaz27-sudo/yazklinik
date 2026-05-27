# Codex Handoff - 2026-05-26 (D700)

> Bu dosya, projeyi Codex'e devretmek icin yazildi. Once **AGENTS.md** oku
> (ozellikle yeni "Operasyonel Tuzaklar" bolumu), sonra bunu oku.

## TL;DR

Bu seansta (Claude) YazKlinik D700'de su isler yapildi ve hepsi CANLI dogrulandi:
- **Alex tamiri** (iki JS syntax hatasi tum inline JS'i kiriyordu)
- **Hiz optimizasyonu** (mojibake skor + gunluk-protokol)
- **DICOM bari** yeniden tasarim (kompakt sabit pill)
- **Hasta portali** revizyon (gelis bazli galeri + video + thumbnail + doktor onizleme + WhatsApp + lightbox hiz)
- **Mobil arayuz** duzeltmeleri (iOS odak-zoom + yuzen buton cakismasi)

Dogrulama: `python CODEX_QUICK_CHECK.py` -> `CODEX_D700_QUICK_CHECK_OK` (Hata 0 / Uyari 0).

> KRITIK: "Edit yaptim ama canliya gecmedi" tuzagina takilmamak icin AGENTS.md
> "Operasyonel Tuzaklar" bolumunu devralmadan ONCE oku. waitress hot-reload YOK.

## Mevcut Durum (dogrulanmis 2026-05-26)

- Server: HTTP **5052** (saglik/smoke kanali) + HTTPS **5443** (werkzeug), HAZIR.
- CODEX_QUICK_CHECK: `CODEX_D700_QUICK_CHECK_OK`, **Hata 0 / Uyari 0**.
- DB: **179 hasta, 728 gelis, 17541 dosya**; quick_check / integrity / foreign_key OK.
- Servisler 200: Ollama (qwen2.5:32b + medgemma:27b), SIP Alex, Whisper, Piper, Orthanc, ComfyUI.
- `yazklinik_web.py` = **13.6 MB** tek dosya. Calisan proc taze (proc start > dosya mtime).

## Bu Seansta Yapilanlar

### 1. Alex tamiri (kritik)
Iki JS syntax hatasi BASE_HTML inline JS'ini kiriyordu -> Alex her yuzeyde olu gorunuyordu:
- `yazklinik_web.py:44557`: `Durdur\'a` -> `Durdur\\'a` (Python tek backslash'i yutuyor, kacisli olmayan apostrof 107KB'lik inline JS bloggunu kiriyordu)
- `yazklinik_web.py:41372`: yorum satiri bir IIFE acilisini yutuyordu ("Unexpected token '}'") -> iki satira bolundu
- `yk-core.js` immutable-cache + statik `?v=` oldugu icin versiyon bump edildi (`?v=D700-alex-jsfix-2026-05-26`).
- Teshis: Playwright `pageerror` + rendered `<script>`'lere `node --check`. Sonuc: 0 uncaught error.

### 2. Hiz optimizasyonu
- `yazklinik_textfix.py` `_mojibake_score`: ASCII fast-path (`text.isascii()`) + tek derlenmis regex -> `fix_mojibake_text` **319ms -> 159ms** (davranis ozdes, 0 mismatch).
- `yazklinik_web.py` `_daily_protocol_rows`: `_assign_missing_visit_protocols` artik 600sn throttle (modul global `_DAILY_PROTO_ASSIGN_LAST`) -> `/gunluk-protokol` **47s -> ~0.2s** (warm).

### 3. DICOM bari (hasta sayfasi, render())
- Eski tam-genislik sticky banner sayfayi ittirip kullanissiz yapiyordu -> kompakt sabit pill (`#yk-patient-dicom-archive-banner`, sag-ust, icerigi ittirmez).
- Mobilde (<=760px) alta tasinir; FAB ile cakismasin diye `bottom:132px`.

### 4. Hasta portali (`/hasta-portal/p/<token>`)
- **Gelis bazli galeri**: `visit_groups`/`ordered_visits` ile her gelisin resim+video+PDF'i ayri; tarih-kart filtre cipleri (`birsey N foto / M video / K pdf`); tum resimler ayni anda yuklenmez.
- **Video bolumu** + `<video preload="metadata" controls>` onizleme.
- **Thumbnail** (`_patient_portal_thumb_response(path, max_px)`, PIL + disk cache `portal_thumbs`): `?thumb=1`->480px, `?view=1`->1400px, else full. `_patient_portal_file_items` 90sn cache + video uzantilari + limit 240.
- **Doktor onizleme**: `/hasta-portal/onizleme/<key>` (`@login_required`). Token `onizleme-<key>` SADECE oturum acik personele dosya servis eder; anonim 403 (`_d700_patient_portal_guard` muafiyeti).
- **Hero karti** doktor takip kartiyla ayni gorunum (koyu lacivert gradyan `linear-gradient(140deg,#1d2b4d,#163f47,#0f4d4a)`, `.phero`/`.pchip`); **telefon numarasi kaldirildi**.
- **WhatsApp ile gonder** butonu (link olusturulunca + son linkler satirlarinda).
- **Lightbox hizi**: viewer `?view=1` (1400px) + komsu preload (idx+-1, idx+2). Full 174KB -> view 62KB / sicak 40ms.

### 5. Mobil arayuz (2026-05-26)
Playwright mobil audit (390x844, iPhone UA) ile 9 sayfa olculdu. Temel saglam: hicbir sayfada yatay tasma yok, JS hatasi yok, alt navigasyon bar var, 390px'e sigiyor. Iki somut kusur duzeltildi:
- **iOS odak-zoom**: `<=820px`'de tum `input/select/textarea/.form-control` 16px'e zorlandi (iPhone <16px input'ta odakta otomatik zoom yapip sayfayi sicratir). Hasta takip ekrani **40 -> 0** tetikleyici alan.
- **Yuzen buton cakismasi**: mobilde DICOM pill + "Hasta Portal" FAB alt-sagda 16px arayla ust uste biniyordu -> ayrildi (`overlapping:false`, 7px bosluk, ikisi de ekran ici).
- Ikisi de `render()` icinde sayfa HTML'ine enjekte (`<style id="yk-mobile-hardening">`, FAB inject'inden hemen sonra). **no-cache** oldugu icin reload'da aninda gecerli; `?v=` bump GEREKMEZ.

### 6. Cloudflare bakim sayfasi (YARIM)
- `/bakim` + `/bakim-sayfasi` route + `cloudflare_bakim_sayfasi.html` mevcut (koyu-teal, 25sn auto-refresh, "Sistem kisa bir bakimda / 5 dakika sonra tekrar deneyin").
- AMA `yazhakan.com.tr` **FREE plan** -> 5xx Custom Pages kapali (err 1219). Bakim sayfasinin yayina girmesi icin **Cloudflare WORKER** lazim (henuz yazilmadi/deploy edilmedi).

## Codex'in Yapacaklari (oneri)

### YUKSEK
1. **Cloudflare bakim WORKER'i**: server restart sirasinda 502 yerine bakim sayfasi. `cloudflare_bakim_worker.js` yaz; origin down / 5xx'te `cloudflare_bakim_sayfasi.html` servis et. CF dashboard'a deploy operator yapar. (FREE planda Custom Pages calismaz, Worker sart.)

### ORTA
2. **Entity-title hatasi**: `/yaklasan-dogumlar` ust seridinde baslik ham HTML-entity gosteriyor (`Yakla&#351;an`). Sebep: sayfa title'inin cift-escape edilmesi (`<title>{_html.escape(title)}</title>` + title zaten `&#351;` iceriyor); muhtemelen masaustu tarayici sekmesinde de var. Fix `render()` title-escape mantigini etkiler -> genis degil, hedefli yap (ya title'i temiz unicode ver, ya title'i escape etmeden once entity decode et).
3. **Header sag kumesi** mobilde ekran disinda (tema/mod/zil). Islevler alt nav (Tema/Ayar) + govdedeki inline mod barinda (Sessiz/Sesli/Tam) zaten var -> kritik degil. Istenirse header grid mobil yerlesimi (DIKKAT: masaustu WebShell ana yuzey, kirma).

### DUSUK
4. Genis veri tablolari (Yaklasan Dogumlar, Portal) zaten "Tabloyu yana kaydir" ile yatay-scroll'lu - ekstra is yok.
5. Alex'i medgemma'ya cevirme: VRAM 32GB + MAX_LOADED_MODELS=1 -> iki model swap thrashing yapar, KOTULESTIRIR. Hasta-ilgili mesaj LOKAL qwen, genel mesaj online gpt-4o-mini routing'i koru.

## Bilinen Sorunlar / Acik Isler

- `yazklinik_web.py` 13.6 MB tek dosya - parcalama riskli; ekleme yakin route'un yanina.
- Mojibake source'ta var (Win-1252 cift encode) - otomatik formatlama YAPMA, yeni kod ASCII-safe.
- Alex sesli (mic/STT/TTS) tarayici/ortam bagimli - server-side tam cozulemez.
- CF maintenance Worker deploy edilmedi.
- Gebelik tarihleme PDF-merkezli: cogu SAT/EDD PDF raporlarda (usg ga_weeks bos). TUM gebeleri listelemek yavas PDF taramasi ister (~60-70s); default hizli (SAT/USG), tam tarama opt-in.

## Degisen Dosyalar (bu seans)

- `yazklinik_web.py` - Alex JS fix (L44557, L41372), yk-core ?v= bump, gunluk-protokol throttle, DICOM bar redesign, portal revizyon (galeri/video/thumbnail/onizleme/hero/WhatsApp/lightbox), mobil-hardening inject (`yk-mobile-hardening`), FAB/DICOM mobil konumlari.
- `yazklinik_textfix.py` - `_mojibake_score` hizlandirma.
- `cloudflare_bakim_sayfasi.html` - yeni bakim sayfasi.

---
Op. Dr. Hakan YAZ icin. Devralma kontrolu: `python CODEX_QUICK_CHECK.py` -> `CODEX_D700_QUICK_CHECK_OK`.
Operasyonel tuzaklar: **AGENTS.md > "Operasyonel Tuzaklar"** bolumu.

