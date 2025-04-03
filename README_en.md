<p align="center">
    
![6e1279651f16d7fdf4727558b72bbaf1](https://github.com/user-attachments/assets/ead4c551-fc3c-48f7-a6f7-afbfdb820512)

</p>

<div align="center">

_✨ Easy-to-use Multi-platform LLM Chatbot & Development Framework ✨_

<a href="https://trendshift.io/repositories/12875" target="_blank"><img src="https://trendshift.io/api/badge/repositories/12875" alt="Soulter%2FAstrBot | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/Soulter/AstrBot)](https://github.com/Soulter/AstrBot/releases/latest)
<img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="python">
<a href="https://hub.docker.com/r/soulter/astrbot"><img alt="Docker pull" src="https://img.shields.io/docker/pulls/soulter/astrbot.svg"/></a>
<a  href="https://qm.qq.com/cgi-bin/qm/qr?k=wtbaNx7EioxeaqS9z7RQWVXPIxg2zYr7&jump_from=webapi&authKey=vlqnv/AV2DbJEvGIcxdlNSpfxVy+8vVqijgreRdnVKOaydpc+YSw4MctmEbr0k5"><img alt="Static Badge" src="https://img.shields.io/badge/QQ群-630166526-purple"></a>
[![wakatime](https://wakatime.com/badge/user/915e5316-99c6-4563-a483-ef186cf000c9/project/018e705a-a1a7-409a-a849-3013485e6c8e.svg)](https://wakatime.com/badge/user/915e5316-99c6-4563-a483-ef186cf000c9/project/018e705a-a1a7-409a-a849-3013485e6c8e)
![Dynamic JSON Badge](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fapi.soulter.top%2Fastrbot%2Fstats&query=v&label=7%E6%97%A5%E6%B6%88%E6%81%AF%E4%B8%8A%E8%A1%8C%E9%87%8F&cacheSeconds=3600)
[![codecov](https://codecov.io/gh/Soulter/AstrBot/graph/badge.svg?token=FF3P5967B8)](https://codecov.io/gh/Soulter/AstrBot)

<a href="https://astrbot.app/">Documentation</a> ｜
<a href="https://github.com/Soulter/AstrBot/issues">Issue Tracking</a>
</div>

AstrBot is a loosely coupled, asynchronous chatbot and development framework that supports multi-platform deployment, featuring an easy-to-use plugin system and comprehensive Large Language Model (LLM) integration capabilities.

## ✨ Key Features

1. **LLM Conversations** - Supports various LLMs including OpenAI API, Google Gemini, Llama, Deepseek, ChatGLM, etc. Enables local model deployment via Ollama/LLMTuner. Features multi-turn dialogues, personality contexts, multimodal capabilities (image understanding), and speech-to-text (Whisper).
2. **Multi-platform Integration** - Supports QQ (OneBot), QQ Channels, WeChat (Gewechat), Feishu, and Telegram. Planned support for DingTalk, Discord, WhatsApp, and Xiaomi Smart Speakers. Includes rate limiting, whitelisting, keyword filtering, and Baidu content moderation.
3. **Agent Capabilities** - Native support for code execution, natural language TODO lists, web search. Integrates with [Dify Platform](https://dify.ai/) for easy access to Dify assistants/knowledge bases/workflows.
4. **Plugin System** - Optimized plugin mechanism with minimal development effort. Supports multiple installed plugins.
5. **Web Dashboard** - Visual configuration management, plugin controls, logging, and WebChat interface for direct LLM interaction.
6. **High Stability & Modularity** - Event bus and pipeline architecture ensures high modularization and loose coupling.

> [!TIP]
> Dashboard Demo: [https://demo.astrbot.app/](https://demo.astrbot.app/)  
> Username: `astrbot`, Password: `astrbot` (LLM not configured for chat page)

## ✨ Deployment

#### Docker Deployment

See docs: [Deploy with Docker](https://astrbot.app/deploy/astrbot/docker.html#docker-deployment)

#### Windows Installer

Requires Python (>3.10). See docs: [Windows Installer Guide](https://astrbot.app/deploy/astrbot/windows.html)

#### Replit Deployment

[![Run on Repl.it](https://repl.it/badge/github/Soulter/AstrBot)](https://repl.it/github/Soulter/AstrBot)

#### CasaOS Deployment

Community-contributed method.  
See docs: [CasaOS Deployment](https://astrbot.app/deploy/astrbot/casaos.html)

#### Manual Deployment

See docs: [Source Code Deployment](https://astrbot.app/deploy/astrbot/cli.html)

## ⚡ Platform Support

| Platform                                                       | Status | Details             | Message Types       |
| -------------------------------------------------------------- | ------ | ------------------- | ------------------- |
| QQ (Official Bot)                                              | ✔      | Private/Group chats | Text, Images        |
| QQ (OneBot)                                                    | ✔      | Private/Group chats | Text, Images, Voice |
| WeChat (Personal)                                              | ✔      | Private/Group chats | Text, Images, Voice |
| [Telegram](https://github.com/Soulter/astrbot_plugin_telegram) | ✔      | Private/Group chats | Text, Images        |
| [WeChat Work](https://github.com/Soulter/astrbot_plugin_wecom) | ✔      | Private chats       | Text, Images, Voice |
| Feishu                                                         | ✔      | Group chats         | Text, Images        |
| WeChat Open Platform                                           | 🚧      | Planned             | -                   |
| Discord                                                        | 🚧      | Planned             | -                   |
| WhatsApp                                                       | 🚧      | Planned             | -                   |
| Xiaomi Speakers                                                | 🚧      | Planned             | -                   |

## Provider Support Status

| Name                      | Support | Type                   | Notes                                                                 |
|---------------------------|---------|------------------------|-----------------------------------------------------------------------|
| OpenAI API                | ✔       | Text Generation        | Supports all OpenAI API-compatible services including DeepSeek, Google Gemini, GLM, Moonshot, Alibaba Cloud Bailian, Silicon Flow, xAI, etc. |
| Claude API                | ✔       | Text Generation        |                                                                       |
| Google Gemini API         | ✔       | Text Generation        |                                                                       |
| Dify                      | ✔       | LLMOps                 |                                                                       |
| DashScope (Alibaba Cloud) | ✔       | LLMOps                 |                                                                       |
| Ollama                    | ✔       | Model Loader           | Local deployment for open-source LLMs (DeepSeek, Llama, etc.)         |
| LM Studio                 | ✔       | Model Loader           | Local deployment for open-source LLMs (DeepSeek, Llama, etc.)         |
| LLMTuner                  | ✔       | Model Loader           | Local loading of fine-tuned models (e.g. LoRA)                        |
| OneAPI                    | ✔       | LLM Distribution       |                                                                       |
| Whisper                   | ✔       | Speech-to-Text         | Supports API and local deployment                                    |
| SenseVoice                | ✔       | Speech-to-Text         | Local deployment                                                     |
| OpenAI TTS API            | ✔       | Text-to-Speech         |                                                                       |
| Fishaudio                 | ✔       | Text-to-Speech         | Project involving GPT-Sovits author                                  |

# 🦌 Roadmap

> [!TIP]
> Suggestions welcome via Issues <3

- [ ] Ensure feature parity across all platform adapters
- [ ] Optimize plugin APIs
- [ ] Add default TTS services (e.g., GPT-Sovits)
- [ ] Enhance chat features with persistent memory
- [ ] i18n Planning

## ❤️ Contributions

All Issues/PRs welcome! Simply submit your changes to this project :)

For major features, please discuss via Issues first.

## 🌟 Support

- Star this project!
- Support via [Afdian](https://afdian.com/a/soulter)
- WeChat support: [QR Code](https://drive.soulter.top/f/pYfA/d903f4fa49a496fda3f16d2be9e023b5.png)

## ✨ Demos

> [!NOTE]
> Code executor file I/O currently tested with Napcat(QQ)/Lagrange(QQ)

<div align='center'>

<img src="https://github.com/user-attachments/assets/4ee688d9-467d-45c8-99d6-368f9a8a92d8" width="600">

_✨ Docker-based Sandboxed Code Executor (Beta) ✨_

<img src="https://github.com/user-attachments/assets/0378f407-6079-4f64-ae4c-e97ab20611d2" height=500>

_✨ Multimodal Input, Web Search, Text-to-Image ✨_

<img src="https://github.com/user-attachments/assets/8ec12797-e70f-460a-959e-48eca39ca2bb" height=100>

_✨ Natural Language TODO Lists ✨_

<img src="https://github.com/user-attachments/assets/e137a9e1-340a-4bf2-bb2b-771132780735" height=150>
<img src="https://github.com/user-attachments/assets/480f5e82-cf6a-4955-a869-0d73137aa6e1" height=150>

_✨ Plugin System Showcase ✨_

<img src="https://github.com/user-attachments/assets/592a8630-14c7-4e06-b496-9c0386e4f36c" width=600>

_✨ Web Dashboard ✨_

![webchat](https://drive.soulter.top/f/vlsA/ezgif-5-fb044b2542.gif)

_✨ Built-in Web Chat Interface ✨_

</div>

## ⭐ Star History

> [!TIP] 
> If this project helps you, please give it a star <3

<div align="center">
    
[![Star History Chart](https://api.star-history.com/svg?repos=soulter/astrbot&type=Date)](https://star-history.com/#soulter/astrbot&Date)

</div>

## Disclaimer

1. Licensed under `AGPL-v3`.
2. WeChat integration uses [Gewechat](https://github.com/Devo919/Gewechat). Use at your own risk with non-critical accounts.
3. Users must comply with local laws and regulations.

<!-- ## ✨ ATRI [Beta]

Available as plugin: [astrbot_plugin_atri](https://github.com/Soulter/astrbot_plugin_atri)

1. Qwen1.5-7B-Chat Lora model fine-tuned with ATRI character data
2. Long-term memory
3. Meme understanding & responses
4. TTS integration
    -->


_私は、高性能ですから!_

