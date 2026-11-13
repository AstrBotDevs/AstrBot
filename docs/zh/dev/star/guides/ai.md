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

判断提供商（Decision Provider）用于低延迟的结构化选择，例如是否回复、回复哪条消息或选择执行分支。先在 WebUI 的「模型提供商」→「判断」中配置提供商，插件通过 `self.context.decision` 调用，它与聊天模型互不影响。

一次请求可以同时回答多个问题。`state` 会原样传给判断模型，类型为 `str | list | dict`：

```py
from astrbot.api.provider import (
    DecisionBooleanQuestion,
    DecisionChoiceAnswer,
    DecisionChoiceQuestion,
    DecisionScoreQuestion,
)


recent_messages = [
    {"role": "user", "content": "I cannot log in; every request returns 500."},
]

answers = await self.context.decision.ask(
    {
        "should_reply": DecisionChoiceQuestion(
            instructions="Should the assistant reply to this message?",
            criteria={"reply": "Reply now", "ignore": "Stay silent"},
        ),
        "target": DecisionChoiceQuestion(
            instructions="Which message should the reply focus on?",
            criteria={"latest": "Latest message", "previous": "Previous message"},
        ),
        "needs_tool": DecisionBooleanQuestion(
            "Does this request require a tool call?"
        ),
        "severity": DecisionScoreQuestion(
            instructions="How severe is the reported problem?",
            criteria=[
                "No impact on normal use",
                "Some features fail, but a workaround exists",
                "Core features are unavailable with no workaround",
            ],
        ),
    },
    state={"messages": recent_messages},
)

should_reply = answers["should_reply"]
if (
    isinstance(should_reply, DecisionChoiceAnswer)
    and should_reply.choice == "reply"
    and should_reply.probability >= 0.7
):
    target = answers["target"]
    # 使用 target.choice 和 answers["needs_tool"].probability 执行后续业务逻辑
```

`DecisionChoiceQuestion.criteria` 是选项 ID 到选项描述的映射，与 System One 请求中的 `criteria` 对应。选择类结果的 `choice` 是选项 ID，`probabilities` 包含完整概率分布，`confidence` 是模型置信度；布尔类结果使用 `probability` 表示陈述为真的概率。主动回复阈值等业务规则由调用方决定。

返回结果按题型分别是 `DecisionChoiceAnswer`、`DecisionBooleanAnswer` 和 `DecisionScoreAnswer`，它们是三个独立的冻结数据类。`DecisionAnswer` 是这三个类的联合类型。调用 `ask()` 后，可使用 `isinstance()` 确认结果类型再读取对应字段；`choose()` 明确返回 `DecisionChoiceAnswer`，`yes_no()` 返回 `bool`。

评分类 `DecisionScoreQuestion.criteria` 是由低到高排列的 2～10 个字符串等级，等级从 0 编号。`DecisionScoreAnswer.score` 是概率加权评分，可以为小数，范围是 `0` 到 `len(criteria) - 1`；`legend` 和 `probabilities` 分别以字符串等级编号（如 `"0"`）映射到描述和概率，`confidence` 表示置信度。评分结果仅包含这四个字段。三种题型可以通过同一次 `ask()` 调用混合提交。

对于单个问题，可以使用以下快捷方法：

```py
choice = await self.context.decision.choose(
    question="Which reply strategy should be used?",
    criteria={"short": "A brief reply", "detailed": "A detailed reply"},
    state=recent_messages,
)

should_reply = await self.context.decision.yes_no(
    question="Should the assistant reply now?",
    state=recent_messages,
    threshold=0.7,
)
```

如需指定已配置的判断提供商，传入 `provider_id="provider_id"`；省略时使用默认判断提供商。提供商未配置、请求超时、连接失败、HTTP 错误、响应不是合法 JSON，或返回的选项与概率不符合请求契约时，统一抛出 `DecisionError`；底层异常详情会写入 AstrBot 日志。插件应捕获该异常并决定跳过本次判断或降级处理。

### 使用 OpenAI Decisions

除 System One 外，判断提供商也可以接入 OpenAI Decisions API（`POST /v1/decisions`）。在 WebUI「模型提供商」→「判断」中新增「OpenAI Decisions」模板，填写 API Key（支持 `$ENV_NAME` 引用环境变量）、接口地址（默认 `https://api.openai.com/v1`，自动补全 `/decisions`）和模型（模板默认 `gpt-6-luna`）。超时、总超时、最大并发、代理与自定义请求头的含义与 System One 相同。

它是独立的判断提供商，与聊天模型互不影响：配置后不会被主对话 Agent 自动调用，只有插件通过 `self.context.decision` 或 `provider_id` 显式请求时才会发送决策请求。插件代码无需改动：

```py
answers = await self.context.decision.ask(
    {
        "should_reply": DecisionChoiceQuestion(
            instructions="Should the assistant reply to this message?",
            criteria={"reply": "Reply now", "ignore": "Stay silent"},
        ),
        "severity": DecisionScoreQuestion(
            instructions="How severe is the reported problem?",
            criteria=["No impact", "Degraded", "Unavailable"],
        ),
    },
    state={"messages": recent_messages},
    provider_id="openai_decision",
)
```

请求映射：布尔题对应 `predicate`；选择题对应 `choice`，`criteria` 的选项 ID 作为 `value`、描述作为 `description`；评分题对应 `score`，等级按顺序以 `"0"`、`"1"`… 作为 `label`，与返回的 `legend` 一致。返回的 `score` 保留小数，`probabilities` 包含完整分布，`confidence` 与选中项概率相互独立。答案按问题名称匹配，与返回顺序无关。

`state` 的处理：

- `str` 或省略：作为文本输入。
- `dict`，或元素全部为 `dict` 的 `list`：作为 `input_json` 数据发送。其中的 `role`、`content`、`image_url` 等键只是普通数据，不会被解释为消息历史或图片。
- 包含其他类型元素的 `list`（如字符串列表）：序列化为 JSON 后作为文本输入发送。
- 不支持的类型、含 `NaN`/`Infinity` 或无法 JSON 序列化的值：在发送前抛出 `ValueError`。

首版不支持图片输入、消息/工具调用历史、问题内的多模态指令、提示缓存控制与 `safety_identifier`。模型对任一问题拒答（`refusal`）时，整批 `ask()` 抛出 `DecisionError`，不会当作否定、零分或空结果；`yes_no(default=...)` 的降级行为保持不变。

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
> 在 v4.5.7 时加入

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

> [!TIP]
> 在 v4.5.7 时加入

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

通过 `self.context.agent.run_turn()` 提交程序触发的输入，可以沿用目标会话的人格、历史、工具、skills 和 Agent hooks，无需自行构造消息事件或 runner。目前支持内置 Agent runtime。

```py
from astrbot.api.agents import PlainInput

run = await self.context.agent.run_turn(
    umo=event.unified_msg_origin,
    input_message=[PlainInput(text="视频分析已完成，请向用户简要说明结果。")],
)
result = await run.result()
```

`run_turn()` 在输入绑定到 runtime turn 后返回，不等待模型执行。同一 session 的输入串行排队，真正执行时读取最新历史。默认由 AstrBot 通过正常输出处理发送回复，插件无需再发送 `result.text`。`result()` 等待执行、历史保存和 Core 输出处理；取消一个等待者不会取消运行，停止运行请使用 `await run.cancel()`。

`run` 提供 turn ID、输出、取消、steer 和 follow-up 操作。`run.session` 返回只读状态快照。

Core 按当前配置档的 `agent.runtime` 选择已注册实现；使用 `ctx.agent.register_runtime(name, runtime)` 注册后，该实现可用于主代理，也可由内置 runtime 作为子代理调用。未注册的名称明确报错；Dify、Coze 等现有第三方路径继续沿用原执行方式。

`/stop` 按 UMO 向已提交的 turn 调用 `turn.request_stop()`。运行中的 turn 会调用 `AgentSession.request_stop_turn(turn)`。runtime 接受请求并负责执行收尾时返回 `True`，返回 `False` 则使用 `cancel_turn()` 和本地任务取消。排队中的 turn 直接取消。`request_stop()` 提交请求后立即返回，用 `await turn.result()` 等待收尾。

Core 传入公共 `AgentInput`：原始 `AstrMessageEvent`、权限、可选的 `plain/image/file` 内容、授权后的插件 tools/skills，以及流式输出偏好。Core 在投递前完成额外唤醒前缀的匹配和剥离，通过 `content` 传入处理后的文本，不修改原始 event。无需覆盖文本的普通平台消息可保留 `content=None`；来源附件仍保留在 event 上。SDK 调用提供显式内容。配置通过 `open_session(..., options={"config": ...})` 交给 runtime 自行解释，Core 不构造内置 `MainAgentInput`、`MainAgentBuildConfig` 或模型请求。

实现 runtime 时复用 `AgentSession.run_turn()`：Core 通过调度参数 `run_turn(input, admit=...)` 传入准入检查，与 `AgentInput` 分离。它在会话串行锁及实现提供的 `_execution_scope()` 内执行，再进入 `execute_turn()`。排队后会重新检查 AI 启用状态、权限和插件能力；不要通过重写调度绕过准入。额外的锁由 runtime 提供。可选的 `active_turn(umo)` 支持普通消息的活跃 turn 发现；未实现时返回 `None`，session 仍负责排队。内置 runtime 在自己的执行阶段构造 `ProviderRequest`、解析模型配置并调用现有模型 hooks；外部实现不需要导入 `astr_agent_runtime`。

如需自行处理模型回复，设置 `send_to_user=False`：

```py
from astrbot.api.event import MessageChain

run = await self.context.agent.run_turn(
    umo=event.unified_msg_origin,
    input_message=[PlainInput(text="请生成视频分析摘要。")],
    send_to_user=False,
)
result = await run.result()
if result.text:
    await self.context.send_message(
        event.unified_msg_origin,
        MessageChain().message(f"视频分析结果：\n{result.text}"),
    )
```

`send_to_user=False` 只跳过 Core 的自动输出呈现及平台回复装饰、自动 TTS，执行历史照常保存。工具或插件显式调用 `event.send()`、`Context.send_message()`、`send_message_to_user` 时仍然正常发送；框架不会拦截这些调用。

`events()` 支持多个独立观察者和事后重放，提供 `message.completed`、工具调用等 runtime 事件；监听不会截走平台输出或重复发送。SDK 的最终 `turn.finished` 事件在自动输出处理结束后发布。

```py
# Queue another turn in this exact conversation, inheriting the output policy.
next_run = await run.follow_up(
    input_message=[PlainInput(text="再给出三条改进建议。")],
)

# Add input to an active turn at the native runner's safe boundary.
receipt = await run.steer(
    input_message=[PlainInput(text="补充：请重点说明安全隐患。")],
)
if receipt is not None:
    consumed = await receipt
```

`follow_up()` 固定提交给原 runtime 和 conversation，配置档切换 runtime 或 UMO 切换当前对话不会改变目标。`steer()` 无法接收时返回 `None`，已接收时返回 `InputReceipt`；等待回执得到的布尔值表示输入是否实际消费并保存，不会自动转成下一轮。目前 steer 中的图片、文件以文本引用传递。

`run.session.state` 为 `idle`、`queued`、`running` 或 `closed`。快照包含 `ref`、`pending_turn_count` 和 `active_turn_id`，重新读取属性即可刷新。

Core 根据 `source_event` 或当前活跃的同 UMO 事件解析权限。没有来源事件的后台调用使用 member 权限，来源事件与目标 UMO 不一致会报错。

不要在当前 turn 的工具中等待同 session 的排队 turn 完成，这会形成互相等待。可以提交后返回，或按目的使用 steer。

## 对话管理器

### 获取会话当前的 LLM 对话历史 `get_conversation`

```py
# AstrBot v4.30.0 之前的导入方式：
# from astrbot.core.conversation_mgr import Conversation
from astrbot.api.provider import Conversation

uid = event.unified_msg_origin
conv_mgr = self.context.conversation_manager
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

conv_mgr = self.context.conversation_manager
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
