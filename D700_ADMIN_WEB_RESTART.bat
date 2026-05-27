@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
cd /d "%~dp0"
set "D700_LOCK_ACQUIRED=0"
set "D700_EXIT_CODE=0"

net session >nul 2>&1
if errorlevel 1 (
  if /I "%YAZKLINIK_ADMIN_RESTART_AUTO_ELEVATE%"=="1" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
  )
  echo  [HATA] Yonetici yetkisi gerekiyor. Lutfen script'i Run as administrator ile acin.
  echo      ^(Oto-yukseltme icin: set YAZKLINIK_ADMIN_RESTART_AUTO_ELEVATE=1^)
  set "D700_EXIT_CODE=5"
  goto :admin_exit
)

echo.
echo  YazKlinik D700 web servisi yonetici modunda yeniden baslatiliyor...
echo  Klasor: %CD%
echo.

if exist "config.env" (
  for /f "usebackq eol=# tokens=1,* delims==" %%a in ("config.env") do (
    if not "%%~a"=="" if not "%%~b"=="" set "%%a=%%b"
  )
)

if not defined YAZKLINIK_WEB_PORT set "YAZKLINIK_WEB_PORT=5052"
if not defined YAZKLINIK_HTTPS_PORT set "YAZKLINIK_HTTPS_PORT=5443"
if not defined YAZKLINIK_CADDY_ACCEL set "YAZKLINIK_CADDY_ACCEL=1"
if not defined YAZKLINIK_CADDY_HTTPS_PORT set "YAZKLINIK_CADDY_HTTPS_PORT=5443"
if not defined YAZKLINIK_WAITRESS_THREADS set "YAZKLINIK_WAITRESS_THREADS=12"
if not defined YAZKLINIK_ADMIN_RESTART_POSTCHECK set "YAZKLINIK_ADMIN_RESTART_POSTCHECK=0"
if not defined YAZKLINIK_ADMIN_RESTART_MIN_INTERVAL_SEC set "YAZKLINIK_ADMIN_RESTART_MIN_INTERVAL_SEC=300"
if not defined YAZKLINIK_ADMIN_RESTART_FORCE set "YAZKLINIK_ADMIN_RESTART_FORCE=0"
set "YAZKLINIK_WAITRESS_THREADS_RAW=%YAZKLINIK_WAITRESS_THREADS%"
for /f "delims=0123456789" %%x in ("%YAZKLINIK_WAITRESS_THREADS_RAW%") do set "YAZKLINIK_WAITRESS_THREADS=12"
if %YAZKLINIK_WAITRESS_THREADS% LSS 12 set "YAZKLINIK_WAITRESS_THREADS=12"
for /f "delims=0123456789" %%x in ("%YAZKLINIK_ADMIN_RESTART_MIN_INTERVAL_SEC%") do set "YAZKLINIK_ADMIN_RESTART_MIN_INTERVAL_SEC=300"
if %YAZKLINIK_ADMIN_RESTART_MIN_INTERVAL_SEC% LSS 60 set "YAZKLINIK_ADMIN_RESTART_MIN_INTERVAL_SEC=60"

set "D700_ADMIN_STATE_DIR=%~dp0runtime_state\maintenance_logs"
if not exist "%D700_ADMIN_STATE_DIR%" mkdir "%D700_ADMIN_STATE_DIR%" >nul 2>&1
set "D700_ADMIN_RESTART_STAMP=%D700_ADMIN_STATE_DIR%\admin_web_restart.last"
set "D700_ADMIN_RESTART_LOCK_DIR=%D700_ADMIN_STATE_DIR%\admin_web_restart.lockdir"

if /I not "%YAZKLINIK_ADMIN_RESTART_FORCE%"=="1" (
  set "D700_ADMIN_RESTART_SINCE=-1"
  for /f "usebackq delims=" %%S in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$f='%D700_ADMIN_RESTART_STAMP%'; if(Test-Path -LiteralPath $f){ [int][Math]::Floor(((Get-Date)-(Get-Item -LiteralPath $f).LastWriteTime).TotalSeconds) } else { -1 }"`) do set "D700_ADMIN_RESTART_SINCE=%%S"
  for /f "delims=0123456789-" %%x in ("!D700_ADMIN_RESTART_SINCE!") do set "D700_ADMIN_RESTART_SINCE=-1"
  if !D700_ADMIN_RESTART_SINCE! GEQ 0 if !D700_ADMIN_RESTART_SINCE! LSS %YAZKLINIK_ADMIN_RESTART_MIN_INTERVAL_SEC% (
    set /a D700_WAIT_LEFT=%YAZKLINIK_ADMIN_RESTART_MIN_INTERVAL_SEC%-!D700_ADMIN_RESTART_SINCE!
    echo  [WARN] Web restart cooldown aktif. !D700_WAIT_LEFT! sn sonra tekrar deneyin.
    echo      ^(Zorunlu ise: set YAZKLINIK_ADMIN_RESTART_FORCE=1 ^&^& D700_ADMIN_WEB_RESTART.bat^)
    goto :admin_exit
  )
)

set "VENV_PATH=%~dp0.venv"
if not exist "%VENV_PATH%\Scripts\pythonw.exe" (
  echo  [HATA] .venv pythonw.exe bulunamadi: %VENV_PATH%\Scripts\pythonw.exe
  set "D700_EXIT_CODE=1"
  pause
  goto :admin_exit
)

if /I "%YAZKLINIK_ADMIN_RESTART_FORCE%"=="1" if exist "%D700_ADMIN_RESTART_LOCK_DIR%\NUL" rd "%D700_ADMIN_RESTART_LOCK_DIR%" >nul 2>&1
2>nul md "%D700_ADMIN_RESTART_LOCK_DIR%"
if errorlevel 1 (
  echo  [WARN] Baska bir admin web restart zaten calisiyor, bu cagrim atlandi.
  goto :admin_exit
)
set "D700_LOCK_ACQUIRED=1"
>"%D700_ADMIN_RESTART_LOCK_DIR%\started_at.txt" echo %DATE% %TIME%

echo  [+] Portlar kapatiliyor: %YAZKLINIK_WEB_PORT% %YAZKLINIK_HTTPS_PORT%
set "D700_KILL_FAIL=0"
for %%P in (%YAZKLINIK_WEB_PORT% %YAZKLINIK_HTTPS_PORT% 5052 5443) do (
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%P " ^| findstr "LISTENING"') do (
    echo      PID %%a kapatiliyor (port %%P)...
    taskkill /F /PID %%a >nul 2>&1
    if errorlevel 1 (
      echo      [!] PID %%a kapatilamadi.
      set "D700_KILL_FAIL=1"
    )
  )
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2" >nul 2>&1

powershell -NoProfile -ExecutionPolicy Bypass -Command "$tempLocks=Join-Path $env:TEMP 'YazKlinik\locks'; Remove-Item -LiteralPath (Join-Path $tempLocks 'web_5052.lock') -Force -ErrorAction SilentlyContinue; Remove-Item -LiteralPath (Join-Path $tempLocks 'web_5443.lock') -Force -ErrorAction SilentlyContinue; $serviceLocks=Join-Path (Resolve-Path '%~dp0').Path 'runtime_state\service_locks'; Remove-Item -LiteralPath (Join-Path $serviceLocks 'yazklinik_web.lock') -Force -ErrorAction SilentlyContinue"

if "%D700_KILL_FAIL%"=="1" (
  echo.
  echo  [!] Bazi eski web surecleri kapatilamadi. Portlar hala doluysa Windows
  echo      Gorev Yoneticisi'nden ilgili pythonw.exe surecini sonlandirin.
)

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "PYTHONW_EXE=%VENV_PATH%\Scripts\pythonw.exe"
set "STDOUT_LOG=%~dp0D700_server.log"
set "STDERR_LOG=%~dp0D700_server_HATA.log"

echo  [+] Web servisi baslatiliyor...
start "" "%PYTHONW_EXE%" "%~dp0D700_SERVICE_RUNNER.py" "%~dp0yazklinik_web.py" "%STDOUT_LOG%" "%STDERR_LOG%"
if "%YAZKLINIK_CADDY_ACCEL%"=="1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0D700_CADDY_ACCEL_BASLAT.ps1" >nul 2>&1
  echo  [+] Caddy hiz katmani baslatildi (HTTPS :%YAZKLINIK_CADDY_HTTPS_PORT%)
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 8" >nul 2>&1

echo  [+] Durum:
netstat -ano | findstr ":%YAZKLINIK_WEB_PORT% "
netstat -ano | findstr ":%YAZKLINIK_HTTPS_PORT% "
echo.
if /I "%YAZKLINIK_ADMIN_RESTART_POSTCHECK%"=="1" (
  echo  [+] Quick check:
  "%VENV_PATH%\Scripts\python.exe" "%~dp0CODEX_QUICK_CHECK.py"
  echo.
  echo  [+] Altyapi Guard:
  "%VENV_PATH%\Scripts\python.exe" "%~dp0yazklinik_infra_guard.py" --deep
) else (
  echo  [i] Post-check varsayilan olarak kapali.
  echo      Gerekirse: set YAZKLINIK_ADMIN_RESTART_POSTCHECK=1 ^&^& D700_ADMIN_WEB_RESTART.bat
)
echo.
echo  Bitti. Pencere 3 saniye sonra kapanacak.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 3" >nul 2>&1
goto :admin_exit

:admin_exit
if "%D700_LOCK_ACQUIRED%"=="1" (
  >"%D700_ADMIN_RESTART_STAMP%" echo %DATE% %TIME%
  rd "%D700_ADMIN_RESTART_LOCK_DIR%" >nul 2>&1
)
exit /b %D700_EXIT_CODE%

