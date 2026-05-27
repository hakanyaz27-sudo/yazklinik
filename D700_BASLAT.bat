@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul
title YazKlinik D700 - Hizli Baslat
cd /d "%~dp0"
cls

set "D700_LAUNCH_LOCK=%TEMP%\YazKlinik_D700_BASLAT.lock"
if exist "%D700_LAUNCH_LOCK%" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$p='%D700_LAUNCH_LOCK%'; $root=(Resolve-Path '%~dp0').Path.TrimEnd('\'); if(Test-Path -LiteralPath $p){ $age=((Get-Date)-(Get-Item -LiteralPath $p).LastWriteTime).TotalMinutes; $svc=Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -and $_.CommandLine.Contains($root) -and $_.CommandLine.Contains('D700_SERVICE_RUNNER.py') } | Select-Object -First 1; $self=$PID; $launcher=Get-CimInstance Win32_Process | Where-Object { $_.ProcessId -ne $self -and ($_.Name -eq 'cmd.exe' -or $_.Name -eq 'powershell.exe') -and $_.CommandLine -and $_.CommandLine.ToLower().Contains($root.ToLower()) -and $_.CommandLine.ToLower().Contains('d700_baslat.bat') } | Select-Object -First 1; if((-not $svc) -and (-not $launcher) -and ($age -gt 1.5)){ Remove-Item -LiteralPath $p -Recurse -Force -ErrorAction SilentlyContinue } }"
)
mkdir "%D700_LAUNCH_LOCK%" >nul 2>&1
if errorlevel 1 (
  echo.
  echo  YazKlinik D700 baslatma zaten calisiyor. Biraz bekleyin.
  timeout /t 3 /nobreak >nul
  exit /b 0
)

echo.
echo  ============================================================
echo                YazKlinik D700 - Hizli Baslat (Asustor)
echo  ============================================================
echo  Klasor: %CD%
echo.

REM 1) config.env dosyasini oku ve env var olarak set et
if exist "config.env" (
  echo  [+] config.env okuniyor...
  for /f "usebackq eol=# tokens=1,* delims==" %%a in ("config.env") do (
    if not "%%~a"=="" if not "%%~b"=="" set "%%~a=%%~b"
  )
  echo      OK
) else (
  echo  [!] config.env YOK - default'lar kullanilacak
  set "YAZKLINIK_NAS_ROOT=\\asustor\Voluson"
  set "YAZKLINIK_DB_PATH=D:\\YazKlinik_Final_D700\local_db\yazklinik_v68.sqlite3"
  set "YAZKLINIK_WEB_PORT=5443"
  set "YAZKLINIK_HTTPS_PORT=5443"
  set "YAZKLINIK_ENABLE_HTTPS=1"
  set "YAZKLINIK_WAITRESS_THREADS=12"
  set "PYTHONUTF8=1"
  set "PYTHONIOENCODING=utf-8"
  set "PYTHONUNBUFFERED=1"
)

if not defined YAZKLINIK_WAITRESS_THREADS set "YAZKLINIK_WAITRESS_THREADS=12"
REM D700 2026-05-27: lock takeover varsayilan kapali. Acik olursa twin runner
REM agaclarinda aktif child surecler kill edilip restart dongusu olusabiliyor.
if not defined YAZKLINIK_LOCK_TAKEOVER set "YAZKLINIK_LOCK_TAKEOVER=0"
if not defined YAZKLINIK_CADDY_ACCEL set "YAZKLINIK_CADDY_ACCEL=1"
if not defined YAZKLINIK_CADDY_HTTPS_PORT set "YAZKLINIK_CADDY_HTTPS_PORT=5443"
if not defined YAZKLINIK_FORCE_RESTART set "YAZKLINIK_FORCE_RESTART=0"
if not defined YAZKLINIK_LAUNCH_COOLDOWN_MIN set "YAZKLINIK_LAUNCH_COOLDOWN_MIN=15"
set "YAZKLINIK_WAITRESS_THREADS_RAW=%YAZKLINIK_WAITRESS_THREADS%"
for /f "delims=0123456789" %%x in ("%YAZKLINIK_WAITRESS_THREADS_RAW%") do set "YAZKLINIK_WAITRESS_THREADS=12"
if %YAZKLINIK_WAITRESS_THREADS% LSS 12 (
  echo  [i] Waitress thread floor uygulan?yor: %YAZKLINIK_WAITRESS_THREADS% ^> 12
  set "YAZKLINIK_WAITRESS_THREADS=12"
)

if /I not "%YAZKLINIK_FORCE_RESTART%"=="1" (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path '%~dp0').Path.TrimEnd('\').ToLower(); $all=Get-CimInstance Win32_Process; $anySvc=$false; foreach($svc in @('D700_HEALTH_MONITOR.py','yazklinik_web.py','yazklinik_whisper_service.py','yazklinik_piper_service.py')){ $svcLower=$svc.ToLower(); foreach($p in $all){ $cmd=[string]$p.CommandLine; if(($p.Name -match '^pythonw?\.exe$') -and $cmd){ $cmdLower=$cmd.ToLower(); if($cmdLower.Contains('d700_service_runner.py') -and $cmdLower.Contains($svcLower)){ $anySvc=$true; break } } }; if($anySvc){ break } }; if($anySvc){ exit 43 } else { exit 0 }"
  if "%ERRORLEVEL%"=="43" (
    echo  [i] Temel D700 servisleri zaten aktif; gereksiz tam restart atlandi.
    echo      Acil tam restart icin: set YAZKLINIK_FORCE_RESTART=1 ^&^& D700_BASLAT.bat
    rmdir "%D700_LAUNCH_LOCK%" >nul 2>&1
    exit /b 0
  )
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$all=Get-CimInstance Win32_Process; $hasMon=$false; foreach($p in $all){ $cmd=[string]$p.CommandLine; if(($p.Name -match '^pythonw?\.exe$') -and $cmd -and $cmd.Contains('D700_SERVICE_RUNNER.py') -and $cmd.Contains('D700_HEALTH_MONITOR.py')){ $hasMon=$true; break } }; if($hasMon){ exit 45 } else { exit 0 }"
  if "%ERRORLEVEL%"=="45" (
    echo  [i] Health Monitor aktif; gereksiz tam restart atlandi.
    echo      Zorla restart icin: set YAZKLINIK_FORCE_RESTART=1 ^&^& D700_BASLAT.bat
    rmdir "%D700_LAUNCH_LOCK%" >nul 2>&1
    exit /b 0
  )
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$all=Get-CimInstance Win32_Process; function HasSvc([string]$svc){ foreach($p in $all){ $cmd=[string]$p.CommandLine; if(($p.Name -match '^pythonw?\.exe$') -and $cmd -and $cmd.Contains('D700_SERVICE_RUNNER.py') -and $cmd.Contains($svc)){ return $true } }; return $false }; $hasWeb=HasSvc 'yazklinik_web.py'; $hasMon=HasSvc 'D700_HEALTH_MONITOR.py'; if($hasWeb -and $hasMon){ exit 44 } else { exit 0 }"
  if "%ERRORLEVEL%"=="44" (
    echo  [i] Web + Health Monitor zaten aktif; gereksiz tam restart atlandi.
    echo      Zorla restart icin: set YAZKLINIK_FORCE_RESTART=1 ^&^& D700_BASLAT.bat
    rmdir "%D700_LAUNCH_LOCK%" >nul 2>&1
    exit /b 0
  )
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$all=Get-CimInstance Win32_Process; $expect=@('yazklinik_web.py','D700_HEALTH_MONITOR.py','yazklinik_whisper_service.py','yazklinik_piper_service.py'); $portalEnabled=([string]$env:YAZKLINIK_PATIENT_PORTAL_ENABLED).Trim().ToLower(); if($portalEnabled -notin @('0','false','no','off','hayir','kapali')){ $expect += 'yazklinik_patient_portal_public.py' }; $xtts=([string]$env:YAZKLINIK_XTTS_ENABLED).Trim().ToLower(); if($xtts -in @('1','true','yes','on','evet','aktif')){ $expect += 'yazklinik_xtts_service.py' }; $comfyHome=[string]$env:YAZKLINIK_COMFYUI_HOME; if([string]::IsNullOrWhiteSpace($comfyHome)){ $comfyHome='C:\YazKlinik_AI\ComfyUI' }; if(Test-Path (Join-Path $comfyHome 'main.py')){ $expect += 'D700_COMFYUI_RUNNER.py' }; $sipEnabled=([string]$env:YAZKLINIK_SIP_ENABLED).Trim().ToLower(); $sipPass=[string]$env:YAZKLINIK_SIP_PASSWORD; $sipOff=($sipEnabled -in @('0','false','no','off','hayir','kapali')); if(((-not $sipOff) -and ($sipEnabled -in @('1','true','yes','on','evet','aktif'))) -or ((-not $sipOff) -and (-not [string]::IsNullOrWhiteSpace($sipPass)))){ $expect += 'yazklinik_sip_alex_client.py' }; $missing=@(); foreach($svc in $expect){ $ok=$false; foreach($p in $all){ $cmd=[string]$p.CommandLine; if(($p.Name -match '^pythonw?\.exe$') -and $cmd -and $cmd.Contains('D700_SERVICE_RUNNER.py') -and $cmd.Contains($svc)){ $ok=$true; break } }; if(-not $ok){ $missing += $svc } }; if($missing.Count -eq 0){ exit 41 } else { exit 0 }"
  if "%ERRORLEVEL%"=="41" (
    echo  [i] D700 stack zaten calisiyor; restart atlandi.
    echo      Zorla restart icin: set YAZKLINIK_FORCE_RESTART=1 ^&^& D700_BASLAT.bat
    rmdir "%D700_LAUNCH_LOCK%" >nul 2>&1
    exit /b 0
  )
  powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path '%~dp0').Path.TrimEnd('\'); $all=Get-CimInstance Win32_Process; function HasSvc([string]$svc){ foreach($p in $all){ $cmd=[string]$p.CommandLine; if(($p.Name -match '^pythonw?\.exe$') -and $cmd -and $cmd.Contains('D700_SERVICE_RUNNER.py') -and $cmd.Contains($svc)){ return $true } }; return $false }; $hasWeb=HasSvc 'yazklinik_web.py'; $hasMonitor=HasSvc 'D700_HEALTH_MONITOR.py'; if($hasWeb -or (-not $hasMonitor)){ exit 0 }; $coreUp=((HasSvc 'yazklinik_whisper_service.py') -and (HasSvc 'yazklinik_piper_service.py')); if(-not $coreUp){ exit 0 }; $selfLock=Join-Path $root 'runtime_state\service_locks\D700_HEALTH_MONITOR.self.lock'; if(-not (Test-Path $selfLock)){ exit 0 }; $ageMin=((Get-Date)-(Get-Item $selfLock).LastWriteTime).TotalMinutes; if($ageMin -le 15){ exit 42 } else { exit 0 }"
  if "%ERRORLEVEL%"=="42" (
    echo  [i] Web gecis/boot penceresi algilandi; tum stack restart atlandi.
    echo      Health Monitor web'i toparlayana kadar bekleniyor.
    rmdir "%D700_LAUNCH_LOCK%" >nul 2>&1
    exit /b 0
  )
)

powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path '%~dp0').Path.TrimEnd('\'); $dir=Join-Path $root 'runtime_state\autostart'; New-Item -ItemType Directory -Path $dir -Force | Out-Null; $stamp=Join-Path $dir 'd700_last_launch.stamp'; (Get-Date).ToString('o') | Set-Content -LiteralPath $stamp -Encoding ascii"

REM 1a) RTX5090/Ollama startup profile (session-scoped, inherited by child services)
if not defined YAZKLINIK_RTX5090_STARTUP_PROFILE set "YAZKLINIK_RTX5090_STARTUP_PROFILE=1"
if "%YAZKLINIK_RTX5090_STARTUP_PROFILE%"=="1" (
  if not defined OLLAMA_CONTEXT_LENGTH (
    if defined YAZKLINIK_OLLAMA_CTX_LIMIT (
      set "OLLAMA_CONTEXT_LENGTH=%YAZKLINIK_OLLAMA_CTX_LIMIT%"
    ) else (
      set "OLLAMA_CONTEXT_LENGTH=8192"
    )
  )
  if not defined OLLAMA_NUM_PARALLEL (
    if defined YAZKLINIK_OLLAMA_NUM_PARALLEL (
      set "OLLAMA_NUM_PARALLEL=%YAZKLINIK_OLLAMA_NUM_PARALLEL%"
    ) else (
      set "OLLAMA_NUM_PARALLEL=1"
    )
  )
  if not defined OLLAMA_MAX_QUEUE (
    if defined YAZKLINIK_OLLAMA_MAX_QUEUE (
      set "OLLAMA_MAX_QUEUE=%YAZKLINIK_OLLAMA_MAX_QUEUE%"
    ) else (
      set "OLLAMA_MAX_QUEUE=256"
    )
  )
  if not defined PYTORCH_CUDA_ALLOC_CONF (
    set "PYTORCH_CUDA_ALLOC_CONF=backend:cudaMallocAsync"
  )
  if not defined PYTORCH_ALLOC_CONF set "PYTORCH_ALLOC_CONF=%PYTORCH_CUDA_ALLOC_CONF%"
  echo  [+] RTX startup profile aktif
  echo      OLLAMA_CONTEXT_LENGTH=%OLLAMA_CONTEXT_LENGTH% ^| OLLAMA_NUM_PARALLEL=%OLLAMA_NUM_PARALLEL% ^| OLLAMA_MAX_QUEUE=%OLLAMA_MAX_QUEUE%
  echo      PYTORCH_CUDA_ALLOC_CONF=%PYTORCH_CUDA_ALLOC_CONF%
  if not defined YAZKLINIK_POWER_PLAN_STARTUP set "YAZKLINIK_POWER_PLAN_STARTUP=1"
  if "%YAZKLINIK_POWER_PLAN_STARTUP%"=="1" (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; $dup=powercfg -duplicatescheme 'e9a42b02-d5df-448d-aa00-03f14749eb61' 2>&1; $guid=[regex]::Match(($dup -join \"`n\"),'[0-9a-fA-F-]{36}').Value; if(-not $guid){$line=powercfg /list | Select-String -Pattern 'Nihai Performans|Ultimate Performance|High performance|Yuksek performans' | Select-Object -First 1; if($line){$guid=[regex]::Match($line.Line,'[0-9a-fA-F-]{36}').Value}}; if($guid){powercfg /setactive $guid | Out-Null; Write-Host ('     Power plan active: ' + $guid)}"
  )
)

echo  [+] NAS Root : %YAZKLINIK_NAS_ROOT%
echo  [+] DB Path  : %YAZKLINIK_DB_PATH%
echo  [+] HTTP Port: %YAZKLINIK_WEB_PORT%
echo  [+] SSL Aktif: %YAZKLINIK_ENABLE_HTTPS%
echo  [+] Threads : %YAZKLINIK_WAITRESS_THREADS%
echo.

REM 1b) Harici araclar: FFmpeg + Tesseract + Browser yollari bu launcher icin garanti.
set "D700_PROJECT_FFMPEG=%~dp0models\ffmpeg\extracted\ffmpeg-n7.1-latest-win64-gpl-shared-7.1\bin"
if exist "%D700_PROJECT_FFMPEG%\ffmpeg.exe" (
  set "YAZKLINIK_FFMPEG_BIN=%D700_PROJECT_FFMPEG%"
  set "FFMPEG_BINARY=%D700_PROJECT_FFMPEG%\ffmpeg.exe"
  if exist "%D700_PROJECT_FFMPEG%\ffprobe.exe" set "FFPROBE_BINARY=%D700_PROJECT_FFMPEG%\ffprobe.exe"
  set "PATH=%D700_PROJECT_FFMPEG%;%PATH%"
) else (
  for /f "usebackq delims=" %%p in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'; $exe=Get-ChildItem -LiteralPath $root -Filter ffmpeg.exe -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName; if($exe){Split-Path -Parent $exe}"`) do (
    if exist "%%p\ffmpeg.exe" (
      set "YAZKLINIK_FFMPEG_BIN=%%p"
      set "FFMPEG_BINARY=%%p\ffmpeg.exe"
      if exist "%%p\ffprobe.exe" set "FFPROBE_BINARY=%%p\ffprobe.exe"
      set "PATH=%%p;%PATH%"
    )
  )
)
if exist "C:\Program Files\Tesseract-OCR\tesseract.exe" (
  set "YAZKLINIK_TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe"
  set "TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe"
  set "YAZKLINIK_TESSDATA_PREFIX=C:\Program Files\Tesseract-OCR\tessdata"
  set "PATH=C:\Program Files\Tesseract-OCR;%PATH%"
)
if not defined YAZKLINIK_TESSDATA_PREFIX if exist "%~dp0tools\tesseract\tessdata\tur.traineddata" (
  set "YAZKLINIK_TESSDATA_PREFIX=%~dp0tools\tesseract\tessdata"
  set "TESSDATA_PREFIX=%~dp0tools\tesseract\tessdata"
)
if exist "%ProgramFiles%\Google\Chrome\Application\chrome.exe" set "YAZKLINIK_CHROME_EXE=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
if not defined YAZKLINIK_CHROME_EXE if exist "%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe" set "YAZKLINIK_CHROME_EXE=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "YAZKLINIK_EDGE_EXE=%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe"
if not defined YAZKLINIK_EDGE_EXE if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "YAZKLINIK_EDGE_EXE=%ProgramFiles%\Microsoft\Edge\Application\msedge.exe"
for /f "usebackq delims=" %%p in (`powershell -NoProfile -ExecutionPolicy Bypass -Command "$roots=@($env:ProgramFiles + '\Microsoft\EdgeWebView\Application', ${env:ProgramFiles(x86)} + '\Microsoft\EdgeWebView\Application'); $exe=$roots | ForEach-Object { if(Test-Path $_){ Get-ChildItem -LiteralPath $_ -Filter msedgewebview2.exe -Recurse -ErrorAction SilentlyContinue } } | Sort-Object LastWriteTime -Descending | Select-Object -First 1 -ExpandProperty FullName; if($exe){$exe}"`) do set "YAZKLINIK_WEBVIEW2_EXE=%%p"

REM 2) Hazir .venv bul - D700 yerel venv zorunlu
set "VENV_PATH="
if exist "%~dp0.venv\Scripts\python.exe" (
  set "VENV_PATH=%~dp0.venv"
  echo  [+] Yerel venv: %~dp0.venv
) else (
  echo  [!] Calisir bir .venv yok. D700\.venv bulunamadi. Once .venv kurulumunu tamamla.
  rmdir "%D700_LAUNCH_LOCK%" >nul 2>&1
  pause
  exit /b 1
)

if not defined YAZKLINIK_LAN_IP set "YAZKLINIK_LAN_IP=192.168.1.50"
if not defined YAZKLINIK_SERVER_URL (
  if "%YAZKLINIK_ENABLE_HTTPS%"=="1" (
    set "YAZKLINIK_SERVER_URL=https://%YAZKLINIK_LAN_IP%:%YAZKLINIK_HTTPS_PORT%"
  ) else if "%YAZKLINIK_CADDY_ACCEL%"=="1" (
    set "YAZKLINIK_SERVER_URL=https://%YAZKLINIK_LAN_IP%:%YAZKLINIK_CADDY_HTTPS_PORT%"
  ) else (
    set "YAZKLINIK_SERVER_URL=http://%YAZKLINIK_LAN_IP%:%YAZKLINIK_WEB_PORT%"
  )
)
set "PYTHONW_EXE=%VENV_PATH%\Scripts\pythonw.exe"
if not exist "%PYTHONW_EXE%" set "PYTHONW_EXE=%VENV_PATH%\Scripts\python.exe"

REM D700: Foto cift tik protokolu server helper'a degil, bu cihazdaki terminal helper'a baglanir.
REM Bu sayede terminalden cift tik yapinca JPG bu bilgisayarin varsayilan foto uygulamasinda acilir.
if exist "%~dp0YAZKLINIK_TERMINAL_YARDIMCI_KUR.bat" (
  call "%~dp0YAZKLINIK_TERMINAL_YARDIMCI_KUR.bat" /silent >nul 2>&1
)

if not defined YAZKLINIK_WEB_URL set "YAZKLINIK_WEB_URL=%YAZKLINIK_SERVER_URL%"
if not defined YAZKLINIK_AI_SERVER_URL set "YAZKLINIK_AI_SERVER_URL=%YAZKLINIK_SERVER_URL%"
if not defined YAZKLINIK_DEFAULT_SERVER_URL set "YAZKLINIK_DEFAULT_SERVER_URL=%YAZKLINIK_SERVER_URL%"
if not defined YAZKLINIK_PATIENT_PORTAL_ENABLED set "YAZKLINIK_PATIENT_PORTAL_ENABLED=1"
if not defined YAZKLINIK_PATIENT_PORTAL_BASE_URL set "YAZKLINIK_PATIENT_PORTAL_BASE_URL=https://hasta.yazhakan.com.tr"
if not defined YAZKLINIK_PATIENT_PORTAL_HOST set "YAZKLINIK_PATIENT_PORTAL_HOST=127.0.0.1"
if not defined YAZKLINIK_PATIENT_PORTAL_PORT set "YAZKLINIK_PATIENT_PORTAL_PORT=5053"
set "YAZKLINIK_ALLOW_LOCAL_TERMINAL_SERVER=1"
if not defined YAZKLINIK_TERMINAL_TOKEN for /f %%t in ('powershell -NoProfile -Command "[guid]::NewGuid().ToString(''N'')"') do set "YAZKLINIK_TERMINAL_TOKEN=%%t"
REM D700: terminal sync app startup'i bloke etmemeli; server kapaliyken
REM uzun sure beklerse web/servis launch zinciri takiliyordu.
start "D700 Terminal Sync" /b "%PYTHONW_EXE%" "%~dp0D700_TERMINAL_SYNC.py" --server-url "%YAZKLINIK_SERVER_URL%" >nul 2>&1

REM 3) Eski D700 servislerini durdur (python.exe ve pythonw.exe)
echo  [+] Eski D700 arka plan servisleri temizleniyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$names=@('yazklinik_whisper_service.py','yazklinik_xtts_service.py','D700_HEALTH_MONITOR.py','yazklinik_piper_service.py','yazklinik_sip_alex_client.py','yazklinik_patient_portal_public.py','yazklinik_web.py'); Get-CimInstance Win32_Process | Where-Object { $cmd=$_.CommandLine; $_.Name -match '^pythonw?\.exe$' -and $cmd -and ( $cmd.Contains('D700_SERVICE_RUNNER.py') -or (($names | Where-Object { $cmd.Contains($_) }).Count -gt 0) ) } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host ('     Eski servis PID ' + $_.ProcessId + ' durduruldu') } catch {} }"
timeout /t 2 /nobreak >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command "$root=(Resolve-Path '%~dp0').Path.TrimEnd('\'); Get-ChildItem -LiteralPath (Join-Path $root 'runtime_state\service_locks') -Filter '*.lock' -ErrorAction SilentlyContinue | Remove-Item -Force -ErrorAction SilentlyContinue; $lockRoot=Join-Path $env:TEMP 'YazKlinik\locks'; foreach($p in @('%YAZKLINIK_WEB_PORT%','%YAZKLINIK_HTTPS_PORT%','%YAZKLINIK_PATIENT_PORTAL_PORT%','5052','5443','5053')){ if($p){ Remove-Item -LiteralPath (Join-Path $lockRoot ('web_' + $p + '.lock')) -Force -ErrorAction SilentlyContinue } }"

REM 3a) Legacy D700/D600 proses karismasini temizle (XTTS/Health Monitor port cakismasi)
echo  [+] Legacy D700/D600 servisleri temizleniyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$rxRoot='YazKlinik_Final_D500|YazKlinik_Final_D600'; $rxSvc='D500_SERVICE_RUNNER\.py|D500_HEALTH_MONITOR\.py|yazklinik_xtts_service\.py|yazklinik_whisper_service\.py|yazklinik_piper_service\.py|yazklinik_sip_alex_client\.py|yazklinik_web\.py'; Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -and $_.CommandLine -match $rxRoot -and $_.CommandLine -match $rxSvc } | ForEach-Object { try { taskkill /PID $_.ProcessId /T /F >$null 2>&1; Write-Host ('     Legacy PID ' + $_.ProcessId + ' durduruldu') } catch {} }"
timeout /t 1 /nobreak >nul

REM 3b) Eski server zombie durdur
echo  [+] Port kontrol: %YAZKLINIK_WEB_PORT%, %YAZKLINIK_HTTPS_PORT%, %YAZKLINIK_PATIENT_PORTAL_PORT% ve fallback portlar...
set "D700_NEEDS_ADMIN_RESTART=0"
for %%P in (%YAZKLINIK_WEB_PORT% %YAZKLINIK_HTTPS_PORT% %YAZKLINIK_PATIENT_PORTAL_PORT% 5052 5443 5053) do (
  set "OLD_PID="
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%P " ^| findstr "LISTENING"') do set "OLD_PID=%%a"
  if defined OLD_PID (
    echo      Port %%P uzerindeki eski PID !OLD_PID! durduruluyor...
    taskkill /PID !OLD_PID! /F >nul 2>&1
    if errorlevel 1 (
      echo      [!] PID !OLD_PID! normal yetkiyle kapatilamadi.
      set "D700_NEEDS_ADMIN_RESTART=1"
    ) else (
      timeout /t 2 /nobreak >nul
    )
  )
)
if "%D700_NEEDS_ADMIN_RESTART%"=="1" (
  echo.
  echo  [!] Eski web sureci yonetici yetkisi istiyor.
  if /I "%YAZKLINIK_AUTO_ADMIN_WEB_RESTART%"=="1" (
    echo      AUTO mod acik -> D700_ADMIN_WEB_RESTART.bat baslatiliyor...
    start "" "%~dp0D700_ADMIN_WEB_RESTART.bat"
  ) else (
    echo      Otomatik admin-restart varsayilan olarak KAPALI.
    echo      Manuel calistir: D700_ADMIN_WEB_RESTART.bat
  )
  rmdir "%D700_LAUNCH_LOCK%" >nul 2>&1
  exit /b 5
)

REM 4) Asustor NAS erisim kontrol (isteyebilir)
echo  [+] Asustor NAS erisim kontrol...
if exist "\\asustor\Voluson" (
  echo      OK - Asustor NAS erisilebilir
) else (
  echo      [!] \\asustor\Voluson erisilmiyor - hasta klasorleri yuklenmeyecek
  echo      Cozum: NAS'a baglan veya /sistem-ayarlari'ndan path degistir
)

REM 4b) Destek servisleri: Orthanc kapaliysa baslat, Ollama kapaliysa arka planda uyandir.
echo  [+] Destek servisleri kontrol ediliyor...
if not defined YAZKLINIK_AUTOSTART_ORTHANC set "YAZKLINIK_AUTOSTART_ORTHANC=1"
if "%YAZKLINIK_AUTOSTART_ORTHANC%"=="1" (
  if exist "%~dp0D700_ORTHANC_MANUEL_BASLAT.bat" (
    call "%~dp0D700_ORTHANC_MANUEL_BASLAT.bat" /silent /autostart
  ) else (
    powershell -NoProfile -ExecutionPolicy Bypass -Command "$ErrorActionPreference='SilentlyContinue'; $svc=Get-Service -Name Orthanc -ErrorAction SilentlyContinue; if($svc -and $svc.Status -ne 'Running'){ Start-Service -Name Orthanc -ErrorAction SilentlyContinue; Start-Sleep -Seconds 2 }"
  )
)
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { Invoke-WebRequest -Uri 'http://127.0.0.1:11434/api/tags' -UseBasicParsing -TimeoutSec 2 | Out-Null } catch { $cmd=(Get-Command ollama.exe -ErrorAction SilentlyContinue).Source; if($cmd){ Start-Process -FilePath $cmd -ArgumentList 'serve' -WindowStyle Hidden -ErrorAction SilentlyContinue } }"
if not defined YAZKLINIK_CLOUDFLARED_AUTOSTART set "YAZKLINIK_CLOUDFLARED_AUTOSTART=1"
if "%YAZKLINIK_CLOUDFLARED_AUTOSTART%"=="1" (
  if exist "%~dp0D700_CLOUDFLARE_TUNNEL_BASLAT.ps1" (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0D700_CLOUDFLARE_TUNNEL_BASLAT.ps1" -Silent
  )
)

REM 5) Local DB klasoru var mi
if not exist "local_db" (
  echo  [+] local_db klasoru yaratiliyor...
  mkdir "local_db"
)
if not exist "auto_backups" (
  mkdir "auto_backups"
)

REM 5a) Database Guard: SQLite butunluk + yedek + PostgreSQL health/senkron.
echo  [+] Database Guard kontrolu...
"%VENV_PATH%\Scripts\python.exe" "%~dp0YAZKLINIK_DB_GUARD.py" --repair --keep-backups 21
if errorlevel 1 (
  echo.
  echo  [!] Database Guard hata verdi. Rapor:
  echo      %~dp0runtime_state\db_guard\last_report.txt
  if "%YAZKLINIK_DB_GUARD_STRICT%"=="0" (
    echo      STRICT=0 oldugu icin baslatmaya devam ediliyor.
  ) else (
    echo      Database netlesmeden server baslatilmadi.
    rmdir "%D700_LAUNCH_LOCK%" >nul 2>&1
    pause
    exit /b 1
  )
) else (
  echo      OK - Database saglam.
)


REM 5a-2) D700 Hardening Guard: lock, backup restore probe, log rotate, NAS soft-fail report.
echo  [+] D700 Hardening Guard kontrolu...
if exist "%~dp0D700_SYSTEM_HARDENING.py" (
  "%VENV_PATH%\Scripts\python.exe" "%~dp0D700_SYSTEM_HARDENING.py" boot-check --soft
  if errorlevel 1 (
    echo      [!] Hardening Guard uyari verdi. Detay: %~dp0runtime_state\hardening\boot_check.txt
  ) else (
    echo      OK - Hardening Guard tamam.
  )
) else (
  echo      [!] D700_SYSTEM_HARDENING.py bulunamadi.
)

REM 5a-3) Hasta Portal public servisi (port 5053) - ana programdan ayri process.
if "%YAZKLINIK_PATIENT_PORTAL_ENABLED%"=="1" (
  echo  [+] Hasta Portal public servisi (port %YAZKLINIK_PATIENT_PORTAL_PORT%)...
  set "PORTAL_OLD_PID="
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%YAZKLINIK_PATIENT_PORTAL_PORT% " ^| findstr "LISTENING"') do set "PORTAL_OLD_PID=%%a"
  if defined PORTAL_OLD_PID (
    echo      Port %YAZKLINIK_PATIENT_PORTAL_PORT% eski PID !PORTAL_OLD_PID! durduruluyor...
    taskkill /PID !PORTAL_OLD_PID! /F >nul 2>&1
    timeout /t 1 /nobreak >nul
  )
  set "PATIENT_PORTAL_LOG=%~dp0D700_patient_portal.log"
  start "" "%PYTHONW_EXE%" "%~dp0D700_SERVICE_RUNNER.py" "%~dp0yazklinik_patient_portal_public.py" "%PATIENT_PORTAL_LOG%" "%~dp0D700_patient_portal.err.log"
  echo      Hasta Portal baslatildi (gizli, log: D700_patient_portal.log)
) else (
  echo  [i] Hasta Portal public servisi kapali (YAZKLINIK_PATIENT_PORTAL_ENABLED=%YAZKLINIK_PATIENT_PORTAL_ENABLED%)
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
set "WHISPER_LOG=%~dp0D700_whisper_service.log"
start "" "%PYTHONW_EXE%" "%~dp0D700_SERVICE_RUNNER.py" "%~dp0yazklinik_whisper_service.py" "%WHISPER_LOG%" "%~dp0D700_whisper_service.err.log"
echo      Whisper service baslatildi (gizli, log: D700_whisper_service.log)

REM 5c) XTTS-v2 mikroservisi (port 9002) - lokal RTX 5090 Emel/Ahmet voice clone
if not defined YAZKLINIK_XTTS_ENABLED set "YAZKLINIK_XTTS_ENABLED=0"
if "%YAZKLINIK_XTTS_ENABLED%"=="1" (
  echo  [+] XTTS-v2 mikroservisi ^(port 9002^)...
  set "XTTS_OLD_PID="
  for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":9002 " ^| findstr "LISTENING"') do set "XTTS_OLD_PID=%%a"
  if defined XTTS_OLD_PID (
    echo      Port 9002 eski PID !XTTS_OLD_PID! durduruluyor...
    taskkill /PID !XTTS_OLD_PID! /F >nul 2>&1
    timeout /t 1 /nobreak >nul
  )
  if not defined YAZKLINIK_XTTS_SERVICE_PORT set "YAZKLINIK_XTTS_SERVICE_PORT=9002"
  set "COQUI_TOS_AGREED=1"
  set "XTTS_LOG=%~dp0D700_xtts_service.log"
  start "" "%PYTHONW_EXE%" "%~dp0D700_SERVICE_RUNNER.py" "%~dp0yazklinik_xtts_service.py" "%XTTS_LOG%" "%~dp0D700_xtts_service.err.log"
  echo      XTTS service baslatildi ^(gizli, log: D700_xtts_service.log^)
) else (
  echo  [i] XTTS-v2 kapali ^(YAZKLINIK_XTTS_ENABLED=%YAZKLINIK_XTTS_ENABLED%^)
)

REM 5e) Health Monitor (her 30sn'de servis check + dusenleri restart)
echo  [+] Health Monitor baslatiliyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$all=Get-CimInstance Win32_Process; $hasMon=$false; foreach($p in $all){ $cmd=[string]$p.CommandLine; if(($p.Name -match '^pythonw?\.exe$') -and $cmd -and $cmd.Contains('D700_SERVICE_RUNNER.py') -and $cmd.Contains('D700_HEALTH_MONITOR.py')){ $hasMon=$true; break } }; if($hasMon){ exit 41 } else { exit 0 }"
if "%ERRORLEVEL%"=="41" (
  echo      [i] Health Monitor zaten calisiyor; yeniden baslatilmadi.
) else (
  set "HEALTH_LOG=%~dp0D700_health_monitor.log"
  start "" "%PYTHONW_EXE%" "%~dp0D700_SERVICE_RUNNER.py" "%~dp0D700_HEALTH_MONITOR.py" "%HEALTH_LOG%" "%~dp0D700_health_monitor.err.log"
  echo      Health Monitor baslatildi (gizli, log: D700_health_monitor.log)
)

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
set "PIPER_LOG=%~dp0D700_piper_service.log"
start "" "%PYTHONW_EXE%" "%~dp0D700_SERVICE_RUNNER.py" "%~dp0yazklinik_piper_service.py" "%PIPER_LOG%" "%~dp0D700_piper_service.err.log"
echo      Piper service baslatildi (gizli, log: D700_piper_service.log)

REM 5d-2) ComfyUI HD Studio servisi (port 8188)
echo  [+] ComfyUI HD Studio servisi (port 8188)...
set "COMFYUI_OLD_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8188 " ^| findstr "LISTENING"') do set "COMFYUI_OLD_PID=%%a"
if defined COMFYUI_OLD_PID (
  echo      Port 8188 eski PID !COMFYUI_OLD_PID! durduruluyor...
  taskkill /PID !COMFYUI_OLD_PID! /F >nul 2>&1
  timeout /t 1 /nobreak >nul
)
if not defined YAZKLINIK_COMFYUI_HOME set "YAZKLINIK_COMFYUI_HOME=C:\YazKlinik_AI\ComfyUI"
if not defined YAZKLINIK_COMFYUI_URL set "YAZKLINIK_COMFYUI_URL=http://127.0.0.1:8188"
if exist "%YAZKLINIK_COMFYUI_HOME%\main.py" (
  start "" "%PYTHONW_EXE%" "%~dp0D700_SERVICE_RUNNER.py" "%~dp0D700_COMFYUI_RUNNER.py" "%~dp0D700_comfyui.log" "%~dp0D700_comfyui.err.log"
  echo      ComfyUI baslatildi (gizli, log: D700_comfyui.log)
) else (
  echo      [!] ComfyUI kurulumu bulunamadi: %YAZKLINIK_COMFYUI_HOME%
)

REM 5f) Alex SIP dahili client (opsiyonel) - PBX 19 numara
set "YAZKLINIK_SIP_ENABLED=%YAZKLINIK_SIP_ENABLED: =%"
if not defined YAZKLINIK_SIP_ENABLED if defined YAZKLINIK_SIP_PASSWORD set "YAZKLINIK_SIP_ENABLED=1"
if "%YAZKLINIK_SIP_ENABLED%"=="0" goto D700_SKIP_SIP_ALEX
echo  [+] Alex SIP dahili client...
if not defined YAZKLINIK_SIP_CONTROL_PORT set "YAZKLINIK_SIP_CONTROL_PORT=9019"
if not defined YAZKLINIK_SIP_LOCAL_PORT set "YAZKLINIK_SIP_LOCAL_PORT=5079"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Get-CimInstance Win32_Process | Where-Object { $_.Name -match '^pythonw?\.exe$' -and $_.CommandLine -and ($_.CommandLine.Contains('D700_SERVICE_RUNNER.py') -and $_.CommandLine.Contains('yazklinik_sip_alex_client.py') -or $_.CommandLine.Contains('D700_sip_alex.log')) } | ForEach-Object { try { Stop-Process -Id $_.ProcessId -Force -ErrorAction Stop; Write-Host ('     Eski SIP PID ' + $_.ProcessId + ' durduruldu') } catch {} }"
set "SIP_ALEX_OLD_PID="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%YAZKLINIK_SIP_CONTROL_PORT% " ^| findstr "LISTENING"') do set "SIP_ALEX_OLD_PID=%%a"
if defined SIP_ALEX_OLD_PID (
  echo      Eski Alex SIP PID !SIP_ALEX_OLD_PID! durduruluyor...
  taskkill /PID !SIP_ALEX_OLD_PID! /F >nul 2>&1
  timeout /t 1 /nobreak >nul
)
set "SIP_ALEX_LOG=%~dp0D700_sip_alex.log"
start "" "%PYTHONW_EXE%" "%~dp0D700_SERVICE_RUNNER.py" "%~dp0yazklinik_sip_alex_client.py" "%SIP_ALEX_LOG%" "%~dp0D700_sip_alex.err.log"
echo      Alex SIP client baslatildi ^(gizli, log: D700_sip_alex.log^)
:D700_SKIP_SIP_ALEX

REM 6) Server BASLAT (arka planda)
echo  ============================================================
echo                  Server BASLIYOR
echo  ============================================================
echo  Adres   : http://%YAZKLINIK_LAN_IP%:%YAZKLINIK_WEB_PORT%
if "%YAZKLINIK_ENABLE_HTTPS%"=="1" (
  echo  HTTPS   : https://%YAZKLINIK_LAN_IP%:%YAZKLINIK_HTTPS_PORT%
  echo  Dis URL : https://176.236.92.142:65187  ^(modem dis 65187 -^> ic %YAZKLINIK_HTTPS_PORT%^)
 ) else if "%YAZKLINIK_CADDY_ACCEL%"=="1" (
  echo  HTTPS   : https://%YAZKLINIK_LAN_IP%:%YAZKLINIK_CADDY_HTTPS_PORT%  ^(Caddy hiz katmani^)
  echo  Dis URL : https://176.236.92.142:65187  ^(modem dis 65187 -^> ic %YAZKLINIK_CADDY_HTTPS_PORT%^)
) else (
  echo  HTTPS   : kapali - %YAZKLINIK_WEB_PORT% SSL'siz HTTP olarak calisir
  echo  Dis URL : http://176.236.92.142:65187  ^(modem dis 65187 -^> ic %YAZKLINIK_WEB_PORT%^)
)
echo  Giris   : doktor / users.json guncel sifre
echo  NAS     : %YAZKLINIK_NAS_ROOT%
echo  DB      : %YAZKLINIK_DB_PATH%
echo.
echo  Lutfen bekleyin (5-15 saniye)...
echo.

set "STDOUT_LOG=%~dp0D700_server.log"
set "STDERR_LOG=%~dp0D700_server_HATA.log"
set "YAZKLINIK_ALLOW_DIRECT_WEB=manual-dev-ok"
set "YAZKLINIK_D700_SERVICE_RUNNER=1"
set "YAZKLINIK_D500_SERVICE_RUNNER=1"

start "" "%PYTHONW_EXE%" "%~dp0D700_SERVICE_RUNNER.py" "%~dp0yazklinik_web.py" "%STDOUT_LOG%" "%STDERR_LOG%"
echo      Web server baslatildi (gizli)
if "%YAZKLINIK_CADDY_ACCEL%"=="1" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0D700_CADDY_ACCEL_BASLAT.ps1" >nul 2>&1
  echo      Caddy hiz katmani baslatildi (HTTPS :%YAZKLINIK_CADDY_HTTPS_PORT%)
)

REM 7) Hazir olmasini bekle (max 180 sn). PowerShell yerine curl kullaniyoruz
REM cunku PS5.1 ServerCertificateValidationCallback self-signed bypass'i guvenilir degil.
REM Windows 10/11'de curl built-in. -k self-signed cert kabul eder.
set "READY=0"
for /l %%i in (1,1,180) do (
  if !READY!==0 (
    timeout /t 1 /nobreak >nul
    set "HTTP_CODE="
    curl -k -s -o nul --connect-timeout 2 --max-time 4 -w "%%{http_code}" "%YAZKLINIK_SERVER_URL%/api/terminal/ping-fast" > "%TEMP%\yk_ready.txt" 2>nul
    set /p HTTP_CODE=<"%TEMP%\yk_ready.txt"
    if "!HTTP_CODE!"=="200" set "READY=1"
    if !READY!==0 (
      curl -k -s -o nul --connect-timeout 2 --max-time 4 -w "%%{http_code}" "%YAZKLINIK_SERVER_URL%/api/sistem-durumu" > "%TEMP%\yk_ready.txt" 2>nul
      set /p HTTP_CODE=<"%TEMP%\yk_ready.txt"
      if "!HTTP_CODE!"=="200" set "READY=1"
    )
    if !READY!==0 (
      curl -k -s -o nul --connect-timeout 2 --max-time 4 -w "%%{http_code}" "%YAZKLINIK_SERVER_URL%/giris" > "%TEMP%\yk_ready.txt" 2>nul
      set /p HTTP_CODE=<"%TEMP%\yk_ready.txt"
      if not "!HTTP_CODE!"=="" if not "!HTTP_CODE!"=="000" set "READY=1"
    )
  )
)
del "%TEMP%\yk_ready.txt" >nul 2>&1

if "%READY%"=="1" (
  echo  ============================================================
  echo   [BASARI] Server hazir! WebShell aciliyor...
  echo  ============================================================
  echo  [+] Altyapi Guard kontrolu...
  "%VENV_PATH%\Scripts\python.exe" "%~dp0yazklinik_infra_guard.py" --deep
  if errorlevel 1 (
    echo      [!] Altyapi Guard kritik uyari verdi.
    echo          Detay: %~dp0runtime_state\infra_guard\last_report.txt
  ) else (
    echo      OK - Altyapi Guard temiz.
  )
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
  "%VENV_PATH%\Scripts\python.exe" "%~dp0D700_TERMINAL_SYNC.py" --server-url "%YAZKLINIK_SERVER_URL%" >nul 2>&1
  call "%~dp0YazKlinik_Web_Tarayici.bat" "%YAZKLINIK_SERVER_URL%"
  echo.
  echo  Web arayuz: normal tarayici penceresi (adres cubugu + sekmeler)
  echo  Kiosk WebShell istersen: YazKlinik_WebShell_Windows.bat
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
echo    taskkill /F /IM pythonw.exe
echo  ============================================================
echo.
rmdir "%D700_LAUNCH_LOCK%" >nul 2>&1
if "%YAZKLINIK_KEEP_LAUNCHER_OPEN%"=="1" (
  cmd /k
) else (
  echo  Pencere 3 saniye icinde kapanacak. Loglar dosyaya yaziliyor.
  timeout /t 3 /nobreak >nul
  exit /b 0
)

