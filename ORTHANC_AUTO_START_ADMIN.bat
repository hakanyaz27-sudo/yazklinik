@echo off
sc config Orthanc start= auto
sc start Orthanc
sc query Orthanc
netstat -ano | findstr :4242
netstat -ano | findstr :8042
pause
