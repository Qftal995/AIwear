# AIWear 3.0 — Java 后端启动脚本
param(
    [string]$Profile = "dev"
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path "$ScriptDir\..\.."
$JavaDir = "$ProjectRoot\apps\api-java"

Write-Host "Java backend dir: $JavaDir" -ForegroundColor Cyan

# 查找 Maven
$MvnCmd = $null
if (Get-Command mvn -ErrorAction SilentlyContinue) {
    $MvnCmd = "mvn"
} elseif (Test-Path "$JavaDir\mvnw.cmd") {
    $MvnCmd = "$JavaDir\mvnw.cmd"
} elseif (Test-Path "$JavaDir\mvnw") {
    $MvnCmd = "$JavaDir\mvnw"
}

if ($MvnCmd) {
    Write-Host "Using Maven: $MvnCmd" -ForegroundColor Green
    Set-Location $JavaDir
    Write-Host "Starting Spring Boot with profile=$Profile..." -ForegroundColor Yellow
    & $MvnCmd spring-boot:run "-Dspring-boot.run.profiles=$Profile"
} else {
    Write-Host "Maven not found on PATH and no mvnw wrapper detected." -ForegroundColor Red
    Write-Host ""
    Write-Host "启动 Java 后端需要以下任一种方式：" -ForegroundColor Yellow
    Write-Host "  1. 安装 Maven: winget install Apache.Maven.3" -ForegroundColor White
    Write-Host "  2. IntelliJ IDEA: 打开 $JavaDir 目录，运行 Application.java" -ForegroundColor White
    Write-Host "  3. 生成 Maven wrapper: 在已安装 Maven 的机器上运行 'mvn wrapper:wrapper'" -ForegroundColor White
    Write-Host ""
    Write-Host "IntelliJ IDEA 运行配置：" -ForegroundColor Cyan
    Write-Host "  Main class: com.bitejiuyeke.BiteWearApplication" -ForegroundColor White
    Write-Host "  Working dir: $JavaDir" -ForegroundColor White
    Write-Host "  Profile: $Profile" -ForegroundColor White
    exit 1
}
