@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

if exist "config.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in ("config.env") do (
    if not "%%~a"=="" if not "%%~b"=="" set "%%a=%%b"
  )
)

if not defined YAZKLINIK_WEB_PORT set "YAZKLINIK_WEB_PORT=5052"
if not defined YAZKLINIK_HTTPS_PORT set "YAZKLINIK_HTTPS_PORT=5443"
if not defined YAZKLINIK_CADDY_ACCEL set "YAZKLINIK_CADDY_ACCEL=1"

set "PYW=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYW%" (
  echo [ERR] pythonw bulunamadi: %PYW%
  exit /b 1
)

echo [INFO] User-level web restart basliyor...

for %%P in (%YAZKLINIK_WEB_PORT% %YAZKLINIK_HTTPS_PORT% 5052 5443) do (
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%P " ^| findstr "LISTENING"') do (
    taskkill /F /PID %%a >nul 2>&1
  )
)

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$root=(Resolve-Path '%~dp0').Path; " ^
  "$tempLocks=Join-Path $env:TEMP 'YazKlinik\locks'; " ^
  "Remove-Item -LiteralPath (Join-Path $tempLocks 'web_5052.lock') -Force -ErrorAction SilentlyContinue; " ^
  "Remove-Item -LiteralPath (Join-Path $tempLocks 'web_5443.lock') -Force -ErrorAction SilentlyContinue; " ^
  "$svcLock=Join-Path $root 'runtime_state\service_locks\yazklinik_web.lock'; " ^
  "if(Test-Path -LiteralPath $svcLock){ " ^
  "  $pid=0; try{$line=Get-Content -LiteralPath $svcLock -ErrorAction Stop | Select-Object -First 1; [int]::TryParse([string]$line,[ref]$pid)|Out-Null}catch{}; " ^
  "  if($pid -le 0 -or -not (Get-Process -Id $pid -ErrorAction SilentlyContinue)){ Remove-Item -LiteralPath $svcLock -Force -ErrorAction SilentlyContinue } " ^
  "}" >nul 2>&1

start "" "%PYW%" "%~dp0D700_SERVICE_RUNNER.py" "%~dp0yazklinik_web.py" "%~dp0D700_server.log" "%~dp0D700_server_HATA.log"
if /I "%YAZKLINIK_CADDY_ACCEL%"=="1" if exist "%~dp0D700_CADDY_ACCEL_BASLAT.ps1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0D700_CADDY_ACCEL_BASLAT.ps1" >nul 2>&1
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 5" >nul 2>&1
echo [OK] User-level web restart tetiklendi.
exit /b 0

