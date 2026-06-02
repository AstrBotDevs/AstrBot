
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

Proactive message push: Supported.

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
