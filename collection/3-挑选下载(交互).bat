@echo off
chcp 65001 >nul
title Pick competitors to download
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0download-videos.ps1" -Pick
echo.
pause