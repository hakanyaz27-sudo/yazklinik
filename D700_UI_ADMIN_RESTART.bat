@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process PowerShell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""%~dp0D700_UI_ADMIN_RESTART.ps1""'"
echo Eger Windows izin sorarsa EVET deyin. D700 arayuzu yeniden baslatilacak.
pause

