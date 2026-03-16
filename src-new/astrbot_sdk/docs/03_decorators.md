# AstrBot SDK 装饰器使用指南

## 概述

本文档详细介绍 `astrbot_sdk.decorators` 中所有装饰器的使用方法、参数说明和最佳实践。

## 目录

- [事件触发装饰器](#事件触发装饰器)
- [修饰器装饰器](#修饰器装饰器)
- [过滤器装饰器](#过滤器装饰器)
- [限制器装饰器](#限制器装饰器)
- [能力暴露装饰器](#能力暴露装饰器)
- [LLM 工具装饰器](#llm-工具装饰器)
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
- `command`: 命令名称（不包含前缀符）
- `aliases`: 命令别名列表
- `description`: 命令描述

**示例：**

```python
from astrbot_sdk.decorators import on_command

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
) -> Callable
```

**参数：**
- `regex`: 正则表达式模式
- `keywords`: 关键词列表（任一匹配即触发）
- `platforms`: 限定平台列表
- `message_types`: 限定消息类型（"group", "private"）

**示例：**

```python
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
def on_event(event_type: str) -> Callable
```

**示例：**

```python
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
) -> Callable
```

**示例：**

```python
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

**示例：**

```python
from astrbot_sdk.decorators import on_command, require_admin

@on_command("admin")
@require_admin
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
@on_command("qq_only")
@platforms("qq")
async def qq_only_command(self, event: MessageEvent, ctx: Context):
    await event.reply("这是 QQ 专属命令")
```

### @message_types

限定消息类型装饰器。

**签名：**
```python
def message_types(*types: str) -> Callable
```

**示例：**

```python
@on_command("group_only")
@message_types("group")
async def group_command(self, event: MessageEvent, ctx: Context):
    await event.reply("这是群聊命令")
```

### @group_only

仅群聊装饰器。

```python
@on_command("group_admin")
@group_only()
async def group_admin_command(self, event: MessageEvent, ctx: Context):
    await event.reply("这是群聊管理命令")
```

### @private_only

仅私聊装饰器。

```python
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

**示例：**

```python
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

**示例：**

```python
@on_command("cast_skill")
@cooldown(30)  # 30秒冷却
async def cast_skill_command(self, event: MessageEvent, ctx: Context):
    await event.reply("技能施放成功!")
```

---

## 能力暴露装饰器

### @provide_capability

暴露能力装饰器。

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

**示例：**

```python
from pydantic import BaseModel, Field
from astrbot_sdk.decorators import provide_capability

class CalculateInput(BaseModel):
    x: int = Field(description="第一个数")
    y: int = Field(description="第二个数")

@provide_capability(
    "my_plugin.calculate",
    description="执行加法计算",
    input_model=CalculateInput
)
async def calculate(self, payload: dict, ctx: Context):
    x = payload["x"]
    y = payload["y"]
    return {"result": x + y}
```

---

## LLM 工具装饰器

### @register_llm_tool

注册 LLM 工具装饰器。

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

**示例：**

```python
from astrbot_sdk.decorators import register_llm_tool

@register_llm_tool()
async def get_weather(self, city: str, unit: str = "celsius"):
    """获取指定城市的天气信息"""
    return f"{city} 的天气: 25°C"
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

**示例：**

```python
from astrbot_sdk.decorators import register_agent
from astrbot_sdk.llm.agents import BaseAgentRunner

@register_agent("my_agent", description="我的智能助手")
class MyAgent(BaseAgentRunner):
    async def run(self, ctx: Context, request) -> Any:
        return "agent result"
```

---

## 最佳实践

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

### 2. 错误处理

始终实现错误处理：

```python
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
