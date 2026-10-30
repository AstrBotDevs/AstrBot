# Connect QQ Official Bot

QQ Official Bot is Tencent's official bot platform. It lets you connect bots to QQ group chats and private chats through official APIs.

Currently, the main integration method is Webhook.

- [Webhook Method](/en/platform/qqofficial/webhook)
- [Websockets Method](/en/platform/qqofficial/websockets)

## Default Message Format

In WebUI, open your QQ Official adapter configuration under `Platforms`. **Use Markdown for Proactive Messages → Use Markdown by default** now controls regular AI replies, plugin replies, and proactive messages for both WebSocket and Webhook adapters.

- When enabled, messages without an explicit format use Markdown; when disabled, they use plain text.
- Explicit `MessageChain.use_markdown(True)` or `MessageChain.use_markdown(False)` calls take precedence. `None` follows the platform setting.
- For plain-text C2C replies, generated streaming content is buffered and sent normally at the end of a segment or before a tool call. Markdown replies retain native streaming.
- Images, voice, video, and files retain their existing media delivery behavior.

The configuration key remains `use_markdown`, with a default of `true`; no configuration migration is needed. **Existing configurations with `use_markdown: false` now also send regular replies as plain text**, instead of affecting only proactive messages.
