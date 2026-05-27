@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" YAZKLINIK_SYSTEM_CAPABILITY_AUDIT.py
) else (
  python YAZKLINIK_SYSTEM_CAPABILITY_AUDIT.py
)
pause
