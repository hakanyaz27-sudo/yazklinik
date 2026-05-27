@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File ""D:\YazKlinik_Final_D700\D700_ENABLE_PG_SERVICE_ADMIN.ps1""'"
endlocal
