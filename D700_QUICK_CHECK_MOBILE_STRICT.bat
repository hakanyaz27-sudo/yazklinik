@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
set "CODEX_QUICK_CHECK_NO_REEXEC=1"
set "PYTHONUNBUFFERED=1"
if "%CODEX_QUICK_CHECK_ALLOW_DURING_MAINT%"=="" set "CODEX_QUICK_CHECK_ALLOW_DURING_MAINT=1"
if "%CODEX_QUICK_CHECK_LOCK_WAIT_SEC%"=="" set "CODEX_QUICK_CHECK_LOCK_WAIT_SEC=60"
if not exist "%PY%" (
  echo [ERR] Python venv bulunamadi: %PY%
  exit /b 1
)

echo [INFO] D700 quick check + mobile scroll strict baslatiliyor...
"%PY%" CODEX_QUICK_CHECK.py --mobile-scroll-strict
set "RC=%ERRORLEVEL%"
if "!RC!"=="0" (
  echo [OK] Tum kontroller basarili.
  exit /b 0
)

echo [WARN] Ilk deneme basarisiz. Kod=!RC!
if "!RC!"=="-1073741510" (
  echo [WARN] Kesinti algilandi ^(Ctrl+C/sinyal^). Bir kez otomatik tekrar denenecek...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2" >nul 2>&1
  "%PY%" CODEX_QUICK_CHECK.py --mobile-scroll-strict
  set "RC=!ERRORLEVEL!"
  if "!RC!"=="0" (
    echo [OK] Otomatik tekrar denemesi basarili.
    exit /b 0
  )
  echo [WARN] Otomatik tekrar da basarisiz. Kod=!RC!
)
if "!RC!"=="130" (
  echo [WARN] Kesinti algilandi ^(130^). Bir kez otomatik tekrar denenecek...
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Sleep -Seconds 2" >nul 2>&1
  "%PY%" CODEX_QUICK_CHECK.py --mobile-scroll-strict
  set "RC=!ERRORLEVEL!"
  if "!RC!"=="0" (
    echo [OK] Otomatik tekrar denemesi basarili.
    exit /b 0
  )
  echo [WARN] Otomatik tekrar da basarisiz. Kod=!RC!
)
if "!RC!"=="2" (
  echo [WARN] Baska CODEX_QUICK_CHECK calisiyor. Bu deneme lock nedeniyle sonlandi.
  exit /b 2
)
if /I not "%YAZKLINIK_QUICKCHECK_SELFHEAL%"=="1" (
  echo [INFO] Self-heal restart varsayilan olarak PASIF. (YAZKLINIK_QUICKCHECK_SELFHEAL=1 olmadan web restart tetiklenmez.)
  exit /b !RC!
)

echo [INFO] Self-heal AKTIF: web-only restart denenecek...
if exist "%~dp0D700_ADMIN_WEB_RESTART.bat" (
  start "" cmd /c "%~dp0D700_ADMIN_WEB_RESTART.bat"
) else (
  echo [WARN] D700_ADMIN_WEB_RESTART.bat bulunamadi, restart atlandi.
)

if exist "%~dp0CODEX_WAIT_WEB_READY.py" (
  "%PY%" CODEX_WAIT_WEB_READY.py --wait-sec 480 --interval-sec 8 --streak 2 --require-both
) else (
  ping 127.0.0.1 -n 21 >nul
)

echo [INFO] Ikinci dogrulama calisiyor...
"%PY%" CODEX_QUICK_CHECK.py --mobile-scroll-strict
set "RC=%ERRORLEVEL%"
if "!RC!"=="0" (
  echo [OK] Tum kontroller basarili.
  exit /b 0
)
echo [ERR] Kontrol basarisiz. Kod=!RC!
exit /b !RC!
