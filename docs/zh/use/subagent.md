# Agent Handsoff 与 Subagent

SubAgent 编排是 AstrBot 提供的一种高级 Agent 组织方式。它允许你将复杂的任务分解给多个专门的子 Agent（SubAgent）来完成，从而降低主 Agent 的 Prompt 长度，提高任务执行的成功率。

在 v4.14.0 引入，目前是**实验性功能**，未稳定。

![](https://files.astrbot.app/docs/source/images/subagent/image.png)

## 动机

在传统的架构中，所有的工具（Tools）都直接挂载在主 Agent 上。当工具数量较多时，会带来以下问题：
1. **Prompt 爆炸**：主 Agent 需要在 System Prompt 中包含所有工具的描述，导致上下文占用过多。
2. **调用失误**：面对大量工具，LLM 容易混淆工具用途或产生错误的调用参数。
3. **逻辑复杂**：主 Agent 既要负责对话，又要负责组织和调用大量工具，负担过重。

通过 SubAgent 编排，主 Agent 仅负责与用户对话以及**任务委派**。具体的工具调用由专门的 SubAgent 负责。

## 工作原理

1. **主 Agent 委派**：开启 SubAgent 模式后，主 Agent 只能看到一系列名为 `transfer_to_<subagent_name>` 的委派工具。
2. **任务移交**：当主 Agent 认为需要执行某项任务时，它会调用对应的委派工具，将任务描述传递给 SubAgent。
3. **子 Agent 执行**：SubAgent 接收到任务后，使用其挂载的工具进行操作，并将结果整理后回传给主 Agent。
4. **结果反馈**：主 Agent 收到 SubAgent 的执行结果，继续与用户对话。

![](https://files.astrbot.app/docs/source/images/subagent/1.png)

## 配置方法

在 AstrBot WebUI 中，点击左侧导航栏的 **SubAgent 编排**。

### 1. 启用 SubAgent 模式

在页面顶部开启“启用 SubAgent 编排”。

### 2. 创建 SubAgent

点击“新增 SubAgent”按钮：

- **Agent 名称**：用于生成委派工具名（如 `transfer_to_weather`）。建议使用英文小写和下划线。
- **选择 Persona**：选择一个预设的 Persona，即人格，作为该子 Agent 的基础性格、行为指导和可以使用的 Tools 集合。你可以在“人格设定”页面创建和管理 Persona。
- **对主 LLM 的描述**：这段描述会告诉主 Agent 这个子 Agent 擅长做什么，以便主 Agent 准确委派。
- **分配工具**：选择该子 Agent 可以调用的工具。
- **Provider 覆盖（可选）**：你可以为特定的子 Agent 指定不同的模型提供商。例如，主 Agent 使用 GPT-4o，而负责简单查询的子 Agent 使用 GPT-4o-mini 以节省成本。

## 最佳实践

- **职责单一**：每个 SubAgent 应该只负责一类相关的任务（如：搜索、文件处理、智能家居控制）。
- **清晰的描述**：给主 Agent 的描述应当简洁明了，突出该子 Agent 的核心能力。
- **分层管理**：对于极其复杂的任务，可以考虑多级委派（如果需要）。

## 已知问题

SubAgent 系统目前是**实验性功能**，未稳定。

1. 目前无法隔离人格的 Skills。
2. 子 Agent 的对话历史暂时不会被保存。
