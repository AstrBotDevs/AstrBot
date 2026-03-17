# MessageEvent 类 - 消息事件对象完整参考

## 概述

`MessageEvent` 表示接收到的聊天消息事件，包含消息的所有信息（发送者、内容、组件等）和响应方法。当用户发送消息时，AstrBot 会创建一个 `MessageEvent` 实例并传递给插件的事件处理器。

**模块路径**: `astrbot_sdk.events.MessageEvent`

---

## 类定义

```python
class MessageEvent:
    # 基本属性
    text: str                    # 消息文本内容
    user_id: str | None          # 发送者用户 ID
    group_id: str | None         # 群组 ID（私聊时为 None）
    platform: str | None         # 平台标识（如 "qq", "wechat"）
    session_id: str              # 会话 ID
    self_id: str                 # 机器人账号 ID
    platform_id: str             # 平台实例标识
    message_type: str            # 消息类型（"private" 或 "group"）
    sender_name: str             # 发送者昵称
    raw: dict[str, Any]          # 原始消息数据（协议层 payload）
    context: Context | None      # 运行时上下文
```

---

## 导入方式

```python
# 从主模块导入（推荐）
from astrbot_sdk import MessageEvent

# 从子模块导入
from astrbot_sdk.events import MessageEvent

# 常用配套导入
from astrbot_sdk import Context  # 上下文对象
from astrbot_sdk.decorators import on_command, on_message  # 装饰器
```

---

## 基本属性

### 消息内容属性

#### `text`

消息的纯文本内容。

```python
# 类型: str
# 说明: 提取消息中的纯文本部分

@on_message()
async def handler(self, event: MessageEvent):
    print(f"收到消息: {event.text}")
```

**注意**: 此属性只包含文本部分，不包含图片、@等其他组件的内容。

---

### 发送者属性

#### `user_id`

发送者的用户 ID。

```python
# 类型: str | None
# 说明: 发送者的唯一标识符

@on_command("whoami")
async def whoami(self, event: MessageEvent):
    await event.reply(f"你的 ID 是: {event.user_id}")
```

#### `sender_name`

发送者的昵称。

```python
# 类型: str
# 说明: 发送者的显示名称

@on_command("greet")
async def greet(self, event: MessageEvent):
    await event.reply(f"你好，{event.sender_name}!")
```

---

### 会话属性

#### `session_id`

当前会话的唯一标识符。

```python
# 类型: str
# 说明: 群聊时为 group_id，私聊时为 user_id

@on_command("session")
async def session(self, event: MessageEvent):
    await event.reply(f"当前会话: {event.session_id}")
```

#### `group_id`

群组 ID（仅在群聊消息中有值）。

```python
# 类型: str | None
# 说明: 私聊时为 None

@on_command("check_group")
async def check_group(self, event: MessageEvent):
    if event.group_id:
        await event.reply(f"群组 ID: {event.group_id}")
    else:
        await event.reply("这是私聊消息")
```

#### `message_type`

消息类型。

```python
# 类型: str
# 说明: "private"（私聊）或 "group"（群聊）

@on_command("type")
async def msg_type(self, event: MessageEvent):
    await event.reply(f"消息类型: {event.message_type}")
```

---

### 平台属性

#### `platform`

平台标识。

```python
# 类型: str | None
# 说明: 如 "qq", "wechat", "telegram" 等

@on_command("platform")
async def platform(self, event: MessageEvent):
    await event.reply(f"来自平台: {event.platform}")
```

#### `platform_id`

平台实例标识。

```python
# 类型: str
# 说明: 同一平台可能有多个实例（如多个 QQ 账号）

@on_command("platform_id")
async def platform_id(self, event: MessageEvent):
    await event.reply(f"平台实例: {event.platform_id}")
```

#### `self_id`

机器人自己的 ID。

```python
# 类型: str
# 说明: 当前机器人账号在平台上的 ID

@on_command("bot_id")
async def bot_id(self, event: MessageEvent):
    await event.reply(f"机器人 ID: {event.self_id}")
```

---

### 原始数据属性

#### `raw`

原始消息数据（协议层 payload）。

```python
# 类型: dict[str, Any]
# 说明: 包含完整的原始消息数据

@on_command("raw")
async def raw(self, event: MessageEvent):
    # 访问原始数据
    raw_data = event.raw
    print(f"原始数据: {raw_data}")
```

**注意**: 此属性包含完整的协议层数据，格式可能因平台而异。

---

## 消息组件访问方法

### `get_messages()`

获取当前事件的所有 SDK 消息组件。

```python
def get_messages(self) -> list[BaseMessageComponent]:
    """Return SDK message components for the current event."""
```

**返回**: 消息组件列表

**示例**:

```python
@on_command("analyze")
async def analyze(self, event: MessageEvent):
    components = event.get_messages()
    for comp in components:
        print(f"组件类型: {comp.type}")
```

---

### `has_component(type_)`

检查是否包含特定类型的组件。

```python
def has_component(self, type_: type[BaseMessageComponent]) -> bool
```

**参数**:
- `type_`: 组件类型（如 `Image`, `At`, `File`）

**返回**: `bool` - 是否包含该类型组件

**示例**:

```python
@on_command("has_img")
async def has_img(self, event: MessageEvent):
    if event.has_component(Image):
        await event.reply("消息包含图片")
    else:
        await event.reply("消息不包含图片")
```

---

### `get_components(type_)`

获取特定类型的所有组件。

```python
def get_components(self, type_: type[BaseMessageComponent]) -> list[BaseMessageComponent]
```

**参数**:
- `type_`: 组件类型

**返回**: 匹配的组件列表

**示例**:

```python
@on_command("list_at")
async def list_at(self, event: MessageEvent):
    at_comps = event.get_components(At)
    for at in at_comps:
        await event.reply(f"@了用户: {at.qq}")
```

---

### `get_images()`

获取所有图片组件的便捷方法。

```python
def get_images(self) -> list[Image]
```

**返回**: 图片组件列表

**示例**:

```python
@on_message(keywords=["保存图片"])
async def save_images(self, event: MessageEvent):
    images = event.get_images()
    if not images:
        await event.reply("消息中没有图片")
        return

    saved_paths = []
    for img in images:
        try:
            local_path = await img.convert_to_file_path()
            saved_paths.append(local_path)
        except Exception as e:
            await event.reply(f"保存失败: {e}")
            return

    await event.reply(f"已保存 {len(saved_paths)} 张图片")
```

---

### `get_files()`

获取所有文件组件的便捷方法。

```python
def get_files(self) -> list[File]
```

**返回**: 文件组件列表

**示例**:

```python
@on_message(keywords=["文件"])
async def handle_files(self, event: MessageEvent):
    files = event.get_files()
    for file in files:
        await event.reply(f"收到文件: {file.name}")
```

---

### `extract_plain_text()`

提取所有 Plain 组件的文本内容。

```python
def extract_plain_text(self) -> str
```

**返回**: 纯文本内容（拼接所有 Plain 组件）

**注意**: 这会移除所有非文本组件（图片、@等），仅拼接纯文本。

**示例**:

```python
@on_command("gettext")
async def get_text(self, event: MessageEvent):
    text = event.extract_plain_text()
    await event.reply(f"纯文本内容: {text}")
```

---

### `get_at_users()`

获取消息中所有被@的用户ID列表（不包括 @全体成员）。

```python
def get_at_users(self) -> list[str]
```

**返回**: 被@的用户 ID 列表

**示例**:

```python
@on_command("who_at")
async def who_at(self, event: MessageEvent):
    at_users = event.get_at_users()
    if at_users:
        await event.reply(f"你@了这些用户: {', '.join(at_users)}")
    else:
        await event.reply("你没有@任何人")
```

---

## 会话与平台信息方法

### `is_private_chat()` / `is_group_chat()`

判断消息类型。

```python
def is_private_chat(self) -> bool
def is_group_chat(self) -> bool
```

**返回**: `bool` - 是否为对应类型

**示例**:

```python
@on_command("check")
async def check(self, event: MessageEvent):
    if event.is_group_chat():
        await event.reply("这是群聊消息")
        # 获取群组信息
        group_info = await event.get_group()
        if group_info:
            await event.reply(f"群名: {group_info.get('name')}")
    elif event.is_private_chat():
        await event.reply("这是私聊消息")
```

---

### `is_admin()`

判断发送者是否有管理员权限。

```python
def is_admin(self) -> bool
```

**返回**: `bool` - 是否为管理员

**示例**:

```python
@on_command("admin_check")
async def admin_check(self, event: MessageEvent):
    if event.is_admin():
        await event.reply("你是管理员")
    else:
        await event.reply("你不是管理员")
```

---

### `get_group()`

获取当前群组元数据（仅群聊有效）。

```python
async def get_group(self) -> dict[str, Any] | None
```

**返回**: 群组信息字典，失败返回 None

**示例**:

```python
@on_command("group_info")
async def group_info(self, event: MessageEvent):
    if not event.is_group_chat():
        await event.reply("这不是群聊消息")
        return

    group_info = await event.get_group()
    if group_info:
        await event.reply(f"群名: {group_info.get('name')}")
```

---

## 回复与发送方法

### `reply(text)`

回复纯文本消息。

```python
async def reply(self, text: str) -> None
```

**参数**:
- `text`: 要回复的文本内容

**异常**:
- `RuntimeError`: 如果未绑定 reply handler

**示例**:

```python
@on_command("hello")
async def hello(self, event: MessageEvent):
    await event.reply("Hello, World!")
```

---

### `reply_image(image_url)`

回复图片消息。

```python
async def reply_image(self, image_url: str) -> None
```

**参数**:
- `image_url`: 图片 URL

**支持格式**:
- URL: `https://example.com/image.jpg`
- 本地文件: `file:///absolute/path/to/image.jpg`
- Base64: `base64://iVBORw0KGgo...`

**示例**:

```python
@on_command("cat")
async def cat(self, event: MessageEvent):
    await event.reply_image("https://example.com/cat.jpg")

@on_command("local_img")
async def local_img(self, event: MessageEvent):
    await event.reply_image("file:///path/to/local/image.jpg")
```

---

### `reply_chain(chain)`

回复消息链（多类型消息组合）。

```python
async def reply_chain(
    self,
    chain: MessageChain | list[BaseMessageComponent] | list[dict[str, Any]]
) -> None
```

**参数**:
- `chain`: 消息链组件列表

**示例**:

```python
from astrbot_sdk.message_components import Plain, At, Image

@on_command("rich")
async def rich(self, event: MessageEvent):
    # 方式1: 使用 MessageChain
    chain = MessageChain([
        Plain("Hello "),
        At("123456"),
        Plain("!"),
        Image.fromURL("https://example.com/img.jpg")
    ])
    await event.reply_chain(chain)

    # 方式2: 直接传递组件列表
    await event.reply_chain([
        Plain("文本"),
        Image.fromURL("url")
    ])
```

---

### `react(emoji)`

发送表情反应（如果平台支持）。

```python
async def react(self, emoji: str) -> bool
```

**参数**:
- `emoji`: emoji 表情

**返回**: `bool` - 是否平台支持并成功发送

**示例**:

```python
@on_command("react")
async def react_cmd(self, event: MessageEvent):
    supported = await event.react("👍")
    if not supported:
        await event.reply("该平台不支持表情反应")
```

---

### `send_typing()`

发送正在输入状态（如果平台支持）。

```python
async def send_typing(self) -> bool
```

**返回**: `bool` - 是否平台支持并成功发送

---

### `send_streaming(generator, use_fallback=False)`

发送流式消息。

```python
async def send_streaming(
    self,
    generator,
    use_fallback: bool = False
) -> bool
```

**参数**:
- `generator`: 异步生成器
- `use_fallback`: 是否使用降级模式

**示例**:

```python
@on_command("stream")
async def stream_cmd(self, event: MessageEvent):
    async def text_gen():
        parts = ["正在", "处理", "你的", "请求", "..."]
        for part in parts:
            yield part
            await asyncio.sleep(0.5)

    success = await event.send_streaming(text_gen())
    if not success:
        await event.reply("不支持流式消息")
```

---

## 事件控制方法

### `stop_event()`

标记事件为已停止，阻止后续处理器执行。

```python
def stop_event(self) -> None
```

**示例**:

```python
@on_command("admin")
@require_admin
async def admin_cmd(self, event: MessageEvent):
    await event.reply("管理员操作已执行")
    event.stop_event()  # 阻止后续处理器

@on_command("public")
async def public_cmd(self, event: MessageEvent):
    # 如果事件被停止，不会执行
    await event.reply("这是公共命令")
```

---

### `continue_event()`

清除停止标记。

```python
def continue_event(self) -> None
```

---

### `is_stopped()`

检查事件是否已停止。

```python
def is_stopped(self) -> bool
```

---

## Extra 数据管理

### `set_extra(key, value)`

存储 SDK 本地的临时事件数据。

```python
def set_extra(self, key: str, value: Any) -> None
```

**参数**:
- `key`: 键名
- `value`: 值

**示例**:

```python
# 存储数据
event.set_extra("custom_flag", True)
event.set_extra("temp_data", {"count": 5})
```

---

### `get_extra(key, default)`

读取 SDK 本地临时事件数据。

```python
def get_extra(self, key: str | None = None, default: Any = None) -> Any
```

**参数**:
- `key`: 键名，None 时返回全部 extras
- `default`: 默认值

**示例**:

```python
# 读取单个值
flag = event.get_extra("custom_flag", False)

# 读取全部
all_extras = event.get_extra()
```

---

### `clear_extra()`

清除所有 extra 数据。

```python
def clear_extra(self) -> None
```

---

## 结果构建方法

### `plain_result(text)`

创建纯文本结果对象。

```python
def plain_result(self, text: str) -> PlainTextResult
```

**示例**:

```python
@on_command("test")
async def test(self, event: MessageEvent):
    return event.plain_result("返回内容")
```

---

### `image_result(url_or_path)`

创建包含单个图片的链结果。

```python
def image_result(self, url_or_path: str) -> MessageEventResult
```

**参数**:
- `url_or_path`: URL 或本地路径

**支持格式**:
- URL: `https://example.com/image.jpg`
- 本地路径: `/path/to/image.jpg`
- Base64: `base64://iVBORw0KGgo...`

**示例**:

```python
@on_command("avatar")
async def avatar(self, event: MessageEvent):
    return event.image_result("https://example.com/avatar.jpg")
```

---

### `chain_result(chain)`

从 SDK 组件创建链结果。

```python
def chain_result(
    self,
    chain: MessageChain | list[BaseMessageComponent]
) -> MessageEventResult
```

**示例**:

```python
@on_command("info")
async def info(self, event: MessageEvent):
    return event.chain_result([
        Plain(f"用户: {event.sender_name}\n"),
        Plain(f"ID: {event.user_id}")
    ])
```

---

### `make_result()`

创建空的 SDK 结果包装器。

```python
def make_result(self) -> MessageEventResult
```

---

## 序列化与反序列化

### `from_payload()`

从协议载荷创建事件实例（类方法）。

**签名**:
```python
@classmethod
def from_payload(
    cls,
    payload: dict[str, Any],
    *,
    context: Context | None = None,
    reply_handler: ReplyHandler | None = None
) -> MessageEvent
```

**参数**:
- `payload`: 协议层传递的消息数据字典
- `context`: 运行时上下文
- `reply_handler`: 自定义回复处理器

**返回**: `MessageEvent` 实例

---

### `to_payload()`

转换为协议载荷格式。

**签名**:
```python
def to_payload(self) -> dict[str, Any]
```

**返回**: 可序列化的字典

---

## 会话引用属性

### `session_ref`

获取会话引用对象。

**类型**: `SessionRef | None`

**说明**: 包含会话的完整信息，用于跨平台通信。

---

### `target`

`session_ref` 的别名。

**类型**: `SessionRef | None`

---

### `unified_msg_origin`

统一消息来源标识符。

**类型**: `str`

**说明**: 等同于 `session_id`。

---

## LLM 相关方法

### `request_llm()`

请求触发默认 LLM 链处理当前消息。

**签名**:
```python
async def request_llm(self) -> bool
```

**返回**: `bool` - 是否应该调用 LLM

**示例**:

```python
@on_command("ask")
async def ask(self, event: MessageEvent):
    should_call = await event.request_llm()
    if should_call:
        await event.reply("已触发 LLM 处理")
```

---

### `should_call_llm()`

读取当前默认 LLM 决策状态。

**签名**:
```python
async def should_call_llm(self) -> bool
```

**返回**: `bool` - 是否应该调用 LLM

**示例**:

```python
@on_message()
async def handle(self, event: MessageEvent):
    if await event.should_call_llm():
        response = await ctx.llm.chat(event.text)
        await event.reply(response)
```

---

## 结果管理方法

### `set_result()`

存储请求范围的 SDK 结果到主机桥。

**签名**:
```python
async def set_result(self, result: MessageEventResult) -> MessageEventResult
```

**参数**:
- `result`: 消息事件结果对象

**返回**: 传入的 `result` 对象

**示例**:

```python
result = event.chain_result([Plain("处理结果")])
await event.set_result(result)
```

---

### `get_result()`

从主机桥读取当前请求范围的 SDK 结果。

**签名**:
```python
async def get_result(self) -> MessageEventResult | None
```

**返回**: `MessageEventResult | None` - 结果对象，不存在则返回 None

---

### `clear_result()`

清除当前请求范围的 SDK 结果。

**签名**:
```python
async def clear_result(self) -> None
```

---

## 其他方法

### `get_message_outline()`

获取规范化的消息摘要。

**签名**:
```python
def get_message_outline(self) -> str
```

**返回**: 消息摘要文本

---

### `bind_reply_handler()`

绑定自定义回复处理器。

**签名**:
```python
def bind_reply_handler(self, reply_handler: ReplyHandler) -> None
```

**参数**:
- `reply_handler`: 回复处理函数，接收文本参数

**示例**:

```python
def custom_reply(text: str):
    print(f"回复: {text}")

event.bind_reply_handler(custom_reply)
await event.reply("测试")  # 会调用 custom_reply
```

---

## 完整使用示例

### 示例 1: 基础消息处理

```python
from astrbot_sdk.decorators import on_command, on_message

@on_command("hello")
async def hello(self, event: MessageEvent, ctx: Context):
    await event.reply(f"你好，{event.sender_name}!")

@on_message(keywords=["帮助"])
async def help(self, event: MessageEvent, ctx: Context):
    await event.reply("可用命令: /hello")
```

---

### 示例 2: 处理图片消息

```python
@on_message(regex="^保存图片$")
async def save_image(self, event: MessageEvent):
    images = event.get_images()
    if not images:
        await event.reply("消息中没有图片")
        return

    for img in images:
        try:
            local_path = await img.convert_to_file_path()
            # 保存图片...
            await event.reply(f"已保存: {local_path}")
        except Exception as e:
            await event.reply(f"保存失败: {e}")
```

---

### 示例 3: 检测@和群聊/私聊

```python
@on_command("check")
async def check(self, event: MessageEvent):
    # 检查是否群聊
    if event.is_group_chat():
        await event.reply("这是群聊消息")
    elif event.is_private_chat():
        await event.reply("这是私聊消息")

    # 检查@的用户
    at_users = event.get_at_users()
    if at_users:
        await event.reply(f"你@了: {', '.join(at_users)}")

    # 检查是否包含图片
    if event.has_component(Image):
        await event.reply("消息包含图片")
```

---

### 示例 4: 返回富文本结果

```python
@on_command("info")
async def info(self, event: MessageEvent):
    return event.chain_result([
        Plain(f"用户: {event.sender_name}\n"),
        Plain(f"ID: {event.user_id}\n"),
        Plain(f"平台: {event.platform}"),
    ])
```

---

### 示例 5: 事件控制

```python
@on_command("admin")
@require_admin
async def admin(self, event: MessageEvent):
    await event.reply("管理员操作已执行")
    event.stop_event()  # 阻止后续处理器

@on_command("public")
async def public(self, event: MessageEvent):
    # 如果事件被停止，不会执行
    await event.reply("这是公共命令")
```

---

## 注意事项

1. **必须绑定上下文**: 某些方法（如 `reply_image`, `reply_chain`, `get_group`）需要运行时上下文，未绑定时会抛出 `RuntimeError`

2. **私有/群聊判断**:
   - `is_private_chat()` 和 `is_group_chat()` 优先使用 `message_type` 字段
   - 其次通过 `group_id` 是否为 None 判断

3. **Extra 数据**: `_extras` 是 SDK 本地的，不会传递到核心，适合存储插件级别的临时状态

4. **事件停止**: `stop_event()` 只在 SDK 层面标记，不同处理器可能有不同的行为

5. **消息组件解析**: `get_messages()` 返回 SDK 组件列表，`extract_plain_text()` 只提取 Plain 组件

---

## 相关模块

- **消息组件**: `astrbot_sdk.message_components` - 所有消息组件类
- **消息链**: `astrbot_sdk.message_result.MessageChain` - 消息链类
- **消息构建器**: `astrbot_sdk.message_result.MessageBuilder` - 流式消息构建器
- **会话引用**: `astrbot_sdk.protocol.descriptors.SessionRef` - 会话引用对象

---

**版本**: v4.0
**模块**: `astrbot_sdk.events.MessageEvent`
**最后更新**: 2026-03-17
