@echo off
setlocal
set "STARTUP=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"
set "D500_CMD=%STARTUP%\YazKlinik_D500_AutoStart.cmd"
set "ORTH_CMD=%STARTUP%\YazKlinik_Orthanc_AutoStart.cmd"

schtasks /Delete /TN "YazKlinik_D500_AutoStart" /F >nul 2>&1
schtasks /Create /TN "YazKlinik_D500_AutoStart" /SC ONLOGON /DELAY 0000:30 /TR "cmd.exe /c \"%D500_CMD%\"" /F

schtasks /Delete /TN "YazKlinik_Orthanc_Logon_AutoStart" /F >nul 2>&1
schtasks /Create /TN "YazKlinik_Orthanc_Logon_AutoStart" /SC ONLOGON /DELAY 0000:20 /TR "cmd.exe /c \"%ORTH_CMD%\"" /F

schtasks /Query /TN "YazKlinik_D500_AutoStart"
schtasks /Query /TN "YazKlinik_Orthanc_Logon_AutoStart"
endlocal
