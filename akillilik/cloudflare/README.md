# Cloudflare Tunnel — YazKlinik Public Erisim (alternatif)

Tailscale Funnel'in alternatifi: kendi domain'in + Cloudflare hesabi varsa
**istediğin port numarasini** kullanabilirsin (Funnel 443/8443/10000 ile sinirli).

## Adim 1 - cloudflared kur

```powershell
winget install Cloudflare.cloudflared
```

## Adim 2 - Tunnel olustur (ikinci PC'de, login bir kez)

```powershell
cloudflared tunnel login
# Tarayici acilir, Cloudflare hesabina giris yap, domain'i sec
cloudflared tunnel create yazklinik-tunnel
# Bir UUID + credentials JSON .cloudflared/ altinda olusur
```

## Adim 3 - DNS route

```powershell
cloudflared tunnel route dns yazklinik-tunnel yazklinik.ornek.com
```

## Adim 4 - config.yml (ikinci PC'de)

`~/.cloudflared/config.yml`:

```yaml
tunnel: yazklinik-tunnel
credentials-file: C:\Users\yazha\.cloudflared\<uuid>.json

ingress:
  - hostname: yazklinik.ornek.com
    service: https://100.115.42.18:5443       # Bu PC'nin Tailscale IP'si
    originRequest:
      noTLSVerify: true                       # YazKlinik self-signed
      httpHostHeader: yazklinik.ornek.com
  - service: http_status:404
```

## Adim 5 - Calistir

```powershell
# Test (foreground)
cloudflared tunnel run yazklinik-tunnel

# Servis olarak kur (kalici)
cloudflared service install
```

## Karsilastirma

| | Tailscale Funnel | Cloudflare Tunnel |
|---|---|---|
| Port | 443/8443/10000 sabit | Istedigin (80/443 default, custom HTTPS) |
| Domain | `<host>.tailnet.ts.net` (free) | Kendi domain'in (gerek) |
| Cert | LE otomatik | LE otomatik |
| Setup | 5 dk | 15 dk (domain + DNS) |
| Maliyet | Tailscale ucretsiz tier'da limit | CF ucretsiz hesapta neredeyse limitsiz |
| Bagimliik | Tailscale tailnet | CF hesabi + domain |

## YazKlinik wire

Cloudflare Tunnel arkasinda calisirken `yazklinik_remote_access.py`
ProxyFix zaten X-Forwarded-* basliklarini okur. Ek konfigurasyon yok.

Audit log'da gorulur:
```
REMOTE GET /hasta/F... from=<gercek IP> host=yazklinik.ornek.com
```

## Guvenlik

- Cloudflare Access ekle: sadece dogrulanmis email/Google login sonrasi sayfa
- Rate limit + DDoS koruma Cloudflare tarafinda otomatik
- WAF kurali: `path contains "/api/" require login`
