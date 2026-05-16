# Jitsi Meet — YazKlinik Video Konsultasyon

Hastayla **HTTPS uzerinden video gorusme**, ekran paylasimi, kayit. Self-host =
hicbir 3. taraf sunucudan gecmez (KVKK uyumlu).

## Hizli baslatma (Tailscale Funnel arkasinda)

```powershell
cd D:\YazKlinik_Final_D300\akillilik\jitsi

# 1. docker-jitsi-meet config indir
git clone https://github.com/jitsi/docker-jitsi-meet . 2>$null
git checkout stable-9893

# 2. .env hazirla
Copy-Item env.example .env
# .env duzenle:
#   PUBLIC_URL=https://<ikinci-pc>.<tailnet>.ts.net   (Tailscale Funnel URL)
#   ENABLE_LETSENCRYPT=1
#   LETSENCRYPT_EMAIL=anil@ucandoktor.com
#   LETSENCRYPT_DOMAIN=<ayni-funnel-host>

# 3. CONFIG dizinleri olustur
.\gen-passwords.sh   # bash gerek; alternatif: PowerShell ile manuel parola

# 4. Calistir
docker compose up -d

# 5. Test: PUBLIC_URL'ine git, oda olustur (orn https://.../yk-konsult-001)
# Hastaya link gonder, gelir, sesli+gorseli baglanir.
```

## YazKlinik entegrasyonu

Konsultasyon ajani veya hasta dosyasinda "Video oda olustur" butonu:
```python
import uuid
room = f"yk-{uuid.uuid4().hex[:8]}"
link = f"{JITSI_PUBLIC_URL}/{room}"
# Hastaya WhatsApp/SMS ile gonder
```

## KVKK / Guvenlik

- Self-host -> hicbir uydu sunucu yok
- E2EE varsayilan kapali; ayar: `XMPP_ENABLE_E2E_ENCRYPTION=1`
- Oda parolasi: oda olusturunca ayarla
- Kayit: Jibri container (opsiyonel, ek 4 GB RAM)
- ACL: meet.jit.si tarzi public access default; **Authentication** ekle:
  `ENABLE_AUTH=1`, `AUTH_TYPE=internal` ve `prosodyctl register` ile hasta hesap

## Manuel kurulum tercih edilen sebep

Jitsi 8+ container'lik karmasik bir stack (prosody, jicofo, jvb, web, jibri).
LE sertifika icin gercek domain veya Tailscale Funnel hostname gerek. Bu
yuzden tek dokunusla kurmak yerine `docker-jitsi-meet` resmi reposunu clone
edip kendi config'ini yapmak guvenli.

Alternatif: Resmi `https://meet.jit.si` (3. taraf ama ucretsiz, ozellik kisitli).

---

*Hazirlik: 15-30 dk + Tailscale Funnel domain*
