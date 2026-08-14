$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $root "backend"
$frontendDir = Join-Path $root "frontend"
$python = Join-Path $backendDir ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "[启动失败] 未找到虚拟环境 python: $python" -ForegroundColor Red
    exit 1
}

Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  小说创作智能体 - 一键启动 (终端日志模式)"
Write-Host "============================================" -ForegroundColor Cyan

function Start-ChildLog {
    param([string]$Name, [scriptblock]$Block)
    Start-Job -Name $Name -ScriptBlock $Block
}

# 后端：fastapi @ 8000
$backendJob = Start-ChildLog -Name "backend" -Block {
    param($dir, $py)
    Set-Location $dir
    & $py dev.py
} -ArgumentList $backendDir, $python

# 前端：vite @ 5173
$frontendJob = Start-ChildLog -Name "frontend" -Block {
    param($dir)
    Set-Location $dir
    npm run dev
} -ArgumentList $frontendDir

Write-Host ""
Write-Host "[提示] 两个服务正在并行启动，日志实时输出如下。按 Ctrl+C 可同时停止两者并退出。" -ForegroundColor Yellow
Write-Host "      后端 http://127.0.0.1:8000 | 前端 http://localhost:5173"
Write-Host ""

try {
    # 轮询接收两个 job 的输出，实时打印
    while ($true) {
        Start-Sleep -Milliseconds 300
        $jobs = Get-Job -State Running, Completed
        foreach ($j in $jobs) {
            $tag = "[$($j.Name)] "
            Receive-Job -Job $j | ForEach-Object { Write-Host "$tag$_" }
        }
        # 任一方退出即整体终止
        $done = @(Get-Job -State Completed, Failed)
        if ($done.Count -gt 0) {
            Write-Host "[提示] 有服务已退出，正在停止另一端..." -ForegroundColor Yellow
            break
        }
    }
}
finally {
    Stop-Job -Job (Get-Job) -ErrorAction SilentlyContinue
    Remove-Job -Job (Get-Job) -Force -ErrorAction SilentlyContinue
    Write-Host "[提示] 已停止全部服务。按任意键关闭窗口。" -ForegroundColor Cyan
    $null = Read-Host
}
