![AstrBot-Logo-Simplified](https://github.com/user-attachments/assets/36fb04e4-cc75-4454-bd8b-049d11aa86f9)

<div align="center">

<a href="./README.md">English</a> ｜
<a href="./README_zh.md">简体中文</a>

<div>
<img src="https://img.shields.io/badge/python-3.14+-blue.svg" alt="python">
<img src="https://img.shields.io/badge/deployment-source%20build-76bad9" alt="source build">
</div>

<br>

<a href="./docs/zh/index.md">文档</a> ｜
<a href="https://github.com/Xero-Team/AstrBot/issues">问题提交</a> ｜
<a href="./docs/zh/dev/development.md">开发指南</a>

</div>

AstrBot 是一个开源的一站式 Agentic 个人和群聊助手，可在 QQ、Telegram、企业微信、飞书、钉钉、Slack 等数十款主流即时通讯软件上部署，此外还内置类似 OpenWebUI 的轻量化 ChatUI，为个人、开发者和团队打造可靠、可扩展的对话式智能基础设施。无论是个人 AI 伙伴、智能客服、自动化助手，还是本地知识库检索，都能在即时通讯软件的工作流中构建 AI 应用。知识库当前是单机 SQLite + FAISS，不是托管式企业检索服务。

这个仓库是 AstrBot 的现代化 fork。这里记录的命令、部署文件和兼容性边界均以当前分支为准：Python 3.14+、后端使用 `uv`、前端使用 `pnpm`，并且不再为旧兼容路径背书。

![landingpage](https://github.com/user-attachments/assets/45fc5699-cddf-4e21-af35-13040706f6c0)

## 主要功能

1. 💯 免费 & 开源。
2. ✨ AI 大模型对话，多模态，Agent，MCP，Skills，知识库，人格设定，自动压缩对话。
3. 🤖 支持接入 Dify、阿里云百炼、Coze 等智能体平台。
4. 🌐 多平台，支持 QQ、企业微信、飞书、钉钉、微信公众号、Telegram、Slack 以及[更多](#支持的消息平台)。
5. 📦 插件扩展，提供社区插件市场和沙箱化的 Dashboard Extension Protocol。
6. 🛡️ [Agent Sandbox](docs/zh/use/astrbot-agent-sandbox.md) 隔离化环境，安全地执行代码、调用 Shell、复用会话级资源。
7. 💻 WebUI 支持。
8. 🌈 Web ChatUI 支持，ChatUI 内置代理沙盒、网页搜索等。
9. 🌐 WebUI 双语：简体中文和英文。

<br>

<table align="center">
  <tr align="center">
    <th>💙 角色扮演 & 情感陪伴</th>
    <th>✨ 主动式 Agent</th>
    <th>🚀 通用 Agentic 能力</th>
    <th>🧩 社区插件</th>
  </tr>
  <tr>
    <td align="center"><p align="center"><img width="984" height="1746" alt="99b587c5d35eea09d84f33e6cf6cfd4f" src="https://github.com/user-attachments/assets/89196061-3290-458d-b51f-afa178049f84" /></p></td>
    <td align="center"><p align="center"><img width="976" height="1612" alt="c449acd838c41d0915cc08a3824025b1" src="https://github.com/user-attachments/assets/f75368b4-e022-41dc-a9e0-131c3e73e32e" /></p></td>
    <td align="center"><p align="center"><img width="974" height="1732" alt="image" src="https://github.com/user-attachments/assets/e22a3968-87d7-4708-a7cd-e7f198c7c32e" /></p></td>
    <td align="center"><p align="center"><img width="976" height="1734" alt="image" src="https://github.com/user-attachments/assets/0952b395-6b4a-432a-8a50-c294b7f89750" /></p></td>
  </tr>
</table>

## 快速开始

### 从源码运行

当前 fork 不发布 PyPI 包或预构建 Release。PyPI 上名为 `astrbot` 的包、AUR 包和上游容器镜像都不代表本分支。请从当前仓库 checkout 运行：

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
uv sync --locked
cd dashboard
pnpm install --frozen-lockfile
pnpm build
cd ..
uv run python scripts/sync_dashboard_dist.py
uv run main.py
```

请先安装 [uv](https://docs.astral.sh/uv/)、Node.js 26.5.0 和 pnpm 11.21.0。仓库固定使用 Python 3.14.6 和对应的 pnpm 版本。首次启动后访问 `http://localhost:6185`，默认用户名为 `astrbot`，随机初始密码会打印在日志中。

如果启用本地文转图或插件 HTML 渲染，还需执行一次 `uv run astrbot install-browser`。更新、远程访问和安全配置请参阅[从源码部署 AstrBot](docs/zh/deploy/astrbot/cli.md)。

### Docker 部署

当前 fork 不提供官方预构建镜像，请从当前 checkout 本地构建。Compose 会将容器内 Dashboard 监听在 `0.0.0.0`，宿主机端口默认只绑定 `127.0.0.1`；需要远程访问时，请显式设置 `ASTRBOT_BIND_ADDRESS=0.0.0.0`，并配置防火墙或 HTTPS 反向代理。

然后构建并启动：

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
docker compose up -d --build
docker compose logs -f astrbot
```

Compose 默认构建完整运行时。如果不需要浏览器、文档转换、媒体处理、OCR、Node.js
或 Docker CLI，可以通过 `ASTRBOT_FEATURES` 缩小镜像；它是构建参数，修改后需要重新构建：

`minimal` 仍然可以正常使用 WebUI：Dashboard 已在镜像构建阶段编译成静态文件，运行时由
Python/FastAPI 提供；只有 Node.js MCP 启动器等集成才需要加入 `node`。

```bash
# 一次性使用最小运行时
ASTRBOT_FEATURES=minimal docker compose up -d --build

# 只启用浏览器、Node.js 和 Docker CLI
ASTRBOT_FEATURES=browser,node,docker docker compose up -d --build
```

如需固定配置，可在仓库根目录 `.env` 中写入，例如
`ASTRBOT_FEATURES=browser,media,fonts`。NapCat 组合使用同样的参数：

```bash
ASTRBOT_FEATURES=browser,node,docker \
  docker compose -f compose-with-napcat.yml up -d --build
```

如果希望一并拉起 AstrBot 和 NapCat：

```bash
docker compose -f compose-with-napcat.yml up -d --build
```

绑定到 `0.0.0.0` 是显式扩大暴露面的选择，请同时限制防火墙来源，并优先使用 HTTPS 反向代理。更多细节请参考[使用 Docker 部署 AstrBot](docs/zh/deploy/astrbot/docker.md)。

## 支持的消息平台

将 AstrBot 连接到你常用的聊天平台。

| 内置接入                      | 适配器类型                             |
| ----------------------------- | -------------------------------------- |
| QQ 官方机器人                 | `qq_official`、`qq_official_webhook`   |
| OneBot v11                    | `aiocqhttp`                            |
| NapCat                        | `napcat`                               |
| Telegram                      | `telegram`                             |
| 企业微信 / 企业微信智能机器人 | `wecom`、`wecom_ai_bot`                |
| 微信公众号 / 个人微信         | `weixin_official_account`、`weixin_oc` |
| 飞书 / 钉钉                   | `lark`、`dingtalk`                     |
| Slack / Discord               | `slack`、`discord`                     |
| LINE / Satori / KOOK          | `line`、`satori`、`kook`               |
| Misskey / Mattermost          | `misskey`、`mattermost`                |
| 内置浏览器聊天                | `webchat`                              |

本表来自当前代码中的内置适配器发现表。插件还可以注册其他适配器；运行中 WebUI 的 **机器人 → 创建机器人** 列表才是最终依据。详见[接入消息平台](docs/zh/platform/start.md)。

## 支持的模型提供商

| 服务类型           | 当前内置范围                                                                                                              |
| ------------------ | ------------------------------------------------------------------------------------------------------------------------- |
| 对话模型           | OpenAI Chat Completions/Responses 与兼容接口、Anthropic、Gemini、智谱、小米、MiniMax、Kimi Code、xAI、Groq、OpenRouter 等 |
| 本地模型           | 通过受支持接口接入 Ollama、LM Studio                                                                                      |
| Agent 执行器       | 内置本地 Agent，以及 Dify、Coze、阿里云百炼应用、DeerFlow                                                                 |
| 语音               | Whisper、SenseVoice、小米 MiMo、Xinference、OpenAI/Gemini/Edge/Azure/ElevenLabs TTS、GPT-SoVITS、FishAudio、DashScope 等  |
| Embedding / Rerank | OpenAI、Gemini、NVIDIA、Ollama、vLLM、Xinference、阿里云百炼                                                              |

Provider 模板来自代码注册表，后续版本可能变化；请以运行中 WebUI 的 **提供商 → 新增 Provider 来源** 为准。详见[模型 Provider](docs/zh/providers/start.md)。

## ❤️ 贡献

欢迎任何 Issues/Pull Requests！只需要将你的更改提交到此项目 ：)

### 如何贡献

你可以通过查看问题或帮助审核 PR（拉取请求）来贡献。任何问题或 PR 都欢迎参与，以促进社区贡献。当然，这些只是建议，你可以以任何方式进行贡献。对于新功能的添加，请先通过 Issue 讨论。

### 开发环境

请使用仓库定义的可复现工具链和检查入口：

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
make doctor
make bootstrap
```

Linux 下完整的工具安装、开发服务、日志、检查与 NapCat 代码生成流程请参阅
[Linux 开发环境](docs/zh/dev/linux.md)。

## ❤️ Special Thanks

特别感谢所有 Contributors 和插件开发者对 AstrBot 的贡献 ❤️

此外，本项目的诞生离不开以下开源项目的帮助：

- [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ) - 伟大的猫猫框架

开源项目友情链接：

- [NoneBot2](https://github.com/nonebot/nonebot2) - 优秀的 Python 异步 ChatBot 框架
- [Koishi](https://github.com/koishijs/koishi) - 优秀的 Node.js ChatBot 框架
- [MaiBot](https://github.com/Mai-with-u/MaiBot) - 优秀的拟人化 AI ChatBot
- [nekro-agent](https://github.com/KroMiose/nekro-agent) - 优秀的 Agent ChatBot
- [LangBot](https://github.com/langbot-app/LangBot) - 优秀的多平台 AI ChatBot
- [ChatLuna](https://github.com/ChatLunaLab/chatluna) - 优秀的多平台 AI ChatBot Koishi 插件
- [Operit AI](https://github.com/AAswordman/Operit) - 优秀的 AI 智能助手 Android APP

## ⭐ Star History

> [!TIP]
> 如果本项目对您的生活 / 工作产生了帮助，或者您关注本项目的未来发展，请给项目 Star，这是我们维护这个开源项目的动力 <3

_陪伴与能力从来不应该是对立面。我们希望创造的是一个既能理解情绪、给予陪伴，也能可靠完成工作的机器人。_

_私は、高性能ですから!_

<img src="https://files.astrbot.app/watashiwa-koseino-desukara.gif" width="100"/>

</div>
