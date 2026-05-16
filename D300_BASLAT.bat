@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title YazKlinik D300 - Hizli Baslat
cd /d "%~dp0"
cls

echo.
echo  ============================================================
echo                YazKlinik D300 - Hizli Baslat (Asustor)
echo  ============================================================
echo  Klasor: %CD%
echo.

REM 1) config.env dosyasini oku ve env var olarak set et
if exist "config.env" (
  echo  [+] config.env okuniyor...
  for /f "usebackq tokens=1,* delims==" %%a in ("config.env") do (
    set "_LINE=%%a"
    setlocal enabledelayedexpansion
    set "_FIRST=!_LINE:~0,1!"
    if not "!_FIRST!"=="#" if not "!_LINE!"=="" (
      endlocal
      set "%%a=%%b"
    ) else (
      endlocal
    )
  )
  echo      OK
) else (
  echo  [!] config.env YOK - default'lar kullanilacak
  set "YAZKLINIK_NAS_ROOT=\\asustor\Voluson"
  set "YAZKLINIK_DB_PATH=D:\YazKlinik_Final_D300\local_db\yazklinik_v68.sqlite3"
  set "YAZKLINIK_WEB_PORT=5443"
  set "YAZKLINIK_HTTPS_PORT=5443"
  set "YAZKLINIK_ENABLE_HTTPS=1"
  set "YAZKLINIK_WAITRESS_THREADS=12"
  set "PYTHONUTF8=1"
  set "PYTHONIOENCODING=utf-8"
  set "PYTHONUNBUFFERED=1"
)

echo  [+] NAS Root : %YAZKLINIK_NAS_ROOT%
echo  [+] DB Path  : %YAZKLINIK_DB_PATH%
echo  [+] HTTP Port: %YAZKLINIK_WEB_PORT%
echo  [+] SSL Aktif: %YAZKLINIK_ENABLE_HTTPS%
echo.

REM 2) Hazir .venv bul - D104 paylasim, D300 yerel veya yenide kur
set "VENV_PATH="
if exist "C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe" (
  set "VENV_PATH=C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv"
  echo  [+] Hazir venv: D104\.venv - paylasimli
) else if exist "%~dp0.venv\Scripts\python.exe" (
  set "VENV_PATH=%~dp0.venv"
  echo  [+] Yerel venv: %~dp0.venv
) else (
  echo  [!] Calisir bir .venv yok. HEMEN_BASLAT.bat ile kur veya D104 venv'i kullan.
  pause
  exit /b 1
)

if "%YAZKLINIK_ENABLE_HTTPS%"=="1" (
  set "YAZKLINIK_SERVER_URL=https://127.0.0.1:%YAZKLINIK_HTTPS_PORT%"
) else (
  set "YAZKLINIK_SERVER_URL=http://127.0.0.1:%YAZKLINIK_WEB_PORT%"
)
set "YAZKLINIK_WEB_URL=%YAZKLINIK_SERVER_URL%"
set "YAZKLINIK_AI_SERVER_URL=%YAZKLINIK_SERVER_URL%"
set "YAZKLINIK_DEFAULT_SERVER_URL=%YAZKLINIK_SERVER_URL%"
set "YAZKLINIK_ALLOW_LOCAL_TERMINAL_SERVER=1"
if not defined YAZKLINIK_TERMINAL_TOKEN for /f %%t in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString(''N'')"') do set "YAZKLINIK_TERMINAL_TOKEN=%%t"
"%VENV_PATH%\Scripts\python.exe" "%~dp0D300_TERMINAL_SYNC.py" --server-url "%YAZKLINIK_SERVER_URL%" >nul 2>&1

REM 3) Eski server zombie durdur
echo  [+] Port kontrol: %YAZKLINIK_WEB_PORT% ve eski 5052 fallback...
for %%P in (%YAZKLINIK_WEB_PORT% 5052) do (
  set "OLD_PID="
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%P " ^| findstr "LISTENING"') do set "OLD_PID=%%a"
  if defined OLD_PID (
    echo      Port %%P uzerindeki eski PID !OLD_PID! durduruluyor...
    taskkill /PID !OLD_PID! /F >nul 2>&1
    timeout /t 2 /nobreak >nul
  )
)

REM 4) Asustor NAS erisim kontrol (isteyebilir)
echo  [+] Asustor NAS erisim kontrol...
if exist "\\asustor\Voluson" (
  echo      OK - Asustor NAS erisilebilir
) else (
  echo      [!] \\asustor\Voluson erisilmiyor - hasta klasorleri yuklenmeyecek
  echo      Cozum: NAS'a baglan veya /sistem-ayarlari'ndan path degistir
)

REM 5) Local DB klasoru var mi
if not exist "local_db" (
  echo  [+] local_db klasoru yaratiliyor...
  mkdir "local_db"
)
if not exist "auto_backups" (
  mkdir "auto_backups"
)

REM 5b) Whisper mikroservisi (port 9000) - werkzeug threading deadlock
REM kacis yolu. Bagimsiz process olarak baslatilir.
echo  [+] Whisper mikroservisi (port 9000)...
set "WHISPER_OLD_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9000 " ^| findstr "LISTENING"') do set "WHISPER_OLD_PID=%%a"
if defined WHISPER_OLD_PID (
  echo      Port 9000 eski PID !WHISPER_OLD_PID! durduruluyor...
  taskkill /PID !WHISPER_OLD_PID! /F >nul 2>&1
  timeout /t 1 /nobreak >nul
)
if not defined YAZKLINIK_WHISPER_SERVICE_PORT set "YAZKLINIK_WHISPER_SERVICE_PORT=9000"
REM Whisper model/device/compute config.env'den okunur (RTX 5090: cuda/large-v3-turbo/float16).
REM HF_HUB_OFFLINE=1 ise model ilk indirme'de basarisiz olur - off birak ki turbo indirilebilsin.
set "WHISPER_LOG=%~dp0D300_whisper_service.log"
start "" /B /HIGH "%VENV_PATH%\Scripts\python.exe" -u "%~dp0yazklinik_whisper_service.py" 1>"%WHISPER_LOG%" 2>&1
echo      Whisper service baslatildi (log: D300_whisper_service.log)

REM 5c) XTTS-v2 mikroservisi (port 9002) - lokal RTX 5090 Emel/Ahmet voice clone
echo  [+] XTTS-v2 mikroservisi (port 9002)...
set "XTTS_OLD_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9002 " ^| findstr "LISTENING"') do set "XTTS_OLD_PID=%%a"
if defined XTTS_OLD_PID (
  echo      Port 9002 eski PID !XTTS_OLD_PID! durduruluyor...
  taskkill /PID !XTTS_OLD_PID! /F >nul 2>&1
  timeout /t 1 /nobreak >nul
)
if not defined YAZKLINIK_XTTS_SERVICE_PORT set "YAZKLINIK_XTTS_SERVICE_PORT=9002"
set "COQUI_TOS_AGREED=1"
set "XTTS_LOG=%~dp0D300_xtts_service.log"
start "" /B /HIGH "%VENV_PATH%\Scripts\python.exe" -u "%~dp0yazklinik_xtts_service.py" 1>"%XTTS_LOG%" 2>&1
echo      XTTS service baslatildi (log: D300_xtts_service.log)

REM 5e) Health Monitor (her 30sn'de servis check + dusenleri restart)
echo  [+] Health Monitor baslatiliyor...
set "HEALTH_OLD_PID="
for /f "tokens=2" %%a in ('tasklist /FI "IMAGENAME eq python.exe" /FO csv ^| findstr /I "D300_HEALTH_MONITOR"') do set "HEALTH_OLD_PID=%%a"
set "HEALTH_LOG=%~dp0D300_health_monitor.log"
start "" /B "%VENV_PATH%\Scripts\python.exe" -u "%~dp0D300_HEALTH_MONITOR.py" 1>"%HEALTH_LOG%" 2>&1
echo      Health Monitor baslatildi (log: D300_health_monitor.log)

REM 5d) Piper TTS mikroservisi (port 9001) - lokal yedek robotic ses
echo  [+] Piper TTS mikroservisi (port 9001)...
set "PIPER_OLD_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9001 " ^| findstr "LISTENING"') do set "PIPER_OLD_PID=%%a"
if defined PIPER_OLD_PID (
  echo      Port 9001 eski PID !PIPER_OLD_PID! durduruluyor...
  taskkill /PID !PIPER_OLD_PID! /F >nul 2>&1
  timeout /t 1 /nobreak >nul
)
if not defined YAZKLINIK_PIPER_SERVICE_PORT set "YAZKLINIK_PIPER_SERVICE_PORT=9001"
set "PIPER_LOG=%~dp0D300_piper_service.log"
start "" /B /HIGH "%VENV_PATH%\Scripts\python.exe" -u "%~dp0yazklinik_piper_service.py" 1>"%PIPER_LOG%" 2>&1
echo      Piper service baslatildi (log: D300_piper_service.log)

REM 6) Server BASLAT (arka planda)
echo  ============================================================
echo                  Server BASLIYOR
echo  ============================================================
echo  Adres   : http://127.0.0.1:%YAZKLINIK_WEB_PORT%
if "%YAZKLINIK_ENABLE_HTTPS%"=="1" (
  echo  HTTPS   : https://127.0.0.1:%YAZKLINIK_HTTPS_PORT%
  echo  Dis URL : https://176.236.92.142:65187  ^(modem dis 65187 -^> ic %YAZKLINIK_HTTPS_PORT%^)
) else (
  echo  HTTPS   : kapali - %YAZKLINIK_WEB_PORT% SSL'siz HTTP olarak calisir
  echo  Dis URL : http://176.236.92.142:65187  ^(modem dis 65187 -^> ic %YAZKLINIK_WEB_PORT%^)
)
echo  Giris   : doktor / 1234
echo  NAS     : %YAZKLINIK_NAS_ROOT%
echo  DB      : %YAZKLINIK_DB_PATH%
echo.
echo  Lutfen bekleyin (5-15 saniye)...
echo.

set "STDOUT_LOG=%~dp0D300_server.log"
set "STDERR_LOG=%~dp0D300_server_HATA.log"

start "" /B /HIGH "%VENV_PATH%\Scripts\python.exe" -u yazklinik_web.py 1>"%STDOUT_LOG%" 2>"%STDERR_LOG%"

REM 7) Hazir olmasini bekle (max 45 sn). PowerShell yerine curl kullaniyoruz
REM cunku PS5.1 ServerCertificateValidationCallback self-signed bypass'i guvenilir degil.
REM Windows 10/11'de curl built-in. -k self-signed cert kabul eder.
set "READY=0"
for /l %%i in (1,1,30) do (
  if !READY!==0 (
    timeout /t 1 /nobreak >nul
    curl -k -s -o nul --connect-timeout 2 --max-time 4 -w "%%{http_code}" "%YAZKLINIK_SERVER_URL%/giris" > "%TEMP%\yk_ready.txt" 2>nul
    set /p HTTP_CODE=<"%TEMP%\yk_ready.txt"
    if not "!HTTP_CODE!"=="" if not "!HTTP_CODE!"=="000" set "READY=1"
  )
)
del "%TEMP%\yk_ready.txt" >nul 2>&1

if "%READY%"=="1" (
  echo  ============================================================
  echo   [BASARI] Server hazir! WebShell aciliyor...
  echo  ============================================================
  set "YAZKLINIK_DESKTOP_MODE=hybrid"
  set "YAZKLINIK_DESKTOP_MODE_FORCE=1"
  set "YAZKLINIK_DESKTOP_FAST_START=1"
  set "YAZKLINIK_DESKTOP_START_ROUTE=/giris"
  set "YAZKLINIK_DESKTOP_WEB_SHELL=1"
  set "YAZKLINIK_DESKTOP_ENABLE_WEBENGINE=1"
  set "YAZKLINIK_DESKTOP_DISABLE_WEBENGINE=0"
  set "YAZKLINIK_DESKTOP_WEB_MIRROR=0"
  set "YAZKLINIK_DESKTOP_WEB_CENTER_FIRST=1"
  set "YAZKLINIK_TERMINAL_DEFAULT_SERVER_URL=%YAZKLINIK_SERVER_URL%"
  set "YAZKLINIK_WEBSHELL_ALT_PORTS=%YAZKLINIK_WEB_PORT%,5443"
  if not defined YAZKLINIK_WEBSHELL_CACHE_MB set "YAZKLINIK_WEBSHELL_CACHE_MB=512"
  if not defined YAZKLINIK_WEBSHELL_WINDOWS_ACCELERATOR set "YAZKLINIK_WEBSHELL_WINDOWS_ACCELERATOR=1"
  if not defined YAZKLINIK_WEBSHELL_PRIORITY set "YAZKLINIK_WEBSHELL_PRIORITY=above"
  if not defined YAZKLINIK_WEBSHELL_KEEP_BACKGROUND_ACTIVE set "YAZKLINIK_WEBSHELL_KEEP_BACKGROUND_ACTIVE=1"
  if not defined YAZKLINIK_WEBSHELL_GPU_TURBO set "YAZKLINIK_WEBSHELL_GPU_TURBO=1"
  if not defined YAZKLINIK_WEBSHELL_SAFE_MODE set "YAZKLINIK_WEBSHELL_SAFE_MODE=0"
  if not defined YAZKLINIK_WEBSHELL_ROUTE_PREWARM set "YAZKLINIK_WEBSHELL_ROUTE_PREWARM=0"
  set "YAZKLINIK_SMART_ASSISTANT=1"
  set "YAZKLINIK_SMART_ASSISTANT_QUIET=1"
  "%VENV_PATH%\Scripts\python.exe" "%~dp0D300_TERMINAL_SYNC.py" --server-url "%YAZKLINIK_SERVER_URL%" >nul 2>&1
  call "%~dp0YazKlinik_WebShell_Windows.bat" "%YAZKLINIK_SERVER_URL%"
  echo.
  echo  WebShell: hizli browser web arayuz
  echo  Tarayici URL: %YAZKLINIK_SERVER_URL%
  echo.
  echo  NAS / DB ayarini degistirmek icin:
  echo    Tarayicidan: %YAZKLINIK_SERVER_URL%/sistem-ayarlari
  echo    Veya elinizle: %~dp0config.env dosyasini editleyin + bu launcher'i restart edin
  echo.
) else (
  echo  ============================================================
  echo   [HATA] Server 30 saniyede acilmadi.
  echo  ============================================================
  echo  HATA log son 20 satir:
  powershell -NoProfile -Command "Get-Content '%STDERR_LOG%' -Tail 20 -ErrorAction SilentlyContinue"
)

echo.
echo  ============================================================
echo  Server arka planda calisiyor. Bu pencere LOG icin acik.
echo  Server'i durdurmak: bu pencereyi kapat veya:
echo    taskkill /F /IM python.exe
echo  ============================================================
echo.
cmd /k
