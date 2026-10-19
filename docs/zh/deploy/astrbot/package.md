# 包管理器部署（uv）

使用 `uv` 可以快速安装并启动 AstrBot。

## 前置条件

如果尚未安装 `uv`，请先按照官方文档安装：<https://docs.astral.sh/uv/>

`uv` 支持 Linux、Windows、macOS。

## 注意事项

> [!WARNING]
> 通过 `uv` 部署的 AstrBot **不支持在 WebUI 中进行版本升级**。如需更新，请在命令行中执行 `uv tool upgrade astrbot --python 3.12`。

AstrBot 需要 Python 3.12 或更高版本。使用 `--python 3.12` 可以确保 `uv` 使用 Python 3.12 创建 tool 环境；如果启用了 Python 自动下载，`uv` 会在缺少 Python 3.12 时自动下载。

## 安装并启动

### Linux / macOS / WSL 安装向导

使用 **Bash 3.2 或更高版本**运行：

```bash
curl -fsSL https://docs.astrbot.app/install.sh | bash
```

向导同样先选择简体中文、English、日本語，再选择下载源；可选的中国大陆加速下载镜像源、官方源、自定义源与下方 Windows 向导一致。即使通过管道运行，菜单也会从终端读取输入；没有可用终端时跳过菜单，默认使用系统语言和官方源。

无人值守安装示例：

```bash
curl -fsSL https://docs.astrbot.app/install.sh -o install.sh
bash install.sh --language zh-CN --download-source china --non-interactive
```

自定义源使用 `--download-source custom --uv-download-base-url <HTTPS目录> --pypi-index-url <HTTPS索引>`。目录中需包含当前平台的 `uv-<平台>.tar.gz` 及同名 `.sha256` 文件；压缩包采用 uv 官方发布的目录结构。可通过 `--python-install-mirror <HTTPS地址>` 单独配置 Python 解释器镜像，也支持已有的 `UV_PYTHON_INSTALL_MIRROR`。

脚本自动匹配 macOS/Linux 架构，在 Linux 上优先使用静态 musl 构建；镜像不可用或校验失败时尝试备用镜像和官方安装器。需要 `curl` 或 `wget`；镜像安装还需要 `tar` 和 `sha256sum` 或 `shasum`。uv 安装目录会加入当前安装进程的 PATH，镜像安装后也会提示新终端需要使用的目录。

### Windows 安装向导

在 **Windows PowerShell 5.1 或 PowerShell 7+**中运行：

```powershell
irm https://docs.astrbot.app/install.ps1 | iex
```

向导首先提供简体中文、English、日本語三种显示语言，然后选择下载源：

- **中国大陆加速下载镜像源**：从 MirrorZ 收录的高校镜像下载 uv，并使用 `https://mirrors.cernet.edu.cn/pypi/web/simple/` 安装 AstrBot 及其 Python 包依赖。uv 镜像下载或 SHA256 校验失败时，依次尝试备用镜像和官方安装器。
- **官方源**：使用 uv 官方安装器和官方 PyPI。
- **自定义**：指定 uv ZIP 下载目录和 PyPI simple 索引。uv 目录需包含对应架构的 `uv-<架构>-pc-windows-msvc.zip` 及同名 `.sha256` 文件。

交互模式根据系统语言预选显示语言；中文界面默认选择中国大陆加速下载镜像源，英文和日文界面默认选择官方源，均可手动切换。

也可下载脚本后通过参数跳过交互：

```powershell
Invoke-WebRequest https://docs.astrbot.app/install.ps1 -OutFile install.ps1 -UseBasicParsing
.\install.ps1 -Language zh-CN -DownloadSource china -NonInteractive
```

`-Language` 支持 `zh-CN`、`en-US`、`ja-JP`；`-DownloadSource` 支持 `china`、`official`、`custom`。无人值守或输入被重定向时，不显示交互菜单；未指定语言时使用系统语言，未指定下载源时使用官方源。

自定义源示例（请替换为自己的 HTTPS 地址）：

```powershell
.\install.ps1 -Language zh-CN -DownloadSource custom -NonInteractive `
    -UvDownloadBaseUrl 'https://mirror.example.com/uv/release' `
    -PypiIndexUrl 'https://mirror.example.com/pypi/simple/'
```

PyPI 镜像不包含 Python 解释器。缺少 Python 3.12 时，解释器下载沿用 uv 的现有配置；可通过 `-PythonInstallMirror <HTTPS地址>` 单独指定兼容 uv 的 Python 下载镜像，或提前设置 `UV_PYTHON_INSTALL_MIRROR`。脚本不修改全局 pip 配置，参数指定的 Python 镜像只在本次安装期间生效。

### 手动安装并启动

```bash
uv tool install astrbot --python 3.12
astrbot init # 只需要在第一次部署时执行，后续启动不需要执行
astrbot run
```
