@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

set "YK_LOCAL=%LOCALAPPDATA%\YazKlinik"
set "YK_CACHE_1=%YK_LOCAL%\BrowserShellCache"
set "YK_CACHE_2=%YK_LOCAL%\BrowserShell\Default\Cache"
set "YK_CACHE_3=%YK_LOCAL%\BrowserShell\Default\Code Cache"
set "YK_CACHE_4=%YK_LOCAL%\BrowserShell\Default\GPUCache"

echo [1/3] WebShell surecleri kapatiliyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*YazKlinikWebShell/1.0*' -or $_.CommandLine -like '*YazKlinik\\BrowserShell*' -or $_.CommandLine -like '*WebShell\\main.py*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }" >nul 2>&1

echo [2/3] BrowserShell cache temizleniyor...
if exist "%YK_CACHE_1%" rmdir /s /q "%YK_CACHE_1%" >nul 2>nul
if exist "%YK_CACHE_2%" rmdir /s /q "%YK_CACHE_2%" >nul 2>nul
if exist "%YK_CACHE_3%" rmdir /s /q "%YK_CACHE_3%" >nul 2>nul
if exist "%YK_CACHE_4%" rmdir /s /q "%YK_CACHE_4%" >nul 2>nul

if not exist "%YK_CACHE_1%" mkdir "%YK_CACHE_1%" >nul 2>nul
if not exist "%YK_CACHE_2%" mkdir "%YK_CACHE_2%" >nul 2>nul
if not exist "%YK_CACHE_3%" mkdir "%YK_CACHE_3%" >nul 2>nul
if not exist "%YK_CACHE_4%" mkdir "%YK_CACHE_4%" >nul 2>nul

if /I "%~1"=="--no-launch" (
  echo [3/3] Tamamlandi. WebShell acilmadi: --no-launch
  endlocal
  exit /b 0
)

echo [3/3] WebShell yeniden baslatiliyor...
start "" "%~dp0YazKlinik_WebShell_Windows.bat"
endlocal
exit /b 0
