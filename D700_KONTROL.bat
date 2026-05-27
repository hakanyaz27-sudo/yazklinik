@echo off
chcp 65001 >nul
title YazKlinik - Sistem Kontrol (CODEX_QUICK_CHECK)
cd /d "D:\YazKlinik_Final_D700"
echo ============================================================
echo   YazKlinik sistem kontrolu calistiriliyor...
echo   (CODEX_QUICK_CHECK.py = compile + DB + servis + route smoke)
echo   Bu islem ~30-60 saniye surebilir.
echo ============================================================
echo.
"D:\YazKlinik_Final_D700\.venv\Scripts\python.exe" "D:\YazKlinik_Final_D700\CODEX_QUICK_CHECK.py"
echo.
echo ============================================================
echo   BITTI. En alttaki satira bak:
echo     CODEX_D700_QUICK_CHECK_OK  +  "Hata: 0"  =  sistem saglikli.
echo   Hata 0'dan buyukse yukari kaydirip [HATA] satirlarini oku.
echo ============================================================
pause
