@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

REM YazKlinik Final D700 - D128 tipi Windows WebShell
REM Var olan YazKlinik web serverini sol menulu native Windows kabugu icinde acar.
REM Kullanim: YazKlinik_WebShell_Windows.bat [http://SERVER_IP:5443]

set "DEFAULT_SERVER=https://192.168.1.50:5443"
set "SERVER_URL=%~1"
if not defined SERVER_URL (
  if exist "%~dp0terminal_server_url.txt" (
    for /f "usebackq delims=" %%I in ("%~dp0terminal_server_url.txt") do (
      if not defined SERVER_URL set "SERVER_URL=%%~I"
    )
  )
)
if not defined SERVER_URL set "SERVER_URL=%DEFAULT_SERVER%"

if /I not "%YAZKLINIK_FORCE_QT_WEBSHELL%"=="1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0YazKlinik_BrowserShell_Windows.ps1" -ServerUrl "%SERVER_URL%"
  if not errorlevel 1 (
    endlocal
    exit /b 0
  )
  if not exist "%LOCALAPPDATA%\YazKlinik" mkdir "%LOCALAPPDATA%\YazKlinik" >nul 2>nul
  echo %SERVER_URL%>"%~dp0terminal_server_url.txt"
  echo %SERVER_URL%>"%LOCALAPPDATA%\YazKlinik\terminal_server_url.txt"
  echo browser>"%~dp0desktop_mode.txt"
  echo browser>"%LOCALAPPDATA%\YazKlinik\desktop_mode.txt"

  set "BROWSER_EXE="
  if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "BROWSER_EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
  if not defined BROWSER_EXE if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "BROWSER_EXE=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
  if not defined BROWSER_EXE if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "BROWSER_EXE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
  if not defined BROWSER_EXE if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "BROWSER_EXE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"

  if defined BROWSER_EXE (
    echo [1/2] Server kontrol ediliyor: %SERVER_URL%
    powershell -NoProfile -ExecutionPolicy Bypass -Command "[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}; try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 '%SERVER_URL%/api/terminal/ping'; if($r.StatusCode -eq 200){ exit 0 } else { exit 1 } } catch { exit 1 }"
    if errorlevel 1 (
      echo Server su anda cevap vermedi; yine de web motoru aciliyor.
    )
    echo [2/2] YazKlinik hizli Browser WebShell aciliyor...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { ($_.CommandLine -like '*WebShell\main.py*') -or ($_.CommandLine -like '*YazKlinik\BrowserShell*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
    if not exist "%LOCALAPPDATA%\YazKlinik\BrowserShellCache" mkdir "%LOCALAPPDATA%\YazKlinik\BrowserShellCache" >nul 2>nul
    start "YazKlinik WebShell" "%BROWSER_EXE%" --app="%SERVER_URL%/?yk_webshell=1" --user-data-dir="%LOCALAPPDATA%\YazKlinik\BrowserShell" --disk-cache-dir="%LOCALAPPDATA%\YazKlinik\BrowserShellCache" --disk-cache-size=536870912 --media-cache-size=268435456 --autoplay-policy=no-user-gesture-required "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 YazKlinikWebShell/1.0" --no-first-run --no-default-browser-check --disable-extensions --disable-sync --disable-background-networking --disable-component-update --disable-domain-reliability --disable-notifications --disable-search-engine-choice-screen --disable-features=Translate,MediaRouter,CalculateNativeWinOcclusion --enable-gpu-rasterization --enable-zero-copy --enable-features=CanvasOopRasterization --enable-smooth-scrolling --disable-background-timer-throttling --disable-backgrounding-occluded-windows --disable-renderer-backgrounding --no-proxy-server
    endlocal
    exit /b 0
  )
)

set "PYTHON_EXE=%~dp0.venv\Scripts\python.exe"
set "PYTHONW_EXE=%~dp0.venv\Scripts\pythonw.exe"
if not exist "%PYTHON_EXE%" (
  echo Python ortami bulunamadi.
  pause
  exit /b 1
)

set "DEPS_MARK=%LOCALAPPDATA%\YazKlinik\webshell_deps_D200.ok"
if not exist "%LOCALAPPDATA%\YazKlinik" mkdir "%LOCALAPPDATA%\YazKlinik" >nul 2>nul
if /I "%YAZKLINIK_WEBSHELL_FORCE_PIP%"=="1" del "%DEPS_MARK%" >nul 2>nul
if exist "%~dp0requirements.txt" if not exist "%DEPS_MARK%" (
  echo [1/3] WebShell paketleri hizli kontrol ediliyor...
  "%PYTHON_EXE%" -c "import PySide6, requests, PIL, fitz" >nul 2>nul
  if errorlevel 1 (
    echo      Eksik paket var; tek seferlik kurulum yapiliyor...
    "%PYTHON_EXE%" -m pip install --disable-pip-version-check -r "%~dp0requirements.txt" >nul
    if errorlevel 1 (
      echo Paket kurulumu tamamlanamadi.
      pause
      exit /b 1
    )
  )
  echo ok>"%DEPS_MARK%"
  echo      OK
)

echo %SERVER_URL%>"%~dp0terminal_server_url.txt"
if not exist "%LOCALAPPDATA%\YazKlinik" mkdir "%LOCALAPPDATA%\YazKlinik" >nul 2>nul
echo %SERVER_URL%>"%LOCALAPPDATA%\YazKlinik\terminal_server_url.txt"
echo hybrid>"%~dp0desktop_mode.txt"
echo hybrid>"%LOCALAPPDATA%\YazKlinik\desktop_mode.txt"

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "YAZKLINIK_SERVER_URL=%SERVER_URL%"
set "YAZKLINIK_WEB_URL=%SERVER_URL%"
set "YAZKLINIK_AI_SERVER_URL=%SERVER_URL%"
set "YAZKLINIK_DEFAULT_SERVER_URL=%SERVER_URL%"
set "YAZKLINIK_TERMINAL_DEFAULT_SERVER_URL=%SERVER_URL%"
set "YAZKLINIK_ALLOW_LOCAL_TERMINAL_SERVER=1"
set "YAZKLINIK_DESKTOP_MODE=hybrid"
set "YAZKLINIK_DESKTOP_MODE_FORCE=1"
set "YAZKLINIK_DESKTOP_FAST_START=1"
set "YAZKLINIK_DESKTOP_START_ROUTE=/giris"
set "YAZKLINIK_DESKTOP_WEB_MIRROR=0"
set "YAZKLINIK_DESKTOP_WEB_SHELL=1"
set "YAZKLINIK_DESKTOP_ENABLE_WEBENGINE=1"
set "YAZKLINIK_DESKTOP_DISABLE_WEBENGINE=0"
set "YAZKLINIK_DESKTOP_WEB_CENTER_FIRST=1"
set "YAZKLINIK_WEBSHELL_ALT_PORTS=5443"
set "YAZKLINIK_WEBSHELL_CACHE_MB=512"
set "YAZKLINIK_WEBSHELL_WINDOWS_ACCELERATOR=1"
set "YAZKLINIK_WEBSHELL_PRIORITY=above"
set "YAZKLINIK_WEBSHELL_KEEP_BACKGROUND_ACTIVE=1"
set "YAZKLINIK_WEBSHELL_GPU_TURBO=1"
set "YAZKLINIK_WEBSHELL_SAFE_MODE=0"
set "YAZKLINIK_WEBSHELL_ROUTE_PREWARM=0"
set "YAZKLINIK_SMART_ASSISTANT=1"
set "YAZKLINIK_SMART_ASSISTANT_QUIET=1"

echo [2/3] Server kontrol ediliyor: %SERVER_URL%
powershell -NoProfile -ExecutionPolicy Bypass -Command "[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}; try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 4 '%SERVER_URL%/api/terminal/ping'; if($r.StatusCode -eq 200){ exit 0 } else { exit 1 } } catch { exit 1 }"
if errorlevel 1 (
  echo Server su anda cevap vermedi; WebShell acilacak ve gerekirse adres soracak.
)

echo [3/3] YazKlinik D700 WebShell aciliyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*WebShell\main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1
if exist "%PYTHONW_EXE%" (
  start "YazKlinik WebShell" /ABOVENORMAL "%PYTHONW_EXE%" -X utf8 "%~dp0WebShell\main.py" --server "%SERVER_URL%"
) else (
  start "YazKlinik WebShell" /ABOVENORMAL "%PYTHON_EXE%" -X utf8 "%~dp0WebShell\main.py" --server "%SERVER_URL%"
)
endlocal



