@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0D700_PATIENT_PORTAL_BASLAT.ps1" %*
