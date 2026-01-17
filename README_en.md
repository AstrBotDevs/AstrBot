![AstrBot-Logo-Simplified](https://github.com/user-attachments/assets/ffd99b6b-3272-4682-beaa-6fe74250f7d9)

</p>

<div align="center">

<br>

<div>
<a href="https://trendshift.io/repositories/12875" target="_blank"><img src="https://trendshift.io/api/badge/repositories/12875" alt="Soulter%2FAstrBot | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>
<a href="https://hellogithub.com/repository/AstrBotDevs/AstrBot" target="_blank"><img src="https://api.hellogithub.com/v1/widgets/recommend.svg?rid=d127d50cd5e54c5382328acc3bb25483&claim_uid=ZO9by7qCXgSd6Lp&t=2" alt="Featured｜HelloGitHub" style="width: 250px; height: 54px;" width="250" height="54" /></a>
</div>

<br>

<div>
<img src="https://img.shields.io/github/v/release/AstrBotDevs/AstrBot?style=for-the-badge&color=76bad9" href="https://github.com/AstrBotDevs/AstrBot/releases/latest">
<img src="https://img.shields.io/badge/python-3.10+-blue.svg?style=for-the-badge&color=76bad9" alt="python">
<a href="https://hub.docker.com/r/soulter/astrbot"><img alt="Docker pull" src="https://img.shields.io/docker/pulls/soulter/astrbot.svg?style=for-the-badge&color=76bad9"/></a>
<a href="https://qm.qq.com/cgi-bin/qm/qr?k=wtbaNx7EioxeaqS9z7RQWVXPIxg2zYr7&jump_from=webapi&authKey=vlqnv/AV2DbJEvGIcxdlNSpfxVy+8vVqijgreRdnVKOaydpc+YSw4MctmEbr0k5"><img alt="QQ_community" src="https://img.shields.io/badge/QQ群-775869627-purple?style=for-the-badge&color=76bad9"></a>
<a href="https://t.me/+hAsD2Ebl5as3NmY1"><img alt="Telegram_community" src="https://img.shields.io/badge/Telegram-AstrBot-purple?style=for-the-badge&color=76bad9"></a>
<img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fapi.soulter.top%2Fastrbot%2Fplugin-num&query=%24.result&suffix=%20plugins&style=for-the-badge&label=Marketplace&cacheSeconds=3600">
</div>

<br>

<a href="https://github.com/AstrBotDevs/AstrBot/blob/master/README.md">中文</a> ｜
<a href="https://github.com/AstrBotDevs/AstrBot/blob/master/README_ja.md">日本語</a> ｜
<a href="https://github.com/AstrBotDevs/AstrBot/blob/master/README_zh-TW.md">繁體中文</a> ｜
<a href="https://github.com/AstrBotDevs/AstrBot/blob/master/README_fr.md">Français</a> ｜
<a href="https://github.com/AstrBotDevs/AstrBot/blob/master/README_ru.md">Русский</a>

<a href="https://astrbot.app/">Documentation</a> ｜
<a href="https://blog.astrbot.app/">Blog</a> ｜
<a href="https://astrbot.featurebase.app/roadmap">Roadmap</a> ｜
<a href="https://github.com/AstrBotDevs/AstrBot/issues">Issue Tracker</a>
</div>

AstrBot is an open-source all-in-one Agent chatbot platform that integrates with mainstream instant messaging apps. It provides reliable and scalable conversational AI infrastructure for individuals, developers, and teams. Whether you're building a personal AI companion, intelligent customer service, automation assistant, or enterprise knowledge base, AstrBot enables you to quickly build production-ready AI applications within your IM platform workflows.

<img width="1776" height="1080" alt="image" src="https://github.com/user-attachments/assets/00782c4c-4437-4d97-aabc-605e3738da5c" />

## Key Features

1. 💯 Free & Open Source.
2. ✨ AI LLM Conversations, Multimodal, Agent, MCP, Knowledge Base, Persona Settings.
3. 🤖 Supports integration with Dify, Alibaba Cloud Bailian, Coze and other agent platforms.
4. 🌐 Multi-Platform: QQ, WeChat Work, Feishu, DingTalk, WeChat Official Accounts, Telegram, Slack, and [more](#supported-messaging-platforms).
5. 📦 Plugin Extensions with nearly 800 plugins available for one-click installation.
6. 💻 WebUI Support.
7. 🌐 Internationalization (i18n) Support.

## Quick Start

#### Docker Deployment (Recommended 🥳)

We recommend deploying AstrBot using Docker or Docker Compose.

Please refer to the official documentation: [Deploy AstrBot with Docker](https://astrbot.app/deploy/astrbot/docker.html#%E4%BD%BF%E7%94%A8-docker-%E9%83%A8%E7%BD%B2-astrbot).

#### uv Deployment

```bash
uvx astrbot
```

#### BT-Panel Deployment

AstrBot has partnered with BT-Panel and is now available in their marketplace.

Please refer to the official documentation: [BT-Panel Deployment](https://astrbot.app/deploy/astrbot/btpanel.html).

#### 1Panel Deployment

AstrBot has been officially listed on the 1Panel marketplace.

Please refer to the official documentation: [1Panel Deployment](https://astrbot.app/deploy/astrbot/1panel.html).

#### Deploy on RainYun

AstrBot has been officially listed on RainYun's cloud application platform with one-click deployment.

[![Deploy on RainYun](https://rainyun-apps.cn-nb1.rains3.com/materials/deploy-on-rainyun-en.svg)](https://app.rainyun.com/apps/rca/store/5994?ref=NjU1ODg0)

#### Deploy on Replit

Community-contributed deployment method.

[![Run on Repl.it](https://repl.it/badge/github/AstrBotDevs/AstrBot)](https://repl.it/github/AstrBotDevs/AstrBot)

#### Windows One-Click Installer

Please refer to the official documentation: [Deploy AstrBot with Windows One-Click Installer](https://astrbot.app/deploy/astrbot/windows.html).

#### CasaOS Deployment

Community-contributed deployment method.

Please refer to the official documentation: [CasaOS Deployment](https://astrbot.app/deploy/astrbot/casaos.html).

#### Manual Deployment

First, install uv:

```bash
pip install uv
```

Install AstrBot via Git Clone:

```bash
git clone https://github.com/AstrBotDevs/AstrBot && cd AstrBot
uv run main.py
```

Or refer to the official documentation: [Deploy AstrBot from Source](https://astrbot.app/deploy/astrbot/cli.html).

## Supported Messaging Platforms

**Officially Maintained**

- QQ (Official Platform & OneBot)
- Telegram
- WeChat Work Application & WeChat Work Intelligent Bot
- WeChat Customer Service & WeChat Official Accounts
- Feishu (Lark)
- DingTalk
- Slack
- Discord
- Satori
- Misskey
- WhatsApp (Coming Soon)
- LINE (Coming Soon)

**Community Maintained**

- [Matrix](https://github.com/stevessr/astrbot_plugin_matrix_adapter)
- [KOOK](https://github.com/wuyan1003/astrbot_plugin_kook_adapter)
- [VoceChat](https://github.com/HikariFroya/astrbot_plugin_vocechat)

## Supported Model Services

**LLM Services**

- OpenAI and Compatible Services
- Anthropic
- Google Gemini
- Moonshot AI
- Zhipu AI
- DeepSeek
- Ollama (Self-hosted)
- LM Studio (Self-hosted)
- [CompShare](https://www.compshare.cn/?ytag=GPU_YY-gh_astrbot&referral_code=FV7DcGowN4hB5UuXKgpE74)
- [302.AI](https://share.302.ai/rr1M3l)
- [TokenPony](https://www.tokenpony.cn/3YPyf)
- [SiliconFlow](https://docs.siliconflow.cn/cn/usecases/use-siliconcloud-in-astrbot)
- [PPIO Cloud](https://ppio.com/user/register?invited_by=AIOONE)
- ModelScope
- OneAPI

**LLMOps Platforms**

- Dify
- Alibaba Cloud Bailian Applications
- Coze

**Speech-to-Text Services**

- OpenAI Whisper
- SenseVoice

**Text-to-Speech Services**

- OpenAI TTS
- Gemini TTS
- GPT-Sovits-Inference
- GPT-Sovits
- FishAudio
- Edge TTS
- Alibaba Cloud Bailian TTS
- Azure TTS
- Minimax TTS
- Volcano Engine TTS

## ❤️ Contributing

Issues and Pull Requests are always welcome! Feel free to submit your changes to this project :)

### How to Contribute

You can contribute by reviewing issues or helping with pull request reviews. Any issues or PRs are welcome to encourage community participation. Of course, these are just suggestions—you can contribute in any way you like. For adding new features, please discuss through an Issue first.

### Development Environment

AstrBot uses `ruff` for code formatting and linting.

```bash
git clone https://github.com/AstrBotDevs/AstrBot
pip install pre-commit
pre-commit install
```

## 🌍 Community

### QQ Groups

- Group 1: 322154837
- Group 3: 630166526
- Group 5: 822130018
- Group 6: 753075035
- Developer Group: 975206796

### Telegram Group

<a href="https://t.me/+hAsD2Ebl5as3NmY1"><img alt="Telegram_community" src="https://img.shields.io/badge/Telegram-AstrBot-purple?style=for-the-badge&color=76bad9"></a>

### Discord Server

<a href="https://discord.gg/hAVk6tgV36"><img alt="Discord_community" src="https://img.shields.io/badge/Discord-AstrBot-purple?style=for-the-badge&color=76bad9"></a>

## ❤️ Special Thanks

Special thanks to all Contributors and plugin developers for their contributions to AstrBot ❤️

<a href="https://github.com/AstrBotDevs/AstrBot/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=AstrBotDevs/AstrBot" />
</a>

Additionally, the birth of this project would not have been possible without the help of the following open-source projects:

- [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ) - The amazing cat framework

## ⭐ Star History

> [!TIP]
> If this project has helped you in your life or work, or if you're interested in its future development, please give the project a Star. It's the driving force behind maintaining this open-source project <3

<div align="center">

[![Star History Chart](https://api.star-history.com/svg?repos=astrbotdevs/astrbot&type=Date)](https://star-history.com/#astrbotdevs/astrbot&Date)

</div>

</details>

_私は、高性能ですから!_
