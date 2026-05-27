# D700 Linux hizlandirma paketi

Bu paket canli Windows D700'i bozmadan Linux/Gunicorn/Nginx denemesi yapmak
icin eklendi. Hasta verisi silmez, NAS icine yazmaz, PostgreSQL primary cutover
yapmaz.

## 1) Windows baseline

Windows'ta once mevcut hizi olc:

```powershell
D700_HIZ_BASELINE.bat
```

Bugun alinan baseline ornegi:

- `/api/sistem-durumu` max 279 ms
- `/hastalar` avg 144 ms
- DB WAL saglikli, eksik index yok
- NAS ilk 120 listeleme 3 ms

## 2) Linux kurulum provasi

Repo Linux sunucuya `/opt/yazklinik/d700` olarak kopyalanir. NAS SMB mount
ornegi:

```bash
sudo mkdir -p /mnt/yazklinik-voluson
sudo mount -t cifs //asustor/Voluson /mnt/yazklinik-voluson \
  -o credentials=/etc/yazklinik/asustor.cred,iocharset=utf8,vers=3.1.1,uid=yazklinik,gid=yazklinik,file_mode=0660,dir_mode=0770
```

Kur:

```bash
cd /opt/yazklinik/d700
bash D700_LINUX_KUR.sh
nano .env.linux
```

Baslat:

```bash
bash D700_LINUX_BASLAT.sh
```

Hiz testi:

```bash
bash D700_LINUX_HIZ_TESTI.sh
```

## 3) Karsilastirma

Windows ve Linux JSON raporlarini karsilastir:

```bash
python D700_PERF_COMPARE.py runtime_state/perf/perf_audit_WINDOWS.json runtime_state/perf/perf_audit_LINUX.json
```

## 4) Production sablonlari

- `infra/linux/d700.env.example` -> `/etc/yazklinik/d700.env`
- `infra/linux/yazklinik-d700.service` -> `/etc/systemd/system/yazklinik-d700.service`
- `infra/linux/nginx-yazklinik-d700.conf` -> `/etc/nginx/sites-available/yazklinik-d700.conf`

SQLite modunda Gunicorn `workers=1, threads=24` kalmali. PostgreSQL primary
tam yesil olmadan worker sayisi artirilmaz.

## 5) PostgreSQL yolu

PostgreSQL'e gecis icin once mirror/readiness:

```bash
python YAZKLINIK_POSTGRES_FULL_MIGRATE.py --dry-run
python YAZKLINIK_POSTGRES_FULL_MIGRATE.py --apply --yes
python YAZKLINIK_POSTGRES_CUTOVER_READINESS.py
```

Raporlar yesil olmadan `.env.linux` icinde `YAZKLINIK_DB_PRIMARY=postgres`
yapilmaz.
