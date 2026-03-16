# AstrBot SDK 消息事件与组件 API 参考文档

## 概述

本文档详细介绍 `astrbot_sdk` 中消息事件和消息组件的使用方法，包括 `MessageEvent` 类和所有消息组件类。

## 目录

- [MessageEvent - 消息事件对象](#messageevent---消息事件对象)
- [消息组件类](#消息组件类)
- [MessageChain - 消息链](#messagechain---消息链)
- [MessageBuilder - 消息构建器](#messagebuilder---消息构建器)

---

## MessageEvent - 消息事件对象

**模块路径**: `astrbot_sdk.events.MessageEvent`

### 核心属性

| 属性名 | 类型 | 说明 |
|--------|------|------|
| `text` | `str` | 消息文本内容 |
| `user_id` | `str \| None` | 发送者用户 ID |
| `group_id` | `str \| None` | 群组 ID（私聊时为 None） |
| `platform` | `str \| None` | 平台标识（如 "qq", "wechat"） |
| `session_id` | `str` | 会话 ID |
| `self_id` | `str` | 机器人账号 ID |
| `platform_id` | `str` | 平台实例标识 |
| `message_type` | `str` | 消息类型（"private" 或 "group"） |
| `sender_name` | `str` | 发送者昵称 |

### 消息组件访问方法

#### `get_messages()`

获取当前事件的所有 SDK 消息组件。

```python
components = event.get_messages()
for comp in components:
    print(f"组件类型: {comp.type}")
```

#### `has_component(type_)`

检查是否包含特定类型的组件。

```python
if event.has_component(Image):
    print("消息包含图片")
```

#### `get_components(type_)`

获取特定类型的所有组件。

```python
at_comps = event.get_components(At)
for at in at_comps:
    print(f"@了用户: {at.qq}")
```

#### `get_images()`

获取所有图片组件。

```python
images = event.get_images()
for img in images:
    path = await img.convert_to_file_path()
    print(f"图片路径: {path}")
```

#### `get_files()`

获取所有文件组件。

```python
files = event.get_files()
```

#### `extract_plain_text()`

提取所有纯文本内容。

```python
text = event.extract_plain_text()
```

#### `get_at_users()`

获取消息中所有被@的用户ID列表。

```python
at_users = event.get_at_users()
```

### 会话与平台信息方法

#### `is_private_chat()` / `is_group_chat()`

判断消息类型。

```python
if event.is_private_chat():
    await event.reply("这是私聊")
elif event.is_group_chat():
    await event.reply("这是群聊")
```

#### `is_admin()`

判断发送者是否有管理员权限。

```python
if event.is_admin():
    await event.reply("你是管理员")
```

### 回复与发送方法

#### `reply(text)`

回复纯文本消息。

```python
await event.reply("Hello World!")
```

#### `reply_image(image_url)`

回复图片消息。

```python
await event.reply_image("https://example.com/image.jpg")
```

#### `reply_chain(chain)`

回复消息链。

```python
from astrbot_sdk.message_components import Plain, At

await event.reply_chain([
    Plain("Hello "),
    At("123456"),
    Plain("!")
])
```

### 事件控制方法

#### `stop_event()`

标记事件为已停止，阻止后续处理器执行。

```python
event.stop_event()
```

### 结果构建方法

#### `plain_result(text)`

创建纯文本结果。

```python
return event.plain_result("回复内容")
```

#### `image_result(url_or_path)`

创建图片结果。

```python
return event.image_result("https://example.com/image.jpg")
```

#### `chain_result(chain)`

创建链结果。

```python
return event.chain_result([
    Plain("Hello"),
    At("123456")
])
```

---

## 消息组件类

### Plain - 纯文本组件

```python
from astrbot_sdk.message_components import Plain

text = Plain("Hello World")
```

### At - @某人组件

```python
from astrbot_sdk.message_components import At

at = At("123456", name="张三")
```

### AtAll - @全体成员组件

```python
from astrbot_sdk.message_components import AtAll

at_all = AtAll()
```

### Image - 图片组件

```python
from astrbot_sdk.message_components import Image

# URL 图片
img1 = Image.fromURL("https://example.com/image.jpg")

# 本地文件
img2 = Image.fromFileSystem("/path/to/image.jpg")

# Base64
img3 = Image.fromBase64("iVBORw0KGgo...")
```

### Record - 语音组件

```python
from astrbot_sdk.message_components import Record

# URL 音频
audio = Record.fromURL("https://example.com/audio.mp3")

# 本地文件
audio = Record.fromFileSystem("/path/to/audio.mp3")
```

### Video - 视频组件

```python
from astrbot_sdk.message_components import Video

video = Video.fromURL("https://example.com/video.mp4")
```

### File - 文件组件

```python
from astrbot_sdk.message_components import File

# URL 文件
file1 = File(name="document.pdf", url="https://example.com/doc.pdf")

# 本地文件
file2 = File(name="image.jpg", file="/path/to/image.jpg")
```

### Reply - 回复组件

```python
from astrbot_sdk.message_components import Reply, Plain

reply = Reply(
    id="msg_123",
    sender_id="789",
    chain=[Plain("被回复的消息")]
)
```

---

## MessageChain - 消息链

### 构造方法

```python
from astrbot_sdk.message_result import MessageChain
from astrbot_sdk.message_components import Plain, At

# 空消息链
chain = MessageChain()

# 带初始组件
chain = MessageChain([Plain("Hello"), At("123456")])
```

### 实例方法

#### `append(component)`

追加单个组件。

```python
chain.append(Plain("More text"))
```

#### `extend(components)`

追加多个组件。

```python
chain.extend([Plain("A"), Plain("B")])
```

#### `to_payload()`

转换为协议 payload。

```python
payload = chain.to_payload()
```

#### `get_plain_text()`

提取纯文本内容。

```python
text = chain.get_plain_text()
```

---

## MessageBuilder - 消息构建器

### 使用示例

```python
from astrbot_sdk.message_result import MessageBuilder

chain = (MessageBuilder()
    .text("Hello ")
    .at("123456")
    .text("!\n")
    .image("https://example.com/img.jpg")
    .build())

await event.reply_chain(chain)
```

### 可用方法

- `.text(content)` - 添加文本
- `.at(user_id)` - 添加@用户
- `.at_all()` - 添加@全体成员
- `.image(url)` - 添加图片
- `.record(url)` - 添加语音
- `.video(url)` - 添加视频
- `.file(name, url=...)` - 添加文件
- `.build()` - 构建消息链

---

## 使用示例

### 处理图片消息

```python
@on_message()
async def handle_image(event: MessageEvent):
    images = event.get_images()
    if not images:
        await event.reply("消息中没有图片")
        return

    for img in images:
        path = await img.convert_to_file_path()
        await event.reply(f"收到图片: {path}")
```

### 检测@和群聊/私聊

```python
@on_command("check")
async def check_handler(event: MessageEvent):
    if event.is_group_chat():
        await event.reply("这是群聊消息")
    elif event.is_private_chat():
        await event.reply("这是私聊消息")

    at_users = event.get_at_users()
    if at_users:
        await event.reply(f"你@了: {', '.join(at_users)}")
```

### 返回富文本结果

```python
@on_command("info")
async def info_handler(event: MessageEvent):
    return event.chain_result([
        Plain(f"用户: {event.sender_name}\n"),
        Plain(f"ID: {event.user_id}\n"),
        Plain(f"平台: {event.platform}"),
    ])
```
