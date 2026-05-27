@echo off
setlocal

echo [1/6] Orthanc crash dongusu kesiliyor...
sc stop Orthanc >nul 2>&1
sc config Orthanc start= demand

echo [2/6] Acronis Scheduler2 stabil moda alin?yor...
sc stop AcrSch2Svc >nul 2>&1
sc config AcrSch2Svc start= demand >nul 2>&1

echo [3/6] Acronis Mini servis kontrol...
sc stop mmsminisrv >nul 2>&1
sc config mmsminisrv start= demand >nul 2>&1

echo [4/6] DISM onarimi basliyor (biraz surebilir)...
DISM /Online /Cleanup-Image /RestoreHealth

echo [5/6] SFC taramasi basliyor...
sfc /scannow

echo [6/6] Disk online taramasi...
chkdsk C: /scan

echo.
echo Tamamlandi. Lutfen bilgisayari yeniden baslatin.
pause
endlocal
