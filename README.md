![AstrBot-Logo-Simplified](https://github.com/user-attachments/assets/ffd99b6b-3272-4682-beaa-6fe74250f7d9)

</p>

<div align="center">

<br>

<div>
<a href="https://trendshift.io/repositories/12875" target="_blank"><img src="https://trendshift.io/api/badge/repositories/12875" alt="Soulter%2FAstrBot | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>
<a href="https://hellogithub.com/repository/AstrBotDevs/AstrBot" target="_blank"><img src="https://api.hellogithub.com/v1/widgets/recommend.svg?rid=d127d50cd5e54c5382328acc3bb25483&claim_uid=ZO9by7qCXgSd6Lp&t=1" alt="Featured｜HelloGitHub" style="width: 250px; height: 54px;" width="250" height="54" /></a>
</div>

<br>

<div>
<img src="https://img.shields.io/github/v/release/AstrBotDevs/AstrBot?style=for-the-badge&color=76bad9" href="https://github.com/AstrBotDevs/AstrBot/releases/latest">
<img src="https://img.shields.io/badge/python-3.10+-blue.svg?style=for-the-badge&color=76bad9" alt="python">
<a href="https://hub.docker.com/r/soulter/astrbot"><img alt="Docker pull" src="https://img.shields.io/docker/pulls/soulter/astrbot.svg?style=for-the-badge&color=76bad9"/></a>
<a href="https://qm.qq.com/cgi-bin/qm/qr?k=wtbaNx7EioxeaqS9z7RQWVXPIxg2zYr7&jump_from=webapi&authKey=vlqnv/AV2DbJEvGIcxdlNSpfxVy+8vVqijgreRdnVKOaydpc+YSw4MctmEbr0k5"><img alt="QQ_community" src="https://img.shields.io/badge/QQ群-775869627-purple?style=for-the-badge&color=76bad9"></a>
<a href="https://t.me/+hAsD2Ebl5as3NmY1"><img alt="Telegram_community" src="https://img.shields.io/badge/Telegram-AstrBot-purple?style=for-the-badge&color=76bad9"></a>
<img src="https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fapi.soulter.top%2Fastrbot%2Fplugin-num&query=%24.result&suffix=%E4%B8%AA&style=for-the-badge&label=%E6%8F%92%E4%BB%B6%E5%B8%82%E5%9C%BA&cacheSeconds=3600">
</div>

<br>

<a href="https://github.com/AstrBotDevs/AstrBot/blob/master/README_en.md">English</a> ｜
<a href="https://github.com/AstrBotDevs/AstrBot/blob/master/README_ja.md">日本語</a> ｜
<a href="https://astrbot.app/">文档</a> ｜
<a href="https://blog.astrbot.app/">Blog</a> ｜
<a href="https://astrbot.featurebase.app/roadmap">路线图</a> ｜
<a href="https://github.com/AstrBotDevs/AstrBot/issues">问题提交</a>
</div>

AstrBot 是一个开源的一站式 Agent 聊天机器人平台及开发框架。

## 主要功能

1. **大模型对话**。支持接入多种大模型服务。支持多模态、工具调用、MCP、原生知识库、人设等功能。
2. **多消息平台支持**。支持接入 QQ、企业微信、微信公众号、飞书、Telegram、钉钉、Discord、KOOK 等平台。支持速率限制、白名单、百度内容审核。
3. **Agent**。完善适配的 Agentic 能力。支持多轮工具调用、内置沙盒代码执行器、网页搜索等功能。
4. **插件扩展**。深度优化的插件机制，支持[开发插件](https://astrbot.app/dev/plugin.html)扩展功能，社区插件生态丰富。
5. **WebUI**。可视化配置和管理机器人，功能齐全。

## 部署方式

#### Docker 部署(推荐 🥳)

推荐使用 Docker / Docker Compose 方式部署 AstrBot。

请参阅官方文档 [使用 Docker 部署 AstrBot](https://astrbot.app/deploy/astrbot/docker.html#%E4%BD%BF%E7%94%A8-docker-%E9%83%A8%E7%BD%B2-astrbot) 。

#### 宝塔面板部署

AstrBot 与宝塔面板合作，已上架至宝塔面板。

请参阅官方文档 [宝塔面板部署](https://astrbot.app/deploy/astrbot/btpanel.html) 。

#### 1Panel 部署

AstrBot 已由 1Panel 官方上架至 1Panel 面板。

请参阅官方文档 [1Panel 部署](https://astrbot.app/deploy/astrbot/1panel.html) 。

#### 在 雨云 上部署

AstrBot 已由雨云官方上架至云应用平台，可一键部署。

[![Deploy on RainYun](https://rainyun-apps.cn-nb1.rains3.com/materials/deploy-on-rainyun-en.svg)](https://app.rainyun.com/apps/rca/store/5994?ref=NjU1ODg0)

#### 在 Replit 上部署

社区贡献的部署方式。

[![Run on Repl.it](https://repl.it/badge/github/AstrBotDevs/AstrBot)](https://repl.it/github/AstrBotDevs/AstrBot)

#### Windows 一键安装器部署

请参阅官方文档 [使用 Windows 一键安装器部署 AstrBot](https://astrbot.app/deploy/astrbot/windows.html) 。

#### CasaOS 部署

社区贡献的部署方式。

请参阅官方文档 [CasaOS 部署](https://astrbot.app/deploy/astrbot/casaos.html) 。

#### 手动部署

首先安装 uv：

```bash
pip install uv
```

通过 Git Clone 安装 AstrBot：

```bash
git clone https://github.com/AstrBotDevs/AstrBot && cd AstrBot
uv run main.py
```

或者请参阅官方文档 [通过源码部署 AstrBot](https://astrbot.app/deploy/astrbot/cli.html) 。

## 🌍 社区

### QQ 群组

- 1 群：322154837
- 3 群：630166526
- 5 群：822130018
- 6 群：753075035
- 开发者群：975206796

### Telegram 群组

<a href="https://t.me/+hAsD2Ebl5as3NmY1"><img alt="Telegram_community" src="https://img.shields.io/badge/Telegram-AstrBot-purple?style=for-the-badge&color=76bad9"></a>

### Discord 群组

<a href="https://discord.gg/hAVk6tgV36"><img alt="Discord_community" src="https://img.shields.io/badge/Discord-AstrBot-purple?style=for-the-badge&color=76bad9"></a>

## ⚡ 消息平台支持情况

**官方维护**

| 平台    | 支持性 |
| -------- | ------- |
| QQ(官方平台) | ✔    |
| QQ(OneBot)      | ✔    |
| Telegram   | ✔    |
| 企微应用    | ✔    |
| 企微智能机器人 | ✔ |
| 微信客服    | ✔    |
| 微信公众号    | ✔    |
| 飞书   | ✔    |
| 钉钉   | ✔    |
| Slack   | ✔    |
| Discord   | ✔    |
| Satori   | ✔    |
| Misskey   | ✔    |
| Whatsapp | 将支持 |
| LINE | 将支持 |

**社区维护**

| 平台    | 支持性 |
| -------- | ------- |
| [KOOK](https://github.com/wuyan1003/astrbot_plugin_kook_adapter)   | ✔    |
| [VoceChat](https://github.com/HikariFroya/astrbot_plugin_vocechat)   | ✔    |
| [Bilibili 私信](https://github.com/Hina-Chat/astrbot_plugin_bilibili_adapter)   | ✔    |
| [wxauto](https://github.com/luosheng520qaq/wxauto-repost-onebotv11)   | ✔    |

## ⚡ 提供商支持情况

**大模型服务**

| 名称  | 支持性 | 备注 |
| -------- | ------- | ------- |
| OpenAI | ✔    | 支持任何兼容 OpenAI API 的服务 |
| Anthropic | ✔    |  |
| Google Gemini | ✔   |  |
| Moonshot AI | ✔   |  |
| 智谱 AI | ✔   |  |
| DeepSeek | ✔   |  |
| Ollama | ✔     | 本地部署 DeepSeek 等开源语言模型 |
| LM Studio | ✔    | 本地部署 DeepSeek 等开源语言模型 |
| [优云智算](https://www.compshare.cn/?ytag=GPU_YY-gh_astrbot&referral_code=FV7DcGowN4hB5UuXKgpE74) | ✔  |  |
| [302.AI](https://share.302.ai/rr1M3l) | ✔   |  |
| [小马算力](https://www.tokenpony.cn/3YPyf) | ✔   |  |
| 硅基流动 | ✔    |  |
| PPIO 派欧云 | ✔    |  |
| ModelScope | ✔    |  |
| OneAPI | ✔    |  |
| Dify | ✔    |  |
| 阿里云百炼应用 | ✔    |  |
| Coze | ✔    |  |

**语音转文本服务**

| 名称  | 支持性 | 备注 |
| -------- | ------- | ------- |
| Whisper | ✔    | 支持 API、本地部署 |
| SenseVoice | ✔   | 本地部署 |

**文本转语音服务**

| 名称  | 支持性 | 备注 |
| -------- | ------- | ------- |
| OpenAI TTS | ✔    |  |
| Gemini TTS | ✔    |  |
| GSVI | ✔    | GPT-Sovits-Inference |
| GPT-SoVITs | ✔     | GPT-Sovits |
| FishAudio | ✔    | |
| Edge TTS | ✔    | Edge 浏览器的免费 TTS |
| 阿里云百炼 TTS | ✔    |  |
| Azure TTS | ✔   | |
| Minimax TTS | ✔   | |
| 火山引擎 TTS | ✔   | |

## ❤️ 贡献

欢迎任何 Issues/Pull Requests！只需要将你的更改提交到此项目 ：)

### 如何贡献

你可以通过查看问题或帮助审核 PR（拉取请求）来贡献。任何问题或 PR 都欢迎参与，以促进社区贡献。当然，这些只是建议，你可以以任何方式进行贡献。对于新功能的添加，请先通过 Issue 讨论。

### 开发环境

AstrBot 使用 `ruff` 进行代码格式化和检查。

```bash
git clone https://github.com/AstrBotDevs/AstrBot
pip install pre-commit
pre-commit install
```

## ❤️ Special Thanks

特别感谢所有 Contributors 和插件开发者对 AstrBot 的贡献 ❤️

<a href="https://github.com/AstrBotDevs/AstrBot/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=AstrBotDevs/AstrBot" />
</a>

此外，本项目的诞生离不开以下开源项目的帮助：

- [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ) - 伟大的猫猫框架

## ⭐ Star History

> [!TIP] 
> 如果本项目对您的生活 / 工作产生了帮助，或者您关注本项目的未来发展，请给项目 Star，这是我们维护这个开源项目的动力 <3

<div align="center">

[![Star History Chart](https://api.star-history.com/svg?repos=astrbotdevs/astrbot&type=Date)](https://star-history.com/#astrbotdevs/astrbot&Date)

</div>

</details>

_私は、高性能ですから!_
