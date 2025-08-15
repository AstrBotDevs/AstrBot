[![MseeP.ai Security Assessment Badge](https://mseep.net/pr/astrbotdevs-astrbot-badge.png)](https://mseep.ai/app/astrbotdevs-astrbot)

<p align="center">
 
![AstrBot-Logo-Simplified](https://github.com/user-attachments/assets/ffd99b6b-3272-4682-beaa-6fe74250f7d9)

</p>

<div align="center">

_✨ 易上手的多平台 LLM 聊天机器人及开发框架 ✨_

<a href="https://trendshift.io/repositories/12875" target="_blank"><img src="https://trendshift.io/api/badge/repositories/12875" alt="Soulter%2FAstrBot | Trendshift" style="width: 250px; height: 55px;" width="250" height="55"/></a>

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/Soulter/AstrBot?style=for-the-badge&color=76bad9)](https://github.com/Soulter/AstrBot/releases/latest)
<img src="https://img.shields.io/badge/python-3.10+-blue.svg?style=for-the-badge&color=76bad9" alt="python">
<a href="https://hub.docker.com/r/soulter/astrbot"><img alt="Docker pull" src="https://img.shields.io/docker/pulls/soulter/astrbot.svg?style=for-the-badge&color=76bad9"/></a>
<a  href="https://qm.qq.com/cgi-bin/qm/qr?k=wtbaNx7EioxeaqS9z7RQWVXPIxg2zYr7&jump_from=webapi&authKey=vlqnv/AV2DbJEvGIcxdlNSpfxVy+8vVqijgreRdnVKOaydpc+YSw4MctmEbr0k5"><img alt="QQ_community" src="https://img.shields.io/badge/QQ群-775869627-purple?style=for-the-badge&color=76bad9"></a>
<a  href="https://t.me/+hAsD2Ebl5as3NmY1"><img alt="Telegram_community" src="https://img.shields.io/badge/Telegram-AstrBot-purple?style=for-the-badge&color=76bad9"></a>
[![wakatime](https://wakatime.com/badge/user/915e5316-99c6-4563-a483-ef186cf000c9/project/018e705a-a1a7-409a-a849-3013485e6c8e.svg?style=for-the-badge&color=76bad9)](https://wakatime.com/badge/user/915e5316-99c6-4563-a483-ef186cf000c9/project/018e705a-a1a7-409a-a849-3013485e6c8e)
![Dynamic JSON Badge](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fapi.soulter.top%2Fastrbot%2Fstats&query=v&label=7日消息量&cacheSeconds=3600&style=for-the-badge&color=3b618e)
![Dynamic JSON Badge](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fapi.soulter.top%2Fastrbot%2Fplugin-num&query=%24.result&suffix=%E4%B8%AA&style=for-the-badge&label=%E6%8F%92%E4%BB%B6%E5%B8%82%E5%9C%BA&cacheSeconds=3600)

<a href="https://github.com/Soulter/AstrBot/blob/master/README_en.md">English</a> ｜
<a href="https://github.com/Soulter/AstrBot/blob/master/README_ja.md">日本語</a> ｜
<a href="https://astrbot.app/">查看文档</a> ｜
<a href="https://github.com/Soulter/AstrBot/issues">问题提交</a>
</div>

AstrBot 是一个松耦合、异步、支持多消息平台部署、具有易用的插件系统和完善的大语言模型（LLM）接入功能的聊天机器人及开发框架。

## ✨ 主要功能

1. **大模型对话**。支持接入多种大模型服务。支持多模态、工具调用、MCP、原生知识库、人设等功能。
2. **多消息平台支持**。支持接入 QQ、企业微信、微信公众号、飞书、Telegram、钉钉、Discord、KOOK 等平台。支持速率限制、白名单、百度内容审核。
3. **Agent**。完善适配的 Agentic 能力。支持多轮工具调用、内置沙盒代码执行器、网页搜索等功能。
4. **插件扩展**。深度优化的插件机制，支持[开发插件](https://astrbot.app/dev/plugin.html)扩展功能，社区插件生态丰富。
5. **WebUI**。可视化配置和管理机器人，功能齐全。

## ✨ 使用方式

#### Docker 部署

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

[![Run on Repl.it](https://repl.it/badge/github/Soulter/AstrBot)](https://repl.it/github/Soulter/AstrBot)

#### Windows 一键安装器部署

请参阅官方文档 [使用 Windows 一键安装器部署 AstrBot](https://astrbot.app/deploy/astrbot/windows.html) 。

#### CasaOS 部署

社区贡献的部署方式。

请参阅官方文档 [CasaOS 部署](https://astrbot.app/deploy/astrbot/casaos.html) 。

#### 手动部署

> 推荐使用 `uv`。

首先，安装 uv：

```bash
pip install uv
```

通过 Git Clone 安装 AstrBot：

```bash
git clone https://github.com/AstrBotDevs/AstrBot && cd AstrBot
uv run main.py
```

或者请参阅官方文档 [通过源码部署 AstrBot](https://astrbot.app/deploy/astrbot/cli.html) 。

## ⚡ 消息平台支持情况

| 平台    | 支持性 |
| -------- | ------- |
| QQ(官方机器人接口) | ✔    |
| QQ(OneBot)      | ✔    |
| Telegram   | ✔    |
| 企业微信    | ✔    |
| 微信客服    | ✔    |
| 微信公众号    | ✔    |
| 飞书   | ✔    |
| 钉钉   | ✔    |
| Slack   | ✔    |
| Discord   | ✔    |
| [KOOK](https://github.com/wuyan1003/astrbot_plugin_kook_adapter)   | ✔    |
| [VoceChat](https://github.com/HikariFroya/astrbot_plugin_vocechat)   | ✔    |
| 微信对话开放平台 | 🚧    |
| WhatsApp   | 🚧    |
| 小爱音响   | 🚧    |

## ⚡ 提供商支持情况

| 名称    | 支持性 | 类型 | 备注 |
| -------- | ------- | ------- | ------- |
| OpenAI API | ✔    | 文本生成 | 也支持 DeepSeek、Gemini、Kimi、xAI 等兼容 OpenAI API 的服务 |
| Claude API | ✔    | 文本生成 |  |
| Google Gemini API | ✔    | 文本生成 |  |
| Dify | ✔    | LLMOps |  |
| 阿里云百炼应用 | ✔    | LLMOps |  |
| Ollama | ✔    | 模型加载器 | 本地部署 DeepSeek、Llama 等开源语言模型 |
| LM Studio | ✔    | 模型加载器 | 本地部署 DeepSeek、Llama 等开源语言模型 |
| LLMTuner | ✔    | 模型加载器 | 本地加载 lora 等微调模型 |
| [优云智算](https://www.compshare.cn/?ytag=GPU_YY-gh_astrbot&referral_code=FV7DcGowN4hB5UuXKgpE74) | ✔    | 模型 API 及算力服务平台 |  |
| [302.AI](https://share.302.ai/rr1M3l) | ✔    | 模型 API 服务平台 |  |
| 硅基流动 | ✔    | 模型 API 服务平台 |  |
| PPIO 派欧云 | ✔    | 模型 API 服务平台 |  |
| OneAPI | ✔    | LLM 分发系统 |  |
| Whisper | ✔    | 语音转文本 | 支持 API、本地部署 |
| SenseVoice | ✔    | 语音转文本 | 本地部署 |
| OpenAI TTS API | ✔    | 文本转语音 |  |
| GSVI | ✔    | 文本转语音 | GPT-Sovits-Inference |
| GPT-SoVITs | ✔    | 文本转语音 | GPT-Sovits-Inference |
| FishAudio | ✔    | 文本转语音 | GPT-Sovits 作者参与的项目 |
| Edge TTS | ✔    | 文本转语音 | Edge 浏览器的免费 TTS |
| 阿里云百炼 TTS | ✔    | 文本转语音 |  |
| Azure TTS | ✔    | 文本转语音 | Microsoft Azure TTS |


## ❤️ 贡献

欢迎任何 Issues/Pull Requests！只需要将你的更改提交到此项目 ：)

### 如何贡献

你可以通过查看问题或帮助审核 PR（拉取请求）来贡献。任何问题或 PR 都欢迎参与，以促进社区贡献。当然，这些只是建议，你可以以任何方式进行贡献。对于新功能的添加，请先通过 Issue 讨论。

### 开发环境

AstrBot 使用 `ruff` 进行代码格式化和检查。

```bash
git clone https://github.com/Soulter/AstrBot
pip install pre-commit
pre-commit install
```

## 🌟 支持

- Star 这个项目！
- 在[爱发电](https://afdian.com/a/soulter)支持我！

## ✨ Demo

<details><summary>👉 点击展开多张 Demo 截图 👈</summary>

<div align='center'>

<img src="https://github.com/user-attachments/assets/4ee688d9-467d-45c8-99d6-368f9a8a92d8" width="600">

_✨基于 Docker 的沙箱化代码执行器（Beta 测试）✨_

<img src="https://github.com/user-attachments/assets/0378f407-6079-4f64-ae4c-e97ab20611d2" height=500>

_✨ 多模态、网页搜索、长文本转图片（可配置） ✨_

<img src="https://github.com/user-attachments/assets/e137a9e1-340a-4bf2-bb2b-771132780735" height=150>
<img src="https://github.com/user-attachments/assets/480f5e82-cf6a-4955-a869-0d73137aa6e1" height=150>

_✨ 插件系统——部分插件展示 ✨_

<img src="https://github.com/user-attachments/assets/0cdbf564-2f59-4da5-b524-ce0e7ef3d978" width=600>

_✨ WebUI ✨_

</div>

</details>


## ❤️ Special Thanks

特别感谢所有 Contributors 和插件开发者对 AstrBot 的贡献 ❤️

<a href="https://github.com/AstrBotDevs/AstrBot/graphs/contributors">
  <img src="https://contrib.rocks/image?repo=AstrBotDevs/AstrBot" />
</a>

此外，本项目的诞生离不开以下开源项目：

- [NapNeko/NapCatQQ](https://github.com/NapNeko/NapCatQQ) - 伟大的猫猫框架
- [wechatpy/wechatpy](https://github.com/wechatpy/wechatpy)

## ⭐ Star History

> [!TIP] 
> 如果本项目对您的生活 / 工作产生了帮助，或者您关注本项目的未来发展，请给项目 Star，这是我维护这个开源项目的动力 <3

<div align="center">
    
[![Star History Chart](https://api.star-history.com/svg?repos=soulter/astrbot&type=Date)](https://star-history.com/#soulter/astrbot&Date)

</div>

![10k-star-banner-credit-by-kevin](https://github.com/user-attachments/assets/c97fc5fb-20b9-4bc8-9998-c20b930ab097)


_私は、高性能ですから!_

