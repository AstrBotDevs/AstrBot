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

## 检查更新

桌面客户端进入主界面后会自动检查客户端新版本。发现更新时，Bot 模式和聊天模式的顶部栏都会显示「AstrBot 有新版本！」文字提示。右上角的功能菜单也会显示提示圆点，菜单内的「更新」入口会显示标记。

点击顶部的「AstrBot 有新版本！」文字，即可打开桌面客户端更新弹窗。也可以点击右上角功能菜单中的「更新」，手动检查版本并确认安装。自动检查不会直接下载或安装更新；检查失败时，也可以通过此入口重试。

## 与启动器部署的区别

- 桌面客户端：更偏向开箱即用的 GUI 体验。
- 启动器部署：更偏向自动化脚本拉起，适合希望保持传统部署流程的用户。
- 参考 [启动器部署](/deploy/astrbot/launcher)。
