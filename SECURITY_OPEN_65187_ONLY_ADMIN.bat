@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0SECURITY_OPEN_65187_ONLY_ADMIN.ps1"
