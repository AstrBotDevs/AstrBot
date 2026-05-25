# 使用 AstrBot 桌面客户端部署

`AstrBot-desktop` 适合在本地电脑快速部署和使用 AstrBot，支持 Windows、macOS、Linux。

在多种部署方式中，桌面客户端更适合个人本地快速使用，不建议用于服务器长期运行或生产环境；如需生产部署，建议优先考虑 [Docker 部署](/deploy/astrbot/docker) 或 [Kubernetes 部署](/deploy/astrbot/kubernetes)。

相比命令行或容器方案，桌面客户端更偏向「开箱即用」体验，适合希望少折腾环境、直接开始使用的用户。

仓库地址：[AstrBotDevs/AstrBot-desktop](https://github.com/AstrBotDevs/AstrBot-desktop)

## 适合谁

- 想快速本地部署，优先使用图形化界面的用户。
- 不想手动维护 Docker / Python 运行环境的新手用户。
- 个人设备长期在线，主要用于个人或小团队日常使用的场景。

## 主要特点

- 多平台安装包，下载后可直接安装使用。
- 图形化界面配置，降低首次部署成本。
- 适合作为本地常驻客户端。

## 下载并安装

1. 打开 [AstrBot-desktop Releases](https://github.com/AstrBotDevs/AstrBot-desktop/releases)。
2. 下载与你系统对应的安装包（如 `.exe`、`.dmg`、`.rpm`、`.deb`）。
3. 安装完成后启动桌面客户端，按向导完成初始化。

## 与启动器部署的区别

- 桌面客户端：更偏向开箱即用的 GUI 体验。
- 启动器部署：更偏向自动化脚本拉起，适合希望保持传统部署流程的用户。
- 参考 [启动器部署](/deploy/astrbot/launcher)。
