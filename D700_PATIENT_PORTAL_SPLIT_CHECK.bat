@echo off
setlocal
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [D700] Hasta Portal ayrim kontrolu basliyor...
"%PY%" "%~dp0D700_PATIENT_PORTAL_SPLIT_CHECK.py" %*
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" (
  echo.
  echo [OK] Hasta Portal ayrimi saglam.
) else (
  echo.
  echo [HATA] Hasta Portal ayrim kontrolu gecemedi. Ustteki FAIL satirlarini inceleyin.
)

exit /b %RC%
