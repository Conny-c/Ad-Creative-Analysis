@echo off
chcp 65001 >nul
title Step 1 - fetch newest issue and rebuild list
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update-list.ps1"
echo.
echo ==== finished - list saved to .\list ====
pause