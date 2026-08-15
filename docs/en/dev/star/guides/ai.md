# Calling AI from a Plugin

A Star should call models through public `astrbot.api` events, `PluginContext` capabilities, and tool interfaces. Do not import internal types from `astrbot.core.agent`, `astrbot.core.conversation_mgr`, or concrete Provider implementations; those modules evolve with the Agent Runtime.

## Choose the right path

| Need                                                                          | Recommended interface                            |
| ----------------------------------------------------------------------------- | ------------------------------------------------ |
| Continue through AstrBot's standard Persona, conversation, and Agent pipeline | `yield event.request_llm(...)`                   |
| Call one selected chat model without executing tools                          | `await self.context.models.generate(...)`        |
| Run a multi-step Agent over an explicit tool set                              | `await self.context.models.tool_loop(...)`       |
| Register a tool for ordinary AstrBot conversations                            | `@filter.llm_tool` or `self.context.tools.add()` |

## Resolve the current session model

```python
provider_id = await self.context.models.current_chat_provider_id(
    event.unified_msg_origin
)
```

This follows the profile and Provider selection for the message session. If no chat model is available, it raises an error. Return a useful failure instead of silently falling back to a hard-coded Provider ID.

## Use the standard pipeline

When a handler should reuse the current conversation, Persona, Skills, knowledge base, and default Agent, create a `ProviderRequest` and yield it:

```python
from astrbot.api.event import AstrMessageEvent, filter


@filter.command("ask")
async def ask(self, event: AstrMessageEvent):
    prompt = event.message_str.removeprefix("/ask").strip()
    if not prompt:
        yield event.plain_result("Please provide a question.")
        return
    yield event.request_llm(prompt=prompt)
```

This does not immediately return model text. It hands the request to the remaining Process pipeline and is the right choice for a plugin that replaces or augments the current user prompt.

## Generate text directly

```python
response = await self.context.models.generate(
    chat_provider_id=provider_id,
    prompt="Summarize the following text: ...",
    system_prompt="Return a concise factual summary.",
    image_urls=[],
    audio_urls=[],
)

text = response.completion_text
```

`models.generate()` performs one Provider request. Even when given a `ToolSet`, it does not execute returned tool calls. Use `models.tool_loop()` for a tool loop.

A direct call does not automatically save its input and output into the current conversation history. Prefer the standard pipeline for user-visible continuous conversations instead of manipulating internal `conversation_manager` objects.

## Register tools

### Decorator form

```python
from astrbot.api.event import AstrMessageEvent, filter


@filter.llm_tool(name="get_weather", required_actions=("provider.use",))
async def get_weather(
    self,
    event: AstrMessageEvent,
    location: str,
):
    """Get current weather for one location.

    Args:
        location(string): City or region name.
    """
    return await self.weather_client.lookup(location)
```

AstrBot generates the schema from the Google-style docstring. In `Args:`, use `name(type): description`. Supported forms include `string`, `number`, `object`, `boolean`, `array`, and array subtypes such as `array[string]`. Python annotations do not replace the docstring schema.

Return a concise string or another framework-supported result. Never include API keys, complete response headers, or remote credentials in an error.

Every tool must declare stable capabilities with `required_actions`; an undeclared tool is denied at the execution boundary. A plugin-defined action uses the complete `plugin:<plugin-id>:<action>` form and must also be declared in `metadata.yaml` under `authorization.actions`.

### Explicit `FunctionTool`

For a hand-written JSON Schema, use public types. The handler receives the current `AstrMessageEvent` as its first argument:

```python
from astrbot.api import FunctionTool
from astrbot.api.event import AstrMessageEvent


async def weather_handler(event: AstrMessageEvent, city: str):
    return await lookup_weather(city)


weather_tool = FunctionTool(
    name="weather",
    description="Get weather for a city.",
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "City name",
            }
        },
        "required": ["city"],
    },
    handler=weather_handler,
    required_actions=("provider.use",),
)

self.context.tools.add(weather_tool)
```

Tool names must be unique within a runtime. Use a plugin prefix and test that disable or hot reload leaves no stale handler behind.

## Run a tool-loop Agent

```python
from astrbot.api import ToolSet

tools = ToolSet([weather_tool])
response = await self.context.models.tool_loop(
    event=event,
    chat_provider_id=provider_id,
    prompt="Check the weather in Beijing and give one travel suggestion.",
    system_prompt="Use only the supplied tools. Do not invent weather data.",
    tools=tools,
    max_steps=8,
    tool_call_timeout=30,
)

yield event.plain_result(response.completion_text)
```

`models.tool_loop()` repeats model → tool → model until a final response or `max_steps`. Keep in mind:

- `event` supplies permission, workspace, and cancellation context. Do not fabricate another user's event.
- Pass only the tools required for the task. `None` means no explicit tool set and should not be treated as “all tools.”
- `tool_call_timeout` limits one tool call; `max_steps` limits the overall loop.
- HTTP clients, subprocesses, and tasks created by the plugin still need cleanup on timeout, cancellation, and `terminate()`.
- Output is not automatically added to ordinary conversation history unless the call path explicitly uses the standard conversation pipeline.

## Tool ownership

The public SDK deliberately does not expose a mutable runtime-wide tool manager.
Declare a tool with `@filter.llm_tool`, add a plugin-owned `FunctionTool` through
`self.context.tools.add(...)`, or build an explicit `ToolSet` from tools your
plugin owns. Do not cache tool objects across hot reload.

## Agent-as-tool and SubAgents

`astrbot.api.agent` registers an Agent handoff tool, and `RegisteringAgent.llm_tool()` can bind tools to it. This suits code-defined agents with a fixed responsibility. For ordinary operations, prefer WebUI [SubAgent Orchestration](../../../use/subagent), where Persona, Provider, and tool permissions are easier to audit.

A SubAgent is not a security container. Whether created in code or the WebUI, give it the smallest tool set, a clear description, and a finite step limit, and avoid recursive delegation.

## Provider access

`PluginContext.models` also exposes:

- `get(provider_id)`;
- `using_chat(umo)`;
- `chat()`;
- corresponding TTS, STT, and embedding query methods.

These return current Provider abstractions. A plugin can call abstract capabilities but must not import `provider/sources/*` or depend on private fields of one adapter. Put service-specific values in plugin configuration and pass them only through supported public calls.

## Security and tests

- Validate user-controlled prompts, URLs, files, and tool parameters.
- Do not treat model output as a trusted instruction. Continue authorization checks for file writes, shell, accounts, and external actions.
- Cover unavailable Providers, empty output, invalid tool arguments, timeout, cancellation, step exhaustion, and plugin hot reload.
- Use mock Providers and tools in unit tests. Enable live Provider tests only through explicit environment variables.
- Keep user-facing errors concise and redacted; put detailed exceptions only in protected logs.
