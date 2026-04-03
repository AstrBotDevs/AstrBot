# 包管理器部署（uv）

使用 `uv` 可以快速安装并启动 AstrBot。

## 前置条件

如果尚未安装 `uv`，请先按照官方文档安装：<https://docs.astral.sh/uv/>

`uv` 支持 Linux、Windows、macOS。

## 注意事项

> [!WARNING]
> 通过 `uv` 部署的 AstrBot **不支持在 WebUI 中进行版本升级**。如需更新，请在命令行中执行 `uv tool upgrade astrbot`。

## 安装并启动

```bash
uv tool install astrbot
astrbot init # 只需要在第一次部署时执行，后续启动不需要执行
astrbot run
```
