# 工具

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

