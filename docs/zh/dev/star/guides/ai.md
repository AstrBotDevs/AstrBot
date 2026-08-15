# 在插件中调用 AI

Star 应通过 `astrbot.api` 的事件、`PluginContext` 能力和工具接口调用模型。不要从 `astrbot.core.agent`、`astrbot.core.conversation_mgr` 或 Provider 具体实现导入内部类型；这些模块会随 Agent Runtime 演进。

## 选择调用方式

| 需求                                                           | 推荐接口                                         |
| -------------------------------------------------------------- | ------------------------------------------------ |
| 让当前消息继续走 AstrBot 的标准 Persona、会话和 Agent pipeline | `yield event.request_llm(...)`                   |
| 直接调用一个指定聊天模型，不自动执行工具                       | `await self.context.models.generate(...)`        |
| 在插件内运行指定工具集的多 step Agent                          | `await self.context.models.tool_loop(...)`       |
| 为普通 AstrBot 对话注册一个可被模型调用的工具                  | `@filter.llm_tool` 或 `self.context.tools.add()` |

## 使用当前会话模型

```python
provider_id = await self.context.models.current_chat_provider_id(
    event.unified_msg_origin
)
```

这个方法会遵循当前消息会话的配置档和 Provider 选择。如果没有可用聊天模型会抛出错误，插件应返回可理解的失败消息，而不是回退到硬编码 Provider ID。

## 交给标准 pipeline

事件处理器希望复用当前会话、Persona、Skills、知识库和默认 Agent 时，生成 `ProviderRequest` 并 yield：

```python
from astrbot.api.event import AstrMessageEvent, filter


@filter.command("ask")
async def ask(self, event: AstrMessageEvent):
    prompt = event.message_str.removeprefix("/ask").strip()
    if not prompt:
        yield event.plain_result("请提供问题。")
        return
    yield event.request_llm(prompt=prompt)
```

这不是立即返回的模型文本；它把请求交给后续 Process pipeline。适合“替换/补充当前用户提示词”的插件。

## 直接生成文本

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

`models.generate()` 只执行一次 Provider 请求。即使传入 `ToolSet`，它也不会自动执行返回的工具调用；需要工具循环时使用 `models.tool_loop()`。

直接调用不会自动把本次输入输出保存进当前会话历史。插件如果需要用户可见的连续会话，应优先使用标准 pipeline，而不是直接操作 `conversation_manager` 内部对象。

## 注册工具

### 装饰器方式

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

工具 schema 由 Google-style docstring 生成。`Args:` 中使用 `name(type): description`，支持 `string`、`number`、`object`、`boolean`、`array` 和 `array[string]` 等数组子类型。类型注解不能代替 docstring schema。

工具返回简短字符串或框架支持的结果。不要在错误中返回 API Key、完整响应头或远端凭据。

每个工具都必须以 `required_actions` 声明稳定能力；缺少声明的工具会在执行边界被拒绝。插件自定义动作使用完整的 `plugin:<plugin-id>:<action>`，并且必须在 `metadata.yaml` 的 `authorization.actions` 中声明。

### 显式 `FunctionTool`

需要手写 JSON Schema 时只使用公开类型；handler 的第一个参数会收到当前 `AstrMessageEvent`：

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

工具名在一个运行时内必须唯一。使用插件前缀并在 `terminate()` / 热重载测试中确认不会留下旧 handler。

## 运行工具循环 Agent

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

`models.tool_loop()` 会重复执行模型 → 工具 → 模型，直到得到最终回复或达到 `max_steps`。注意：

- `event` 提供本次运行的权限、工作区和取消上下文；不要伪造其他用户的 event。
- 只传递完成任务所需的工具；`None` 表示无显式工具集，不应拿“所有工具”作默认。
- `tool_call_timeout` 是单次工具超时，`max_steps` 是整个循环的 step 上限。
- 插件创建的 HTTP client、子进程和任务仍需在超时、取消与 `terminate()` 中清理。
- 返回内容不会自动写入普通会话历史，除非调用链明确使用标准会话 pipeline。

## 工具归属

公开 SDK 有意不暴露可变的全运行时工具管理器。请通过 `@filter.llm_tool`
声明工具、用 `self.context.tools.add(...)` 添加插件自有的 `FunctionTool`，或从插件自有工具构造显式 `ToolSet`。不要跨热重载缓存工具对象。

## Agent-as-tool 与子代理

`astrbot.api.agent` 可以注册一个 Agent handoff 工具，`RegisteringAgent.llm_tool()` 可以把工具绑定到该 Agent。它适合由代码定义、职责固定的 agent-as-tool；普通运维场景优先使用 WebUI 的[子代理编排](../../../use/subagent)，便于审计 Persona、Provider 和工具权限。

子代理不是权限隔离容器。无论通过装饰器还是 WebUI 创建，都应采用最小工具集、清晰描述和有限 step，并避免递归委派。

## Provider 访问

`PluginContext.models` 还提供：

- `get(provider_id)`；
- `using_chat(umo)`；
- `chat()`；
- 对应的 TTS、STT 和 Embedding 查询方法。

这些返回当前 Provider 抽象实例。插件可以调用抽象能力，但不得导入 `provider/sources/*` 或依赖某个具体适配器的私有字段。需要某服务专用参数时，把它作为插件配置并通过受支持的公共调用传入。

## 安全与测试

- 对用户可控 prompt、URL、文件和工具参数做边界校验。
- 不要把模型输出当作可信指令；涉及写文件、Shell、账号和外部操作时继续做权限检查。
- 覆盖 Provider 不可用、空回复、工具参数错误、超时、取消、达到 step 上限和插件热重载。
- 用 mock Provider / tool 做单元测试，Provider 实网测试应由环境变量显式启用。
- 面向用户的错误应简短并脱敏，详细异常只写安全日志。
