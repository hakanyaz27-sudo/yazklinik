@echo off
setlocal

set "ORTHANC_EXE=E:\Orthanc Server\Orthanc.exe"
set "ORTHANC_CFG=E:\Orthanc Server\Configuration\config.json"

for /L %%i in (1,1,30) do (
  if exist "%ORTHANC_EXE%" if exist "%ORTHANC_CFG%" goto :start
  timeout /t 2 /nobreak >nul
)
exit /b 1

:start
for /f "tokens=2 delims=," %%p in ('tasklist /FI "IMAGENAME eq Orthanc.exe" /FO CSV /NH') do (
  if not "%%~p"=="" exit /b 0
)
start "" /min "%ORTHANC_EXE%" "%ORTHANC_CFG%"
exit /b 0
