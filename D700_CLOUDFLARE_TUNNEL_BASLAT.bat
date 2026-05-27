@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0D700_CLOUDFLARE_TUNNEL_BASLAT.ps1" %*
exit /b %ERRORLEVEL%
