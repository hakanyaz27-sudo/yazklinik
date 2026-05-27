@echo off
setlocal
cd /d "%~dp0"
set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" D700_PERF_AUDIT.py --repeat 3 --timeout 10
echo.
echo Baseline raporu runtime_state\perf altina yazildi.
pause
