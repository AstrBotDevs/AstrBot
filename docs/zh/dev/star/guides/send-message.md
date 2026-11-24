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

### 需要平台的发送结果时

`send_message()` 返回的 `True` 只表示找到了消息平台。想获取平台返回的消息 ID 或跟踪键，使用 `send_message_with_receipt()`：

```python
receipt = await self.context.send_message_with_receipt(
    event.unified_msg_origin,
    MessageChain().message("Hello!"),
)

if receipt is False:
    print("没有找到消息平台，未发送")
elif receipt is None:
    print("结果不确定，不要直接重发")
else:
    print(receipt.message_ids)
    print(receipt.tracking_keys)
```

返回值取决于适配器能确认哪些发送结果。

| 返回值 | 你该怎么做 |
| --- | --- |
| `MessageSendReceipt` | 平台已受理整条消息。按需读取平台返回的 `message_ids`、`tracking_keys` 或 `reference_ids`。 |
| `None` | 结果不确定。消息可能已经发出，**不要直接重发**，否则可能重复。 |
| `False` | 没有找到匹配的消息平台，本次没有发送。 |

目前支持返回回执的场景：

- 钉钉：完整的纯文本消息，包括先合并再发送的流式消息。
- 企业微信应用：发给单个成员的完整纯文本消息，包括先合并再发送的流式消息。
- QQ 官方机器人：在群聊或私聊中用 `event.send()` 回复的纯文本消息。QQ 有时还会返回供客户端显示引用的标识。
- 飞书：纯文本消息和交互按钮卡片。完整的卡片回执包含该卡片的消息 ID。
- 其他平台或消息类型：通常返回 `None`。

回执说明平台已受理，请另查送达或已读状态。适配器能确认整条消息都被拒绝时，可以抛出 `MessageSendRejected`，其 `reason` 可说明回复窗口已过期、缺少权限等原因。网络中断或只有部分内容成功时，整条消息的结果仍然未知。保留原请求，核对后再决定是否重发。

### 稍后回复原来的消息

会话标识可以定位聊天。要在 QQ 官方机器人或飞书上回复聊天中的某一条消息，插件可以在收件时保存这条消息的回复上下文。

```python
import json
from dataclasses import asdict

from astrbot.api.event import MessageChain
from astrbot.api.platform import MessageReplyContext

def save_reply_target(self, event):
    platform = self.context.get_platform_inst(event.get_platform_id())
    if platform is not None:
        return json.dumps(asdict(platform.get_reply_context(event)))

async def send_saved_reply(self, saved, text):
    target = MessageReplyContext(**json.loads(saved))
    platform = self.context.get_platform_inst(target.platform_id)
    if platform is not None:
        return await platform.create_event(target).send(MessageChain().message(text))
```

上下文保存原平台账号、发送人、会话和消息号。发出回复前按当前权限核实是否可以回信。QQ 原消息带有引用标识时，在消息链中加入 `Reply(id=target.message_id)` 即可显示引用。若 QQ 明确拒绝过期的被动回复，且插件获准对同一聊天主动发消息，可用 `dataclasses.replace(target, mode="proactive")` 单独发起这次通知。

发出飞书 `ActionRow` 按钮卡片时，把卡片回执中的 `receipt.message_ids[0]` 与回复上下文一起保存。稍后调用 `await platform.update_message(target, card_message_id, replacement_chain)` 就能更新原卡。新内容可包含文字和按钮行，也可只保留文字以移除按钮。回复原来那条人类消息时使用 `target.message_id`。

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

目前的平台支持情况：

| 支持方式 | 平台 |
| --- | --- |
| 回调按钮和链接按钮 | QQ 官方机器人、Telegram、飞书（Lark）、钉钉、Discord、Slack、LINE、KOOK、Satori、企业微信（含微信客服）、企业微信 AI Bot、WebChat |
| 回调按钮，URL 动作显示为普通链接 | Mattermost |
| 文字或链接回退，不触发按钮回调 | OneBot v11（aiocqhttp）、Misskey、微信公众号、微信个人号（weixin_oc） |

Satori 的按钮支持取决于所连接的平台和客户端。Mattermost 的回调按钮需要配置可由 Mattermost 服务访问的回调地址。对于使用文字回退的平台，建议设置 `fallback_text`，说明可用的文字指令。

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
- `@filter.button_action()` 不指定 ID 时匹配所有按钮回调。通过 `event.get_button_interaction()` 获取 `ButtonInteraction` 事件组件。

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
