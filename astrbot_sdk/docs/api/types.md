# 类型定义 API 完整参考

## 概述

本文档介绍 AstrBot SDK 中常用的类型定义，包括类型别名、泛型变量和类型注解。

**模块路径**: 分布在各个 SDK 模块中

---

## 目录

- [类型别名](#类型别名)
- [泛型变量](#泛型变量)
- [特殊类型](#特殊类型)
- [使用示例](#使用示例)

---

## 导入方式

```python
# 类型别名
from astrbot_sdk.context import PlatformCompatContent
from astrbot_sdk.clients.llm import ChatMessage, ChatHistoryItem, LLMResponse

# 泛型变量（通常不需要直接导入）
from astrbot_sdk.session_waiter import _P, _ResultT, _OwnerT
from astrbot_sdk.plugin_kv import _VT

# 通用类型
from typing import Callable, Awaitable, Any, Sequence, Mapping

HandlerType = Callable[..., Awaitable[Any]]
FilterType = Callable[..., Awaitable[bool]]
```

---

## 类型别名

### PlatformCompatContent

平台兼容的内容类型，用于表示可以发送到平台的各种消息格式。

**定义位置**: `astrbot_sdk.context`

**定义**:

```python
from collections.abc import Sequence
from typing import Any

PlatformCompatContent = (
    str | MessageChain | Sequence[BaseMessageComponent] | Sequence[dict[str, Any]]
)
```

**说明**:

此类型别名表示可以用于平台发送方法的内容类型，支持以下四种格式：

| 格式 | 说明 | 示例 |
|------|------|------|
| `str` | 纯文本字符串 | `"Hello World"` |
| `MessageChain` | 消息链对象 | `MessageChain([Plain("Hi")])` |
| `Sequence[BaseMessageComponent]` | 消息组件列表 | `[Plain("Hi"), At("123")]` |
| `Sequence[dict[str, Any]]` | 序列化后的字典列表 | `[{"type": "text", "data": {"text": "Hi"}}]` |

**使用位置**:

- `Context.send_message()`
- `Context.send_message_by_id()`
- `PlatformClient.send_by_session()`
- `StarTools.send_message()`

**示例**:

```python
from astrbot_sdk import Plain, Image, MessageChain

# 纯文本
await ctx.platform.send_by_session("session_id", "Hello")

# 消息链
chain = MessageChain([Plain("Hello"), Image.fromURL("...")])
await ctx.platform.send_by_session("session_id", chain)

# 组件列表
await ctx.platform.send_by_session("session_id", [
    Plain("Hello"),
    At("123456")
])

# 字典列表
await ctx.platform.send_by_session("session_id", [
    {"type": "text", "data": {"text": "Hello"}}
])
```

---

### ChatHistoryItem

聊天历史项类型，用于构建对话历史。

**定义位置**: `astrbot_sdk.clients.llm`

**定义**:

```python
from collections.abc import Mapping
from typing import Any
from pydantic import BaseModel

class ChatMessage(BaseModel):
    role: str
    content: str

ChatHistoryItem = ChatMessage | Mapping[str, Any]
```

**说明**:

此类型别名表示对话历史中的一项，可以是 `ChatMessage` 对象或任何字典类型的映射。

**支持格式**:

| 格式 | 说明 | 示例 |
|------|------|------|
| `ChatMessage` | Pydantic 模型对象 | `ChatMessage(role="user", content="Hi")` |
| `Mapping[str, Any]` | 字典类型 | `{"role": "user", "content": "Hi"}` |

**使用位置**:

- `LLMClient.chat()` - `history` 参数
- `LLMClient.chat_raw()` - `history` 参数
- `LLMClient.stream_chat()` - `history` 参数

**示例**:

```python
from astrbot_sdk.clients.llm import ChatMessage

# 使用 ChatMessage 对象
history = [
    ChatMessage(role="user", content="你好"),
    ChatMessage(role="assistant", content="你好！"),
]

# 使用字典
history = [
    {"role": "user", "content": "你好"},
    {"role": "assistant", "content": "你好！"},
]

# 混合使用
history = [
    ChatMessage(role="user", content="你好"),
    {"role": "assistant", "content": "你好！"},
    {"role": "user", "content":今天天气怎么样？"},
]
```

---

## 泛型变量

SDK 内部使用的泛型类型变量，用于类型注解。

### `_P` - 参数规范

**定义位置**: `astrbot_sdk.session_waiter`

**定义**:

```python
from typing import ParamSpec

_P = ParamSpec("_P")
```

**说明**:

用于捕获可调用对象的参数签名，主要在装饰器中使用。

---

### `_ResultT` - 结果类型

**定义位置**: `astrbot_sdk.session_waiter`

**定义**:

```python
from typing import TypeVar

_ResultT = TypeVar("_ResultT")
```

**说明**:

表示异步函数的返回结果类型。

---

### `_OwnerT` - 所有者类型

**定义位置**: `astrbot_sdk.session_waiter`

**定义**:

```python
_OwnerT = TypeVar("_OwnerT")
```

**说明**:

表示类的所有者类型（通常是 `Star` 子类）。

---

### `_VT` - 值类型

**定义位置**: `astrbot_sdk.plugin_kv`

**定义**:

```python
_VT = TypeVar("_VT")
```

**说明**:

用于 KV 存储中默认值的类型。

**使用位置**:

- `PluginKVStoreMixin.get_kv_data()` - `default` 参数的类型注解

**示例**:

```python
# default 参数的类型会根据传入的值自动推断
value = await self.get_kv_data("key", default="default")  # _VT 推断为 str
count = await self.get_kv_data("count", default=0)        # _VT 推断为 int
```

---

## 特殊类型

### HandlerType

事件处理器函数类型。

**定义**:

```python
from typing import Callable, Awaitable, Any

HandlerType = Callable[..., Awaitable[Any]]
```

**说明**:

表示事件处理器的函数签名，接受任意参数并返回异步结果。

**特征**:
- 可变参数 (`...`)
- 异步返回 (`Awaitable[Any]`)

**示例**:

```python
async def my_handler(event: MessageEvent, ctx: Context) -> None:
    pass

# 符合 HandlerType 类型
```

---

### FilterType

过滤器函数类型。

**定义**:

```python
FilterType = Callable[..., Awaitable[bool]]
```

**说明**:

表示过滤器函数的类型，返回布尔值。

**特征**:
- 可变参数 (`...`)
- 异步返回布尔值 (`Awaitable[bool]`)

**示例**:

```python
async def my_filter(event: MessageEvent, ctx: Context) -> bool:
    return event.platform == "qq"

# 符合 FilterType 类型
```

---

## Pydantic 模型类型

### ChatMessage

聊天消息模型，用于构建对话历史。

**定义位置**: `astrbot_sdk.clients.llm`

**定义**:

```python
from pydantic import BaseModel

class ChatMessage(BaseModel):
    """聊天消息模型。"""
    role: str
    content: str
```

**属性**:

| 属性 | 类型 | 说明 |
|------|------|------|
| `role` | `str` | 消息角色，如 `"user"`, `"assistant"`, `"system"` |
| `content` | `str` | 消息内容 |

**示例**:

```python
from astrbot_sdk.clients.llm import ChatMessage

# 系统提示
system_msg = ChatMessage(
    role="system",
    content="你是一个友好的助手"
)

# 用户消息
user_msg = ChatMessage(
    role="user",
    content="你好"
)

# 助手回复
assistant_msg = ChatMessage(
    role="assistant",
    content="你好！有什么可以帮助你的？"
)
```

---

### LLMResponse

LLM 响应模型，包含完整的响应信息。

**定义位置**: `astrbot_sdk.clients.llm`

**定义**:

```python
from pydantic import BaseModel, Field

class LLMResponse(BaseModel):
    """LLM 响应模型。"""
    text: str
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    role: str | None = None
    reasoning_content: str | None = None
    reasoning_signature: str | None = None
```

**属性**:

| 属性 | 类型 | 说明 |
|------|------|------|
| `text` | `str` | 生成的文本内容 |
| `usage` | `dict[str, Any] \| None` | Token 使用统计 |
| `finish_reason` | `str \| None` | 结束原因（`"stop"`, `"length"`, `"tool_calls"`） |
| `tool_calls` | `list[dict[str, Any]]` | 工具调用列表 |
| `role` | `str \| None` | 响应角色 |
| `reasoning_content` | `str \| None` | 推理内容（用于推理模型） |
| `reasoning_signature` | `str \| None` | 推理签名 |

**示例**:

```python
from astrbot_sdk.clients.llm import LLMResponse

response = await ctx.llm.chat_raw("写一首诗")

print(f"生成内容: {response.text}")
print(f"Token 使用: {response.usage}")
print(f"结束原因: {response.finish_reason}")

if response.usage:
    print(f"提示词 Token: {response.usage.get('prompt_tokens')}")
    print(f"完成 Token: {response.usage.get('completion_tokens')}")
```

---

## 使用示例

### 类型注解在函数签名中的使用

```python
from typing import Sequence, Mapping, Any
from astrbot_sdk.clients.llm import ChatMessage, ChatHistoryItem
from astrbot_sdk import MessageChain, BaseMessageComponent, PlatformCompatContent

# 使用 ChatHistoryItem
async def chat_with_history(
    prompt: str,
    history: Sequence[ChatHistoryItem] | None = None
) -> str:
    """与 LLM 聊天的函数。"""
    pass

# 使用 PlatformCompatContent
async def send_content(
    session: str,
    content: PlatformCompatContent
) -> dict[str, Any]:
    """发送内容的函数。"""
    pass
```

### 类型检查和类型守卫

```python
from collections.abc import Mapping, Sequence
from astrbot_sdk.clients.llm import ChatMessage, ChatHistoryItem

def normalize_history_item(item: ChatHistoryItem) -> dict[str, Any]:
    """将聊天历史项规范化为字典。"""
    if isinstance(item, ChatMessage):
        return item.model_dump()
    if isinstance(item, Mapping):
        return dict(item)
    raise TypeError("无效的聊天历史项类型")

# 使用
history: Sequence[ChatHistoryItem] = [
    ChatMessage(role="user", content="Hi"),
    {"role": "assistant", "content": "Hello"},
]

normalized = [normalize_history_item(item) for item in history]
```

### 泛型函数

```python
from typing import TypeVar, Generic

T = TypeVar("T")

class Container(Generic[T]):
    def __init__(self, value: T) -> None:
        self.value = value

    def get(self) -> T:
        return self.value

# 使用
int_container: Container[int] = Container(42)
str_container: Container[str] = Container("hello")
```

---

## 相关模块

- **LLM 客户端**: `astrbot_sdk.clients.LLMClient`
- **消息组件**: `astrbot_sdk.message_components`
- **消息链**: `astrbot_sdk.message_result.MessageChain`
- **上下文**: `astrbot_sdk.context.Context`

---

**版本**: v4.0
**最后更新**: 2026-03-17
