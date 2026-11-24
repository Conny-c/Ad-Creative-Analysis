@echo off
chcp 65001 >nul
title Preview - what can be downloaded
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0download-videos.ps1" -List
echo.
pause