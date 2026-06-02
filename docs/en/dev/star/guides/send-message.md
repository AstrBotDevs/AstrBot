# Sending Messages

## Passive Messages

Passive messages refer to the bot responding to messages reactively.

```python
@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent):
    yield event.plain_result("Hello!")
    yield event.plain_result("你好！")

    yield event.image_result("path/to/image.jpg") # Send an image
    yield event.image_result("https://example.com/image.jpg") # Send an image from URL, must start with http or https
```

## Active Messages

Active messages refer to the bot proactively pushing messages. Some platforms may not support active message sending.

For scheduled tasks or when you don't want to send messages immediately, you can use `event.unified_msg_origin` to get a string and store it, then use `self.context.send_message(unified_msg_origin, chains)` to send messages when needed.

```python
from astrbot.api.event import MessageChain

@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent):
    umo = event.unified_msg_origin
    message_chain = MessageChain().message("Hello!").file_image("path/to/image.jpg")
    await self.context.send_message(event.unified_msg_origin, message_chain)
```

With this feature, you can store the `unified_msg_origin` and send messages when needed.

> [!TIP]
> About unified_msg_origin.
> `unified_msg_origin` is a string that records the unique ID of a session. AstrBot uses it to identify which messaging platform and which session it belongs to. This allows messages to be sent to the correct session when using `send_message`. For more about MessageChain, see the next section.

## Rich Media Messages

AstrBot supports sending rich media messages such as images, audio, videos, etc. Use `MessageChain` to construct messages.

```python
import astrbot.api.message_components as Comp

@filter.command("helloworld")
async def helloworld(self, event: AstrMessageEvent):
    chain = [
        Comp.At(qq=event.get_sender_id()), # Mention the message sender
        Comp.Plain("Check out this image:"),
        Comp.Image.fromURL("https://example.com/image.jpg"), # Send image from URL
        Comp.Image.fromFileSystem("path/to/image.jpg"), # Send image from local file system
        Comp.Plain("This is an image.")
    ]
    yield event.chain_result(chain)
```

The above constructs a `message chain`, which will ultimately send a message containing both images and text while preserving the order.

> [!TIP]
> In the aiocqhttp message adapter, for messages of type `plain`, the `strip()` method is used during sending to remove spaces and line breaks. You can add zero-width spaces `\u200b` before and after the message to resolve this issue.

Similarly,

**File**

```py
Comp.File(file="path/to/file.txt", name="file.txt") # Not supported by some platforms
```

**Audio Record**

```py
path = "path/to/record.wav" # Currently only accepts wav format, please convert other formats yourself
Comp.Record(file=path, url=path)
```

**Video**

```py
path = "path/to/video.mp4"
Comp.Video.fromFileSystem(path=path)
Comp.Video.fromURL(url="https://example.com/video.mp4")
```

## Sending Video Messages

```python
from astrbot.api.event import filter, AstrMessageEvent

@filter.command("test")
async def test(self, event: AstrMessageEvent):
    from astrbot.api.message_components import Video
    # fromFileSystem requires the user's protocol client and bot to be on the same system.
    video = Video.fromFileSystem(
        path="test.mp4"
    )
    # More universal approach
    video = Video.fromURL(
        url="https://example.com/video.mp4"
    )
    yield event.chain_result([video])
```

![Sending video messages](https://files.astrbot.app/docs/source/images/plugin/db93a2bb-671c-4332-b8ba-9a91c35623c2.png)

## Telegram-Specific Send Options

The Telegram adapter supports Telegram-specific components in `MessageChain` for Markdown/HTML parsing, link previews, and Inline Keyboard. These components also work with proactive sends through `self.context.send_message(unified_msg_origin, chains)`.

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
    chain.message("**Choose an approval action**\n\n[Open details](https://example.com/item/42)")
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
                    TelegramInlineButton("Approve", callback_data="approve:42"),
                    TelegramInlineButton("Reject", callback_data="reject:42"),
                ],
                [TelegramInlineButton("Open Web Page", url="https://example.com/item/42")],
            ]
        )
    )
    yield event.chain_result(chain)
```

`TelegramMessageOptions.parse_mode` supports `MarkdownV2`, `Markdown`, and `HTML`. You can also pass `plaintext`, `plain`, or `none` to send plain text. Link previews support every Telegram `LinkPreviewOptions` field: disabled state, preview URL, small/large media preference, and whether the preview is shown above the text.

Each `TelegramInlineButton` must set exactly one action. Supported actions are `url`, `callback_data`, `login_url`, `web_app`, `switch_inline_query`, `switch_inline_query_current_chat`, `switch_inline_query_chosen_chat`, `copy_text`, `callback_game`, and `pay`, plus `style` and `icon_custom_emoji_id` when supported by the Bot API. `callback_data` must be 1-64 UTF-8 bytes.

You can also send Telegram Reply Keyboard, remove an existing keyboard, or force a reply:

```python
chain = MessageChain()
chain.message("Choose a contact method")
chain.chain.append(
    TelegramReplyKeyboard(
        [[TelegramKeyboardButton("Share phone", request_contact=True), "Cancel"]],
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Choose",
    )
)
yield event.chain_result(chain)

remove = MessageChain()
remove.message("Cancelled")
remove.chain.append(TelegramRemoveKeyboard(selective=True))
yield event.chain_result(remove)

force = MessageChain()
force.message("Please reply with the approval reason")
force.chain.append(TelegramForceReply(input_field_placeholder="Reason"))
yield event.chain_result(force)
```

Plugins can listen for button callbacks with the Telegram custom filter to build approval, confirmation, pagination, and similar flows. The important part is `@filter.custom_filter(telegram_event_filter(...))`; regular command filters do not specifically match Telegram callback/inline/member events:

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.platform.sources.telegram.filters import telegram_event_filter

@filter.custom_filter(telegram_event_filter("callback_query"))
async def on_telegram_button(self, event: AstrMessageEvent):
    action = event.get_interaction_data()
    await event.ack_interaction()

    if action == "approve:42":
        yield event.plain_result("Approved")
        return

    if action == "reject:42":
        await event.answer_interaction("Rejected", show_alert=True)
        return

    await event.answer_interaction(f"Unknown action: {action}", show_alert=True)
```

Use `event.ack_interaction()` for a quick acknowledgment so the Telegram client stops showing the button loading state. Use `event.answer_interaction(text, show_alert=False)` to answer the callback query; `show_alert=True` shows an alert dialog. `event.get_interaction_custom_id()` and `event.get_interaction_data()` both return Telegram `callback_data`, which is the value set by `TelegramInlineButton(..., callback_data="approve:42")` above.

The same filter entrypoint can also listen for Telegram inline/member events. For these events, read the original Telegram `Update` object from `event.message_obj.raw_message`:

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
                title=f"Send: {query}",
                input_message_content=TelegramInputTextMessageContent(query or "Empty query"),
            )
        ],
        cache_time=0,
        is_personal=True,
    )

@filter.custom_filter(telegram_event_filter("chat_member"))
async def on_telegram_chat_member(self, event: AstrMessageEvent):
    member_update = event.get_chat_member_update()
    yield event.plain_result(f"Member status changed: {member_update.new_chat_member.status}")
```

Available event types include `callback_query`, `inline_query`, `chosen_inline_result`, `chat_member`, `my_chat_member`, `member_joined`, `member_left`, `poll`, and `dice`. Button callbacks are the most common interaction enhancement case. A practical pattern is to encode `callback_data` as `action:resource_id` and branch explicitly in the handler.

If AstrBot has not wrapped a Telegram Bot API method yet, Telegram events expose `event.get_telegram_client()` for direct `python-telegram-bot` Bot calls. Use `event.get_telegram_update()` when you need the raw Telegram `Update`.

## Sending Group Forward Messages

> Most platforms do not support this message type. Current support: OneBot v11

You can send group forward messages as follows.

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

![Sending group forward messages](https://files.astrbot.app/docs/source/images/plugin/image-4.png)
