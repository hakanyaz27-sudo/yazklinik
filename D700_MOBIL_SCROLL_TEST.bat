@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo [ERR] Python venv bulunamadi: %PY%
  exit /b 1
)

if "%YAZKLINIK_MOBILE_SELFHEAL%"=="" set "YAZKLINIK_MOBILE_SELFHEAL=0"

set "HTTP_CODE=000"
set "HTTPS_CODE=000"
for /f "usebackq delims=" %%A in (`curl.exe -s -o NUL -w "%%{http_code}" http://127.0.0.1:5052/giris`) do set "HTTP_CODE=%%A"
for /f "usebackq delims=" %%A in (`curl.exe -k -s -o NUL -w "%%{http_code}" https://127.0.0.1:5443/giris`) do set "HTTPS_CODE=%%A"
echo [INFO] Anlik web durumu: 5052=!HTTP_CODE! 5443=!HTTPS_CODE!

if /I not "!HTTP_CODE!!HTTPS_CODE!"=="200200" (
  if /I "%YAZKLINIK_MOBILE_SELFHEAL%"=="1" (
    echo [WARN] Web hazir degil. Self-heal tetikleniyor...
    set "YAZKLINIK_WEB_SELFHEAL_APPLY=1"
    if exist "%~dp0D700_WEB_SELF_HEAL_CHECK.bat" (
      call "%~dp0D700_WEB_SELF_HEAL_CHECK.bat"
      if errorlevel 1 (
        echo [ERR] Web self-heal basarisiz, mobil test durduruldu.
        exit /b 1
      )
    ) else (
      echo [ERR] D700_WEB_SELF_HEAL_CHECK.bat bulunamadi.
      exit /b 1
    )
  ) else (
    echo [ERR] Web hazir degil ve self-heal kapali ^(YAZKLINIK_MOBILE_SELFHEAL=0^).
    echo      Gerekirse: set YAZKLINIK_MOBILE_SELFHEAL=1 ^&^& D700_MOBIL_SCROLL_TEST.bat
    exit /b 2
  )
)

echo [INFO] Mobil scroll smoke baslatiliyor...
"%PY%" CODEX_MOBILE_SCROLL_CHECK.py
set "RC=%ERRORLEVEL%"

if "%RC%"=="0" (
  echo [OK] Mobil scroll smoke gecti.
) else (
  echo [ERR] Mobil scroll smoke basarisiz. Kod=%RC%
)

exit /b %RC%
