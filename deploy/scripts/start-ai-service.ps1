# AIWear 3.0 — ai-service 启动脚本
param(
    [int]$Port = 5001,
    [switch]$Debug = $false
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\..\.."
$AiServiceDir = "$ProjectRoot\apps\ai-service"

# 查找 Python
$PythonPaths = @(
    "$env:LOCALAPPDATA\Programs\Python\Python314\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "python"
)
$Python = $null
foreach ($p in $PythonPaths) {
    $check = Get-Command $p -ErrorAction SilentlyContinue
    if ($check) {
        $Python = $p
        break
    }
}
if (-not $Python) {
    Write-Error "Python not found. Tried: $PythonPaths"
    exit 1
}

Write-Host "Using Python: $Python" -ForegroundColor Cyan
Write-Host "ai-service dir: $AiServiceDir" -ForegroundColor Cyan

# 加载 .env
$EnvFile = "$ProjectRoot\.env"
if (Test-Path $EnvFile) {
    Write-Host "Loading .env from $EnvFile" -ForegroundColor Green
    Get-Content $EnvFile | ForEach-Object {
        if ($_ -match '^\s*([^#=]+)=(.*)') {
            $key = $Matches[1].Trim()
            $val = $Matches[2].Trim()
            [Environment]::SetEnvironmentVariable($key, $val, 'Process')
        }
    }
} else {
    Write-Warning ".env not found at $EnvFile — using existing env vars"
}

$env:FLASK_PORT = $Port
Set-Location $AiServiceDir
Write-Host "Starting ai-service on port $Port..." -ForegroundColor Yellow
& $Python server.py
