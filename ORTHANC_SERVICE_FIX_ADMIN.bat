@echo off
setlocal

sc stop Orthanc >nul 2>&1
sc delete Orthanc >nul 2>&1

sc create Orthanc binPath= "\"E:\Orthanc Server\Orthanc.exe\" \"E:\Orthanc Server\Configuration\orthanc.json\"" start= auto DisplayName= "Orthanc"
sc description Orthanc "Orthanc DICOM Server"
sc failure Orthanc reset= 86400 actions= restart/5000/restart/15000/restart/30000
sc start Orthanc

sc query Orthanc
netstat -ano | findstr :8042
netstat -ano | findstr :4242

pause
endlocal
