@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "PY=python"
where python >nul 2>nul || set "PY=D:\Program Files\python.exe"

echo ============================================
echo  竞品素材周更分析
echo ============================================
set /p D=1) 期号(如 20261026，回车=今天): 
if "%D%"=="" for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set D=%%i

echo.
echo 2) 分析范围：
echo    [回车]  素材量 TOP5
echo    [ALL]   本期全部竞品
echo    [产品名] 指定，如 Sugo  或  Sugo;Tango
set /p P=请输入: 
set "ARG=--top5"
if /i "%P%"=="ALL" set "ARG=--all"
if not "%P%"=="" if /i not "%P%"=="ALL" set "ARG=--competitors "%P%""

echo.
echo === 期号 %D% / 参数 %ARG% ===
if not exist "%~dp0analysis\tools\weekly.py" (
  echo [错误] 找不到 %~dp0analysis\tools\weekly.py
  pause & exit /b 1
)
"%PY%" "%~dp0analysis\tools\weekly.py" --date %D% --root "E:\video-download" --work "%~dp0analysis" %ARG%
if errorlevel 1 (
  echo.
  echo [失败] 检查 python 路径，或该期没有对应竞品素材
  pause & exit /b 1
)
echo.
echo 完成：本期技术指标与新增清单在 out\weekly_%D%_新增.csv
echo 下一步：1) 按 label_guide_v2.md 给新增素材打标  2) 按 label_guide_ai.md 复核 ai_visual_worklist  3) 跑 merge_all + build_library_xlsx
pause
