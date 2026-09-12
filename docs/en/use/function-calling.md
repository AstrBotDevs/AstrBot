---
outline: deep
---

# Function Calling

## Introduction

Function calling aims to provide large language models with **the ability to invoke external tools**, enabling various Agentic functionalities.

For example, when you ask the LLM: "Help me search for information about cats", the model will call external search tools, such as search engines, and return the search results.

Currently, supported models include but are not limited to:

- GPT-5.x series
- Gemini 3.x series
- Claude 4.x series
- DeepSeek v3.2 (deepseek-chat)
- Qwen 3.x series

Mainstream models released after 2025 typically support function calling.

Commonly unsupported models include older models such as DeepSeek-R1 and Gemini 2.0 thinking-type models.

In AstrBot, tools such as web search, todo reminders, `send_message_to_user` (sending multimedia messages to the user), and `get_group_message_history` (searching the persisted message history of the current group, since v4.27.0) are provided by default. <span style="color: gray">~~web search, todo reminders, and code interpreter tools are provided by default~~ (Archived: the code interpreter has been replaced by Computer Use and the Agent sandbox environment)</span> Many plugins, such as:

- astrbot_plugin_cloudmusic
- astrbot_plugin_bilibili
- ...

also provide function calling capabilities in addition to traditional command invocation.

Tool management (enable/disable) can be done in the `Handlers` tab of the `Plugins` page in the WebUI, where you can also configure per-tool permissions.

Some models may not support function calling and will return errors such as `tool call is not supported`, `function calling is not supported`, `tool use is not supported`, etc. In most cases, AstrBot can detect these errors and automatically remove function calling tools for you. If you find that a model doesn't support function calling, you can also disable all calling tools in the WebUI and try again, or switch to a model that supports function calling.


Below are some common tool calling demos:

![image](https://files.astrbot.app/docs/source/images/function-calling/image.png)

![image](https://files.astrbot.app/docs/source/images/function-calling/image-1.png)


## MCP

Please refer to this documentation: [AstrBot - MCP](/en/use/mcp).
