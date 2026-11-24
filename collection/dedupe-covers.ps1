<#
  竞品创意速递 · 按封面去重（抽首帧 + 中间帧复核）
  ===============================================================
  用 ffmpeg 抽封面帧（默认第 0.1 秒），缩放 64×64 灰度后算两种指纹：

    1) 封面指纹 XHash = 64×64 灰度像素的 SHA256 → 像素级相同的封面
    2) 感知哈希 AHash = 8×8 块均值二值化的 64 位   → 视觉相似的封面
       （海明距离判定，-Threshold 0 表示必须完全一致，1~4 允许轻微差异）

  两道安全网，避免"同一个片头、内容不同"被误删：
    · 时长须接近（默认 ±0.5 秒），-IgnoreDuration 可关掉
    · 中间帧复核（默认开）：再抽第 50% 处的帧比对，中间帧不同的直接放过，
      -SkipMidFrameCheck 可关掉

  ── 用法（默认演练，只报告不删）─────────────────────────────────
    powershell -ExecutionPolicy Bypass -File .\dedupe-covers.ps1
    powershell -ExecutionPolicy Bypass -File .\dedupe-covers.ps1 -Threshold 2
    powershell -ExecutionPolicy Bypass -File .\dedupe-covers.ps1 -IgnoreDuration -SkipMidFrameCheck
    powershell -ExecutionPolicy Bypass -File .\dedupe-covers.ps1 -Apply -SaveCovers

  -Apply              真的删除
  -Keep               保留：mp4（默认）/ webm / largest / shortest / newest / oldest
  -SaveCovers         每组封面存到 <BaseDir>\_covers\，方便肉眼核对
  -AllDates           整个 E:\video-download（跨天）一起扫
  -Jobs               并发抽帧数（默认 8）
  -At                 首帧取第几秒（默认 0.1）
  报告：<BaseDir>\重复封面.csv
#>
[CmdletBinding()]
param(
    [string]$Root = '',
    [string]$BaseDir = 'E:\video-download',
    [string]$DateFolder = '',
    [switch]$AllDates,
    [double]$At = 0.1,
    [int]$Size = 64,
    [int]$Threshold = 0,
    [switch]$IgnoreDuration,
    [double]$DurationTolerance = 0.5,
    [switch]$SkipMidFrameCheck,
    [ValidateSet('mp4', 'webm', 'largest', 'shortest', 'newest', 'oldest')][string]$Keep = 'mp4',
    [switch]$Apply,
    [int]$Jobs = 8,
    [switch]$SaveCovers
)

$ErrorActionPreference = 'Stop'

# ── 扫描目录 ───────────────────────────────────────────────────
if (-not $Root) {
    if ($AllDates) {
        $Root = $BaseDir
    } elseif ($DateFolder) {
        $Root = Join-Path $BaseDir $DateFolder
    } else {
        $cands = @(Get-ChildItem -LiteralPath $BaseDir -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}' } | Sort-Object Name -Descending)
        if ($cands.Count -gt 0) {
            $Root = $cands[0].FullName
            Write-Host "自动选用最新的日期目录：$($cands[0].Name)" -ForegroundColor DarkGray
        } else { $Root = Join-Path $BaseDir (Get-Date -Format 'yyyy-MM-dd') }
    }
}
if (-not (Test-Path -LiteralPath $Root)) { throw "找不到目录：$Root" }

# ── ffmpeg / ffprobe ──────────────────────────────────────────
$ffmpeg = (Get-Command ffmpeg.exe -ErrorAction SilentlyContinue).Source
$ffprobe = (Get-Command ffprobe.exe -ErrorAction SilentlyContinue).Source
if (-not $ffmpeg) {
    foreach ($c in 'C:\ffmpeg\bin\ffmpeg.exe', 'D:\ffmpeg\bin\ffmpeg.exe', 'C:\tools\ffmpeg\bin\ffmpeg.exe') {
        if (Test-Path -LiteralPath $c) { $ffmpeg = $c; break }
    }
}
if (-not $ffmpeg) { throw '找不到 ffmpeg.exe（可安装到 C:\ffmpeg\bin 或加入 PATH）' }
if (-not $ffprobe) {
    $guess = Join-Path (Split-Path $ffmpeg -Parent) 'ffprobe.exe'
    if (Test-Path -LiteralPath $guess) { $ffprobe = $guess }
}
Write-Host "ffmpeg：$ffmpeg" -ForegroundColor DarkGray
if (-not $ffprobe) { Write-Host '没有 ffprobe → 无法取时长，时长条件将不生效' -ForegroundColor Yellow }

$tmpDir = Join-Path $env:TEMP ('covers_' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $tmpDir -Force | Out-Null

# ── 抽帧 + 指纹（worker，在 runspace 里跑）──────────────────────
# At < 0 表示"取该视频 50% 位置的帧"（中间帧复核用）
$worker = {
    param($File, $Ffmpeg, $Ffprobe, $At, $Size, $TmpDir)
    Add-Type -AssemblyName System.Drawing

    $dur = 0.0
    if ($Ffprobe) {
        $ds = & $Ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 $File 2>$null
        if ($ds) { [void][double]::TryParse("$ds".Trim(), [ref]$dur) }
    }
    if ($At -lt 0) { $seek = if ($dur -gt 1) { $dur * 0.5 } else { 0.1 } } else { $seek = $At }

    $png = Join-Path $TmpDir ([guid]::NewGuid().ToString('N') + '.png')
    $vf = "scale=${Size}:${Size}:flags=area,format=gray"
    & $Ffmpeg -v error -ss "$seek" -i $File -frames:v 1 -vf $vf -y $png 2>$null
    if (-not (Test-Path -LiteralPath $png) -or (Get-Item -LiteralPath $png).Length -eq 0) {
        & $Ffmpeg -v error -i $File -frames:v 1 -vf $vf -y $png 2>$null
    }
    if (-not (Test-Path -LiteralPath $png) -or (Get-Item -LiteralPath $png).Length -eq 0) {
        return @{ Path = $File; Ok = $false; Png = $null; XHash = ''; AHash = [uint64]0; Duration = $dur; Seek = $seek; Error = '抽帧失败' }
    }

    $src = [System.Drawing.Bitmap]::FromFile($png)
    $bmp = New-Object System.Drawing.Bitmap $Size, $Size, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $g = [System.Drawing.Graphics]::FromImage($bmp)
    $g.DrawImage($src, 0, 0, $Size, $Size)
    $g.Dispose(); $src.Dispose()
    $rect = New-Object System.Drawing.Rectangle 0, 0, $Size, $Size
    $bd = $bmp.LockBits($rect, [System.Drawing.Imaging.ImageLockMode]::ReadOnly, [System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $stride = $bd.Stride
    $buf = New-Object byte[] ($stride * $Size)
    [System.Runtime.InteropServices.Marshal]::Copy($bd.Scan0, $buf, 0, $buf.Length)
    $bmp.UnlockBits($bd)
    $bmp.Dispose()

    $sha = [System.Security.Cryptography.SHA256]::Create()
    $hb = $sha.ComputeHash($buf)
    $sha.Dispose()
    $xhash = (($hb | ForEach-Object { $_.ToString('x2') }) -join '')

    $blk = [int]($Size / 8)
    $blocks = New-Object 'double[]' 64
    $sumAll = 0.0
    for ($by = 0; $by -lt 8; $by++) {
        for ($bx = 0; $bx -lt 8; $bx++) {
            $sum = 0.0
            $y0 = $by * $blk; $x0 = $bx * $blk
            for ($y = $y0; $y -lt ($y0 + $blk); $y++) {
                $row = $y * $stride
                for ($x = $x0; $x -lt ($x0 + $blk); $x++) {
                    $p = $row + $x * 4
                    $sum += ($buf[$p] + $buf[$p + 1] + $buf[$p + 2]) / 3.0
                }
            }
            $v = $sum / ($blk * $blk)
            $blocks[$by * 8 + $bx] = $v
            $sumAll += $v
        }
    }
    $avg = $sumAll / 64.0
    [uint64]$ah = 0
    for ($i = 0; $i -lt 64; $i++) { if ($blocks[$i] -gt $avg) { $ah = $ah -bor ([uint64]1 -shl $i) } }

    return @{ Path = $File; Ok = $true; Png = $png; XHash = $xhash; AHash = $ah; Duration = $dur; Seek = $seek; Error = '' }
}

function Invoke-FramePass {
    param($Paths, $AtValue, $Label)
    $pool = [runspacefactory]::CreateRunspacePool(1, [Math]::Max(1, $Jobs))
    $pool.Open()
    $handles = New-Object System.Collections.ArrayList
    foreach ($f in $Paths) {
        $ps = [powershell]::Create()
        $ps.RunspacePool = $pool
        [void]$ps.AddScript($worker).AddArgument($f).AddArgument($ffmpeg).AddArgument($ffprobe).AddArgument($AtValue).AddArgument($Size).AddArgument($tmpDir)
        [void]$handles.Add([pscustomobject]@{ PS = $ps; Handle = $ps.BeginInvoke(); Path = $f })
    }
    $sw = [System.Diagnostics.Stopwatch]::StartNew()
    while ($true) {
        $done = @($handles | Where-Object { $_.Handle.IsCompleted }).Count
        Write-Progress -Activity $Label -Status "$done / $($handles.Count)" -PercentComplete ([int](100 * $done / [Math]::Max(1, $handles.Count)))
        if ($done -ge $handles.Count) { break }
        Start-Sleep -Milliseconds 400
    }
    $map = @{}
    $bad = New-Object System.Collections.ArrayList
    foreach ($h in $handles) {
        try {
            foreach ($r in $h.PS.EndInvoke($h.Handle)) {
                if ($r.Ok) { $map[$r.Path] = $r } else { [void]$bad.Add($r.Path) }
            }
        } catch { [void]$bad.Add($h.Path) } finally { $h.PS.Dispose() }
    }
    $pool.Close(); $pool.Dispose()
    Write-Progress -Activity $Label -Completed
    return @{ Map = $map; Bad = $bad; Seconds = [Math]::Round($sw.Elapsed.TotalSeconds, 1) }
}

# ── 第 1 遍：首帧 ─────────────────────────────────────────────
$files = @(Get-ChildItem -LiteralPath $Root -Recurse -File |
        Where-Object { $_.Extension -match '^\.(mp4|webm)$' -and $_.Length -gt 0 })
if ($files.Count -eq 0) { throw "目录里没有 mp4/webm：$Root" }
$totalGB = [math]::Round((($files | Measure-Object Length -Sum).Sum) / 1GB, 2)
Write-Host "扫描目录：$Root" -ForegroundColor Cyan
Write-Host "第 1 遍·首帧：$($files.Count) 个视频（$totalGB GB），并发 $Jobs …" -ForegroundColor Cyan
$pass1 = Invoke-FramePass -Paths @($files | ForEach-Object { $_.FullName }) -AtValue $At -Label '抽取首帧'
$items = @($pass1.Map.Values)
Write-Host "抽帧成功 $($items.Count)，失败 $($pass1.Bad.Count)，用时 $($pass1.Seconds) 秒" -ForegroundColor Green

# ── 分组 ───────────────────────────────────────────────────────
$pop = New-Object int[] 256
for ($b = 0; $b -lt 256; $b++) { $c = 0; $t = $b; while ($t) { $c += ($t -band 1); $t = $t -shr 1 }; $pop[$b] = $c }
function Get-Hamming([uint64]$a, [uint64]$b) {
    $x = $a -bxor $b
    return ($pop[[int]($x -band 0xFF)] + $pop[[int](($x -shr 8) -band 0xFF)] + $pop[[int](($x -shr 16) -band 0xFF)] +
        $pop[[int](($x -shr 24) -band 0xFF)] + $pop[[int](($x -shr 32) -band 0xFF)] + $pop[[int](($x -shr 40) -band 0xFF)] +
        $pop[[int](($x -shr 48) -band 0xFF)] + $pop[[int](($x -shr 56) -band 0xFF)])
}
function Test-DurationOk($a, $b) {
    if ($IgnoreDuration -or -not $ffprobe) { return $true }
    if ($a.Duration -le 0 -or $b.Duration -le 0) { return $true }
    return ([Math]::Abs($a.Duration - $b.Duration) -le $DurationTolerance)
}

$groups = New-Object System.Collections.ArrayList
if ($Threshold -le 0) {
    $byA = @{}
    foreach ($it in $items) {
        $k = "$($it.AHash)"
        if (-not $byA.ContainsKey($k)) { $byA[$k] = New-Object System.Collections.ArrayList }
        [void]$byA[$k].Add($it)
    }
    foreach ($k in $byA.Keys) {
        $bucket = @($byA[$k])
        if ($bucket.Count -lt 2) { continue }
        $byX = @{}
        foreach ($it in $bucket) {
            if (-not $byX.ContainsKey($it.XHash)) { $byX[$it.XHash] = New-Object System.Collections.ArrayList }
            [void]$byX[$it.XHash].Add($it)
        }
        foreach ($xk in $byX.Keys) {
            $grp = @($byX[$xk])
            if ($grp.Count -lt 2) { continue }
            $sub = @{}
            foreach ($it in $grp) {
                $dk = if ($IgnoreDuration -or -not $ffprobe) { 'x' } else { [string]([Math]::Round($it.Duration * 2) / 2) }
                if (-not $sub.ContainsKey($dk)) { $sub[$dk] = New-Object System.Collections.ArrayList }
                [void]$sub[$dk].Add($it)
            }
            foreach ($s in $sub.Keys) { if ($sub[$s].Count -gt 1) { [void]$groups.Add(@($sub[$s])) } }
        }
    }
} else {
    $used = New-Object 'System.Collections.Generic.HashSet[int]'
    for ($i = 0; $i -lt $items.Count; $i++) {
        if ($used.Contains($i)) { continue }
        $grp = New-Object System.Collections.ArrayList
        [void]$grp.Add($items[$i]); [void]$used.Add($i)
        for ($j = $i + 1; $j -lt $items.Count; $j++) {
            if ($used.Contains($j)) { continue }
            if ((Get-Hamming $items[$i].AHash $items[$j].AHash) -le $Threshold -and (Test-DurationOk $items[$i] $items[$j])) {
                [void]$grp.Add($items[$j]); [void]$used.Add($j)
            }
        }
        if ($grp.Count -gt 1) { [void]$groups.Add(@($grp)) }
    }
}
Write-Host "首帧判定：$($groups.Count) 组候选重复（涉及 $(($groups | ForEach-Object { $_.Count } | Measure-Object -Sum).Sum) 个文件）" -ForegroundColor Cyan

# ── 第 2 遍：中间帧复核 ───────────────────────────────────────
if (-not $SkipMidFrameCheck -and $groups.Count -gt 0) {
    $targets = @($groups | ForEach-Object { $_ } | ForEach-Object { $_.Path } | Select-Object -Unique)
    Write-Host "第 2 遍·中间帧复核：$($targets.Count) 个视频 …" -ForegroundColor Cyan
    $pass2 = Invoke-FramePass -Paths $targets -AtValue -1 -Label '抽取中间帧'
    $mid = $pass2.Map
    Write-Host "中间帧抽帧成功 $($mid.Count)，失败 $($pass2.Bad.Count)，用时 $($pass2.Seconds) 秒" -ForegroundColor Green

    $verified = New-Object System.Collections.ArrayList
    foreach ($g in $groups) {
        if (-not $mid.ContainsKey($g[0].Path)) { continue }
        $ref = $mid[$g[0].Path]
        $kept = New-Object System.Collections.ArrayList
        [void]$kept.Add($g[0])
        for ($i = 1; $i -lt $g.Count; $i++) {
            $it = $g[$i]
            if (-not $mid.ContainsKey($it.Path)) { continue }
            $m = $mid[$it.Path]
            $same = if ($Threshold -le 0) { $m.XHash -eq $ref.XHash } else { (Get-Hamming $m.AHash $ref.AHash) -le $Threshold }
            if ($same) { [void]$kept.Add($it) }
        }
        if ($kept.Count -gt 1) { [void]$verified.Add(@($kept)) }
    }
    Write-Host "中间帧复核后：$($verified.Count) 组确认重复（淘汰 $($groups.Count - $verified.Count) 组）" -ForegroundColor Cyan
    $groups = $verified
}

# ── 处置计划 ───────────────────────────────────────────────────
function Select-Keep($list, $mode) {
    switch ($mode) {
        'mp4' { $p = @($list | Where-Object { [System.IO.Path]::GetExtension($_.Path) -eq '.mp4' }); if ($p.Count) { return $p[0] } }
        'webm' { $p = @($list | Where-Object { [System.IO.Path]::GetExtension($_.Path) -eq '.webm' }); if ($p.Count) { return $p[0] } }
        'largest' { return ($list | Sort-Object { (Get-Item -LiteralPath $_.Path).Length } -Descending)[0] }
        'shortest' { return ($list | Sort-Object { $_.Path.Length })[0] }
        'newest' { return ($list | Sort-Object { (Get-Item -LiteralPath $_.Path).LastWriteTime } -Descending)[0] }
        'oldest' { return ($list | Sort-Object { (Get-Item -LiteralPath $_.Path).LastWriteTime })[0] }
    }
    return $list[0]
}

$plan = New-Object System.Collections.ArrayList
$covDir = Join-Path $BaseDir '_covers'
$gno = 0
foreach ($g in $groups) {
    $gno++
    $g = @($g | Sort-Object { $_.Path })
    $keepFile = Select-Keep $g $Keep
    foreach ($it in $g) {
        if ($it.Path -eq $keepFile.Path) { continue }
        [void]$plan.Add([pscustomobject]@{
                group       = $gno
                reason      = if ($Threshold -le 0) { '首帧+中间帧均相同' } else { "首帧+中间帧相近(≤$Threshold)" }
                keep        = $keepFile.Path
                remove      = $it.Path
                keepSeconds = [math]::Round($keepFile.Duration, 1)
                rmSeconds   = [math]::Round($it.Duration, 1)
                coverHash   = $it.XHash.Substring(0, 16)
                sizeMB      = [math]::Round((Get-Item -LiteralPath $it.Path).Length / 1MB, 2)
            })
    }
    if ($SaveCovers) {
        if (-not (Test-Path $covDir)) { New-Item -ItemType Directory -Path $covDir -Force | Out-Null }
        Copy-Item -LiteralPath $keepFile.Png -Destination (Join-Path $covDir ("g{0:d3}_{1}.png" -f $gno, $keepFile.XHash.Substring(0, 8))) -Force
    }
}

Write-Host ''
if ($plan.Count -eq 0) {
    Write-Host '没有确认重复的视频（首帧与中间帧都一致的才算）。' -ForegroundColor Green
    Remove-Item -LiteralPath $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
    return
}

$freedMB = [math]::Round((($plan | Measure-Object sizeMB -Sum).Sum), 1)
Write-Host "确认 $($groups.Count) 组重复，可删除 $($plan.Count) 个文件，释放 $freedMB MB（保留策略：$Keep）" -ForegroundColor Yellow
$plan | Select-Object -First 8 | ForEach-Object {
    Write-Host ("  [组{0}] 删 {1}  ({2}s, {3} MB)" -f $_.group, $_.remove.Replace($Root, '$Root'), $_.rmSeconds, $_.sizeMB) -ForegroundColor DarkGray
    Write-Host ("        留 {0}  ({1}s)" -f $_.keep.Replace($Root, '$Root'), $_.keepSeconds) -ForegroundColor DarkGray
}

$report = Join-Path $BaseDir '重复封面.csv'
$plan | Export-Csv -LiteralPath $report -NoTypeInformation -Encoding UTF8
Write-Host "`n明细：$report" -ForegroundColor Cyan
if ($SaveCovers) { Write-Host "每组封面：$covDir" -ForegroundColor Cyan }
if ($pass1.Bad.Count -gt 0) { Write-Host "抽帧失败已跳过：$($pass1.Bad.Count) 个" -ForegroundColor Yellow }

if (-not $Apply) {
    Write-Host '演练模式，未删除任何文件。核对后加 -Apply 执行。' -ForegroundColor Green
    Remove-Item -LiteralPath $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
    return
}

$removed = 0; $err = 0
foreach ($p in $plan) {
    try { Remove-Item -LiteralPath $p.remove -Force -ErrorAction Stop; $removed++ }
    catch { $err++; Write-Host "删除失败：$($p.remove)" -ForegroundColor Red }
}
Write-Host "已删除 $removed 个，释放约 $freedMB MB；失败 $err 个。" -ForegroundColor Green

# ── 记入「已删除重复名单」：以后下载自动跳过，不会又被拉回来 ──────
$listDir = Join-Path $BaseDir 'list'
if (-not (Test-Path -LiteralPath $listDir)) { New-Item -ItemType Directory -Path $listDir -Force | Out-Null }
$blockPath = Join-Path $listDir '已删除重复.csv'
$now = (Get-Date).ToString('yyyy-MM-dd HH:mm')
$deletedRows = New-Object System.Collections.ArrayList
foreach ($p in $plan) {
    if (Test-Path -LiteralPath $p.remove) { continue }
    [void]$deletedRows.Add([pscustomobject]@{
            file      = [System.IO.Path]::GetFileName($p.remove)
            folder    = Split-Path -Path (Split-Path -Path $p.remove -Parent) -Leaf
            reason    = $p.reason
            keepFile  = [System.IO.Path]::GetFileName($p.keep)
            deletedAt = $now
        })
}
if ($deletedRows.Count -gt 0) {
    $old = @()
    if (Test-Path -LiteralPath $blockPath) { $old = @(Import-Csv -LiteralPath $blockPath -Encoding UTF8) }
    $seen = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($o in $old) { if ($o.file) { [void]$seen.Add([string]$o.file) } }
    $merged = New-Object System.Collections.ArrayList
    foreach ($o in $old) { [void]$merged.Add($o) }
    foreach ($d in $deletedRows) {
        if (-not $seen.Contains($d.file)) { [void]$merged.Add($d); [void]$seen.Add($d.file) }
    }
    $merged | Export-Csv -LiteralPath $blockPath -NoTypeInformation -Encoding UTF8
    Write-Host "已记入去重名单：$blockPath（累计 $($merged.Count) 条，下次下载自动跳过）" -ForegroundColor Cyan
}
Remove-Item -LiteralPath $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
