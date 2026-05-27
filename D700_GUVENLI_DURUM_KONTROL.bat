@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "ARGS=-StopRisky -RepairConfig -StrictManagedOwnerOff -PersistManagedOwnerOff -RepairPortal -RequirePortal"
if /I "%~1"=="status" (
  set "ARGS="
) else if /I "%~1"=="--status" (
  set "ARGS="
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0D700_GUVENLI_DURUM_KONTROL.ps1" %ARGS%
exit /b %ERRORLEVEL%
