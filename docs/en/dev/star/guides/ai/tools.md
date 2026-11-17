# Tools

## Defining Tools

Tools enable large language models to invoke external capabilities.

```py
from pydantic import Field
from pydantic.dataclasses import dataclass

# Before AstrBot v4.30.0:
# from astrbot.core.agent.run_context import ContextWrapper
# from astrbot.core.agent.tool import FunctionTool, ToolExecResult
# from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.api import FunctionTool, ToolExecResult
from astrbot.api.agents import AstrAgentContext, ContextWrapper


@dataclass
class BilibiliTool(FunctionTool[AstrAgentContext]):
    name: str = "bilibili_videos"  # Tool name
    description: str = "A tool to fetch Bilibili videos."  # Tool description
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
        return "1. Video Title: How to Use AstrBot\nVideo Link: xxxxxx"
```

## Registering Tools with AstrBot

Once a Tool is defined, if you want it to be automatically invoked during user conversations, register it in your plugin's `__init__` method:

```py
class MyPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        # >= v4.5.1:
        self.context.add_llm_tools(BilibiliTool(), SecondTool(), ...)

        # < v4.5.1:
        tool_mgr = self.context.provider_manager.llm_tools
        tool_mgr.func_list.append(BilibiliTool())
```

> [!WARNING]
> `context.register_llm_tool()` is deprecated. Do not use it in new plugins.
>
> If you must use it for legacy compatibility, `func_args` must be a **list of dicts** in this format:
> ```py
> func_args = [{"type": "string", "name": "arg_name", "description": "..."}, ...]
> ```
> Passing a list of strings or any other format will raise `AttributeError: 'str' object has no attribute 'pop'`.

### Registering Tools via Decorator

Alternatively, you can use the `@filter.llm_tool` decorator to define and register a tool in one step. Make sure to follow the exact format below, including the docstring — AstrBot parses the docstring to generate the parameter schema:

```py{3,4,5,6,7}
@filter.llm_tool(name="get_weather")  # If name is omitted, the function name is used
async def get_weather(
    self, event: AstrMessageEvent, location: str
) -> MessageEventResult:
    """Get weather information.

    Args:
        location(string): The location to query
    """
    resp = self.get_weather_from_api(location)
    yield event.plain_result("Weather: " + resp)
```

In `location(string): The location to query`, `location` is the parameter name, `string` is the type, and the remainder is the description.

Supported types: `string`, `number`, `object`, `boolean`, `array`. Since v4.5.7, array subtypes are supported, e.g. `array[string]`.

> [!WARNING]
> **The `Args:` block is required and must be formatted correctly.**
>
> The `@filter.llm_tool` decorator generates the parameter schema by parsing the function's docstring — it does **not** read Python type annotations. If the docstring is missing an `Args:` block, or the format does not follow `param_name(type): description`, the generated schema will be empty. Any arguments passed by the LLM will be silently dropped, causing the function to fail with a missing-argument error.
>
> Additionally, passing `parameters=...` directly to the decorator is **not supported** and will be silently ignored. If you need manual control over the schema, use the `@dataclass` + `add_llm_tools()` approach above.

