# YazKlinik Pro Final D700

**Op. Dr. Hakan YAZ** Ã¢â‚¬â€ Klinik yÃƒÂ¶netim sistemi, temiz kurulum.

## Lokasyon

```
D:\YazKlinik_Final_D700\
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_web.py              ana Flask uygulamasi
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_v68.py              ortak helper'lar
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_feature_sync.py     route manifesti
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_*.py                15+ ek modul
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik\                    Python paketi
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ static\                       UI varlik
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ tools\                        yan araclar (PDF/OCR vs)
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ local_db\
Ã¢â€â€š   Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ yazklinik_v68.sqlite3     LOKAL DB (server PC'de, NAS'ta degil)
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ auto_backups\                 24 saatte bir DB yedek
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ config.env                    Ayar dosyasi (NAS, DB, port)
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ D700_BASLAT.bat               Tek tikla baslat (WebShell)
Ã¢â€Å“Ã¢â€â‚¬Ã¢â€â‚¬ D700_WEBSHELL_WINDOWS.bat      Windows WebShell arayuzu
Ã¢â€â€Ã¢â€â‚¬Ã¢â€â‚¬ README_D700.md                Bu dosya
```

## Konfigurasyon

### `config.env` (default'lar)

```
YAZKLINIK_NAS_ROOT=\\asustor\Voluson\Hastalar
YAZKLINIK_DB_PATH=D:\YazKlinik_Final_D700\local_db\yazklinik_v68.sqlite3
YAZKLINIK_WEB_PORT=5443
YAZKLINIK_HTTPS_PORT=5443
YAZKLINIK_ENABLE_HTTPS=1
YAZKLINIK_WAITRESS_THREADS=12
YAZKLINIK_BACKUP_ROOT=D:\YazKlinik_Final_D700\auto_backups
YAZKLINIK_VOLUSON_AUTO_PREFIX=F137230
```

### NAS / DB degistirme

1. **Web UI** (kolay): `https://192.168.1.50:5443/sistem-ayarlari` Ã¢â‚¬â€ form'dan editle, kaydet, sonra D700_BASLAT.bat ile restart.
2. **Manuel**: `D:\YazKlinik_Final_D700\config.env` dosyasini Notepad ile editle, kaydet, restart.

Her iki yontem de ayni dosyaya yazar.

## Calistirma

```
D:\YazKlinik_Final_D700\D700_BASLAT.bat        (cift tikla, WebShell acar)
D:\YazKlinik_Final_D700\D700_WEBSHELL_WINDOWS.bat  (sadece WebShell)
```

Acilis sirasi:
1. `config.env` okunur, env var olarak set edilir
2. `\\asustor\Voluson` erisimi kontrol edilir
3. `D700 yerel `.venv` Python bulunur; yoksa sistem Python fallback kullanilir
4. Eski port 5443 zombie temizlenir
5. Server arka planda baslar
6. 30 saniye icinde WebShell acilir: sol Windows menu + orta web ekran

## Erisim

- HTTP: `https://192.168.1.50:5443`
- HTTPS: `https://192.168.1.50:5443`
- LAN: `https://192.168.1.50:5443`
- Giris: `doktor / users.json guncel sifre` (bu PC: 1133, TAM YETKI)

## D700 Yenilikleri (D128'den geldi + yeni)

### Sistem
- **Lokal DB** server PC'de (`D:\local_db\`) Ã¢â‚¬â€ NAS yokken bile calisir
- **NAS yolu** `\\asustor\Voluson\Hastalar` (Asustor NAS) Ã¢â‚¬â€ Voluson USG cihazi paylasimi
- **config.env** ile tum yollar editlenebilir
- **/sistem-ayarlari** UI ile NAS/DB/port web'den degistirilir

### D128'den miras (devam ediyor)
- **Tedavi Planlayici** + DDI etkilesim + A5 recete + QR + RX no + PDF indir
- **Hasta autocomplete** + SAT/USG bazli gebelik haftasi otomatik
- **Hasta listesi GA chip** (sari SAT / mavi USG / yesil PDF)
- **Hasta Birlestir** Ã¢â‚¬â€ 2 hasta = 1 hasta merge (46 tablo bulk transfer)
- **Wake word "Alex"** Ã¢â‚¬â€ arka planda dinler, "Alex" deyince aktif
- **Klavye kisayolu** Ctrl+Shift+A toggle, Esc stop
- **DB performans** synchronous=NORMAL + 64MB cache + retry logic

### Klinik moduller
- OB/GYN Rehber (textbook 11 kategori)
- Turkiye Ilac Marka DB (110+ jenerik Ã¢â€ â€™ 400+ marka)
- Profesyonel Diyet Rehberi (8 senaryo)
- Hastaya Ozel Gebelik Plani
- IVF Super Destek
- Ovulasyon Induksiyonu
- AUB / Endometrial Hiperplazi
- Pelvik Enfeksiyon & Vajinit
- Ilac Guvenligi (gebelikte kategori + DDI)
- Riskli Gebelik (DM/HT/tiroid/APS/preterm/VTE)
- Gebelik Komplikasyonlari (HG/abortus/ektopik/PPH/HELLP)

## Sorun giderme

| Sorun | Cozum |
|---|---|
| `unable to open database file` | config.env'de `YAZKLINIK_DB_PATH` mevcut path mi kontrol |
| `\\asustor\Voluson erisilmiyor` | Map drive (Asustor IP, kullanici/sifre) veya farkli NAS path tanimla |
| Port 5443 dolu | D700_BASLAT.bat otomatik temizliyor; manuel: `taskkill /F /IM python.exe` |
| Mikrofon yok | RDP audio capture aktif olmali (KLINIK_DOKTOR_MIKROFONLU.rdp) |

## Versiyon

- **D700** (2026-05-18): Asustor NAS + lokal DB + D700 menuler/ajanlar + modern tema
- D700 (2026-05-10): Asustor NAS + lokal DB + temiz kurulum
- D128 (2026-05-09): SUPER paket Ã¢â‚¬â€ DDI + Wake word + Hasta merge + perf tuning
- D700: Aktif kaynak klasoru ve yerel `.venv` kullanilir





