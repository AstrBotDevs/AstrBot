#!/usr/bin/env bash
# deploy-cli.sh - Install astrbot with uv on Linux / macOS / WSL.

set -euo pipefail

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[1;33m'
  CYAN='\033[0;36m'
  NC='\033[0m'
else
  RED=''
  GREEN=''
  YELLOW=''
  CYAN=''
  NC=''
fi

info() { echo -e "${CYAN}[INFO]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
ok() { echo -e "${GREEN}[OK]${NC} $*"; }
err() { echo -e "${RED}[ERROR]${NC} $*" >&2; }

has() {
  command -v "$1" >/dev/null 2>&1
}

refresh_uv_path() {
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
}

install_uv() {
  info "uv was not found. Installing uv..."

  if has curl; then
    curl -fsSL https://astral.sh/uv/install.sh | sh
    refresh_uv_path
    return
  fi

  if has wget; then
    wget -qO- https://astral.sh/uv/install.sh | sh
    refresh_uv_path
    return
  fi

  err "curl or wget is required to install uv."
  exit 1
}

if has uv; then
  UV_BIN="uv"
else
  install_uv
  UV_BIN="uv"
fi

if ! has "$UV_BIN"; then
  err "uv was not found after installation."
  err "Please install uv manually: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi  

ok "$("$UV_BIN" --version)"
info "Installing AstrBot with Python 3.12..."
"$UV_BIN" tool install --python 3.12 astrbot
ok "AstrBot has been installed."
