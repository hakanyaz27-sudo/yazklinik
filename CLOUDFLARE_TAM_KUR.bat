@echo off
setlocal
cd /d "%~dp0"
echo.
echo YazKlinik Cloudflare Worker + Bakim kurulumu
echo Token yoksa PowerShell guvenli sekilde soracak; ekranda gorunmez.
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0CLOUDFLARE_TAM_KUR.ps1"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  echo CLOUDFLARE_TAM_KUR_OK
) else (
  echo CLOUDFLARE_TAM_KUR_HATA ExitCode=%RC%
)
echo.
pause
exit /b %RC%
