@echo off
setlocal
cd /d "%~dp0"
echo D700 Tailscale kalicilastirma yonetici yetkisi isteyecek...
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell.exe -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%~dp0D700_TAILSCALE_TUNNEL_ONAR.ps1"" -AdminFix'"
