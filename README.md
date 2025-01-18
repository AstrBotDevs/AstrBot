
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

## ✨ 多消息平台部署

1. QQ 群、QQ 频道、微信个人号、Telegram。
2. 内置 Web Chat，即使不部署到消息平台也能聊天。
3. 支持文本转图片，Markdown 渲染。
   
## ✨ 多 LLM 配置

1. 适配 OpenAI API，支持接入 Gemini、GPT、Llama、Claude、DeepSeek、GLM 等各种大语言模型。
2. 支持 OneAPI 等分发平台。
3. 支持 LLMTuner 载入微调模型。
4. 支持 Ollama 载入自部署模型。
4. 支持网页搜索（Web Search）、自然语言待办提醒。
5. 支持 Whisper 语音转文字

## ✨ 管理面板

1. 支持可视化修改配置
2. 日志实时查看
3. 简单的信息统计
4. 插件管理

## ✨ 支持 Dify

1. 对接了 LLMOps 平台 Dify，便捷接入 Dify 智能助手、知识库和 Dify 工作流！[接入 Dify - AstrBot 文档](https://astrbot.lwl.lol/others/dify.html)

## ✨ 代码执行器(Beta)

基于 Docker 的沙箱化代码执行器（Beta 测试中）

> [!NOTE]
> 文件输入/输出目前仅测试了 Napcat(QQ), Lagrange(QQ)

<div align='center'>

<img src="https://github.com/user-attachments/assets/4ee688d9-467d-45c8-99d6-368f9a8a92d8" width="600">

</div>

## ✨ 云部署

[![Run on Repl.it](https://repl.it/badge/github/Soulter/AstrBot)](https://repl.it/github/Soulter/AstrBot)

## ❤️ 贡献

欢迎任何 Issues/Pull Requests！只需要将你的更改提交到此项目 ：)

对于新功能的添加，请先通过 Issue 讨论。

## 🔭 展望

1. 更强大的 Agent 系统。
2. 打造插件工作流平台。

## ✨ Support

- Star 这个项目！
- 在[爱发电](https://afdian.com/a/soulter)支持我！
- 在[微信](https://drive.soulter.top/f/pYfA/d903f4fa49a496fda3f16d2be9e023b5.png)支持我~



## ✨ Demo

<div align='center'>

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

