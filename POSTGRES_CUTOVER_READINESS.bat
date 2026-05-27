@echo off
setlocal
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
echo [YazKlinik] PostgreSQL cutover readiness kontrolu...
echo.
"%PY%" "%~dp0YAZKLINIK_POSTGRES_CUTOVER_READINESS.py" --deep
echo.
pause
