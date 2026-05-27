@echo off
chcp 65001 >nul
title Claude Code - Remote Control (Telefondan baglan)
cd /d "%~dp0"
cls

echo.
echo  ============================================================
echo            Claude Code Remote Control - YazKlinik D700
echo  ============================================================
echo.

REM Claude komutu var mi
where claude >nul 2>&1
if errorlevel 1 (
  echo  [HATA] 'claude' komutu bulunamadi.
  echo.
  echo  Cozum:
  echo    PowerShell ac, su komutu calistir:
  echo      npm install -g @anthropic-ai/claude-code
  echo.
  pause
  exit /b 1
)

echo  [+] Claude bulundu
echo.

REM Auth durumu kontrol
echo  [+] Auth durumu kontrol...
claude auth status >nul 2>&1
if errorlevel 1 (
  echo.
  echo  ============================================================
  echo   GIRIS YAPILMAMIS - Claude hesabina login gerekli!
  echo  ============================================================
  echo.
  echo  Asagidaki komut tarayici acacak.
  echo  Claude hesabin (Anthropic) ile giris yap.
  echo  Login bitince bu pencereye DON.
  echo.
  pause
  echo.
  echo  Login basliyor...
  claude auth login
  echo.
  echo  Login bitti. Devam etmek icin bir tusa bas...
  pause >nul
)

echo.
echo  ============================================================
echo   Claude Remote Control BASLIYOR
echo  ============================================================
echo.
echo  ASAGIDA QR KOD VE URL CIKACAK.
echo.
echo  TELEFONDA YAPILACAKLAR:
echo.
echo    1. Claude iOS / Android app ac
echo       (yoksa: App Store / Play Store -^> "Claude" Anthropic PBC)
echo.
echo    2. Sag ust "+" -^> "Connect to Claude Code"
echo.
echo    3. PC ekranindaki QR kodu kameraya tut
echo.
echo    4. Bagli olunca yaz: "AGENTS.md oku, hazir misin?"
echo.
echo  ============================================================
echo.

REM Claude Code'u remote-control modunda baslat
claude --remote-control "yazklinik-d700"

echo.
echo  ============================================================
echo   Claude session kapandi.
echo  ============================================================
pause


