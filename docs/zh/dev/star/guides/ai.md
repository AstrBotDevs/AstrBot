# AI

AstrBot 内置了对多种大语言模型（LLM）提供商的支持，并且提供了统一的接口，方便插件开发者调用各种 LLM 服务。

您可以使用 AstrBot 提供的 LLM / Agent 接口来实现自己的智能体。

我们在 `v4.5.7` 版本之后对 LLM 提供商的调用方式进行了较大调整，推荐使用新的调用方式。新的调用方式更加简洁，并且支持更多的功能。当然，您仍然可以使用[旧的调用方式](/dev/star/plugin#ai)。

## 获取当前会话使用的聊天模型 ID

> [!TIP]
> 在 v4.5.7 时加入

```py
umo = event.unified_msg_origin
provider_id = await self.context.get_current_chat_provider_id(umo=umo)
```

## 调用大模型

> [!TIP]
> 在 v4.5.7 时加入

```py
llm_resp = await self.context.llm_generate(
    chat_provider_id=provider_id,  # 聊天模型 ID
    prompt="Hello, world!",
)
# print(llm_resp.completion_text) # 获取返回的文本
```

## 结构化判断

判断提供商用于是否回复、选择执行分支等任务。先在 WebUI **模型提供商 → 判断** 中配置提供商，再通过 `self.context.decision` 调用。

```py
should_reply = await self.context.decision.yes_no(
    question="Should the assistant reply to this message?",
    state="I cannot log in; every request returns 500.",
    threshold=0.7,
)

strategy = await self.context.decision.choose(
    question="Which reply strategy should be used?",
    criteria={"short": "A brief reply", "detailed": "A detailed reply"},
    state="The user asks for step-by-step troubleshooting.",
)
print(strategy.choice)
```

`yes_no()` 返回 `bool`，当肯定概率达到 `threshold` 时为 `True`；`choose()` 返回 `DecisionChoiceAnswer`，通过 `.choice` 读取选项值。

`state` 提供判断所需的上下文，支持文本、列表或字典。默认使用当前判断提供商，也可传入 `provider_id` 指定。

需要一次回答多个问题时，调用 `ask({问题名: 问题对象}, state=...)`，结果按问题名返回。以下类型从 `astrbot.api.provider` 导入：

| 问题类型 | 配置 | 返回类型及主要字段 |
| --- | --- | --- |
| `DecisionBooleanQuestion` | `instructions`：待判断的陈述。 | `DecisionBooleanAnswer.probability`：陈述为真的概率。 |
| `DecisionChoiceQuestion` | `instructions` 和 `criteria`：选项 ID 到描述的映射。 | `DecisionChoiceAnswer.choice`：选中的选项 ID。 |
| `DecisionScoreQuestion` | `instructions` 和 `criteria`：由低到高的 2～10 个等级描述。 | `DecisionScoreAnswer.score`：从 0 到等级数减 1 的评分，可为小数。 |

提供商不可用、请求失败或返回结果无效时抛出 `DecisionError`。`yes_no()` 可通过 `default=False` 在这类错误发生时返回默认值。

## 定义 Tool

Tool 是大语言模型调用外部工具的能力。

```py
from pydantic import Field
from pydantic.dataclasses import dataclass

# AstrBot v4.30.0 之前的导入方式：
# from astrbot.core.agent.run_context import ContextWrapper
# from astrbot.core.agent.tool import FunctionTool, ToolExecResult
# from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.api import FunctionTool, ToolExecResult
from astrbot.api.agents import AstrAgentContext, ContextWrapper


@dataclass
class BilibiliTool(FunctionTool[AstrAgentContext]):
    name: str = "bilibili_videos"  # 工具名称
    description: str = "A tool to fetch Bilibili videos."  # 工具描述
    parameters: dict = Field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "keywords": {
                    "type": "string",
                    "description": "Keywords to search for Bilibili videos.",
                },
            },
            "required": ["keywords"],
        }
    )

    async def call(
        self, context: ContextWrapper[AstrAgentContext], **kwargs
    ) -> ToolExecResult:
        return "1. 视频标题：如何使用AstrBot\n视频链接：xxxxxx"
```

## 注册 Tool 到 AstrBot

在上面定义好 Tool 之后，如果你需要实现的功能是让用户在使用 AstrBot 进行对话时自动调用该 Tool，那么你需要在插件的 __init__ 方法中将 Tool 注册到 AstrBot 中：

```py
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # >= v4.5.1 使用：
        self.context.add_llm_tools(BilibiliTool(), SecondTool(), ...)

        # < v4.5.1 之前使用：
        tool_mgr = self.context.provider_manager.llm_tools
        tool_mgr.func_list.append(BilibiliTool())
```

> [!WARNING]
> `context.register_llm_tool()` 已被弃用，请勿在新插件中使用。
>
> 如需通过该方法注册（旧插件兼容），`func_args` 必须是 **字典列表**，格式为：
> ```py
> func_args = [{"type": "string", "name": "arg_name", "description": "参数描述"}, ...]
> ```
> 传入字符串列表或其他格式会导致 `AttributeError: 'str' object has no attribute 'pop'`。

### 通过装饰器定义 Tool 和注册 Tool

除了上述的通过 `@dataclass` 定义 Tool 的方式之外，你也可以使用装饰器的方式注册 tool 到 AstrBot。请务必按照以下格式编写一个工具（包括函数注释，AstrBot 会解析该函数注释，请务必将注释格式写对）：

```py{3,4,5,6,7}
@filter.llm_tool(name="get_weather")  # 如果 name 不填，将使用函数名
async def get_weather(
    self, event: AstrMessageEvent, location: str
) -> MessageEventResult:
    """获取天气信息。

    Args:
        location(string): 地点
    """
    resp = self.get_weather_from_api(location)
    yield event.plain_result("天气信息: " + resp)
```

在 `location(string): 地点` 中，`location` 是参数名，`string` 是参数类型，`地点` 是参数描述。

支持的参数类型有 `string`, `number`, `object`, `boolean`, `array`。在 v4.5.7 之后，支持对 `array` 类型参数指定子类型，例如 `array[string]`。

> [!WARNING]
> **`Args:` 段是必须的，且格式不能写错。**
>
> `@filter.llm_tool` 装饰器通过解析函数的 docstring 来生成工具的参数 schema，**不会**读取函数签名中的类型注解。如果 docstring 缺少 `Args:` 段，或格式不符合 `参数名(类型): 描述` 的规范，框架生成的参数 schema 将为空，LLM 传入的参数会被静默丢弃，最终导致函数因缺少参数而报错。
>
> 此外，装饰器**不支持**通过 `parameters=...` 显式传入参数 schema，该写法会被忽略。如需手动控制 schema，请使用上方的 `@dataclass` + `add_llm_tools()` 方式。

## 调用 Agent

> [!TIP]
> 本节及下文的 Multi-Agent 示例适用于由插件自行配置模型、提示词、上下文和工具，构建 Agent 执行流程。若要在已有会话中触发任务，并沿用会话的人格、历史和工具配置，请使用[在现有会话中运行 Agent](#在现有会话中运行-agent)的方式。

Agent 可以被定义为 system_prompt + tools + llm 的结合体，可以实现更复杂的智能体行为。

在上面定义好 Tool 之后，可以通过以下方式调用 Agent：

```py
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

## Multi-Agent

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

## 在现有会话中运行 Agent

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

`run.session.state` 为 `idle`、`queued`、`running` 或 `closed`。快照包含 `ref`、`pending_turn_count` 和 `active_turn_id`，重新读取属性即可刷新。

Core 根据 `source_event` 或当前活跃的同 UMO 事件解析权限。没有来源事件的后台调用使用 member 权限，来源事件与目标 UMO 不一致会报错。

不要在当前 turn 的工具中等待同 session 的排队 turn 完成，这会形成互相等待。可以提交后返回，或按目的使用 steer。

## Agent Runtime 事件 {#runtime-events}

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

## 自定义 Agent runtime {#custom-agent-runtimes}

通过 `ctx.agent.register_runtime(name, runtime)` 注册实现，在配置档的 `agent.runtime` 或专用 Agent 配置中选择该名称。注册的 runtime 可用于主代理和子代理。

实现 `AgentRuntime` 来创建或恢复 `AgentSession`。输入包含来源事件、权限、授权后的工具与技能，以及可选的 `PlainInput`、`ImageInput` 或 `FileInput` 内容。运行配置通过 `open_session(..., options={"config": ...})` 传入。

复用 `AgentSession.run_turn()`，实现 `execute_turn()`，使排队任务在执行前经过 Core 准入检查。可选的 `active_turn(umo)` 用于发现普通消息可追加输入的活跃 turn。若需协作式处理 `/stop`，实现 `request_stop_turn()`，仅在 runtime 负责收尾时返回 `True`，否则会使用取消机制。

按实际执行情况发布类型化事件，返回 `TurnResult`，并将 session 的 `runtime_name` 设为注册名称。没有事件订阅者时，也必须正常执行和保存历史。

## 对话管理器

通过 `self.context.conversations` 创建、读取、更新、切换和删除对话。`self.context.conversation_manager` 保留为兼容别名。`Conversation.history` 是包含模型消息的 JSON 字符串。

`_no_save` 会将消息或内容片段排除在后续模型上下文之外，但不会阻止原文保存。

接口迁移：

- 将 `event.conversation_events` 和 `get_conversation_events()` 替换为 `append_message()` 或 `append_plugin_event()`。
- 将 `update_conversation_title()` 和 `update_conversation_persona_id()` 替换为 `update_conversation(..., title=...)` 和 `update_conversation(..., persona_id=...)`。
- 平台历史关联中的 `llm_checkpoint_id` 改用 `turn_id` 和 `context_event_id`。

### 追加模型消息 `append_message`

```py
conversations = self.context.conversations
message_id = await conversations.append_message(
    "用户偏好简洁的回答。",
    cid=target_cid,
)
```

`content` 接受文本或 AstrBot 的 `ContentPart` 对象列表：

```py
from astrbot.core.agent.message import ImageURLPart, TextPart

await conversations.append_message(
    [
        TextPart(text="请描述这张图片。"),
        ImageURLPart(
            image_url=ImageURLPart.ImageURL(url="https://example.com/image.png")
        ),
    ],
    cid=target_cid,
)
```

消息以 `role="user"` 保存并进入后续上下文，不会修改正在运行的 Agent 的上下文。返回值是已保存的消息 ID；可传入 `message_id` 标识同一次提交的重试。

### 追加插件自定义事件 `append_plugin_event`

```py
event_id = await conversations.append_plugin_event(
    event_type="my_plugin.retrieval_completed",
    data={"document_ids": ["document-1"]},
    cid=target_cid,
)
```

插件事件与对话一起保存，不会进入模型上下文。`event_type` 建议使用插件名称前缀，`data` 必须是可 JSON 序列化的字典。返回值是已保存的事件 ID；可传入 `event_id` 标识同一次提交的重试。

无需事件历史的可变状态可使用[插件 KV 存储](./storage.md)。按对话区分时，将 `cid` 放入 key。

两个追加接口都必须传入已有对话的 `cid`，无效或不存在时抛出 `ValueError`。它们不会启动 Agent turn。

修改当前执行的上下文，请编辑相应 hook 的 `ProviderRequest.contexts` 或运行时消息列表。直接调用对话写入接口（包括 `update_conversation()` 和 `add_message_pair()`）不会更新正在运行的 Agent 上下文；并发修改已保存的历史可能触发 `ConversationConflictError`。

### 获取会话当前的 LLM 对话历史 `get_conversation`

```py
# AstrBot v4.30.0 之前的导入方式：
# from astrbot.core.conversation_mgr import Conversation
from astrbot.api.provider import Conversation

uid = event.unified_msg_origin
conv_mgr = self.context.conversations
curr_cid = await conv_mgr.get_curr_conversation_id(uid)
conversation = await conv_mgr.get_conversation(uid, curr_cid)  # Conversation
```

::: details Conversation 类型定义

```py
@dataclass
class Conversation:
    """The conversation entity representing a chat session."""

    platform_id: str
    """The platform ID in AstrBot"""
    user_id: str
    """The user ID associated with the conversation."""
    cid: str
    """The conversation ID, in UUID format."""
    history: str = ""
    """The conversation history as a string."""
    title: str | None = ""
    """The title of the conversation. For now, it's only used in WebChat."""
    persona_id: str | None = ""
    """The persona ID associated with the conversation."""
    created_at: int = 0
    """The timestamp when the conversation was created."""
    updated_at: int = 0
    """The timestamp when the conversation was last updated."""
```

:::

### 快速添加 LLM 记录到对话 `add_message_pair`

```py
# AstrBot v4.30.0 之前的导入方式：
# from astrbot.core.agent.message import AssistantMessageSegment, UserMessageSegment, TextPart
from astrbot.api.agents import (
    AssistantMessageSegment,
    UserMessageSegment,
    TextPart,
)

conv_mgr = self.context.conversations
provider_id = await self.context.get_current_chat_provider_id(event.unified_msg_origin)
curr_cid = await conv_mgr.get_curr_conversation_id(event.unified_msg_origin)
user_msg = UserMessageSegment(content=[TextPart(text="hi")])
llm_resp = await self.context.llm_generate(
    chat_provider_id=provider_id,  # 聊天模型 ID
    contexts=[
        user_msg
    ],  # 当未指定 prompt 时，使用 contexts 作为输入；同时指定 prompt 和 contexts 时，prompt 会被添加到 LLM 输入的最后
)
await conv_mgr.add_message_pair(
    cid=curr_cid,
    user_message=user_msg,
    assistant_message=AssistantMessageSegment(
        content=[TextPart(text=llm_resp.completion_text)]
    ),
)
```

### 主要方法

#### `new_conversation`

- __Usage__  
  在当前会话中新建一条对话，并自动切换为该对话。
- __Arguments__  
  - `unified_msg_origin: str` – 形如 `platform_name:message_type:session_id`  
  - `platform_id: str | None` – 平台标识，默认从 `unified_msg_origin` 解析  
  - `content: list[dict] | None` – 初始历史消息  
  - `title: str | None` – 对话标题  
  - `persona_id: str | None` – 绑定的 persona ID
- __Returns__  
  `str` – 新生成的 UUID 对话 ID

#### `switch_conversation`

- __Usage__  
  将会话切换到指定的对话。
- __Arguments__  
  - `unified_msg_origin: str`  
  - `conversation_id: str`
- __Returns__  
  `None`

#### `delete_conversation`

- __Usage__  
  删除会话中的某条对话；若 `conversation_id` 为 `None`，则删除当前对话。
- __Arguments__  
  - `unified_msg_origin: str`  
  - `conversation_id: str | None`
- __Returns__  
  `None`

#### `get_curr_conversation_id`

- __Usage__  
  获取当前会话正在使用的对话 ID。
- __Arguments__  
  - `unified_msg_origin: str`
- __Returns__  
  `str | None` – 当前对话 ID，不存在时返回 `None`

#### `get_conversation`

- __Usage__  
  获取指定对话的完整对象；若不存在且 `create_if_not_exists=True` 则自动创建。
- __Arguments__  
  - `unified_msg_origin: str`  
  - `conversation_id: str`  
  - `create_if_not_exists: bool = False`
- __Returns__  
  `Conversation | None`

#### `get_conversations`

- __Usage__  
  拉取用户或平台下的全部对话列表。
- __Arguments__  
  - `unified_msg_origin: str | None` – 为 `None` 时不过滤用户  
  - `platform_id: str | None`
- __Returns__  
  `List[Conversation]`

#### `update_conversation`

- __Usage__  
  更新对话的标题、历史记录或 persona_id。
- __Arguments__  
  - `unified_msg_origin: str`  
  - `conversation_id: str | None` – 为 `None` 时使用当前对话  
  - `history: list[dict] | None`  
  - `title: str | None`  
  - `persona_id: str | None`
- __Returns__  
  `None`

## 人格设定管理器

`PersonaManager` 负责统一加载、缓存并提供所有人格（Persona）的增删改查接口，同时兼容 AstrBot 4.x 之前的旧版人格格式（v3）。  
初始化时会自动从数据库读取全部人格，并生成一份 v3 兼容数据，供旧代码无缝使用。

```py
persona_mgr = self.context.persona_manager
```

### 主要方法

#### `get_persona`

- __Usage__
  获取根据人格 ID 获取人格数据。
- __Arguments__
  - `persona_id: str` – 人格 ID
- __Returns__
  `Persona` – 人格数据，若不存在则返回 None
- __Raises__
  `ValueError` – 当不存在时抛出

#### `get_all_personas`

- __Usage__  
  一次性获取数据库中所有人格。
- __Returns__  
  `list[Persona]` – 人格列表，可能为空

#### `create_persona`

- __Usage__  
  新建人格并立即写入数据库，成功后自动刷新本地缓存。
- __Arguments__  
  - `persona_id: str` – 新人格 ID（唯一）  
  - `system_prompt: str` – 系统提示词  
  - `begin_dialogs: list[str]` – 可选，开场对话（偶数条，user/assistant 交替）  
  - `tools: list[str]` – 可选，允许使用的工具列表；`None`=全部工具，`[]`=禁用全部
- __Returns__  
  `Persona` – 新建后的人格对象
- __Raises__  
  `ValueError` – 若 `persona_id` 已存在

#### `update_persona`

- __Usage__  
  更新现有人格的任意字段，并同步到数据库与缓存。
- __Arguments__  
  - `persona_id: str` – 待更新的人格 ID  
  - `system_prompt: str` – 可选，新的系统提示词  
  - `begin_dialogs: list[str]` – 可选，新的开场对话  
  - `tools: list[str]` – 可选，新的工具列表；语义同 `create_persona`
- __Returns__  
  `Persona` – 更新后的人格对象
- __Raises__  
  `ValueError` – 若 `persona_id` 不存在

#### `delete_persona`

- __Usage__  
  删除指定人格，同时清理数据库与缓存。
- __Arguments__  
  - `persona_id: str` – 待删除的人格 ID
- __Raises__  
  `ValueError` – 若 `persona_id` 不存在

#### `get_default_persona_v3`

- __Usage__  
  根据当前会话配置，获取应使用的默认人格（v3 格式）。  
  若配置未指定或指定的人格不存在，则回退到 `DEFAULT_PERSONALITY`。
- __Arguments__  
  - `umo: str | MessageSession | None` – 会话标识，用于读取用户级配置
- __Returns__  
  `Personality` – v3 格式的默认人格对象

::: details Persona / Personality 类型定义

```py
class Persona(SQLModel, table=True):
    """Persona is a set of instructions for LLMs to follow.

    It can be used to customize the behavior of LLMs.
    """

    __tablename__ = "personas"

    id: int = Field(primary_key=True, sa_column_kwargs={"autoincrement": True})
    persona_id: str = Field(max_length=255, nullable=False)
    system_prompt: str = Field(sa_type=Text, nullable=False)
    begin_dialogs: Optional[list] = Field(default=None, sa_type=JSON)
    """a list of strings, each representing a dialog to start with"""
    tools: Optional[list] = Field(default=None, sa_type=JSON)
    """None means use ALL tools for default, empty list means no tools, otherwise a list of tool names."""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column_kwargs={"onupdate": datetime.now(timezone.utc)},
    )

    __table_args__ = (
        UniqueConstraint(
            "persona_id",
            name="uix_persona_id",
        ),
    )


class Personality(TypedDict):
    """LLM 人格类。

    在 v4.0.0 版本及之后，推荐使用上面的 Persona 类。并且， mood_imitation_dialogs 字段已被废弃。
    """

    prompt: str
    name: str
    begin_dialogs: list[str]
    mood_imitation_dialogs: list[str]
    """情感模拟对话预设。在 v4.0.0 版本及之后，已被废弃。"""
    tools: list[str] | None
    """工具列表。None 表示使用所有工具，空列表表示不使用任何工具"""
```

:::
