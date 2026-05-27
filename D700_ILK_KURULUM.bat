@echo off
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

echo [D700] Ilk kurulum kontrolu basliyor...
if exist ".venv\Scripts\python.exe" goto RUN

echo [D700] .venv bulunamadi, olusturuluyor...
where py >nul 2>&1
if %errorlevel%==0 (
  py -3.11 -m venv .venv >nul 2>&1
  if not exist ".venv\Scripts\python.exe" py -3.10 -m venv .venv >nul 2>&1
) else (
  where python >nul 2>&1
  if %errorlevel%==0 (
    python -m venv .venv >nul 2>&1
  ) else (
    if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
      "%LocalAppData%\Programs\Python\Python312\python.exe" -m venv .venv >nul 2>&1
    ) else if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
      "%LocalAppData%\Programs\Python\Python311\python.exe" -m venv .venv >nul 2>&1
    ) else if exist "%ProgramFiles%\Python312\python.exe" (
      "%ProgramFiles%\Python312\python.exe" -m venv .venv >nul 2>&1
    ) else if exist "%ProgramFiles%\Python311\python.exe" (
      "%ProgramFiles%\Python311\python.exe" -m venv .venv >nul 2>&1
    )
  )
)

if not exist ".venv\Scripts\python.exe" (
  echo [HATA] Python 3.10+ bulunamadi. Once Python kur.
  pause
  exit /b 1
)

echo [D700] Pip guncelleme...
".venv\Scripts\python.exe" -m pip install --upgrade pip setuptools wheel >nul 2>&1

echo [D700] Bagimliliklar yukleniyor...
if exist "wheelhouse" (
  ".venv\Scripts\python.exe" -m pip install --no-index --find-links wheelhouse -r requirements-lock.txt
  if errorlevel 1 ".venv\Scripts\python.exe" -m pip install --no-index --find-links wheelhouse -r requirements.txt
) else (
  ".venv\Scripts\python.exe" -m pip install -r requirements-lock.txt
  if errorlevel 1 ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)

:RUN
echo [D700] Baslatiliyor...
call "%~dp0D700_BASLAT.bat"
endlocal

