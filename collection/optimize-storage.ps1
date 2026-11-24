<#
  竞品创意速递 · 存量空间回收（跨周同名文件改硬链接）
  ===============================================================
  多个日期目录里存着同一素材（文件名相同）时，只保留一份真实数据，
  其余路径改成硬链接：看起来、用起来还是各自目录下的一堆文件，
  但占用空间只算一次。

  安全性：
    · 只处理「文件名相同 + 字节数相同」的文件；加 -VerifyContent 还会比对 SHA256
    · 改链接的顺序是：先建临时硬链接 → 删除旧文件 → 改名占位，
      任何一步失败都不会丢数据
    · 默认只报告，-Apply 才真正执行

  ── 用法 ──────────────────────────────────────────────────────
    # 先看能省多少
    powershell -ExecutionPolicy Bypass -File .\optimize-storage.ps1

    # 确认后执行
    powershell -ExecutionPolicy Bypass -File .\optimize-storage.ps1 -Apply

    # 最严格：连内容哈希都比对（慢，但万无一失）
    powershell -ExecutionPolicy Bypass -File .\optimize-storage.ps1 -Apply -VerifyContent

  报告：<BaseDir>\空间回收.csv
#>
[CmdletBinding()]
param(
    [string]$BaseDir = 'E:\video-download',
    [switch]$Apply,
    [switch]$VerifyContent,
    [string]$Report = ''
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $BaseDir)) { throw "找不到目录：$BaseDir" }

$dirs = @(Get-ChildItem -LiteralPath $BaseDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}$' } | Sort-Object Name)
if ($dirs.Count -lt 2) { Write-Host "日期目录不足 2 个，无需处理（当前 $($dirs.Count) 个）" -ForegroundColor Green; return }

Write-Host "共 $($dirs.Count) 个日期目录：$($dirs.Name -join ', ')" -ForegroundColor Cyan
if ($VerifyContent) { Write-Host '已开启内容哈希比对（较慢）' -ForegroundColor Yellow }

# 以"最早出现的那个"作为真实数据，后面同名的都改成指向它
$index = @{}
$plan = New-Object System.Collections.ArrayList
$totalFiles = 0

foreach ($d in $dirs) {
    $files = @(Get-ChildItem -LiteralPath $d.FullName -Recurse -File -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -match '^\.(mp4|webm)$' -and $_.Length -gt 0 })
    $totalFiles += $files.Count
    $dupInDir = 0
    foreach ($f in $files) {
        if ($index.ContainsKey($f.Name)) {
            $src = $index[$f.Name]
            if ([int64]$src.Len -ne [int64]$f.Length) { continue }   # 同名不同大小 → 不动
            $ok = $true
            if ($VerifyContent) {
                $ok = ((Get-FileHash -LiteralPath $src.Path -Algorithm SHA256).Hash -eq (Get-FileHash -LiteralPath $f.FullName -Algorithm SHA256).Hash)
            }
            if ($ok) {
                [void]$plan.Add([pscustomobject]@{
                        keep   = $src.Path
                        dup    = $f.FullName
                        sizeMB = [math]::Round($f.Length / 1MB, 2)
                        size   = $f.Length
                        date   = $d.Name
                    })
                $dupInDir++
                continue
            }
        }
        $index[$f.Name] = [pscustomobject]@{ Path = $f.FullName; Len = $f.Length }
    }
    if ($dupInDir -gt 0) { Write-Host ("  {0}: 其中 {1} 个与更早的一周同名" -f $d.Name, $dupInDir) }
}

$reclaimMB = [math]::Round((($plan | Measure-Object sizeMB -Sum).Sum), 1)
$reclaimGB = [math]::Round($reclaimMB / 1024, 2)

Write-Host ''
if ($plan.Count -eq 0) {
    Write-Host '没有可回收的重复文件（各周之间没有同名同大小的素材）。' -ForegroundColor Green
    return
}

Write-Host "可改硬链接：$($plan.Count) 个文件 / $reclaimMB MB（约 $reclaimGB GB）" -ForegroundColor Yellow
Write-Host "扫描了 $totalFiles 个视频，唯一内容 $($index.Count) 个" -ForegroundColor DarkGray
$plan | Group-Object date | Sort-Object Name | ForEach-Object {
    Write-Host ("  {0}: {1,5} 个 / {2,8} MB" -f $_.Name, $_.Count, [math]::Round((($_.Group | Measure-Object sizeMB -Sum).Sum), 1))
}

$reportPath = if ($Report) { $Report } else { Join-Path $BaseDir '空间回收.csv' }
$plan | Select-Object keep, dup, date, sizeMB | Export-Csv -LiteralPath $reportPath -NoTypeInformation -Encoding UTF8
Write-Host "`n明细：$reportPath" -ForegroundColor Cyan

if (-not $Apply) {
    Write-Host '演练模式，未改动任何文件。确认后加 -Apply 执行。' -ForegroundColor Green
    Write-Host '提示：执行后文件数量不变、文件名不变，只是不再重复占用空间。' -ForegroundColor DarkGray
    return
}

$done = 0; $fail = 0; $freed = 0L
foreach ($p in $plan) {
    $tmp = $p.dup + '.hltmp'
    try {
        # 1) 先建临时硬链接（失败则什么都不做）
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force }
        New-Item -ItemType HardLink -Path $tmp -Value $p.keep -Force -ErrorAction Stop | Out-Null
        # 2) 删除原来的重复文件
        $size = (Get-Item -LiteralPath $p.dup).Length
        Remove-Item -LiteralPath $p.dup -Force -ErrorAction Stop
        # 3) 把临时链接改成原来的名字
        Rename-Item -LiteralPath $tmp -NewName (Split-Path -Path $p.dup -Leaf) -ErrorAction Stop
        $done++; $freed += $size
    } catch {
        $fail++
        Write-Host "失败：$($p.dup) — $($_.Exception.Message)" -ForegroundColor Red
        if (Test-Path -LiteralPath $tmp) { Remove-Item -LiteralPath $tmp -Force -ErrorAction SilentlyContinue }
    }
}
Write-Host ''
Write-Host ("完成：$done 个改为硬链接，回收约 {0} MB（{1} GB）；失败 $fail 个" -f [math]::Round($freed / 1MB, 1), [math]::Round($freed / 1GB, 2)) -ForegroundColor Green
Write-Host "E 盘可用：$([math]::Round((Get-PSDrive E).Free/1GB,2)) GB"
