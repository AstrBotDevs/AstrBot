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

`--download-source` 可选 `china`、`official` 或 `custom`。省略参数时使用系统语言和官方源。

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

`-DownloadSource` 可选 `china`、`official` 或 `custom`；省略参数时使用系统语言和官方源。

## 启动 AstrBot

首次使用时初始化目录，之后直接启动：

```bash
astrbot init
astrbot run
```

> 通过脚本部署的 AstrBot 不支持在 WebUI 中升级。更新请执行 `uv tool upgrade astrbot --python 3.12`。
