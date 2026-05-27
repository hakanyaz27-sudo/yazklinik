@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0SECURITY_BASELINE_ZAMANLI_KUR.ps1" %*
exit /b %ERRORLEVEL%

