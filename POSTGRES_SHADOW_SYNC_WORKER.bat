@echo off
setlocal
cd /d "%~dp0"

if not exist "runtime_state\postgres_shadow_sync" mkdir "runtime_state\postgres_shadow_sync"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

echo [%DATE% %TIME%] PostgreSQL shadow sync started > "runtime_state\postgres_shadow_sync\scheduled_last.log"
"%PY%" YAZKLINIK_POSTGRES_SHADOW_SYNC.py --deep --json >> "runtime_state\postgres_shadow_sync\scheduled_last.log" 2>> "runtime_state\postgres_shadow_sync\scheduled_last_error.log"
set "RC=%ERRORLEVEL%"
echo [%DATE% %TIME%] PostgreSQL shadow sync finished rc=%RC% >> "runtime_state\postgres_shadow_sync\scheduled_last.log"
exit /b %RC%
