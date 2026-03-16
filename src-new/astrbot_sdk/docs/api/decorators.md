# 装饰器 - 事件处理注册完整参考

## 概述

装饰器是 AstrBot SDK 中用于注册事件处理器的核心机制。通过装饰器标记方法，SDK 会自动收集这些方法并在适当时机调用它们。

**模块路径**: `astrbot_sdk.decorators`

---

## 目录

- [事件触发装饰器](#事件触发装饰器)
- [修饰器装饰器](#修饰器装饰器)
- [过滤器装饰器](#过滤器装饰器)
- [限制器装饰器](#限制器装饰器)
- [能力暴露装饰器](#能力暴露装饰器)
- [LLM 工具装饰器](#llm-工具装饰器)
- [使用示例](#使用示例)

---

## 导入方式

```python
# 从主模块导入（推荐）
from astrbot_sdk.decorators import (
    # 事件触发
    on_command,
    on_message,
    on_event,
    on_schedule,
    # 修饰器
    require_admin,
    # 过滤器
    platforms,
    message_types,
    group_only,
    private_only,
    # 限制器
    rate_limit,
    cooldown,
    # 能力暴露
    provide_capability,
    # LLM 工具
    register_llm_tool,
    register_agent,
)

# 或者按需导入
from astrbot_sdk.decorators import on_command, on_message
```

---

## 事件触发装饰器

### @on_command

命令触发装饰器，当用户输入指定命令时触发。

#### 签名

```python
def on_command(
    command: str | Sequence[str],
    *,
    aliases: list[str] | None = None,
    description: str | None = None,
) -> Callable[[HandlerCallable], HandlerCallable]
```

#### 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `command` | `str \| Sequence[str]` | 是 | 命令名称（不包含前缀符），可传入单个命令或命令列表 |
| `aliases` | `list[str] \| None` | 否 | 命令别名列表 |
| `description` | `str \| None` | 否 | 命令描述，用于帮助信息生成 |

#### 示例

```python
# 简单命令
@on_command("hello")
async def hello(self, event: MessageEvent, ctx: Context):
    await event.reply("Hello, World!")

# 带别名
@on_command("echo", aliases=["repeat", "say"])
async def echo(self, event: MessageEvent, text: str):
    await event.reply(f"你说: {text}")

# 带描述
@on_command("help", description="显示帮助信息")
async def help(self, event: MessageEvent, ctx: Context):
    await event.reply("可用命令: /hello")

# 批量命令
@on_command(["start", "begin"])
async def start(self, event: MessageEvent, ctx: Context):
    await event.reply("开始执行...")
```

#### 注意事项

1. 命令名称不应包含前缀符（如 `/`），框架会自动处理
2. 传入命令列表时，第一个命令作为主命令名，其余作为别名
3. `aliases` 参数中的别名会与命令列表合并，重复项会自动去重
4. 命令名不能为空字符串

---

### @on_message

消息触发装饰器，当消息匹配指定条件时触发。

#### 签名

```python
def on_message(
    *,
    regex: str | None = None,
    keywords: list[str] | None = None,
    platforms: list[str] | None = None,
    message_types: list[str] | None = None,
) -> Callable[[HandlerCallable], HandlerCallable]
```

#### 参数

| 参数 | 类型 | 必需* | 说明 |
|------|------|--------|------|
| `regex` | `str \| None` | 否* | 正则表达式模式 |
| `keywords` | `list[str] \| None` | 否* | 关键词列表（任一匹配即触发） |
| `platforms` | `list[str] \| None` | 否 | 限定平台列表 |
| `message_types` | `list[str] \| None` | 否 | 限定消息类型（`"group"`, `"private"`） |

*注: `regex` 和 `keywords` 至少需要提供一个

#### 示例

```python
# 关键词匹配
@on_message(keywords=["帮助", "help"])
async def help(self, event: MessageEvent, ctx: Context):
    await event.reply("可用命令: /hello")

# 正则匹配
@on_message(regex=r"\d{4,}")
async def number(self, event: MessageEvent, ctx: Context):
    await event.reply("检测到数字!")

# 多条件过滤
@on_message(
    keywords=["天气"],
    platforms=["qq"],
    message_types=["private"]
)
async def weather(self, event: MessageEvent, ctx: Context):
    await event.reply("请输入城市名称查询天气")

# 组合使用
@on_message(regex=r"^打卡")
async def check_in(self, event: MessageEvent, ctx: Context):
    await event.reply(f"{event.sender_name} 打卡成功!")
```

#### 注意事项

1. 正则表达式使用 Python `re` 模块语法
2. 关键词匹配是包含匹配，不是精确匹配
3. 不能与 `@platforms()` 装饰器混用（会有 `ValueError`）
4. 不能与 `@group_only()` / `@private_only()` / `@message_types()` 混用

---

### @on_event

事件触发装饰器，用于处理非消息类型的系统事件。

#### 签名

```python
def on_event(event_type: str) -> Callable[[HandlerCallable], HandlerCallable]
```

#### 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `event_type` | `str` | 是 | 事件类型标识 |

#### 示例

```python
# 群成员加入事件
@on_event("group_member_join")
async def welcome(self, event, ctx: Context):
    await ctx.platform.send(event.group_id, f"欢迎 {event.user_id}!")

# 群成员离开事件
@on_event("group_member_decrease")
async def goodbye(self, event, ctx: Context):
    await ctx.platform.send(event.group_id, f"再见 {event.user_id}")

# 好友请求事件
@on_event("friend_request")
async def handle_request(self, event, ctx: Context):
    await ctx.platform.send(event.user_id, "已自动通过好友请求")
```

#### 注意事项

1. 用于处理非消息类型的事件（如群成员变动、好友请求等）
2. 不能与 `@rate_limit` 或 `@cooldown` 一起使用
3. 不同平台的事件类型可能不同，需要查阅平台文档

---

### @on_schedule

定时任务装饰器，按指定时间间隔或 cron 表达式触发。

#### 签名

```python
def on_schedule(
    *,
    cron: str | None = None,
    interval_seconds: int | None = None,
) -> Callable[[HandlerCallable], HandlerCallable]
```

#### 参数

| 参数 | 类型 | 必需* | 说明 |
|------|------|--------|------|
| `cron` | `str \| None` | 否* | cron 表达式（如 `"0 8 * * *"` 表示每天 8:00） |
| `interval_seconds` | `int \| None` | 否* | 执行间隔（秒） |

*注: `cron` 和 `interval_seconds` 必须且只能提供一个

#### 示例

```python
# 固定间隔（每小时执行）
@on_schedule(interval_seconds=3600)
async def hourly_check(self, ctx: Context):
    ctx.logger.info("每小时执行一次")

# cron 表达式（每天 8:00）
@on_schedule(cron="0 8 * * *")
async def morning_greeting(self, ctx: Context):
    await ctx.platform.send("group_123", "早上好!")

# 每2小时
@on_schedule(cron="0 */2 * * *")
async def bi_hourly_task(self, ctx: Context):
    pass

# 工作日 9:00-17:00 每小时
@on_schedule(cron="0 9-17 * * 1-5")
async def work_hours_check(self, ctx: Context):
    pass
```

#### cron 表达式格式

```
分钟 小时 日 月 星期
*    *    *  *  *

示例:
0 8 * * *      # 每天 8:00
0 */2 * * *    # 每2小时
0 9-17 * * 1-5 # 工作日 9:00-17:00 每小时
*/10 * * * *    # 每10分钟
```

#### 注意事项

1. cron 表达式格式: `分钟 小时 日 月 星期`
2. 不能与 `@rate_limit` 或 `@cooldown` 一起使用
3. 定时任务的 handler 不接收 `MessageEvent` 参数
4. `interval_seconds` 最小值为 60（1分钟）

---

## 修饰器装饰器

### @require_admin

管理员权限装饰器，限制只有管理员才能调用。

#### 签名

```python
def require_admin(func: HandlerCallable) -> HandlerCallable
```

#### 示例

```python
from astrbot_sdk.decorators import on_command, require_admin

@on_command("shutdown")
@require_admin
async def shutdown(self, event: MessageEvent, ctx: Context):
    await event.reply("正在关闭系统...")
```

#### 注意事项

1. 必须放在事件触发装饰器（如 `@on_command`）之后
2. 非管理员用户触发时，handler 不会被调用
3. 别名: `@admin_only()` 功能完全相同

---

## 过滤器装饰器

### @platforms

限定平台装饰器，只在指定平台上触发。

#### 签名

```python
def platforms(*names: str) -> Callable[[HandlerCallable], HandlerCallable]
```

#### 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `*names` | `str` | 是 | 平台名称（可变参数） |

#### 示例

```python
@on_command("qq_only")
@platforms("qq")
async def qq_only(self, event: MessageEvent, ctx: Context):
    await event.reply("这是 QQ 专属命令")

@on_command("multi")
@platforms("qq", "telegram", "discord")
async def multi(self, event: MessageEvent, ctx: Context):
    await event.reply("支持多平台")
```

---

### @message_types

限定消息类型装饰器。

#### 签名

```python
def message_types(*types: str) -> Callable[[HandlerCallable], HandlerCallable]
```

#### 示例

```python
@on_command("group_only")
@message_types("group")
async def group_only(self, event: MessageEvent, ctx: Context):
    await event.reply("这是群聊命令")
```

---

### @group_only

仅群聊装饰器。

#### 签名

```python
def group_only() -> Callable[[HandlerCallable], HandlerCallable]
```

#### 示例

```python
@on_command("group_admin")
@group_only()
async def group_admin(self, event: MessageEvent, ctx: Context):
    await event.reply("这是群聊管理命令")
```

#### 注意事项

功能等同于 `@message_types("group")`

---

### @private_only

仅私聊装饰器。

#### 签名

```python
def private_only() -> Callable[[HandlerCallable], HandlerCallable]
```

#### 示例

```python
@on_command("private_chat")
@private_only()
async def private_only(self, event: MessageEvent, ctx: Context):
    await event.reply("这是私聊命令")
```

---

## 限制器装饰器

### @rate_limit

速率限制装饰器，限制时间窗口内的调用次数。

#### 签名

```python
def rate_limit(
    limit: int,
    window: float,
    *,
    scope: LimiterScope = "session",
    behavior: LimiterBehavior = "hint",
    message: str | None = None,
) -> Callable[[HandlerCallable], HandlerCallable]
```

#### 参数

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `limit` | `int` | 是 | - | 时间窗口内最大调用次数 |
| `window` | `float` | 是 | - | 时间窗口大小（秒） |
| `scope` | `LimiterScope` | 否 | `"session"` | 限制范围 |
| `behavior` | `LimiterBehavior` | 否 | `"hint"` | 触发限制后的行为 |
| `message` | `str \| None` | 否 | `None` | 自定义提示消息 |

**scope 可选值**:
- `"session"` - 会话级别
- `"user"` - 用户级别
- `"group"` - 群组级别
- `"global"` - 全局级别

**behavior 可选值**:
- `"hint"` - 返回提示消息
- `"silent"` - 静默忽略
- `"error"` - 抛出异常

#### 示例

```python
# 每分钟最多5次
@on_command("search")
@rate_limit(5, 60)
async def search(self, event: MessageEvent, ctx: Context):
    await event.reply("搜索结果...")

# 每用户每小时3次
@on_command("draw")
@rate_limit(3, 3600, scope="user")
async def draw(self, event: MessageEvent, ctx: Context):
    await event.reply("绘图结果...")

# 全局限制，自定义消息
@on_command("global")
@rate_limit(
    10, 60,
    scope="global",
    message="操作过于频繁，请稍后再试"
)
async def global_action(self, event: MessageEvent, ctx: Context):
    await event.reply("执行全局操作")
```

---

### @cooldown

冷却时间装饰器，限制连续调用的间隔。

#### 签名

```python
def cooldown(
    seconds: float,
    *,
    scope: LimiterScope = "session",
    behavior: LimiterBehavior = "hint",
    message: str | None = None,
) -> Callable[[HandlerCallable], HandlerCallable]
```

#### 参数

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `seconds` | `float` | 是 | - | 冷却时间（秒） |
| `scope` | `LimiterScope` | 否 | `"session"` | 限制范围 |
| `behavior` | `LimiterBehavior` | 否 | `"hint"` | 触发限制后的行为 |
| `message` | `str \| None` | 否 | `None` | 自定义提示消息 |

#### 示例

```python
# 30秒冷却
@on_command("cast_skill")
@cooldown(30)
async def cast_skill(self, event: MessageEvent, ctx: Context):
    await event.reply("技能施放成功!")

# 每用户24小时冷却
@on_command("daily_reward")
@cooldown(86400, scope="user")
async def daily_reward(self, event: MessageEvent, ctx: Context):
    await event.reply("领取每日奖励!")

# 群组5分钟冷却
@on_command("group_activity")
@cooldown(300, scope="group")
async def group_activity(self, event: MessageEvent, ctx: Context):
    await event.reply("群活动已开始")
```

#### 注意事项

1. 只适用于 `@on_command` 和 `@on_message`
2. 不能与 `@rate_limit` 叠加使用
3. `cooldown` 本质上是 `limit=1` 的 `rate_limit`

---

## 能力暴露装饰器

### @provide_capability

暴露插件能力给其他插件调用的装饰器。

#### 签名

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
) -> Callable[[HandlerCallable], HandlerCallable]
```

#### 参数

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | `str` | 是 | 能力名称（不能使用保留命名空间） |
| `description` | `str` | 是 | 能力描述 |
| `input_schema` | `dict \| None` | 否* | 输入 JSON Schema |
| `output_schema` | `dict \| None` | 否* | 输出 JSON Schema |
| `input_model` | `type[BaseModel] \| None` | 否* | 输入 pydantic 模型 |
| `output_model` | `type[BaseModel] \| None` | 否* | 输出 pydantic 模型 |
| `supports_stream` | `bool` | 否 | 是否支持流式输出 |
| `cancelable` | `bool` | 否 | 是否可取消 |

*注: `input_schema` 与 `input_model` 二选一，`output_schema` 与 `output_model` 二选一

#### 示例

```python
from pydantic import BaseModel, Field

class CalculateInput(BaseModel):
    x: int = Field(description="第一个数")
    y: int = Field(description="第二个数")

class CalculateOutput(BaseModel):
    result: int = Field(description="计算结果")

@provide_capability(
    "my_plugin.calculate",
    description="执行加法计算",
    input_model=CalculateInput,
    output_model=CalculateOutput
)
async def calculate(self, payload: dict, ctx: Context):
    x = payload["x"]
    y = payload["y"]
    return {"result": x + y}
```

#### 注意事项

1. 保留命名空间（`handler.`, `system.`, `internal.`）不能用于插件能力
2. `input_schema` 和 `input_model` 不能同时提供
3. `output_schema` 和 `output_model` 不能同时提供
4. 能力名称格式建议: `插件名.功能名`

---

## LLM 工具装饰器

### @register_llm_tool

注册 LLM 工具装饰器，使插件函数可被 LLM 调用。

#### 签名

```python
def register_llm_tool(
    name: str | None = None,
    *,
    description: str | None = None,
    parameters_schema: dict[str, Any] | None = None,
    active: bool = True,
) -> Callable[[HandlerCallable], HandlerCallable]
```

#### 参数

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | `str \| None` | 否 | 函数名 | 工具名称 |
| `description` | `str \| None` | 否 | 函数文档字符串首行 | 工具描述 |
| `parameters_schema` | `dict \| None` | 否 | 自动从函数签名推断 | 参数 JSON Schema |
| `active` | `bool` | 否 | `True` | 是否激活 |

#### 示例

```python
# 自动推断参数
@register_llm_tool()
async def get_weather(self, city: str, unit: str = "celsius"):
    """获取指定城市的天气信息"""
    return f"{city} 的天气: 25°C"

# 自定义 schema
@register_llm_tool(
    name="search_database",
    description="搜索数据库中的记录",
    parameters_schema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索关键词"},
            "limit": {"type": "integer", "description": "返回结果数量", "default": 10}
        },
        "required": ["query"]
    },
    active=True
)
async def search_database(self, query: str, limit: int = 10):
    # 实现数据库搜索逻辑
    return {"results": [...]}
```

#### 注意事项

1. 如果不提供 `name`，将使用函数名作为工具名
2. 如果不提供 `description`，将使用函数文档字符串的第一行
3. 如果不提供 `parameters_schema`，会自动从函数签名推断
4. 参数推断时会跳过 `self`, `event`, `ctx`, `context` 等特殊参数

---

### @register_agent

注册 Agent 装饰器，将类注册为 LLM Agent。

#### 签名

```python
def register_agent(
    name: str,
    *,
    description: str = "",
    tool_names: list[str] | None = None,
) -> Callable[[type[BaseAgentRunner]], type[BaseAgentRunner]]
```

#### 参数

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `name` | `str` | 是 | - | Agent 名称 |
| `description` | `str` | 否 | `""` | Agent 描述 |
| `tool_names` | `list[str] \| None` | 否 | `None` | 可用工具名称列表 |

#### 示例

```python
from astrbot_sdk.llm.agents import BaseAgentRunner
from astrbot_sdk.llm.entities import ProviderRequest

class WeatherAgent(BaseAgentRunner):
    async def run(self, ctx: Context, request: ProviderRequest) -> Any:
        # 实现 agent 运行逻辑
        return "天气信息"

class MyPlugin(Star):
    @register_agent("my_agent", description="我的智能助手")
    class MyAgentRunner(BaseAgentRunner):
        async def run(self, ctx: Context, request: ProviderRequest) -> Any:
            return "多工具处理结果"
```

#### 注意事项

1. 必须应用于 `BaseAgentRunner` 的子类
2. `tool_names` 指定该 agent 可以使用的 LLM 工具
3. Agent 的实际执行由 core tool loop 管理

---

## 使用示例

### 示例 1: 基础命令

```python
from astrbot_sdk import Star, Context, MessageEvent
from astrbot_sdk.decorators import on_command

class MyPlugin(Star):
    @on_command("hello")
    async def hello(self, event: MessageEvent, ctx: Context):
        await event.reply(f"你好，{event.sender_name}!")

    @on_command("echo", aliases=["repeat", "say"])
    async def echo(self, event: MessageEvent, text: str):
        await event.reply(f"你说: {text}")
```

---

### 示例 2: 消息匹配

```python
from astrbot_sdk.decorators import on_message

class MyPlugin(Star):
    @on_message(keywords=["帮助", "help"])
    async def help(self, event: MessageEvent, ctx: Context):
        await event.reply("可用命令: /hello, /echo")

    @on_message(regex=r"\d{4,}")
    async def number(self, event: MessageEvent, ctx: Context):
        await event.reply("检测到数字!")
```

---

### 示例 3: 装饰器组合

```python
from astrbot_sdk.decorators import (
    on_command, require_admin, group_only, rate_limit
)

class MyPlugin(Star):
    @on_command("admin")
    @require_admin
    @group_only()
    @rate_limit(5, 60)
    async def admin_cmd(self, event: MessageEvent, ctx: Context):
        await event.reply("管理员群聊命令（每分钟最多5次）")
```

---

### 示例 4: 定时任务

```python
from astrbot_sdk.decorators import on_schedule

class MyPlugin(Star):
    @on_schedule(interval_seconds=3600)
    async def hourly_task(self, ctx: Context):
        # 每小时执行
        pass

    @on_schedule(cron="0 8 * * *")
    async def morning_task(self, ctx: Context):
        # 每天8点执行
        await ctx.platform.send("group_123", "早上好!")
```

---

### 示例 5: LLM 工具注册

```python
from astrbot_sdk import Star
from astrbot_sdk.decorators import register_llm_tool

class MyPlugin(Star):
    @register_llm_tool()
    async def get_time(self) -> str:
        """获取当前时间"""
        import time
        return f"当前时间: {time.strftime('%Y-%m-%d %H:%M:%S')}"

    @register_llm_tool(
        name="calculate",
        description="执行计算",
        parameters_schema={
            "type": "object",
            "properties": {
                "expression": {"type": "string", "description": "数学表达式"}
            },
            "required": ["expression"]
        }
    )
    async def calculate(self, expression: str) -> str:
        try:
            result = eval(expression)
            return f"结果: {result}"
        except Exception as e:
            return f"计算错误: {e}"
```

---

## 注意事项

### 1. 装饰器顺序

正确的装饰器顺序很重要：

```python
@on_command("command")      # 1. 事件触发装饰器
@platforms("qq")            # 2. 过滤器装饰器
@rate_limit(5, 60)          # 3. 限制器装饰器
@require_admin              # 4. 修饰器装饰器
async def my_handler(self, event: MessageEvent, ctx: Context):
    pass
```

### 2. 避免常见陷阱

**不要混用冲突的装饰器**:

```python
# 错误示例
@on_message(platforms=["qq"])
@platforms("wechat")  # 冲突!
async def handler(...): pass

# 正确示例
@on_message(platforms=["qq", "wechat"])
async def handler(...): pass
```

**不要在非消息处理器使用限制器**:

```python
# 错误示例
@on_event("ready")
@rate_limit(5, 60)  # 不支持!
async def handler(...): pass

# 正确示例
@on_command("cmd")
@rate_limit(5, 60)
async def handler(...): pass
```

### 3. 类型注解建议

使用类型注解提高代码可读性：

```python
from typing import Optional

@on_command("greet")
async def greet_handler(
    self,
    event: MessageEvent,
    ctx: Context
) -> None:
    await event.reply("Hello!")
```

---

## 相关模块

- **装饰器实现**: `astrbot_sdk.decorators`
- **协议描述符**: `astrbot_sdk.protocol.descriptors`
- **事件定义**: `astrbot_sdk.events`
- **LLM 实体**: `astrbot_sdk.llm.entities`

---

**版本**: v4.0
**模块**: `astrbot_sdk.decorators`
**最后更新**: 2026-03-17
