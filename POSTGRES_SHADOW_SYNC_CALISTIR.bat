@echo off
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo PostgreSQL shadow mirror guncelleniyor...
"%PY%" YAZKLINIK_POSTGRES_SHADOW_SYNC.py --deep
set "RC=%ERRORLEVEL%"

echo.
if "%RC%"=="0" (
  echo OK: Shadow PostgreSQL mirror hazir.
) else (
  echo HATA: Shadow sync tamamlanamadi. Yukaridaki rapora bakin.
)
echo.
pause
exit /b %RC%
