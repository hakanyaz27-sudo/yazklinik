@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title YazKlinik D300 - Alex SIP Dahili 19
cd /d "%~dp0"

echo.
echo  ============================================================
echo              YazKlinik D300 - Alex SIP Dahili
echo  ============================================================
echo.

if exist "config.env" (
  for /f "usebackq tokens=1,* delims==" %%a in ("config.env") do (
    set "_LINE=%%a"
    setlocal enabledelayedexpansion
    set "_FIRST=!_LINE:~0,1!"
    if not "!_FIRST!"=="#" if not "!_LINE!"=="" (
      endlocal
      set "%%a=%%b"
    ) else (
      endlocal
    )
  )
) else (
  echo  [!] config.env bulunamadi.
)

set "VENV_PATH="
if exist "%~dp0.venv\Scripts\python.exe" (
  set "VENV_PATH=%~dp0.venv"
) else if exist "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" (
  set "VENV_PATH=C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv"
) else (
  echo  [HATA] Python venv bulunamadi.
  pause
  exit /b 1
)

if not defined YAZKLINIK_SIP_ENABLED set "YAZKLINIK_SIP_ENABLED=1"
if not defined YAZKLINIK_SIP_PBX_HOST set "YAZKLINIK_SIP_PBX_HOST=192.168.1.250"
if not defined YAZKLINIK_SIP_EXTENSION set "YAZKLINIK_SIP_EXTENSION=19"
if not defined YAZKLINIK_SIP_LOCAL_PORT set "YAZKLINIK_SIP_LOCAL_PORT=5079"
if not defined YAZKLINIK_SIP_CONTROL_PORT set "YAZKLINIK_SIP_CONTROL_PORT=9019"

if not defined YAZKLINIK_SIP_PASSWORD (
  echo  [HATA] YAZKLINIK_SIP_PASSWORD config.env icinde yok.
  echo  Gercek sifreyi bu ekrana yazmayin; config.env'e lokal olarak ekleyin.
  pause
  exit /b 1
)

echo  [+] PBX       : %YAZKLINIK_SIP_PBX_HOST%:%YAZKLINIK_SIP_PBX_PORT%
echo  [+] Dahili    : %YAZKLINIK_SIP_EXTENSION%
echo  [+] Kontrol   : http://127.0.0.1:%YAZKLINIK_SIP_CONTROL_PORT%/status
echo  [+] Log       : D300_sip_alex.log
echo.

"%VENV_PATH%\Scripts\python.exe" -u "%~dp0yazklinik_sip_alex_client.py" 1>"%~dp0D300_sip_alex.log" 2>&1

echo.
echo  Alex SIP servisi kapandi. Son log:
powershell -NoProfile -Command "Get-Content '%~dp0D300_sip_alex.log' -Tail 25 -ErrorAction SilentlyContinue"
echo.
pause
