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

## 安装为系统服务

初始化完成后，可以安装用户级服务，让 AstrBot 随用户会话自动启动：

```bash
astrbot service install --now
```

该命令会自动使用当前 `PATH` 中的 `astrbot` 可执行文件（通常由 `uv tool install` 生成），并将当前目录作为 AstrBot 工作目录。不同系统会使用对应的用户级服务机制：

- Linux：`systemd --user`
- macOS：`LaunchAgent`
- Windows：任务计划程序

如果需要指定 AstrBot 工作目录或可执行文件路径，可以使用：

```bash
astrbot service install --workdir /path/to/astrbot-root --executable /path/to/astrbot --now
```

查看服务状态和 WebUI 健康状态：

```bash
astrbot service status
```

状态输出会包含服务管理器状态、AstrBot 工作目录、Dashboard 端口、WebUI URL、WebUI 是否可访问，以及整体健康状态。

也可以使用以下命令管理服务生命周期：

```bash
astrbot service start
astrbot service stop
astrbot service restart
astrbot service uninstall
```

查看服务日志：

```bash
astrbot service logs
astrbot service logs -f
```

macOS 和 Windows 下默认只显示标准输出日志；如需同时查看 stderr：

```bash
astrbot service logs --include-stderr
```

如果需要查看 AstrBot 应用日志文件 `data/logs/astrbot.log`，先启用应用日志文件并重启服务：

```bash
astrbot service logs enable
astrbot service restart
astrbot service logs --source app
```

查看或关闭应用日志文件：

```bash
astrbot service logs status
astrbot service logs disable
```
