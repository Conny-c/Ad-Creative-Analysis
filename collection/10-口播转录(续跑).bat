@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "PY=python"
where python >nul 2>nul || set "PY=D:\Program Files\python.exe"

set "SMALL=C:\Users\Administrator\.cache\huggingface\hub\models--Systran--faster-whisper-small\snapshots\536b0662742c02347bc0e980a01041f333bce120"
set "CSV=analysis\out\weekly_20261116_新增.csv"
set "DATA=analysis\data_20261116"

echo ============================================
echo  1116 期口播转录（续跑）
echo ============================================
if not exist "%DATA%\asr.json" (
  echo [提示] 没有找到 %DATA%\asr.json，将从第 1 条开始
)

echo.
echo [1/3] 转写（已转过的自动跳过）
"%PY%" analysis\tools\asr_batch.py --csv "%CSV%" --model "%SMALL%" ^
   --out "%DATA%\asr.json" --audio "%DATA%\audio" --threads 16
if errorlevel 1 goto fail

echo.
echo [2/3] 二次判定：真口播 / 歌词 / 幻觉 / 无人声
"%PY%" analysis\tools\classify_vo.py
if errorlevel 1 goto fail

echo.
echo [3/3] 出表：analysis\out\2026-11-16_口播转录表.xlsx
"%PY%" analysis\tools\build_vo_xlsx.py
if errorlevel 1 goto fail

echo.
echo [完成] out\2026-11-16_口播转录表.xlsx
echo 进度说明见 analysis\data_20261116\口播转录_进度与续跑.md
pause
exit /b 0

:fail
echo.
echo [失败] 见上方错误；asr.json 已断点保存，可直接重跑本脚本
pause
exit /b 1
