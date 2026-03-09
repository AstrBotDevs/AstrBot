# Agent 执行器

Agent 执行器是 AstrBot 中用于执行 Agent 的组件。

在 v4.7.0 版本之后，我们将 Dify、Coze、阿里云百炼应用这三个提供商迁移到了 Agent 执行器层面，减少了与 AstrBot 目前功能的一些冲突。请放心，如果您从旧版本升级到 v4.7.0 版本，您无需进行任何操作，AstrBot 会自动为您迁移。此后，AstrBot 也新增了 DeerFlow Agent 执行器支持。

AstrBot 目前支持五种 Agent 执行器：

- AstrBot 内置 Agent 执行器
- Dify Agent 执行器
- Coze Agent 执行器
- 阿里云百炼应用 Agent 执行器
- DeerFlow Agent 执行器

默认情况下，AstrBot 内置 Agent 执行器为默认执行器。

## 为什么需要抽象出 Agent 执行器

在早期版本中，Dify、Coze、阿里云百炼应用这类「自带 Agent 能力」的平台，是作为普通 Chat Provider 集成进 AstrBot 的。实践下来会发现，它们和传统「只负责补全文本」的 Chat Provider 有本质差异，强行放在同一层会带来很多设计和使用上的冲突。因此，从 v4.7.0 起，我们将它们抽象为独立的 Agent 执行器（Agent Runner）。

从架构上看，可以理解为：

- Chat Provider 负责「说话」；
- Agent 执行器负责「思考 + 做事」。

Agent 执行器会调用 Chat Provider 的接口，并根据 Chat Provider 的回复，进行多轮「感知 → 规划 → 执行动作 → 观察结果 → 再规划」的循环。

Chat Provider 本质上是一个 `单轮补全接口`，输入 prompt + 历史对话 + 工具列表，输出模型回复（文本、工具调用指令等）。

而 Agent Runner 通常是一个 `循环（Loop）`，接收用户意图、上下文与环境状态，基于策略 / 模型做出规划（Plan），选择并调用工具（Act），从环境中读取结果（Observe），再次理解结果、更新内部状态，决定下一步动作，重复上述过程，直到任务完成或超时。

![image](https://files.astrbot.app/docs/source/images/use/agent-runner/agent-arch.svg)

Dify、Coze、百炼应用、DeerFlow 等平台已经内置了这个循环，如果把它们当成普通 Chat Provider，会和 AstrBot 的内置 Agent 执行器功能冲突。

## 使用

默认情况下，AstrBot 内置 Agent 执行器为默认执行器。使用默认执行器已经可以满足大部分需求，并且可以使用 AstrBot 的 MCP、知识库、网页搜索等功能。

如果你需要使用 Dify、Coze、百炼应用、DeerFlow 等平台的能力，可以创建一个 Agent 执行器，并选择相应的提供商。

## 创建 Agent 执行器

![image](https://files.astrbot.app/docs/source/images/use/agent-runner/image-1.png)

在 WebUI 中，点击「模型提供商」->「新增提供商」，选择「Agent 执行器」，选择你想接入的平台或执行器类型，填写相关信息即可。

## 更换默认 Agent 执行器

![image](https://files.astrbot.app/docs/source/images/use/agent-runner/image.png)

在 WebUI 中，点击「配置」->「Agent 执行方式」，将执行器类型更换为你刚刚创建的 Agent 执行器类型，然后选择 `XX Agent 执行器提供商 ID` 为你刚刚创建的 Agent 执行器提供商的 ID，点击保存即可。
