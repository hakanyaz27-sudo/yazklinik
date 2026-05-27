@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0D700_TAILSCALE_TUNNEL_ONAR.ps1"
echo.
pause
