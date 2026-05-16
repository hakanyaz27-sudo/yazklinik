@echo off
chcp 65001 >nul
cd /d "%~dp0"
title YazKlinik D250 - WebShell
call "%~dp0YazKlinik_WebShell_Windows.bat" %*
