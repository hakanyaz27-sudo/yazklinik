@echo off
setlocal
cd /d "%~dp0"
echo Firewall geri alma araci.
echo Son security_backups klasorundeki firewall-before-lockdown.wfw dosyasi iceri alinacak.
for /f "delims=" %%D in ('dir /b /ad /o-d "%~dp0security_backups" 2^>nul') do (
  set "LAST=%%D"
  goto :found
)
echo Backup bulunamadi.
pause
exit /b 1
:found
set "WFW=%~dp0security_backups\%LAST%\firewall-before-lockdown.wfw"
if not exist "%WFW%" (
  echo Backup dosyasi yok: "%WFW%"
  pause
  exit /b 1
)
echo Import: "%WFW%"
netsh advfirewall import "%WFW%"
echo.
echo Geri alma tamamlandi.
pause
