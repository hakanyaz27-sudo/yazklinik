# D700 14 Gun Ultra Plani

Amac: D700'u hizli, stabil, kolay, guvenli ve olculur sekilde her gun iyilestirmek.

## Gun 1-3 (Temel Stabilite + Hiz)
- Gun 1: Mobil scroll ve temel UI kilitleri temizle, quick check kanitini al.
- Gun 2: Yavas route'larda (hastalar, gunluk-protokol, hasta dosyasi) sure olcumu ve ilk optimizasyon.
- Gun 3: Restart sonrasi canliya gecis checklisti ve stale-process tespiti otomasyonu.

## Gun 4-6 (Klinik UX)
- Gun 4: Hasta listesinde tek elle hizli akis (arama, grid/liste, kart aksiyonlari).
- Gun 5: Hasta dosyasinda en sik 5 islem icin 1-2 tik hedefine in.
- Gun 6: Mobil Chrome ve WebShell gorunum dengeleme (cakisma, sabit bar, okunurluk).

## Gun 7-9 (Guvenlik + Veri)
- Gun 7: Kritik islem onaylari ve audit izini daha gorunur hale getir.
- Gun 8: DB backup/saglik kontrolleri ve geri donus dogrulama senaryosu.
- Gun 9: CF Access/uzak erisim akisi icin yanlis teshisleri azaltan net durum paneli.

## Gun 10-12 (Alex + Otomasyon)
- Gun 10: Alex paneli hata toleransi ve sessiz/voice mod gecis guvenilirligi.
- Gun 11: Klinik komutlarda hedefli otomasyon (doktor kontrolu korunarak).
- Gun 12: Uzun sureli oturumlarda performans dususu ve bellek birikimi temizligi.

## Gun 13-14 (Olcum + Kalici Standart)
- Gun 13: Haftalik kalite skor panosu (hiz, hata, UX, servis sagligi).
- Gun 14: Tum kazanimi dondur: runbook + quick smoke + operator teslim paketi.

## Basari Kriterleri
- Her degisiklikte `py_compile` + `CODEX_QUICK_CHECK.py` temiz.
- Mobil Chrome/WebShell'de scroll, tiklama, panel ac-kapa akisi hatasiz.
- Kritik klinik akislarda "bekleme/yanlis durum" sikayeti gozle gorulur sekilde azalir.
