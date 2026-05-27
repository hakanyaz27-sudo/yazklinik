@echo off
chcp 65001 >nul
title YazKlinik D700 - MedGemma Online Kurulum
cd /d "%~dp0"

echo.
echo ============================================================
echo  MedGemma ONLINE kurulum basliyor
echo  - Ollama kurulur/dogrulanir
echo  - medgemma:27b pull edilir
echo  - HF MedGemma (4b-it + 1.5-4b-it) indirilir
echo ============================================================
echo.
pause

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0MEDGEMMA_KURULUM_ONLINE.ps1" -DownloadHfModels

echo.
echo Islem bitti. Ayrinti icin runtime_state\MEDGEMMA_ONLINE_INSTALL_REPORT_*.json
pause
