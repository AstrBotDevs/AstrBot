# deploy-cli.ps1 — AstrBot 一行命令部署脚本 (Windows PowerShell 原生)
# 用法: irm https://raw.githubusercontent.com/AstrBotDevs/AstrBot/master/docs/scripts/deploy-cli.ps1 | iex
#
# 环境变量:
#   $env:ASTRBOT_REPO  — 仓库地址 (默认: https://github.com/AstrBotDevs/AstrBot.git)
#   $env:ASTRBOT_DIR   — 安装目录 (默认: AstrBot)

#Requires -Version 7.0

$ErrorActionPreference = 'Stop'

# ── 颜色 ──
function Info  { Write-Host "[INFO]    $args" -ForegroundColor Cyan }
function Warn  { Write-Host "[WARN]    $args" -ForegroundColor Yellow }
function Ok     { Write-Host "[OK]      $args" -ForegroundColor Green }
function Err    { Write-Host "[ERROR]   $args" -ForegroundColor Red }

# ── 检测命令 ──
function Test-Command {
    param([string]$Name)
    $null = Get-Command $Name -ErrorAction SilentlyContinue
    return $?
}

# ── 可配置变量 ─-
$REPO_URL = if ($env:ASTRBOT_REPO) { $env:ASTRBOT_REPO } else { "https://github.com/AstrBotDevs/AstrBot.git" }

# ── 1. 检测并安装依赖 ──
Info "正在检测运行环境..."

if (-not (Test-Command "git")) {
    Err "未检测到 git，请先安装: https://git-scm.com/downloads"
    exit 1
}
Ok "git 已安装"

if (-not (Test-Command "curl")) {
    Err "未检测到 curl，请先安装或使用 PowerShell 7 内置 Invoke-WebRequest"
    exit 1
}
Ok "curl 已安装"

# 检测 Python
$PythonCmd = $null
foreach ($cmd in @("python3", "python")) {
    if (Test-Command $cmd) {
        $PythonCmd = $cmd
        break
    }
}

if (-not $PythonCmd) {
    Err "未检测到 Python (>=3.12)，请先安装: https://www.python.org/downloads/"
    exit 1
}

# 检查 Python 版本
$pyVersion = & $PythonCmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ([int]($pyVersion.Split('.')[0]) -lt 3 -or ($pyVersion.Split('.')[0] -eq '3' -and [int]($pyVersion.Split('.')[1]) -lt 12)) {
    Err "Python 版本过低: $pyVersion，需要 >= 3.12"
    exit 1
}
Ok "Python $pyVersion"

# ── 安装 uv（如未安装） ──
if (-not (Test-Command "uv")) {
    Info "正在安装 uv 包管理器..."
    # 使用 PowerShell 安装 uv
    $tempScript = [System.IO.Path]::GetTempFileName() + ".ps1"
    try {
        Invoke-WebRequest -Uri "https://astral.sh/uv/install.ps1" -OutFile $tempScript -UseBasicParsing
        . $tempScript
    } catch {
        Err "uv 安装失败，请手动安装: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    } finally {
        Remove-Item $tempScript -ErrorAction SilentlyContinue
    }
}

# 刷新 PATH 并检查 uv
$uvVersion = (Get-Command uv -ErrorAction SilentlyContinue).Version.ToString()
if (-not $uvVersion) {
    # 尝试从默认安装位置检查
    $uvPath = "$env:LOCALAPPDATA\uv\uv.exe"
    if (Test-Path $uvPath) {
        $uvVersion = & $uvPath --version
    }
}

if ($uvVersion) {
    Ok "uv $uvVersion"
} else {
    Err "uv 安装失败，请手动安装: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
}

# ── 2. 定位项目目录 ──
# 优先检测当前目录是否已是项目根目录（支持本地运行场景）
if ((Test-Path "main.py") -and (Test-Path ".git")) {
    Info "检测到已在项目目录中，跳过克隆"
    $ProjectDir = $PWD.Path
} else {
    $INSTALL_DIR = if ($env:ASTRBOT_DIR) { $env:ASTRBOT_DIR } else { "AstrBot" }
    if (Test-Path "$INSTALL_DIR\.git") {
        Info "目录 $INSTALL_DIR 已存在，跳过克隆"
        $ProjectDir = (Resolve-Path $INSTALL_DIR).Path
    } elseif (Test-Path $INSTALL_DIR) {
        Err "目录 $INSTALL_DIR 已存在但不是 AstrBot 仓库，请指定其他目录或手动清理"
        exit 1
    } else {
        Info "正在克隆 AstrBot 仓库到 $INSTALL_DIR ..."
        git clone --depth=1 $REPO_URL $INSTALL_DIR
        $ProjectDir = (Resolve-Path $INSTALL_DIR).Path
    }
    Set-Location $ProjectDir
}

# ── 3. 安装依赖 ──
Info "正在安装项目依赖 (uv sync)..."
uv sync

# ── 4. 启动 AstrBot ──
Ok "依赖安装完成，正在启动 AstrBot..."
Write-Host ""
Info "管理面板默认地址: http://localhost:6185"
Info "默认用户名/密码: astrbot / astrbot"
Write-Host ""
uv run main.py