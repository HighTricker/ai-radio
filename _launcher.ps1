# ============================================================
#  AI 音乐电台 · 一键启动器（逻辑文件）
#  请不要直接双击本文件，双击同目录的「点我启动电台.bat」。
# ============================================================

try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch {}

$root        = $PSScriptRoot
$py          = Join-Path $root 'ai-radio\.venv\Scripts\python.exe'
$backendDir  = Join-Path $root 'ai-radio\backend'
$qqDir       = Join-Path $root 'third_party\QQMusicApi'
$backendBat  = Join-Path $root '_run-backend.bat'
$qqBat       = Join-Path $root '_run-qqmusic.bat'
$backendPort = 8000
$qqPort      = 8080

function Test-Port {
    param([int]$Port)
    $client = New-Object System.Net.Sockets.TcpClient
    try {
        $iar = $client.BeginConnect('127.0.0.1', $Port, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(600) -and $client.Connected) {
            $client.EndConnect($iar)
            return $true
        }
        return $false
    } catch {
        return $false
    } finally {
        $client.Close()
    }
}

# 按当前实际路径生成一个服务启动 bat（独立 bat 比把长命令塞进 Start-Process 可靠）
function Write-ServiceBat {
    param([string]$Path, [string]$Title, [string]$WorkDir, [string]$Command)
    $lines = @(
        '@echo off',
        'chcp 65001 >nul',
        "title $Title",
        'set PYTHONUTF8=1',
        "cd /d $WorkDir",
        $Command
    )
    $text = ($lines -join "`r`n") + "`r`n"
    [System.IO.File]::WriteAllText($Path, $text, (New-Object System.Text.UTF8Encoding $false))
}

try { Clear-Host } catch {}
Write-Host ''
Write-Host '  ============================================' -ForegroundColor Magenta
Write-Host '            AI 音乐电台  ·  一键启动' -ForegroundColor Magenta
Write-Host '  ============================================' -ForegroundColor Magenta
Write-Host ''

# --- [1/4] 环境自检 ---
Write-Host '  [1/4] 检查运行环境...' -ForegroundColor Cyan
if (-not (Test-Path $py)) {
    Write-Host '  [X] 找不到 Python 虚拟环境（ai-radio\.venv）。' -ForegroundColor Red
    Write-Host '      项目可能不完整，或启动器被移走了位置。' -ForegroundColor Yellow
    Read-Host '  按回车键关闭'; exit 1
}
if (-not (Test-Path (Join-Path $backendDir 'main.py'))) {
    Write-Host '  [X] 找不到后端入口 ai-radio\backend\main.py。' -ForegroundColor Red
    Read-Host '  按回车键关闭'; exit 1
}
if (-not (Test-Path (Join-Path $qqDir 'web\run.py'))) {
    Write-Host '  [X] 找不到 QQ 音乐服务 third_party\QQMusicApi\web\run.py。' -ForegroundColor Red
    Read-Host '  按回车键关闭'; exit 1
}
Write-Host '        环境正常。' -ForegroundColor Green
Write-Host ''

# --- 生成两个服务的启动脚本（按当前路径，项目整体搬家也不会失效）---
Write-ServiceBat -Path $qqBat -Title "QQ音乐服务 :$qqPort  -  关闭此窗口=停止" -WorkDir $qqDir -Command "`"$py`" web\run.py"
Write-ServiceBat -Path $backendBat -Title "电台后端 :$backendPort  -  关闭此窗口=停止" -WorkDir $backendDir -Command "`"$py`" -m uvicorn main:app --host 0.0.0.0 --port $backendPort"

# --- [2/4] 启动 QQ 音乐服务 :8080 ---
Write-Host "  [2/4] 启动 QQ 音乐服务（端口 $qqPort）..." -ForegroundColor Cyan
if (Test-Port $qqPort) {
    Write-Host "        端口 $qqPort 已被占用，服务似乎已在运行，跳过。" -ForegroundColor Yellow
} else {
    Start-Process -FilePath $qqBat
    Write-Host '        已在新的黑窗口启动。' -ForegroundColor Green
}
Write-Host ''

# --- [3/4] 启动电台后端 :8000 ---
Write-Host "  [3/4] 启动电台后端（端口 $backendPort）..." -ForegroundColor Cyan
if (Test-Port $backendPort) {
    Write-Host "        端口 $backendPort 已被占用，后端似乎已在运行，跳过。" -ForegroundColor Yellow
} else {
    Start-Process -FilePath $backendBat
    Write-Host '        已在新的黑窗口启动。' -ForegroundColor Green
}
Write-Host ''

# --- [4/4] 等待后端就绪 ---
Write-Host '  [4/4] 等待电台后端就绪...' -ForegroundColor Cyan
$ready = $false
for ($i = 1; $i -le 40; $i++) {
    if (Test-Port $backendPort) { $ready = $true; break }
    Start-Sleep -Seconds 1
    if ($i % 5 -eq 0) { Write-Host "        ...已等待 $i 秒" -ForegroundColor DarkGray }
}
Write-Host ''

# --- 检测局域网 IP（VPN 环境优先用内网段地址）---
$ips = @()
try { $ips = @((Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue).IPAddress) } catch {}
$lan = $ips | Where-Object { $_ -like '192.168.*' } | Select-Object -First 1
if (-not $lan) { $lan = $ips | Where-Object { $_ -like '10.*' } | Select-Object -First 1 }
$primary = if ($lan) { "http://${lan}:$backendPort/" } else { "http://127.0.0.1:$backendPort/" }

# --- 结果汇报 ---
Write-Host '  ============================================' -ForegroundColor Magenta
if ($ready) {
    Write-Host '          电台已启动，正在打开浏览器' -ForegroundColor Green
    Write-Host '  ============================================' -ForegroundColor Magenta
    Start-Process $primary
} else {
    Write-Host '         后端等待超时（可能仍在启动中）' -ForegroundColor Yellow
    Write-Host '  ============================================' -ForegroundColor Magenta
    Write-Host ''
    Write-Host '  请看标题为「电台后端」的黑窗口：' -ForegroundColor Yellow
    Write-Host '    · 仍在滚动日志  → 还在启动，稍等后手动刷新浏览器；' -ForegroundColor Gray
    Write-Host '    · 出现红色报错  → 把报错截图发我，我来排查。' -ForegroundColor Gray
}
Write-Host ''
Write-Host '  浏览器访问地址（按顺序试，开 VPN 时第 1 个最稳）：' -ForegroundColor White
if ($lan) {
    Write-Host "    1)  $primary" -ForegroundColor Green
    Write-Host "    2)  http://127.0.0.1:$backendPort/" -ForegroundColor Gray
    Write-Host "    3)  http://localhost:$backendPort/" -ForegroundColor Gray
} else {
    Write-Host "    1)  http://127.0.0.1:$backendPort/" -ForegroundColor Green
    Write-Host "    2)  http://localhost:$backendPort/" -ForegroundColor Gray
}
Write-Host ''
Write-Host '  怎么关闭电台：' -ForegroundColor Yellow
Write-Host '    关掉弹出的两个黑窗口（标题「电台后端」「QQ音乐服务」）即可。' -ForegroundColor Gray
Write-Host '    本窗口现在可以随便关，不影响电台运行。' -ForegroundColor Gray
Write-Host ''
Write-Host '  首次使用提示：' -ForegroundColor Yellow
Write-Host '    · 网页首次打开会要求填 API（音乐 / 语音 / 大模型），按页面引导填。' -ForegroundColor Gray
Write-Host '    · 后端会在后台预热几首歌，刚打开就点播放可能稍慢，属正常。' -ForegroundColor Gray
Write-Host "    · QQ 音乐扫码登录页： http://127.0.0.1:$backendPort/qq-login.html" -ForegroundColor Gray
Write-Host ''
Read-Host '  按回车键关闭本窗口（电台继续在后台运行）'
exit 0
