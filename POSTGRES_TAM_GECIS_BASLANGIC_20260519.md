# PostgreSQL tam gecis baslangic notu - 2026-05-19

Bu adimda canli YazKlinik uygulamasi SQLite'tan koparilmadi. Once guvenli
PostgreSQL mirror hatti kuruldu.

## Neden bu sekilde?

- Canli klinik verisi `local_db/yazklinik_v68.sqlite3` icinde duruyor.
- Uygulama kodunda cok sayida SQLite uyumlu SQL ve `?` parametre kullanimi var.
- Direkt PostgreSQL'e almak riskli olurdu.
- Bu nedenle tum SQLite tablolari once PostgreSQL'de ayri bir schema altina
  birebir kopyalanip sayi dogrulamasindan geciriliyor.

## Yeni arac

`YAZKLINIK_POSTGRES_FULL_MIGRATE.py`

Kullanim:

```powershell
.\.venv\Scripts\python.exe .\YAZKLINIK_POSTGRES_FULL_MIGRATE.py --dry-run
.\.venv\Scripts\python.exe .\YAZKLINIK_POSTGRES_FULL_MIGRATE.py --apply --yes
.\.venv\Scripts\python.exe .\YAZKLINIK_POSTGRES_FULL_MIGRATE.py --compare
```

## Guvenlik

- SQLite dosyasina yazmaz; read-only acar.
- NAS dosyalarina dokunmaz.
- PostgreSQL'de ayri schema olusturur.
- Canli uygulama DB motoru bu adimda degistirilmez.

## Sonraki faz

1. PostgreSQL mirror satir sayilari eksiksiz dogrulanir.
2. `db_conn` icin PostgreSQL uyumlu adapter hazirlanir.
3. SQLite `?` parametreli SQL'ler adapter ile uyumlu hale getirilir veya
   kritik route'lardan baslayarak Postgres-native repository katmani eklenir.
4. Once okuma-only shadow mode, sonra yazma dual-write, en son PostgreSQL primary.
