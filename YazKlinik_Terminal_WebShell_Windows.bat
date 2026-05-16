@echo off
chcp 65001 >nul
cd /d "%~dp0"
call "%~dp0YazKlinik_WebShell_Windows.bat" %*
