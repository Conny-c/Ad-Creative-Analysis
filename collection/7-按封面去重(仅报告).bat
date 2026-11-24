@echo off
chcp 65001 >nul
title Cover dedupe - REPORT ONLY (no delete)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dedupe-covers.ps1" -SaveCovers
echo.
echo To really delete, run in PowerShell:
echo   powershell -ExecutionPolicy Bypass -File .\dedupe-covers.ps1 -Apply
pause