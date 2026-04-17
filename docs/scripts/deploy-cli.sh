#!/usr/bin/env bash
# deploy-cli.sh — AstrBot 一行命令部署脚本 (Linux / macOS / WSL)
# 用法: bash -c "$(curl -fsSL https://raw.githubusercontent.com/AstrBotDevs/AstrBot/master/docs/scripts/deploy-cli.sh)"

set -euo pipefail

# ── 颜色 ──
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

info()  { echo -e "${CYAN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
ok()    { echo -e "${GREEN}[OK]${NC} $*"; }
err()   { echo -e "${RED}[ERROR]${NC} $*"; }

# ── 检测命令 ──
has() { command -v "$1" &>/dev/null; }

# ── 1. 检测并安装依赖 ──
info "正在检测运行环境..."

if ! has git; then
    err "未检测到 git，请先安装: https://git-scm.com/downloads"
    exit 1
fi

if has python3; then
    PY=python3
elif has python; then
    PY=python
else
    err "未检测到 Python (>=3.10)，请先安装: https://www.python.org/downloads/"
    exit 1
fi

PY_VER=$($PY -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
if [ "$(printf '%s\n' "3.10" "$PY_VER" | sort -V | head -n1)" != "3.10" ]; then
    err "Python 版本过低: $PY_VER，需要 >= 3.10"
    exit 1
fi
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

# ── 2. 克隆仓库 ──
INSTALL_DIR="${1:-AstrBot}"
if [ ! -d "$INSTALL_DIR/.git" ]; then
    info "正在克隆 AstrBot 仓库到 $INSTALL_DIR ..."
    git clone --depth=1 https://github.com/AstrBotDevs/AstrBot.git "$INSTALL_DIR"
else
    info "目录 $INSTALL_DIR 已存在，跳过克隆"
fi
cd "$INSTALL_DIR"

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
