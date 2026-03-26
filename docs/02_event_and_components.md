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

**模块路径**: `astrbot_sdk.MessageEvent`

每个 handler 调用都会创建新的 `MessageEvent` 实例，封装收到的消息并提供便捷的回复方法。

### 核心属性

| 属性名 | 类型 | 说明 |
|--------|------|------|
| `text` | `str` | 消息文本内容 |
| `user_id` | `str` | 发送者用户 ID |
| `group_id` | `str \| None` | 群组 ID（私聊时为 None） |
| `platform` | `str` | 平台标识（如 "qq", "wechat"） |
| `session_id` | `str` | 会话 ID（通常是 group_id 或 user_id） |
| `self_id` | `str` | 机器人账号 ID |
| `platform_id` | `str` | 平台实例标识 |
| `message_type` | `str` | 消息类型（"private" 或 "group"） |
| `sender_name` | `str` | 发送者昵称 |
| `raw` | `dict` | 原始消息数据 |

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
from astrbot_sdk import Image

if event.has_component(Image):
    print("消息包含图片")
```

#### `get_components(type_)`

获取特定类型的所有组件。

```python
from astrbot_sdk import At

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
from astrbot_sdk import Plain, At

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

#### `continue_event()`

清除停止标记，允许后续处理器继续执行。

```python
event.continue_event()
```

#### `is_stopped()`

检查事件是否已停止。

```python
if event.is_stopped():
    print("事件已被停止")
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
from astrbot_sdk import Plain, At

return event.chain_result([
    Plain("Hello"),
    At("123456")
])
```

### 临时数据存储

#### `set_extra(key, value)` / `get_extra(key)` / `clear_extra()`

存储和读取 SDK 本地临时事件数据。

```python
# 存储数据
event.set_extra("custom_key", {"foo": "bar"})

# 读取数据
data = event.get_extra("custom_key", default={})

# 读取所有 extra
all_extras = event.get_extra()

# 清除数据
event.clear_extra()
```

---

## 消息组件类

所有消息组件都继承自 `BaseMessageComponent`，可通过以下方式导入：

```python
from astrbot_sdk import Plain, At, AtAll, Image, Record, Video, File, Reply, Forward, Poke, UnknownComponent
```

### Plain - 纯文本组件

```python
from astrbot_sdk import Plain

text = Plain("Hello World")
```

**属性**：
- `text`: 文本内容
- `convert`: 是否转换特殊字符（默认 True）

### At - @某人组件

```python
from astrbot_sdk import At

at = At("123456", name="张三")
```

**属性**：
- `qq`: 用户 ID（支持 `int` 或 `str`）
- `name`: 用户昵称（可选）

### AtAll - @全体成员组件

```python
from astrbot_sdk import AtAll

at_all = AtAll()
```

### Image - 图片组件

```python
from astrbot_sdk import Image

# URL 图片
img1 = Image.fromURL("https://example.com/image.jpg")

# 本地文件
img2 = Image.fromFileSystem("/path/to/image.jpg")

# Base64
img3 = Image.fromBase64("iVBORw0KGgo...")
```

**属性**：
- `file`: 图片文件路径或 URL
- `url`: 图片 URL
- `path`: 本地路径

**方法**：
- `convert_to_file_path()`: 异步方法，将图片转换为本地文件路径
- `register_to_file_service()`: 异步方法，注册到文件服务

### Record - 语音组件

```python
from astrbot_sdk import Record

# URL 音频
audio = Record.fromURL("https://example.com/audio.mp3")

# 本地文件
audio = Record.fromFileSystem("/path/to/audio.mp3")
```

**方法**：
- `convert_to_file_path()`: 异步方法，将音频转换为本地文件路径
- `register_to_file_service()`: 异步方法，注册到文件服务

### Video - 视频组件

```python
from astrbot_sdk import Video

# URL 视频
video = Video.fromURL("https://example.com/video.mp4")

# 本地文件
video = Video.fromFileSystem("/path/to/video.mp4")
```

**方法**：
- `convert_to_file_path()`: 异步方法，将视频转换为本地文件路径
- `register_to_file_service()`: 异步方法，注册到文件服务

### File - 文件组件

```python
from astrbot_sdk import File

# URL 文件
file1 = File(name="document.pdf", url="https://example.com/doc.pdf")

# 本地文件
file2 = File(name="image.jpg", file="/path/to/image.jpg")
```

**属性**：
- `name`: 文件名
- `file`: 本地文件路径
- `url`: 文件 URL

**方法**：
- `get_file(allow_return_url=False)`: 异步方法，获取文件路径
- `register_to_file_service()`: 异步方法，注册到文件服务

### Reply - 回复组件

```python
from astrbot_sdk import Reply, Plain

reply = Reply(
    id="msg_123",
    sender_id="789",
    sender_nickname="张三",
    chain=[Plain("被回复的消息")]
)
```

**属性**：
- `id`: 消息 ID
- `sender_id`: 发送者 ID
- `sender_nickname`: 发送者昵称
- `chain`: 被回复的消息链
- `time`: 消息时间
- `message_str`: 消息字符串
- `text`: 消息文本
- `qq`: QQ 号
- `seq`: 序列号

---

## MessageChain - 消息链

消息链用于组合多个消息组件。

### 导入

```python
from astrbot_sdk import MessageChain, Plain, At
```

### 构造方法

```python
# 空消息链
chain = MessageChain()

# 带初始组件
chain = MessageChain([Plain("Hello"), At("123456")])
```

### 实例方法

#### `append(component)`

追加单个组件，返回自身支持链式调用。

```python
chain.append(Plain("More text"))
```

#### `extend(components)`

追加多个组件，返回自身支持链式调用。

```python
chain.extend([Plain("A"), Plain("B")])
```

#### `to_payload()`

同步转换为协议 payload。

```python
payload = chain.to_payload()
```

#### `to_payload_async()`

异步转换为协议 payload。

```python
payload = await chain.to_payload_async()
```

#### `get_plain_text(with_other_comps_mark=False)`

提取纯文本内容。

```python
text = chain.get_plain_text()

# 包含其他组件标记
text = chain.get_plain_text(with_other_comps_mark=True)
# 输出: "Hello [At] World"
```

#### `plain_text(with_other_comps_mark=False)`

`get_plain_text` 的别名。

```python
text = chain.plain_text()
```

---

## MessageBuilder - 消息构建器

提供流畅的 API 来构建消息链。

### 导入

```python
from astrbot_sdk import MessageBuilder
```

### 使用示例

```python
from astrbot_sdk import MessageBuilder

chain = (MessageBuilder()
    .text("Hello ")
    .at("123456")
    .text("!\n")
    .image("https://example.com/img.jpg")
    .build())

await event.reply_chain(chain)
```

### 可用方法

| 方法 | 说明 |
|------|------|
| `.text(content)` | 添加文本 |
| `.at(user_id)` | 添加@用户 |
| `.at_all()` | 添加@全体成员 |
| `.image(url)` | 添加图片 |
| `.record(url)` | 添加语音 |
| `.video(url)` | 添加视频 |
| `.file(name, file="", url="")` | 添加文件 |
| `.reply(**kwargs)` | 添加回复组件 |
| `.append(component)` | 追加任意组件 |
| `.extend(components)` | 追加多个组件 |
| `.build()` | 构建消息链 |

---

## 使用示例

### 处理图片消息

```python
from astrbot_sdk import Star, MessageEvent, Image
from astrbot_sdk.decorators import on_message

class MyPlugin(Star):
    @on_message()
    async def handle_image(self, event: MessageEvent):
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
from astrbot_sdk import Star, MessageEvent
from astrbot_sdk.decorators import on_command

class MyPlugin(Star):
    @on_command("check")
    async def check_handler(self, event: MessageEvent):
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
from astrbot_sdk import Star, MessageEvent, Plain, At
from astrbot_sdk.decorators import on_command

class MyPlugin(Star):
    @on_command("info")
    async def info_handler(self, event: MessageEvent):
        return event.chain_result([
            Plain(f"用户: {event.sender_name}\n"),
            Plain(f"ID: {event.user_id}\n"),
            Plain(f"平台: {event.platform}"),
        ])
```

---

## 媒体辅助类

### MediaHelper

媒体辅助类，提供从 URL 检测媒体类型和下载功能。

```python
from astrbot_sdk import MediaHelper
```

#### from_url - 从 URL 创建组件

自动检测 URL 的媒体类型并创建对应的消息组件。

```python
from astrbot_sdk import MediaHelper

# 自动检测媒体类型
component = await MediaHelper.from_url("https://example.com/video.mp4")
# 返回 Video 组件

component = await MediaHelper.from_url("https://example.com/image.jpg")
# 返回 Image 组件

component = await MediaHelper.from_url("https://example.com/audio.mp3")
# 返回 Record 组件

# 强制指定类型
component = await MediaHelper.from_url("https://example.com/data", kind="image")
```

**参数**：
- `url`: 媒体文件 URL（必需）
- `kind`: 媒体类型（可选，默认 "auto" 自动检测）
  - `"auto"`: 自动检测
  - `"image"`: 图片
  - `"record"` / `"audio"`: 音频
  - `"video"`: 视频
  - `"file"`: 文件

**返回值**：
- `Image` / `Video` / `Record` / `File` 组件实例

#### download - 下载媒体文件

下载媒体文件到本地目录。

```python
from astrbot_sdk import MediaHelper
from pathlib import Path

# 下载到指定目录
path = await MediaHelper.download(
    url="https://example.com/video.mp4",
    save_dir=Path("/tmp/downloads")
)
print(f"下载到: {path}")  # /tmp/downloads/video.mp4
```

**参数**：
- `url`: 文件 URL（必需，仅支持 http/https）
- `save_dir`: 保存目录（必需，Path 对象）

**返回值**：
- `Path`: 下载文件的本地路径

**示例：完整媒体处理流程**

```python
from astrbot_sdk import Star, Context, MessageEvent, MediaHelper, Plain
from astrbot_sdk.decorators import on_command
from pathlib import Path

class MediaPlugin(Star):
    @on_command("download")
    async def download_media(self, event: MessageEvent, ctx: Context, url: str):
        """下载媒体文件"""
        try:
            # 发送下载中提示
            await event.reply(f"正在下载: {url}")

            # 下载文件到临时目录
            path = await MediaHelper.download(url, Path("/tmp/downloads"))

            # 创建对应组件并发送
            component = await MediaHelper.from_url(url)
            component.file = str(path)  # 使用本地文件

            await event.reply_chain([Plain("下载完成！"), component])
        except Exception as e:
            await event.reply(f"下载失败: {e}")

    @on_command("mirror")
    async def mirror_media(self, event: MessageEvent, ctx: Context):
        """转发收到的媒体"""
        images = event.get_images()
        if images:
            for img in images:
                # 下载并重新发送
                if img.url:
                    local_path = await MediaHelper.download(img.url, Path("/tmp/downloads"))
                    await event.reply(f"已镜像保存: {local_path}")
```

---

## 未知组件

### UnknownComponent

未知消息组件，用于表示 SDK 无法识别的平台特定组件。

```python
from astrbot_sdk import UnknownComponent
```

**说明**：
- 当收到 SDK 不支持的消息类型时，会返回此组件
- 保留原始数据供插件自行处理
- 通常出现在新平台或平台新功能中

**属性**：
- `raw_type`: 原始组件类型字符串
- `raw_data`: 原始组件数据（dict）

```python
from astrbot_sdk import UnknownComponent
from astrbot_sdk.decorators import on_message

@on_message()
async def handle_unknown(self, event: MessageEvent, ctx: Context):
    components = event.get_messages()
    for comp in components:
        if isinstance(comp, UnknownComponent):
            ctx.logger.warning(f"未知组件类型: {comp.raw_type}")
            ctx.logger.debug(f"原始数据: {comp.raw_data}")
            # 插件可以尝试自行处理 raw_data
```

---

## 特殊消息组件

### Forward - 合并转发消息

合并转发消息组件（仅部分平台支持，如 QQ）。

```python
from astrbot_sdk import Forward

# 通过消息 ID 引用转发消息
forward = Forward(id="msg_forward_123")
```

**属性**：
- `id`: 转发消息 ID

**注意**：
- Forward 组件的支持程度取决于具体平台适配器
- 发送转发消息需要平台支持，具体用法请参考平台文档

### Poke - 戳一戳/拍一拍

戳一戳消息组件（QQ 等平台支持）。

```python
from astrbot_sdk import Poke

# 发送戳一戳（通过 id 或 qq 指定目标用户）
poke = Poke(id="123456")

# 或使用 qq 参数
poke = Poke(qq="123456")

# 指定戳一戳类型
poke = Poke(poke_type="126", id="123456")
```

**属性**：
- `_type`: 戳一戳类型（默认 "126"）
- `id`: 目标用户 ID
- `qq`: 目标用户 QQ 号

**检测戳一戳**：

```python
from astrbot_sdk import Poke
from astrbot_sdk.decorators import on_message

@on_message()
async def on_poke(self, event: MessageEvent, ctx: Context):
    for comp in event.get_messages():
        if isinstance(comp, Poke):
            target_id = comp.target_id()
            await event.reply(f"戳了一下 {target_id or '某人'}！")
```

**方法**：
- `target_id()`: 获取被戳目标用户 ID
