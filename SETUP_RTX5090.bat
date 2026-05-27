@echo off
chcp 65001 >nul
title YazKlinik D700 - RTX 5090 Setup
cd /d "%~dp0"

echo.
echo ============================================================
echo  YazKlinik D700 - RTX 5090 PC Sifirdan Kurulum
echo ============================================================
echo.
echo  Bu script SETUP_RTX5090.ps1'i YONETICI olarak baslatacak.
echo  UAC penceresi acilinca "Evet" tikla.
echo.
echo  Yapacaklari:
echo    1. Python 3.12 yukle (yoksa)
echo    2. .venv olustur + requirements.txt yukle
echo    3. CUDA destek paketleri (cuBLAS, cuDNN) yukle
echo    4. Whisper modelleri indir (small + large-v3)
echo    5. Klasor yapisini hazirla
echo    6. HTTPS sertifika olustur
echo    7. Ollama check (manuel yuklenecek)
echo    8. Windows Turkce TTS yukle
echo    9. config.env RTX 5090 profilini yerlestir
echo.
echo  Sure: 15-40 dakika (internet hizina + GPU'ya bagli)
echo.
pause

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%~dp0SETUP_RTX5090.ps1\"'"

echo.
echo  Yonetici PowerShell acildi. Oradaki adimlari takip et.
echo.
pause

