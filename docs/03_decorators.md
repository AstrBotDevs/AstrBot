# AstrBot SDK 装饰器使用指南

## 概述

本文档详细介绍 `astrbot_sdk.decorators` 中所有装饰器的使用方法、参数说明和最佳实践。

## 目录

- [事件触发装饰器](#事件触发装饰器)
- [修饰器装饰器](#修饰器装饰器)
- [过滤器装饰器](#过滤器装饰器)
- [限制器装饰器](#限制器装饰器)
- [优先级装饰器](#优先级装饰器)
- [对话装饰器](#对话装饰器)
- [能力暴露装饰器](#能力暴露装饰器)
- [LLM 工具装饰器](#llm-工具装饰器)
- [生命周期装饰器](#生命周期装饰器)
- [HTTP API 装饰器](#http-api-装饰器)
- [MCP 装饰器](#mcp-装饰器)
- [最佳实践](#最佳实践)

---

## 事件触发装饰器

### @on_command

命令触发装饰器。

**签名：**
```python
def on_command(
    command: str | Sequence[str],
    *,
    aliases: list[str] | None = None,
    description: str | None = None,
) -> Callable
```

**参数：**
- `command`: 命令名称（不包含前缀符），或命令名称列表（首个为主命令，其余为别名）
- `aliases`: 额外的命令别名列表
- `description`: 命令描述

**示例：**

```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command

class MyPlugin(Star):
    @on_command("hello")
    async def hello(self, event: MessageEvent, ctx: Context):
        await event.reply("Hello!")

    @on_command(["echo", "repeat"], aliases=["say", "speak"])
    async def echo(self, event: MessageEvent, text: str):
        await event.reply(text)
```

### @on_message

消息触发装饰器。

**签名：**
```python
def on_message(
    *,
    regex: str | None = None,
    keywords: list[str] | None = None,
    platforms: list[str] | None = None,
    message_types: list[str] | None = None,
    description: str | None = None,
) -> Callable
```

**参数：**
- `regex`: 正则表达式模式
- `keywords`: 关键词列表（任一匹配即触发）
- `platforms`: 限定平台列表
- `message_types`: 限定消息类型（"group", "private"）
- `description`: 处理器描述

**示例：**

```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_message

class MyPlugin(Star):
    # 关键词匹配
    @on_message(keywords=["帮助", "help"])
    async def help_handler(self, event: MessageEvent, ctx: Context):
        await event.reply("可用命令: /hello")

    # 正则匹配
    @on_message(regex=r"\d{4,}")
    async def number_handler(self, event: MessageEvent, ctx: Context):
        await event.reply("检测到数字!")

    # 多条件过滤
    @on_message(
        keywords=["天气"],
        platforms=["qq"],
        message_types=["private"]
    )
    async def weather_query(self, event: MessageEvent, ctx: Context):
        await event.reply("请输入城市名称")
```

### @on_event

事件触发装饰器。

**签名：**
```python
def on_event(
    event_type: str,
    *,
    description: str | None = None,
) -> Callable
```

**参数：**
- `event_type`: 事件类型标识
- `description`: 处理器描述

**示例：**

```python
from astrbot_sdk import Star, Context
from astrbot_sdk.decorators import on_event

class MyPlugin(Star):
    @on_event("group_member_join")
    async def welcome_new_member(self, event, ctx: Context):
        await ctx.platform.send(event.group_id, "欢迎新成员!")
```

### @on_schedule

定时任务装饰器。

**签名：**
```python
def on_schedule(
    *,
    cron: str | None = None,
    interval_seconds: int | None = None,
    description: str | None = None,
) -> Callable
```

**参数：**
- `cron`: cron 表达式（如 "0 8 * * *" 表示每天 8:00）
- `interval_seconds`: 执行间隔（秒）
- `description`: 任务描述

**注意：** `cron` 和 `interval_seconds` 必须且只能提供一个。

**示例：**

```python
from astrbot_sdk import Star, Context
from astrbot_sdk.decorators import on_schedule

class MyPlugin(Star):
    # 固定间隔
    @on_schedule(interval_seconds=3600)
    async def hourly_check(self, ctx: Context):
        pass

    # cron 表达式
    @on_schedule(cron="0 8 * * *")  # 每天 8:00
    async def morning_greeting(self, ctx: Context):
        await ctx.platform.send("group_123", "早上好!")
```

---

## 修饰器装饰器

### @require_admin

管理员权限装饰器。

**签名：**
```python
def require_admin(func: HandlerCallable) -> HandlerCallable
```

**示例：**

```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command, require_admin

class MyPlugin(Star):
    @on_command("admin")
    @require_admin
    async def admin_cmd(self, event: MessageEvent, ctx: Context):
        await event.reply("管理员命令")
```

### @admin_only

管理员权限装饰器（`@require_admin` 的别名）。

**签名：**
```python
def admin_only(func: HandlerCallable) -> HandlerCallable
```

**示例：**

```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command, admin_only

class MyPlugin(Star):
    @on_command("admin")
    @admin_only
    async def admin_cmd(self, event: MessageEvent, ctx: Context):
        await event.reply("管理员命令")
```

**说明：**
- 功能与 `@require_admin` 完全相同
- 更简洁的语法，无需括号
- 适合快速标记管理员命令

### @require_permission

通用角色权限装饰器。

**签名：**
```python
def require_permission(
    role: Literal["member", "admin"],
) -> Callable[[HandlerCallable], HandlerCallable]
```

**参数：**
- `role`: 要求的角色，支持 "member" 或 "admin"

**示例：**

```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command, require_permission

class MyPlugin(Star):
    @on_command("member_cmd")
    @require_permission("member")
    async def member_cmd(self, event: MessageEvent, ctx: Context):
        await event.reply("成员命令")

    @on_command("admin_cmd")
    @require_permission("admin")
    async def admin_cmd(self, event: MessageEvent, ctx: Context):
        await event.reply("管理员命令")
```

---

## 过滤器装饰器

### @platforms

限定平台装饰器。

**签名：**
```python
def platforms(*names: str) -> Callable
```

**示例：**

```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command, platforms

class MyPlugin(Star):
    @on_command("qq_only")
    @platforms("qq")
    async def qq_only_command(self, event: MessageEvent, ctx: Context):
        await event.reply("这是 QQ 专属命令")

    @on_command("multi_platform")
    @platforms("qq", "wechat")
    async def multi_platform_command(self, event: MessageEvent, ctx: Context):
        await event.reply("QQ 和微信都可用的命令")
```

### @message_types

限定消息类型装饰器。

**签名：**
```python
def message_types(*types: str) -> Callable
```

**示例：**

```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command, message_types

class MyPlugin(Star):
    @on_command("group_only")
    @message_types("group")
    async def group_command(self, event: MessageEvent, ctx: Context):
        await event.reply("这是群聊命令")
```

### @group_only

仅群聊装饰器。

**签名：**
```python
def group_only() -> Callable[[HandlerCallable], HandlerCallable]
```

**示例：**

```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command, group_only

class MyPlugin(Star):
    @on_command("group_admin")
    @group_only()
    async def group_admin_command(self, event: MessageEvent, ctx: Context):
        await event.reply("这是群聊管理命令")
```

### @private_only

仅私聊装饰器。

**签名：**
```python
def private_only() -> Callable[[HandlerCallable], HandlerCallable]
```

**示例：**

```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command, private_only

class MyPlugin(Star):
    @on_command("private_chat")
    @private_only()
    async def private_command(self, event: MessageEvent, ctx: Context):
        await event.reply("这是私聊命令")
```

---

## 限制器装饰器

### @rate_limit

速率限制装饰器。

**签名：**
```python
def rate_limit(
    limit: int,
    window: float,
    *,
    scope: LimiterScope = "session",
    behavior: LimiterBehavior = "hint",
    message: str | None = None,
) -> Callable
```

**参数：**
- `limit`: 时间窗口内最大调用次数
- `window`: 时间窗口大小（秒）
- `scope`: 限制范围（"session", "user", "group", "global"）
- `behavior`: 触发限制后的行为（"hint", "silent", "error"）
- `message`: 自定义提示消息

**示例：**

```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command, rate_limit

class MyPlugin(Star):
    @on_command("search")
    @rate_limit(5, 60)  # 每分钟最多5次
    async def search_command(self, event: MessageEvent, ctx: Context):
        await event.reply("搜索结果...")

    @on_command("draw")
    @rate_limit(3, 3600, scope="user")  # 每用户每小时3次
    async def draw_command(self, event: MessageEvent, ctx: Context):
        await event.reply("绘图结果...")
```

### @cooldown

冷却时间装饰器。

**签名：**
```python
def cooldown(
    seconds: float,
    *,
    scope: LimiterScope = "session",
    behavior: LimiterBehavior = "hint",
    message: str | None = None,
) -> Callable
```

**参数：**
- `seconds`: 冷却时间（秒）
- `scope`: 限制范围（"session", "user", "group", "global"）
- `behavior`: 触发限制后的行为（"hint", "silent", "error"）
- `message`: 自定义提示消息

**示例：**

```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command, cooldown

class MyPlugin(Star):
    @on_command("cast_skill")
    @cooldown(30)  # 30秒冷却
    async def cast_skill_command(self, event: MessageEvent, ctx: Context):
        await event.reply("技能施放成功!")
```

**注意：** `rate_limit` 和 `cooldown` 只适用于 `@on_command` 和 `@on_message` 触发器。

---

## 优先级装饰器

### @priority

设置 handler 执行优先级。

**签名：**
```python
def priority(value: int) -> Callable[[HandlerCallable], HandlerCallable]
```

**参数：**
- `value`: 优先级数值，**越大越先执行**
- 默认优先级为 0

**示例：**

```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command, priority

class MyPlugin(Star):
    @on_command("hello")
    @priority(10)  # 高优先级，先执行
    async def hello_high(self, event: MessageEvent, ctx: Context):
        await event.reply("高优先级处理器")

    @on_command("hello")
    @priority(5)   # 较低优先级，后执行
    async def hello_low(self, event: MessageEvent, ctx: Context):
        await event.reply("低优先级处理器")
```

**使用场景：**
- 多个插件注册了相同命令时控制执行顺序
- 确保核心处理器先于扩展处理器执行
- 实现插件间的协作处理链

**注意事项：**
- 相同优先级的 handler 执行顺序不确定
- 高优先级 handler 不会阻止低优先级 handler 执行（除非显式调用 `event.stop_event()`）

---

## 对话装饰器

### @conversation_command

对话命令装饰器，用于创建交互式对话流程。

**签名：**
```python
def conversation_command(
    command: str | Sequence[str],
    *,
    aliases: list[str] | None = None,
    description: str | None = None,
    timeout: int = 60,
    mode: ConversationMode = "replace",
    busy_message: str | None = None,
    grace_period: float = 1.0,
) -> Callable
```

**参数：**
- `command`: 命令名称或序列（首项为正式名，其余视为别名）
- `aliases`: 额外别名列表
- `description`: 命令描述
- `timeout`: 会话超时时间（秒），默认 60
- `mode`: 会话冲突时的行为：
  - `"replace"`: 替换当前会话
  - `"reject"`: 拒绝新请求
- `busy_message`: 拒绝新请求时的提示消息
- `grace_period`: 宽限期（秒），用于会话生命周期处理

**示例：**

```python
from astrbot_sdk import Star, MessageEvent, Context, ConversationSession
from astrbot_sdk.decorators import conversation_command

class MyPlugin(Star):
    @conversation_command("survey", timeout=120)
    async def survey(self, event: MessageEvent, ctx: Context, session: ConversationSession):
        """交互式调查问卷"""
        # ask() 返回 MessageEvent，通过 .text 获取文本内容
        name_event = await session.ask("请输入您的姓名：")
        name = name_event.text

        age_event = await session.ask(f"{name}，请输入您的年龄：")
        age = age_event.text

        await session.reply(f"感谢参与！姓名：{name}，年龄：{age}")
        session.end()  # 结束对话

    @conversation_command("chat", mode="reject", busy_message="请稍后再试")
    async def chat(self, event: MessageEvent, ctx: Context, session: ConversationSession):
        """拒绝模式的对话"""
        while session.active:
            response = await session.ask("你说点什么？")
            # response 是 MessageEvent，用 .text 获取文本
            await session.reply(f"你说的是：{response.text}")
            if response.text.lower() == "退出":
                session.end()
```

**ConversationSession 方法：**

| 方法 | 说明 |
|------|------|
| `ask(prompt, timeout=None) -> MessageEvent` | 发送提示并等待用户回复，返回 MessageEvent（通过 `.text` 获取文本） |
| `reply(text)` | 回复文本消息 |
| `reply_chain(chain)` | 回复消息链 |
| `send_message(content)` | 发送消息 |
| `end()` | 结束对话会话（状态设为 COMPLETED） |
| `close(state)` | 以指定状态关闭会话 |
| `mark_replaced()` | 标记会话被替换 |

**异常处理：**

```python
from astrbot_sdk import ConversationClosed, ConversationReplaced

@conversation_command("demo")
async def demo(self, event: MessageEvent, ctx: Context, session: ConversationSession):
    try:
        await event.reply("输入 'exit' 结束对话")
        if event.text.lower() == "exit":
            session.end()
    except ConversationClosed:
        # 会话被关闭
        await event.reply("对话已结束")
    except ConversationReplaced:
        # 会话被新会话替换
        await event.reply("开始新的对话")
```

---

## 能力暴露装饰器

### @provide_capability

暴露能力装饰器，允许其他插件或 Core 通过 capability 名称调用此方法。

**签名：**
```python
def provide_capability(
    name: str,
    *,
    description: str,
    input_schema: dict[str, Any] | None = None,
    output_schema: dict[str, Any] | None = None,
    input_model: type[BaseModel] | None = None,
    output_model: type[BaseModel] | None = None,
    supports_stream: bool = False,
    cancelable: bool = False,
) -> Callable
```

**参数：**
- `name`: capability 名称（格式为 "namespace.action"，不能使用保留命名空间）
- `description`: 能力描述
- `input_schema`: 输入 JSON Schema
- `output_schema`: 输出 JSON Schema
- `input_model`: 输入 pydantic 模型（与 `input_schema` 二选一）
- `output_model`: 输出 pydantic 模型（与 `output_schema` 二选一）
- `supports_stream`: 是否支持流式输出
- `cancelable`: 是否可取消

**保留命名空间：**
- `handler.` - 处理器相关
- `system.` - 系统内部能力
- `internal.` - 内部实现细节

**示例：**

```python
from pydantic import BaseModel, Field
from astrbot_sdk import Star, Context
from astrbot_sdk.decorators import provide_capability

class CalculateInput(BaseModel):
    x: int = Field(description="第一个数")
    y: int = Field(description="第二个数")

class CalculateOutput(BaseModel):
    result: int = Field(description="计算结果")

class MyPlugin(Star):
    @provide_capability(
        "my_plugin.calculate",
        description="执行加法计算",
        input_model=CalculateInput,
        output_model=CalculateOutput,
    )
    async def calculate(self, payload: dict, ctx: Context):
        return {"result": payload["x"] + payload["y"]}

    # 使用 JSON Schema
    @provide_capability(
        "my_plugin.translate",
        description="翻译文本",
        input_schema={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "要翻译的文本"},
                "target_lang": {"type": "string", "description": "目标语言"},
            },
            "required": ["text", "target_lang"],
        },
        output_schema={
            "type": "object",
            "properties": {
                "translated": {"type": "string"},
            },
        },
    )
    async def translate(self, payload: dict, ctx: Context):
        return {"translated": f"[translated] {payload['text']}"}
```

---

## LLM 工具装饰器

### @register_llm_tool

注册 LLM 工具装饰器，将方法注册为 LLM 可调用的工具。

**签名：**
```python
def register_llm_tool(
    name: str | None = None,
    *,
    description: str | None = None,
    parameters_schema: dict[str, Any] | None = None,
    active: bool = True,
) -> Callable
```

**参数：**
- `name`: 工具名称，默认使用函数名
- `description`: 工具描述，默认使用函数 docstring
- `parameters_schema`: 参数 JSON Schema，默认从函数签名自动推断
- `active`: 是否激活

**示例：**

```python
from astrbot_sdk import Star
from astrbot_sdk.decorators import register_llm_tool

class MyPlugin(Star):
    @register_llm_tool()
    async def get_weather(self, city: str, unit: str = "celsius"):
        """获取指定城市的天气信息"""
        return f"{city} 的天气: 25°C"

    @register_llm_tool("search_web", description="搜索网页内容")
    async def search(self, query: str, limit: int = 10):
        return f"搜索结果: {query}"
```

### @register_agent

注册 Agent 装饰器。

**签名：**
```python
def register_agent(
    name: str,
    *,
    description: str = "",
    tool_names: list[str] | None = None,
) -> Callable
```

**参数：**
- `name`: Agent 名称
- `description`: Agent 描述
- `tool_names`: 关联的工具名称列表

**示例：**

```python
from astrbot_sdk import Star, Context
from astrbot_sdk.decorators import register_agent
from astrbot_sdk.llm.agents import BaseAgentRunner

@register_agent("my_agent", description="我的智能助手", tool_names=["get_weather"])
class MyAgent(BaseAgentRunner):
    async def run(self, ctx: Context, request) -> Any:
        return "agent result"
```

---

## 生命周期装饰器

### @validate_config

配置验证装饰器，用于验证插件配置。

**签名：**
```python
def validate_config(
    *,
    model: type[BaseModel] | None = None,
    schema: dict[str, Any] | None = None,
) -> Callable
```

**参数：**
- `model`: pydantic BaseModel 子类，用于验证配置
- `schema`: 配置 schema 字典（与 `model` 二选一）

**示例：**

```python
from pydantic import BaseModel, Field
from astrbot_sdk import Star
from astrbot_sdk.decorators import validate_config

class MyConfig(BaseModel):
    api_key: str = Field(description="API 密钥")
    timeout: int = Field(default=30, description="超时时间")

class MyPlugin(Star):
    @validate_config(model=MyConfig)
    async def validate_my_config(self, config: dict):
        # 配置已通过 pydantic 验证
        pass
```

### @on_provider_change

Provider 变更钩子装饰器。

**签名：**
```python
def on_provider_change(
    *,
    provider_types: list[str] | tuple[str, ...] | None = None,
) -> Callable
```

**参数：**
- `provider_types`: 关注的 provider 类型列表，为空表示所有类型

**示例：**

```python
from astrbot_sdk import Star, Context
from astrbot_sdk.decorators import on_provider_change

class MyPlugin(Star):
    @on_provider_change(provider_types=["openai", "anthropic"])
    async def on_llm_provider_change(self, ctx: Context):
        # LLM provider 变更时触发
        pass
```

### @background_task

后台任务装饰器，用于在插件启动时自动启动后台任务。

**签名：**
```python
def background_task(
    *,
    description: str = "",
    auto_start: bool = True,
    on_error: Literal["log", "restart"] = "log",
) -> Callable
```

**参数：**
- `description`: 任务描述
- `auto_start`: 是否自动启动
- `on_error`: 错误处理方式
  - `"log"`: 记录日志
  - `"restart"`: 重启任务

**示例：**

```python
from astrbot_sdk import Star, Context
from astrbot_sdk.decorators import background_task

class MyPlugin(Star):
    @background_task(description="定时清理任务", on_error="restart")
    async def cleanup_task(self, ctx: Context):
        while True:
            await ctx.sleep(3600)  # 每小时执行
            # 执行清理逻辑
            pass
```

---

## HTTP API 装饰器

### @http_api

HTTP API 暴露装饰器，将方法暴露为 HTTP 端点。

**签名：**
```python
def http_api(
    route: str,
    *,
    methods: list[str] | None = None,
    description: str = "",
    capability_name: str | None = None,
) -> Callable
```

**参数：**
- `route`: API 路由路径
- `methods`: HTTP 方法列表，默认 `["GET"]`
- `description`: API 描述
- `capability_name`: 关联的 capability 名称

**示例：**

```python
from astrbot_sdk import Star
from astrbot_sdk.decorators import http_api

class MyPlugin(Star):
    @http_api("/hello", methods=["GET", "POST"], description="打招呼接口")
    async def hello_api(self, request):
        return {"message": "Hello, World!"}

    @http_api("/data/{id}", methods=["GET"])
    async def get_data(self, request, id: str):
        return {"id": id, "data": "some data"}
```

---

## MCP 装饰器

### @mcp_server

MCP 服务器注册装饰器。

**签名：**
```python
def mcp_server(
    *,
    name: str,
    scope: Literal["local", "global"] = "global",
    config: dict[str, Any] | None = None,
    timeout: float = 30.0,
    wait_until_ready: bool = True,
)
```

**参数：**
- `name`: MCP 服务器名称
- `scope`: 作用域
  - `"local"`: 本地作用域
  - `"global"`: 全局作用域
- `config`: MCP 服务器配置
- `timeout`: 超时时间（秒）
- `wait_until_ready`: 是否等待就绪

**示例：**

```python
from astrbot_sdk import Star
from astrbot_sdk.decorators import mcp_server

class MyPlugin(Star):
    @mcp_server(name="my_mcp", scope="global", timeout=60.0)
    async def my_mcp_server(self):
        # MCP 服务器实现
        pass
```

### @register_skill

技能注册装饰器。

**签名：**
```python
def register_skill(
    *,
    name: str,
    path: str,
    description: str = "",
)
```

**参数：**
- `name`: 技能名称
- `path`: 技能路径
- `description`: 技能描述

**示例：**

```python
from astrbot_sdk import Star
from astrbot_sdk.decorators import register_skill

@register_skill(name="my_skill", path="skills/my_skill", description="我的技能")
class MyPlugin(Star):
    pass
```

### @acknowledge_global_mcp_risk

标记插件类允许修改全局 MCP 状态。

**签名：**
```python
def acknowledge_global_mcp_risk(cls: type[Any]) -> type[Any]
```

**示例：**

```python
from astrbot_sdk import Star
from astrbot_sdk.decorators import acknowledge_global_mcp_risk

@acknowledge_global_mcp_risk
class MyPlugin(Star):
    # 此插件可以修改全局 MCP 状态
    pass
```

---

## 最佳实践

### 1. 装饰器顺序

正确的装饰器顺序很重要：

```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command, platforms, rate_limit, require_admin

class MyPlugin(Star):
    @on_command("command")      # 1. 事件触发装饰器
    @platforms("qq")            # 2. 过滤器装饰器
    @rate_limit(5, 60)          # 3. 限制器装饰器
    @require_admin              # 4. 修饰器装饰器
    async def my_handler(self, event: MessageEvent, ctx: Context):
        pass
```

### 2. 错误处理

始终实现错误处理：

```python
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command

class MyPlugin(Star):
    @on_command("risky_command")
    async def risky_handler(self, event: MessageEvent, ctx: Context):
        try:
            result = await some_risky_operation()
            await event.reply(f"成功: {result}")
        except Exception as e:
            ctx.logger.error(f"操作失败: {e}")
            await event.reply("操作失败，请稍后重试")
```

### 3. 类型注解

使用类型注解提高代码可读性：

```python
from typing import Optional
from astrbot_sdk import Star, MessageEvent, Context
from astrbot_sdk.decorators import on_command

class MyPlugin(Star):
    @on_command("greet")
    async def greet_handler(
        self,
        event: MessageEvent,
        ctx: Context
    ) -> None:
        await event.reply("Hello!")
```

### 4. 避免常见陷阱

**不要混用冲突的装饰器：**

```python
# 错误
@on_message(platforms=["qq"])
@platforms("wechat")  # 冲突!
async def handler(...): pass

# 正确
@on_message(platforms=["qq", "wechat"])
async def handler(...): pass
```

**不要在非消息处理器使用限制器：**

```python
# 错误
@on_event("ready")
@rate_limit(5, 60)  # 不支持!
async def handler(...): pass

# 正确
@on_command("cmd")
@rate_limit(5, 60)
async def handler(...): pass
```

**不要叠加多个限制器：**

```python
# 错误
@on_command("cmd")
@rate_limit(5, 60)
@cooldown(30)  # 不能与 rate_limit 叠加!
async def handler(...): pass

# 正确 - 只使用一种限制器
@on_command("cmd")
@rate_limit(5, 60)
async def handler(...): pass
```
