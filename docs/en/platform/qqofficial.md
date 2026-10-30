# Connect QQ Official Bot

QQ Official Bot is Tencent's official bot platform. It lets you connect bots to QQ group chats and private chats through official APIs.

Currently, the main integration method is Webhook.

- [Webhook Method](/en/platform/qqofficial/webhook)
- [Websockets Method](/en/platform/qqofficial/websockets)

## Default Message Format

In WebUI, open your QQ Official adapter configuration under `Platforms`. **Use Markdown for Proactive Messages → Use Markdown by default** controls the default format for replies and proactive messages in both WebSocket and Webhook adapters. Explicit `MessageChain.use_markdown(True/False)` calls take precedence.

The configuration key remains `use_markdown`, with a default of `true`. Existing configurations with `use_markdown: false` now also send regular replies as plain text.
