@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set "PY=python"
where python >nul 2>nul || set "PY=D:\Program Files\python.exe"

set "SMALL=C:\Users\Administrator\.cache\huggingface\hub\models--Systran--faster-whisper-small\snapshots\536b0662742c02347bc0e980a01041f333bce120"
set "CSV=analysis\out\weekly_20261123_新增_去重.csv"
set "DATA=analysis\data_20261123"

echo ============================================
echo  1123 期口播转录（续跑，已去重 1316 条）
echo ============================================

echo.
echo [1/2] 转写（已转过的自动跳过，只补剩下的）
"%PY%" analysis\tools\asr_batch.py --csv "%CSV%" --model "%SMALL%" ^
   --out "%DATA%\asr.json" --audio "%DATA%\audio" --threads 16
if errorlevel 1 goto fail

echo.
echo [2/2] 二次判定：真口播 / 歌词 / 幻觉 / 无人声
"%PY%" analysis\tools\classify_vo.py --asr "%DATA%\asr.json" --out "%DATA%\vo_class.json"
if errorlevel 1 goto fail

echo.
echo [完成] 下一步由 AI 接手：三层去重 - 唯一段翻译 - 出表
echo 进度说明见 analysis\data_20261123\口播转录_进度与续跑.md
pause
exit /b 0

:fail
echo.
echo [失败] 见上方错误；asr.json 已断点保存，可直接重跑本脚本
pause
exit /b 1
