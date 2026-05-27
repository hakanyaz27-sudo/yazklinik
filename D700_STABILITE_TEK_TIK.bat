@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "LOG_ROOT=%~dp0runtime_state\maintenance_logs"
if not exist "%LOG_ROOT%" mkdir "%LOG_ROOT%" >nul 2>&1
if "%YAZKLINIK_STABILITE_FORCE_MODE%"=="" set "YAZKLINIK_STABILITE_FORCE_MODE=1"
if /I "%YAZKLINIK_STABILITE_FORCE_MODE%"=="1" (
  set "YAZKLINIK_STABILITE_APPLY_FIX=1"
  rem SAFE DEFAULT: strict quick-check failures should not auto-restart web
  set "YAZKLINIK_STABILITE_STRICT_SELFHEAL=0"
) else (
  if "%YAZKLINIK_STABILITE_APPLY_FIX%"=="" set "YAZKLINIK_STABILITE_APPLY_FIX=1"
  if "%YAZKLINIK_STABILITE_STRICT_SELFHEAL%"=="" set "YAZKLINIK_STABILITE_STRICT_SELFHEAL=0"
)

for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "(Get-Date).ToString('yyyyMMdd_HHmmss')"`) do set "STAMP=%%A"
if "%STAMP%"=="" set "STAMP=manual"
set "LOG_FILE=%LOG_ROOT%\stabilite_tek_tik_%STAMP%.log"

echo [INFO] D700 stabilite tek-tik basladi. > "%LOG_FILE%"
echo [INFO] Baslangic: %DATE% %TIME% >> "%LOG_FILE%"
echo [INFO] Mode: APPLY_FIX=%YAZKLINIK_STABILITE_APPLY_FIX% STRICT_SELFHEAL=%YAZKLINIK_STABILITE_STRICT_SELFHEAL%
echo [INFO] Mode: APPLY_FIX=%YAZKLINIK_STABILITE_APPLY_FIX% STRICT_SELFHEAL=%YAZKLINIK_STABILITE_STRICT_SELFHEAL% >> "%LOG_FILE%"

set "QC_FLAG=%~dp0runtime_state\maintenance_locks\quick_check_disabled.flag"
set "QC_TEMP_FLAG=%TEMP%\D700_quick_check_disabled.flag"
if exist "%QC_FLAG%" (
  if /I "%YAZKLINIK_KEEP_MAINT_FLAG%"=="1" (
    echo [INFO] quick_check maintenance flag korunuyor ^(YAZKLINIK_KEEP_MAINT_FLAG=1^). >> "%LOG_FILE%"
  ) else (
    del /f /q "%QC_FLAG%" >nul 2>&1
    echo [INFO] stale quick_check maintenance flag temizlendi. >> "%LOG_FILE%"
  )
)
if exist "%QC_TEMP_FLAG%" (
  if /I "%YAZKLINIK_KEEP_MAINT_FLAG%"=="1" (
    echo [INFO] temp quick_check maintenance flag korunuyor ^(YAZKLINIK_KEEP_MAINT_FLAG=1^). >> "%LOG_FILE%"
  ) else (
    del /f /q "%QC_TEMP_FLAG%" >nul 2>&1
    echo [INFO] stale temp quick_check maintenance flag temizlendi. >> "%LOG_FILE%"
  )
)

for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$p='D:\YazKlinik_Final_D700\runtime_state\locks\CODEX_QUICK_CHECK.lock'; if(-not (Test-Path $p)){ 'NOLOCK'; exit 0 }; try{ $j=Get-Content -LiteralPath $p -Raw | ConvertFrom-Json; $lockPid=[int]$j.pid } catch { $lockPid=0 }; if($lockPid -le 0 -or -not (Get-Process -Id $lockPid -ErrorAction SilentlyContinue)){ Remove-Item -LiteralPath $p -Force -ErrorAction SilentlyContinue; 'STALE_LOCK_CLEARED' } else { 'LOCK_ACTIVE_PID=' + $lockPid }"`) do set "QC_LOCK_STATE=%%A"
if not "%QC_LOCK_STATE%"=="" echo [INFO] quick-check lock durumu: %QC_LOCK_STATE% >> "%LOG_FILE%"

for /f "usebackq delims=" %%A in (`powershell -NoProfile -Command "$k=@(); Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'powershell.exe' -and $_.CommandLine -and $_.CommandLine -like '*D700_stop_old_test_queue.ps1*' } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; $k += [string]$_.ProcessId } catch {} }; if($k.Count -gt 0){ 'STOPPED_GUARD=' + ($k -join ',') } else { 'NO_GUARD_RUNNING' }"`) do set "GUARD_FIX=%%A"
if not "%GUARD_FIX%"=="" echo [INFO] guard durumu: %GUARD_FIX% >> "%LOG_FILE%"

echo [1/2] Web self-heal kontrolu...
echo [1/2] Web self-heal kontrolu... >> "%LOG_FILE%"
set "YAZKLINIK_WEB_SELFHEAL_APPLY=%YAZKLINIK_STABILITE_APPLY_FIX%"
call "%~dp0D700_WEB_SELF_HEAL_CHECK.bat" >> "%LOG_FILE%" 2>&1
if errorlevel 1 (
  echo [ERR] Web self-heal basarisiz.
  echo [ERR] Web self-heal basarisiz. >> "%LOG_FILE%"
  if /I not "%YAZKLINIK_STABILITE_APPLY_FIX%"=="1" (
    echo [NOT] Otomatik restart kapali oldugu icin onarim uygulanmadi. ^(YAZKLINIK_STABILITE_APPLY_FIX=0^)
    echo [NOT] Otomatik restart kapali oldugu icin onarim uygulanmadi ^(YAZKLINIK_STABILITE_APPLY_FIX=0^). >> "%LOG_FILE%"
  )
  echo [LOG] %LOG_FILE%
  exit /b 1
)

echo [2/2] Strict quick-check (mobil dahil)...
echo [2/2] Strict quick-check (mobil dahil)... >> "%LOG_FILE%"
set "YAZKLINIK_QUICKCHECK_SELFHEAL=%YAZKLINIK_STABILITE_STRICT_SELFHEAL%"
call "%~dp0D700_QUICK_CHECK_MOBILE_STRICT.bat" >> "%LOG_FILE%" 2>&1
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" (
  echo [ERR] Strict quick-check basarisiz. Kod=%RC%
  echo [ERR] Strict quick-check basarisiz. Kod=%RC% >> "%LOG_FILE%"
  echo [LOG] %LOG_FILE%
  exit /b %RC%
)

echo [OK] D700 stabilite turu basarili.
echo [OK] D700 stabilite turu basarili. >> "%LOG_FILE%"
echo [LOG] %LOG_FILE%
exit /b 0
