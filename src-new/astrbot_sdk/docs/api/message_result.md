# 消息结果 API 完整参考

## 概述

消息结果是用于构建和返回消息结果的类，包括消息链容器、流式构建器和事件结果包装器。

**模块路径**: `astrbot_sdk.message_result`

---

## 目录

- [EventResultType - 事件结果类型枚举](#eventresulttype---事件结果类型枚举)
- [MessageChain - 消息链](#messagechain---消息链)
- [MessageBuilder - 消息构建器](#messagebuilder---消息构建器)
- [MessageEventResult - 消息事件结果](#messageeventresult---消息事件结果)

---

## 导入方式

```python
# 从主模块导入
from astrbot_sdk import MessageChain, MessageBuilder, MessageEventResult

# 从子模块导入
from astrbot_sdk.message_result import (
    MessageChain,
    MessageBuilder,
    MessageEventResult,
    EventResultType,
)

# 消息组件（用于构建消息链）
from astrbot_sdk.message_components import Plain, At, Image, File
```

---

## EventResultType - 事件结果类型枚举

事件结果的类型枚举，定义消息结果的类型。

### 定义

```python
class EventResultType(str, Enum):
    EMPTY = "empty"      # 空结果
    CHAIN = "chain"      # 消息链结果
    PLAIN = "plain"      # 纯文本结果
```

### 值说明

| 值 | 说明 |
|------|------|
| `EventResultType.EMPTY` | 空结果，不返回任何内容 |
| `EventResultType.CHAIN` | 消息链结果，返回一个或多个消息组件 |
| `EventResultType.PLAIN` | 纯文本结果，返回文本内容 |

---

## MessageChain - 消息链

消息链是消息组件的容器，用于组合多个组件形成复杂的消息。

### 类定义

```python
@dataclass(slots=True)
class MessageChain:
    components: list[BaseMessageComponent] = field(default_factory=list)
```

### 构造方法

#### 空消息链

```python
from astrbot_sdk.message_result import MessageChain

chain = MessageChain()
```

#### 带初始组件

```python
from astrbot_sdk.message_result import MessageChain
from astrbot_sdk.message_components import Plain, At

chain = MessageChain([
    Plain("Hello"),
    At("123456")
])
```

### 实例方法

#### `append(component)`

追加单个组件，返回 self 支持链式调用。

```python
def append(self, component: BaseMessageComponent) -> MessageChain:
    """追加单个组件，返回 self"""
    self.components.append(component)
    return self
```

**参数**:
- `component` (`BaseMessageComponent`): 要追加的组件

**返回**: `MessageChain` - self

**示例**:

```python
chain = MessageChain()
chain.append(Plain("Hello "))
    .append(At("123456"))
    .append(Plain("!"))
```

---

#### `extend(components)`

追加多个组件，返回 self。

```python
def extend(self, components: list[BaseMessageComponent]) -> MessageChain:
    """追加多个组件，返回 self"""
    self.components.extend(components)
    return self
```

**参数**:
- `components` (`list[BaseMessageComponent]`): 组件列表

**示例**:

```python
chain = MessageChain()
chain.extend([
    Plain("A"),
    Plain("B"),
    Plain("C")
])
```

---

#### `to_payload()`

同步转换为协议 payload。

```python
def to_payload(self) -> list[dict[str, Any]]:
    """转换为协议 payload"""
    return [component_to_payload_sync(c) for c in self.components]
```

**返回**: `list[dict]` - 可序列化的字典列表

---

#### `to_payload_async()`

异步转换为协议 payload。

```python
async def to_payload_async(self) -> list[dict[str, Any]]:
    """异步转换为协议 payload"""
    return [await component_to_payload(c) for c in self.components]
```

**注意**: 某些组件（如 Reply）的异步序列化可能包含额外逻辑

---

#### `get_plain_text(with_other_comps_mark=False)`

提取纯文本内容。

```python
def get_plain_text(self, with_other_comps_mark: bool = False) -> str:
    """提取纯文本内容"""
    texts: list[str] = []
    for component in self.components:
        if isinstance(component, Plain):
            texts.append(component.text)
        elif with_other_comps_mark:
            texts.append(f"[{component.__class__.__name__}]")
    return " ".join(texts)
```

**参数**:
- `with_other_comps_mark`: 是否为非文本组件显示类型标记

**返回**: `str` - 纯文本内容

**示例**:

```python
chain = MessageChain([
    Plain("Hello "),
    At("123456"),
    Plain("!")
])

chain.get_plain_text()       # "Hello !"
chain.get_plain_text(True)    # "Hello [At] !"
```

---

#### `plain_text(with_other_comps_mark=False)`

`get_plain_text()` 的别名。

```python
def plain_text(self, with_other_comps_mark: bool = False) -> str:
    return self.get_plain_text(with_other_comps_mark=with_other_comps_mark)
```

---

### 迭代与长度

```python
# 迭代
for component in chain:
    print(f"组件: {component.__class__.__name__}")

# 长度
len(chain)  # 组件数量
```

---

### 使用示例

```python
from astrbot_sdk.message_result import MessageChain
from astrbot_sdk.message_components import Plain, At, Image

# 创建并使用
chain = MessageChain([
    Plain("Hello "),
    At("123456"),
    Plain("!"),
    Image.fromURL("https://example.com/img.jpg")
])

# 转换为 payload
payload = chain.to_payload()

# 提取文本
text = chain.get_plain_text()

# 链式追加
chain.append(Plain("More text"))
```

---

## MessageBuilder - 消息构建器

流式构建消息链的工具类，提供流畅的 API。

### 类定义

```python
@dataclass(slots=True)
class MessageBuilder:
    components: list[BaseMessageComponent] = field(default_factory=list)
```

### 链式方法

所有方法都返回 `self`，支持链式调用。

#### `text(content)`

添加文本组件。

```python
def text(self, content: str) -> MessageBuilder:
    """添加文本组件"""
    self.components.append(Plain(content, convert=False))
    return self
```

**示例**:

```python
builder = MessageBuilder()
builder.text("Hello ")
```

---

#### `at(user_id)`

添加@组件。

```python
def at(self, user_id: str) -> MessageBuilder:
    """添加@用户"""
    self.components.append(At(user_id))
    return self
```

---

#### `at_all()`

添加@全体成员。

```python
def at_all(self) -> MessageBuilder:
    """添加@全体成员"""
    self.components.append(AtAll())
    return self
```

---

#### `image(url)`

添加图片。

```python
def image(self, url: str) -> MessageBuilder:
    """添加图片"""
    self.components.append(Image.fromURL(url))
    return self
```

---

#### `record(url)`

添加语音。

```python
def record(self, url: str) -> MessageBuilder:
    """添加语音"""
    self.components.append(Record.fromURL(url))
    return self
```

---

#### `video(url)`

添加视频。

```python
def video(self, url: str) -> MessageBuilder:
    """添加视频"""
    self.components.append(Video.fromURL(url))
    return self
```

---

#### `file(name, *, file="", url="")`

添加文件。

```python
def file(self, name: str, *, file: str = "", url: str = "") -> MessageBuilder:
    """添加文件"""
    self.components.append(File(name=name, file=file, url=url))
    return self
```

---

#### `reply(**kwargs)`

添加回复组件。

```python
def reply(self, **kwargs: Any) -> MessageBuilder:
    """添加回复组件"""
    self.components.append(Reply(**kwargs))
    return self
```

---

#### `append(component)`

添加任意组件。

```python
def append(self, component: BaseMessageComponent) -> MessageBuilder:
    """添加任意组件"""
    self.components.append(component)
    return self
```

---

#### `extend(components)`

添加多个组件。

```python
def extend(self, components: list[BaseMessageComponent]) -> MessageBuilder:
    """添加多个组件"""
    self.components.extend(components)
    return self
```

---

#### `build()`

构建 MessageChain。

```python
def build(self) -> MessageChain:
    """构建消息链"""
    return MessageChain(list(self.components))
```

**返回**: `MessageChain` - 包含所有组件的消息链对象

---

### 完整使用示例

```python
from astrbot_sdk.message_result import MessageBuilder
from astrbot_sdk.message_components import Plain, At, Image

# 链式构建
chain = (MessageBuilder()
    .text("Hello ")
    .at("123456")
    .text("!\n")
    .image("https://example.com/img.jpg")
    .build())

# 使用 MessageChain
chain = MessageChain([
    Plain("Hello "),
    At("123456"),
    Plain("!\n"),
    Image.fromURL("https://example.com/img.jpg")
])

# 两种方式结果相同
```

---

## MessageEventResult - 消息事件结果

消息事件结果的包装类，用于 handler 返回值。

### 类定义

```python
@dataclass(slots=True)
class MessageEventResult:
    type: EventResultType = EventResultType.EMPTY
    chain: MessageChain = field(default_factory=MessageChain)
```

### 构造方法

#### 空结果

```python
from astrbot_sdk.message_result import MessageEventResult, EventResultType

result = MessageEventResult()
# 或
result = MessageEventResult(type=EventResultType.EMPTY)
```

---

#### 纯文本结果

```python
result = MessageEventResult(
    type=EventResultType.PLAIN,
    chain=MessageChain([Plain("返回内容")])
)
```

---

#### 消息链结果

```python
from astrbot_sdk.message_result import MessageEventResult, EventResultType, MessageChain
from astrbot_sdk.message_components import Plain, Image

result = MessageEventResult(
    type=EventResultType.CHAIN,
    chain=MessageChain([
        Plain("文本"),
        Image(url="https://example.com/a.png")
    ])
)
```

---

### 实例方法

#### `to_payload()`

转换为协议 payload。

```python
def to_payload(self) -> dict[str, Any]:
    """转换为协议 payload"""
    return {
        "type": self.type.value,
        "chain": self.chain.to_payload(),
    }
```

**返回格式**:

```python
# EMPTY
{"type": "empty", "chain": []}

# CHAIN
{
    "type": "chain",
    "chain": [
        {"type": "text", "data": {"text": "内容"}},
        {"type": "image", "data": {"url": "..."}}
    ]
}

# PLAIN
{
    "type": "plain",
    "chain": [{"type": "text", "data": {"text": "内容"}}]
}
```

---

#### `from_payload(payload)`

从协议 payload 创建实例。

```python
@classmethod
def from_payload(cls, payload: dict[str, Any]) -> MessageEventResult:
    result_type_raw = str(payload.get("type", EventResultType.EMPTY.value))
    try:
        result_type = EventResultType(result_type_raw)
    except ValueError:
        result_type = EventResultType.EMPTY
    chain_payload = payload.get("chain")
    components = (
        payloads_to_components(chain_payload)
        if isinstance(chain_payload, list)
        else []
    )
    return cls(type=result_type, chain=MessageChain(components))
```

---

### 使用示例

```python
@on_command("return_text")
async def return_text(self, event: MessageEvent):
    # 返回纯文本结果
    return event.plain_result("返回内容")

@on_command("return_image")
async def return_image(self, event: MessageEvent):
    # 返回图片结果
    return event.image_result("https://example.com/image.jpg")

@on_command("return_chain")
async def return_chain(self, event: MessageEvent):
    # 返回消息链结果
    return event.chain_result([
        Plain(f"用户: {event.sender_name}"),
        Plain(f"ID: {event.user_id}"),
        Plain(f"平台: {event.platform}"),
    ])
```

---

## 使用场景示例

### 场景1: 使用 MessageBuilder 构建复杂消息

```python
@on_command("rich")
async def rich_message(self, event: MessageEvent):
    chain = (MessageBuilder()
        .text("你好 ")
        .at(event.user_id or "123456")
        .text("!\n\n")
        .image("https://example.com/welcome.jpg")
        .text("这是欢迎图片")
        .build())

    await event.reply_chain(chain)
```

---

### 场景2: 使用 MessageChain 组合组件

```python
@on_command("multi")
async def multi_component(self, event: MessageEvent, count: int):
    components = [Plain(f"发送 {count} 条消息:\n")]

    for i in range(count):
        components.append(Plain(f"{i+1}. "))
        if i < count - 1:
            components.append(Plain("\n"))

    await event.reply_chain(components)
```

---

### 场景3: 返回结构化结果

```python
@on_command("user_info")
async def user_info(self, event: MessageEvent):
    return event.chain_result([
        Plain(f"用户: {event.sender_name}\n"),
        Plain(f"ID: {event.user_id}\n"),
        Plain(f"平台: {event.platform}\n"),
        Plain(f"消息类型: {event.message_type}\n"),
    ])
```

---

## 注意事项

1. **MessageChain 可变性**:
   - `append()` 和 `extend()` 修改原链并返回 self
   - 支持链式调用
   - 注意：链式操作会修改原链

2. **异步序列化**:
   - 大多数情况用 `to_payload()` 即可
   - 包含 `Reply` 组件时建议用 `to_payload_async()`

3. **纯文本提取**:
   - `get_plain_text()` 默认忽略非文本组件
   - 设置 `with_other_comps_mark=True` 显示类型标记

4. **结果类型**:
   - `EMPTY`: 不返回任何内容
   - `CHAIN`: 返回一个或多个消息组件
   - `PLAIN`: 返回文本内容

---

## 相关模块

- **消息组件**: `astrbot_sdk.message_components`
- **事件结果**: `astrbot_sdk.events.MessageEventResult`
- **事件类型**: `astrbot_sdk.events.EventResultType`

---

**版本**: v4.0
**模块**: `astrbot_sdk.message_result`
**最后更新**: 2026-03-17
