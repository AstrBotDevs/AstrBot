# 内置 Agent 执行器

默认情况下，AstrBot 内置 Agent 执行器为默认执行器，您不用进行任何配置，即可使用 AstrBot 的强大的内置 Agent 执行器。`✨ 接入模型服务` 中就是在配置 `内置 Agent 执行器` 的 AI 提供商。

![image](https://files.astrbot.app/docs/source/images/astrbot-agent-runner/image.png)

在内置 Agent 执行器下，您可以使用 AstrBot 的 [MCP 服务器](/use/mcp)、[知识库](/use/knowledge-base)、[网页搜索](/use/websearch)、人格功能。


## 动态工具发现

在 WebUI 打开「配置文件」→「AI」→「其他配置」，将「工具调用模式」设为 **Dynamic（按需加载）** 并保存。配置项为 `agent.config.misc.tool_schema_mode: dynamic`。此模式需要支持 Function Calling 的对话模型。

模型从搜索工具开始。它可以按任务搜索本次运行的内置工具、插件工具和已连接的 MCP 工具。每次搜索最多加载三个匹配项，完整工具定义会在下一轮提供，模型可继续搜索。例如，连接提供 Pull Request 查询的 GitHub MCP Server 后，可以直接问「这个仓库有哪些待审阅的 PR？」。

Persona、会话插件配置和内置能力开关仍决定候选工具。被找到的工具调用时仍须通过权限和参数检查。对话的下一次 Agent 运行会重新选择工具。搜索会增加模型请求轮次，适合工具数量较多的配置。

默认的 **Full（完整参数）** 每轮提供完整定义。**Skills-like（两阶段）** 先提供全部工具的名称和描述，再请求选定工具的参数。实现与适用范围见[动态工具发现设计](../../dev/dynamic-tool-discovery.md)。
