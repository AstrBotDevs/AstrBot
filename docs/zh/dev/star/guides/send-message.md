# 消息的发送

## 被动消息

被动消息指的是机器人被动回复消息。

```python
@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent):
    yield event.plain_result("Hello!")
    yield event.plain_result("你好！")

    yield event.image_result("path/to/image.jpg")  # 发送图片
    yield event.image_result(
        "https://example.com/image.jpg"
    )  # 发送 URL 图片，务必以 http 或 https 开头
```

## 主动消息

主动消息指的是机器人主动推送消息。某些平台可能不支持主动消息发送。

如果是一些定时任务或者不想立即发送消息，可以使用 `event.unified_msg_origin` 得到一个字符串并将其存储，然后在想发送消息的时候使用 `self.context.send_message(unified_msg_origin, chains)` 来发送消息。

```python
from astrbot.api.event import MessageChain


@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent):
    umo = event.unified_msg_origin
    message_chain = MessageChain().message("Hello!").file_image("path/to/image.jpg")
    await self.context.send_message(event.unified_msg_origin, message_chain)
```

通过这个特性，你可以将 unified_msg_origin 存储起来，然后在需要的时候发送消息。

> [!TIP]
> 关于 unified_msg_origin。
> unified_msg_origin 是一个字符串，记录了一个会话的唯一 ID，AstrBot 能够据此找到属于哪个消息平台的哪个会话。这样就能够实现在 `send_message` 的时候，发送消息到正确的会话。有关 MessageChain，请参见接下来的一节。

## 富媒体消息

AstrBot 支持发送富媒体消息，比如图片、语音、视频等。使用 `MessageChain` 来构建消息。

```python
import astrbot.api.message_components as Comp


@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent):
    chain = [
        Comp.At(qq=event.get_sender_id()),  # At 消息发送者
        Comp.Plain("来看这个图："),
        Comp.Image.fromURL("https://example.com/image.jpg"),  # 从 URL 发送图片
        Comp.Image.fromFileSystem("path/to/image.jpg"),  # 从本地文件目录发送图片
        Comp.Plain("这是一个图片。"),
    ]
    yield event.chain_result(chain)
```

上面构建了一个 `message chain`，也就是消息链，最终会发送一条包含了图片和文字的消息，并且保留顺序。

> [!TIP]
> 在 aiocqhttp 消息适配器中，对于 `plain` 类型的消息，在发送中会使用 `strip()` 方法去除空格及换行符，可以在消息前后添加零宽空格 `\u200b` 以解决这个问题。

类似地，

**文件 File**

```py
Comp.File(file="path/to/file.txt", name="file.txt")  # 部分平台不支持
```

**语音 Record**

```py
path = "path/to/record.wav"  # 暂时只接受 wav 格式，其他格式请自行转换
Comp.Record(file=path, url=path)
```

**视频 Video**

```py
path = "path/to/video.mp4"
Comp.Video.fromFileSystem(path=path)
Comp.Video.fromURL(url="https://example.com/video.mp4")
```

## 交互按钮

使用 `ActionRow` 包装 `Button`，并通过 `@filter.button_action("按钮 ID")` 接收点击。下面的方法可以添加到现有的 `Star` 插件类中。

按钮动作和样式分别通过 `Button.CallbackAction`、`Button.UrlAction` 和 `Button.Style` 创建；`ActionRow` 是独立的消息组件。

```python
from astrbot.api.event import AstrMessageEvent, filter
import astrbot.api.message_components as Comp


@filter.command("buttons")
async def buttons(self, event: AstrMessageEvent):
    yield event.chain_result([
        Comp.Plain("请选择操作："),
        Comp.ActionRow(
            buttons=[
                Comp.Button(
                    id="my_plugin:confirm",
                    label="确认",
                    action=Comp.Button.CallbackAction(data={"item_id": 42}),
                    style=Comp.Button.Style.PRIMARY,
                ),
                Comp.Button(
                    id="my_plugin:docs",
                    label="文档",
                    action=Comp.Button.UrlAction(url="https://docs.astrbot.app"),
                ),
            ],
            action_timeout=60,
            fallback_text="当前平台不支持按钮，请使用文字指令。",
        ),
    ])


@filter.button_action("my_plugin:confirm")
async def confirm(self, event: AstrMessageEvent):
    interaction = event.get_button_interaction()
    if interaction is None:
        return
    yield event.plain_result(f"已确认项目：{interaction.data['item_id']}")
```

- `action_timeout` 是这一行回调按钮的有效期，单位为秒，必须是有限正数；默认 `None`，表示不限时。从这行按钮首次渲染发送时开始计时，同一行共享截止时间。复用同一个 `ActionRow` 实例不会刷新有效期；要重新计时，请创建新的实例。
- 截止时间会随回调数据持久化，重启不会重置。到期后的点击会提示“按钮已过期，请重新发起操作。 / This button has expired. Please start again.”，不会执行插件处理器。Telegram 使用弹窗，Discord 和 Slack 使用仅点击者可见的回复，其余平台通过消息回复（企业微信 AI Bot 更新卡片）。重复点击仍会提示。已经受理的操作可以继续执行，按钮可能仍显示在原消息中。
- `Button.CallbackAction.data` 必须可以 JSON 序列化，点击后通过 `interaction.data` 读取；按钮 ID 对应 `interaction.action_id`。建议给 ID 加插件名前缀。
- `Button.UrlAction` 只打开链接，不触发插件回调，也不受 `action_timeout` 限制。`fallback_text` 用于不支持按钮的平台，不是过期提示。
- `@filter.button_action()` 不指定 ID 时匹配所有按钮回调。此 PR 中原来的 `@filter.button_interaction(...)` 更名为 `@filter.button_action(...)`；事件类型仍为 `ButtonInteraction`，通过 `event.get_button_interaction()` 获取。

## 发送视频消息

```python
from astrbot.api.event import filter, AstrMessageEvent


@filter.command("test")
async def test(self, event: AstrMessageEvent):
    from astrbot.api.message_components import Video

    # fromFileSystem 需要用户的协议端和机器人端处于一个系统中。
    video = Video.fromFileSystem(path="test.mp4")
    # 更通用
    video = Video.fromURL(url="https://example.com/video.mp4")
    yield event.chain_result([video])
```

![发送视频消息](https://files.astrbot.app/docs/source/images/plugin/db93a2bb-671c-4332-b8ba-9a91c35623c2.png)

## 发送群合并转发消息

> 大多数平台都不支持此种消息类型，当前适配情况：OneBot v11

可以按照如下方式发送群合并转发消息。

```py
from astrbot.api.event import filter, AstrMessageEvent


@filter.command("test")
async def test(self, event: AstrMessageEvent):
    from astrbot.api.message_components import Node, Plain, Image

    node = Node(
        uin=905617992,
        name="Soulter",
        content=[Plain("hi"), Image.fromFileSystem("test.jpg")],
    )
    yield event.chain_result([node])
```

![发送群合并转发消息](https://files.astrbot.app/docs/source/images/plugin/image-4.png)
