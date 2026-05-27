@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" "%~dp0YAZKLINIK_DB_GUARD.py" --repair --keep-backups 21
echo.
echo Rapor: %~dp0runtime_state\db_guard\last_report.txt
pause
