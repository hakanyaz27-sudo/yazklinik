@echo off
chcp 65001 >nul
title YazKlinik - Turkce TTS Yukleyici
cd /d "%~dp0"

echo.
echo ============================================================
echo  YazKlinik - Windows Turkce TTS Yukleyici
echo ============================================================
echo.
echo  Bu script PowerShell ile YONETICI olarak calistirilacak.
echo  UAC penceresi acilinca EVET tikla.
echo.
echo  Yapilacak:
echo    1. Turkce Konusma yetenekleri (Speech, TextToSpeech) yuklenecek
echo    2. Microsoft Tolga / Sedef Turkce sesleri kayit edilecek
echo    3. SAPI ile OneCore mirror yapilacak
echo.
echo  Sure: 5-15 dakika (internet hizina bagli)
echo.
pause

powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"%~dp0INSTALL_TURKISH_TTS.ps1\"'"

echo.
echo  Yonetici PowerShell penceresi acildi. Oradaki adimlari takip et.
echo.
pause
