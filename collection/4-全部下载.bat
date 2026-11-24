@echo off
chcp 65001 >nul
title Download ALL videos
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0download-videos.ps1" -All
echo.
pause