# PC'deki Codex/Claude Code'u Uzaktan Yonetme

> Telefon, tablet veya baska bir bilgisayardan PC'ndeki AI assistant'ina baglan.

## Karar Tablosu

| Yontem | Ne Icin | Kurulum | Hiz |
|---|---|---|---|
| **1. RDP + Tailscale** â˜… | Tam masaustu, gercek deneyim | 10 dk | Cok iyi |
| **2. SSH + Termius** | Sadece terminal/Codex | 15 dk | Cok hizli |
| **3. Web Terminal (ttyd)** | Tarayicidan terminal | 10 dk | Iyi |
| **4. AnyDesk / RustDesk** | Tam masaustu, kurulum kolay | 5 dk | Iyi |

---

## YOL 1: RDP + Tailscale (en onerilen) â˜…

### Adim 1: PC'de RDP'yi ac

PowerShell **Yonetici olarak** ac:

```powershell
# RDP'yi etkinlestir
Set-ItemProperty -Path "HKLM:\System\CurrentControlSet\Control\Terminal Server" `
  -Name "fDenyTSConnections" -Value 0

# Network Level Authentication
Set-ItemProperty -Path "HKLM:\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp" `
  -Name "UserAuthentication" -Value 1

# Firewall RDP izin ver
Enable-NetFirewallRule -DisplayGroup "Remote Desktop"

Write-Output "RDP aktif. Port: 3389"
```

### Adim 2: Tailscale kur (PC + telefon)

PC:
1. https://tailscale.com/download/windows -> indir + kur
2. Tailscale ikonuna tikla -> Microsoft/Google ile login
3. **PC'nin Tailscale IP'sini ogren** (orn. `100.71.108.26`)

Telefon:
1. Play Store / App Store -> **"Tailscale"** kur
2. Ayni hesapla login

### Adim 3: Microsoft RDP uygulamasi (telefon)

1. Play Store: **"Microsoft Remote Desktop"** (Microsoft Corp.)
2. iOS: App Store -> ayni isim
3. Yeni baglanti ekle:
   - **PC adresi**: Tailscale IP (`100.71.108.26`) veya LAN IP (`192.168.1.40`)
   - **Kullanici**: Windows kullanici adi (orn. `hp` veya `yazha`)
   - **Sifre**: Windows sifresi
4. Bagla -> tam Windows masaustun acilir

### Adim 4: Codex/Claude Code calistir

PC'de RDP ile baglandiktan sonra:

**Windows Terminal'i ac**:
- Win + R -> `wt` Enter
- Codex calistir:
  ```
  cd D:\YazKlinik_Final_D250
  codex
  ```
- Veya Claude Code:
  ```
  cd D:\YazKlinik_Final_D250
  claude
  ```

Mouse/keyboard ile telefonda komut yazarsin, AI cevap verir, kod degisiklikleri yapar.

---

## YOL 2: SSH + Termius (sadece terminal) - HIZLI

### Adim 1: Windows OpenSSH Server'i kur

PowerShell **Yonetici**:

```powershell
# OpenSSH Server kur
Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0

# Servis baslat + her bootta otomatik
Start-Service sshd
Set-Service -Name sshd -StartupType 'Automatic'

# Firewall
New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' `
  -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22

Write-Output "SSH aktif - port 22"
```

### Adim 2: Telefonda Termius (ya da Blink Shell)

1. Play Store: **"Termius"** (hosts/keys yonetimi var)
2. Yeni Host ekle:
   - **Hostname**: `100.71.108.26` (Tailscale) veya LAN IP
   - **Port**: `22`
   - **Username**: Windows kullanici (`hp`)
   - **Password**: Windows sifresi
3. Bagla -> PowerShell prompt acilir

### Adim 3: tmux ile session koru (Codex kapanmasin)

PC'de bir kez:
```powershell
# tmux Windows icin: WSL veya Git Bash gerekli
# Veya screen alternatifi
# Direkt PowerShell de calisir, ama baglanti kopunca Codex de kapanir
```

**En basit**: tmux yerine Codex'i sadece SSH icinde calistir:
```bash
ssh hp@100.71.108.26
cd /d/YazKlinik_Final_D250   # veya cd D:\YazKlinik_Final_D250
codex
```

Bagli kaldigin surece Codex calisir.

---

## YOL 3: Web Terminal (ttyd / wetty)

### Adim 1: ttyd kur

```powershell
# winget ile (Windows 11 var)
winget install tsl0922.ttyd

# Veya manuel: https://github.com/tsl0922/ttyd/releases
```

### Adim 2: ttyd baslat (PowerShell ile)

```powershell
ttyd -p 7681 -W powershell.exe
```

`-W` -> writable mode (yazma izinli)

### Adim 3: Telefondan tarayici ile ac

```
http://100.71.108.26:7681
```

(Tailscale IP varsa internetten de erisilir)

> Tarayici icinde tam terminal acilir, Codex calistirabilirsin.

---

## YOL 4: AnyDesk veya RustDesk (en kolay, kurulum 5 dk)

### Avantaji

- Hesap yok, sadece **9 haneli ID** ile bagli
- Telefonda native uygulama
- Mouse/keyboard direkt calisir
- Ses + dosya transferi var

### AnyDesk (kisisel ucretsiz)

1. PC: https://anydesk.com -> indir + kur
2. Acilinca **9 haneli ID** gosterilir (orn. `123456789`)
3. Telefonda Play Store: **"AnyDesk"**
4. ID'yi gir + Bagla -> PC'de izin ver
5. Tam masaustu telefonda

### RustDesk (open source, ucretsiz)

Tamamen aynisi. https://rustdesk.com

---

## Codex Workflow Karsilastirma

| Senaryo | Onerilen yontem |
|---|---|
| **Hizli kod check** (Codex sor + cevap al) | YOL 2 (SSH/Termius) |
| **Karmasik debug** (mouse/multi-window) | YOL 1 (RDP) veya YOL 4 (AnyDesk) |
| **Internet zayif** | YOL 2 (SSH text-only) |
| **Birden fazla cihaz** | YOL 1 (RDP - cunku tek session) |

---

## D700 Sistem Icin Hazir Komutlar (uzaktan baglandiktan sonra)

### Sistem durum check
```powershell
cd D:\YazKlinik_Final_D250
python CODEX_QUICK_CHECK.py
```

### Server kontrol
```powershell
# Calisiyor mu
Get-NetTCPConnection -LocalPort 5052 | Select OwningProcess, State

# Restart
.\D250_BASLAT.bat
```

### Codex CLI baslat
```powershell
cd D:\YazKlinik_Final_D250
codex
```

Codex `AGENTS.md`'i otomatik okur, baglanir.

### Claude Code (eger kurulu ise)
```powershell
cd D:\YazKlinik_Final_D250
claude
```

### Log oku (devam eden)
```powershell
Get-Content D250_server.log -Tail 30 -Wait
```

---

## Guvenlik Notlari

- **RDP** sadece Tailscale veya VPN icinde kullan, internete acmĞ°
- **SSH** Tailscale ile sandboxla, public internete acmĞ°
- **AnyDesk/RustDesk** parola koy + her seferinde manuel onay aktif et
- **Tailscale** bir VPN, internetten guvenli, iki yana acÄ±lÄ±
- **PC sifresi guclu** olsun (RDP cracker'i icin)

---

## En Hizli Onerim

```
1. Tailscale kur (PC + telefon, 5 dk)
2. RDP'yi ac (yukaridaki PowerShell, 1 dk)
3. Telefonda Microsoft Remote Desktop kur
4. Bagla -> Codex'i acabildigin Windows masaustu telefonda
```

Toplam **10 dakika**, sonra her zaman telefondan PC'ndeki Codex'e/Claude Code'a tam erisim.

---
**D700** | **Op. Dr. Hakan YAZ** | **2026-05-10**

