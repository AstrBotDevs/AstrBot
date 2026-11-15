# Agents

Use `ctx.agent.run_turn()` to invoke an existing conversation’s Agent, or `tool_loop_agent()` to assemble your own model, prompt, and tools. Use the examples in an async plugin method.

## Run an Agent in an Existing Conversation {#run-session-agent}

Use `self.context.agent.run_turn()` to submit programmatic inputs to a conversation. With the built-in runtime, turns use that conversation’s persona, history, tools, skills, and Agent hooks. Plugins do not need to construct events or runners.

```py
from astrbot.api.agents import PlainInput

run = await self.context.agent.run_turn(
    umo=event.unified_msg_origin,
    input_message=[PlainInput(text="Video analysis is complete. Explain the result briefly.")],
)
result = await run.result()
```

`run_turn()` submits a turn without waiting for completion. Turns in the same session execute serially. `await run.result()` waits for execution, history persistence, and output handling. AstrBot sends replies by default; do not send `result.text` again.

Use `await run.cancel()` to stop execution. Cancelling a result waiter does not stop the turn.

### Pass metadata to hooks

Pass `metadata` to identify a plugin-triggered turn in existing hooks:

```py
run = await self.context.agent.run_turn(
    umo=event.unified_msg_origin,
    input_message=[PlainInput(text="Check in with the user briefly.")],
    metadata={
        "private_companion": {
            "kind": "proactive_message",
            "attempt_id": "check-in-001",
        }
    },
)
```

Inside an existing hook, read the metadata from that hook's wakeup event:

```py
metadata = event.get_extra("agent_metadata", {})
companion = metadata.get("private_companion", {})
```

Use a plugin namespace and JSON-compatible values. Metadata is copied into `event.get_extra("agent_metadata")` before hooks run. It is not added to the model prompt or history; add model context explicitly through a hook if needed.

Metadata defaults to `{}` and is not inherited from `source_event` or by `follow_up()`. To pass metadata to another turn, call `run_turn()` with the target `session_id`.

### Collect messages before sending

Set `send_to_user=False` to collect prepared messages through `run.events()`, then process and send them from your plugin. Use this example inside an async plugin method:

```py
from astrbot.api.agents import PlainInput, TurnStatus, chain_from_content

run = await self.context.agent.run_turn(
    umo=event.unified_msg_origin,
    input_message=[PlainInput(text="Summarize the video analysis.")],
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

The `output.ready` payload is an `OutputReady` instance:

| Field | Meaning |
| --- | --- |
| `target_umo` | Destination conversation. |
| `source` | `tool` for a message prepared by a tool; `reply` for the final reply. |
| `content` | An ordered `tuple[OutputComponent, ...]` containing text, images, audio, video, files, and other message components. |

These events already include the final reply; do not send `result.text` again. To keep only the final reply, filter on `output.source == "reply"`. An `output.ready` event means content is prepared, not that the platform has received it.

### Continue or steer a turn

```py
# Queue another turn in this exact conversation, inheriting the output policy.
next_run = await run.follow_up(
    input_message=[PlainInput(text="Now suggest three improvements.")],
)

# Submit steering while the current turn is still active.
receipt = await run.steer(
    input_message=[PlainInput(text="Also focus on safety concerns.")],
)
if receipt is not None:
    consumed = await receipt
```

`follow_up()` queues a turn in the original runtime and conversation. `steer()` adds input to an active turn: it returns `None` if rejected, or an `InputReceipt` whose awaited boolean indicates whether the input was consumed and saved. Rejected input is not queued automatically. Steering images and files are currently passed as text references.

For event-backed main sessions, user and assistant messages are committed incrementally. Assistant tool calls are committed before tool execution, and tool results are stored as `message.appended`. `tool.started` and `tool.finished` remain runtime notifications and are not stored in the conversation journal. Missing tool results after an interrupted execution are represented as unknown results when preparing the next turn.

`run.session.state` is `idle`, `queued`, `running`, or `closed`. The snapshot contains `ref`, `pending_turn_count`, and `active_turn_id`. Read the property again to refresh it.

Core resolves permissions from `source_event` or the current active same-UMO event. Background calls without a source run as members. A source event from another UMO is rejected.

A tool must not wait for another queued turn in its own session: that turn is waiting for the tool's current turn to finish. Submit and return, or use steering as appropriate.

### Agent Runtime Events {#runtime-events}

`run.events()` yields typed `RuntimeEvent` objects. Read `event.type` for the event name and `event.payload` for its data. Events can be replayed by independent readers; reading them does not send messages.

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

| Event | Use |
| --- | --- |
| `text.delta`, `reasoning.delta` | Display incremental content. |
| `message.completed` | Replace a message's deltas with its complete snapshot, matched by `message_id`. |
| `output.ready` | Collect prepared messages when `send_to_user=False`. |
| `tool.started/progress/finished/rejected` | Track tool execution. |
| `request.started/finished` | Track provider calls. |
| `usage.updated` | Read cumulative usage; replace the previous snapshot rather than adding it. |
| `turn.started/prepared/finished` | Track turn lifecycle. The SDK's `turn.finished` follows output handling. |

`result.content` contains the final reply; `result.text` extracts its plain text. `result.usage` contains cumulative usage and `result.metrics.steps` the executed step count. Unknown usage counts are `None`, not zero; cached input tokens are included in input tokens.

Migration: use `event.payload` instead of `event.data`, and `result.content` instead of `result.chain`. Replace `streaming_delta` / `llm_result` with `text.delta`, `reasoning.delta` / `message.completed`, and `agent_stats` with `usage.updated`. Read status, errors, and metrics from the final result.

## Build a Custom Agent {#build-agent}

> [!TIP]
> Use this section and the multi-agent orchestration example below to build an Agent workflow with models, prompts, context, and tools configured by your plugin. To trigger a task using an existing conversation’s persona, history, and tool configuration, see [Run an Agent in an Existing Conversation](#run-session-agent).

Use `tool_loop_agent()` to combine a model, prompt, and tools. This example uses `BilibiliTool` from [Defining Tools](./tools.md#defining-tools):

```py
# Before AstrBot v4.30.0:
# from astrbot.core.agent.tool import ToolSet
from astrbot.api import ToolSet

prov_id = await self.context.get_current_chat_provider_id(event.unified_msg_origin)
llm_resp = await self.context.tool_loop_agent(
    event=event,
    chat_provider_id=prov_id,
    prompt="Search for videos related to AstrBot on Bilibili.",
    tools=ToolSet([BilibiliTool()]),
    max_steps=30,  # Maximum agent execution steps
    tool_call_timeout=120,  # Tool invocation timeout
)
# print(llm_resp.completion_text) # Get the returned text
```

`tool_loop_agent()` method automatically handles the loop of tool invocations and LLM requests until the model stops calling tools or the maximum number of steps is reached.

### Example: Multi-Agent Orchestration {#multi-agent}

Multi-Agent systems decompose complex applications into multiple specialized agents that collaborate to solve problems. Unlike relying on a single agent to handle every step, multi-agent architectures allow smaller, more focused agents to be composed into coordinated workflows. We implement multi-agent systems using the `agent-as-tool` pattern.

In the example below, we define a Main Agent responsible for delegating tasks to different Sub-Agents based on user queries. Each Sub-Agent focuses on specific tasks, such as retrieving weather information.

![multi-agent-example-1](https://files.astrbot.app/docs/en/dev/star/guides/multi-agent-example-1.svg)

Define Tools:

```py
# Before AstrBot v4.30.0:
# from astrbot.core.agent.run_context import ContextWrapper
# from astrbot.core.agent.tool import FunctionTool, ToolExecResult, ToolSet
# from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.api import FunctionTool, ToolExecResult, ToolSet, logger
from astrbot.api.agents import AstrAgentContext, ContextWrapper
from pydantic import Field
from pydantic.dataclasses import dataclass


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

Then, similarly, invoke the Agent using the `tool_loop_agent()` method:

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

