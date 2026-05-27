# SaaS Multi-Tenancy (Stub)

## Amac

YazKlinik'i baska klinikler de kullanabilsin diye SaaS yapi:
- Her klinik = tenant
- Veri izolasyonu: schema-per-tenant veya row-level (tenant_id)
- Onboarding: yeni klinik kayit + DB sema kurulum
- Faturalama: aylik plan (Iyzico)

## Mimari Tercih (3 yontem)

### 1. Schema-per-tenant (PostgreSQL)
```sql
CREATE SCHEMA tenant_42;
SET search_path TO tenant_42, public;
```
Avantaj: tam izolasyon. Dezavantaj: 100+ tenant'ta yonetim ag.

### 2. Database-per-tenant
Avantaj: maximum izolasyon. Dezavantaj: kaynak israfi.

### 3. Row-Level Security (RLS) - Onerilen
```sql
CREATE POLICY tenant_isolation ON visits
  FOR ALL USING (tenant_id = current_setting('app.tenant_id')::int);
```
Avantaj: tek DB, kolay yedek. Dezavantaj: dogru config sart.

## Tenant Onboarding Akisi (taslak)

```
1. Yeni klinik kayit -> tenant_id uretilir
2. Subdomain veya path: klinik42.yazklinik.com / yazklinik.com/k42
3. Admin user uretilir + magic link gonderilir
4. Demo veri yuklenir (10 hasta + 5 visit)
5. Faturalama: 14 gun trial, sonra Iyzico subscription
```

## Production yol haritasi

1. `tenants` tablosu: id, name, subdomain, plan, created_at, active
2. Tum hasta/visit tablolarina `tenant_id` ekle
3. Flask middleware: `g.tenant_id = resolve_from_subdomain()`
4. SQLAlchemy filter veya RLS policy
5. Stripe Connect / Iyzico subscription
6. Tenant-specific Ollama model (opsiyonel)
7. Yedek: her tenant icin ayri restic snapshot

## Status

**STUB - tek hekim mode aktif.** SaaS gercek dunyada talep oldugunda 2-3 hafta ile aktif.
