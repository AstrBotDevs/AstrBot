
# Connecting to Telegram

## Supported Message Types

> Version v4.15.0.

| Message Type | Receive Support | Send Support | Notes |
| --- | --- | --- | --- |
| Text | Yes | Yes | |
| Image | Yes | Yes | |
| Voice | Yes | Yes | |
| Video | Yes | Yes | |
| File | Yes | Yes | |
| Inline Keyboard | Yes | Yes | Supports button callback events |
| Reply Keyboard | - | Yes | Supports custom reply keyboard, keyboard removal, and force reply |
| Inline Query | Yes | Yes | Plugins can listen for and answer inline queries |

Proactive message push: Supported.

## Interaction Events

The Telegram adapter lets plugins listen for Telegram-specific events such as callback queries, inline queries, chosen inline results, member status changes, member join/leave events, polls, and dice. Register these handlers with the custom filter `@filter.custom_filter(telegram_event_filter(...))`. Common event types include `callback_query`, `inline_query`, `chosen_inline_result`, `chat_member`, `my_chat_member`, `member_joined`, and `member_left`.

These structured events do not enter the regular LLM conversation flow by default. Match them explicitly with `telegram_event_filter(...)` and handle them in your plugin, otherwise a button click or inline/member event may appear to do nothing.

Short button callback example:

```python
from astrbot.api.event import filter, AstrMessageEvent
from astrbot.core.platform.sources.telegram.filters import telegram_event_filter

@filter.custom_filter(telegram_event_filter("callback_query"))
async def on_telegram_button(self, event: AstrMessageEvent):
    data = event.get_interaction_data()
    await event.answer_interaction(f"Received: {data}", show_alert=False)
```

For complete Inline Keyboard, Reply Keyboard, inline query answer, and callback handling examples, see "Telegram-Specific Send Options" in the developer guide.

## 1. Create a Telegram Bot

First, open Telegram and search for `BotFather`. Click `Start`, then send `/newbot` and follow the prompts to enter your bot's name and username.

After successful creation, `BotFather` will provide you with a `token`. Please keep it secure.

If you need to use the bot in group chats, you must disable the bot's [Privacy mode](https://core.telegram.org/bots/features#privacy-mode). Send the `/setprivacy` command to `BotFather`, select your bot, and then choose `Disable`.

## 2. Configure AstrBot

1. Enter the AstrBot admin panel
2. Click `Bots` in the left sidebar
3. In the interface on the right, click `+ Create Bot`
4. Select `telegram`

Fill in the configuration fields that appear:

- ID: Enter any value to distinguish between different messaging platform instances.
- Enable: Check this option.
- Bot Token: Your Telegram bot's `token`.

Please ensure your network environment can access Telegram. You can configure a global proxy in `Configuration -> Other Settings -> HTTP Proxy`, or configure Telegram-specific proxies in the Telegram adapter:

- `telegram_proxy`: Used only for this Telegram adapter's Bot API requests.
- `telegram_get_updates_proxy`: Used only for this Telegram adapter's `getUpdates` polling requests.

### Update Mode

Telegram uses `telegram_update_mode="polling"` by default and receives updates through `getUpdates` polling. You can switch to `telegram_update_mode="webhook"` to use an independent Telegram adapter webhook listener.

Webhook mode requires these settings:

- `telegram_webhook_listen`: Local listen address.
- `telegram_webhook_port`: Local listen port.
- `telegram_webhook_url_path`: Local webhook path.
- `telegram_webhook_url`: HTTPS public URL reachable by Telegram. Required.
- `telegram_webhook_secret_token`: Optional token for verifying Telegram webhook requests.
- `telegram_webhook_drop_pending_updates`: Whether Telegram should drop pending updates when starting webhook mode.

If HTTPS is provided by a reverse proxy such as Nginx or Caddy, `telegram_webhook_cert_path` and `telegram_webhook_key_path` are usually not needed. Set them only when `python-telegram-bot` serves HTTPS directly.

## Command Registration

The Telegram adapter can register AstrBot plugin commands as Telegram Bot Commands:

- `telegram_command_register`: Whether command registration is enabled.
- `telegram_command_auto_refresh`: Whether commands are refreshed at runtime.
- `telegram_command_register_interval`: Auto-refresh interval in seconds.
- `telegram_command_registered_plugins`: Only register commands from selected plugins. Leave empty to register commands from all enabled plugins.
- `telegram_command_scopes`: Scope configs for command registration. The default is `[{"type": "default"}]`.

`telegram_command_scopes` supports these Telegram Bot API scopes: `default`, `all_private_chats`, `all_group_chats`, `all_chat_administrators`, `chat`, `chat_administrators`, and `chat_member`. `chat` and `chat_administrators` require `chat_id`; `chat_member` requires both `chat_id` and `user_id`. Each scope can also set `language_code`.

Example:

```json
[
  {"type": "default", "language_code": "en"},
  {"type": "chat", "chat_id": 123456789}
]
```

Telegram supports at most 100 commands per scope. If registration fails, use `telegram_command_registered_plugins` to narrow the plugin set.

## Streaming Output

The Telegram platform supports streaming output. Enable the "Streaming Output" switch in "AI Configuration" -> "Other Settings".

### Private Chat Streaming

In private chats, AstrBot uses the `sendMessageDraft` API (added in Telegram Bot API v9.3) for streaming output. This displays a "typing" draft preview animation in the chat interface, creating a more natural "typewriter" effect. It avoids issues with the traditional approach such as message flickering, push notification interference, and API edit frequency limits.

### Group Chat Streaming

In group chats, since the `sendMessageDraft` API only supports private chats, AstrBot automatically falls back to the traditional `send_message` + `edit_message_text` approach.

:::warning
`sendMessageDraft` requires `python-telegram-bot>=22.6`.
:::
