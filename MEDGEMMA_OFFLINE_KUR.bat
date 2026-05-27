@echo off
chcp 65001 >nul
title YazKlinik D700 - MedGemma Offline Kurulum
cd /d "%~dp0"

echo.
echo ============================================================
echo  MedGemma OFFLINE kurulum basliyor
echo  Kaynak: %~dp0MEDGEMMA_OLLAMA_PACK
echo ============================================================
echo.
pause

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0MEDGEMMA_KURULUM_OFFLINE.ps1"

echo.
echo Islem bitti. Ayrinti icin runtime_state\MEDGEMMA_OFFLINE_INSTALL_REPORT_*.json
pause
