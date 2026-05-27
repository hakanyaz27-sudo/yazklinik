@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

REM YazKlinik Final D700 - Normal tarayici (web tabanli) baslatici
REM WebShell (kiosk / --app modu) yerine server'i NORMAL tarayici penceresinde acar:
REM adres cubugu + sekmeler + tam web arayuzu. ?yk_webshell parametresi ve ozel
REM WebShell User-Agent EKLENMEZ; boylece server sade/kiosk moduna gecmez.
REM Kiosk WebShell'e geri donmek icin: YazKlinik_WebShell_Windows.bat
REM Kullanim: YazKlinik_Web_Tarayici.bat [https://SERVER_IP:5443]

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

set "BROWSER_EXE="
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "BROWSER_EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER_EXE if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "BROWSER_EXE=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if not defined BROWSER_EXE if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "BROWSER_EXE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
if not defined BROWSER_EXE if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "BROWSER_EXE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"

if not defined BROWSER_EXE (
  echo Chrome veya Edge bulunamadi; varsayilan tarayicida aciliyor...
  start "" "%SERVER_URL%/"
  endlocal
  exit /b 0
)

echo [1/2] Server kontrol ediliyor: %SERVER_URL%
powershell -NoProfile -ExecutionPolicy Bypass -Command "[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}; try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 '%SERVER_URL%/api/terminal/ping'; if($r.StatusCode -eq 200){ exit 0 } else { exit 1 } } catch { exit 1 }"
if errorlevel 1 (
  echo Server su anda cevap vermedi; yine de tarayici aciliyor.
)

REM Eski kiosk WebShell penceresini kapat (ayni profili paylasir; tek temiz pencere).
REM Name filtresi (chrome/msedge) ile: bu komutu calistiran powershell ETKILENMEZ.
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { ($_.Name -eq 'chrome.exe' -or $_.Name -eq 'msedge.exe') -and ($_.CommandLine -like '*YazKlinik\BrowserShell*') } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

if not exist "%LOCALAPPDATA%\YazKlinik\BrowserShellCache" mkdir "%LOCALAPPDATA%\YazKlinik\BrowserShellCache" >nul 2>nul

echo [2/2] YazKlinik web arayuzu normal tarayici penceresinde aciliyor...
start "YazKlinik Web" "%BROWSER_EXE%" --new-window --user-data-dir="%LOCALAPPDATA%\YazKlinik\BrowserShell" --disk-cache-dir="%LOCALAPPDATA%\YazKlinik\BrowserShellCache" --disk-cache-size=536870912 --no-first-run --no-default-browser-check --disable-search-engine-choice-screen --enable-gpu-rasterization --enable-zero-copy --enable-smooth-scrolling "%SERVER_URL%/"
endlocal
exit /b 0
