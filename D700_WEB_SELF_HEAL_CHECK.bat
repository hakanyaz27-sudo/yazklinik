@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERR] Python venv bulunamadi: %PY%
  exit /b 1
)
if "%YAZKLINIK_WEB_SELFHEAL_APPLY%"=="" set "YAZKLINIK_WEB_SELFHEAL_APPLY=0"

echo [INFO] D700 web health kontrolu basliyor...

set "HTTP_CODE=000"
set "HTTPS_CODE=000"
for /f "usebackq delims=" %%A in (`curl.exe -s -o NUL -w "%%{http_code}" http://127.0.0.1:5052/giris`) do set "HTTP_CODE=%%A"
for /f "usebackq delims=" %%A in (`curl.exe -k -s -o NUL -w "%%{http_code}" https://127.0.0.1:5443/giris`) do set "HTTPS_CODE=%%A"

echo [INFO] Anlik durum: 5052=!HTTP_CODE! 5443=!HTTPS_CODE!

if "!HTTP_CODE!"=="200" if "!HTTPS_CODE!"=="200" (
  echo [OK] Web zaten hazir.
  exit /b 0
)

if /I not "%YAZKLINIK_WEB_SELFHEAL_APPLY%"=="1" (
  echo [ERR] Web hazir degil ve otomatik restart kapali. ^(YAZKLINIK_WEB_SELFHEAL_APPLY=0^)
  echo      Gerekirse: set YAZKLINIK_WEB_SELFHEAL_APPLY=1 ^&^& D700_WEB_SELF_HEAL_CHECK.bat
  exit /b 2
)

if exist "%~dp0D700_ADMIN_WEB_RESTART.bat" (
  echo [WARN] Web hazir degil. Web-only restart uygulanacak...
  if "%YAZKLINIK_ADMIN_RESTART_AUTO_ELEVATE%"=="" set "YAZKLINIK_ADMIN_RESTART_AUTO_ELEVATE=0"
  call "%~dp0D700_ADMIN_WEB_RESTART.bat"
  if errorlevel 1 (
    echo [WARN] Admin restart basarisiz oldu. User-level fallback denenecek...
    if exist "%~dp0D700_USER_WEB_RESTART.bat" (
      call "%~dp0D700_USER_WEB_RESTART.bat"
      if errorlevel 1 (
        echo [ERR] D700_USER_WEB_RESTART.bat da basarisiz oldu.
        exit /b 1
      )
    ) else (
      echo [ERR] D700_USER_WEB_RESTART.bat bulunamadi.
      exit /b 1
    )
  )
) else (
  echo [ERR] D700_ADMIN_WEB_RESTART.bat bulunamadi.
  exit /b 1
)

if not exist "%~dp0CODEX_WAIT_WEB_READY.py" (
  echo [ERR] CODEX_WAIT_WEB_READY.py bulunamadi.
  exit /b 1
)

echo [INFO] Hazirlik bekleniyor (5052 + 5443)...
"%PY%" CODEX_WAIT_WEB_READY.py --wait-sec 600 --interval-sec 8 --streak 2 --require-both
if errorlevel 1 (
  echo [ERR] Web self-heal basarisiz.
  exit /b 1
)

echo [OK] Web self-heal basarili.
exit /b 0
