@echo off
chcp 65001 >nul
title YazKlinik D700 - Uzaktan Erisim Kurulum
cd /d "%~dp0"
cls

REM Yonetici modunu kontrol et
net session >nul 2>&1
if errorlevel 1 (
  echo.
  echo  ============================================================
  echo   HATA: Bu script YONETICI olarak calistirilmali!
  echo  ============================================================
  echo.
  echo  Cozum: Bu BAT dosyasinin uzerine sag tikla -^>
  echo         "Yonetici olarak calistir"
  echo.
  pause
  exit /b 1
)

echo.
echo  ============================================================
echo   YazKlinik D700 - Uzaktan Erisim Kurulum
echo  ============================================================
echo.
echo  Bu script su 3 servisi acar:
echo    1. Windows RDP (Remote Desktop) - port 3389
echo    2. Windows OpenSSH Server      - port 22
echo    3. Firewall kurallari
echo.
echo  SONUC: Telefondan Microsoft Remote Desktop veya
echo         Termius (SSH) ile baglanabilirsiniz.
echo.
echo  Devam? (Ctrl+C iptal)
pause >nul

echo.
echo  [1/4] RDP aciliyor...
powershell -NoProfile -Command "Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server' -Name 'fDenyTSConnections' -Value 0; Set-ItemProperty -Path 'HKLM:\System\CurrentControlSet\Control\Terminal Server\WinStations\RDP-Tcp' -Name 'UserAuthentication' -Value 1; Enable-NetFirewallRule -DisplayGroup 'Remote Desktop'; Write-Output 'RDP OK'"

echo.
echo  [2/4] OpenSSH Server kuruluyor (3-5 dk surebilir)...
powershell -NoProfile -Command "Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 -ErrorAction SilentlyContinue | Out-Null; Write-Output 'OpenSSH paketi OK'"

echo.
echo  [3/4] SSH servisi baslatiliyor + otomatik baslat...
powershell -NoProfile -Command "Start-Service sshd -ErrorAction SilentlyContinue; Set-Service -Name sshd -StartupType 'Automatic' -ErrorAction SilentlyContinue; Write-Output 'sshd OK'"

echo.
echo  [4/4] Firewall: SSH ve RDP icin allow...
powershell -NoProfile -Command "New-NetFirewallRule -Name sshd -DisplayName 'OpenSSH Server (sshd)' -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 -ErrorAction SilentlyContinue | Out-Null; Write-Output 'Firewall OK'"

echo.
echo  ============================================================
echo                       KURULUM BITTI
echo  ============================================================
echo.
echo  PC bilgileri:
echo  ----------------------------------------------------------------
powershell -NoProfile -Command "$wmi = Get-CimInstance Win32_ComputerSystem; Write-Output ('  PC adi    : ' + $wmi.Name); Write-Output ('  Kullanici : ' + $env:USERNAME)"

echo.
echo  Network adresleri:
powershell -NoProfile -Command "Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.PrefixOrigin -eq 'Dhcp' -or $_.IPAddress -like '192.168.*' -or $_.IPAddress -like '100.*' } | Select-Object IPAddress, InterfaceAlias | Format-Table -AutoSize"

echo.
echo  Telefondan baglanmak icin:
echo  ----------------------------------------------------------------
echo.
echo   A^) RDP (tam masaustu, mouse+keyboard):
echo       1. Telefonda "Microsoft Remote Desktop" uygulamasini kur
echo       2. Yeni baglanti -^> PC adresi: 192.168.1.40 (LAN'da)
echo                          veya Tailscale IP (internetten)
echo       3. Username: %USERNAME%
echo       4. Bagla -^> Windows masaustun telefonda
echo.
echo   B^) SSH (sadece terminal, hizli):
echo       1. Telefonda "Termius" uygulamasini kur
echo       2. Yeni Host -^> Hostname: 192.168.1.40
echo                       Port    : 22
echo                       User    : %USERNAME%
echo       3. Bagla -^> PowerShell prompt
echo.
echo   C^) Internetten: Tailscale kur (https://tailscale.com)
echo       PC + telefon ayni hesapla baglandiktan sonra,
echo       PC'nin Tailscale IP'sini kullan.
echo.
echo  ============================================================
echo  Detayli rehber: D:\YazKlinik_Final_D250\UZAKTAN_KONTROL_REHBER.md
echo  ============================================================
echo.
pause

