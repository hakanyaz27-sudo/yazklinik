@echo off
chcp 65001 >nul
title YazKlinik D700 - MedGemma 2 Mod Kurulum
cd /d "%~dp0"

echo.
echo ============================================================
echo  YazKlinik D700 - MedGemma Kurulum Secimi
echo ============================================================
echo.
echo  1^) ONLINE  : Ollama + MedGemma modeller internetten cekilir
echo  2^) OFFLINE : MEDGEMMA_OLLAMA_PACK klasorunden kurulur
echo.
set /p _secim=Seciminiz [1/2]:

if "%_secim%"=="1" (
  call "%~dp0MEDGEMMA_ONLINE_KUR.bat"
  goto :eof
)

if "%_secim%"=="2" (
  call "%~dp0MEDGEMMA_OFFLINE_KUR.bat"
  goto :eof
)

echo.
echo Gecersiz secim.
pause
