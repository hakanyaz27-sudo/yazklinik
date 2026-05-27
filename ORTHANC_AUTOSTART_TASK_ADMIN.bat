@echo off
setlocal

REM 1) Kirik Orthanc servisini devre disi birak
sc stop Orthanc >nul 2>&1
sc config Orthanc start= disabled >nul 2>&1

REM 2) Baslangicta Orthanc helper calissin (SYSTEM)
schtasks /Delete /TN "YazKlinik_Orthanc_Autostart" /F >nul 2>&1
schtasks /Create /TN "YazKlinik_Orthanc_Autostart" /SC ONSTART /RU "SYSTEM" /RL HIGHEST /TR "\"%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe\" -NoProfile -ExecutionPolicy Bypass -File \"%~dp0D700_ORTHANC_MANUEL_BASLAT.ps1\" -Mode start -Quiet 1" /F

REM 3) Simdi bir kez calistir
schtasks /Run /TN "YazKlinik_Orthanc_Autostart"
timeout /t 4 /nobreak >nul

REM 4) Durum
schtasks /Query /TN "YazKlinik_Orthanc_Autostart" /V /FO LIST
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0D700_ORTHANC_MANUEL_BASLAT.ps1" -Mode status -Quiet 0

pause
endlocal
