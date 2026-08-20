# Linux 开发环境

这是 Linux 下受支持的源码开发流程。项目使用 Python 3.14.6、`uv`、Node.js
26 和 pnpm；以下命令不依赖 PowerShell。

## 前置工具

先使用发行版包管理器安装基础工具，再用发行版推荐的方式安装 Python 3.14.6、`uv`
与 Node.js 26。CI 使用 Node.js 26.5.0；`make doctor` 接受兼容的 Node 26
版本。

Ubuntu/Debian：

```bash
sudo apt update
sudo apt install git make curl shellcheck shfmt hadolint
```

Fedora：

```bash
sudo dnf install git make curl ShellCheck shfmt hadolint
```

Arch Linux：

```bash
sudo pacman -S git make curl shellcheck shfmt hadolint
```

若发行版没有打包 `hadolint`，请使用其官方发布的二进制文件。除非需要调试容器部署，
Docker 本身不是开发前置条件。

## 首次安装

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
make doctor
make bootstrap
```

`make bootstrap` 会按照锁文件创建 Python 环境、安装根目录格式化工具和 Dashboard
依赖；它不会安装系统软件包，应先解决 `make doctor` 报出的缺失工具。

`make format` 在修改文件前也会执行同样的预检。若提示找不到 Node.js，请在当前
shell 中安装或启用 Node 26，确认 `node --version` 可用后再执行。根目录
`node_modules/.bin` 中的本地工具使用 `/usr/bin/env node` 启动，因此 `node`
必须在 `PATH` 中。

## 日常开发

```bash
make dev             # 后端 6185，Vite Dashboard 3000
make status          # 检查两个进程
make stop            # 停止两个进程组
make check           # 严格执行 Linux/macOS 源码检查
make test            # 执行全量 pytest
make test-blocking   # 执行 blocking pytest
make pr-test-full    # lint、测试、启动 smoke test 与 Dashboard 构建
```

后端日志为 `backend_run.log`、`backend_run.err.log`；Dashboard 日志为
`frontend_run.log`、`frontend_run.err.log`。PID 文件放在 `.make/`。
`make clean` 会停止开发进程并清理生成的本地状态，但不会删除 `data/config` 与
`data/plugins`。

`make check-all-platforms` 会额外检查 PowerShell 脚本。只有修改 PS 脚本时才需要；
该目标要求安装 `pwsh` 和 PSScriptAnalyzer，CI 会单独验证它们。

## NapCat 事件模型生成

NapCat 生成流程在 Linux 与 Windows 都使用 Python 原生入口。它需要 `git`、`pnpm`、
`uv`，并需要联网克隆 NapCat 仓库和下载 schema 生成器。

```bash
make napcat-codegen
make napcat-test
```

中间文件位于 `.tmp/napcat-schema`；受版本控制的生成结果为
`astrbot/core/platform/sources/napcat/generated/ob11_events.py`。
