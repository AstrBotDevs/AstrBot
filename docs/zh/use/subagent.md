# Agent Handoff 与子代理编排

子代理编排允许主 Agent 通过 `transfer_to_<name>` 工具把一个明确任务交给专门的子 Agent。它适合把搜索、文件处理或某个业务域的工具收拢到独立角色中，同时让主 Agent 继续负责理解用户意图和组织最终回复。

此功能目前标记为**实验性**，建议先在非关键配置档中验证模型、工具权限和成本。

![子代理编排页面](https://files.astrbot.app/docs/source/images/subagent/image.png)

## 当前工作方式

启用编排后：

1. 主 Agent 保留自己原本可用的工具，并额外挂载每个已启用子 Agent 的 `transfer_to_*` handoff 工具。
2. 主 Agent 根据 handoff 工具描述决定是否委派，并传入任务说明；需要时还可传递图片引用，或把耗时任务作为后台任务执行。
3. 子 Agent 使用自己的系统提示词、开场对话、模型和工具集运行。
4. 同步任务的结果会返回主 Agent，由主 Agent 继续对话；后台任务完成后会重新唤醒主 Agent，以便通知用户。

![Handoff 流程](https://files.astrbot.app/docs/source/images/subagent/1.png)

> [!IMPORTANT]
> 启用子代理并不会自动移除主 Agent 的业务工具。只有同时开启“主 LLM 去重重复工具”时，系统才会从主 Agent 工具集中隐藏已经分配给子 Agent 的同名工具。未重叠的主 Agent 工具仍然保留。

## 配置步骤

在 WebUI 左侧打开 **子代理编排**。

### 1. 准备 Persona

当前页面要求每个子 Agent 绑定一个 Persona。子 Agent 会从 Persona 读取：

- 系统提示词；
- 开场对话；
- 工具列表。Persona 的工具值为“全部工具”时，子 Agent 会获得当前已启用的全部普通工具和适用的 Computer 工具，但不会获得其他 `transfer_to_*` 工具。

Persona 的 Skills 和自定义错误回复目前不会作为独立的子 Agent 配置继承。请把子 Agent 必需的行为规则写入 Persona 的系统提示词，并只授权完成职责所需的工具。

### 2. 新增子 Agent

点击“新增子代理”，填写：

- **Agent 名称**：必须以小写英文字母开头，只能包含小写字母、数字和下划线，并且全局唯一。例如 `web_search` 会生成 `transfer_to_web_search`。
- **Chat Provider（可选）**：覆盖该子 Agent 使用的聊天模型。留空时跟随当前会话的模型解析结果。
- **Persona**：提供提示词、开场对话和工具权限。
- **对主 LLM 的描述**：直接成为 handoff 工具描述。应说明何时委派、输入需要包含什么、会返回什么，不要复制冗长的 Persona 提示词。

保存后可以在卡片预览中确认主 Agent 将看到的工具名称和描述。单个子 Agent 也可以独立停用。

### 3. 决定是否工具去重

默认关闭工具去重，适合逐步试用：主 Agent 既可以直接调用工具，也可以委派。

打开“主 LLM 去重重复工具”后，凡是出现在已启用子 Agent 工具集中的同名工具都会从主 Agent 隐藏。这样能减少主 Agent 的工具 schema，但会让对应能力依赖 handoff。启用前应确认：

- 子 Agent 描述足以让模型稳定路由；
- Persona 没有意外选择“全部工具”；
- 关键工具在子 Agent 的模型上可正常调用。

## 设计建议

- 每个子 Agent 保持单一、可判断的职责，例如“查找公开资料并返回带来源摘要”。
- 描述中写清边界，避免多个子 Agent 都声称能处理同一类任务。
- 为低风险、结构化任务选择较小模型；对复杂推理或多工具任务再使用能力更强的模型。
- 工具按最小权限分配，特别是 Shell、文件写入、浏览器和外部系统操作工具。
- 当前编排是主 Agent 到子 Agent 的一层 handoff；子 Agent 工具集中会排除 handoff 工具，不应按多级递归委派来设计。

## 当前限制

- 功能仍为实验性，配置和行为可能继续调整。
- 子 Agent 不保存为独立会话历史；每次 handoff 根据本次输入、Persona 开场对话和工具执行构建上下文。
- Persona Skills 目前不会隔离并继承到子 Agent。
- 子 Agent 使用配置档中的 `agent_runner.config.misc.max_steps`、流式响应和工具超时等运行设置，没有单独的 step 上限。
