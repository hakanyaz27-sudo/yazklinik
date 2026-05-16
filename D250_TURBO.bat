@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title YazKlinik D250 - TURBO Temizleyici + Restart
cd /d "%~dp0"
cls

echo.
echo  ============================================================
echo            YazKlinik D250 - TURBO Mode (RAM + Cache + DB)
echo  ============================================================
echo  Bu betik su islemleri yapar:
echo    1. RAM bogucularini durdur (Logitech, Cowork VM)
echo    2. Hyper-V compute servisi Manual'a sabitle
echo    3. Eski server'i kapat
echo    4. DB VACUUM + WAL checkpoint
echo    5. Browser WebShell cache temizle
echo    6. Server'i AboveNormal oncelikle yeniden baslat
echo    7. Smoke test (CODEX_QUICK_CHECK.py)
echo  ============================================================
echo.

REM ---------------------------------------------------------------
REM 1) RAM bogucu agent'lari durdur
REM ---------------------------------------------------------------
echo  [1/7] RAM bogucu agent'lar durduruluyor...
powershell -NoProfile -Command "Get-Process logioptionsplus_agent -ErrorAction SilentlyContinue | Stop-Process -Force"
powershell -NoProfile -Command "Get-Process logioptionsplus -ErrorAction SilentlyContinue | Stop-Process -Force"
powershell -NoProfile -Command "Get-Process LogiOptionsPlus* -ErrorAction SilentlyContinue | Stop-Process -Force"
echo      OK

REM ---------------------------------------------------------------
REM 2) Hyper-V compute (Cowork/Sandbox VM) Manual yap, varsa durdur
REM ---------------------------------------------------------------
echo  [2/7] Hyper-V compute servisi Manual yapiliyor...
powershell -NoProfile -Command "Stop-Service vmcompute -Force -ErrorAction SilentlyContinue; Set-Service vmcompute -StartupType Manual -ErrorAction SilentlyContinue"
echo      OK

REM ---------------------------------------------------------------
REM 3) Eski server'i durdur (port 5052)
REM ---------------------------------------------------------------
echo  [3/7] Eski server (port 5052) durduruluyor...
set "OLD_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5052 " ^| findstr "LISTENING"') do set "OLD_PID=%%a"
if defined OLD_PID (
  echo      PID %OLD_PID% durduruluyor...
  taskkill /PID %OLD_PID% /F >nul 2>&1
  timeout /t 2 /nobreak >nul
) else (
  echo      Port 5052 zaten bos.
)

REM ---------------------------------------------------------------
REM 4) DB VACUUM + WAL checkpoint (server kapali iken)
REM ---------------------------------------------------------------
echo  [4/7] DB VACUUM + WAL checkpoint...
set "DB_PATH=D:\YazKlinik_Final_D250\local_db\yazklinik_v68.sqlite3"
set "VENV_PY=C:\Users\yazha\OneDrive\Desktop\YazKlinik_Final_D104\.venv\Scripts\python.exe"
if not exist "%VENV_PY%" set "VENV_PY=%~dp0.venv\Scripts\python.exe"
if exist "%DB_PATH%" (
  "%VENV_PY%" -c "import sqlite3,os,time;t=time.time();c=sqlite3.connect(r'%DB_PATH%',timeout=10);c.execute('PRAGMA wal_checkpoint(TRUNCATE)');c.execute('VACUUM');c.close();sz=os.path.getsize(r'%DB_PATH%')/1024/1024;print(f'      VACUUM tamam: {sz:.2f} MB, {time.time()-t:.1f} sn')"
) else (
  echo      DB bulunamadi: %DB_PATH%
)

REM ---------------------------------------------------------------
REM 5) Browser WebShell cache temizle
REM ---------------------------------------------------------------
echo  [5/7] Browser WebShell cache temizleniyor...
set "CACHE_DIR=%LOCALAPPDATA%\YazKlinik\BrowserShellCache"
if exist "%CACHE_DIR%" (
  rd /s /q "%CACHE_DIR%" >nul 2>&1
  mkdir "%CACHE_DIR%" >nul 2>&1
  echo      OK - cache sifirlandi
) else (
  echo      Cache klasoru yoktu, atlandi.
)

REM ---------------------------------------------------------------
REM 6) Server'i AboveNormal oncelikle baslat
REM ---------------------------------------------------------------
echo  [6/7] Server AboveNormal oncelikle baslatiliyor...
set "STDOUT_LOG=%~dp0D250_server.log"
set "STDERR_LOG=%~dp0D250_server_HATA.log"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUNBUFFERED=1"
set "YAZKLINIK_NAS_ROOT=\\asustor\Voluson"
set "YAZKLINIK_DB_PATH=%DB_PATH%"
set "YAZKLINIK_WEB_PORT=5443"
set "YAZKLINIK_HTTPS_PORT=5443"
set "YAZKLINIK_ENABLE_HTTPS=1"
set "YAZKLINIK_WAITRESS_THREADS=12"
set "YAZKLINIK_SERVER_URL=https://127.0.0.1:5443"
start "" /ABOVENORMAL /B "%VENV_PY%" -u "%~dp0yazklinik_web.py" 1>"%STDOUT_LOG%" 2>"%STDERR_LOG%"

REM Server hazir olmasini bekle (max 30 sn)
echo      Server hazir olmasi bekleniyor...
set "READY=0"
for /l %%i in (1,1,30) do (
  if !READY!==0 (
    timeout /t 1 /nobreak >nul
    powershell -NoProfile -Command "[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}; try { (Invoke-WebRequest 'https://127.0.0.1:5443/giris' -UseBasicParsing -TimeoutSec 1).StatusCode } catch { exit 1 }" >nul 2>&1
    if not errorlevel 1 set "READY=1"
  )
)
if "%READY%"=="1" (
  echo      OK - server hazir
) else (
  echo      [!] Server 30 sn icinde acilmadi, HATA log:
  powershell -NoProfile -Command "Get-Content '%STDERR_LOG%' -Tail 15 -EA SilentlyContinue"
  pause
  exit /b 1
)

REM ---------------------------------------------------------------
REM 7) CODEX_QUICK_CHECK.py smoke test
REM ---------------------------------------------------------------
echo  [7/7] Smoke test (CODEX_QUICK_CHECK.py)...
"%VENV_PY%" "%~dp0CODEX_QUICK_CHECK.py"

echo.
echo  ============================================================
echo   TURBO tamamlandi. Hizli olcum (cold + cached ping):
echo  ============================================================
powershell -NoProfile -Command "[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}; $t=Measure-Command{Invoke-WebRequest 'https://127.0.0.1:5443/api/terminal/ping?deep=1' -UseBasicParsing};'  cold ping = '+$t.TotalMilliseconds+' ms'; Start-Sleep 1; $t=Measure-Command{Invoke-WebRequest 'https://127.0.0.1:5443/api/terminal/ping?deep=1' -UseBasicParsing};'  cached ping = '+$t.TotalMilliseconds+' ms'; $t=Measure-Command{Invoke-WebRequest 'https://127.0.0.1:5443/hastalar' -UseBasicParsing};'  /hastalar = '+$t.TotalMilliseconds+' ms'"
echo.
echo  WebShell acmak istersen: D250_BASLAT.bat veya
echo    YazKlinik_WebShell_Windows.bat
echo  ============================================================
echo.
pause
endlocal
