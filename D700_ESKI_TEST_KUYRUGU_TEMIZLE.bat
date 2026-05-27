@echo off
setlocal
cd /d "%~dp0"
echo D700 eski Codex test/compile kuyrugu temizleniyor...
echo.
if "%D700_GUARD_SECONDS%"=="" set "D700_GUARD_SECONDS=60"
if "%D700_GUARD_MIN_AGE_SECONDS%"=="" set "D700_GUARD_MIN_AGE_SECONDS=120"
if "%D700_GUARD_KILL_QUICKCHECK%"=="" set "D700_GUARD_KILL_QUICKCHECK=0"
if "%D700_GUARD_ENABLE_IMMEDIATE_RISK%"=="" set "D700_GUARD_ENABLE_IMMEDIATE_RISK=0"

for /f "delims=0123456789" %%x in ("%D700_GUARD_SECONDS%") do set "D700_GUARD_SECONDS=60"
if %D700_GUARD_SECONDS% LSS 1 set "D700_GUARD_SECONDS=1"
if %D700_GUARD_SECONDS% GTR 180 set "D700_GUARD_SECONDS=180"

set "PS_ARGS=-Seconds %D700_GUARD_SECONDS% -MinAgeSeconds %D700_GUARD_MIN_AGE_SECONDS%"
if /I "%D700_GUARD_KILL_QUICKCHECK%"=="1" set "PS_ARGS=%PS_ARGS% -KillQuickCheck"
if /I "%D700_GUARD_ENABLE_IMMEDIATE_RISK%"=="1" set "PS_ARGS=%PS_ARGS% -EnableImmediateRiskKill"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\D700_stop_old_test_queue.ps1" %PS_ARGS%
echo.
echo Bitti. Bu pencereyi kapatabilirsiniz.
if /I not "%D700_NO_PAUSE%"=="1" pause
