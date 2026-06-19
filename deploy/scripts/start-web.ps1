# AIWear 3.0 — 前端启动脚本
param(
    [int]$Port = 5173
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\..\.."
$WebDir = "$ProjectRoot\apps\web"

Write-Host "Frontend dir: $WebDir" -ForegroundColor Cyan

Set-Location $WebDir

# 检查 node_modules
if (-not (Test-Path "$WebDir\node_modules")) {
    Write-Host "node_modules not found, running npm install..." -ForegroundColor Yellow
    npm install
    if ($LASTEXITCODE -ne 0) {
        Write-Error "npm install failed"
        exit 1
    }
}

Write-Host "Starting Vite dev server on port $Port..." -ForegroundColor Yellow
npm run dev -- --port $Port --host
