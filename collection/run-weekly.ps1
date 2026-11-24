<#
  竞品创意速递 · 每周一键流水线
  ===============================================================
  一条命令跑完：抓最新一期页面 → 生成清单 → 下载 → 三种去重体检 → 生成本周新增素材集

      页面  https://<你的素材源域名>/<yyyyMMdd>-竞品周推.html
        ↓  update-list.ps1
      清单  E:\video-download\list\视频下载清单_<期号>.csv（+ 最新清单.csv / aria2_<期号>.txt）
        ↓  download-videos.ps1
      视频  E:\video-download\<期号>\<竞品>\*.mp4|webm
            ↳ 与往期同名的素材直接硬链接复用（不重复下载，不额外占空间）
        ↓  dedupe-videos.ps1（按文件内容，只报告）
      报告  重复视频.csv
        ↓  dedupe-covers.ps1（按封面首帧+中间帧，默认只报告）
      报告  重复封面.csv + _covers\ 封面图
        ↓  make-new-set.ps1（跨全部历史做内容去重）
      分析输入  _新增\<期号>\   ← 只含真正新内容，素材分析直接对它跑
                清单 list\新增_<期号>.csv（每条标了"新内容"或"重复于哪一周"）

  ── 用法 ──────────────────────────────────────────────────────
    # 最常用：自动找最新一期并全部下载
    powershell -ExecutionPolicy Bypass -File .\run-weekly.ps1

    # 只更新清单，不下载
    powershell -ExecutionPolicy Bypass -File .\run-weekly.ps1 -NoDownload

    # 指定期号 / 指定页面
    powershell -ExecutionPolicy Bypass -File .\run-weekly.ps1 -Date 20261008
    powershell -ExecutionPolicy Bypass -File .\run-weekly.ps1 -Url "https://<你的素材源域名>/xxx.html"

    # 跳过体积探测（快）／并发 10／跳过末尾去重检查
    powershell -ExecutionPolicy Bypass -File .\run-weekly.ps1 -SkipHead -Jobs 10 -SkipDedupe -SkipCoverDedupe

    # 封面重复直接删（默认只报告，不删）
    powershell -ExecutionPolicy Bypass -File .\run-weekly.ps1 -CoverDedupeApply

    # 不要"本周新增素材集"这一步 / 只要清单不要目录
    powershell -ExecutionPolicy Bypass -File .\run-weekly.ps1 -SkipNewSet
    powershell -ExecutionPolicy Bypass -File .\run-weekly.ps1 -NewSetMode list

  ── 想每周自动跑（任务计划程序，每周四 09:00 为例）─────────────
    先测通一次，然后以管理员身份执行：
      schtasks /create /tn "竞品周推下载" /sc weekly /d THU /st 09:00 ^
        /tr "powershell -ExecutionPolicy Bypass -File \"C:\Users\Administrator\Documents\deepseek-harness\default-workspace\run-weekly.ps1\""
    查看：schtasks /query /tn "竞品周推下载" /v /fo LIST
    删除：schtasks /delete /tn "竞品周推下载" /f
    日志：脚本会写 E:\video-download\list\运行日志_<期号>.log
#>
[CmdletBinding()]
param(
    [string]$Url = '',
    [string]$Date = '',
    [int]$Lookback = 45,
    [string]$ListDir = 'E:\video-download\list',
    [string]$OutputRoot = 'E:\video-download',
    [int]$Jobs = 8,
    [int]$Retries = 3,
    [switch]$SkipHead,
    [switch]$NoDownload,
    [switch]$SkipDedupe,
    [switch]$SkipCoverDedupe,
    [switch]$CoverDedupeApply,
    [int]$CoverJobs = 12,
    [ValidateSet('link', 'copy', 'skip', 'off')][string]$ReuseMode = 'link',
    [switch]$SkipNewSet,
    [ValidateSet('link', 'copy', 'list')][string]$NewSetMode = 'link',
    [int]$NewSetJobs = 12,
    [switch]$IncludeDead
)

$ErrorActionPreference = 'Stop'
$scriptDir = $PSScriptRoot
$updateScript = Join-Path $scriptDir 'update-list.ps1'
$downloadScript = Join-Path $scriptDir 'download-videos.ps1'
$dedupeScript = Join-Path $scriptDir 'dedupe-videos.ps1'
$coverScript = Join-Path $scriptDir 'dedupe-covers.ps1'
$newSetScript = Join-Path $scriptDir 'make-new-set.ps1'

foreach ($s in @($updateScript, $downloadScript)) {
    if (-not (Test-Path -LiteralPath $s)) { throw "缺少脚本：$s" }
}

$watch = [System.Diagnostics.Stopwatch]::StartNew()
Write-Host ''
Write-Host '════════ 竞品创意速递 · 每周流水线 ════════' -ForegroundColor Cyan
Write-Host "开始时间：$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"

# ── 第 1 步：抓页面 + 生成清单 ──────────────────────────────────
Write-Host ''
Write-Host '【1/5】抓取页面并生成下载清单' -ForegroundColor Yellow
$updateArgs = @{ ListDir = $ListDir }
if ($Url) { $updateArgs['Url'] = $Url }
if ($Date) { $updateArgs['Date'] = $Date }
if ($Lookback) { $updateArgs['Lookback'] = $Lookback }
if ($SkipHead) { $updateArgs['SkipHead'] = $true }
& $updateScript @updateArgs
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "清单生成失败（exit $LASTEXITCODE）" }

# 找出这一次生成的清单（最新清单.csv 的内容/时间戳）
$latestManifest = Join-Path $ListDir '最新清单.csv'
if (-not (Test-Path -LiteralPath $latestManifest)) { throw "没有生成 最新清单.csv，请检查上面的输出。" }
$rows = @(Import-Csv -LiteralPath $latestManifest -Encoding UTF8)
$stamp8 = ''
$mm = [regex]::Match([System.IO.Path]::GetFileName(((Get-ChildItem -LiteralPath $ListDir -Filter '视频下载清单_*.csv' |
                        Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName)), '(\d{8})')
if ($mm.Success) { $stamp8 = $mm.Groups[1].Value }
$okRows = @($rows | Where-Object { $_.httpStatus -eq '200' -or -not $_.httpStatus })
$okMB = [math]::Round((($okRows | Measure-Object sizeMB -Sum).Sum), 1)
Write-Host "  → $($rows.Count) 条素材，可下载 $($okRows.Count) 条 / $okMB MB"

if ($NoDownload) {
    Write-Host ''
    Write-Host '已按 -NoDownload 停在清单阶段。' -ForegroundColor Green
    return
}

# ── 第 2 步：下载全部 ───────────────────────────────────────────
Write-Host ''
Write-Host '【2/5】下载视频到 ' -NoNewline -ForegroundColor Yellow
Write-Host "$OutputRoot\<期号>\" -ForegroundColor Yellow
$dlArgs = @{
    Manifest   = $latestManifest
    ListDir    = $ListDir
    OutputRoot = $OutputRoot
    Jobs       = $Jobs
    Retries    = $Retries
    All        = $true
    Yes        = $true
    ReuseMode  = $ReuseMode
}
if ($IncludeDead) { $dlArgs['IncludeDead'] = $true }
& $downloadScript @dlArgs

# ── 第 3 步：按文件内容去重体检（只报告）────────────────────────
if (-not $SkipDedupe -and (Test-Path -LiteralPath $dedupeScript)) {
    Write-Host ''
    Write-Host '【3/5】按文件内容去重（只报告，不删除）' -ForegroundColor Yellow
    $dedupeArgs = @{ BaseDir = $OutputRoot; CrossFormat = $true }
    if ($stamp8) { $dedupeArgs['DateFolder'] = [datetime]::ParseExact($stamp8, 'yyyyMMdd', $null).ToString('yyyy-MM-dd') }
    & $dedupeScript @dedupeArgs
}

# ── 第 4 步：按封面去重体检（默认只报告）────────────────────────
$coverStat = '未执行'
if (-not $SkipCoverDedupe -and (Test-Path -LiteralPath $coverScript)) {
    Write-Host ''
    if ($CoverDedupeApply) {
        Write-Host '【4/5】按封面去重（首帧+中间帧复核，发现重复会直接删除）' -ForegroundColor Yellow
    } else {
        Write-Host '【4/5】按封面去重（首帧+中间帧复核，只报告不删除）' -ForegroundColor Yellow
    }
    $coverArgs = @{ BaseDir = $OutputRoot; Jobs = $CoverJobs; SaveCovers = $true }
    if ($stamp8) { $coverArgs['DateFolder'] = [datetime]::ParseExact($stamp8, 'yyyyMMdd', $null).ToString('yyyy-MM-dd') }
    if ($CoverDedupeApply) { $coverArgs['Apply'] = $true }
    & $coverScript @coverArgs
    $coverReport = Join-Path $OutputRoot '重复封面.csv'
    if (Test-Path -LiteralPath $coverReport) {
        $cr = @(Import-Csv -LiteralPath $coverReport -Encoding UTF8)
        $groups = @($cr | Group-Object group).Count
        $coverStat = "$groups 组 / $($cr.Count) 个$([string]::Empty)"
        if (-not $CoverDedupeApply) { $coverStat += '（待确认）' }
    } else {
        $coverStat = '0 组'
    }
} elseif ($SkipCoverDedupe) {
    Write-Host ''
    Write-Host '【4/5】按封面去重：已跳过' -ForegroundColor DarkGray
} elseif (-not (Test-Path -LiteralPath $coverScript)) {
    Write-Host ''
    Write-Host "【4/5】按封面去重：找不到 $coverScript，已跳过" -ForegroundColor Yellow
}

# ── 第 5 步：生成"本周新增素材集"（跨全部历史做内容去重）──────────
$newStat = '未执行'
$newSetDir = ''
if (-not $SkipNewSet -and (Test-Path -LiteralPath $newSetScript)) {
    $dateFolderForSet = if ($stamp8) { [datetime]::ParseExact($stamp8, 'yyyyMMdd', $null).ToString('yyyy-MM-dd') } else { '' }
    Write-Host ''
    Write-Host '【5/5】生成本周新增素材集（跨全部历史内容去重，供素材分析直接用）' -ForegroundColor Yellow
    $nsArgs = @{ BaseDir = $OutputRoot; Jobs = $NewSetJobs; Mode = $NewSetMode }
    if ($dateFolderForSet) { $nsArgs['DateFolder'] = $dateFolderForSet }
    & $newSetScript @nsArgs
    $newCsv = Join-Path $ListDir ("新增_" + $(if ($stamp8) { $stamp8 } else { (Get-Date -Format 'yyyyMMdd') }) + ".csv")
    if (Test-Path -LiteralPath $newCsv) {
        $nr = @(Import-Csv -LiteralPath $newCsv -Encoding UTF8)
        $newCnt = @($nr | Where-Object { $_.status -eq '新内容' }).Count
        $dupCnt = @($nr | Where-Object { $_.status -eq '与往期重复' }).Count
        $newStat = "新内容 $newCnt / 重复 $dupCnt（共 $($nr.Count)）"
        if ($NewSetMode -ne 'list') { $newSetDir = Join-Path (Join-Path $OutputRoot '_新增') $dateFolderForSet }
    } else { $newStat = '0' }
} elseif ($SkipNewSet) {
    Write-Host ''
    Write-Host '【5/5】本周新增素材集：已跳过' -ForegroundColor DarkGray
} elseif (-not (Test-Path -LiteralPath $newSetScript)) {
    Write-Host ''
    Write-Host "【5/5】本周新增素材集：找不到 $newSetScript，已跳过" -ForegroundColor Yellow
}

# ── 收尾：统计 + 日志 ───────────────────────────────────────────
$dateFolder = if ($stamp8) { [datetime]::ParseExact($stamp8, 'yyyyMMdd', $null).ToString('yyyy-MM-dd') } else { Get-Date -Format 'yyyy-MM-dd' }
$videoDir = Join-Path $OutputRoot $dateFolder
$files = @(Get-ChildItem -LiteralPath $videoDir -Recurse -File -ErrorAction SilentlyContinue | Where-Object { $_.Extension -match '^\.(mp4|webm)$' })
$totalMB = [math]::Round((($files | Measure-Object Length -Sum).Sum) / 1MB, 1)

Write-Host ''
Write-Host '════════ 完成 ════════' -ForegroundColor Cyan
Write-Host "  期号        : $(if ($stamp8) { $stamp8 } else { '-' })"
Write-Host "  清单        : $latestManifest"
Write-Host "  视频目录    : $videoDir"
Write-Host "  本地已有    : $($files.Count) 个文件 / $totalMB MB"
Write-Host "  封面重复    : $coverStat"
if (-not $CoverDedupeApply -and $coverStat -ne '未执行' -and $coverStat -ne '0 组') {
    Write-Host "                确认要删就运行：powershell -ExecutionPolicy Bypass -File .\dedupe-covers.ps1 -Apply" -ForegroundColor Yellow
}
Write-Host "  本周新增    : $newStat"
if ($newSetDir) {
    Write-Host "  分析输入    : $newSetDir" -ForegroundColor Green
    Write-Host "                素材分析就对这个目录跑，里面没有与往期重复的视频" -ForegroundColor DarkGray
}
Write-Host "  用时        : $([math]::Round($watch.Elapsed.TotalMinutes, 1)) 分钟"

$logPath = Join-Path $ListDir ("运行日志_" + $(if ($stamp8) { $stamp8 } else { (Get-Date -Format 'yyyyMMdd') }) + '.log')
$logLine = "{0}  期号={1}  清单条数={2}  可下载={3}  本地文件={4}  体积MB={5}  封面重复={6}  本周新增={7}  用时分钟={8}" -f `
    (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $(if ($stamp8) { $stamp8 } else { '-' }), $rows.Count, $okRows.Count, $files.Count, $totalMB, $coverStat, $newStat, [math]::Round($watch.Elapsed.TotalMinutes, 1)
Add-Content -LiteralPath $logPath -Value $logLine -Encoding UTF8
Write-Host "  运行日志    : $logPath"
