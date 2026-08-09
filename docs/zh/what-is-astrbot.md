---
outline: deep
---

# 👋 关于 AstrBot

## 简介

AstrBot 是一个开源的一站式 Agentic 个人和群聊助手，可在 QQ、Telegram、企业微信、飞书、钉钉、Slack 等数十款主流即时通讯软件上部署，此外还内置类似 OpenWebUI 的轻量化 ChatUI，为个人、开发者和团队打造可靠、可扩展的对话式智能基础设施。无论是个人 AI 伙伴、智能客服、自动化助手，还是企业知识库，AstrBot 都能在你的即时通讯软件平台的工作流中快速构建 AI 应用。

本文档描述的是当前 fork 分支的真实行为。这个仓库会选择性同步上游，但一旦与上游存在差异，以当前仓库中的代码、配置、API 和部署文件为准。

当前分支使用 Python 3.14+，Dashboard 后端已经迁移到 FastAPI，并通过显式运行时服务、生命周期管理器、事件总线和有序 Pipeline 组织平台、Provider、插件与 Agent。文本转图片使用本地 Playwright Chromium，不再依赖旧的远程文转图服务。

## 文档概览

本文档分为以下几个部分：

- **部署**。我们提供多种方式帮助您把 AstrBot 快速部署到云服务器或本地机器上。
- **消息平台接入**。我们提供 18+ 主流即时通讯软件的接入指南，帮助您把 AstrBot 连接到您喜欢的 IM 平台。
- **AI 模型提供商接入**。我们支持各种 AI 模型提供商的接入，您可以选择使用 AstrBot 内置的 Agent 执行器，也可以接入第三方的 Agent 执行器服务，例如 Dify、Coze、阿里云百炼应用、DeerFlow 等，或者自己开发 Agent 执行器。
- **使用指南**。我们提供了丰富的使用指南，帮助您充分利用 AstrBot 的各种功能，例如插件、工具调用、知识库、MCP、Skills、Agent 沙箱环境等。

## 快速开始

- 部署 AstrBot：从[源码部署](/deploy/astrbot/cli)开始，或使用当前仓库本地构建的 [Docker](/deploy/astrbot/docker) 方案。
- 连接 IM 平台：按照说明将 AstrBot 连接到您喜欢的 IM 平台，如 Discord、Telegram、Slack 等。
- 配置 AI 模型：AstrBot 支持各种 AI 模型。请参阅 [连接模型服务](/providers/start)

## 发行边界

当前 fork 不发布独立 PyPI 包、GitHub Release 资产、桌面端安装包或容器镜像。以下安装源属于 AstrBot 上游或第三方，并不是当前分支的构建产物：

- `uv tool install astrbot` 与 `uv tool upgrade astrbot`；
- 以 AstrBot 命名的 AUR 包；
- `soulter/astrbot` 等上游镜像；
- 上游 Release 中的 Dashboard 静态资源；启动入口不会下载或使用这些资源。

源码部署应直接使用当前 checkout；容器部署应通过 `compose.yml` 或 `compose-with-napcat.yml` 构建仓库根目录的 `Dockerfile`。源码部署的 WebUI 默认只监听 `127.0.0.1:6185`；Compose 会显式将容器内监听地址设为 `0.0.0.0`，同时让宿主机端口保持环回绑定。远程发布仍需设置 `ASTRBOT_BIND_ADDRESS`，并配置防火墙和反向代理保护。

## 它是如何实现的？

平台适配器把入站消息统一为 `AstrMessageEvent`，`EventBus` 根据配置文件选择 Pipeline，依次执行唤醒、白名单、会话状态、限流、安全、预处理、插件/Agent、结果装饰和发送阶段。完整的启动流程、所有权边界和修改位置请参阅[项目架构](/dev/architecture)。

## 说明

- AstrBot 受 [AGPL-3.0-or-later](https://github.com/Xero-Team/AstrBot/blob/master/LICENSE) 开源许可证保护。通过网络向用户提供修改版服务时，请确认自己履行了许可证义务。
- 使用此项目前，请务必阅读本项目的最终用户许可协议（EULA）：[最终用户许可协议](https://github.com/Xero-Team/AstrBot/blob/master/EULA.md)。如果您不同意该协议的任何条款，请勿使用本项目。
