@echo off
chcp 65001 >nul
title Duplicate check (report only)
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0dedupe-videos.ps1" -CrossFormat
echo.
pause