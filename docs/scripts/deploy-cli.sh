#!/usr/bin/env bash
# deploy-cli.sh — AstrBot 一行命令部署脚本 (Linux / macOS / WSL)
# 用法: bash -c "$(curl -fsSL https://raw.githubusercontent.com/AstrBotDevs/AstrBot/master/docs/scripts/deploy-cli.sh)"
#
# 环境变量:
#   ASTRBOT_REPO  — 仓库地址 (默认: https://github.com/AstrBotDevs/AstrBot.git)
#   ASTRBOT_DIR   — 安装目录 (默认: AstrBot)

set -euo pipefail

# ── 颜色 ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ── 检测命令 ──
has() { command -v "$1" &>/dev/null; }

# ── 可配置变量 ──
REPO_URL="${ASTRBOT_REPO:-https://github.com/AstrBotDevs/AstrBot.git}"

# ── 1. 检测并安装依赖 ──
info "正在检测运行环境..."

if ! has git; then
    err "未检测到 git，请先安装: https://git-scm.com/downloads"
    exit 1
fi

if ! has curl; then
    err "未检测到 curl，请先安装: macOS 使用 'brew install curl'，Ubuntu/Debian 使用 'sudo apt install curl'"
    exit 1
fi

if has python3; then
    PY=python3
elif has python; then
    PY=python
else
    err "未检测到 Python (>=3.12)，请先安装: https://www.python.org/downloads/"
    exit 1
fi

# 使用 Python 自身进行版本比较，兼容 macOS BSD sort
if ! $PY -c 'import sys; exit(0 if sys.version_info >= (3, 12) else 1)'; then
    PY_VER=$($PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
    err "Python 版本过低: $PY_VER，需要 >= 3.12"
    exit 1
fi
PY_VER=$($PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
ok "Python $PY_VER"

# ── 安装 uv（如未安装） ──
if ! has uv; then
    info "正在安装 uv 包管理器..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
    if ! has uv; then
        err "uv 安装失败，请手动安装: https://docs.astral.sh/uv/getting-started/installation/"
        exit 1
    fi
fi
ok "uv $(uv --version)"

# ── 2. 定位项目目录 ──
# 优先检测当前目录是否已是项目根目录（支持本地运行场景）
if [ -f "main.py" ] && [ -d ".git" ]; then
    info "检测到已在项目目录中，跳过克隆"
else
    INSTALL_DIR="${ASTRBOT_DIR:-${1:-AstrBot}}"
    if [ -d "$INSTALL_DIR/.git" ]; then
        info "目录 $INSTALL_DIR 已存在，跳过克隆"
    elif [ -d "$INSTALL_DIR" ]; then
        err "目录 $INSTALL_DIR 已存在但不是 AstrBot 仓库，请指定其他目录或手动清理"
        exit 1
    else
        info "正在克隆 AstrBot 仓库到 $INSTALL_DIR ..."
        git clone --depth=1 "$REPO_URL" "$INSTALL_DIR"
    fi
    cd "$INSTALL_DIR"
fi

# ── 3. 安装依赖 ──
info "正在安装项目依赖 (uv sync)..."
uv sync

# ── 4. 启动 AstrBot ──
ok "依赖安装完成，正在启动 AstrBot..."
echo ""
info "管理面板默认地址: http://localhost:6185"
info "默认用户名/密码: astrbot / astrbot"
echo ""
uv run main.py
