# 消息的发送

## 被动消息

被动消息指的是机器人被动回复消息。

```python
@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent):
    yield event.plain_result("Hello!")
    yield event.plain_result("你好！")

    yield event.image_result("path/to/image.jpg") # 发送图片
    yield event.image_result("https://example.com/image.jpg") # 发送 URL 图片，务必以 http 或 https 开头
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
        Comp.At(qq=event.get_sender_id()), # At 消息发送者
        Comp.Plain("来看这个图："),
        Comp.Image.fromURL("https://example.com/image.jpg"), # 从 URL 发送图片
        Comp.Image.fromFileSystem("path/to/image.jpg"), # 从本地文件目录发送图片
        Comp.Plain("这是一个图片。")
    ]
    yield event.chain_result(chain)
```

上面构建了一个 `message chain`，也就是消息链，最终会发送一条包含了图片和文字的消息，并且保留顺序。

> [!TIP]
> 在 aiocqhttp 消息适配器中，对于 `plain` 类型的消息，在发送中会使用 `strip()` 方法去除空格及换行符，可以在消息前后添加零宽空格 `\u200b` 以解决这个问题。

类似地，

**文件 File**

```py
Comp.File(file="path/to/file.txt", name="file.txt") # 部分平台不支持
```

**语音 Record**

```py
path = "path/to/record.wav" # 暂时只接受 wav 格式，其他格式请自行转换
Comp.Record(file=path, url=path)
```

**视频 Video**

```py
path = "path/to/video.mp4"
Comp.Video.fromFileSystem(path=path)
Comp.Video.fromURL(url="https://example.com/video.mp4")
```

## 发送视频消息

```python
from astrbot.api.event import filter, AstrMessageEvent

@filter.command("test")
async def test(self, event: AstrMessageEvent):
    from astrbot.api.message_components import Video
    # fromFileSystem 需要用户的协议端和机器人端处于一个系统中。
    video = Video.fromFileSystem(
        path="test.mp4"
    )
    # 更通用
    video = Video.fromURL(
        url="https://example.com/video.mp4"
    )
    yield event.chain_result([video])
```

![发送视频消息](https://files.astrbot.app/docs/source/images/plugin/db93a2bb-671c-4332-b8ba-9a91c35623c2.png)

## Telegram 专属发送选项

Telegram 适配器支持在 `MessageChain` 中加入 Telegram 专属组件，用于控制 Markdown/HTML 解析、链接预览和 Inline Keyboard。这些组件同样适用于 `self.context.send_message(unified_msg_origin, chains)` 主动发送。

```python
from astrbot.api.event import MessageChain, filter, AstrMessageEvent
from astrbot.core.platform.sources.telegram.components import (
    TelegramInlineButton,
    TelegramInlineKeyboard,
    TelegramMessageOptions,
    TelegramReplyKeyboard,
    TelegramKeyboardButton,
    TelegramRemoveKeyboard,
    TelegramForceReply,
)

@filter.command("review")
async def review(self, event: AstrMessageEvent):
    chain = MessageChain()
    chain.message("**请选择审批动作**\n\n[查看详情](https://example.com/item/42)")
    chain.chain.append(
        TelegramMessageOptions(
            parse_mode="MarkdownV2",
            link_preview_is_disabled=False,
            link_preview_url="https://example.com/item/42",
            link_preview_prefer_large_media=True,
            link_preview_show_above_text=True,
        )
    )
    chain.chain.append(
        TelegramInlineKeyboard(
            [
                [
                    TelegramInlineButton("通过", callback_data="approve:42"),
                    TelegramInlineButton("拒绝", callback_data="reject:42"),
                ],
                [TelegramInlineButton("打开网页", url="https://example.com/item/42")],
            ]
        )
    )
    yield event.chain_result(chain)
```

`TelegramMessageOptions.parse_mode` 支持 `MarkdownV2`、`Markdown`、`HTML`，也可以传 `plaintext`、`plain` 或 `none` 发送纯文本。链接预览支持 Telegram `LinkPreviewOptions` 的所有字段：是否禁用预览、预览 URL、小/大媒体偏好、是否显示在文本上方。

`TelegramInlineButton` 每个按钮必须且只能设置一种动作。支持 `url`、`callback_data`、`login_url`、`web_app`、`switch_inline_query`、`switch_inline_query_current_chat`、`switch_inline_query_chosen_chat`、`copy_text`、`callback_game`、`pay`，以及 Bot API 支持时的 `style`、`icon_custom_emoji_id`。`callback_data` 必须是 1-64 UTF-8 字节。

也可以发送 Telegram Reply Keyboard、移除键盘或强制用户回复：

```python
chain = MessageChain()
chain.message("请选择联系方式")
chain.chain.append(
    TelegramReplyKeyboard(
        [[TelegramKeyboardButton("分享手机号", request_contact=True), "取消"]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="请选择",
    )
)
yield event.chain_result(chain)

remove = MessageChain()
remove.message("已取消")
remove.chain.append(TelegramRemoveKeyboard(selective=True))
yield event.chain_result(remove)

force = MessageChain()
force.message("请回复审批理由")
force.chain.append(TelegramForceReply(input_field_placeholder="理由"))
yield event.chain_result(force)
```

插件可以通过 Telegram 自定义过滤器监听按钮回调，实现审批、确认、翻页等交互。关键是使用 `@filter.custom_filter(telegram_event_filter(...))`，否则普通命令过滤器不会专门匹配 Telegram 的 callback/inline/member 类事件：

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.platform.sources.telegram.filters import telegram_event_filter

@filter.custom_filter(telegram_event_filter("callback_query"))
async def on_telegram_button(self, event: AstrMessageEvent):
    action = event.get_interaction_data()
    await event.ack_interaction()

    if action == "approve:42":
        yield event.plain_result("已通过")
        return

    if action == "reject:42":
        await event.answer_interaction("已拒绝", show_alert=True)
        return

    await event.answer_interaction(f"未知操作：{action}", show_alert=True)
```

`event.ack_interaction()` 可以快速确认回调，避免 Telegram 客户端一直显示按钮加载状态；`event.answer_interaction(text, show_alert=False)` 可以回应 callback query，`show_alert=True` 时会弹出提示框。`event.get_interaction_custom_id()` 与 `event.get_interaction_data()` 都会返回 Telegram 的 `callback_data`，也就是上面 `TelegramInlineButton(..., callback_data="approve:42")` 中设置的值。

同一个过滤器入口也可以监听 Telegram inline/member 类事件。处理这些事件时，通常需要从 `event.message_obj.raw_message` 读取 Telegram 原始 `Update` 对象中的字段：

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.platform.sources.telegram.components import (
    TelegramInlineQueryResult,
    TelegramInputTextMessageContent,
)
from astrbot.core.platform.sources.telegram.filters import telegram_event_filter

@filter.custom_filter(telegram_event_filter("inline_query"))
async def on_telegram_inline_query(self, event: AstrMessageEvent):
    query = event.get_inline_query_text()
    await event.answer_inline_query(
        [
            TelegramInlineQueryResult(
                "article",
                id="echo",
                title=f"发送：{query}",
                input_message_content=TelegramInputTextMessageContent(query or "空查询"),
            )
        ],
        cache_time=0,
        is_personal=True,
    )

@filter.custom_filter(telegram_event_filter("chat_member"))
async def on_telegram_chat_member(self, event: AstrMessageEvent):
    member_update = event.get_chat_member_update()
    yield event.plain_result(f"成员状态变更：{member_update.new_chat_member.status}")
```

可用事件类型包括 `callback_query`、`inline_query`、`chosen_inline_result`、`chat_member`、`my_chat_member`、`member_joined`、`member_left`、`poll`、`dice`。按钮回调是最常见的交互增强场景，建议将 `callback_data` 设计成 `动作:资源ID` 这类可解析格式，并在处理函数里显式分支处理。

如果 AstrBot 尚未封装某个 Telegram Bot API，可以在 Telegram 事件里用 `event.get_telegram_client()` 获取只读暴露的 `python-telegram-bot` Bot 客户端自行调用；原始 `Update` 可通过 `event.get_telegram_update()` 获取。

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
        content=[
            Plain("hi"),
            Image.fromFileSystem("test.jpg")
        ]
    )
    yield event.chain_result([node])
```

![发送群合并转发消息](https://files.astrbot.app/docs/source/images/plugin/image-4.png)
