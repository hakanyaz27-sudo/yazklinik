@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title YazKlinik Whisper Mikroservisi (port 9000)
cd /d "%~dp0"

REM YazKlinik web ana app'inden BAGIMSIZ Whisper transcribe servisi.
REM Werkzeug threading + faster-whisper deadlock'undan kacinmak icin gerekli.
REM Yazklinik ana server bu URL'e HTTP istek atar.

REM config.env'i oku (model/device/compute config.env'den gelir)
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
)

if not defined YAZKLINIK_WHISPER_SERVICE_PORT set "YAZKLINIK_WHISPER_SERVICE_PORT=9000"
if not defined YAZKLINIK_WHISPER_MODEL set "YAZKLINIK_WHISPER_MODEL=small"
if not defined YAZKLINIK_WHISPER_DEVICE set "YAZKLINIK_WHISPER_DEVICE=cpu"
if not defined YAZKLINIK_WHISPER_COMPUTE_TYPE set "YAZKLINIK_WHISPER_COMPUTE_TYPE=int8"
set "HF_HUB_OFFLINE=1"
set "TRANSFORMERS_OFFLINE=1"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

REM Venv yolu: once D300 yerli, sonra eski D104 (fallback)
set "VENV_PATH="
if exist "%~dp0.venv\Scripts\python.exe" (
  set "VENV_PATH=%~dp0.venv"
) else if exist "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" (
  set "VENV_PATH=C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv"
)
if not defined VENV_PATH (
  echo .venv bulunamadi
  pause
  exit /b 1
)

echo.
echo ============================================================
echo  YazKlinik Whisper Mikroservisi
echo  Port    : %YAZKLINIK_WHISPER_SERVICE_PORT%
echo  Model   : %YAZKLINIK_WHISPER_MODEL%
echo  Device  : %YAZKLINIK_WHISPER_DEVICE%
echo  Compute : %YAZKLINIK_WHISPER_COMPUTE_TYPE%
echo  Venv    : %VENV_PATH%
echo ============================================================
echo.

"%VENV_PATH%\Scripts\python.exe" -u yazklinik_whisper_service.py
pause
