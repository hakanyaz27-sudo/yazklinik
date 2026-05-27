# YazKlinik Uzaktan Erisim Rehberi (Tailscale Funnel + Reverse Proxy)

**Senaryo:** Op. Dr. Hakan Yaz'in klinik PC'sindeki YazKlinik (port 5443) klinik disindan da
kullanilabilsin. Tailscale Funnel veya router NAT'i ikinci bir PC uzerinden yapiyoruz; ana PC
internet'e direkt acilmiyor.

```
                   INTERNET
                       |
            +--------- v ---------+
            |  Public endpoint:    |
            |  176.236.92.142:65187|
            +----------+-----------+
                       |
                       |  (1) Router NAT veya Tailscale Funnel
                       v
            +----------+-----------+
            |  Ikinci PC           |   Tailscale: 100.102.239.42
            |  - reverse proxy /   |   Public-facing edge
            |    Tailscale Serve   |
            +----------+-----------+
                       |  (2) Tailscale tunnel (sifreli)
                       v
            +----------+-----------+
            |  Bu PC (klinik)      |   Tailscale: 100.x.x.x
            |  YazKlinik           |   waitress, https://127.0.0.1:5443
            +----------------------+
```

> **KVKK notu:** Hasta verisi internet uzerinden geciyor. Funnel/proxy mutlaka HTTPS
> ile yapilmali, login HER ZAMAN zorunlu olmali, brute-force koruma (fail2ban veya
> Tailscale ACL) onerilir. Public IP'yi paylasmayin.

---

## Server tarafi - 1 Eylul kez yapilacak ayar

Bu PR'da eklenen `yazklinik_remote_access.py` modulu Flask app'e ProxyFix middleware'i
takar; X-Forwarded-Host/Proto/For basliklarina guvenilir. **Yeni kod gerek yok**, sadece
sunucuyu yeniden baslat:

```powershell
# Eski instanci durdur
Stop-Process -Name python -Force -ErrorAction SilentlyContinue
Remove-Item "$env:LOCALAPPDATA\Temp\YazKlinik\locks\web_5443.lock" -ErrorAction SilentlyContinue
# Yeniden baslat
D:\YazKlinik_Final_D500\D500_BASLAT.bat
```

Server her response'a `X-YK-Server: D700` header'i ekler ve uzak istekleri tespit edip
`X-YK-Remote-Detected: 1` header'i koyar. Audit log'larda uzak istekler ayrica isaretlenir:

```
INFO yazklinik.remote: REMOTE GET /hasta/F123_... from=176.236.92.142 host=176.236.92.142 ua=Mozilla/...
```

### Trust derinligi (kac proxy var?)

Default: `x_for=1, x_proto=1, x_host=1, x_port=1` (tek reverse proxy).
Tailscale Funnel + nginx zinciri varsa 2:

```python
# yazklinik_web.py icinde register satirini:
_yk_register_remote(app, trust_x_for=2, trust_x_proto=2, trust_x_host=2, trust_x_port=2,
                    log_remote_requests=True)
```

---

## YONTEM A â€” Tailscale Funnel (en kolay, en guvenli)

Tailscale Funnel public HTTPS endpoint verir; subdomain otomatik yonetilir, sertifika
ucretsiz Let's Encrypt'tir. **Tek dezavantaji:** sadece 3 port acabilir (443 / 8443 / 10000).

### Adim 1 - Ikinci PC'de Tailscale kurulu mu?

Windows: https://tailscale.com/download/windows
macOS: `brew install tailscale`
Linux: `curl -fsSL https://tailscale.com/install.sh | sh`

Login: `tailscale up --accept-routes`

### Adim 2 - Funnel'i tailnet'te enable et

Tailscale admin paneli (https://login.tailscale.com/admin/dns) -> Settings -> Funnel
"Enable Funnel" tikla. ACL'de funnel iznini ver:

```json
"nodeAttrs": [
  { "target": ["autogroup:member"], "attr": ["funnel"] }
]
```

### Adim 3 - Bu PC'nin Tailscale IP/hostname'ini ogren

Bu PC'de:
```powershell
tailscale ip -4
# ornek: 100.115.42.18
tailscale status | Select-Object -First 1
# ornek: 100.115.42.18  dr-yaz-pc  yazhakan@  windows
```

Hostname'i not al: `dr-yaz-pc` (varsayim, sizin makinada ne ise o)

### Adim 4 - Ikinci PC'de Serve + Funnel config

Ikinci PC'de PowerShell admin acin:

```powershell
# Serve: bu PC'nin port 5443'unu ikinci PC'nin 8443'unde dinle
tailscale serve --bg --https=8443 https+insecure://dr-yaz-pc:5443

# Funnel'a tasi (public)
tailscale funnel --bg 8443

# Durum kontrol
tailscale serve status
tailscale funnel status
```

Ciktida `https://<ikinci-pc-hostname>.<tailnet>.ts.net` URL'i goreceksiniz. Bu adres
herkese ACIK ve Let's Encrypt sertifika ile HTTPS.

### Adim 5 - YazKlinik'i denemek

Tarayicidan `https://<funnel-url>` ac -> login sayfasi gelmeli (`doktor / 1234`).
Sertifika uyarisi gelmemeli (Tailscale Let's Encrypt halletti).

### Iptal

```powershell
tailscale funnel --bg off
tailscale serve reset
```

---

## YONTEM B â€” Router NAT + Caddy/Nginx (ozel port istiyorsaniz)

Sizin gibi `176.236.92.142:65187` ozel port istiyorsaniz Tailscale Funnel olmaz. Router'da
**port forwarding** ayarlayip ikinci PC'ye reverse proxy kurun.

### Adim 1 - Router'da port forward

`Public 65187 -> Ikinci PC LAN IP:8443` (ornek). Modeminizin web arayuzunden:
- Port Forwarding / Virtual Server
- Service: YazKlinik
- Outside Port: 65187
- Inside IP: ikinci PC'nin LAN IP'si (ipconfig ile bakin)
- Inside Port: 8443
- Protocol: TCP

### Adim 2 - Ikinci PC'de Caddy (onerilen, en kolay)

Caddy indir: https://caddyserver.com/download

`Caddyfile` (ikinci PC, c:\Caddy\Caddyfile):
```caddyfile
:8443 {
    # Self-signed kullaniyoruz cunku 176.236.92.142 IP'sine LE sertifika alinmaz
    tls internal
    reverse_proxy https://100.115.42.18:5443 {
        # Bu PC'nin Tailscale IP'si - dr-yaz-pc.ts.net hostnamesini de kullanabilirsiniz
        transport http {
            tls
            tls_insecure_skip_verify   # YazKlinik self-signed kullaniyor
        }
        header_up X-Forwarded-Host {host}
        header_up X-Forwarded-Proto https
        header_up X-Real-IP {remote}
    }
}
```

Caddy'yi servis olarak baslat:
```powershell
cd C:\Caddy
caddy run --config Caddyfile
# Servis yapmak icin: caddy.exe service install / start
```

### Adim 3 - Test

Tarayicidan `https://176.236.92.142:65187` ac. Sertifika uyarisi gelir (self-signed),
"Yine de devam et" ile gec. Login ekrani gelmeli.

### Alternatif - Nginx

`nginx.conf`:
```nginx
server {
    listen 8443 ssl;
    ssl_certificate     ssl/server.crt;   # kendi sertifikaniz
    ssl_certificate_key ssl/server.key;
    location / {
        proxy_pass https://100.115.42.18:5443;
        proxy_ssl_verify off;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Real-IP $remote_addr;
        # WebSocket destek (Alex voice, real-time)
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
}
```

---

## YONTEM C â€” Tailscale Funnel + ozel port (en gelismis)

Funnel sadece 443/8443/10000 destekler. Ozel port (65187) icin Cloudflare Tunnel
veya ngrok da kullanabilirsiniz; ama bunlar Tailscale ekosisteminin disinda.

### Cloudflare Tunnel ozet

```bash
# Ikinci PC'de
cloudflared tunnel create yazklinik
cloudflared tunnel route dns yazklinik yazklinik.ornek.com
# Config:
# tunnel: yazklinik
# credentials-file: ~/.cloudflared/...json
# ingress:
#   - hostname: yazklinik.ornek.com
#     service: https://100.115.42.18:5443
#     originRequest:
#       noTLSVerify: true
#   - service: http_status:404
cloudflared tunnel run yazklinik
```

Dezavantaj: bir Cloudflare hesabi ve domain gerekir.

---

## GUVENLIK CHECKLIST (KVKK + medikal etik)

| Onlem | Yapildi mi? | Aciklama |
|---|---|---|
| HTTPS zorunlu | [x] | YazKlinik zaten HTTPS (waitress + self-signed) |
| ProxyFix devrede | [x] | Bu PR ile eklendi (`yazklinik_remote_access.py`) |
| Guclu password | [ ] | Default `1234` -> hemen degistir (`/sifre-degistir`) |
| Brute-force koruma | [ ] | fail2ban veya nginx limit_req kullan |
| Login attempt log | [x] | Mevcut audit log Codex tarafindan eklendi |
| Tailscale ACL | [ ] | Sadece doktor cihazlari erisebilsin |
| Funnel uzerinde 2FA | [ ] | YazKlinik 2FA destekli mi ? login sayfasinda kontrol |
| IP whitelist | [opsiyonel] | Ek bir guvenlik katmani; cloudflare WAF veya nginx geo block |
| Audit log rotate | [x] | D500_health_monitor zaten yapiyor |
| Public IP gizli | [!] | Whatsapp/Instagram bio'larda paylasilmamali |

---

## SORUN GIDERME

### "Sertifika uyarisi cikiyor"
- Self-signed kullaniyorsaniz normal. Production icin Caddy `tls internal` yerine
  `tls your-email@example.com` ile Let's Encrypt; ama bunun icin domain gerek.

### "Sayfa acilmiyor, timeout"
1. `tailscale ping <hostname>` - Tailscale baglantisi var mi?
2. Bu PC'de `Test-NetConnection 127.0.0.1 -Port 5443` - YazKlinik calisiyor mu?
3. Router port-forward dogru mu? `Test-NetConnection 176.236.92.142 -Port 65187`
   (baska bir agdan)
4. Windows Defender Firewall ikinci PC'de 8443'u acmis mi?

### "Login sonrasi sayfa kayboluyor / 502"
- ProxyFix yanlis sayida hop trust ediyor. `trust_x_for=2` yapip yeniden baslat.

### "WebSocket / Alex ses calismiyor"
- Reverse proxy WebSocket'i forward etmiyor. Nginx config'inde `proxy_http_version 1.1`
  ve `Upgrade` header'lari MUTLAK gerekli.

### "Audit log'larda her istek 'remote' gozukuyor"
- `LOCAL_PREFIXES_DEFAULT` listesinde sizin LAN aralidi yok. Ornek 192.168.x.x degil
  172.30.x.x ise zaten kapsiyor. Ozel bir aralik varsa
  `_yk_register_remote(app, extra_local_prefixes=("172.16.5.",))` ile gec.

---

## ZAMANLAMA / ICINDE ALDIGI ZAMAN

| Adim | Sure |
|---|---|
| YazKlinik kod (zaten yapildi) | 0 |
| Tailscale kurulumu ikinci PC | 5 dk |
| Tailscale Funnel enable + serve config | 10 dk |
| Caddy kurulumu + config (alternatif) | 15 dk |
| Router port-forward (alternatif) | 5 dk |
| Test + ilk login | 5 dk |
| **Toplam** | **20-40 dk** |

---

## EK - HIZLI BASLATMA SCRIPTI (ikinci PC icin)

`C:\YazKlinik_Funnel_Baslat.bat`:
```batch
@echo off
echo YazKlinik Funnel baslaniyor...
tailscale serve --bg --https=8443 https+insecure://dr-yaz-pc:5443
if errorlevel 1 (
    echo HATA: Tailscale serve baslamadi. Once 'tailscale up' calistirin.
    pause
    exit /b 1
)
tailscale funnel --bg 8443
echo.
echo BAGLANTI ADRESLERI:
tailscale funnel status
echo.
echo Funnel aktif. Kapatmak icin: tailscale funnel --bg off
pause
```

---

*Hazirlayan: Claude. Op. Dr. Hakan Yaz'in talebi uzerine 2026-05-16.*

