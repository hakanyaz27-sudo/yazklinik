@echo off
setlocal
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"

"%PY%" YAZKLINIK_SQL_DIALECT_CHECK.py
echo.
pause
