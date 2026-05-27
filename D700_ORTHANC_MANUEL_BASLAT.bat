@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "QUIET=0"
set "MODE=start"
for %%A in (%*) do (
  if /I "%%~A"=="/silent" set "QUIET=1"
  if /I "%%~A"=="/autostart" set "QUIET=1"
  if /I "%%~A"=="/status" set "MODE=status"
  if /I "%%~A"=="/stop" set "MODE=stop"
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0D700_ORTHANC_MANUEL_BASLAT.ps1" -Mode "%MODE%" -Quiet %QUIET%
exit /b %errorlevel%

