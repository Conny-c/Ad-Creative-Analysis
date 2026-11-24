@echo off
chcp 65001 >nul
title Weekly pipeline - fetch + download + dedupe + new-set
cd /d "%~dp0"
echo ============================================================
echo  Steps: fetch page -^> list -^> download -^> auto dedupe -^> new set
echo.
echo  Duplicates (same cover + same duration + same mid frame)
echo  are DELETED automatically and recorded in list\?????.csv.
echo  A content-unique "new set" for creative analysis is produced at
echo  _??\<issue>\  (nothing repeated from earlier weeks).
echo ============================================================
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-weekly.ps1" -CoverDedupeApply
echo.
echo ==== finished ====
pause