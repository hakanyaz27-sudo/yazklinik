@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "LOOPS=%~1"
if "%LOOPS%"=="" set "LOOPS=3"
set "DELAY_SEC=%~2"
if "%DELAY_SEC%"=="" set "DELAY_SEC=8"

set /a _tmp_loops=%LOOPS% >nul 2>&1
if errorlevel 1 (
  echo [ERR] Gecersiz LOOP degeri: %LOOPS%
  exit /b 1
)
if %LOOPS% LSS 1 (
  echo [ERR] LOOP en az 1 olmali.
  exit /b 1
)

set /a _tmp_delay=%DELAY_SEC% >nul 2>&1
if errorlevel 1 (
  echo [ERR] Gecersiz DELAY degeri: %DELAY_SEC%
  exit /b 1
)
if %DELAY_SEC% LSS 0 set "DELAY_SEC=0"

set "PASS=0"
set "FAIL=0"
set "LAST_LOG="

echo [INFO] D700 stabilite soak basliyor. loop=%LOOPS% delay=%DELAY_SEC%s

for /L %%I in (1,1,%LOOPS%) do (
  echo.
  echo [SOAK %%I/%LOOPS%] Tek-tik stabilite calisiyor...
  for /f "usebackq delims=" %%L in (`powershell -NoProfile -Command "(Get-Date).ToString('yyyy-MM-dd HH:mm:ss')"`) do set "RUN_AT=%%L"

  set "YAZKLINIK_STABILITE_APPLY_FIX=1"
  set "YAZKLINIK_STABILITE_STRICT_SELFHEAL=1"
  call "%~dp0D700_STABILITE_TEK_TIK.bat"
  set "RC=!ERRORLEVEL!"

  for /f "usebackq delims=" %%F in (`powershell -NoProfile -Command "$p='D:\YazKlinik_Final_D700\runtime_state\maintenance_logs'; $f=Get-ChildItem -LiteralPath $p -Filter 'stabilite_tek_tik_*.log' -File | Sort-Object LastWriteTime -Descending | Select-Object -First 1; if($f){$f.FullName}"`) do set "LAST_LOG=%%F"
  set "LOG_PASS=0"
  if defined LAST_LOG (
    findstr /c:"CODEX_D700_QUICK_CHECK_OK" "!LAST_LOG!" >nul && set "LOG_PASS=1"
    findstr /c:"D700 stabilite turu basarili." "!LAST_LOG!" >nul || set "LOG_PASS=0"
  )

  if "!RC!"=="0" (
    set /a PASS+=1
    echo [SOAK %%I] PASS  rc=!RC!  at=!RUN_AT!
  ) else if "!LOG_PASS!"=="1" if "!RC!"=="-1" (
    set /a PASS+=1
    echo [SOAK %%I] PASS* rc=!RC! ^(gecici kesinti kodu, log OK^) at=!RUN_AT!
  ) else if "!LOG_PASS!"=="1" if "!RC!"=="-1073741510" (
    set /a PASS+=1
    echo [SOAK %%I] PASS* rc=!RC! ^(kesinti kodu, log OK^) at=!RUN_AT!
  ) else if "!LOG_PASS!"=="1" if "!RC!"=="130" (
    set /a PASS+=1
    echo [SOAK %%I] PASS* rc=!RC! ^(kesinti kodu, log OK^) at=!RUN_AT!
  ) else (
    set /a FAIL+=1
    echo [SOAK %%I] FAIL  rc=!RC!  at=!RUN_AT!
    if defined LAST_LOG echo [SOAK %%I] LOG !LAST_LOG!
    echo [ERR] Soak durduruldu.
    exit /b !RC!
  )

  if %%I LSS %LOOPS% if %DELAY_SEC% GTR 0 (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds %DELAY_SEC%" >nul 2>&1
  )
)

echo.
echo [OK] SOAK tamamlandi. PASS=%PASS% FAIL=%FAIL%
if defined LAST_LOG echo [LAST_LOG] %LAST_LOG%
exit /b 0
