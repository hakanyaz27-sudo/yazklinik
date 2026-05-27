@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

if not exist "runtime_state\db_guard" mkdir "runtime_state\db_guard" >nul 2>&1
set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [%date% %time%] DB Guard daily start>> "%~dp0runtime_state\db_guard\daily.log"
"%PY%" "%~dp0YAZKLINIK_DB_GUARD.py" --repair --keep-backups 30 >> "%~dp0runtime_state\db_guard\daily.log" 2>&1
if errorlevel 1 (
  exit /b 1
)
exit /b 0
