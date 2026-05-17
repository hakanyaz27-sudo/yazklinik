@echo off
REM YazKlinik DB Migration - Session 7 tablolari (audit_log, consent, 2fa, vs)
REM Kullanim: cift tikla veya .\RUN_DB_MIGRATE.bat
REM Idempotent - kac kez calistirilsa bozulmaz.

setlocal
cd /d "%~dp0"

set PY=D:\YazKlinik_Final_D300\.venv\Scripts\python.exe
if not exist "%PY%" set PY=C:\Users\yazha\AppData\Local\Programs\Python\Python312\python.exe

echo.
echo === YazKlinik DB Migration ===
echo.

"%PY%" yazklinik_db_migrate_agent.py

echo.
echo Bitti. Pencereyi kapatabilirsiniz.
pause
