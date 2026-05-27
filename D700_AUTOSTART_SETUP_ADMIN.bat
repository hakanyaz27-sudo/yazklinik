@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

net session >nul 2>&1
if errorlevel 1 (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b 0
)

set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "APP_CMD=%STARTUP%\YazKlinik_D700_AutoStart.cmd"
set "ORTH_CMD=%STARTUP%\YazKlinik_Orthanc_AutoStart.cmd"

>"%APP_CMD%" echo @echo off
>>"%APP_CMD%" echo timeout /t 25 /nobreak ^>nul
>>"%APP_CMD%" echo cd /d "%~dp0"
>>"%APP_CMD%" echo call "%~dp0D700_BASLAT.bat"

>"%ORTH_CMD%" echo @echo off
>>"%ORTH_CMD%" echo timeout /t 12 /nobreak ^>nul
>>"%ORTH_CMD%" echo cd /d "%~dp0"
>>"%ORTH_CMD%" echo call "%~dp0ORTHANC_BOOT_START.cmd"

schtasks /Delete /TN "YazKlinik_D700_AutoStart" /F >nul 2>&1
schtasks /Create /TN "YazKlinik_D700_AutoStart" /SC ONLOGON /DELAY 0000:30 /TR "cmd.exe /c ""%APP_CMD%""" /F

schtasks /Delete /TN "YazKlinik_Orthanc_Logon_AutoStart" /F >nul 2>&1
schtasks /Create /TN "YazKlinik_Orthanc_Logon_AutoStart" /SC ONLOGON /DELAY 0000:20 /TR "cmd.exe /c ""%ORTH_CMD%""" /F

schtasks /Delete /TN "YazKlinik_Orthanc_Autostart" /F >nul 2>&1
schtasks /Create /TN "YazKlinik_Orthanc_Autostart" /SC ONSTART /RU "SYSTEM" /RL HIGHEST /TR "cmd.exe /c ""%~dp0ORTHANC_BOOT_START.cmd""" /F

echo.
echo [OK] D700 autostart gorevleri kuruldu.
echo - YazKlinik_D700_AutoStart
echo - YazKlinik_Orthanc_Logon_AutoStart
echo - YazKlinik_Orthanc_Autostart

schtasks /Query /TN "YazKlinik_D700_AutoStart"
schtasks /Query /TN "YazKlinik_Orthanc_Logon_AutoStart"
schtasks /Query /TN "YazKlinik_Orthanc_Autostart"

echo.
echo Simdi test icin calistiriliyor...
schtasks /Run /TN "YazKlinik_Orthanc_Autostart" >nul 2>&1
schtasks /Run /TN "YazKlinik_D700_AutoStart" >nul 2>&1

pause
endlocal
