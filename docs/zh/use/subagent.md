# 子代理 {#agent-handsoff-与-subagent}

子代理是 AstrBot **内置 AI** 的委派能力。主 Agent 可以继续与用户交流，同时把任务交给具有独立上下文的后台 worker。无需安装或启用额外插件。

## 配置入口

进入 **内置 AI → 子代理**，打开 **启用子代理编排**，配置后点击 **保存**。这里管理全局子代理配置，保存后立即生效。

| 设置 | 说明 |
| --- | --- |
| 每会话并发数 | 同一会话同时执行的 worker 数量，默认 3。其余任务等待执行。 |
| 任务超时 | 包含等待执行的时间，默认 600 秒。 |
| 每轮最大步数 | 默认 30，且不超过主 Agent 的步数上限。 |

![子代理配置页面](images/subagent-create-zh.png)

## 专家模板

专家模板提供名称、用途说明、可选的模型提供商以及人格设置。名称必须以小写英文字母开头，只能包含小写字母、数字和下划线，最多 64 个字符。

选择人格后，使用该人格的系统提示词、工具和预设对话。也可以不选择人格，直接配置系统提示词和工具。空工具列表表示不使用工具；选择全部可用工具时，仍应用工具启用状态、插件范围和执行权限。

模型提供商留空时跟随当前会话。没有指定专家模板时，主 Agent 可以创建通用 worker，使用本轮可委派的工具。worker 不继承主 Agent 的完整聊天历史，任务说明需要包含必要背景和约束。

主 Agent 的 system prompt 会列出可用专家的名称和用途，以及可选的模型提供商。`spawn_agent` 的工具定义保持固定，不包含专家目录或动态枚举。调用时才读取所选专家的当前配置并创建 worker；专家完整的人格提示词和预设对话用于该 worker。

## 执行与继续对话

`spawn_agent` 建立 agent runtime 会话后返回 agent ID，不等待模型任务完成。主 Agent 可以通过 `list_agents` 查看状态、`wait_agent` 等待结果、`get_agent_result` 读取结果、`send_message` 追加指令，或通过 `cancel_agent` 取消单个任务。

`spawn_agent` 和 `send_message` 都使用 `messages` 数组，组件格式与 `send_message_to_user` 一致。这两个工具目前支持 `plain`（`text`）、`image` 和 `file`（`path` 或 `url`）。首次委派的图片作为模型图片输入，文件作为可供工具读取的引用；不会自动附带原用户消息中的图片。内置 runtime 的追加指令暂时统一转成文本，保留图片和文件的引用，不作为新的多模态输入；其他 runtime 接收原始结构化内容。

```json
{
  "template": "researcher",
  "messages": [
    {"type": "plain", "text": "分析这张图，并参考报告"},
    {"type": "image", "path": "chart.png"},
    {"type": "file", "path": "report.pdf"}
  ]
}
```

图片的相对路径从当前会话工作目录解析，也支持权限范围内的本地绝对路径和 sandbox 文件路径。`send_message` 使用相同的 `messages`，并额外指定目标 `agent_id`。

完成结果绑定直接父代理的 runtime/session。通知任务先调用父代理活跃 turn 的 `steer()`，独立等待其确认消费，子代理任务本身无需等待通知完成。被拒绝或未消费的输入通过正常消息流水线排队，并明确指定原父会话；UMO 当前 conversation 的切换不会改变投递目标。结果正文直接放入本次输入，不再通过单独的 step-start 注入或投递 checkpoint 处理。追加指令会进入正在执行的 worker，或沿用其私有历史开始下一轮。worker 不能继续创建子代理。

页面下方的 **执行进度** 展示任务状态、完成步数、结果和错误。点击 worker 可以查看执行记录。专家模板的修改不会改变已经启动的任务。

## 持久化与恢复

agent 的公共 ID、runtime 类型、runtime session ID、直接父会话引用和每次输入的执行结果按 UMO 和主 conversation 持久化。同一个 conversation 内的用户共享子代理；对话隔离沿用主会话的 UMO/conversation 划分，不再按发送者额外隔离。每条输入使用其调用者自己的身份和权限，发送者信息仅作为元数据保留。私有对话历史由对应 runtime 保存。重启时，未完成和排队中的输入均标记为已中断，不自动执行；检查中断记录后，可通过 `send_message` 沿用同一会话发送新的指令。内置 runtime 保留完整步骤，正在执行的工具不会重放。切换主 conversation 后，结果仍绑定原父会话；父会话已删除或停止时不会唤醒。

## Agent runtime

内置 `astrbot` runtime 管理原生会话、历史、hooks、模型执行和内置能力。主代理与 worker 使用相同的 session/turn 接口；原生 tool loop 是其内部实现。Core 负责消息输入前处理和输出呈现。公共子代理服务管理公共 ID、已接受任务、并发配额、超时和结果通知，不直接读写 runtime 的私有历史存储；投递确认通过父 session 提供的公共历史视图完成。

Runtime 适配器通过 `AgentInput.content` 接收有类型的输入：`PlainInput`、`ImageInput`、`FileInput` 分别保持 `plain`、`image`、`file` 的语义。这些是不可变的数据对象，不包含 IM 协议序列化或媒体下载方法。工具请求和任务存储继续使用原有的 `messages` JSON 格式，在进入 runtime 时转换为内容对象。

`AgentRuntime` 创建或恢复 `AgentSession`。`session.run_turn(input)` 返回独立执行的 turn，提供可重复读取的 `events()`、`result()`、`cancel()`、排队开始新一轮的 `follow_up()`，以及可选的安全边界 `steer()`。输出消费者或结果等待者被取消不会自动取消执行；流水线停止时，由调用方明确取消该 turn。

扩展实现可以通过 `ctx.subagents.register_runtime(name, runtime)` 注册，由 `spawn_agent` 的 `runtime` 参数选择。默认值为 `astrbot`。本阶段不包含 ACP runtime 或持续实时语音会话；现有第三方主代理执行路径保持原样。

`list_agents` 返回每个 agent 的 `agent_id`、`runtime`，以及通过 `conversation_id` 字段提供的 runtime 私有会话 ID。`send_message` 根据 agent ID 找回 runtime 和会话。`owner_conversation_id` 单独表示所属主会话。

## 入口与接口

管理功能统一位于 **内置 AI → 子代理**，对应 `/subagent`。原插件扩展页面中的专家管理和执行进度合并到这里。

原生 API 使用 `/api/v1/subagents/config`、`/api/v1/subagents/available-tools` 和 `/api/v1/subagents/runtime`，需要 `config` 权限。兼容的 Dashboard 配置入口 `/api/subagent/*` 保留。
