@echo off
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo [YazKlinik] PostgreSQL tam mirror basliyor...
echo.
"%PY%" "%~dp0YAZKLINIK_POSTGRES_FULL_MIGRATE.py" --apply --yes
if errorlevel 1 (
  echo.
  echo [HATA] Mirror tamamlanamadi.
  pause
  exit /b 1
)
echo.
echo [YazKlinik] Satir sayisi dogrulaniyor...
"%PY%" "%~dp0YAZKLINIK_POSTGRES_FULL_MIGRATE.py" --compare
echo.
pause
