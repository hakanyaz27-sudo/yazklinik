@echo off
setlocal EnableExtensions
chcp 65001 >nul
title YazKlinik D700 - Windows Stabilizasyon (Admin)

net session >nul 2>&1
if not "%errorlevel%"=="0" (
  echo [HATA] Bu script Yonetici olarak calistirilmalidir.
  echo        Sag tik ^> "Yonetici olarak calistir"
  pause
  exit /b 1
)

set "ROOT=%~dp0"
set "ORTHANC_EXE=E:\Orthanc Server\Orthanc.exe"
set "ORTHANC_CFG=E:\Orthanc Server\Configuration\config.json"
set "ORTHANC_TASK=YazKlinik_Orthanc_Autostart"
set "ORTHANC_BOOT_PS=%ROOT%D700_ORTHANC_MANUEL_BASLAT.ps1"
if not exist "%ORTHANC_BOOT_PS%" set "ORTHANC_BOOT_PS=D:\YazKlinik_Final_D700\D700_ORTHANC_MANUEL_BASLAT.ps1"

echo.
echo ============================================================
echo   YazKlinik D700 - BSOD ve Orthanc Stabilizasyonu
echo ============================================================
echo.

echo [1/7] Son 24 saat crash ozeti:
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(Get-Date).AddHours(-24); Get-WinEvent -FilterHashtable @{LogName='System'; StartTime=$s} -MaxEvents 300 | ? { $_.Id -in 41,6008,1001 } | Select TimeCreated,Id,ProviderName | ft -Auto"
echo.

echo [2/7] Orthanc servis yolu duzeltiliyor...
if exist "%ORTHANC_EXE%" if exist "%ORTHANC_CFG%" (
  sc stop Orthanc >nul 2>&1
  sc config Orthanc binPath= "\"E:\Orthanc Server\Orthanc.exe\" \"E:\Orthanc Server\Configuration\config.json\"" >nul
  sc config Orthanc start= delayed-auto >nul 2>&1
  if errorlevel 1 sc config Orthanc start= auto >nul 2>&1
  sc failure Orthanc reset= 86400 actions= restart/5000/restart/10000/restart/30000 >nul 2>&1
  echo      [OK] Orthanc service ayarlari guncellendi.
) else (
  echo      [UYARI] Orthanc exe/config bulunamadi, servis adimi atlandi.
)
echo.

echo [3/7] Orthanc startup gorevi olusturuluyor...
schtasks /Delete /TN "%ORTHANC_TASK%" /F >nul 2>&1
if exist "%ORTHANC_BOOT_PS%" (
  schtasks /Create /TN "%ORTHANC_TASK%" /SC ONSTART /DELAY 0000:45 /RU "SYSTEM" /RL HIGHEST /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -File \"%ORTHANC_BOOT_PS%\" -Mode start -Quiet 1" /F >nul
  if errorlevel 1 (
    echo      [UYARI] Task olusturulamadi.
  ) else (
    echo      [OK] %ORTHANC_TASK% olusturuldu.
  )
) else (
  echo      [UYARI] D700_ORTHANC_MANUEL_BASLAT.ps1 bulunamadi.
)
echo.

echo [4/7] Orthanc canli test...
sc start Orthanc >nul 2>&1
timeout /t 5 /nobreak >nul
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p=Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue | ? { $_.LocalPort -in 8042,4242 }; if($p){$p|Select LocalAddress,LocalPort,OwningProcess|ft -Auto; exit 0} else {Write-Host 'ORTHANC_PORT_YOK'; exit 1}"
echo.

echo [5/7] Acronis gercek-zamanli servisler test amacli devre disi (reversible)...
for %%S in (AcronisActiveProtectionService AcronisCyberProtectionService aakore) do (
  sc query "%%S" >nul 2>&1
  if not errorlevel 1 (
    sc stop "%%S" >nul 2>&1
    sc config "%%S" start= demand >nul 2>&1
    echo      [OK] %%S -> demand
  )
)
echo      Not: Bu adim sadece test icin; gerekirse start= auto yaparak geri alinabilir.
echo.

echo [6/7] Sistem dosya saglik taramalari...
DISM /Online /Cleanup-Image /RestoreHealth
sfc /scannow
echo.

echo [7/7] Son durum:
sc query Orthanc
schtasks /Query /TN "%ORTHANC_TASK%" /V /FO LIST
echo.

echo Tamamlandi. Simdi PC'yi yeniden baslatip tekrar kontrol edin.
echo Komut: shutdown /r /t 0
pause
endlocal
