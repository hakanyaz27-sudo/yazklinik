# YazKlinik D250 - Telefondan Claude'a Brief

> Bu dosyayi telefondan Claude.ai uygulamasina YAPISTIR.
> Claude PC'deki sistemin guncel durumunu ogrenir + soru sorabilirsin.

## Sistem

- **Proje**: YazKlinik Pro Final D250 (Op. Dr. Hakan YAZ - Kadin Dogum)
- **Klasor**: `D:\YazKlinik_Final_D250\`
- **Server**: `http://127.0.0.1:5052` (HTTPS: 5443)
- **LAN**: `http://192.168.1.40:5052`
- **Versiyon**: D250 (2026-05-11)
- **Stack**: Python 3.10+ / Flask / waitress / sqlite3
- **DB**: 138 hasta, 131 visit, 4718 dosya, 73 tablo (3.66 MB lokal)
- **NAS**: `\\asustor\Voluson` (Voluson USG cihazi)

## Bugun Yapilanlar (en yeniden eskiye)

1. **D250 yeni sürüm** - D drive'a temiz kurulum (`D:\YazKlinik_Final_D250\`)
2. **NAS** `\\Sam\usg` -> `\\asustor\Voluson` (Asustor NAS)
3. **Lokal DB** server PC'de (`local_db\yazklinik_v68.sqlite3`)
4. **`/sistem-ayarlari`** UI - NAS/DB/port web'den editlenebilir
5. **`config.env`** - tum ayarlar tek dosyada
6. **`D250_BASLAT.bat`** - tek tikla launcher
7. **`AGENTS.md`** + 4 CODEX_*.md - Codex/AI agent dokumantasyonu

## D128'den Devam Eden Super Ozellikler

- **Tedavi Planlayici** - hasta autocomplete + DDI etkilesim + A5 profesyonel recete + QR kod + RX numara + PDF indir
- **Hasta listesi GA chip** - sari SAT / mavi USG / yesil PDF kaynakli gebelik haftasi
- **Hasta Birlestir (Merge)** - 2 hasta = 1 hasta (46 tablo bulk transfer)
- **Wake word "Alex"** - arkada surekli dinler, "Alex" deyince aktif
- **Klavye kisayolu** Ctrl+Shift+A toggle, Esc stop
- **DB performans** synchronous=NORMAL + 64MB cache + 3-retry
- **18+ klinik modul**: OB/GYN rehber, IVF, Diyet, Pelvik enfeksiyon, AUB, EH, Riskli gebelik, Gebelik komplikasyonlari, vs

## Kritik Kurallar

1. `yazklinik_v68.py` dokunma (~8000 satir legacy)
2. Hasta verisi silme (sadece archived_at)
3. Mevcut pattern takip et (yakin route'larin yanina)
4. Compile + smoke test her degisiklikten sonra

## Erisim

- Server PC: `http://127.0.0.1:5052`
- LAN'dan: `http://192.168.1.40:5052`
- Giris: `doktor / 1234`
- Sistem ayar: `/sistem-ayarlari`

## Smoke Test Komutu (PC'de)

```powershell
cd D:\YazKlinik_Final_D250
python CODEX_QUICK_CHECK.py
```

Beklenen son satir: `CODEX_D250_QUICK_CHECK_OK`

## Telefondan Sormak Istediklerin Icin Sablon

> Hey Claude, ben Op. Dr. Hakan YAZ. PC'mde YazKlinik Pro D200 calisiyor (Python/Flask).
> Klasor `D:\YazKlinik_Final_D250\`. 138 hasta, NAS `\\asustor\Voluson`.
> Soru: [BURAYA SORU YAZ]

---
**Hazirlandi**: 2026-05-10 | **Server PID**: aktif | **CODEX_QUICK_CHECK**: OK
