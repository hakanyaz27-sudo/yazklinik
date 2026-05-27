# D700 PostgreSQL hardening yol haritasi (etki / sure)

Bu plan dogrudan canli stabilite etkisine gore siralanmistir.

## Faz-1 (hemen, en yuksek etki)

1. Login guvenligi: rate limit + 2FA zorunlulugu (doktor/admin).
2. Flask 500 yakalama: Sentry entegrasyonu.
3. Aylik guvenlik taramasi: `pip-audit + bandit`.

## Faz-2 (kisa vade)

1. PgBouncer ile baglanti havuzu.
2. Staging instance (5543) ile canli oncesi duman testi.

## Faz-3 (orta vade)

1. PostgreSQL PITR: WAL arsiv + base backup + point-in-time restore.
2. UPS kontrollu kapanis scripti + operasyon proseduru.

## Bu teslimde eklenen dosyalar

- `ops/postgres/pitr/*`
- `ops/pgbouncer/*`
- `ops/staging/*`
- `ops/security/*`
- `ops/ups/*`

## Sonraki uygulama adimi

1. `config.env` icinde login+2FA+Sentry degiskenlerini doldur.
2. Staging ortaminda ac (`ops/staging/STAGING_BASLAT.bat`).
3. Staging smoke OK ise canliya al.

