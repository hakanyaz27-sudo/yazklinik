# YazKlinik Pro Final D250

**Op. Dr. Hakan YAZ** — Klinik yönetim sistemi, temiz kurulum.

## Lokasyon

```
D:\YazKlinik_Final_D250\
├── yazklinik_web.py              ana Flask uygulamasi
├── yazklinik_v68.py              ortak helper'lar
├── yazklinik_feature_sync.py     route manifesti
├── yazklinik_*.py                15+ ek modul
├── yazklinik\                    Python paketi
├── static\                       UI varlik
├── tools\                        yan araclar (PDF/OCR vs)
├── local_db\
│   └── yazklinik_v68.sqlite3     LOKAL DB (server PC'de, NAS'ta degil)
├── auto_backups\                 24 saatte bir DB yedek
├── config.env                    Ayar dosyasi (NAS, DB, port)
├── D250_BASLAT.bat               Tek tikla baslat (WebShell)
├── D250_WEBSHELL_WINDOWS.bat      Windows WebShell arayuzu
└── README_D250.md                Bu dosya
```

## Konfigurasyon

### `config.env` (default'lar)

```
YAZKLINIK_NAS_ROOT=\\asustor\Voluson\Hastalar
YAZKLINIK_DB_PATH=D:\YazKlinik_Final_D250\local_db\yazklinik_v68.sqlite3
YAZKLINIK_WEB_PORT=5052
YAZKLINIK_HTTPS_PORT=5443
YAZKLINIK_ENABLE_HTTPS=1
YAZKLINIK_WAITRESS_THREADS=12
YAZKLINIK_BACKUP_ROOT=D:\YazKlinik_Final_D250\auto_backups
YAZKLINIK_VOLUSON_AUTO_PREFIX=F137230
```

### NAS / DB degistirme

1. **Web UI** (kolay): `http://127.0.0.1:5052/sistem-ayarlari` — form'dan editle, kaydet, sonra D250_BASLAT.bat ile restart.
2. **Manuel**: `D:\YazKlinik_Final_D250\config.env` dosyasini Notepad ile editle, kaydet, restart.

Her iki yontem de ayni dosyaya yazar.

## Calistirma

```
D:\YazKlinik_Final_D250\D250_BASLAT.bat        (cift tikla, WebShell acar)
D:\YazKlinik_Final_D250\D250_WEBSHELL_WINDOWS.bat  (sadece WebShell)
```

Acilis sirasi:
1. `config.env` okunur, env var olarak set edilir
2. `\\asustor\Voluson` erisimi kontrol edilir
3. `D104\.venv` veya yerel `.venv` Python bulunur
4. Eski port 5052 zombie temizlenir
5. Server arka planda baslar
6. 30 saniye icinde WebShell acilir: sol Windows menu + orta web ekran

## Erisim

- HTTP: `http://127.0.0.1:5052`
- HTTPS: `https://127.0.0.1:5443`
- LAN: `http://192.168.1.40:5052`
- Giris: `doktor / 1234` (TAM YETKI)

## D250 Yenilikleri (D128'den geldi + yeni)

### Sistem
- **Lokal DB** server PC'de (`D:\local_db\`) — NAS yokken bile calisir
- **NAS yolu** `\\asustor\Voluson\Hastalar` (Asustor NAS) — Voluson USG cihazi paylasimi
- **config.env** ile tum yollar editlenebilir
- **/sistem-ayarlari** UI ile NAS/DB/port web'den degistirilir

### D128'den miras (devam ediyor)
- **Tedavi Planlayici** + DDI etkilesim + A5 recete + QR + RX no + PDF indir
- **Hasta autocomplete** + SAT/USG bazli gebelik haftasi otomatik
- **Hasta listesi GA chip** (sari SAT / mavi USG / yesil PDF)
- **Hasta Birlestir** — 2 hasta = 1 hasta merge (46 tablo bulk transfer)
- **Wake word "Alex"** — arka planda dinler, "Alex" deyince aktif
- **Klavye kisayolu** Ctrl+Shift+A toggle, Esc stop
- **DB performans** synchronous=NORMAL + 64MB cache + retry logic

### Klinik moduller
- OB/GYN Rehber (textbook 11 kategori)
- Turkiye Ilac Marka DB (110+ jenerik → 400+ marka)
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
| Port 5052 dolu | D250_BASLAT.bat otomatik temizliyor; manuel: `taskkill /F /IM python.exe` |
| Mikrofon yok | RDP audio capture aktif olmali (KLINIK_DOKTOR_MIKROFONLU.rdp) |

## Versiyon

- **D200** (2026-05-10): Asustor NAS + lokal DB + temiz kurulum
- D128 (2026-05-09): SUPER paket — DDI + Wake word + Hasta merge + perf tuning
- D104 (eski): Aktif kaynak klasoru
