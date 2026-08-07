---
outline: deep
---

# 函数调用（Function-calling）

## 简介

函数调用旨在提供大模型**调用外部工具的能力**，以此实现 Agentic 的一些功能。

比如，问大模型：帮我搜索一下关于“猫”的信息，大模型会调用用于搜索的外部工具，比如搜索引擎，然后返回搜索结果。

目前，支持的模型包括但远不限于

- GPT-5.x 系列
- Gemini 3.x 系列
- Claude 4.x 系列
- Deepseek v3.2(deepseek-chat)
- Qwen 3.x 系列

2025年后推出的主流模型通常已支持函数调用。

不支持的模型比较常见的有 Deepseek-R1, Gemini 2.0 的 thinking 类等较老模型。

在 AstrBot 中，可以通过函数调用暴露网页搜索、待办提醒以及 Agent / 沙盒相关工具链。很多插件，如:

- astrbot_plugin_cloudmusic
- astrbot_plugin_bilibili
- ...

等在提供传统的指令调用的基础上，也提供了函数调用的功能。

相关操作请在 WebUI 中管理工具的开启和关闭。

## 原生并行工具调用

AstrBot 可以并行执行同一轮模型响应中彼此独立的函数调用。该功能默认关闭，
需要先在 WebUI 工具面板开启总开关，再逐个允许工具。具有副作用、直接向用户
发送消息、Handoff、后台任务或明确要求串行的工具不能启用并行。

即使工具完成顺序不同，写回模型上下文的结果仍保持调用顺序。MCP 工具使用
按服务器划分的并发限制（默认值为 1），因此启用工具并不会自动让有共享状态的
MCP 服务器并发执行。

某些模型可能不支持函数调用，会返回诸如 `tool call is not supported`, `function calling is not supported`, `tool use is not supported` 等错误。在大多数情况下，AstrBot 能够检测到这种错误并自动帮您去除函数调用工具。如果你发现某个模型不支持函数调用，也可在 WebUI 中关闭所有调用工具，然后再次尝试。或者更换为支持函数调用的模型。

下面是一些常见的工具调用 Demo：

![image](https://files.astrbot.app/docs/source/images/function-calling/image.png)

![image](https://files.astrbot.app/docs/source/images/function-calling/image-1.png)

## MCP

请前往此文档 [AstrBot - MCP](/use/mcp) 查看。
