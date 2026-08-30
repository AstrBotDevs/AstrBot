# Agent 执行器

Agent 执行器是 AstrBot 中用于执行 Agent 的组件。

AstrBot 目前支持五种 Agent 执行器：

- AstrBot 内置 Agent 执行器
- Dify Agent 执行器
- Coze Agent 执行器
- 阿里云百炼应用 Agent 执行器
- DeerFlow Agent 执行器

默认情况下，AstrBot 内置 Agent 执行器为默认执行器。

## 为什么需要抽象出 Agent 执行器

像 Dify、Coze、阿里云百炼应用、DeerFlow 这类「自带 Agent 能力」的平台，与传统「只负责补全文本」的 Chat Provider 有本质差异。强行放在同一层会带来设计和使用上的冲突，因此 AstrBot 将它们抽象为独立的 Agent 执行器（Agent Runner）。

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

如果你需要使用 Dify、Coze、百炼应用、DeerFlow 等平台的能力，在对应配置文件中切换执行器并填写该类型的配置即可。切换执行器会使用新类型的默认配置，不会保留上一类型的参数。

## 配置 Agent 执行器

在 WebUI 中，打开「配置」->「Agent 执行方式」，选择执行器类型，然后在同页出现的该类型配置项中填写 API Key、应用 ID 等参数，点击保存即可。

内置 Agent 的对话模型、人格、压缩和工具参数也写在同一配置文件中，不再作为独立的模型提供商。
