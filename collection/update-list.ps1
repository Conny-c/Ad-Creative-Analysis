<#
  竞品创意速递 · 第一期流水线（抓页面 → 提取链接 → 生成清单）
  ===============================================================
  从竞品周推页面里把内嵌的 const creatives 数据整段抽出来，生成下载清单，
  统一放在  E:\video-download\list\  ：

      视频下载清单_20261008.csv     完整清单（竞品/文件名/体积/链接状态/签名过期时间）
      最新清单.csv                  始终是最近一期的副本，下载脚本默认读它
      aria2_20261008.txt            可直接交给 aria2 / IDM / 迅雷 的输入清单
      清单索引.csv                  每期的汇总台账（条数、可下数、体积、页面地址）

  ── 用法 ──────────────────────────────────────────────────────
    # 自动找最新一期（从今天往回找，默认回溯 45 天）
    powershell -ExecutionPolicy Bypass -File .\update-list.ps1

    # 指定期号 / 指定页面
    powershell -ExecutionPolicy Bypass -File .\update-list.ps1 -Date 20261008
    powershell -ExecutionPolicy Bypass -File .\update-list.ps1 -Url "https://<你的素材源域名>/xxxx.html"

    # 跳过体积/状态探测（快很多，但清单里没有 sizeMB/httpStatus）
    powershell -ExecutionPolicy Bypass -File .\update-list.ps1 -SkipHead

  说明：站点根目录没有索引，所以"自动找"是按文件名规律
        https://<你的素材源域名>/<yyyyMMdd>-竞品周推.html 逐日回探，
        命中第一个 HTTP 200 且含 const creatives 的页面即采用。
#>
[CmdletBinding()]
param(
    [string]$Url = '',
    [string]$Date = '',
    [int]$Lookback = 45,
    [string]$BaseUrl = 'https://<你的素材源域名>',
    [string[]]$NameTemplates = @('竞品周推', '竞品周报', '竞品创意速递'),
    [string]$ListDir = 'E:\video-download\list',
    [switch]$SkipHead,
    [int]$HeadJobs = 16,
    [switch]$KeepHtml
)

$ErrorActionPreference = 'Stop'

# ── 取页面 HTML（自签证书用 curl -k，回退 .NET）───────────────────
function Get-PageHtml([string]$u) {
    $curlExe = (Get-Command curl.exe -ErrorAction SilentlyContinue).Source
    if ($curlExe) {
        $tmp = Join-Path $env:TEMP ("jl_" + [guid]::NewGuid().ToString('N') + '.html')
        $code = & $curlExe -k -sS -L --max-time 90 -o $tmp -w '%{http_code}' $u
        if ("$code" -ne '200') { Remove-Item $tmp -Force -ErrorAction SilentlyContinue; return $null }
        $html = [System.IO.File]::ReadAllText($tmp, [System.Text.Encoding]::UTF8)
        if (-not $KeepHtml) { Remove-Item $tmp -Force -ErrorAction SilentlyContinue } else { Write-Host "  页面已保存：$tmp" -ForegroundColor DarkGray }
        return $html
    }
    try {
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
        [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.SecurityProtocolType]::Tls12
        $wc = New-Object System.Net.WebClient
        $bytes = $wc.DownloadData($u)
        $wc.Dispose()
        return [System.Text.Encoding]::UTF8.GetString($bytes)
    } catch { return $null }
}

function Test-UrlExists([string]$u) {
    $curlExe = (Get-Command curl.exe -ErrorAction SilentlyContinue).Source
    if ($curlExe) {
        $code = & $curlExe -k -sS -I -o NUL --max-time 20 -w '%{http_code}' $u
        return ("$code" -eq '200')
    }
    try {
        [System.Net.ServicePointManager]::ServerCertificateValidationCallback = { $true }
        $req = [System.Net.HttpWebRequest]::Create($u)
        $req.Method = 'HEAD'
        $req.Timeout = 20000
        $resp = $req.GetResponse()
        $ok = ($resp.StatusCode -eq 200)
        $resp.Close()
        return $ok
    } catch { return $false }
}

# ── 1. 定位页面 ─────────────────────────────────────────────────
$pageUrl = ''
if ($Url) {
    $pageUrl = $Url
    Write-Host "使用指定页面：$pageUrl" -ForegroundColor Cyan
} elseif ($Date) {
    $d = $Date -replace '\D', ''
    if ($d.Length -ne 8) { throw "-Date 需要 yyyyMMdd 或 yyyy-MM-dd，例如 20261008" }
    foreach ($t in $NameTemplates) {
        $cand = "$BaseUrl/$d-$([uri]::EscapeDataString($t)).html"
        if (Test-UrlExists $cand) { $pageUrl = $cand; break }
    }
    if (-not $pageUrl) { throw "找不到期号 $d 对应的页面（试过：$($NameTemplates -join ' / ')）" }
    Write-Host "按期号定位到：$pageUrl" -ForegroundColor Cyan
} else {
    $today = Get-Date
    for ($i = 0; $i -le $Lookback; $i++) {
        $d = $today.AddDays(-$i)
        $stamp = $d.ToString('yyyyMMdd')
        foreach ($t in $NameTemplates) {
            $cand = "$BaseUrl/$stamp-$([uri]::EscapeDataString($t)).html"
            if (Test-UrlExists $cand) { $pageUrl = $cand; break }
        }
        if ($pageUrl) { break }
    }
    if (-not $pageUrl) { throw "最近 $Lookback 天都没找到新页面（从 $($today.ToString('yyyy-MM-dd')) 往回找）" }
    Write-Host "自动找到最新一期：$pageUrl" -ForegroundColor Cyan
}

# ── 2. 抓 HTML + 抽 creatives ───────────────────────────────────
Write-Host '正在下载页面…' -ForegroundColor DarkGray
$html = Get-PageHtml $pageUrl
if (-not $html) { throw "页面抓取失败：$pageUrl" }
Write-Host ("页面大小：{0:N0} 字符" -f $html.Length) -ForegroundColor DarkGray

$json = ''
$m = [regex]::Match($html, 'const\s+creatives\s*=\s*(\[[\s\S]*?\])\s*;')
if ($m.Success) { $json = $m.Groups[1].Value }
if ($json) {
    try { $null = $json | ConvertFrom-Json } catch { $json = '' }
}
if (-not $json) {
    # 正则不稳时用括号深度扫描兜底（正确处理字符串内的引号与转义）
    $i = $html.IndexOf('const creatives')
    if ($i -lt 0) { throw '页面里找不到 const creatives 数据块（模板可能变了）' }
    $start = $html.IndexOf('[', $i)
    $depth = 0; $inStr = $false; $esc = $false; $end = -1
    for ($k = $start; $k -lt $html.Length; $k++) {
        $ch = $html[$k]
        if ($inStr) {
            if ($esc) { $esc = $false }
            elseif ($ch -eq '\') { $esc = $true }
            elseif ($ch -eq '"') { $inStr = $false }
            continue
        }
        if ($ch -eq '"') { $inStr = $true; continue }
        if ($ch -eq '[') { $depth++ }
        elseif ($ch -eq ']') { $depth--; if ($depth -eq 0) { $end = $k; break } }
    }
    if ($end -lt 0) { throw 'creatives 数组不完整，解析失败' }
    $json = $html.Substring($start, $end - $start + 1)
}
# 注意：PS 5.1 的 ConvertFrom-Json 会把整个数组当作“单个对象”输出，
# 所以这里必须先赋值给变量再用 @() 包，否则会得到「1 个元素 = 整个数组」的坑。
$parsed = ConvertFrom-Json -InputObject $json
$creatives = @($parsed)
Write-Host "提取到 $($creatives.Count) 条素材数据" -ForegroundColor Green
if ($creatives.Count -eq 0) { throw '提取到 0 条，放弃。' }
if (-not $creatives[0].PSObject.Properties['video']) {
    throw "数据结构不对：第一条里没有 video 字段（拿到的是 $($creatives[0].GetType().FullName)），页面模板可能变了。"
}
if ($creatives.Count -lt 10) {
    Write-Host "警告：只提取到 $($creatives.Count) 条，明显偏少，请核对页面。" -ForegroundColor Yellow
}

# ── 3. 期号（报告日期）───────────────────────────────────────────
$reportDate = $null
$tm = [regex]::Match($html, '<title>\s*(\d{4})年(\d{1,2})月(\d{1,2})日')
if ($tm.Success) {
    $reportDate = [datetime]::new([int]$tm.Groups[1].Value, [int]$tm.Groups[2].Value, [int]$tm.Groups[3].Value)
} else {
    $um = [regex]::Match($pageUrl, '/(\d{8})-')
    if ($um.Success) { $reportDate = [datetime]::ParseExact($um.Groups[1].Value, 'yyyyMMdd', $null) }
}
if (-not $reportDate) { $reportDate = Get-Date }
$stamp8 = $reportDate.ToString('yyyyMMdd')
$dateFolder = $reportDate.ToString('yyyy-MM-dd')
Write-Host "报告日期：$dateFolder（下载目录将是 E:\video-download\$dateFolder）" -ForegroundColor Cyan

# ── 4. 生成清单（按竞品分目录 + 唯一文件名）──────────────────────
function San([string]$s) {
    if ($null -eq $s) { return '' }
    $s = [uri]::UnescapeDataString($s)
    $s = $s -replace '[\\/:*?"<>|\x00-\x1f]', '-'
    $s = $s -replace '\s*[;；]\s*', '-'
    $s = $s -replace '\s+', ' '
    return $s.Trim(' ', '.', '-')
}

$epoch = [datetime]'1970-01-01 00:00:00Z'
$taken = @{}
$rows = foreach ($c in $creatives) {
    $url = [uri]::UnescapeDataString($c.video)
    $noq = ($url -split '\?')[0]
    $base = [System.IO.Path]::GetFileName($noq)
    $ext = [System.IO.Path]::GetExtension($base).TrimStart('.').ToLower()
    if (-not $ext) { $ext = 'mp4' }
    $h = ($base -replace '\.[a-z0-9]+$', '') -replace '^x_v_', ''
    $h = ($h -replace '[^0-9a-zA-Z]', '')

    $comp = San $c.competitor; $src = San $c.source; $reg = San $c.crawlRegions
    $hashLen = 8
    while ($true) {
        $hash = $h.Substring(0, [Math]::Min($hashLen, $h.Length))
        $file = "$comp`_$src`_$reg`_$hash.$ext"
        if ($file.Length -gt 120) { $file = $comp.Substring(0, [Math]::Min(40, $comp.Length)) + "_$src`_$hash.$ext" }
        $key = "$comp/$file"
        if (-not $taken.ContainsKey($key)) { $taken[$key] = 1; break }
        $hashLen++
        if ($hashLen -gt $h.Length) { $file = "$comp`_$src`_$reg`_$($c.id).$ext"; $taken["$comp/$file"] = 1; break }
    }

    $km = [regex]::Match($url, 'auth_key=(\d{10})')
    [pscustomobject]@{
        competitor     = $c.competitor
        source         = $c.source
        region         = $c.region
        crawlRegions   = $c.crawlRegions
        folder         = $comp
        file           = $file
        sizeMB         = 0
        httpStatus     = ''
        url            = $url
        linkType       = if ($km.Success) { '带签名(会过期)' } else { '长期直链' }
        linkExpiry     = if ($km.Success) { [datetime]::SpecifyKind($epoch.AddSeconds([int64]$km.Groups[1].Value), [DateTimeKind]::Utc).ToLocalTime().ToString('yyyy-MM-dd HH:mm') } else { '' }
    }
}
$rows = @($rows)
$uniq = @($rows | ForEach-Object { "$($_.folder)/$($_.file)" } | Select-Object -Unique)
Write-Host "清单 $($rows.Count) 条，唯一路径 $($uniq.Count) 条" -ForegroundColor Green
if ($uniq.Count -ne $rows.Count) { throw '文件名冲突没能完全消除，请检查数据。' }

# ── 5. HEAD 探测体积与链接状态 ──────────────────────────────────
if (-not $SkipHead) {
    Write-Host '正在探测每条链接的体积与状态（这就是慢的一步）…' -ForegroundColor DarkGray
    $curlExe = (Get-Command curl.exe -ErrorAction SilentlyContinue).Source
    $worker = {
        param($Url, $CurlExe)
        $h = & $CurlExe -k -sS -I --connect-timeout 15 --max-time 45 $Url 2>$null
        $txt = $h -join "`n"
        $status = 0; $bytes = 0
        $m1 = [regex]::Match($txt, '(?m)^HTTP/[\d.]+ (\d{3})')
        if ($m1.Success) { $status = [int]$m1.Groups[1].Value }
        $m2 = [regex]::Match($txt, '(?im)^Content-Length:\s*(\d+)')
        if ($m2.Success) { $bytes = [int64]$m2.Groups[1].Value }
        return @{ Url = $Url; Status = $status; Bytes = $bytes }
    }
    $pool = [runspacefactory]::CreateRunspacePool(1, $HeadJobs)
    $pool.Open()
    $hs = New-Object System.Collections.ArrayList
    foreach ($r in $rows) {
        $ps = [powershell]::Create(); $ps.RunspacePool = $pool
        [void]$ps.AddScript($worker).AddArgument($r.url).AddArgument($curlExe)
        [void]$hs.Add([pscustomobject]@{ PS = $ps; Handle = $ps.BeginInvoke() })
    }
    while (@($hs | Where-Object { $_.Handle.IsCompleted }).Count -lt $hs.Count) {
        $done = @($hs | Where-Object { $_.Handle.IsCompleted }).Count
        Write-Progress -Activity '探测链接' -Status "$done / $($hs.Count)" -PercentComplete ([int](100 * $done / $hs.Count))
        Start-Sleep -Milliseconds 400
    }
    $info = @{}
    foreach ($h in $hs) {
        foreach ($res in $h.PS.EndInvoke($h.Handle)) { $info[$res.Url] = $res }
        $h.PS.Dispose()
    }
    $pool.Close(); $pool.Dispose()
    Write-Progress -Activity '探测链接' -Completed
    foreach ($r in $rows) {
        $s = $info[$r.url]
        if ($s) {
            $r.httpStatus = [string]$s.Status
            if ($s.Bytes -gt 0) { $r.sizeMB = [math]::Round($s.Bytes / 1MB, 2) }
        }
    }
}

# ── 6. 落盘 ─────────────────────────────────────────────────────
if (-not (Test-Path -LiteralPath $ListDir)) { New-Item -ItemType Directory -Path $ListDir -Force | Out-Null }
$csvPath = Join-Path $ListDir "视频下载清单_$stamp8.csv"
$rows | Export-Csv -LiteralPath $csvPath -NoTypeInformation -Encoding UTF8

$latestPath = Join-Path $ListDir '最新清单.csv'
Copy-Item -LiteralPath $csvPath -Destination $latestPath -Force
# 期号侧车文件：下载脚本靠它知道"最新清单"属于哪一期（文件名里看不出来）
[System.IO.File]::WriteAllText((Join-Path $ListDir '最新期号.txt'), "$stamp8|$dateFolder$([Environment]::NewLine)", (New-Object System.Text.UTF8Encoding($false)))

$ariaPath = Join-Path $ListDir "aria2_$stamp8.txt"
$sb = New-Object System.Text.StringBuilder
$videoDir = ('E:\video-download\' + $dateFolder).Replace('\', '/')
foreach ($r in $rows) {
    [void]$sb.AppendLine($r.url)
    [void]$sb.AppendLine("  dir=$videoDir/$($r.folder)")
    [void]$sb.AppendLine("  out=$($r.file)")
}
[System.IO.File]::WriteAllText($ariaPath, $sb.ToString(), (New-Object System.Text.UTF8Encoding($false)))

# ── 7. 台账（每期一行，可反复覆盖）──────────────────────────────
$okRows = @($rows | Where-Object { $_.httpStatus -eq '200' -or $_.httpStatus -eq '' })
$badRows = @($rows | Where-Object { $_.httpStatus -and $_.httpStatus -ne '200' })
$okMB = [math]::Round((($okRows | Measure-Object sizeMB -Sum).Sum), 1)
$signRows = @($rows | Where-Object { $_.linkExpiry })
$idxPath = Join-Path $ListDir '清单索引.csv'
$entry = [pscustomobject]@{
    期号         = $stamp8
    报告日期     = $dateFolder
    页面         = $pageUrl
    条数         = $rows.Count
    可下载       = $okRows.Count
    已失效       = $badRows.Count
    总体积MB     = $okMB
    带签名条数   = $signRows.Count
    最早过期     = if ($signRows.Count) { ($signRows | Sort-Object linkExpiry)[0].linkExpiry } else { '' }
    清单文件     = [System.IO.Path]::GetFileName($csvPath)
    生成时间     = (Get-Date).ToString('yyyy-MM-dd HH:mm')
}
$idx = @()
if (Test-Path -LiteralPath $idxPath) { $idx = @(Import-Csv -LiteralPath $idxPath -Encoding UTF8 | Where-Object { $_.期号 -ne $stamp8 }) }
$idx = @($idx) + @($entry)
$idx | Sort-Object 期号 | Export-Csv -LiteralPath $idxPath -NoTypeInformation -Encoding UTF8

# ── 8. 汇报 ─────────────────────────────────────────────────────
Write-Host ''
Write-Host '──── 本期清单 ────────────────────────────────' -ForegroundColor Cyan
Write-Host "  期号        : $stamp8（$dateFolder）"
Write-Host "  页面        : $pageUrl"
Write-Host "  素材条数    : $($rows.Count)"
Write-Host "  可下载      : $($okRows.Count) 条 / $okMB MB"
if ($badRows.Count) { Write-Host "  源站已失效  : $($badRows.Count) 条（已标 httpStatus，下载脚本会自动跳过）" -ForegroundColor Yellow }
if ($signRows.Count) {
    Write-Host "  带签名链接  : $($signRows.Count) 条，最早 $(($signRows | Sort-Object linkExpiry)[0].linkExpiry) 过期" -ForegroundColor Yellow
}
Write-Host "  竞品目录    : $((@($rows | Group-Object folder)).Count) 个"
Write-Host ''
Write-Host "  清单   : $csvPath"
Write-Host "  最新   : $latestPath"
Write-Host "  aria2  : $ariaPath"
Write-Host "  台账   : $idxPath"
Write-Host '──────────────────────────────────────────────' -ForegroundColor Cyan
Write-Host "下一步：powershell -ExecutionPolicy Bypass -File .\download-videos.ps1 -All" -ForegroundColor Green
