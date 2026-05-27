@echo off
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" "YAZKLINIK_POSTGRES_RESILIENCE_CHECK.py" %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo.
  echo [UYARI] PostgreSQL resilience check FAIL.
)
exit /b %RC%
