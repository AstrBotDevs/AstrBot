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

```bash
uv tool install astrbot --python 3.12
astrbot init # 只需要在第一次部署时执行，后续启动不需要执行
astrbot run
```

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
