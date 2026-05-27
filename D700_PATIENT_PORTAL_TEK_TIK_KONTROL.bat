@echo off
setlocal
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [D700] 1/2 - Genel sistem kontrolu (CODEX_QUICK_CHECK.py)
"%PY%" "%~dp0CODEX_QUICK_CHECK.py"
if errorlevel 1 goto :fail

echo.
echo [D700] 2/2 - Hasta portal ayrim kontrolu (D700_PATIENT_PORTAL_SPLIT_CHECK.py)
"%PY%" "%~dp0D700_PATIENT_PORTAL_SPLIT_CHECK.py" %*
if errorlevel 1 goto :fail

echo.
echo [OK] D700 ana sistem + hasta portal ayrimi kontrolu gecti.
exit /b 0

:fail
echo.
echo [HATA] Kontrol zinciri hata verdi. Ustteki FAIL/HATA satirlarini inceleyin.
exit /b 1
