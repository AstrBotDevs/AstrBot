# 脚本部署

AstrBot 提供 Linux、macOS、WSL 和 Windows 安装脚本。脚本会安装 `uv`、AstrBot 及 Python 3.12。

## Linux / macOS / WSL

交互式安装：

```bash
curl -fsSL https://docs.astrbot.app/install.sh | bash
```

无人值守安装：

```bash
curl -fsSL https://docs.astrbot.app/install.sh -o install.sh
bash install.sh --language zh-CN --download-source china --non-interactive
```

`--download-source` 可选 `china`、`official` 或 `custom`。省略语言参数时默认使用 English；未指定下载源时，中文使用中国大陆加速下载镜像源，英文和日文使用官方源。

## Windows

在 PowerShell 5.1 或 PowerShell 7+ 中运行：

交互式安装：

```powershell
irm https://docs.astrbot.app/install.ps1 | iex
```

无人值守安装：

```powershell
Invoke-WebRequest https://docs.astrbot.app/install.ps1 -OutFile install.ps1 -UseBasicParsing
.\install.ps1 -Language zh-CN -DownloadSource china -NonInteractive
```

`-DownloadSource` 可选 `china`、`official` 或 `custom`；省略语言参数时默认使用 English；未指定下载源时，中文使用中国大陆加速下载镜像源，英文和日文使用官方源。

选择中国大陆源时，脚本也会为 Python 3.12 配置 USTC 镜像，失败后使用官方 Python 源重试。已有的 Python 镜像环境变量或显式参数优先。

## 安装完成后

安装脚本会自动执行 `uv tool update-shell`。请根据你使用的终端重新加载环境：

```bash
# Bash
source ~/.bashrc
# Zsh
source ~/.zshrc
# Fish
source ~/.config/fish/config.fish
# PowerShell
. $PROFILE
```

重新加载后，手动运行：

```bash
astrbot init
astrbot run
```

> 通过脚本部署的 AstrBot 不支持在 WebUI 中升级。更新请执行 `uv tool upgrade astrbot --python 3.12`。
