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
