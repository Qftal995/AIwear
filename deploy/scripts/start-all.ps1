# AIWear 3.0 — 全栈启动脚本
# 用法:
#   .\start-all.ps1              # Docker Compose 启动全部服务
#   .\start-all.ps1 -Dev         # 开发模式（Docker 中间件 + 本地运行 Python/Java/前端）
#   .\start-all.ps1 -CheckHealth # 仅健康检查

param(
    [switch]$Dev,
    [switch]$CheckHealth
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\..\.."
$ComposeFile = "$ProjectRoot\deploy\docker-compose-mid.yml"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  AIWear 3.0 — 全栈启动" -ForegroundColor Cyan
Write-Host "  Project: $ProjectRoot" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# ---- 健康检查模式 ----
if ($CheckHealth) {
    Write-Host "[健康检查]" -ForegroundColor Yellow
    $Endpoints = @(
        @{Name="ai-service /api/health"; Url="http://localhost:5001/api/health"},
        @{Name="Java /api/health"; Url="http://localhost:8081/api/health"},
        @{Name="nginx /"; Url="http://localhost/"},
        @{Name="前端 Vite"; Url="http://localhost:5173/"}
    )
    foreach ($ep in $Endpoints) {
        try {
            $res = Invoke-WebRequest -Uri $ep.Url -TimeoutSec 3 -UseBasicParsing
            Write-Host "  [OK] $($ep.Name)" -ForegroundColor Green
        } catch {
            Write-Host "  [DOWN] $($ep.Name) — $($_.Exception.Message)" -ForegroundColor Red
        }
    }
    exit 0
}

# ---- 检查 .env ----
$EnvFile = "$ProjectRoot\.env"
if (-not (Test-Path $EnvFile)) {
    Write-Warning ".env 文件不存在，从 .env.example 复制..."
    if (Test-Path "$ProjectRoot\.env.example") {
        Copy-Item "$ProjectRoot\.env.example" $EnvFile
        Write-Host "已创建 $EnvFile，请编辑填入真实 API Key 后重新运行。" -ForegroundColor Yellow
        exit 1
    } else {
        Write-Error ".env.example 也不存在，无法继续"
        exit 1
    }
}

# ---- Docker Compose 模式 ----
Write-Host "[Docker Compose] 启动中间件 + AI 服务..." -ForegroundColor Yellow
docker compose -p bite_wear -f $ComposeFile up -d
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker Compose 启动失败"
    exit 1
}

Write-Host ""
Write-Host "等待服务就绪..." -ForegroundColor Yellow
Start-Sleep -Seconds 5

# 健康检查
docker compose -p bite_wear -f $ComposeFile ps
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  服务启动完成！" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  nginx:           http://localhost" -ForegroundColor White
Write-Host "  ai-service:      http://localhost:5001" -ForegroundColor White
Write-Host "  rabbitmq 管理:    http://localhost:15672 (aiwear/aiwear@mq)" -ForegroundColor White
Write-Host "  mysql:           localhost:3307 (bite/bite@123)" -ForegroundColor White
Write-Host "  redis:           localhost:6379" -ForegroundColor White
Write-Host ""
Write-Host "  查看日志: docker compose -p bite_wear -f $ComposeFile logs -f" -ForegroundColor Gray
Write-Host "  停止服务: docker compose -p bite_wear -f $ComposeFile down" -ForegroundColor Gray
Write-Host ""

if ($Dev) {
    Write-Host "[开发模式] 额外启动本地服务:" -ForegroundColor Yellow
    Write-Host "  前端:  .\deploy\scripts\start-web.ps1" -ForegroundColor White
    Write-Host "  Java:  .\deploy\scripts\start-java.ps1" -ForegroundColor White
}
