@echo off
setlocal EnableExtensions
cd /d "%~dp0"
call "%~dp0D700_GUVENLI_DURUM_KONTROL.bat" aggressive
exit /b %ERRORLEVEL%
