@echo off
setlocal
cd /d "%~dp0"
echo YazKlinik D700 guvenlik kilidi baslatiliyor...
echo Sadece dis TCP 65187 acik kalacak. Devam icin UAC onayi gerekebilir.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0SECURITY_LOCKDOWN_65187_ADMIN.ps1" -PublicPort 65187 -InternalPort 5443
echo.
echo Islem bitti. Bu pencereyi kapatabilirsiniz.
pause

