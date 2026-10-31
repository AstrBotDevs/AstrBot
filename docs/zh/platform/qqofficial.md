# 接入 QQ 官方机器人平台

QQ 官方机器人平台是腾讯官方提供的一个机器人接入平台，允许开发者通过官方接口将机器人接入 QQ 群聊和个人聊天中。

目前主要通过 Webhook 方式接入。

- [Webhook 方式](/platform/qqofficial/webhook)
- [Websockets 方式](/platform/qqofficial/websockets)

## 默认消息格式

在 WebUI 的 `机器人` 页面打开 QQ 官方机器人的配置，找到 **默认使用 Markdown**（原名 **主动消息使用 Markdown**）。此设置控制 WebSocket 和 Webhook 的普通回复及主动消息的默认格式；显式调用 `MessageChain.use_markdown(True/False)` 时，以消息级设置为准。

配置键仍为 `use_markdown`，默认值仍为 `true`。已有配置将此项设为 `false` 时，普通回复也会使用纯文本。
