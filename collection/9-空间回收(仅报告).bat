@echo off
chcp 65001 >nul
title Storage optimization - hardlink cross-week duplicates (REPORT ONLY)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0optimize-storage.ps1"
echo.
echo To really apply, run in PowerShell:
echo   powershell -ExecutionPolicy Bypass -File .\optimize-storage.ps1 -Apply
pause