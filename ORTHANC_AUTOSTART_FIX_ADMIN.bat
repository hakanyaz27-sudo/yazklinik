@echo off
setlocal

sc stop Orthanc >nul 2>&1
sc config Orthanc start= disabled >nul 2>&1

schtasks /Delete /TN "YazKlinik_Orthanc_Autostart" /F >nul 2>&1
schtasks /Create /TN "YazKlinik_Orthanc_Autostart" /SC ONSTART /DELAY 0000:45 /RU "SYSTEM" /RL HIGHEST /TR "cmd.exe /c ""%~dp0ORTHANC_BOOT_START.cmd""" /F
schtasks /Run /TN "YazKlinik_Orthanc_Autostart"

echo Kuruldu. 10 sn sonra port kontrol edin: 8042 / 4242
pause
endlocal
