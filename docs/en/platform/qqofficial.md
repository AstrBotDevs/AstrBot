# Connect QQ Official Bot

QQ Official Bot is Tencent's official bot platform. It lets you connect bots to QQ group chats and private chats through official APIs.

Currently, the main integration method is Webhook.

- [Webhook Method](/en/platform/qqofficial/webhook)
- [Websockets Method](/en/platform/qqofficial/websockets)

## Streaming Replies

QQ C2C private chats support native streaming; group chats and guild channels do not. With streaming enabled, groups and channels follow the unsupported-platform setting: **Real-time segmented replies** sends text at sentence-ending punctuation and flushes unfinished text before tool status messages; **Disable streaming replies** sends each complete model reply after it is generated.

**Merge Agent intermediate messages** combines model replies from the same turn in non-streaming mode. It does not affect real-time segmented group replies. Webhook and Websockets connections behave the same way.
