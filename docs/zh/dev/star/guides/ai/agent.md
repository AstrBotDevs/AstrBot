# Agent

通过 `ctx.agent.run_turn()` 调用现有会话的 Agent，或通过 `tool_loop_agent()` 自行组合模型、提示词和工具。以下示例用于插件的异步方法。

## 调用现有会话的 Agent {#run-session-agent}

通过 `self.context.agent.run_turn()` 向会话提交程序触发的输入。使用内置 runtime 时，会沿用该会话的人格、历史、工具、skills 和 Agent hooks，无需自行构造消息事件或 runner。

```py
from astrbot.api.agents import PlainInput

run = await self.context.agent.run_turn(
    umo=event.unified_msg_origin,
    input_message=[PlainInput(text="视频分析已完成，请向用户简要说明结果。")],
)
result = await run.result()
```

`run_turn()` 提交后即返回，不等待执行完成。同一 session 的 turn 串行执行。`await run.result()` 等待执行、历史保存和输出处理完成。AstrBot 默认发送回复，插件无需再次发送 `result.text`。

停止执行请使用 `await run.cancel()`。取消结果等待者不会停止 turn。

### 向 hooks 传递 metadata

可以通过 `metadata` 传入业务标记，让已有 hooks 识别插件触发的这一轮：

```py
run = await self.context.agent.run_turn(
    umo=event.unified_msg_origin,
    input_message=[PlainInput(text="请简短地问候用户。")],
    metadata={
        "private_companion": {
            "kind": "proactive_message",
            "attempt_id": "check-in-001",
        }
    },
)
```

在已有 hook 中，从该 hook 收到的 wakeup event 读取 metadata：

```py
metadata = event.get_extra("agent_metadata", {})
companion = metadata.get("private_companion", {})
```

请使用插件自己的命名空间和 JSON 兼容值。Metadata 会在 hooks 执行前复制到 `event.get_extra("agent_metadata")`，不会自动加入模型提示词或历史；需要传给模型的上下文应通过 hook 显式添加。

Metadata 默认为 `{}`，不会从 `source_event` 或 `follow_up()` 继承。后续 turn 需要 metadata 时，请指定目标 `session_id` 调用 `run_turn()`。

### 收集待发送消息

设置 `send_to_user=False` 后，可以通过 `run.events()` 收集待发送消息，再由插件处理和发送。在插件的异步方法中使用：

```py
from astrbot.api.agents import PlainInput, TurnStatus, chain_from_content

run = await self.context.agent.run_turn(
    umo=event.unified_msg_origin,
    input_message=[PlainInput(text="请生成视频分析摘要。")],
    send_to_user=False,
)
outputs = []
async for agent_event in run.events():
    if agent_event.type == "output.ready":
        outputs.append(agent_event.payload)

result = await run.result()
if result.status == TurnStatus.COMPLETED:
    # Review or transform the outputs before sending.
    for output in outputs:
        await self.context.send_message(
            output.target_umo, chain_from_content(output.content)
        )
```

`output.ready` 的 payload 类型为 `OutputReady`：

| 字段 | 含义 |
| --- | --- |
| `target_umo` | 消息的目标会话。 |
| `source` | `tool` 表示工具准备的消息；`reply` 表示最终回复。 |
| `content` | 有序的 `tuple[OutputComponent, ...]`，包含文本、图片、音频、视频、文件等消息组件。 |

这些事件已包含最终回复，无需再次发送 `result.text`。只需要最终回复时，可筛选 `output.source == "reply"`。`output.ready` 表示内容就绪，不代表平台投递成功。

### 继续对话与追加输入

```py
# Queue another turn in this exact conversation, inheriting the output policy.
next_run = await run.follow_up(
    input_message=[PlainInput(text="再给出三条改进建议。")],
)

# Submit steering while the current turn is still active.
receipt = await run.steer(
    input_message=[PlainInput(text="补充：请重点说明安全隐患。")],
)
if receipt is not None:
    consumed = await receipt
```

`follow_up()` 在原 runtime 和 conversation 中排队开始下一轮。`steer()` 向活跃 turn 追加输入：被拒绝时返回 `None`，接收时返回 `InputReceipt`，等待回执得到的布尔值表示输入是否已消费并保存。被拒绝的输入不会自动排队。目前 steer 中的图片、文件以文本引用传递。

内置 runtime 在一批工具结果之后，将同一批 steer 输入合为一条独立的 `user` 消息，`content` 使用按到达顺序排列的文本片段列表，不改写工具结果。如果模型直接返回普通回复，已接收的 steer 会追加在该回复之后，像后续输入一样由当前执行继续处理，不另行排队创建 turn。停止、取消、错误和步数上限仍会结束执行，剩余未消费输入的回执返回 `False`。相同 UMO 和会话内允许不同发送者 steer，但权限、输出策略和插件范围仍须与当前执行一致。

`run.session.state` 为 `idle`、`queued`、`running` 或 `closed`。快照包含 `ref`、`pending_turn_count` 和 `active_turn_id`，重新读取属性即可刷新。

Core 根据 `source_event` 或当前活跃的同 UMO 事件解析权限。没有来源事件的后台调用使用 member 权限，来源事件与目标 UMO 不一致会报错。

不要在当前 turn 的工具中等待同 session 的排队 turn 完成，这会形成互相等待。可以提交后返回，或按目的使用 steer。

### Agent Runtime 事件 {#runtime-events}

`run.events()` 产生有类型的 `RuntimeEvent` 对象，通过 `event.type` 读取事件名称、`event.payload` 读取数据。多个读者可独立重放事件，读取本身不会发送消息。

```py
from astrbot.api.agents import MessageCompleted, TextDelta

async for event in run.events():
    payload = event.payload
    if isinstance(payload, TextDelta):
        print(payload.text, end="")
    elif isinstance(payload, MessageCompleted):
        # Replace earlier deltas for this message_id with the complete content.
        print(payload.message_id, payload.content)

result = await run.result()
print(result.status, result.text)
```

| 事件 | 用途 |
| --- | --- |
| `text.delta`、`reasoning.delta` | 展示增量内容。 |
| `message.completed` | 按 `message_id` 用完整快照替换该消息的增量内容。 |
| `output.ready` | 在 `send_to_user=False` 时收集待发送消息。 |
| `tool.started/progress/finished/rejected` | 跟踪工具执行。 |
| `request.started/finished` | 跟踪提供商调用。 |
| `usage.updated` | 读取累计用量；替换上次快照，不要累加。 |
| `turn.started/prepared/finished` | 跟踪 turn 生命周期。SDK 的 `turn.finished` 在输出处理后发布。 |

`result.content` 包含最终回复，`result.text` 提取其中的纯文本。`result.usage` 提供累计用量，`result.metrics.steps` 提供执行步数。未知用量为 `None`，不等同于零；缓存命中 token 包含在输入 token 中。

接口迁移：`event.data` 改为 `event.payload`，`result.chain` 改为 `result.content`。`streaming_delta` / `llm_result` 改用 `text.delta`、`reasoning.delta` / `message.completed`，`agent_stats` 改用 `usage.updated`。从最终结果读取状态、错误和执行指标。

## 构建自定义 Agent {#build-agent}

> [!TIP]
> 本节及下文的多 Agent 编排示例适用于由插件自行配置模型、提示词、上下文和工具，构建 Agent 执行流程。若要在已有会话中触发任务，并沿用会话的人格、历史和工具配置，请使用[调用现有会话的 Agent](#run-session-agent)的方式。

使用 `tool_loop_agent()` 组合模型、提示词与工具。以下示例使用[工具定义示例](./tools.md#定义-tool)中的 `BilibiliTool`：

```py
# AstrBot v4.30.0 之前的导入方式：
# from astrbot.core.agent.tool import ToolSet
from astrbot.api import ToolSet

prov_id = await self.context.get_current_chat_provider_id(event.unified_msg_origin)
llm_resp = await self.context.tool_loop_agent(
    event=event,
    chat_provider_id=prov_id,
    prompt="搜索一下 bilibili 上关于 AstrBot 的相关视频。",
    tools=ToolSet([BilibiliTool()]),
    max_steps=30,  # Agent 最大执行步骤
    tool_call_timeout=60,  # 工具调用超时时间
)
# print(llm_resp.completion_text) # 获取返回的文本
```

`tool_loop_agent()` 方法会自动处理工具调用和大模型请求的循环，直到大模型不再调用工具或者达到最大步骤数为止。

### 示例：多 Agent 编排 {#multi-agent}

Multi-Agent（多智能体）系统将复杂应用分解为多个专业化智能体，它们协同解决问题。不同于依赖单个智能体处理每一步，多智能体架构允许将更小、更专注的智能体组合成协调的工作流程。我们使用 `agent-as-tool` 模式来实现多智能体系统。

在下面的例子中，我们定义了一个主智能体（Main Agent），它负责根据用户查询将任务分配给不同的子智能体（Sub-Agents）。每个子智能体专注于特定任务，例如获取天气信息。

![multi-agent-example-1](https://files.astrbot.app/docs/zh/dev/star/guides/multi-agent-example-1.svg)

定义 Tools:

```py
from pydantic import Field
from pydantic.dataclasses import dataclass

# AstrBot v4.30.0 之前的导入方式：
# from astrbot.core.agent.run_context import ContextWrapper
# from astrbot.core.agent.tool import FunctionTool, ToolExecResult, ToolSet
# from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.api import FunctionTool, ToolExecResult, ToolSet, logger
from astrbot.api.agents import AstrAgentContext, ContextWrapper


@dataclass
class AssignAgentTool(FunctionTool[AstrAgentContext]):
    """Main agent uses this tool to decide which sub-agent to delegate a task to."""

    name: str = "assign_agent"
    description: str = "Assign an agent to a task based on the given query"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The query to call the sub-agent with.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        # Here you would implement the actual agent assignment logic.
        # For demonstration purposes, we'll return a dummy response.
        return "Based on the query, you should assign agent 1."


@dataclass
class WeatherTool(FunctionTool[AstrAgentContext]):
    """In this example, sub agent 1 uses this tool to get weather information."""

    name: str = "weather"
    description: str = "Get weather information for a location"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "city": {
                    "type": "string",
                    "description": "The city to get weather information for.",
                },
            },
            "required": ["city"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        city = kwargs["city"]
        # Here you would implement the actual weather fetching logic.
        # For demonstration purposes, we'll return a dummy response.
        return f"The current weather in {city} is sunny with a temperature of 25°C."


@dataclass
class SubAgent1(FunctionTool[AstrAgentContext]):
    """Define a sub-agent as a function tool."""

    name: str = "subagent1_name"
    description: str = "subagent1_description"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The query to call the sub-agent with.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        ctx = context.context.context
        event = context.context.event
        logger.info(f"the llm context messages: {context.messages}")
        llm_resp = await ctx.tool_loop_agent(
            event=event,
            chat_provider_id=await ctx.get_current_chat_provider_id(
                event.unified_msg_origin
            ),
            prompt=kwargs["query"],
            tools=ToolSet([WeatherTool()]),
            max_steps=30,
        )
        return llm_resp.completion_text


@dataclass
class SubAgent2(FunctionTool[AstrAgentContext]):
    """Define a sub-agent as a function tool."""

    name: str = "subagent2_name"
    description: str = "subagent2_description"
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "The query to call the sub-agent with.",
                },
            },
            "required": ["query"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        return "I am useless :(, you shouldn't call me :("
```

然后，同样地，通过 `tool_loop_agent()` 方法调用 Agent：

```py
@filter.command("test")
async def test(self, event: AstrMessageEvent):
    umo = event.unified_msg_origin
    prov_id = await self.context.get_current_chat_provider_id(umo)
    llm_resp = await self.context.tool_loop_agent(
        event=event,
        chat_provider_id=prov_id,
        prompt="Test calling sub-agent for Beijing's weather information.",
        system_prompt=(
            "You are the main agent. Your task is to delegate tasks to sub-agents based on user queries."
            "Before delegating, use the 'assign_agent' tool to determine which sub-agent is best suited for the task."
        ),
        tools=ToolSet([SubAgent1(), SubAgent2(), AssignAgentTool()]),
        max_steps=30,
    )
    yield event.plain_result(llm_resp.completion_text)
```

