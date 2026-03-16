# 消息组件 API 完整参考

## 概述

消息组件是用于构建聊天消息的各种元素。每个组件代表消息中的一种特定内容类型，可以单独使用或组合成消息链。

**模块路径**: `astrbot_sdk.message_components`

---

## 目录

- [BaseMessageComponent - 基类](#basemessagecomponent---基类)
- [Plain - 纯文本组件](#plain---纯文本组件)
- [At / AtAll - @组件](#at--atall---组件)
- [Image - 图片组件](#image---图片组件)
- [Record - 语音组件](#record---语音组件)
- [Video - 视频组件](#video---视频组件)
- [File - 文件组件](#file---文件组件)
- [Reply - 回复组件](#reply---回复组件)
- [Poke - 戳一戳组件](#poke---戳一戳组件)
- [Forward - 转发组件](#forward---转发组件)
- [MessageChain - 消息链](#messagechain---消息链)
- [辅助函数](#辅助函数)

---

## 导入方式

```python
# 从主模块导入（推荐）
from astrbot_sdk import (
    Plain, At, AtAll, Image, Record, Video, File, Reply, Poke, Forward,
    MessageChain, MessageBuilder
)

# 从子模块导入
from astrbot_sdk.message_components import (
    Plain, At, AtAll, Image, Record, Video, File, Reply, Poke, Forward
)
from astrbot_sdk.message_result import MessageChain, MessageBuilder

# 辅助函数
from astrbot_sdk.message_components import (
    payload_to_component,
    component_to_payload_sync,
    component_to_payload,
)
```

---

## BaseMessageComponent - 基类

所有消息组件的基类。

### 类定义

```python
class BaseMessageComponent:
    type: str = "unknown"

    def toDict(self) -> dict[str, Any]:
        """同步转换为字典 payload"""

    async def to_dict(self) -> dict[str, Any]:
        """异步转换为字典 payload"""
```

---

## Plain - 纯文本组件

最简单的消息组件，只包含文本内容。

### 类定义

```python
class Plain(BaseMessageComponent):
    type = "plain"  # 序列化时为 "text"

    def __init__(self, text: str, convert: bool = True, **_: Any) -> None:
        self.text = text
        self.convert = convert
```

### 构造方法

```python
from astrbot_sdk import Plain

# 基本用法
text = Plain("Hello World")

# 不自动 strip（保留首尾空格）
text = Plain("  Hello  ", convert=False)
```

### 序列化格式

```python
# toDict() 会自动 strip 文本
{
    "type": "text",
    "data": {"text": "Hello World"}
}

# to_dict() 保留原始文本
{
    "type": "text",
    "data": {"text": "  Hello  "}
}
```

### 使用示例

```python
@on_command("echo")
async def echo(self, event: MessageEvent, text: str):
    await event.reply_chain([Plain(f"你说: {text}")])
```

---

## At / AtAll - @组件

用于在消息中提及用户。

### At - @某人

#### 类定义

```python
class At(BaseMessageComponent):
    type = "at"

    def __init__(self, qq: int | str, name: str | None = "", **_: Any) -> None:
        self.qq = qq
        self.name = name or ""
```

#### 构造方法

```python
from astrbot_sdk import At

# @ 单个用户
at = At(123456)
at = At("123456", name="张三")
```

#### 序列化格式

```python
{
    "type": "at",
    "data": {"qq": "123456"}
}
```

---

### AtAll - @全体成员

#### 类定义

```python
class AtAll(At):
    def __init__(self, **_: Any) -> None:
        super().__init__(qq="all")
```

#### 构造方法

```python
from astrbot_sdk import AtAll

at_all = AtAll()
```

#### 序列化格式

```python
{
    "type": "at",
    "data": {"qq": "all"}
}
```

---

### 使用示例

```python
from astrbot_sdk import At, AtAll, Plain

@on_command("at_test")
async def at_test(self, event: MessageEvent):
    await event.reply_chain([
        Plain("你好 "),
        At(event.user_id or "123456"),
        Plain("！"),
        AtAll(),
        Plain("所有人请注意！")
    ])
```

---

## Image - 图片组件

用于在消息中发送图片。

### 类定义

```python
class Image(BaseMessageComponent):
    type = "image"

    def __init__(self, file: str | None, **kwargs: Any) -> None:
        self.file = file or ""
        self._type = kwargs.get("_type", "")
        self.subType = kwargs.get("subType", 0)
        self.url = kwargs.get("url", "")
        self.cache = kwargs.get("cache", True)
        self.id = kwargs.get("id", 40000)
        self.c = kwargs.get("c", 2)
        self.path = kwargs.get("path", "")
        self.file_unique = kwargs.get("file_unique", "")
```

### 静态构造方法

#### `fromURL(url, **kwargs)`

从 URL 创建图片。

```python
from astrbot_sdk import Image

img = Image.fromURL("https://example.com/image.jpg")
```

#### `fromFileSystem(path, **kwargs)`

从本地文件系统创建图片。

```python
img = Image.fromFileSystem("/path/to/image.jpg")
```

#### `fromBase64(base64_data, **kwargs)`

从 Base64 数据创建图片。

```python
img = Image.fromBase64("iVBORw0KGgo...")
```

#### `fromBytes(data, **kwargs)`

从字节数据创建图片。

```python
img = Image.fromBytes(b"...")
```

### 实例方法

#### `convert_to_file_path()`

将图片转换为本地文件路径（下载或解码）。

```python
path = await img.convert_to_file_path()
```

#### `register_to_file_service()`

将图片注册到文件服务，返回可访问 URL。

```python
public_url = await img.register_to_file_service()
```

### 支持的格式

```python
# URL: "https://example.com/image.jpg"
# 本地文件: "file:///absolute/path/to/image.jpg"
# Base64: "base64://iVBORw0KGgo..."
```

### 使用示例

```python
from astrbot_sdk import Image

@on_command("cat")
async def cat(self, event: MessageEvent):
    await event.reply_image("https://example.com/cat.jpg")

@on_command("local_img")
async def local_img(self, event: MessageEvent):
    await event.reply_image("file:///path/to/image.jpg")
```

---

## Record - 语音组件

用于在消息中发送语音/音频。

### 类定义

```python
class Record(BaseMessageComponent):
    type = "record"

    def __init__(self, file: str | None, **kwargs: Any) -> None:
        self.file = file or ""
        self.magic = kwargs.get("magic", False)
        self.url = kwargs.get("url", "")
        self.cache = kwargs.get("cache", True)
        self.proxy = kwargs.get("proxy", True)
        self.timeout = kwargs.get("timeout", 0)
        self.text = kwargs.get("text")
        self.path = kwargs.get("path")
```

### 静态构造方法

#### `fromFileSystem(path, **kwargs)`

```python
from astrbot_sdk import Record

audio = Record.fromFileSystem("/path/to/audio.mp3")
```

#### `fromURL(url, **kwargs)`

```python
audio = Record.fromURL("https://example.com/audio.mp3")
```

### 实例方法

#### `convert_to_file_path()`

```python
path = await audio.convert_to_file_path()
```

#### `register_to_file_service()`

```python
public_url = await audio.register_to_file_service()
```

---

## Video - 视频组件

用于在消息中发送视频。

### 类定义

```python
class Video(BaseMessageComponent):
    type = "video"

    def __init__(self, file: str, **kwargs: Any) -> None:
        self.file = file
        self.cover = kwargs.get("cover", "")
        self.c = kwargs.get("c", 2)
        self.path = kwargs.get("path", "")
```

### 静态构造方法

#### `fromFileSystem(path, **kwargs)`

```python
from astrbot_sdk import Video

video = Video.fromFileSystem("/path/to/video.mp4")
```

#### `fromURL(url, **kwargs)`

```python
video = Video.fromURL("https://example.com/video.mp4")
```

---

## File - 文件组件

用于在消息中发送文件附件。

### 类定义

```python
class File(BaseMessageComponent):
    type = "file"

    def __init__(self, name: str, file: str = "", url: str = "") -> None:
        self.name = name
        self.file_ = file
        self.url = url
```

### 属性

- `name` (`str`): 文件名
- `file_` (`str`): 本地文件路径（内部使用）
- `url` (`str`): 文件 URL

### file 属性 (getter/setter)

```python
@property
def file(self) -> str:
    return self.file_

@file.setter
def file(self, value: str) -> None:
    if value.startswith(("http://", "https://")):
        self.url = value
    else:
        self.file_ = value
```

### 构造方法

```python
from astrbot_sdk import File

# URL 文件
file1 = File(name="document.pdf", url="https://example.com/doc.pdf")

# 本地文件
file2 = File(name="image.jpg", file="/path/to/image.jpg")
```

### 实例方法

#### `get_file(allow_return_url=False)`

获取文件路径或 URL。

```python
path = await file.get_file()

# 优先返回 URL
path = await file.get_file(allow_return_url=True)
```

#### `register_to_file_service()`

```python
public_url = await file.register_to_file_service()
```

### 序列化格式

```python
# toDict()
{
    "type": "file",
    "data": {
        "name": "文件名.pdf",
        "file": "本地路径或URL"
    }
}

# to_dict()
{
    "type": "file",
    "data": {
        "name": "文件名.pdf",
        "file": "优先返回URL，否则本地路径"
    }
}
```

---

## Reply - 回复组件

用于回复某条消息。

### 类定义

```python
class Reply(BaseMessageComponent):
    type = "reply"

    def __init__(self, **kwargs: Any) -> None:
        self.id = kwargs.get("id", "")
        self.chain = _coerce_reply_chain(kwargs.get("chain", []))
        self.sender_id = kwargs.get("sender_id", 0)
        self.sender_nickname = kwargs.get("sender_nickname", "")
        self.time = kwargs.get("time", 0)
        self.message_str = kwargs.get("message_str", "")
        self.text = kwargs.get("text", "")
        self.qq = kwargs.get("qq", 0)
        self.seq = kwargs.get("seq", 0)
```

### 构造方法

```python
from astrbot_sdk import Reply, Plain

reply = Reply(
    id="msg_123",
    sender_id="789",
    sender_nickname="张三",
    chain=[Plain("被回复的消息")]
)
```

### 实例方法

#### `toDict()` / `to_dict()`

序列化为字典。

---

## Poke - 戳一戳组件

用于发送戳一戳操作。

### 类定义

```python
class Poke(BaseMessageComponent):
    type = "poke"

    def __init__(self, poke_type: str | int | None = None, **kwargs: Any) -> None:
        self._type = str(poke_type)
        self.id = kwargs.get("id")
        self.qq = kwargs.get("qq", 0)
```

### 构造方法

```python
from astrbot_sdk import Poke

poke = Poke(poke_type="126", qq="123456")
```

---

## Forward - 转发组件

用于转发消息。

### 类定义

```python
class Forward(BaseMessageComponent):
    type = "forward"

    def __init__(self, id: str, **_: Any) -> None:
        self.id = id
```

### 构造方法

```python
from astrbot_sdk import Forward

forward = Forward(id="forward_msg_123")
```

---

## MessageChain - 消息链

用于组合多个消息组件。

### 类定义

```python
@dataclass(slots=True)
class MessageChain:
    components: list[BaseMessageComponent] = field(default_factory=list)
```

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

追加单个组件，返回 self 支持链式调用。

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

#### `get_plain_text(with_other_comps_mark=False)`

提取纯文本内容。

```python
text = chain.get_plain_text()
```

---

## MessageBuilder - 消息构建器

流式构建消息链的工具类。

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

## 辅助函数

### `payload_to_component(payload)`

将协议 payload 转换为消息组件。

```python
from astrbot_sdk.message_components import payload_to_component

component = payload_to_component(payload)
```

### `component_to_payload_sync(component)`

将组件同步转换为 payload。

```python
from astrbot_sdk.message_components import component_to_payload_sync

payload = component_to_payload_sync(component)
```

### `component_to_payload(component)`

将组件异步转换为 payload。

```python
from astrbot_sdk.message_components import component_to_payload

payload = await component_to_payload(component)
```

---

## 使用示例

### 处理图片消息

```python
@on_message()
async def save_image(self, event: MessageEvent):
    images = event.get_images()
    if not images:
        await event.reply("消息中没有图片")
        return

    for img in images:
        try:
            path = await img.convert_to_file_path()
            # 保存图片...
            await event.reply(f"已保存: {path}")
        except Exception as e:
            await event.reply(f"保存失败: {e}")
```

### 检测@和群聊/私聊

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
```

### 返回富文本结果

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

## 注意事项

1. **序列化差异**:
   - `Plain.toDict()` 会 strip 文本
   - `Plain.to_dict()` 保留原始文本
   - `File.toDict()` 和 `to_dict()` 对 file 字段处理不同

2. **路径格式**:
   - 本地文件: `file:///absolute/path` (Windows 下特殊处理)
   - URL: `http://` 或 `https://`
   - Base64: `base64://<data>`

3. **文件下载**:
   - `convert_to_file_path()` 会下载网络文件到临时目录
   - `register_to_file_service()` 需要运行时上下文

4. **兼容性**:
   - `At` 和 `AtAll` 序列化后的 type 都是 "at"
   - `Reply` 的 chain 字段在序列化时递归处理

---

## 相关模块

- **消息组件**: `astrbot_sdk.message_components`
- **消息链**: `astrbot_sdk.message_result.MessageChain`
- **消息构建器**: `astrbot_sdk.message_result.MessageBuilder`
- **协议描述符**: `astrbot_sdk.protocol.descriptors`

---

**版本**: v4.0
**模块**: `astrbot_sdk.message_components`
**最后更新**: 2026-03-17
