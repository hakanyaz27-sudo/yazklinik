@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0D700_CADDY_ACCEL_BASLAT.ps1" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo [HATA] Caddy accel baslatma basarisiz. Kod=%RC%
  pause
)
exit /b %RC%
