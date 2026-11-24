<#
  竞品创意速递 · 视频下载器（自己挑要下哪些）
  ===============================================================
  清单：同目录下的「视频下载清单.csv」（2116 条，含每条的 sizeMB 真实体积）
  产物：<输出目录>\<竞品>\<竞品>_<数据源>_<地区>_<hash>.<mp4|webm>
        默认输出目录 = E:\video-download\<当天日期>\ ，例如
        E:\video-download\2026-10-13\Sugo\Sugo_insightrackr热云_北美洲_10f2bafc.mp4

  特点：免依赖（系统自带 curl.exe，回退 WebClient）、多并发、失败重试、
        断点续传（.part 残留自动续）、跳过已下载、失败清单单独导出。

  ── 先看有什么可选 ────────────────────────────────────────────
    powershell -ExecutionPolicy Bypass -File .\download-videos.ps1 -List

  ── 四种挑法 ─────────────────────────────────────────────────
    1) 交互式挑竞品（推荐，输编号即可）
       .\download-videos.ps1 -Pick

    2) 按竞品 / 数据源（支持通配符）
       .\download-videos.ps1 -Competitor "Sugo"
       .\download-videos.ps1 -Competitor "Tango*","Mico"
       .\download-videos.ps1 -Source "AppGrowing"          # 只会过期的签名链接
       .\download-videos.ps1 -Source "insightrackr*"       # 长期直链

    3) 按清单行号（如 1,3,5-20）——行号顺序见 -List / CSV
       .\download-videos.ps1 -Index 1,3,5-20

    4) 全量
       .\download-videos.ps1 -All

  ── 只要清单不要下载（交给 aria2 / IDM / 迅雷）────────────────
    .\download-videos.ps1 -Competitor "Sugo" -Export sugo.aria2.txt
    aria2c -i sugo.aria2.txt -j 8 -x 4 -c

  ── 清单从哪来 ───────────────────────────────────────────────
    -Manifest E:\...\list\视频下载清单_20261008.csv   指定某一期清单
    不传 = E:\video-download\list\最新清单.csv（由 update-list.ps1 每周刷新）
    -ListDir E:\video-download\list                   清单目录

  ── 输出位置 ─────────────────────────────────────────────────
    默认 = E:\video-download\<清单期号>\
      例：清单是 20261008 那一期 → 输出到 E:\video-download\2026-10-08\
      （期号来源：清单文件名 → list\最新期号.txt → list\清单索引.csv）
    -ByRunDate                改成按"运行当天"建目录（如 2026-10-13）
    -DateFolder 2026-10-13    手动指定日期子目录名
    -DateFolder none          不建日期子目录，直接放 -OutputRoot 下
    -OutputRoot D:\videos     换根目录
    -Root E:\other\path       完全自定义输出目录（指定后上面失效）

  ── 跨周复用（避免每周重复下载同一素材）───────────────────────
    文件名里带素材哈希，所以"同名 = 同一素材"。下载前会先扫一遍其它
    日期目录，同名的直接复用，不再走网络：
      -ReuseMode link   默认：硬链接（同一块磁盘，不额外占空间，秒完成）
      -ReuseMode copy   复制一份（占双倍空间，但两个文件互不影响）
      -ReuseMode skip   只用已有文件、新周目录里不出现
      -ReuseMode off    关闭复用，照旧重新下载
    复用明细写进 list\复用记录_<期号>.csv

  ── 其他常用参数 ─────────────────────────────────────────────
    -Jobs 8             并发数（默认 6）
    -Retries 3          单文件重试次数
    -Limit 20           只取选中集合的前 N 条（先试跑）
    -Simulate           只打印计划，不下载
    -Overwrite          已存在的也重新下
    -IncludeDead        连源站已 404 的 28 条也尝试一遍
    -IgnoreBlocklist    忽略"已删除重复名单"，把删过的再下一次
    -Yes                跳过确认

  注意 1：清单里 2116 条中有 28 条源站视频已被删除（httpStatus=404），脚本默认跳过，
          只剩 2088 条可下，约 5.63 GB。
  注意 2：其中 966 条 AppGrowing 链接带 auth_key 签名，2026-10-23 起陆续失效。
#>
[CmdletBinding()]
param(
    [string]$Manifest = '',
    [string]$ListDir = 'E:\video-download\list',
    [string]$OutputRoot = 'E:\video-download',
    [string]$DateFolder = '',
    [string]$Root = '',
    [int]$Jobs = 6,
    [int]$Retries = 3,
    [string[]]$Competitor = @('*'),
    [string]$Source = '*',
    [string[]]$Index = @(),
    [int]$Limit = 0,
    [string]$Export = '',
    [switch]$ByRunDate,
    [switch]$List,
    [switch]$Pick,
    [switch]$All,
    [switch]$Overwrite,
    [switch]$Simulate,
    [switch]$Yes,
    [switch]$IncludeDead,
    [switch]$IgnoreBlocklist,
    [switch]$NoAlias,
    [ValidateSet('link', 'copy', 'skip', 'off')][string]$ReuseMode = 'link'
)

$ErrorActionPreference = 'Stop'

# ── 解析清单文件：默认用 E:\video-download\list\最新清单.csv ──────
if (-not $Manifest) {
    $latest = Join-Path $ListDir '最新清单.csv'
    if (Test-Path -LiteralPath $latest) {
        $Manifest = $latest
    } else {
        $cands = @(Get-ChildItem -LiteralPath $ListDir -Filter '视频下载清单*.csv' -ErrorAction SilentlyContinue | Sort-Object Name -Descending)
        if ($cands.Count -gt 0) { $Manifest = $cands[0].FullName }
        else {
            $local = Join-Path $PSScriptRoot '视频下载清单.csv'
            if (Test-Path -LiteralPath $local) { $Manifest = $local }
            else { throw "找不到清单：$latest 与 $local 都不存在。请先运行 update-list.ps1 生成清单。" }
        }
    }
}
if (-not (Test-Path -LiteralPath $Manifest)) { throw "找不到清单文件：$Manifest" }

# 期号解析（决定下载目录）：① 清单文件名里的 8 位期号 →
# ② 同目录 最新期号.txt（update-list.ps1 写）→ ③ 同目录 清单索引.csv 里最大的期号
$stamp8 = ''
$mm = [regex]::Match([System.IO.Path]::GetFileNameWithoutExtension($Manifest), '(\d{8})')
if ($mm.Success) { $stamp8 = $mm.Groups[1].Value }
$manifestDir = Split-Path -Path $Manifest -Parent
if (-not $stamp8) {
    $side = Join-Path $manifestDir '最新期号.txt'
    if (Test-Path -LiteralPath $side) {
        $m2 = [regex]::Match((Get-Content -LiteralPath $side -TotalCount 1), '(\d{8})')
        if ($m2.Success) { $stamp8 = $m2.Groups[1].Value }
    }
}
if (-not $stamp8) {
    $idxFile = Join-Path $manifestDir '清单索引.csv'
    if (Test-Path -LiteralPath $idxFile) {
        $e = @(Import-Csv -LiteralPath $idxFile -Encoding UTF8 | Sort-Object 期号 -Descending | Select-Object -First 1)
        if ($e.Count -gt 0) { $stamp8 = "$($e[0].期号)".Trim() }
    }
}
Write-Host "清单：$Manifest$(if ($stamp8) { "（期号 $stamp8）" } else { '' })" -ForegroundColor DarkGray

# ── 解析输出目录：默认 E:\video-download\<清单期号>\ ──────────────
if ($Root) {
    $outDir = $Root
    $modeText = '自定义目录'
} else {
    if ($DateFolder -eq 'none' -or $DateFolder -eq '-') {
        $outDir = $OutputRoot
        $modeText = '不建日期子目录'
    } else {
        if (-not $DateFolder) {
            if ($ByRunDate) {
                $DateFolder = Get-Date -Format 'yyyy-MM-dd'
                $modeText = "按运行当天 $DateFolder"
            } elseif ($stamp8) {
                $DateFolder = [datetime]::ParseExact($stamp8, 'yyyyMMdd', $null).ToString('yyyy-MM-dd')
                $modeText = "按清单期号 $DateFolder"
            } else {
                $DateFolder = Get-Date -Format 'yyyy-MM-dd'
                $modeText = "按当天日期 $DateFolder"
            }
        } else {
            $modeText = "指定日期目录 $DateFolder"
        }
        $outDir = Join-Path $OutputRoot $DateFolder
    }
}
$Root = [System.IO.Path]::GetFullPath($outDir)

# ── 读清单（补 no 行号与 sizeMB 兜底列）──────────────────────────
$everything = @(Import-Csv -LiteralPath $Manifest -Encoding UTF8)
$n = 0
foreach ($r in $everything) {
    $n++
    Add-Member -InputObject $r -NotePropertyName no -NotePropertyValue $n -Force
    if (-not $r.PSObject.Properties['sizeMB']) {
        Add-Member -InputObject $r -NotePropertyName sizeMB -NotePropertyValue 0 -Force
    }
}

# ── 已删除重复名单：去重删掉过的文件不再重复下载 ──────────────────
$blockPath = Join-Path $ListDir '已删除重复.csv'
if ((Test-Path -LiteralPath $blockPath) -and -not $IgnoreBlocklist) {
    $blocked = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($b in @(Import-Csv -LiteralPath $blockPath -Encoding UTF8)) {
        if ($b.file) { [void]$blocked.Add([string]$b.file) }
    }
    $beforeCount = $everything.Count
    $everything = @($everything | Where-Object { -not $blocked.Contains($_.file) })
    $skippedByList = $beforeCount - $everything.Count
    if ($skippedByList -gt 0) {
        Write-Host "按去重名单跳过 $skippedByList 条（$blockPath）" -ForegroundColor DarkGray
    }
}

# ── 竞品别名：把 Tango(2) 这类重复竞品并入主目录 ──────────────────
$aliasPath = Join-Path $ListDir '竞品别名.csv'
$aliasMapped = 0
if ((Test-Path -LiteralPath $aliasPath) -and -not $NoAlias) {
    $alias = @{}
    foreach ($a in @(Import-Csv -LiteralPath $aliasPath -Encoding UTF8)) {
        if ($a.from -and $a.to -and $a.from.Trim() -ne $a.to.Trim()) { $alias[$a.from.Trim()] = $a.to.Trim() }
    }
    if ($alias.Count -gt 0) {
        foreach ($r in $everything) {
            if ($alias.ContainsKey($r.folder)) { $r.folder = $alias[$r.folder]; $aliasMapped++ }
        }
        if ($aliasMapped -gt 0) {
            Write-Host "按竞品别名并入主目录 $aliasMapped 条（$aliasPath）" -ForegroundColor DarkGray
        }
    }
}

$folders = @($everything | Group-Object folder | Sort-Object Name)

function Get-SizeMB($rows) {
    $sum = (@($rows | ForEach-Object { [double]$_.sizeMB }) | Measure-Object -Sum).Sum
    if (-not $sum) { return 0 }
    return [math]::Round($sum, 1)
}

function Expand-Selection([string[]]$Items, [int]$Max) {
    $set = New-Object 'System.Collections.Generic.HashSet[int]'
    foreach ($raw in $Items) {
        foreach ($part in ($raw -split '[,，\s]+' | Where-Object { $_ })) {
            if ($part -match '^(\d+)\s*-\s*(\d+)$') {
                $a = [int]$Matches[1]; $b = [int]$Matches[2]
                if ($a -ge 1 -and $b -le $Max -and $a -le $b) { for ($k = $a; $k -le $b; $k++) { [void]$set.Add($k) } }
            } elseif ($part -match '^\d+$') {
                $a = [int]$part
                if ($a -ge 1 -and $a -le $Max) { [void]$set.Add($a) }
            }
        }
    }
    return @($set)
}

function Show-Catalog {
    Write-Host ''
    Write-Host ("{0,-5} {1,-16} {2,6} {3,11}  {4}" -f '编号', '竞品目录', '条数', '体积(MB)', '清单行号范围') -ForegroundColor Cyan
    Write-Host ('-' * 62) -ForegroundColor DarkGray
    for ($k = 0; $k -lt $folders.Count; $k++) {
        $g = $folders[$k]
        $mb = Get-SizeMB $g.Group
        $range = "$(($g.Group | Measure-Object no -Minimum).Minimum)-$(($g.Group | Measure-Object no -Maximum).Maximum)"
        Write-Host ("[{0,3}] {1,-16} {2,6} {3,11}  {4}" -f ($k + 1), $g.Name, $g.Count, $mb, $range)
    }
    Write-Host ('-' * 62) -ForegroundColor DarkGray
    Write-Host ("合计 {0} 个竞品 / {1} 条 / {2} MB" -f $folders.Count, $everything.Count, (Get-SizeMB $everything)) -ForegroundColor Cyan
}

function Read-Pick([int]$Max) {
    while ($true) {
        $ans = Read-Host '输入竞品编号（如 1,3,5-8；A=全部；Q=退出）'
        $ans = "$ans".Trim()
        if ($ans -match '^[Qq]$') { return @() }
        if ($ans -match '^[Aa]$') { return @(1..$Max) }
        $nums = Expand-Selection @($ans) $Max
        if ($nums.Count -gt 0) { return $nums }
        Write-Host '输入无效。示例：1,3,5-8 或 A 或 Q' -ForegroundColor Yellow
    }
}

# ── 先算选中集合 ────────────────────────────────────────────────
$pickedFolders = $null
if ($Pick) {
    Show-Catalog
    $nums = Read-Pick $folders.Count
    if ($nums.Count -eq 0) { Write-Host '已取消。'; return }
    $pickedFolders = @($nums | ForEach-Object { $folders[$_ - 1].Name })
}

$selected = $null
if ($null -ne $pickedFolders) {
    $selected = @($everything | Where-Object { $pickedFolders -contains $_.folder })
} elseif ($Index.Count -gt 0) {
    $want = Expand-Selection $Index $everything.Count
    $selected = @($everything | Where-Object { $want -contains $_.no })
} else {
    $selected = @($everything | Where-Object {
            $okc = $false
            foreach ($pat in $Competitor) { if ($_.competitor -like $pat -or $_.folder -like $pat) { $okc = $true; break } }
            $okc -and ($_.source -like $Source)
        })
}
if ($Limit -gt 0) { $selected = @($selected | Select-Object -First $Limit) }

# 没给任何筛选条件：只列目录 + 用法，绝不误下全量
$noSelector = (-not $Pick) -and ($Index.Count -eq 0) -and (-not $All) -and
             ((@($Competitor) -join ',') -eq '*') -and ($Source -eq '*') -and ($Limit -eq 0) -and (-not $Export)
if ($List -or $noSelector) {
    Show-Catalog
    Write-Host ''
    Write-Host "输出位置：$Root   （$modeText）" -ForegroundColor Cyan
    $drive = [System.IO.Path]::GetPathRoot($Root).TrimEnd('\')
    if ($drive -and (Test-Path ($drive + '\'))) {
        $free = (Get-PSDrive ($drive.TrimEnd(':')) -ErrorAction SilentlyContinue).Free
        if ($free) { Write-Host ("该盘剩余空间：{0} GB（本次全量约需 5.7 GB）" -f [math]::Round($free / 1GB, 1)) -ForegroundColor DarkGray }
    }
    if ($noSelector) {
        Write-Host ''
        Write-Host '用法：' -ForegroundColor Green
        Write-Host '  .\download-videos.ps1 -Pick                      # 交互式挑竞品'
        Write-Host '  .\download-videos.ps1 -Competitor "Sugo"         # 按竞品名'
        Write-Host '  .\download-videos.ps1 -Source "AppGrowing"       # 按数据源'
        Write-Host '  .\download-videos.ps1 -Index 1,3,5-20            # 按清单行号'
        Write-Host '  .\download-videos.ps1 -All                       # 全部 2088 条'
        Write-Host '  .\download-videos.ps1 -All -Export all.aria2.txt # 只导出清单给 aria2/IDM'
        Write-Host '  .\download-videos.ps1 -All -DateFolder none      # 不建日期子目录'
    }
    return
}

if ($selected.Count -eq 0) {
    Write-Host '没有匹配的条目，检查一下 -Competitor / -Source / -Index 的写法。' -ForegroundColor Yellow
    return
}

$selMB = Get-SizeMB $selected
$selFolders = @($selected | Group-Object folder).Count
Write-Host ''
Write-Host "选中 $($selected.Count) 条 / $selMB MB / $selFolders 个竞品目录" -ForegroundColor Cyan
$expiring = @($selected | Where-Object { $_.linkExpiry })
if ($expiring.Count -gt 0) {
    $soonest = ($expiring | Sort-Object linkExpiry)[0].linkExpiry
    Write-Host "其中 $($expiring.Count) 条为带签名链接，最早 $soonest 过期。" -ForegroundColor Yellow
}

# ── 只导出清单，不下载 ──────────────────────────────────────────
if ($Export) {
    $sb = New-Object System.Text.StringBuilder
    foreach ($r in $selected) {
        [void]$sb.AppendLine($r.url)
        [void]$sb.AppendLine('  dir=' + (Join-Path $Root $r.folder).Replace('\', '/'))
        [void]$sb.AppendLine("  out=$($r.file)")
    }
    $path = if ([System.IO.Path]::IsPathRooted($Export)) { $Export } else { Join-Path $PSScriptRoot $Export }
    [System.IO.File]::WriteAllText($path, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))
    Write-Host "已导出 $($selected.Count) 条到：$path" -ForegroundColor Green
    Write-Host "清单里的 dir= 已写成绝对路径：$($Root.Replace('\', '/'))"
    Write-Host "下载：aria2c -i `"$([System.IO.Path]::GetFileName($path))`" -j 8 -x 4 -c --console-log-level=warn"
    return
}

# ── 跨周复用索引：历史日期目录里已有同名文件就不再下载 ────────────
$reuseIndex = @{}
$reuseDirCount = 0
if ($ReuseMode -ne 'off') {
    $parentDir = Split-Path -Path $Root -Parent
    if ($parentDir -and (Test-Path -LiteralPath $parentDir)) {
        $otherDirs = @(Get-ChildItem -LiteralPath $parentDir -Directory -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match '^\d{4}-\d{2}-\d{2}$' -and $_.FullName -ne $Root } |
                Sort-Object Name -Descending)
        foreach ($d in $otherDirs) {
            $reuseDirCount++
            foreach ($f in @(Get-ChildItem -LiteralPath $d.FullName -Recurse -File -ErrorAction SilentlyContinue |
                        Where-Object { $_.Extension -match '^\.(mp4|webm)$' })) {
                if (-not $reuseIndex.ContainsKey($f.Name)) { $reuseIndex[$f.Name] = $f.FullName }
            }
        }
    }
    if ($reuseDirCount -gt 0) {
        Write-Host "跨周复用索引：$reuseDirCount 个历史日期目录，可复用 $($reuseIndex.Count) 个文件（模式 $ReuseMode）" -ForegroundColor DarkGray
    }
}

# ── 建目录 + 跳过已存在 + 分类（下载 / 复用）──────────────────────
$tasks = New-Object System.Collections.ArrayList
$reuseTasks = New-Object System.Collections.ArrayList
$skipped = 0
$dead = 0
foreach ($r in $selected) {
    # 清单里 httpStatus 非 200 的条目源站已删除，默认跳过（-IncludeDead 可强制尝试）
    $status = ''
    if ($r.PSObject.Properties['httpStatus']) { $status = "$($r.httpStatus)".Trim() }
    if ($status -and $status -ne '200' -and -not $IncludeDead) { $dead++; continue }
    $dir = Join-Path $Root $r.folder
    if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
    $target = Join-Path $dir $r.file
    if ((Test-Path -LiteralPath $target) -and -not $Overwrite -and (Get-Item -LiteralPath $target).Length -gt 0) {
        $skipped++
        continue
    }
    # 上周（或更早）已经下过同名文件 → 不重复下载
    if ($reuseIndex.ContainsKey($r.file)) {
        if ($ReuseMode -eq 'skip') { $skipped++; continue }
        [void]$reuseTasks.Add([pscustomobject]@{ Src = $reuseIndex[$r.file]; Target = $target; File = $r.file })
        continue
    }
    [void]$tasks.Add([pscustomobject]@{ Url = $r.url; Target = $target; SizeMB = $r.sizeMB })
}
$reuseHint = if ($reuseTasks.Count -gt 0) { " ｜ 跨周复用 $($reuseTasks.Count) 条" } else { '' }
Write-Host "输出目录：$Root ｜ 待下载 $($tasks.Count) 条$reuseHint ｜ 跳过已存在 $skipped 条 ｜ 源站已失效跳过 $dead 条" -ForegroundColor Cyan
if ($tasks.Count -eq 0 -and $reuseTasks.Count -eq 0) {
    if ($dead -gt 0) { Write-Host "没有需要下载的文件（$dead 条源站已删除，其余已完成）。" -ForegroundColor Green }
    else { Write-Host '没有需要下载的文件，全部已完成。' -ForegroundColor Green }
    return
}

if ($Simulate) {
    if ($reuseTasks.Count -gt 0) {
        Write-Host "`n[Simulate] 跨周复用 $($reuseTasks.Count) 条（用硬链接/复制，不走网络），示例：" -ForegroundColor Green
        $reuseTasks | Select-Object -First 3 | ForEach-Object {
            Write-Host ("  {0}`n    ⇐ {1}" -f $_.Target.Replace($Root, '$Root'), $_.Src.Replace((Split-Path $Root -Parent), '$Root..'))
        }
    }
    if ($tasks.Count -gt 0) {
        Write-Host "`n[Simulate] 需下载 $($tasks.Count) 条，示例前 10：" -ForegroundColor Green
        $tasks | Select-Object -First 10 | ForEach-Object {
            Write-Host ("  {0}  ({1} MB)`n    <- {2}" -f $_.Target.Replace($Root, '$Root'), $_.SizeMB, $_.Url)
        }
    }
    Write-Host "`n[Simulate] 未执行任何下载。"
    return
}

if (-not $Yes) {
    $ans = Read-Host "确认开始？将下载 $($tasks.Count) 个、复用 $($reuseTasks.Count) 个 (Y/N)"
    if ("$ans" -notmatch '^[Yy]') { Write-Host '已取消。'; return }
}

# ── 执行跨周复用（硬链接优先，失败回退复制）───────────────────────
$reused = 0; $reuseCopied = 0; $reuseFailed = 0
$reuseLog = New-Object System.Collections.ArrayList
if ($reuseTasks.Count -gt 0) {
    foreach ($rt in $reuseTasks) {
        $done = $false
        if ($ReuseMode -eq 'copy') {
            try { Copy-Item -LiteralPath $rt.Src -Destination $rt.Target -Force -ErrorAction Stop; $reuseCopied++; $done = $true } catch { }
        } else {
            try { New-Item -ItemType HardLink -Path $rt.Target -Value $rt.Src -Force -ErrorAction Stop | Out-Null; $reused++; $done = $true } catch { }
            if (-not $done) {
                try { Copy-Item -LiteralPath $rt.Src -Destination $rt.Target -Force -ErrorAction Stop; $reuseCopied++; $done = $true } catch { }
            }
        }
        if (-not $done) { $reuseFailed++ }
        else { [void]$reuseLog.Add([pscustomobject]@{ file = $rt.File; source = $rt.Src; target = $rt.Target; mode = if ($ReuseMode -eq 'copy' -or $reuseCopied -gt 0) { 'link/copy' } else { $ReuseMode } }) }
    }
    Write-Host "跨周复用完成：硬链接 $reused 个，复制 $reuseCopied 个，失败 $reuseFailed 个（都没有走网络）" -ForegroundColor Green
    if ($reuseLog.Count -gt 0) {
        $recPath = Join-Path $ListDir ("复用记录_" + $(if ($stamp8) { $stamp8 } else { (Get-Date -Format 'yyyyMMdd') }) + '.csv')
        $old = @()
        if (Test-Path -LiteralPath $recPath) { $old = @(Import-Csv -LiteralPath $recPath -Encoding UTF8) }
        @($old) + @($reuseLog) | Export-Csv -LiteralPath $recPath -NoTypeInformation -Encoding UTF8
        Write-Host "复用记录：$recPath" -ForegroundColor DarkGray
    }
}

if ($tasks.Count -eq 0) {
    Write-Host '没有需要下载的新文件，全部来自跨周复用。' -ForegroundColor Green
    return
}

# ── 下载工人（独立 runspace）─────────────────────────────────────
$curlExe = (Get-Command curl.exe -ErrorAction SilentlyContinue).Source
$useCurl = [bool]$curlExe
if (-not $useCurl) { Write-Host '未找到 curl.exe，回退到 .NET WebClient（较慢）。' -ForegroundColor Yellow }

$worker = {
    param($Url, $Target, $Retries, $UseCurl, $CurlExe)
    $part = "$Target.part"
    $err = ''
    for ($i = 1; $i -le $Retries; $i++) {
        try {
            if ($UseCurl) {
                $curlArgs = @('-L', '-sS', '--fail', '--connect-timeout', '20', '--max-time', '900', '-o', $part)
                if (Test-Path -LiteralPath $part) { $curlArgs += @('-C', '-') }
                $curlArgs += $Url
                & $CurlExe @curlArgs
                if ($LASTEXITCODE -ne 0) { throw "curl 退出码 $LASTEXITCODE" }
            } else {
                $wc = New-Object System.Net.WebClient
                $wc.Headers.Add('User-Agent', 'Mozilla/5.0 (compatible; creative-downloader)')
                $wc.DownloadFile($Url, $part)
                $wc.Dispose()
            }
            $len = (Get-Item -LiteralPath $part).Length
            if ($len -le 0) { throw '下载到的文件为空' }
            Move-Item -LiteralPath $part -Destination $Target -Force
            return @{ Ok = $true; Target = $Target; Bytes = $len; Error = '' }
        } catch {
            $err = $_.Exception.Message
            Start-Sleep -Seconds ([Math]::Min(15, 2 * $i))
        }
    }
    Remove-Item -LiteralPath $part -ErrorAction SilentlyContinue
    return @{ Ok = $false; Target = $Target; Bytes = 0; Error = $err }
}

$pool = [runspacefactory]::CreateRunspacePool(1, $Jobs)
$pool.Open()
$handles = New-Object System.Collections.ArrayList
foreach ($t in $tasks) {
    $ps = [powershell]::Create()
    $ps.RunspacePool = $pool
    [void]$ps.AddScript($worker).AddArgument($t.Url).AddArgument($t.Target).AddArgument($Retries).AddArgument($useCurl).AddArgument($curlExe)
    [void]$handles.Add([pscustomobject]@{ PS = $ps; Handle = $ps.BeginInvoke(); Target = $t.Target; Url = $t.Url })
}

$watch = [System.Diagnostics.Stopwatch]::StartNew()
while ($true) {
    $done = @($handles | Where-Object { $_.Handle.IsCompleted }).Count
    Write-Progress -Activity '下载竞品视频' -Status "$done / $($handles.Count)" -PercentComplete ([int](100 * $done / $handles.Count))
    if ($done -ge $handles.Count) { break }
    Start-Sleep -Milliseconds 300
}

$failed = New-Object System.Collections.ArrayList
$totalBytes = 0L
foreach ($h in $handles) {
    try {
        foreach ($res in $h.PS.EndInvoke($h.Handle)) {
            if ($res.Ok) { $totalBytes += [int64]$res.Bytes }
            else { [void]$failed.Add([pscustomobject]@{ target = $res.Target; url = $h.Url; error = $res.Error }) }
        }
    } catch {
        [void]$failed.Add([pscustomobject]@{ target = $h.Target; url = $h.Url; error = $_.Exception.Message })
    } finally {
        $h.PS.Dispose()
    }
}
$pool.Close(); $pool.Dispose()
Write-Progress -Activity '下载竞品视频' -Completed

Write-Host ''
Write-Host "完成：新下载 $($tasks.Count - $failed.Count) / $($tasks.Count)，跨周复用 $($reused + $reuseCopied) 条，跳过已存在 $skipped，源站失效 $dead，本次选中 $($selected.Count) 条" -ForegroundColor Green
Write-Host ("累计下载 {0} MB，用时 {1} 分钟，输出目录：{2}" -f [math]::Round($totalBytes / 1MB, 1), [math]::Round($watch.Elapsed.TotalMinutes, 1), $Root)
if ($failed.Count -gt 0) {
    $failPath = Join-Path $PSScriptRoot '下载失败.csv'
    $failed | Export-Csv -LiteralPath $failPath -NoTypeInformation -Encoding UTF8
    Write-Host "失败 $($failed.Count) 条，已写入：$failPath（重跑会自动重试，.part 断点保留）" -ForegroundColor Yellow
}
