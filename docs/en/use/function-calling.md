---
outline: deep
---

# Function Calling

## Introduction

Function calling aims to provide large language models with **the ability to invoke external tools**, enabling various Agentic functionalities.

For example, when you ask the LLM: "Help me search for information about cats", the model will call external search tools, such as search engines, and return the search results.

Here is the revised text, updated to reflect your new content while maintaining a formal documentation tone:

Currently, supported models include but are not limited to:

- GPT-5.x series
- Gemini 3.x series
- Claude 4.x series
- DeepSeek v3.2 (deepseek-chat)
- Qwen 3.x series

Mainstream models released after 2025 typically support function calling.

Commonly unsupported models include older models such as DeepSeek-R1 and Gemini 2.0 thinking-type models.

In AstrBot, tools such as web search, todo reminders, and Agent / sandbox-related toolchains can be exposed for function calling. Many plugins, such as:

- astrbot_plugin_cloudmusic
- astrbot_plugin_bilibili
- ...

In addition to providing traditional command invocation, also offer function calling capabilities.

Tool management (enable/disable) can be done in the WebUI.

## Native parallel tool execution

AstrBot can execute independent function calls from the same model turn in
parallel. This feature is disabled by default. Enable the global switch in the
WebUI tool panel, then explicitly allow individual tools. Tools with side
effects, direct user delivery, handoffs, background tasks, or serial-only
policies cannot be enabled.

Results are written back to the model in call order even when execution
finishes out of order. MCP tools use a per-server concurrency limit (default
one), so enabling a tool does not automatically make a stateful MCP server
concurrent.

Some models may not support function calling and will return errors such as `tool call is not supported`, `function calling is not supported`, `tool use is not supported`, etc. In most cases, AstrBot can detect these errors and automatically remove function calling tools for you. If you find that a model doesn't support function calling, you can also disable all calling tools in the WebUI and try again, or switch to a model that supports function calling.

Below are some common tool calling demos:

![image](https://files.astrbot.app/docs/source/images/function-calling/image.png)

![image](https://files.astrbot.app/docs/source/images/function-calling/image-1.png)

## MCP

Please refer to this documentation: [AstrBot - MCP](/en/use/mcp).
