# AstrBot SDK v4 API 参考

本文档提供 AstrBot SDK v4 的完整 API 参考。

## 目录

- [核心概念](#核心概念)
- [顶层 API](#顶层-api)
- [装饰器](#装饰器)
- [Context 上下文](#context-上下文)
- [MessageEvent 消息事件](#messageevent-消息事件)
- [客户端 API](#客户端-api)
- [错误处理](#错误处理)
- [测试工具](#测试工具)

---

## 核心概念

AstrBot SDK v4 采用**协议优先**的设计，插件与宿主通过显式协议消息交互：

```
┌─────────────────┐
│   插件代码       │
├─────────────────┤
│  Context        │  ← 运行时上下文
│  ├─ llm         │  ← LLM 客户端
│  ├─ memory      │  ← 记忆客户端
│  ├─ db          │  ← 数据库客户端
│  └─ platform    │  ← 平台客户端
├─────────────────┤
│  CapabilityProxy│  ← 能力代理
├─────────────────┤
│  Peer           │  ← 对等节点通信
└─────────────────┘
```

---

## 顶层 API

从 `astrbot_sdk` 直接导入的推荐入口：

```python
from astrbot_sdk import (
    Star,           # 插件基类
    Context,        # 运行时上下文
    MessageEvent,   # 消息事件
    AstrBotError,   # 错误类型
    on_command,     # 命令装饰器
    on_message,     # 消息装饰器
    on_event,       # 事件装饰器
    on_schedule,    # 定时任务装饰器
    provide_capability,  # 能力提供装饰器
    require_admin,  # 管理员权限装饰器
)
```

---

## 装饰器

### @on_command

注册命令处理器。

```python
@on_command(
    command: str,              # 命令名称
    *,
    aliases: list[str] | None = None,    # 命令别名
    description: str | None = None,      # 命令描述
)
```

**示例**：

```python
@on_command("hello", aliases=["hi"], description="发送问候")
async def hello(self, event: MessageEvent, ctx: Context):
    await event.reply("Hello!")
```

### @on_message

注册消息处理器，支持正则匹配或关键词匹配。

```python
@on_message(
    *,
    regex: str | None = None,           # 正则表达式
    keywords: list[str] | None = None,  # 关键词列表
    platforms: list[str] | None = None, # 平台过滤
)
```

**示例**：

```python
@on_message(regex=r"^ping$")
async def ping(self, event: MessageEvent):
    await event.reply("pong")

@on_message(keywords=["帮助", "help"])
async def help_handler(self, event: MessageEvent):
    await event.reply("这是帮助信息...")
```

### @on_event

注册事件处理器。

```python
@on_event(event_type: str)  # 事件类型
```

**常见事件类型**：
- `"message"` - 消息事件
- `"group_join"` - 群加入事件
- `"group_leave"` - 群退出事件
- `"friend_add"` - 好友添加事件

**示例**：

```python
@on_event("group_join")
async def on_group_join(self, event: MessageEvent, ctx: Context):
    await ctx.platform.send(event.session_id, "欢迎加入群组！")
```

### @on_schedule

注册定时任务。

```python
@on_schedule(
    *,
    cron: str | None = None,        # Cron 表达式
    interval_seconds: int | None = None,  # 间隔秒数
)
```

**示例**：

```python
# 每 60 秒执行一次
@on_schedule(interval_seconds=60)
async def heartbeat(self, ctx: Context):
    await ctx.db.set("last_heartbeat", {"time": "now"})

# 使用 cron 表达式（每天 9 点）
@on_schedule(cron="0 9 * * *")
async def daily_greeting(self, ctx: Context):
    pass
```

### @require_admin

要求管理员权限才能执行。

```python
@require_admin
@on_command("admin")
async def admin_only(self, event: MessageEvent):
    await event.reply("管理员命令已执行")
```

### @provide_capability

声明插件对外暴露的能力。

```python
@provide_capability(
    name: str,                              # 能力名称
    *,
    description: str,                       # 能力描述
    input_schema: dict | None = None,       # 输入 JSON Schema
    output_schema: dict | None = None,      # 输出 JSON Schema
    supports_stream: bool = False,          # 是否支持流式
    cancelable: bool = False,               # 是否可取消
)
```

**示例**：

```python
@provide_capability(
    "demo.echo",
    description="回显输入文本",
    input_schema={
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
    output_schema={
        "type": "object",
        "properties": {"echo": {"type": "string"}},
    },
)
async def echo_capability(self, payload: dict, ctx: Context, cancel_token):
    return {"echo": payload.get("text", "")}
```

---

## Context 上下文

运行时上下文，提供所有能力客户端。

```python
class Context:
    llm: LLMClient         # LLM 客户端
    memory: MemoryClient   # 记忆客户端
    db: DBClient           # 数据库客户端
    platform: PlatformClient  # 平台客户端
    plugin_id: str         # 插件 ID
    logger: Logger         # 日志器
    cancel_token: CancelToken  # 取消令牌
```

### CancelToken

取消信号，用于处理中断请求。

```python
class CancelToken:
    @property
    def cancelled(self) -> bool  # 是否已取消

    def cancel(self) -> None      # 发送取消信号

    async def wait(self) -> None  # 等待取消

    def raise_if_cancelled(self) -> None  # 如果已取消则抛出异常
```

**示例**：

```python
async def long_task(self, ctx: Context):
    for i in range(100):
        ctx.cancel_token.raise_if_cancelled()  # 检查取消信号
        await asyncio.sleep(1)
```

---

## MessageEvent 消息事件

消息事件对象，包含消息信息和操作方法。

```python
class MessageEvent:
    text: str              # 消息文本
    user_id: str | None    # 用户 ID
    session_id: str        # 会话 ID
    group_id: str | None   # 群组 ID（私聊为 None）
    platform: str          # 平台名称
    raw: dict              # 原始消息数据
```

### 方法

#### event.reply()

回复消息。

```python
async def reply(self, text: str) -> None
```

**示例**：

```python
await event.reply("收到您的消息！")
```

#### event.plain_result()

创建纯文本结果。

```python
def plain_result(self, text: str) -> MessageEventResult
```

**示例**：

```python
return event.plain_result("处理完成")
```

#### event.to_payload()

转换为字典格式。

```python
def to_payload(self) -> dict[str, Any]
```

#### event.session_ref

获取结构化会话引用。

```python
@property
def session_ref(self) -> SessionRef | None
```

---

## 客户端 API

### LLMClient

[详细文档](clients/llm.md)

```python
# 简单对话
reply = await ctx.llm.chat("你好")

# 带历史对话
reply = await ctx.llm.chat("继续", history=[
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！"},
])

# 流式对话
async for chunk in ctx.llm.stream_chat("讲个故事"):
    print(chunk, end="")
```

### DBClient

[详细文档](clients/db.md)

```python
# 读写数据
await ctx.db.set("user:1", {"name": "张三"})
data = await ctx.db.get("user:1")

# 前缀查询
keys = await ctx.db.list("user:")

# 批量操作
await ctx.db.set_many({"a": 1, "b": 2})
values = await ctx.db.get_many(["a", "b"])
```

### MemoryClient

[详细文档](clients/memory.md)

```python
# 保存记忆
await ctx.memory.save("user_pref", {"theme": "dark"})

# 语义搜索
results = await ctx.memory.search("用户偏好")

# 精确获取
pref = await ctx.memory.get("user_pref")
```

### PlatformClient

[详细文档](clients/platform.md)

```python
# 发送消息
await ctx.platform.send(event.session_id, "你好")

# 发送图片
await ctx.platform.send_image(event.session_id, "https://example.com/img.png")

# 获取群成员
members = await ctx.platform.get_members(event.session_id)
```

---

## 错误处理

### AstrBotError

统一的错误类型。

```python
class AstrBotError(Exception):
    code: str       # 错误码
    message: str    # 错误消息
    hint: str       # 解决建议
    retryable: bool # 是否可重试
```

### 错误码

| 错误码 | 说明 | 可重试 |
|--------|------|--------|
| `llm_not_configured` | LLM 未配置 | 否 |
| `capability_not_found` | 能力未找到 | 否 |
| `permission_denied` | 权限不足 | 否 |
| `invalid_input` | 输入无效 | 否 |
| `cancelled` | 操作已取消 | 否 |
| `capability_timeout` | 能力调用超时 | 是 |
| `network_error` | 网络错误 | 是 |

**示例**：

```python
from astrbot_sdk import AstrBotError

try:
    result = await ctx.llm.chat("hello")
except AstrBotError as e:
    print(f"[{e.code}] {e.message}")
    if e.hint:
        print(f"建议: {e.hint}")
```

---

## 测试工具

### MockContext

用于单元测试的模拟上下文。

```python
from astrbot_sdk.testing import MockContext, MockMessageEvent

ctx = MockContext(plugin_id="test")
event = MockMessageEvent(text="hello", context=ctx)

# 模拟 LLM 响应
ctx.llm.mock_response("你好！")

# 断言发送内容
await event.reply("测试")
ctx.platform.assert_sent("测试")
```

### PluginHarness

完整的插件测试工具。

```python
from astrbot_sdk.testing import PluginHarness, LocalRuntimeConfig

harness = PluginHarness(
    LocalRuntimeConfig(plugin_dir=Path("my-plugin"))
)

async with harness:
    records = await harness.dispatch_text("hello")
    assert any(r.text for r in records)
```

---

## 更多资源

- [快速开始](quickstart.md)
- [LLM 客户端文档](clients/llm.md)
- [数据库客户端文档](clients/db.md)
- [平台客户端文档](clients/platform.md)
- [记忆客户端文档](clients/memory.md)
- [架构设计](../../ARCHITECTURE.md)
