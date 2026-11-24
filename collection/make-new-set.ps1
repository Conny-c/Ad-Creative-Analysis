<#
  竞品创意速递 · 本周新增素材集（跨周全历史内容去重）
  ===============================================================
  用途：给素材分析准备输入。把所有周目录里的视频按「内容指纹」比对，
  找出"本周的素材里，哪些内容在更早的周已经出现过"，只把真正新的挑出来。

  为什么不能只靠 md5 / 文件名：
    · 跨周同名（1204 个）：md5 相同，能靠 md5 去重，但那是硬链接，重复分析没意义
    · 同周不同名但同内容（热云 / AppGrowing 各收一份）：字节不同，md5 抓不到
    · 跨周不同名但同内容（老素材换名重新上架）：md5 也抓不到
  所以这里用「画面指纹」：抽 50% 位置的帧，缩 64×64 灰度，SHA256 当内容键；
  再叠一个时长容差（±1 秒）防止"同样的黑场首帧"误判。

  指纹会缓存到 list\封面索引.csv，第二次开始只算没算过的文件。

  ── 用法 ──────────────────────────────────────────────────────
    # 默认：处理最新一期，生成清单 + 硬链接目录 _新增\<期号>\
    powershell -ExecutionPolicy Bypass -File .\make-new-set.ps1

    # 指定某一周
    powershell -ExecutionPolicy Bypass -File .\make-new-set.ps1 -DateFolder 2026-11-02

    # 只要清单，不要目录
    powershell -ExecutionPolicy Bypass -File .\make-new-set.ps1 -Mode list

    # 目录里放复制件而不是硬链接
    powershell -ExecutionPolicy Bypass -File .\make-new-set.ps1 -Mode copy

  产物：
    list\新增_<期号>.csv     本周每个文件的状态（新内容 / 与第几周重复）
    _新增\<期号>\<竞品>\     只有新内容的目录，可直接喂给分析脚本
#>
[CmdletBinding()]
param(
    [string]$BaseDir = 'E:\video-download',
    [string]$DateFolder = '',
    [string]$IndexFile = '',
    [string]$OutRoot = '',
    [ValidateSet('link', 'copy', 'list')][string]$Mode = 'link',
    [int]$Jobs = 12,
    [double]$DurationTolerance = 1.0,
    [switch]$ForceRefresh
)

$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $BaseDir)) { throw "找不到目录：$BaseDir" }

$dirs = @(Get-ChildItem -LiteralPath $BaseDir -Directory -ErrorAction SilentlyContinue |
        Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}$' } | Sort-Object Name)
if ($dirs.Count -eq 0) { throw "没有日期目录（形如 2026-11-02）：$BaseDir" }

if (-not $DateFolder) {
    $DateFolder = $dirs[-1].Name
    Write-Host "自动选用最新一期：$DateFolder" -ForegroundColor DarkGray
}
$targetDir = Join-Path $BaseDir $DateFolder
if (-not (Test-Path -LiteralPath $targetDir)) { throw "找不到本周目录：$targetDir" }
$earlier = @($dirs | Where-Object { $_.Name -lt $DateFolder })
Write-Host "本周：$DateFolder ｜ 更早的周：$(if($earlier.Count){$earlier.Name -join ', '}else{'无（第一周，全部算新）'})" -ForegroundColor Cyan

$listDir = Join-Path $BaseDir 'list'
if (-not (Test-Path -LiteralPath $listDir)) { New-Item -ItemType Directory -Path $listDir -Force | Out-Null }
if (-not $IndexFile) { $IndexFile = Join-Path $listDir '封面索引.csv' }

# ── ffmpeg ─────────────────────────────────────────────────────
$ffmpeg = (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue).Source
if (-not $ffmpeg) { foreach ($c in 'C:\ffmpeg\bin\ffmpeg.exe', 'D:\ffmpeg\bin\ffmpeg.exe') { if (Test-Path -LiteralPath $c) { $ffmpeg = $c; break } } }
if (-not $ffmpeg) { throw '找不到 ffmpeg.exe' }
$ffprobe = (Get-Command ffprobe.exe -ErrorAction SilentlyContinue).Source
if (-not $ffprobe) { $g = Join-Path (Split-Path $ffmpeg -Parent) 'ffprobe.exe'; if (Test-Path -LiteralPath $g) { $ffprobe = $g } }

# ── 读缓存索引 ─────────────────────────────────────────────────
$index = @{}
if ((Test-Path -LiteralPath $IndexFile) -and -not $ForceRefresh) {
    foreach ($row in @(Import-Csv -LiteralPath $IndexFile -Encoding UTF8)) {
        if ($row.path -and (Test-Path -LiteralPath $row.path)) {
            $index[$row.path] = [pscustomobject]@{ Hash = $row.hash; Dur = [double]$row.duration; Week = $row.week; SizeMB = [double]$row.sizeMB }
        }
    }
}
Write-Host "缓存索引：$($index.Count) 条有效记录" -ForegroundColor DarkGray

# ── 收集需要抽帧的文件（所有周）────────────────────────────────
$allFiles = New-Object System.Collections.ArrayList
foreach ($d in $dirs) {
    foreach ($f in @(Get-ChildItem -LiteralPath $d.FullName -Recurse -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Extension -match '^\.(mp4|webm)$' -and $_.Length -gt 0 })) {
        [void]$allFiles.Add([pscustomobject]@{ Path = $f.FullName; Week = $d.Name; Name = $f.Name; SizeMB = [math]::Round($f.Length / 1MB, 2) })
    }
}
$todo = @($allFiles | Where-Object { -not $index.ContainsKey($_.Path) })
Write-Host "总视频 $($allFiles.Count) 个，其中 $($todo.Count) 个需要抽帧（其余走缓存）" -ForegroundColor Cyan

# ── 抽帧 worker ────────────────────────────────────────────────
$tmpDir = Join-Path $env:TEMP ('newset_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null

$worker = {
    param($File, $Ffmpeg, $Ffprobe, $TmpDir)
    Add-Type -AssemblyName System.Drawing
    $dur = 0.0
    if ($Ffprobe) {
        $ds = & $Ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 $File 2>$null
        if ($ds) { [void][double]::TryParse("$ds".Trim(), [ref]$dur) }
    }
    $seek = if ($dur -gt 2) { $dur * 0.5 } else { 0.5 }
    $png = Join-Path $TmpDir ([guid]::NewGuid().ToString('N') + '.png')
    & $Ffmpeg -v error -ss "$seek" -i $File -frames:v 1 -vf "scale=64:64:flags=area,format=gray" -y $png 2>$null
    if (-not (Test-Path -LiteralPath $png) -or (Get-Item -LiteralPath $png).Length -eq 0) {
        & $Ffmpeg -v error -i $File -frames:v 1 -vf "scale=64:64:flags=area,format=gray" -y $png 2>$null
    }
    if (-not (Test-Path -LiteralPath $png) -or (Get-Item -LiteralPath $png).Length -eq 0) {
        return @{ Path = $File; Ok = $false; Hash = ''; Dur = $dur }
    }
    $src = [System.Drawing.Bitmap]::FromFile($png)
    $bmp = New-Object System.Drawing.Bitmap 64, 64, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.DrawImage($src, 0, 0, 64, 64); $g.Dispose(); $src.Dispose()
    $rect = New-Object System.Drawing.Rectangle 0, 0, 64, 64
    $bd = $bmp.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $buf = New-Object byte[] ($bd.Stride * 64)
    [System.Runtime.InteropServices.Marshal]::Copy($bd.Scan0, $buf, 0, $buf.Length)
    $bmp.UnlockBits($bd); $bmp.Dispose()
    Remove-Item -LiteralPath $png -Force -ErrorAction SilentlyContinue
    $sha = [System.Security.Cryptography.SHA256]::Create()
    $hb = $sha.ComputeHash($buf); $sha.Dispose()
    return @{ Path = $File; Ok = $true; Hash = (($hb | ForEach-Object { $_.ToString('x2') }) -join ''); Dur = $dur }
}

if ($todo.Count -gt 0) {
    $pool = [runspacefactory]::CreateRunspacePool(1, [Math]::Max(1, $Jobs))
    $pool.Open()
    $handles = New-Object System.Collections.ArrayList
    foreach ($t in $todo) {
        $ps = [powershell]::Create(); $ps.RunspacePool = $pool
        [void]$ps.AddScript($worker).AddArgument($t.Path).AddArgument($ffmpeg).AddArgument($ffprobe).AddArgument($tmpDir)
        [void]$handles.Add([pscustomobject]@{ PS = $ps; Handle = $ps.BeginInvoke(); Item = $t })
    }
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($true) {
        $done = @($handles | Where-Object { $_.Handle.IsCompleted }).Count
        Write-Progress -Activity '抽帧建立内容指纹' -Status "$done / $($handles.Count)" -PercentComplete ([int](100 * $done / [Math]::Max(1, $handles.Count)))
        if ($done -ge $handles.Count) { break }
        Start-Sleep -Milliseconds 400
    }
    $bad = 0
    foreach ($h in $handles) {
        foreach ($r in $h.PS.EndInvoke($h.Handle)) {
            if ($r.Ok) {
                $index[$r.Path] = [pscustomobject]@{ Hash = $r.Hash; Dur = $r.Dur; Week = $h.Item.Week; SizeMB = $h.Item.SizeMB }
            } else { $bad++ }
        }
        $h.PS.Dispose()
    }
    $pool.Close(); $pool.Dispose()
    Write-Progress -Activity '抽帧建立内容指纹' -Completed
    Write-Host "抽帧完成：成功 $($todo.Count - $bad)，失败 $bad，用时 $([math]::Round($sw.Elapsed.TotalSeconds,1)) 秒" -ForegroundColor Green
}
Remove-Item -LiteralPath $tmpDir -Recurse -Force -ErrorAction SilentlyContinue

# ── 存回索引（只存仍存在的文件）───────────────────────────────
$idxRows = foreach ($k in $index.Keys) {
    $v = $index[$k]
    [pscustomobject]@{ path = $k; hash = $v.Hash; duration = [math]::Round($v.Dur, 2); week = $v.Week; sizeMB = $v.SizeMB }
}
$idxRows | Sort-Object week, path | Export-Csv -LiteralPath $IndexFile -NoTypeInformation -Encoding UTF8
Write-Host "索引已更新：$IndexFile（$($index.Count) 条）" -ForegroundColor DarkGray

# ── 内容 → 最早出现的周 ────────────────────────────────────────
$firstSeen = @{}
foreach ($k in $index.Keys) {
    $v = $index[$k]
    if (-not $v.Hash) { continue }
    if (-not $firstSeen.ContainsKey($v.Hash)) { $firstSeen[$v.Hash] = $v.Week }
    elseif ($v.Week -lt $firstSeen[$v.Hash]) { $firstSeen[$v.Hash] = $v.Week }
}

# ── 判定本周每个文件是"新内容"还是"与往期重复"──────────────
$rows = New-Object System.Collections.ArrayList
foreach ($f in @($allFiles | Where-Object { $_.Week -eq $DateFolder })) {
    $v = $index[$f.Path]
    $status = '新内容'; $dupWeek = ''
    if ($v -and $v.Hash) {
        $fs = $firstSeen[$v.Hash]
        if ($fs -and $fs -lt $DateFolder) {
            # 同内容更早出现过，且时长接近 → 判重复
            $same = $false
            foreach ($k in $index.Keys) {
                $o = $index[$k]
                if ($o.Hash -eq $v.Hash -and $o.Week -lt $DateFolder) {
                    if ([Math]::Abs($o.Dur - $v.Dur) -le $DurationTolerance) { $same = $true; break }
                }
            }
            if ($same) { $status = '与往期重复'; $dupWeek = $fs }
        }
    }
    [void]$rows.Add([pscustomobject]@{
            competitor = (Split-Path -Path (Split-Path -Path $f.Path -Parent) -Leaf)
            file       = $f.Name
            status     = $status
            duplicateOf= $dupWeek
            duration   = if ($v) { [math]::Round($v.Dur, 1) } else { 0 }
            sizeMB     = $f.SizeMB
            path       = $f.Path
        })
}

$newRows = @($rows | Where-Object { $_.status -eq '新内容' })
$dupRows = @($rows | Where-Object { $_.status -eq '与往期重复' })
$csvPath = Join-Path $listDir ("新增_" + ($DateFolder -replace '-','') + ".csv")
$rows | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8

Write-Host ''
Write-Host "──── $DateFolder 素材构成 ────────────────────────────" -ForegroundColor Cyan
Write-Host ("  本周文件        : {0} 个 / {1} MB" -f $rows.Count, [math]::Round((($rows | Measure-Object sizeMB -Sum).Sum), 1))
Write-Host ("  新内容          : {0} 个 / {1} MB" -f $newRows.Count, [math]::Round((($newRows | Measure-Object sizeMB -Sum).Sum), 1)) -ForegroundColor Green
Write-Host ("  与往期重复      : {0} 个 / {1} MB（md5 可能不同，但画面同一条）" -f $dupRows.Count, [math]::Round((($dupRows | Measure-Object sizeMB -Sum).Sum), 1)) -ForegroundColor Yellow
if ($dupRows.Count) {
    $dupRows | Group-Object duplicateOf | Sort-Object Name | ForEach-Object { Write-Host ("      来自 {0}: {1} 个" -f $_.Name, $_.Count) }
}
Write-Host "  明细            : $csvPath"
Write-Host '────────────────────────────────────────────────' -ForegroundColor Cyan

# ── 生成分析用目录 ─────────────────────────────────────────────
if ($Mode -ne 'list' -and $newRows.Count -gt 0) {
    if (-not $OutRoot) { $OutRoot = Join-Path $BaseDir '_新增' }
    $outDir = Join-Path $OutRoot $DateFolder
    $made = 0; $failed = 0
    foreach ($r in $newRows) {
        $sub = Join-Path $outDir $r.competitor
        if (-not (Test-Path -LiteralPath $sub)) { New-Item -ItemType Directory -Path $sub -Force | Out-Null }
        $dst = Join-Path $sub $r.file
        if (Test-Path -LiteralPath $dst) { $made++; continue }
        try {
            if ($Mode -eq 'copy') { Copy-Item -LiteralPath $r.path -Destination $dst -Force -ErrorAction Stop }
            else { New-Item -ItemType HardLink -Path $dst -Value $r.path -Force -ErrorAction Stop | Out-Null }
            $made++
        } catch {
            try { Copy-Item -LiteralPath $r.path -Destination $dst -Force -ErrorAction Stop; $made++ } catch { $failed++ }
        }
    }
    Write-Host "分析输入目录：$outDir（$made 个文件，失败 $failed）" -ForegroundColor Green
    Write-Host "下一步：python scripts/probe.py --root `"$outDir`" --out data/probe.json --frames frames --sheets grid,cap" -ForegroundColor Green
}
