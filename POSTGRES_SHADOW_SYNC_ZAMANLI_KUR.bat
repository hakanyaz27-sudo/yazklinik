@echo off
setlocal
cd /d "%~dp0"

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0POSTGRES_SHADOW_SYNC_ZAMANLI_KUR.ps1" -IntervalMinutes 60 -RunNow
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo OK: PostgreSQL shadow sync scheduled task kuruldu.
) else (
  echo HATA: Scheduled task kurulamadi.
)
echo.
pause
exit /b %RC%
