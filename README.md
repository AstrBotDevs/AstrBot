
<p align="center">

<img src="https://github.com/user-attachments/assets/de10f24d-cd64-433a-90b8-16c0a60de24a" width=500>

</p>

<div align="center">

<h1>AstrBot</h1>

_✨ 易上手的多平台 LLM 聊天机器人及开发框架 ✨_

[![GitHub release (latest by date)](https://img.shields.io/github/v/release/Soulter/AstrBot)](https://github.com/Soulter/AstrBot/releases/latest)
<img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="python">
<a href="https://hub.docker.com/r/soulter/astrbot"><img alt="Docker pull" src="https://img.shields.io/docker/pulls/soulter/astrbot.svg"/></a>
<img alt="Static Badge" src="https://img.shields.io/badge/QQ群-322154837-purple">
[![wakatime](https://wakatime.com/badge/user/915e5316-99c6-4563-a483-ef186cf000c9/project/018e705a-a1a7-409a-a849-3013485e6c8e.svg)](https://wakatime.com/badge/user/915e5316-99c6-4563-a483-ef186cf000c9/project/018e705a-a1a7-409a-a849-3013485e6c8e)
[![codecov](https://codecov.io/gh/Soulter/AstrBot/graph/badge.svg?token=FF3P5967B8)](https://codecov.io/gh/Soulter/AstrBot)
[<img src="https://api.gitsponsors.com/api/badge/img?id=575865240" height="20">](https://api.gitsponsors.com/api/badge/link?p=XEpbdGxlitw/RbcwiTX93UMzNK/jgDYC8NiSzamIPMoKvG2lBFmyXhSS/b0hFoWlBBMX2L5X5CxTDsUdyvcIEHTOfnkXz47UNOZvMwyt5CzbYpq0SEzsSV1OJF1cCo90qC/ZyYKYOWedal3MhZ3ikw==)
</a>

<a href="https://astrbot.lwl.lol/">查看文档</a> ｜
<a href="https://github.com/Soulter/AstrBot/issues">问题提交</a>
</div>

AstrBot 是一个松耦合、异步、支持多消息平台部署、具有易用的插件系统和完善的大语言模型（LLM）接入功能的聊天机器人及开发框架。

## ✨ 主要功能

1. **大语言模型对话**。支持各种大语言模型，包括 OpenAI API、Google Gemini、Llama、Deepseek、ChatGLM 等，支持接入本地部署的大模型，通过 Ollama、LLMTuner。具有多轮对话、人格情境、多模态能力，支持图片理解、语音转文字（Whisper）。
2. **多消息平台接入**。支持接入 QQ（OneBot）、QQ 频道、微信（Gewechat、VChat）、Telegram。后续将支持钉钉、飞书、Discord、WhatsApp、小爱音响。支持速率限制、白名单、关键词过滤、百度内容审核。
3. **Agent**。原生支持部分 Agent 能力，如代码执行器、自然语言待办、网页搜索。对接 [Dify 平台](https://astrbot.soulter.top/others/dify.html)，便捷接入 Dify 智能助手、知识库和 Dify 工作流。
4. **插件扩展**。深度优化的插件机制，支持[开发插件](https://astrbot.soulter.top/dev/plugin.html)扩展功能，极简开发。已支持安装多个插件。
5. **可视化管理面板**。支持可视化修改配置、插件管理、日志查看等功能，降低配置难度。集成 WebChat，可在面板上与大模型对话。
6. **高稳定性、高模块化**。基于事件总线和流水线的架构设计，高度模块化，低耦合。

> [!TIP]
> 管理面板在线体验 Demo: [https://astrbot-demo.soulter.top/](https://astrbot-demo.soulter.top/)
> 
> 用户名: `astrbot`, 密码: `astrbot`。此 Demo 未配置 LLM，因此无法在聊天页使用大模型。

## ✨ 使用方式

#### Docker 部署

请参阅官方文档 [使用 Docker 部署 AstrBot](https://astrbot.soulter.top/deploy/astrbot/docker.html#%E4%BD%BF%E7%94%A8-docker-%E9%83%A8%E7%BD%B2-astrbot) 。

#### Windows 一键安装器部署

需要电脑上安装有 Python（>3.10）。请参阅官方文档 [使用 Windows 一键安装器部署 AstrBot](https://astrbot.soulter.top/deploy/astrbot/windows.html) 。

#### Replit 部署

[![Run on Repl.it](https://repl.it/badge/github/Soulter/AstrBot)](https://repl.it/github/Soulter/AstrBot)

#### CasaOS 部署

社区贡献的部署方式。

请参阅官方文档 [通过源码部署 AstrBot](https://astrbot.soulter.top/deploy/astrbot/casaos.html) 。

#### 手动部署

请参阅官方文档 [通过源码部署 AstrBot](https://astrbot.soulter.top/deploy/astrbot/cli.html) 。


## ⚡ 消息平台支持情况


| 平台    | 支持性 | 详情 | 消息类型 |
| -------- | ------- | ------- | ------ |
| QQ      | ✔    | 私聊、群聊 | 文字、图片、语音 |
| QQ 官方API | ✔    | 私聊、群聊，QQ 频道私聊、群聊 | 文字、图片 |
| 微信    | ✔    | [Gewechat](https://github.com/Devo919/Gewechat)。微信个人号私聊、群聊 | 文字 |
| [Telegram](https://github.com/Soulter/astrbot_plugin_telegram)   | ✔    | 私聊、群聊 | 文字、图片 |
| 微信对话开放平台 | 🚧    | 计划内 | - |
| 飞书   | 🚧    | 计划内 | - |
| Discord   | 🚧    | 计划内 | - |
| WhatsApp   | 🚧    | 计划内 | - |
| 小爱音响   | 🚧    | 计划内 | - |

## ❤️ 贡献

欢迎任何 Issues/Pull Requests！只需要将你的更改提交到此项目 ：)

对于新功能的添加，请先通过 Issue 讨论。

## 🌟 支持

- Star 这个项目！
- 在[爱发电](https://afdian.com/a/soulter)支持我！
- 在[微信](https://drive.soulter.top/f/pYfA/d903f4fa49a496fda3f16d2be9e023b5.png)支持我~

## ✨ Demo

> [!NOTE]
> 代码执行器的文件输入/输出目前仅测试了 Napcat(QQ), Lagrange(QQ)

<div align='center'>

<img src="https://github.com/user-attachments/assets/4ee688d9-467d-45c8-99d6-368f9a8a92d8" width="600">

_✨基于 Docker 的沙箱化代码执行器（Beta 测试中）✨_

<img src="https://github.com/user-attachments/assets/0378f407-6079-4f64-ae4c-e97ab20611d2" height=500>

_✨ 多模态、网页搜索、长文本转图片（可配置） ✨_

<img src="https://github.com/user-attachments/assets/8ec12797-e70f-460a-959e-48eca39ca2bb" height=100>

_✨ 自然语言待办事项 ✨_

<img src="https://github.com/user-attachments/assets/e137a9e1-340a-4bf2-bb2b-771132780735" height=150>
<img src="https://github.com/user-attachments/assets/480f5e82-cf6a-4955-a869-0d73137aa6e1" height=150>

_✨ 插件系统——部分插件展示 ✨_

<img src="https://github.com/user-attachments/assets/592a8630-14c7-4e06-b496-9c0386e4f36c" width=600>

_✨ 管理面板 ✨_

![webchat](https://drive.soulter.top/f/vlsA/ezgif-5-fb044b2542.gif)

_✨ 内置 Web Chat，在线与机器人交互 ✨_

</div>


<!-- ## ✨ ATRI [Beta 测试]

该功能作为插件载入。插件仓库地址：[astrbot_plugin_atri](https://github.com/Soulter/astrbot_plugin_atri)

1. 基于《ATRI ~ My Dear Moments》主角 ATRI 角色台词作为微调数据集的 `Qwen1.5-7B-Chat Lora` 微调模型。
2. 长期记忆
3. 表情包理解与回复
4. TTS
    -->

_アトリは、高性能ですから!_

