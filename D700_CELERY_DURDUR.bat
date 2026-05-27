@echo off
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0D700_CELERY_DURDUR.ps1" %*
exit /b %ERRORLEVEL%
