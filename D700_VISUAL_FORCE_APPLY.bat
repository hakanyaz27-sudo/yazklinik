@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"
set "NO_LAUNCH=0"
if /I "%~1"=="--no-launch" set "NO_LAUNCH=1"

echo [0/5] Mevcut v22 force durumu kontrol ediliyor...
curl.exe -k -s --connect-timeout 2 --max-time 5 "http://127.0.0.1:5052/giris" | findstr /C:"d700-force-2026-05-27-v22" >nul
if errorlevel 1 goto D700_VISUAL_APPLY_NEEDED
curl.exe -k -s --connect-timeout 2 --max-time 5 "https://127.0.0.1:5443/giris" | findstr /C:"d700-force-2026-05-27-v22" >nul
if errorlevel 1 goto D700_VISUAL_APPLY_NEEDED
goto D700_VISUAL_ALREADY_OK

:D700_VISUAL_APPLY_NEEDED

echo [1/4] WebShell cache temizligi yapiliyor...
call "%~dp0D700_WEBSHELL_CACHE_REFRESH.bat" --no-launch
if errorlevel 1 (
  echo Cache temizligi tamamlanamadi.
  endlocal
  exit /b 1
)

echo [2/4] Web servisi yenileniyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$c=Get-NetTCPConnection -LocalPort 5052 -State Listen -ErrorAction SilentlyContinue; if($c){ Stop-Process -Id $c[0].OwningProcess -Force -ErrorAction SilentlyContinue; exit 0 } else { exit 0 }"

echo [3/4] Servis geri donusu bekleniyor (5052/5443)...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "[System.Net.ServicePointManager]::ServerCertificateValidationCallback = {$true}; $ok5052=$false; $ok5443=$false; $h1=0; $h2=0; for($i=1;$i -le 120;$i++){ try { $h1=(Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'http://127.0.0.1:5052/giris').StatusCode } catch { $h1=0 }; try { $h2=(Invoke-WebRequest -UseBasicParsing -TimeoutSec 3 'https://127.0.0.1:5443/giris').StatusCode } catch { $h2=0 }; if($h1 -eq 200){ $ok5052=$true }; if($h2 -eq 200){ $ok5443=$true }; if($ok5052 -and $ok5443){ Write-Host ('OK 5052/5443 - ' + ($i*2) + ' sn'); exit 0 }; Start-Sleep -Seconds 2 }; Write-Host ('Servis geri donmedi (timeout). Son durum 5052=' + $h1 + ' 5443=' + $h2); exit 1"
if errorlevel 1 (
  echo Servis timeout verdi.
  endlocal
  exit /b 1
)

echo [4/5] v22 force token dogrulaniyor...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ok=$true; $urls=@('http://127.0.0.1:5052/giris','https://127.0.0.1:5443/giris','http://127.0.0.1:5052/bakim','https://127.0.0.1:5443/bakim'); foreach($u in $urls){ try { $h=((curl.exe -k -s $u) | Out-String); if($h -notmatch 'd700-force-2026-05-27-v22'){ Write-Host ('TOKEN_EKSIK ' + $u); $ok=$false } } catch { Write-Host ('TOKEN_HATA ' + $u); $ok=$false } }; if($ok){ Write-Host 'FORCE_TOKEN_OK'; exit 0 } else { exit 1 }"
if errorlevel 1 (
  echo v22 force token dogrulamasi basarisiz.
  endlocal
  exit /b 1
)

if "%NO_LAUNCH%"=="1" (
  echo [5/5] WebShell acilmadi: --no-launch
) else (
  echo [5/5] WebShell aciliyor...
  start "" "%~dp0YazKlinik_WebShell_Windows.bat"
)

echo Tamamlandi: gorsel force paketi uygulandi.
endlocal
exit /b 0

:D700_VISUAL_ALREADY_OK
echo [1/1] v22 force zaten canli; web restart atlandi.
if "%NO_LAUNCH%"=="1" (
  echo WebShell acilmadi: --no-launch
) else (
  start "" "%~dp0YazKlinik_WebShell_Windows.bat"
)
echo Tamamlandi: gorsel force zaten aktif.
endlocal
exit /b 0

