![AstrBot-Logo-Simplified](https://github.com/user-attachments/assets/36fb04e4-cc75-4454-bd8b-049d11aa86f9)

<div align="center">

<a href="./README.md">English</a> ｜
<a href="./README_zh.md">简体中文</a>

<br>

<div>
<img src="https://img.shields.io/badge/python-3.14+-blue.svg" alt="python">
<img src="https://img.shields.io/badge/deployment-source%20build-76bad9" alt="source build">
</div>

<br>

<a href="./docs/en/index.md">Documentation</a> ｜
<a href="https://github.com/Xero-Team/AstrBot/issues">Issue Tracker</a> ｜
<a href="./docs/en/dev/development.md">Development Guide</a>

</div>

AstrBot is an open-source all-in-one Agent chatbot platform that integrates with mainstream instant messaging apps. It provides reliable and scalable conversational AI infrastructure for individuals, developers, and teams. Whether you're building a personal AI companion, intelligent customer service, automation assistant, or local knowledge-base retrieval, AstrBot lets you assemble AI applications inside IM workflows. The knowledge base is currently a single-node SQLite + FAISS store, not a hosted enterprise search service.

This repository is a modernized fork of AstrBot. The code, commands, deployment files, and compatibility expectations documented here describe this fork only: Python 3.14+, `uv` for backend workflows, `pnpm` for the dashboard, and no legacy compatibility shims.

![screenshot_1 5x_postspark_2026-02-27_22-37-45](https://github.com/user-attachments/assets/f17cdb90-52d7-4773-be2e-ff64b566af6b)

## Key Features

1. 💯 Free & Open Source.
2. ✨ AI LLM Conversations, Multimodal, Agent, MCP, Skills, Knowledge Base, Persona Settings, Auto Context Compression.
3. 🤖 Supports integration with Dify, Alibaba Cloud Bailian, Coze, and other agent platforms.
4. 🌐 Multi-Platform: QQ, WeChat Work, Feishu, DingTalk, WeChat Official Accounts, Telegram, Slack, and [more](#supported-messaging-platforms).
5. 📦 Plugin extensions with a community marketplace and a sandboxed Dashboard Extension Protocol.
6. 🛡️ [Agent Sandbox](docs/en/use/astrbot-agent-sandbox.md) for isolated, safe execution of code, shell calls, and session-level resource reuse.
7. 💻 WebUI Support.
8. 🌈 Web ChatUI Support with built-in agent sandbox and web search.
9. 🌐 Bilingual WebUI: Simplified Chinese and English.

<br>

<table align="center">
  <tr align="center">
    <th>💙 Role-playing & Emotional Companionship</th>
    <th>✨ Proactive Agent</th>
    <th>🚀 General Agentic Capabilities</th>
    <th>🧩 Community Plugins</th>
  </tr>
  <tr>
    <td align="center"><p align="center"><img width="984" height="1746" alt="99b587c5d35eea09d84f33e6cf6cfd4f" src="https://github.com/user-attachments/assets/89196061-3290-458d-b51f-afa178049f84" /></p></td>
    <td align="center"><p align="center"><img width="976" height="1612" alt="c449acd838c41d0915cc08a3824025b1" src="https://github.com/user-attachments/assets/f75368b4-e022-41dc-a9e0-131c3e73e32e" /></p></td>
    <td align="center"><p align="center"><img width="974" height="1732" alt="image" src="https://github.com/user-attachments/assets/e22a3968-87d7-4708-a7cd-e7f198c7c32e" /></p></td>
    <td align="center"><p align="center"><img width="976" height="1734" alt="image" src="https://github.com/user-attachments/assets/0952b395-6b4a-432a-8a50-c294b7f89750" /></p></td>
  </tr>
</table>

## Quick Start

### Run from Source

This fork currently publishes neither a PyPI package nor prebuilt release assets. The package named `astrbot` on PyPI, AUR packages, and upstream container images do not represent this branch. Run the current code from a checkout:

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

Install [uv](https://docs.astral.sh/uv/), Node.js 26.5.0, and pnpm 11.21.0 first. The checkout pins Python 3.14.6 and the required pnpm version. On first startup, open `http://localhost:6185` and use the random password printed in the log; the default username is `astrbot`.

If you enable local text-to-image or plugin HTML rendering, also run `uv run astrbot install-browser` once. See [Deploy AstrBot from Source](docs/en/deploy/astrbot/cli.md) for updates, remote access, and security guidance.

### Docker Deployment

This fork does not publish an official prebuilt image. Build from the current checkout. Compose binds the containerized Dashboard to `0.0.0.0`, while host ports bind to `127.0.0.1` by default. For remote access, explicitly set `ASTRBOT_BIND_ADDRESS=0.0.0.0` and configure a firewall or HTTPS reverse proxy.

Then build and start it:

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
docker compose up -d --build
docker compose logs -f astrbot
```

Compose builds the complete runtime by default. To omit optional browser,
document-conversion, media, OCR, Node.js, or Docker CLI assets, set the
`ASTRBOT_FEATURES` build argument and rebuild the image:

The `minimal` profile still serves the WebUI: the Dashboard is compiled into
static files during the image build and served by AstrBot's Python/FastAPI
runtime. Add `node` only for Node-based MCP launchers and other Node.js
integrations.

```bash
# Minimal runtime for a smaller image
ASTRBOT_FEATURES=minimal docker compose up -d --build

# Enable only Chromium, Node.js, and Docker CLI
ASTRBOT_FEATURES=browser,node,docker docker compose up -d --build
```

To persist the choice, add for example
`ASTRBOT_FEATURES=browser,media,fonts` to `.env` in the repository root.
The NapCat stack accepts the same argument:

```bash
ASTRBOT_FEATURES=browser,node,docker \
  docker compose -f compose-with-napcat.yml up -d --build
```

If you want to start AstrBot and NapCat together from this repository:

```bash
docker compose -f compose-with-napcat.yml up -d --build
```

Binding to `0.0.0.0` is an explicit exposure choice. Restrict access with a firewall and preferably an HTTPS reverse proxy. More details: [Deploy AstrBot with Docker](docs/en/deploy/astrbot/docker.md).

## Supported Messaging Platforms

Connect AstrBot to your favorite chat platform.

| Built-in integration               | Adapter type(s)                        |
| ---------------------------------- | -------------------------------------- |
| QQ Official Bot                    | `qq_official`, `qq_official_webhook`   |
| OneBot v11                         | `aiocqhttp`                            |
| NapCat                             | `napcat`                               |
| Telegram                           | `telegram`                             |
| WeCom / WeCom AI Bot               | `wecom`, `wecom_ai_bot`                |
| WeChat Official Account / Personal | `weixin_official_account`, `weixin_oc` |
| Lark / DingTalk                    | `lark`, `dingtalk`                     |
| Slack / Discord                    | `slack`, `discord`                     |
| LINE / Satori / KOOK               | `line`, `satori`, `kook`               |
| Misskey / Mattermost               | `misskey`, `mattermost`                |
| Built-in browser chat              | `webchat`                              |

This table reflects the current built-in adapter discovery map. Plugins can add more adapters; the **Bots → Create Bot** list in the running WebUI is authoritative. See [Messaging Platforms](docs/en/platform/start.md).

## Supported Model Services

| Service type       | Current built-in range                                                                                                                         |
| ------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Chat models        | OpenAI Chat Completions/Responses and compatible APIs, Anthropic, Gemini, Zhipu, Xiaomi, MiniMax, Kimi Code, xAI, Groq, OpenRouter, and others |
| Local models       | Ollama and LM Studio through their supported APIs                                                                                              |
| Agent Runners      | Built-in local Agent plus Dify, Coze, Alibaba Cloud Bailian applications, and DeerFlow                                                         |
| Speech             | Whisper, SenseVoice, Xiaomi MiMo, Xinference, OpenAI/Gemini/Edge/Azure/ElevenLabs TTS, GPT-SoVITS, FishAudio, DashScope, and others            |
| Embedding / Rerank | OpenAI, Gemini, NVIDIA, Ollama, vLLM, Xinference, and Alibaba Cloud Bailian                                                                    |

Provider templates come from the code registry and evolve over time. Treat **Providers → Add Provider Source** in the running WebUI as authoritative; see [Model Providers](docs/en/providers/start.md).

## ❤️ Contributing

Issues and Pull Requests are always welcome. Please target this fork's repository and keep documentation aligned with the current branch behavior rather than upstream historical behavior.

### How to Contribute

You can contribute by reviewing issues or helping with pull request reviews. Any issues or PRs are welcome to encourage community participation. Of course, these are just suggestions—you can contribute in any way you like. For adding new features, please discuss through an Issue first.

### Development Environment

Use the repository's reproducible toolchain and checks:

```bash
git clone https://github.com/Xero-Team/AstrBot.git
cd AstrBot
make doctor
make bootstrap
```

For the complete Linux workflow, including tool installation, development
servers, logs, checks, and NapCat code generation, see [Linux Development](docs/en/dev/linux.md).

## ❤️ Special Thanks

Special thanks to all Contributors and plugin developers for their contributions to AstrBot ❤️

Additionally, the birth of this project would not have been possible without the help of the following open-source projects:

- [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ) - The amazing cat framework

## ⭐ Star History

> [!TIP]
> If this project has helped you in your life or work, or if you're interested in its future development, please give the project a Star. It's the driving force behind maintaining this open-source project <3

_Companionship and capability should never be at odds. What we aim to create is a robot that can understand emotions, provide genuine companionship, and reliably accomplish tasks._

_私は、高性能ですから!_

<img src="https://files.astrbot.app/watashiwa-koseino-desukara.gif" width="100"/>
</div>
