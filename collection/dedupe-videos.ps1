<#
  竞品创意速递 · 视频去重（按内容指纹）
  ===============================================================
  在下载目录里找出「内容真正相同」的视频，默认只报告不删除。

  判定方式（两遍法，避免白读 5.6 GB）：
    第一遍 按文件字节数分组，只有长度相同的才继续；
    第二遍 组内算 SHA256，指纹相同 = 内容完全相同的重复文件。

  另有 -CrossFormat：把「同一素材的 mp4 / webm 双封装」也算重复
    （依据文件名结尾的 _<hash8> 相同而扩展名不同，例如
      Tango(1)_insightrackr热云_北美洲_f461036e.webm 与
      Tango(2)_insightrackr热云_东南亚_f461036e.mp4）

  ── 用法 ──────────────────────────────────────────────────────
    powershell -ExecutionPolicy Bypass -File .\dedupe-videos.ps1                 # 只扫描报告
    powershell -ExecutionPolicy Bypass -File .\dedupe-videos.ps1 -CrossFormat    # 连 mp4/webm 双份一起算
    powershell -ExecutionPolicy Bypass -File .\dedupe-videos.ps1 -Apply          # 真删（保留策略见 -Keep）
    powershell -ExecutionPolicy Bypass -File .\dedupe-videos.ps1 -Keep webm -Apply

  ── 扫哪个目录 ────────────────────────────────────────────────
    默认 = E:\video-download\<最新的日期目录>\ （例如 2026-10-13）
    -DateFolder 2026-10-08    指定某一天的目录
    -AllDates                 整个 E:\video-download 一起扫（能揪出跨天重复的素材）
    -Root D:\videos           完全自定义目录

  -Keep 保留哪一个：mp4（默认，优先保留 mp4）/ webm / largest / shortest / oldest
  报告文件：重复视频.csv（含 保留文件 / 待删文件 / 体积 / 原因）
#>
[CmdletBinding()]
param(
    [string]$Root = '',
    [string]$BaseDir = 'E:\video-download',
    [string]$DateFolder = '',
    [switch]$AllDates,
    [ValidateSet('SHA256', 'MD5')][string]$Algorithm = 'SHA256',
    [ValidateSet('mp4', 'webm', 'largest', 'shortest', 'oldest')][string]$Keep = 'mp4',
    [switch]$CrossFormat,
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'

# ── 解析扫描目录 ────────────────────────────────────────────────
if (-not $Root) {
    if ($AllDates) {
        $Root = $BaseDir
        Write-Host "扫描整个目录（含所有日期子目录）：$Root" -ForegroundColor DarkGray
    } elseif ($DateFolder) {
        $Root = Join-Path $BaseDir $DateFolder
    } else {
        $cands = @(Get-ChildItem -LiteralPath $BaseDir -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}' } | Sort-Object Name -Descending)
        if ($cands.Count -gt 0) {
            $Root = $cands[0].FullName
            Write-Host "自动选用最新的日期目录：$($cands[0].Name)" -ForegroundColor DarkGray
        } else {
            $Root = Join-Path $BaseDir (Get-Date -Format 'yyyy-MM-dd')
        }
    }
}
if (-not (Test-Path -LiteralPath $Root)) {
    throw "找不到目录：$Root`n（E:\video-download 下现有子目录：$(if (Test-Path $BaseDir) { (@(Get-ChildItem $BaseDir -Directory | ForEach-Object { $_.Name }) -join ', ') } else { '根目录不存在' })）"
}

function Select-Keep($list, $mode) {
    switch ($mode) {
        'mp4' { $p = @($list | Where-Object { $_.Extension -eq '.mp4' }); if ($p.Count) { return $p[0] } }
        'webm' { $p = @($list | Where-Object { $_.Extension -eq '.webm' }); if ($p.Count) { return $p[0] } }
        'largest' { return ($list | Sort-Object Length -Descending)[0] }
        'shortest' { return ($list | Sort-Object { $_.FullName.Length })[0] }
        'oldest' { return ($list | Sort-Object LastWriteTime)[0] }
    }
    return $list[0]
}

$files = @(Get-ChildItem -LiteralPath $Root -Recurse -File |
        Where-Object { $_.Extension -match '^\.(mp4|webm)$' -and $_.Length -gt 0 })
if ($files.Count -eq 0) { throw "目录里没有 mp4/webm：$Root" }
Write-Host "扫描 $($files.Count) 个视频（$([math]::Round((($files | Measure-Object Length -Sum).Sum) / 1GB, 2)) GB）…" -ForegroundColor Cyan

# ── 第一遍：按字节数分组 ────────────────────────────────────────
$sameSize = @($files | Group-Object Length | Where-Object { $_.Count -gt 1 })
$hashed = 0
$groups = New-Object System.Collections.ArrayList

foreach ($g in $sameSize) {
    $byHash = @{}
    foreach ($f in $g.Group) {
        $h = (Get-FileHash -LiteralPath $f.FullName -Algorithm $Algorithm).Hash
        $hashed++
        if (-not $byHash.ContainsKey($h)) { $byHash[$h] = New-Object System.Collections.ArrayList }
        [void]$byHash[$h].Add($f)
    }
    foreach ($k in $byHash.Keys) {
        if ($byHash[$k].Count -gt 1) {
            [void]$groups.Add([pscustomobject]@{ Reason = '内容完全相同'; Files = $byHash[$k] })
        }
    }
}
Write-Host "实际计算指纹 $hashed 个（只有字节数相同的才需要算）" -ForegroundColor DarkGray

# ── 可选：mp4 / webm 双封装 ─────────────────────────────────────
if ($CrossFormat) {
    $bySuffix = @{}
    foreach ($f in $files) {
        if ($f.BaseName -match '_([0-9a-fA-F]{8,})$') {
            $key = $Matches[1].ToLower()
            if (-not $bySuffix.ContainsKey($key)) { $bySuffix[$key] = New-Object System.Collections.ArrayList }
            [void]$bySuffix[$key].Add($f)
        }
    }
    foreach ($k in $bySuffix.Keys) {
        $grp = @($bySuffix[$k])
        $exts = @($grp | ForEach-Object { $_.Extension.ToLower() } | Select-Object -Unique)
        if ($grp.Count -gt 1 -and $exts.Count -gt 1) {
            [void]$groups.Add([pscustomobject]@{ Reason = "同素材双封装（$($exts -join ' / ')，hash $k）"; Files = $grp })
        }
    }
}

# ── 生成处置计划（同一文件只处理一次）────────────────────────────
$claimed = New-Object 'System.Collections.Generic.HashSet[string]'
$plan = New-Object System.Collections.ArrayList
foreach ($g in $groups) {
    $list = @($g.Files | Where-Object { -not $claimed.Contains($_.FullName) })
    if ($list.Count -lt 2) { continue }
    $keepFile = Select-Keep $list $Keep
    foreach ($f in $list) { [void]$claimed.Add($f.FullName) }
    foreach ($f in $list) {
        if ($f.FullName -ne $keepFile.FullName) {
            [void]$plan.Add([pscustomobject]@{
                    reason  = $g.Reason
                    keep    = $keepFile.FullName
                    remove  = $f.FullName
                    sizeMB  = [math]::Round($f.Length / 1MB, 2)
                })
        }
    }
}

if ($plan.Count -eq 0) {
    Write-Host '没有发现重复视频。' -ForegroundColor Green
    return
}

$freedMB = [math]::Round((($plan | Measure-Object sizeMB -Sum).Sum), 1)
Write-Host ''
Write-Host "发现 $($plan.Count) 个可删除的重复文件，可释放 $freedMB MB（保留策略：$Keep）" -ForegroundColor Yellow
$plan | Group-Object reason | Sort-Object Count -Descending | ForEach-Object {
    Write-Host ("  {0,-28} {1,4} 个" -f $_.Name, $_.Count)
}
$plan | Select-Object -First 5 | ForEach-Object {
    Write-Host "  删 $($_.remove.Replace($Root, '$Root'))" -ForegroundColor DarkGray
    Write-Host "    留 $($_.keep.Replace($Root, '$Root'))" -ForegroundColor DarkGray
}

$report = Join-Path $BaseDir '重复视频.csv'
$plan | Export-Csv -LiteralPath $report -NoTypeInformation -Encoding UTF8
Write-Host "`n处置明细已写入：$report" -ForegroundColor Cyan

if (-not $Apply) {
    Write-Host '这是预览模式，没有删除任何文件。确认无误后加 -Apply 执行。' -ForegroundColor Green
    return
}

$removed = 0; $failedDel = 0
foreach ($p in $plan) {
    try {
        Remove-Item -LiteralPath $p.remove -Force -ErrorAction Stop
        $removed++
    } catch {
        $failedDel++
        Write-Host "删除失败：$($p.remove) — $($_.Exception.Message)" -ForegroundColor Red
    }
}
Write-Host "已删除 $removed 个重复文件，释放约 $freedMB MB；失败 $failedDel 个。" -ForegroundColor Green
