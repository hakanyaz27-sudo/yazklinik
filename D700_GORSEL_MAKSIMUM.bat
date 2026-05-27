@echo off
chcp 65001 >nul
setlocal EnableExtensions
cd /d "%~dp0"

echo D700 gorsel maksimum mod uygulaniyor...
call "%~dp0D700_VISUAL_FORCE_APPLY.bat"
if errorlevel 1 (
  echo Islem basarisiz.
  endlocal
  exit /b 1
)

echo Tamamlandi: WebShell acildi ve v22 gorsel paket aktif.
endlocal
exit /b 0

