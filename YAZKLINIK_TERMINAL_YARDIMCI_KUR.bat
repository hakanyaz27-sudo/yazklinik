@echo off
setlocal EnableExtensions
chcp 65001 >nul
title YazKlinik Terminal Yardimci Kur

set "YK_SILENT=0"
if /I "%~1"=="/silent" set "YK_SILENT=1"

set "YK_DIR=%LOCALAPPDATA%\YazKlinikTerminalHelper"
set "YK_PS1=%YK_DIR%\yk_photo_open.ps1"
set "YK_PY=%YK_DIR%\yk_photo_open.py"
set "YK_SRC=%~dp0YAZKLINIK_TERMINAL_PHOTO_HELPER.ps1"
set "YK_PY_SRC=%~dp0yazklinik_photo_print_helper.py"
set "YK_VENV_PY=%~dp0.venv\Scripts\pythonw.exe"

if not exist "%YK_DIR%" mkdir "%YK_DIR%" >nul 2>&1
if exist "%YK_SRC%" (
  copy /Y "%YK_SRC%" "%YK_PS1%" >nul
) else (
  echo Yardimci dosya bulunamadi: %YK_SRC%
  pause
  exit /b 1
)

if exist "%YK_PY_SRC%" (
  copy /Y "%YK_PY_SRC%" "%YK_PY%" >nul
) else (
  echo Python yardimci dosya bulunamadi: %YK_PY_SRC%
  pause
  exit /b 1
)

if exist "%YK_VENV_PY%" (
  set "YK_CMD=\"%YK_VENV_PY%\" \"%YK_PY%\" \"%%1\""
) else (
  set "YK_CMD=pythonw.exe \"%YK_PY%\" \"%%1\""
)
reg add "HKCU\Software\Classes\yazklinik-print-photo" /ve /d "URL:YazKlinik Photo Helper" /f >nul
reg add "HKCU\Software\Classes\yazklinik-print-photo" /v "URL Protocol" /t REG_SZ /d "" /f >nul
reg add "HKCU\Software\Classes\yazklinik-print-photo\shell\open\command" /ve /d "%YK_CMD%" /f >nul

echo.
echo YazKlinik terminal yardimcisi kuruldu.
echo Foto cift tik artik bu bilgisayardaki varsayilan foto uygulamasini acabilir.
echo.
if "%YK_SILENT%"=="0" pause
